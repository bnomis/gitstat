import asyncio
import dataclasses
import datetime
import zoneinfo

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
import wambatic.reports.errors
import wambatic.reports.html
import wambatic.reports.service
import wambatic.settings
import wambatic.stats.base

Subject = wambatic.fetch.base.Subject
UsageError = wambatic.reports.errors.UsageError
SettingsError = wambatic.settings.SettingsError
Granularity = wambatic.stats.base.Granularity
StatsRequest = wambatic.stats.base.StatsRequest
UTC = datetime.UTC
COMMITS = frozenset({'commits'})
LOGINS = st.from_regex(r'[A-Za-z0-9-]{1,39}', fullmatch=True)
REPO_NAMES = st.from_regex(r'[A-Za-z0-9._-]{1,100}', fullmatch=True)
NOW = datetime.datetime(2027, 3, 1, 12, 0, tzinfo=UTC)
FRESH = (NOW - datetime.timedelta(hours=1)).isoformat()
STALE = (NOW - datetime.timedelta(days=2)).isoformat()


def settings_for(*, tz: str) -> wambatic.settings.Settings:
    return wambatic.settings.load_settings(None, {'stats': {'timezone': tz}})


def fetch_settings(max_age: str) -> wambatic.settings.FetchSettings:
    return wambatic.settings.load_settings(None, {'fetch': {'max_age': max_age}}).fetch


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('user:octocat', Subject('user', 'octocat')),
        ('org:octo-org', Subject('org', 'octo-org')),
        ('repo:octocat/Hello-World', Subject('repo', 'octocat', 'Hello-World')),
        ('octocat/Hello-World', Subject('repo', 'octocat', 'Hello-World')),
        ('octocat/hello.world_2', Subject('repo', 'octocat', 'hello.world_2')),
        ('octocat', 'octocat'),
        ('a' * 39, 'a' * 39),
        ('a' * 39 + '/' + 'b' * 100, Subject('repo', 'a' * 39, 'b' * 100)),
    ],
)
def test_valid_targets(text: str, expected: Subject | str) -> None:
    assert wambatic.reports.service.parse_target(text) == expected


@pytest.mark.parametrize(
    'text',
    [
        '',
        'REPO:octocat/Hello-World',
        'User:octocat',
        'team:octocat',
        'user:',
        'org:',
        'repo:',
        'repo:octocat',
        'user:octocat/Hello-World',
        'a/b/c',
        '/Hello-World',
        'octocat/',
        'a' * 40,
        'a' * 40 + '/b',
        'a/' + 'b' * 101,
        'octo cat',
        'octocat/Hello World',
        'zoë',
        'octocat/zoë',
        'user:octo_cat',
        ':octocat',
        'user:octocat:x',
        'octocat\n',
    ],
)
def test_invalid_targets_name_the_accepted_forms(text: str) -> None:
    with pytest.raises(UsageError, match=r'user:NAME, org:NAME, repo:OWNER/NAME'):
        wambatic.reports.service.parse_target(text)


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(login=LOGINS, name=REPO_NAMES)
def test_every_valid_login_and_repo_name_round_trips(login: str, name: str) -> None:
    assert wambatic.reports.service.parse_target(f'user:{login}') == Subject('user', login)
    assert wambatic.reports.service.parse_target(f'org:{login}') == Subject('org', login)
    assert wambatic.reports.service.parse_target(f'repo:{login}/{name}') == Subject(
        'repo', login, name
    )
    assert wambatic.reports.service.parse_target(f'{login}/{name}') == Subject('repo', login, name)
    assert wambatic.reports.service.parse_target(login) == login


def allowed(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == '-')


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(
    login=LOGINS,
    bad=st.characters().filter(lambda char: not allowed(char)),
    where=st.integers(min_value=0, max_value=39),
    prefix=st.sampled_from(['user:', 'org:', 'repo:', '']),
)
def test_a_character_outside_the_login_rule_is_rejected(
    login: str, bad: str, where: int, prefix: str
) -> None:
    where = min(where, len(login))
    owner = login[:where] + bad + login[where:]
    with pytest.raises(UsageError):
        wambatic.reports.service.parse_target(
            f'{prefix}{owner}/name' if prefix in ('repo:', '') else prefix + owner
        )


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(login=st.text(alphabet='ab-', min_size=40, max_size=60))
def test_a_login_over_the_length_limit_is_rejected(login: str) -> None:
    with pytest.raises(UsageError):
        wambatic.reports.service.parse_target(f'user:{login}')


def test_dates_are_exactly_year_month_day() -> None:
    assert wambatic.reports.service.parse_date('2026-10-29') == datetime.date(2026, 10, 29)


@pytest.mark.parametrize(
    'text', ['20261029', '2026-W44-1', '2026-02-30', '2026-1-1', '26-10-29', '', '2026-10-29 ']
)
def test_other_date_forms_are_rejected_naming_the_flag(text: str) -> None:
    with pytest.raises(UsageError, match='--since must be a date written YYYY-MM-DD'):
        wambatic.reports.service.parse_date(text, '--since')


def test_an_unknown_time_zone_is_a_settings_error_naming_the_setting_not_the_value() -> None:
    settings = settings_for(tz='Mars/Base')
    with pytest.raises(SettingsError, match='stats.timezone') as caught:
        wambatic.reports.service.resolve_tz(settings)
    assert 'Mars' not in str(caught.value)


@pytest.mark.parametrize('zone', ['', '../etc/passwd', 'UTC/..'])
def test_a_malformed_time_zone_key_is_also_a_settings_error(zone: str) -> None:
    settings = settings_for(tz=zone)
    with pytest.raises(SettingsError, match='stats.timezone'):
        wambatic.reports.service.resolve_tz(settings)


def test_a_known_time_zone_resolves() -> None:
    settings = settings_for(tz='Europe/Berlin')
    assert wambatic.reports.service.resolve_tz(settings) == zoneinfo.ZoneInfo('Europe/Berlin')


def test_the_sync_log_line_names_the_rows_written_for_each_resource() -> None:
    messages: list[str] = []
    sink = loguru.logger.add(lambda message: messages.append(message.record['message']))
    try:
        wambatic.reports.service.log_sync(
            wambatic.fetch.base.SyncReport(
                3, 1, {'pull_requests': 5, 'commits': 12, 'issues': 3}, (tests.fixtures.stats.BETA,)
            )
        )
    finally:
        loguru.logger.remove(sink)
    assert messages == [
        'Synced 3 repositories (1 unchanged), rows written: '
        f'commits 12, issues 3, pull_requests 5; read in full again: {tests.fixtures.stats.BETA}'
    ]


@pytest.mark.parametrize(
    ('provenance', 'resources', 'max_age', 'full_refresh', 'no_fetch', 'expected'),
    [
        ({'fetched_at:commits': FRESH}, {'commits'}, '1d', False, True, False),
        ({'fetched_at:commits': STALE}, {'commits'}, '1d', True, True, False),
        ({}, set(), '0s', False, False, False),
        ({}, set(), '0s', True, False, False),
        ({'fetched_at:commits': FRESH}, {'commits'}, '1d', True, False, True),
        ({'fetched_at:commits': FRESH}, {'commits'}, '0s', False, False, True),
        ({'fetched_at:commits': FRESH}, {'commits'}, '1d', False, False, False),
        ({'fetched_at:commits': STALE}, {'commits'}, '1d', False, False, True),
        ({'fetched_at:commits': 'never'}, {'commits'}, '1d', False, False, True),
        ({}, {'commits'}, '1d', False, False, True),
        (
            {'fetched_at:commits': FRESH, 'fetched_at:issues': STALE},
            {'commits', 'issues'},
            '1d',
            False,
            False,
            True,
        ),
        (
            {'fetched_at:commits': FRESH, 'fetched_at:issues': FRESH},
            {'commits', 'issues'},
            '1d',
            False,
            False,
            False,
        ),
    ],
)
def test_needs_sync(
    provenance: dict[str, str],
    resources: set[str],
    max_age: str,
    full_refresh: bool,
    no_fetch: bool,
    expected: bool,
) -> None:
    assert (
        wambatic.reports.service.needs_sync(
            provenance, frozenset(resources), fetch_settings(max_age), full_refresh, no_fetch, NOW
        )
        is expected
    )


def test_a_cache_exactly_max_age_old_is_stale() -> None:
    provenance = {'fetched_at:commits': (NOW - datetime.timedelta(days=1)).isoformat()}
    assert wambatic.reports.service.needs_sync(
        provenance, COMMITS, fetch_settings('1d'), False, False, NOW
    )


ALPHA = Subject('repo', 'octo-org', 'alpha')
SYNCED = tests.fixtures.stats.ALPHA_SYNCED_AT


def month_request(max_age: str = '0s') -> tuple[wambatic.settings.Settings, StatsRequest]:
    settings = wambatic.settings.load_settings(None, {'fetch': {'max_age': max_age}})
    request = wambatic.reports.service.make_request(
        'month', '2026-10-01', '2027-01-31', None, False, zoneinfo.ZoneInfo('UTC'), settings
    )
    return settings, request


def test_period_requests_are_total_then_the_four_periods_and_otherwise_equal() -> None:
    request = StatsRequest(
        since=tests.fixtures.stats.SINCE, until=tests.fixtures.stats.UNTIL, by_author=True
    )
    requests = wambatic.reports.html.period_requests(request)
    assert [item.granularity for item in requests] == [
        Granularity.TOTAL,
        Granularity.YEAR,
        Granularity.MONTH,
        Granularity.WEEK,
        Granularity.DAY,
    ]
    assert all(
        dataclasses.replace(item, granularity=request.granularity) == request for item in requests
    )


def test_html_report_of_the_five_results_is_the_org_report(
    stats_fetcher: wambatic.fetch.base.Fetcher, org_report: wambatic.reports.html.HtmlReport
) -> None:
    request = StatsRequest(
        since=tests.fixtures.stats.SINCE, until=tests.fixtures.stats.UNTIL, by_author=True
    )
    results = [
        tests.conftest.compute_stats(stats_fetcher, tests.fixtures.stats.ORG, item)
        for item in wambatic.reports.html.period_requests(request)
    ]
    assert wambatic.reports.html.html_report(results, Granularity.MONTH) == org_report


@pytest.mark.parametrize('by', ['hour', '', 'Month'])
def test_an_unknown_granularity_is_a_usage_error(by: str) -> None:
    settings = wambatic.settings.load_settings(None, {})
    with pytest.raises(UsageError, match='--by must be one of'):
        wambatic.reports.service.make_request(
            by, None, None, None, False, zoneinfo.ZoneInfo('UTC'), settings
        )


def test_build_results_with_sync_false_makes_no_request_and_needs_no_token(
    stats_cache: wambatic.fetch.cache.Cache,
) -> None:
    settings, request = month_request()
    subject, results = asyncio.run(
        wambatic.reports.service.build_results(
            settings,
            stats_cache,
            ALPHA,
            [request],
            by_author=False,
            full_refresh=False,
            no_fetch=False,
            sync=False,
            clock=lambda: SYNCED,
        )
    )
    assert subject == ALPHA
    assert len(results) == 1


def build_with(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache: wambatic.fetch.cache.Cache,
    sync: bool | None,
    progress: wambatic.fetch.base.SyncProgress | None = None,
) -> int:
    """The number of requests `build_results` makes against the fake GitHub."""
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    settings, request = month_request('30d')

    async def scenario() -> int:
        upstream = tests.fixtures.reports.alpha_upstream()
        async with tests.fixtures.fetch.server.ReplayServer({}, upstream.respond) as server:
            tests.fixtures.reports.install_replay(monkeypatch, make_client, server)
            await wambatic.reports.service.build_results(
                settings,
                stats_cache,
                ALPHA,
                [request],
                by_author=False,
                full_refresh=False,
                no_fetch=False,
                sync=sync,
                progress=progress,
                clock=lambda: SYNCED + datetime.timedelta(days=1),
            )
            return len(server.received)

    return asyncio.run(scenario())


def test_a_fresh_cache_is_not_synced_unless_sync_is_true(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache: wambatic.fetch.cache.Cache,
) -> None:
    assert build_with(monkeypatch, make_client, stats_cache, None) == 0
    assert build_with(monkeypatch, make_client, stats_cache, False) == 0
    progress = wambatic.fetch.base.SyncProgress()
    assert build_with(monkeypatch, make_client, stats_cache, True, progress) > 0
    assert progress.repos_listed == 1
