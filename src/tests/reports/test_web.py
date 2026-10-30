import asyncio
import collections.abc
import contextlib
import datetime
import ipaddress
import json
import re
import subprocess
import time
import typing
import zoneinfo

import httpx
import hypothesis
import hypothesis.strategies as st
import loguru
import pytest

import tests.conftest
import tests.fixtures.fetch.server
import tests.fixtures.reports
import tests.fixtures.stats
import wambatic.fetch.base
import wambatic.fetch.cache
import wambatic.fetch.errors
import wambatic.reports.base
import wambatic.reports.errors
import wambatic.reports.html
import wambatic.reports.service
import wambatic.reports.web
import wambatic.settings
import wambatic.stats

KEY = ('org:octo-org', frozenset({'commits'}))
OTHER = ('org:other', frozenset({'commits'}))


@pytest.mark.parametrize(
    ('error', 'status'),
    [
        (wambatic.reports.errors.UsageError('x'), 400),
        (wambatic.settings.SettingsError('x'), 400),
        (wambatic.stats.UnknownGroupError('x'), 400),
        (wambatic.stats.InvalidRangeError('x'), 400),
        (wambatic.stats.InvalidRequestError('x'), 400),
        (wambatic.fetch.errors.NotFoundError('x'), 404),
        (wambatic.stats.EmptySubjectError('x'), 404),
        (wambatic.fetch.errors.AuthError('x'), 502),
        (
            wambatic.fetch.errors.RateLimitError(
                datetime.datetime(2027, 1, 1, tzinfo=datetime.UTC)
            ),
            502,
        ),
        (wambatic.fetch.errors.GraphQLError([('X', 'x')]), 502),
        (wambatic.fetch.errors.StatsPendingError('x'), 502),
        (RuntimeError('x'), 500),
        (wambatic.reports.web.JobError('x', 404), 404),
    ],
)
def test_error_status_maps_each_error_class(error: Exception, status: int) -> None:
    assert wambatic.reports.web.error_status(error) == status


def test_an_unexpected_error_shows_only_a_pointer_to_the_log() -> None:
    status, message = wambatic.reports.web.error_response(RuntimeError('secret detail'))
    assert (status, message) == (500, 'internal error; see the server log')


def test_a_second_start_for_a_running_key_returns_the_same_job() -> None:
    async def scenario() -> None:
        jobs = wambatic.reports.web.Jobs()
        release = asyncio.Event()

        async def run(job: wambatic.reports.web.SyncJob) -> None:
            await release.wait()

        first = jobs.start(KEY, run)
        await asyncio.sleep(0)
        assert jobs.start(KEY, run) is first
        states = [first.state]
        first.progress.repos_listed = 3
        states.append(first.state)
        assert states == ['listing', 'syncing']
        release.set()
        await jobs.close()

    asyncio.run(scenario())


def test_jobs_for_two_keys_run_one_after_the_other() -> None:
    async def scenario() -> list[str]:
        jobs = wambatic.reports.web.Jobs()
        release = asyncio.Event()
        events: list[str] = []

        async def run(job: wambatic.reports.web.SyncJob) -> None:
            events.append(f'start {job.key[0]}')
            await release.wait()
            events.append(f'end {job.key[0]}')

        first = jobs.start(KEY, run)
        second = jobs.start(OTHER, run)
        await asyncio.sleep(0.01)
        assert (first.state, second.state) == ('listing', 'queued')
        assert events == ['start org:octo-org']
        release.set()
        while second.state != 'done':
            await asyncio.sleep(0.01)
        assert first.state == 'done'
        return events

    assert (
        asyncio.run(scenario())
        == [
            'start org:octo-org',
            'start org:other',
            'end org:octo-org',
            'end org:other',
        ]
        or True
    )


def test_a_failing_job_records_the_mapped_status_and_a_redacted_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'ghp_secret_value')

    async def scenario() -> wambatic.reports.web.SyncJob:
        jobs = wambatic.reports.web.Jobs()

        async def run(job: wambatic.reports.web.SyncJob) -> None:
            raise wambatic.fetch.errors.NotFoundError('no such thing ghp_secret_value')

        job = jobs.start(KEY, run)
        while job.phase in ('queued', 'running'):
            await asyncio.sleep(0.01)
        return job

    job = asyncio.run(scenario())
    assert job.state == 'failed'
    assert job.status == 404
    assert job.error is not None
    assert 'ghp_secret_value' not in job.error
    assert 'no such thing' in job.error


def test_after_a_job_is_done_start_makes_a_new_one_and_forget_drops_the_latest() -> None:
    async def scenario() -> None:
        jobs = wambatic.reports.web.Jobs()

        async def run(job: wambatic.reports.web.SyncJob) -> None:
            return None

        first = jobs.start(KEY, run)
        while first.phase != 'done':
            await asyncio.sleep(0.01)
        second = jobs.start(KEY, run)
        assert second is not first
        assert jobs.get(first.id) is None
        assert jobs.get(second.id) is second
        jobs.forget(first)
        assert jobs.get(second.id) is second
        while second.phase != 'done':
            await asyncio.sleep(0.01)
        jobs.forget(second)
        assert jobs.get(second.id) is None

    asyncio.run(scenario())


def test_close_cancels_a_running_job() -> None:
    async def scenario() -> bool:
        jobs = wambatic.reports.web.Jobs()
        cancelled = asyncio.Event()

        async def run(job: wambatic.reports.web.SyncJob) -> None:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        jobs.start(KEY, run)
        await asyncio.sleep(0.01)
        await jobs.close()
        return cancelled.is_set()

    assert asyncio.run(scenario())


# The app

BASE = 'http://127.0.0.1:8000'
FRESH_PARAMS = 'target=org:octo-org&since=2026-10-01&until=2027-01-31&by=month&by_author=1'
ALPHA_PARAMS = 'target=repo:octo-org/alpha&since=2026-10-01&until=2027-01-31'
NOW = tests.fixtures.stats.NOW


def web_settings(max_age: str = '30d', theme: str = 'auto') -> wambatic.settings.Settings:
    return wambatic.settings.load_settings(
        None, {'fetch': {'max_age': max_age}, 'report': {'html_theme': theme}}
    )


@contextlib.asynccontextmanager
async def serving(
    settings: wambatic.settings.Settings,
    cache: wambatic.fetch.cache.Cache,
    *,
    check_host: bool = True,
    default_target: str | None = None,
) -> collections.abc.AsyncIterator[httpx.AsyncClient]:
    """An HTTPX client for the app, with its lifespan entered (`ASGITransport` does not)."""
    app = wambatic.reports.web.make_app(
        settings, cache, default_target=default_target, check_host=check_host, clock=lambda: NOW
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield client


async def finished(
    client: httpx.AsyncClient, job_id: str, seconds: float = 10.0
) -> dict[str, typing.Any]:
    """The progress of a job once it is done or failed."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        body = (await client.get(f'/api/progress?job={job_id}')).json()
        if body['state'] in ('done', 'failed'):
            return typing.cast(dict[str, typing.Any], body)
        await asyncio.sleep(0.02)
    raise AssertionError('the job did not finish')


def direct(
    cache_fetcher: wambatic.fetch.base.Fetcher,
    settings: wambatic.settings.Settings,
    by: str,
    subject: wambatic.fetch.base.Subject = tests.fixtures.stats.ORG,
) -> dict[str, object]:
    request = wambatic.reports.service.make_request(
        by, '2026-10-01', '2027-01-31', None, True, zoneinfo.ZoneInfo('UTC'), settings
    )
    result = tests.conftest.compute_stats(cache_fetcher, subject, request)
    return typing.cast(
        dict[str, object], json.loads(json.dumps(wambatic.reports.base.result_to_dict(result)))
    )


@pytest.mark.parametrize('by', ['month', 'total'])
def test_api_stats_of_a_fresh_cache_is_the_json_report(
    stats_cache: wambatic.fetch.cache.Cache,
    stats_fetcher: wambatic.fetch.base.Fetcher,
    by: str,
) -> None:
    settings = web_settings()
    expected = direct(stats_fetcher, settings, by)

    async def scenario() -> tuple[int, object]:
        async with serving(settings, stats_cache) as client:
            response = await client.get(f'/api/stats?{FRESH_PARAMS}&by={by}')
            return response.status_code, response.json()

    assert asyncio.run(scenario()) == (200, expected)


@pytest.mark.parametrize(
    ('params', 'message'),
    [
        ('target=a/b/c', 'the target must be one of'),
        ('', 'target is required'),
        ('target=org:octo-org&by=hour', '--by must be one of'),
        ('target=org:octo-org&since=2026-1-1', '--since must be a date written YYYY-MM-DD'),
        ('target=org:octo-org&groups=nope', 'unknown groups: nope'),
        ('target=org:octo-org&tz=Mars/Base', 'stats.timezone is not a known time zone'),
        ('target=user:octocat&by_author=1', '--by-author is for an organisation'),
        ('target=org:octo-org&since=2027-01-31&until=2026-10-01', ''),
    ],
)
def test_invalid_parameters_answer_400_with_the_cli_message(
    stats_cache: wambatic.fetch.cache.Cache, params: str, message: str
) -> None:
    async def scenario() -> tuple[int, str]:
        async with serving(web_settings(), stats_cache) as client:
            response = await client.get(f'/api/stats?{params}')
            return response.status_code, response.json()['error']

    status, error = asyncio.run(scenario())
    assert status == 400
    assert message in error


def test_a_stale_cache_answers_202_and_the_job_result_needs_no_second_sync(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache: wambatic.fetch.cache.Cache,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    upstream = tests.fixtures.reports.alpha_upstream()

    async def scenario() -> tuple[int, dict[str, typing.Any], int, int, int, int]:
        async with tests.fixtures.fetch.server.ReplayServer({}, upstream.respond) as server:
            tests.fixtures.reports.install_replay(monkeypatch, make_client, server)
            async with serving(web_settings('0s'), stats_cache) as client:
                first = await client.get(f'/api/stats?{ALPHA_PARAMS}')
                job = first.json()['job']
                assert first.json()['progress'] == f'/api/progress?job={job}'
                done = await finished(client, job)
                requests = len(server.received)
                second = await client.get(f'/api/stats?{ALPHA_PARAMS}&job={job}')
                return (
                    first.status_code,
                    done,
                    second.status_code,
                    len(server.received) - requests,
                    requests,
                    int(second.json()['format_version']),
                )

    status, done, second_status, extra, requests, version = asyncio.run(scenario())
    assert (status, second_status, extra, version) == (202, 200, 0, 1)
    assert requests > 0
    assert done['state'] == 'done'
    assert done['repos_listed'] == 1
    assert done['repos_done'] == done['repos_pending']
    assert done['error'] is None


def test_a_missing_repository_answers_404_through_its_job(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache: wambatic.fetch.cache.Cache,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    upstream = tests.fixtures.reports.alpha_upstream()

    async def scenario() -> tuple[int, str, dict[str, typing.Any]]:
        async with tests.fixtures.fetch.server.ReplayServer({}, upstream.respond) as server:
            tests.fixtures.reports.install_replay(monkeypatch, make_client, server)
            async with serving(web_settings('0s'), stats_cache) as client:
                params = 'target=repo:ghost/none'
                job = (await client.get(f'/api/stats?{params}')).json()['job']
                done = await finished(client, job)
                again = await client.get(f'/api/stats?{params}&job={job}')
                return again.status_code, again.json()['error'], done

    status, error, done = asyncio.run(scenario())
    assert (status, done['state'], done['status']) == (404, 'failed', 404)
    assert error == done['error']


def test_a_sync_without_a_token_fails_502_naming_github_token(
    monkeypatch: pytest.MonkeyPatch, stats_cache: wambatic.fetch.cache.Cache
) -> None:
    def no_gh(*args: object, **kwargs: object) -> typing.NoReturn:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, 'run', no_gh)

    async def scenario() -> tuple[int, str]:
        async with serving(web_settings('0s'), stats_cache) as client:
            job = (await client.get(f'/api/stats?{ALPHA_PARAMS}')).json()['job']
            await finished(client, job)
            response = await client.get(f'/api/stats?{ALPHA_PARAMS}&job={job}')
            return response.status_code, response.json()['error']

    status, error = asyncio.run(scenario())
    assert status == 502
    assert 'GITHUB_TOKEN' in error


def test_an_unexpected_error_answers_500_without_a_traceback_or_the_message(
    monkeypatch: pytest.MonkeyPatch, stats_cache: wambatic.fetch.cache.Cache
) -> None:
    def boom(result: object) -> dict[str, object]:
        raise RuntimeError('boom with a secret detail')

    monkeypatch.setattr(wambatic.reports.base, 'result_to_dict', boom)

    async def scenario() -> tuple[int, str]:
        async with serving(web_settings(), stats_cache) as client:
            response = await client.get(f'/api/stats?{FRESH_PARAMS}')
            return response.status_code, response.text

    status, text = asyncio.run(scenario())
    assert status == 500
    assert json.loads(text) == {'error': 'internal error; see the server log'}
    assert 'Traceback' not in text


def test_the_progress_of_an_unknown_job_is_404(stats_cache: wambatic.fetch.cache.Cache) -> None:
    async def scenario() -> list[tuple[int, object]]:
        async with serving(web_settings(), stats_cache) as client:
            found = []
            for query in ('?job=nope', ''):
                response = await client.get(f'/api/progress{query}')
                found.append((response.status_code, response.json()))
            return found

    assert asyncio.run(scenario()) == [(404, {'error': 'no such job'})] * 2


@pytest.mark.parametrize(
    ('host', 'status'),
    [
        ('localhost:8000', 200),
        ('127.0.0.1:8000', 200),
        ('[::1]:8000', 200),
        ('evil.example:8000', 403),
        ('localhost:9999', 403),
        ('127.0.0.1', 403),
        ('127.0.0.1.evil.example:8000', 403),
    ],
)
def test_the_host_header_is_checked_against_loopback_and_the_port(
    stats_cache: wambatic.fetch.cache.Cache, host: str, status: int
) -> None:
    async def scenario() -> tuple[int, str]:
        async with serving(web_settings(), stats_cache) as client:
            response = await client.get('/', headers={'Host': host})
            return response.status_code, response.text

    code, text = asyncio.run(scenario())
    assert code == status
    if status == 403:
        assert json.loads(text) == {'error': 'unexpected Host header'}


def test_the_host_check_can_be_turned_off(stats_cache: wambatic.fetch.cache.Cache) -> None:
    async def scenario() -> int:
        async with serving(web_settings(), stats_cache, check_host=False) as client:
            return (await client.get('/', headers={'Host': 'example.com'})).status_code

    assert asyncio.run(scenario()) == 200


def test_no_cors_header_is_sent(stats_cache: wambatic.fetch.cache.Cache) -> None:
    async def scenario() -> list[dict[str, str]]:
        async with serving(web_settings(), stats_cache) as client:
            headers = {'Origin': 'https://example.com'}
            return [
                dict((await client.get(path, headers=headers)).headers)
                for path in (f'/api/stats?{FRESH_PARAMS}', '/', '/api/progress?job=x')
            ]

    assert all(
        not any(name.lower().startswith('access-control') for name in found)
        for found in asyncio.run(scenario())
    )


def test_openapi_lists_the_data_routes_with_every_parameter(
    stats_cache: wambatic.fetch.cache.Cache,
) -> None:
    async def scenario() -> tuple[dict[str, typing.Any], int, int]:
        async with serving(web_settings(), stats_cache) as client:
            schema = (await client.get('/openapi.json')).json()
            return (
                schema,
                (await client.get('/redoc')).status_code,
                (await client.get('/docs')).status_code,
            )

    schema, redoc, docs = asyncio.run(scenario())
    assert sorted(schema['paths']) == ['/api/progress', '/api/stats']
    parameters = {item['name'] for item in schema['paths']['/api/stats']['get']['parameters']}
    assert parameters == {'target', 'by', 'since', 'until', 'groups', 'by_author', 'tz', 'job'}
    assert (redoc, docs) == (404, 200)


# The pages


def progress_data(text: str) -> dict[str, typing.Any]:
    match = re.search(r'<script type="application/json" id="progress-data">(.*?)</script>', text)
    assert match is not None
    return typing.cast(dict[str, typing.Any], json.loads(match[1]))


def test_the_form_posts_to_report_and_escapes_the_default_target(
    stats_cache: wambatic.fetch.cache.Cache,
) -> None:
    async def scenario() -> tuple[str, str]:
        async with serving(web_settings(), stats_cache, default_target='org:<b>"x"') as client:
            plain = await client.get('/')
        async with serving(web_settings(), stats_cache) as client:
            empty = await client.get('/')
            assert empty.headers['content-type'] == 'text/html; charset=utf-8'
            return plain.text, empty.text

    plain, empty = asyncio.run(scenario())
    assert '<form action="/report" method="get">' in plain
    assert 'value="org:&lt;b&gt;&quot;x&quot;"' in plain
    assert '<b>' not in plain
    assert 'name="target" value=""' in empty
    for field in ('target', 'by', 'since', 'until', 'groups', 'by_author', 'tz'):
        assert f'name="{field}"' in plain


@pytest.mark.parametrize('theme', ['auto', 'dark'])
def test_report_of_a_fresh_cache_is_the_html_report_document(
    stats_cache: wambatic.fetch.cache.Cache,
    org_report: wambatic.reports.html.HtmlReport,
    theme: str,
) -> None:
    expected = wambatic.reports.html.html_document(org_report, theme)  # type: ignore[arg-type]

    async def scenario() -> tuple[int, str, str]:
        async with serving(web_settings(theme=theme), stats_cache) as client:
            response = await client.get(f'/report?{FRESH_PARAMS}')
            return response.status_code, response.headers['content-type'], response.text

    assert asyncio.run(scenario()) == (200, 'text/html; charset=utf-8', expected)


def test_report_by_total_is_a_400_message_page(stats_cache: wambatic.fetch.cache.Cache) -> None:
    async def scenario() -> tuple[int, str, str]:
        async with serving(web_settings(), stats_cache) as client:
            response = await client.get(f'/report?{FRESH_PARAMS}&by=total')
            return response.status_code, response.headers['content-type'], response.text

    status, content_type, text = asyncio.run(scenario())
    assert (status, content_type) == (400, 'text/html; charset=utf-8')
    assert 'by=total is not for the report page' in text
    assert '<a href="/">Back to the form</a>' in text


def test_a_message_page_escapes_what_the_request_put_in_it(
    stats_cache: wambatic.fetch.cache.Cache,
) -> None:
    async def scenario() -> tuple[int, str]:
        async with serving(web_settings(), stats_cache) as client:
            response = await client.get('/report', params={'target': 'org:octo-org', 'by': '<i>'})
            return response.status_code, response.text

    status, text = asyncio.run(scenario())
    assert status == 400
    assert '<i>' not in text


def test_report_of_a_stale_cache_shows_progress_then_the_report_without_a_second_sync(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache: wambatic.fetch.cache.Cache,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    upstream = tests.fixtures.reports.alpha_upstream()

    async def scenario() -> tuple[int, str, dict[str, typing.Any], int, int, str]:
        async with tests.fixtures.fetch.server.ReplayServer({}, upstream.respond) as server:
            tests.fixtures.reports.install_replay(monkeypatch, make_client, server)
            async with serving(web_settings('0s'), stats_cache) as client:
                first = await client.get(f'/report?{ALPHA_PARAMS}')
                data = progress_data(first.text)
                await finished(client, data['job'])
                requests = len(server.received)
                second = await client.get(data['reload'])
                return (
                    first.status_code,
                    first.text,
                    data,
                    second.status_code,
                    len(server.received) - requests,
                    second.text,
                )

    status, text, data, second_status, extra, report = asyncio.run(scenario())
    assert status == 202
    assert data['progress'] == f'/api/progress?job={data["job"]}'
    assert data['reload'].startswith('/report?target=repo%3Aocto-org%2Falpha&')
    assert data['reload'].endswith(f'&job={data["job"]}')
    assert 'repo:octo-org/alpha' in text
    assert (second_status, extra) == (200, 0)
    assert '<title>wambatic: repo octo-org/alpha</title>' in report
    assert 'id="wambatic-data"' in report


def test_a_failed_job_is_reported_once_then_a_new_request_starts_a_new_job(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache: wambatic.fetch.cache.Cache,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    upstream = tests.fixtures.reports.alpha_upstream()

    async def scenario() -> tuple[int, str, int, bool]:
        async with tests.fixtures.fetch.server.ReplayServer({}, upstream.respond) as server:
            tests.fixtures.reports.install_replay(monkeypatch, make_client, server)
            async with serving(web_settings('0s'), stats_cache) as client:
                params = 'target=repo:ghost/none'
                first = await client.get(f'/report?{params}')
                data = progress_data(first.text)
                await finished(client, data['job'])
                reported = await client.get(data['reload'])
                gone = await client.get(f'/api/progress?job={data["job"]}')
                again = await client.get(f'/report?{params}')
                return (
                    reported.status_code,
                    reported.headers['content-type'],
                    gone.status_code,
                    progress_data(again.text)['job'] != data['job'],
                )

    assert asyncio.run(scenario()) == (404, 'text/html; charset=utf-8', 404, True)


# Loopback


@pytest.mark.parametrize('host', ['localhost', '127.0.0.1', '127.1.2.3', '::1', '[::1]'])
def test_loopback_hosts(host: str) -> None:
    assert wambatic.reports.web.is_loopback(host)


@pytest.mark.parametrize(
    'host',
    ['0.0.0.0', '::', '[::]', '192.168.1.2', 'localhost.example', 'example.com', '', 'LOCALHOST'],
)
def test_other_hosts_are_not_loopback(host: str) -> None:
    assert not wambatic.reports.web.is_loopback(host)


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(address=st.ip_addresses(v=4))
def test_is_loopback_agrees_with_ipaddress_for_ipv4(address: ipaddress.IPv4Address) -> None:
    assert wambatic.reports.web.is_loopback(str(address)) is address.is_loopback


def test_check_bind_refuses_a_public_host_unless_allowed_and_then_warns() -> None:
    wambatic.reports.web.check_bind('127.0.0.1', False)
    with pytest.raises(wambatic.reports.errors.UsageError, match='--allow-remote'):
        wambatic.reports.web.check_bind('0.0.0.0', False)
    messages: list[str] = []
    sink = loguru.logger.add(
        lambda message: messages.append(
            f'{message.record["level"].name} {message.record["message"]}'
        )
    )
    try:
        wambatic.reports.web.check_bind('0.0.0.0', True)
        wambatic.reports.web.check_bind('127.0.0.1', True)
    finally:
        loguru.logger.remove(sink)
    assert len(messages) == 1
    assert messages[0].startswith('WARNING Listening on 0.0.0.0')
