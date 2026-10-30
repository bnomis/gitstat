import asyncio
import dataclasses
import datetime
import random

import aiohttp
import loguru
import pytest

import tests.conftest
import tests.fixtures.fetch.responses as responses
import tests.fixtures.fetch.server as server_module
import wambatic.fetch.client
import wambatic.fetch.errors
import wambatic.fetch.queries
import wambatic.fetch.ratelimit
import wambatic.settings

Canned = server_module.Canned
GRAPHQL = ('POST', '/graphql')
REPO = ('GET', '/repos/octocat/Hello-World')
STATS = ('GET', '/repos/octocat/Hello-World/stats/code_frequency')
VARIABLES = {'login': 'octocat', 'cursor': None}


def graphql_ok() -> Canned:
    return Canned(200, responses.OWNER_REPOSITORIES_OK, responses.RATE_HEADERS)


def run_graphql(
    routes: dict[tuple[str, str], list[Canned]],
    make_client: tests.conftest.MakeClient,
    settings: wambatic.settings.FetchSettings | None = None,
) -> dict[str, object]:
    async def scenario() -> dict[str, object]:
        async with server_module.ReplayServer(routes) as server:
            async with make_client(server, *([settings] if settings else [])) as client:
                return await client.graphql(wambatic.fetch.queries.OWNER_REPOSITORIES, VARIABLES)

    return asyncio.run(scenario())


def run_rest(
    routes: dict[tuple[str, str], list[Canned]],
    make_client: tests.conftest.MakeClient,
    path: str = REPO[1],
    settings: wambatic.settings.FetchSettings | None = None,
    **kwargs: object,
) -> wambatic.fetch.client.RestResponse:
    async def scenario() -> wambatic.fetch.client.RestResponse:
        async with server_module.ReplayServer(routes) as server:
            async with make_client(server, *([settings] if settings else [])) as client:
                return await client.rest_get(path, **kwargs)  # type: ignore[arg-type]

    return asyncio.run(scenario())


def with_settings(**changes: object) -> wambatic.settings.FetchSettings:
    return dataclasses.replace(wambatic.settings.FetchSettings(), max_retries=2, **changes)  # type: ignore[arg-type]


# Lifecycle


def test_requests_carry_required_headers(make_client: tests.conftest.MakeClient) -> None:
    async def scenario() -> server_module.Received:
        async with server_module.ReplayServer({REPO: [Canned(200, responses.REPO)]}) as server:
            async with make_client(server) as client:
                await client.rest_get(REPO[1])
            return server.received[0]

    headers = asyncio.run(scenario()).headers
    assert headers['Authorization'] == 'Bearer test-token'
    assert headers['Accept'] == 'application/vnd.github+json'
    assert headers['X-GitHub-Api-Version'] == '2022-11-28'
    assert headers['User-Agent'].startswith('wambatic/')


def test_session_closes_on_exit(make_client: tests.conftest.MakeClient) -> None:
    async def scenario() -> tuple[bool, bool]:
        async with server_module.ReplayServer({}) as server:
            client = make_client(server)
            async with client:
                assert client.session is not None
                open_inside = not client.session.closed
            assert client.session is not None
            return open_inside, client.session.closed

    assert asyncio.run(scenario()) == (True, True)


def test_use_outside_context_raises(make_client: tests.conftest.MakeClient) -> None:
    async def scenario() -> None:
        async with server_module.ReplayServer({}) as server:
            client = make_client(server)
            with pytest.raises(RuntimeError):
                await client.graphql('query', {})
            with pytest.raises(RuntimeError):
                await client.rest_get('/x')

    asyncio.run(scenario())


def test_logs_never_contain_token(make_client: tests.conftest.MakeClient) -> None:
    records: list[str] = []
    sink = loguru.logger.add(lambda message: records.append(str(message)), level='DEBUG')

    async def scenario() -> None:
        async with server_module.ReplayServer({REPO: [Canned(200, responses.REPO)]}) as server:
            async with make_client(server) as client:
                await client.rest_get(REPO[1])
                client.logger.info('leaked test-token here')

    try:
        asyncio.run(scenario())
    finally:
        loguru.logger.remove(sink)
    assert any('GET' in record for record in records)
    assert any('***' in record for record in records)
    assert not any('test-token' in record or 'Authorization' in record for record in records)


# Classification and transient retries


@pytest.mark.parametrize(
    ('status', 'body', 'headers', 'error'),
    [
        (401, responses.BAD_CREDENTIALS, {}, wambatic.fetch.errors.AuthError),
        (
            403,
            responses.FORBIDDEN,
            {'x-accepted-oauth-scopes': 'repo'},
            wambatic.fetch.errors.AuthError,
        ),
        (404, responses.NOT_FOUND, {}, wambatic.fetch.errors.NotFoundError),
    ],
)
def test_status_maps_to_error(
    make_client: tests.conftest.MakeClient,
    sleeps: tests.conftest.Sleeps,
    status: int,
    body: dict[str, str],
    headers: dict[str, str],
    error: type[Exception],
) -> None:
    with pytest.raises(error) as info:
        run_rest({REPO: [Canned(status, body, headers)]}, make_client)
    assert 'test-token' not in str(info.value)
    assert 'Bearer' not in str(info.value)
    assert sleeps == []
    if status == 403:
        assert 'repo' in str(info.value)


def test_transient_status_then_success(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps
) -> None:
    result = run_rest(
        {REPO: [Canned(502, responses.SERVER_ERROR), Canned(200, responses.REPO)]}, make_client
    )
    assert result.data == responses.REPO
    assert len(sleeps) == 1
    assert 0 <= sleeps[0] <= wambatic.fetch.ratelimit.BACKOFF_BASE


def test_transient_status_exhausts_retries(
    make_client: tests.conftest.MakeClient,
    sleeps: tests.conftest.Sleeps,
    fetch_settings: wambatic.settings.FetchSettings,
) -> None:
    canned = [Canned(502, responses.SERVER_ERROR)] * (fetch_settings.max_retries + 1)
    with pytest.raises(aiohttp.ClientResponseError) as info:
        run_rest({REPO: canned}, make_client)
    assert info.value.status == 502
    assert len(sleeps) == fetch_settings.max_retries
    for attempt, wait in enumerate(sleeps):
        assert 0 <= wait <= 2**attempt


def test_connection_error_then_success(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps
) -> None:
    async def scenario() -> wambatic.fetch.client.RestResponse:
        async with server_module.ReplayServer({REPO: [Canned(200, responses.REPO)]}) as server:
            async with make_client(server) as client:
                real = client.send
                calls = 0

                async def flaky(*args: object, **kwargs: object) -> wambatic.fetch.client.Response:
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        raise aiohttp.ClientConnectionError('reset')
                    return await real(*args, **kwargs)  # type: ignore[arg-type]

                client.send = flaky  # type: ignore[method-assign]
                return await client.rest_get(REPO[1])

    assert asyncio.run(scenario()).data == responses.REPO
    assert len(sleeps) == 1


def test_other_status_raises_without_retry(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps
) -> None:
    with pytest.raises(aiohttp.ClientResponseError) as info:
        run_rest({REPO: [Canned(422, responses.UNPROCESSABLE)]}, make_client)
    assert info.value.status == 422
    assert sleeps == []


# GraphQL


def test_graphql_returns_data_and_tracks_limit(make_client: tests.conftest.MakeClient) -> None:
    async def scenario() -> tuple[
        dict[str, object], wambatic.fetch.ratelimit.RateLimitState, object
    ]:
        async with server_module.ReplayServer({GRAPHQL: [graphql_ok()]}) as server:
            async with make_client(server) as client:
                data = await client.graphql(wambatic.fetch.queries.OWNER_REPOSITORIES, VARIABLES)
                return data, client.graphql_limit, server.received[0].json

    data, limit, sent = asyncio.run(scenario())
    assert data == responses.OWNER_REPOSITORIES_OK['data']
    assert limit == wambatic.fetch.ratelimit.RateLimitState(4999, responses.RESET)
    assert sent == {'query': wambatic.fetch.queries.OWNER_REPOSITORIES, 'variables': VARIABLES}


def test_graphql_not_found(make_client: tests.conftest.MakeClient) -> None:
    with pytest.raises(wambatic.fetch.errors.NotFoundError):
        run_graphql({GRAPHQL: [Canned(200, responses.GRAPHQL_NOT_FOUND)]}, make_client)


def test_graphql_other_error_discards_data(make_client: tests.conftest.MakeClient) -> None:
    with pytest.raises(wambatic.fetch.errors.GraphQLError) as info:
        run_graphql({GRAPHQL: [Canned(200, responses.GRAPHQL_INTERNAL)]}, make_client)
    assert info.value.errors == [('INTERNAL', 'Something went wrong')]


def test_graphql_requires_rate_limit(make_client: tests.conftest.MakeClient) -> None:
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        run_graphql({GRAPHQL: [Canned(200, responses.GRAPHQL_NO_RATE_LIMIT)]}, make_client)


def test_graphql_dated_returns_the_data_and_the_servers_date_in_utc(
    make_client: tests.conftest.MakeClient,
) -> None:
    headers = {**responses.RATE_HEADERS, 'Date': 'Thu, 29 Oct 2026 12:00:00 GMT'}

    async def scenario() -> tuple[dict[str, object], datetime.datetime, dict[str, object]]:
        canned = [Canned(200, responses.OWNER_REPOSITORIES_OK, headers)] * 2
        async with server_module.ReplayServer({GRAPHQL: canned}) as server:
            async with make_client(server) as client:
                query = wambatic.fetch.queries.OWNER_REPOSITORIES
                data, date = await client.graphql_dated(query, VARIABLES)
                return data, date, await client.graphql(query, VARIABLES)

    data, date, plain = asyncio.run(scenario())
    assert date == datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)
    assert date.utcoffset() == datetime.timedelta(0)
    assert data == plain == responses.OWNER_REPOSITORIES_OK['data']


def test_graphql_dated_with_an_unparseable_date_is_malformed(
    make_client: tests.conftest.MakeClient,
) -> None:
    headers = {**responses.RATE_HEADERS, 'Date': 'not a date'}

    async def scenario() -> None:
        async with server_module.ReplayServer(
            {GRAPHQL: [Canned(200, responses.OWNER_REPOSITORIES_OK, headers)]}
        ) as server:
            async with make_client(server) as client:
                await client.graphql_dated(wambatic.fetch.queries.OWNER_REPOSITORIES, VARIABLES)

    with pytest.raises(wambatic.fetch.errors.GraphQLError) as info:
        asyncio.run(scenario())
    assert info.value.errors[0][0] == 'MALFORMED'


@pytest.mark.parametrize(
    'headers',
    [{}, {'Date': ''}, {'Date': 'Thu, 29 Oct 2026 12:00:00 -0000'}],
    ids=['missing', 'empty', 'naive'],
)
def test_response_date_refuses_a_missing_or_naive_date(headers: dict[str, str]) -> None:
    response = wambatic.fetch.client.Response(200, headers, None, None)  # type: ignore[arg-type]
    with pytest.raises(wambatic.fetch.errors.GraphQLError) as info:
        wambatic.fetch.client.response_date(response)
    assert info.value.errors[0][0] == 'MALFORMED'


def test_response_date_converts_an_offset_to_utc() -> None:
    response = wambatic.fetch.client.Response(
        200,
        {'Date': 'Thu, 29 Oct 2026 14:00:00 +0200'},
        None,
        None,  # type: ignore[arg-type]
    )
    assert wambatic.fetch.client.response_date(response) == datetime.datetime(
        2026, 10, 29, 12, 0, tzinfo=datetime.UTC
    )


# REST


def test_rest_200_returns_data_and_etag(make_client: tests.conftest.MakeClient) -> None:
    headers = {**responses.RATE_HEADERS, 'ETag': responses.REPO_ETAG}
    result = run_rest({REPO: [Canned(200, responses.REPO, headers)]}, make_client)
    assert result == wambatic.fetch.client.RestResponse(
        200, responses.REPO, responses.REPO_ETAG, None
    )


def test_rest_304_sends_if_none_match(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps
) -> None:
    async def scenario() -> tuple[wambatic.fetch.client.RestResponse, server_module.Received]:
        async with server_module.ReplayServer({REPO: [Canned(304)]}) as server:
            async with make_client(server) as client:
                result = await client.rest_get(REPO[1], etag=responses.REPO_ETAG)
                return result, server.received[0]

    result, received = asyncio.run(scenario())
    assert result == wambatic.fetch.client.RestResponse(304, None, responses.REPO_ETAG, None)
    assert received.headers['If-None-Match'] == responses.REPO_ETAG
    assert sleeps == []


def test_rest_limit_tracks_headers(make_client: tests.conftest.MakeClient) -> None:
    async def scenario() -> wambatic.fetch.ratelimit.RateLimitState:
        routes = {REPO: [Canned(200, responses.REPO, responses.RATE_HEADERS)]}
        async with server_module.ReplayServer(routes) as server:
            async with make_client(server) as client:
                await client.rest_get(REPO[1])
                return client.rest_limit

    assert asyncio.run(scenario()) == wambatic.fetch.ratelimit.RateLimitState(4990, responses.RESET)


def test_rest_404(make_client: tests.conftest.MakeClient) -> None:
    with pytest.raises(wambatic.fetch.errors.NotFoundError):
        run_rest({REPO: [Canned(404, responses.NOT_FOUND)]}, make_client)


def test_rest_next_url_from_link(make_client: tests.conftest.MakeClient) -> None:
    link = (
        '<https://api.github.com/x?page=2>; rel="next", '
        '<https://api.github.com/x?page=9>; rel="last"'
    )
    result = run_rest({REPO: [Canned(200, [], {'Link': link})]}, make_client)
    assert result.next_url == 'https://api.github.com/x?page=2'


def test_next_link() -> None:
    link = (
        '<https://a/?page=1>; rel="prev", <https://a/?page=3>; rel="next", '
        '<https://a/?page=9>; rel="last"'
    )
    assert wambatic.fetch.client.next_link(link) == 'https://a/?page=3'
    assert wambatic.fetch.client.next_link('<https://a/?page=9>; rel="last"') is None
    assert wambatic.fetch.client.next_link(None) is None


# Primary rate limit


def primary_rest() -> Canned:
    return Canned(403, responses.PRIMARY_LIMIT, responses.PRIMARY_LIMIT_HEADERS)


def primary_graphql() -> Canned:
    return Canned(200, responses.GRAPHQL_RATE_LIMITED, responses.PRIMARY_LIMIT_HEADERS)


@pytest.mark.parametrize('route', ['rest', 'graphql'])
def test_primary_limit_fail(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps, route: str
) -> None:
    settings = with_settings(on_rate_limit='fail')
    with pytest.raises(wambatic.fetch.errors.RateLimitError) as info:
        if route == 'rest':
            run_rest({REPO: [primary_rest()]}, make_client, settings=settings)
        else:
            run_graphql({GRAPHQL: [primary_graphql()]}, make_client, settings)
    assert info.value.reset_at == responses.RESET
    assert sleeps == []


@pytest.mark.parametrize('route', ['rest', 'graphql'])
def test_primary_limit_wait(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps, route: str
) -> None:
    settings = with_settings(on_rate_limit='wait')
    records: list[str] = []
    sink = loguru.logger.add(lambda message: records.append(str(message)), level='INFO')
    try:
        if route == 'rest':
            run_rest(
                {REPO: [primary_rest(), Canned(200, responses.REPO)]},
                make_client,
                settings=settings,
            )
        else:
            run_graphql({GRAPHQL: [primary_graphql(), graphql_ok()]}, make_client, settings)
    finally:
        loguru.logger.remove(sink)
    assert sleeps == [3601.0]
    assert any('ETA: GitHub rate limit resets in 1:00:01' in record for record in records)


def test_exhausted_state_fails_before_request(make_client: tests.conftest.MakeClient) -> None:
    async def scenario() -> int:
        routes = {REPO: [Canned(200, responses.REPO, responses.PRIMARY_LIMIT_HEADERS)]}
        async with server_module.ReplayServer(routes) as server:
            client = make_client(server, with_settings(on_rate_limit='fail'))
            async with client:
                await client.rest_get(REPO[1])
                with pytest.raises(wambatic.fetch.errors.RateLimitError):
                    await client.rest_get(REPO[1])
            return len(server.received)

    assert asyncio.run(scenario()) == 1


def test_primary_limit_without_reset_is_secondary(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps
) -> None:
    limited = Canned(403, responses.PRIMARY_LIMIT, {'x-ratelimit-remaining': '0'})
    run_rest({REPO: [limited, Canned(200, responses.REPO)]}, make_client)
    assert len(sleeps) == 1
    assert sleeps[0] >= wambatic.fetch.ratelimit.SECONDARY_WAIT


# Secondary rate limits


def test_retry_after_is_honoured(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps
) -> None:
    limited = Canned(429, responses.PRIMARY_LIMIT, {'retry-after': '3'})
    run_rest({REPO: [limited, Canned(200, responses.REPO)]}, make_client)
    assert len(sleeps) == 1
    assert sleeps[0] >= 3


def test_secondary_message_waits_a_minute(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps
) -> None:
    limited = Canned(403, responses.SECONDARY_LIMIT)
    run_rest({REPO: [limited, Canned(200, responses.REPO)]}, make_client)
    assert len(sleeps) == 1
    assert sleeps[0] >= 60


def test_secondary_limit_runs_out_of_retries(
    make_client: tests.conftest.MakeClient,
    sleeps: tests.conftest.Sleeps,
    fetch_settings: wambatic.settings.FetchSettings,
) -> None:
    limited = Canned(429, responses.PRIMARY_LIMIT, {'retry-after': '3'})
    settings = dataclasses.replace(fetch_settings, on_rate_limit='wait')
    with pytest.raises(wambatic.fetch.errors.RateLimitError) as info:
        run_rest({REPO: [limited] * (settings.max_retries + 1)}, make_client, settings=settings)
    assert len(sleeps) == settings.max_retries
    assert info.value.reset_at >= responses.NOW + datetime.timedelta(seconds=3)


def test_forbidden_without_limit_signal_is_auth_error(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps
) -> None:
    with pytest.raises(wambatic.fetch.errors.AuthError):
        run_rest({REPO: [Canned(403, responses.FORBIDDEN)]}, make_client)
    assert sleeps == []


# REST 202


def test_202_then_200(
    make_client: tests.conftest.MakeClient, sleeps: tests.conftest.Sleeps
) -> None:
    done = Canned(200, [[1, 2, 3, 4]])
    result = run_rest({STATS: [responses.STATS_PENDING] * 2 + [done]}, make_client, STATS[1])
    assert result.data == [[1, 2, 3, 4]]
    assert len(sleeps) == 2


def test_202_exhausts_stats_retries(
    make_client: tests.conftest.MakeClient,
    sleeps: tests.conftest.Sleeps,
    fetch_settings: wambatic.settings.FetchSettings,
) -> None:
    pending = [responses.STATS_PENDING] * (fetch_settings.stats_retries + 1)
    with pytest.raises(wambatic.fetch.errors.StatsPendingError) as info:
        run_rest({STATS: pending}, make_client, STATS[1])
    assert STATS[1] in str(info.value)
    assert len(sleeps) == fetch_settings.stats_retries


def test_default_rng_is_independent() -> None:
    client = wambatic.fetch.client.GitHubClient('t', wambatic.settings.FetchSettings())
    assert isinstance(client.rng, random.Random)
