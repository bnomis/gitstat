import asyncio
import dataclasses
import datetime
import pathlib
import sqlite3
import threading

import aiohttp
import loguru
import pytest

import tests.conftest
import tests.fixtures.fetch.responses
import tests.fixtures.fetch.server
import tests.fixtures.fetch.upstream
import wambatic.fetch.base
import wambatic.fetch.cache
import wambatic.fetch.errors
import wambatic.settings

Canned = tests.fixtures.fetch.server.Canned
FakeCommit = tests.fixtures.fetch.upstream.FakeCommit
FakeRepo = tests.fixtures.fetch.upstream.FakeRepo
Upstream = tests.fixtures.fetch.upstream.Upstream

HELLO = 'octocat/Hello-World'
SPOON = 'octocat/Spoon-Knife'
OWNER = wambatic.fetch.base.Subject('user', 'octocat')
COMMITS = frozenset({'commits'})
T0 = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=datetime.UTC)
REST_PATH = '/repos/octocat/Hello-World'


def at(days: int) -> datetime.datetime:
    return T0 + datetime.timedelta(days=days)


def history(prefix: str, count: int, start: int = 1, **changes: object) -> list[FakeCommit]:
    """`count` commits `prefix1`, `prefix2`, ... one day apart, oldest first."""
    return [
        FakeCommit(f'{prefix}{n}', at(n), **changes)  # type: ignore[arg-type]
        for n in range(start, start + count)
    ]


def hello(count: int = 3, **changes: object) -> FakeRepo:
    return FakeRepo(HELLO, history('h', count), **changes)  # type: ignore[arg-type]


def spoon(count: int = 2, **changes: object) -> FakeRepo:
    return FakeRepo(SPOON, history('s', count), **changes)  # type: ignore[arg-type]


@dataclasses.dataclass
class Run:
    report: wambatic.fetch.base.SyncReport
    kinds: list[str]
    max_in_flight: int
    fetcher: wambatic.fetch.base.Fetcher

    @property
    def cache(self) -> wambatic.fetch.cache.Cache:
        return self.fetcher.cache


def sync_once(
    make_fetcher: tests.conftest.MakeFetcher,
    upstream: Upstream,
    subject: wambatic.fetch.base.Subject = OWNER,
    *,
    resources: frozenset[str] = COMMITS,
    full_refresh: bool = False,
    **kwargs: object,
) -> Run:
    async def scenario() -> Run:
        async with tests.fixtures.fetch.server.ReplayServer({}, default=upstream.respond) as server:
            fetcher = make_fetcher(server, **kwargs)
            async with fetcher:
                report = await fetcher.sync(subject, resources, full_refresh)
            return Run(report, upstream.requests(server), server.max_in_flight, fetcher)

    return asyncio.run(scenario())


def stored(cache: wambatic.fetch.cache.Cache, name: str = HELLO) -> list[str]:
    return [commit.oid for commit in cache.read_commits(name, None, None)]


def settings_with(
    base: wambatic.settings.FetchSettings, **changes: object
) -> wambatic.settings.FetchSettings:
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


def listed(upstream: Upstream, name: str = HELLO) -> wambatic.fetch.base.Repo:
    return wambatic.fetch.base.parse_repo(upstream.repos[name].node())


# The shell and cached REST


def test_entering_and_leaving_opens_and_closes_the_client_session(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    async def scenario() -> tuple[bool, bool]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server)
            assert fetcher.client.session is None
            async with fetcher as entered:
                assert entered is fetcher
                assert fetcher.client.session is not None
                open_inside = not fetcher.client.session.closed
            assert fetcher.client.session is not None
            return open_inside, fetcher.client.session.closed

    assert asyncio.run(scenario()) == (True, True)


def test_the_fetcher_builds_a_client_when_given_none(tmp_path: pathlib.Path) -> None:
    cache = wambatic.fetch.cache.Cache.open(tmp_path / 'cache.sqlite3')
    try:
        fetcher = wambatic.fetch.base.Fetcher(
            'test-token', cache, wambatic.settings.FetchSettings()
        )
        assert fetcher.client.token == 'test-token'
    finally:
        cache.close()


def test_the_cache_is_not_closed_by_leaving_the_fetcher(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    async def scenario() -> list[str]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server)
            async with fetcher:
                pass
            return stored(fetcher.cache)

    assert asyncio.run(scenario()) == []


def test_cache_calls_run_off_the_event_loop_thread(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    async def scenario() -> tuple[int, int]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server)
            return threading.get_ident(), await fetcher.db(threading.get_ident)

    loop_thread, worker_thread = asyncio.run(scenario())
    assert loop_thread != worker_thread


def test_rest_cached_revalidates_with_the_stored_etag(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    route = ('GET', REST_PATH)
    routes = {
        route: [
            Canned(200, tests.fixtures.fetch.responses.REPO, {'ETag': '"e1"'}),
            Canned(304),
        ]
    }

    async def scenario() -> tuple[object, object, list[tests.fixtures.fetch.server.Received]]:
        async with tests.fixtures.fetch.server.ReplayServer(routes) as server:
            async with make_fetcher(server) as fetcher:
                first = await fetcher.rest_cached(REST_PATH, {'b': '2', 'a': '1'})
                second = await fetcher.rest_cached(REST_PATH, {'a': '1', 'b': '2'})
            return first, second, server.received

    first, second, received = asyncio.run(scenario())
    assert first == second == tests.fixtures.fetch.responses.REPO
    assert 'If-None-Match' not in received[0].headers
    assert received[1].headers['If-None-Match'] == '"e1"'


def test_rest_cached_keeps_one_etag_per_query_string(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    routes = {
        ('GET', REST_PATH): [
            Canned(200, {'page': 1}, {'ETag': '"p1"'}),
            Canned(200, {'page': 2}, {'ETag': '"p2"'}),
        ]
    }

    async def scenario() -> tuple[object, object, list[tests.fixtures.fetch.server.Received]]:
        async with tests.fixtures.fetch.server.ReplayServer(routes) as server:
            async with make_fetcher(server) as fetcher:
                first = await fetcher.rest_cached(REST_PATH, {'page': '1'})
                second = await fetcher.rest_cached(REST_PATH, {'page': '2'})
            return first, second, server.received

    first, second, received = asyncio.run(scenario())
    assert (first, second) == ({'page': 1}, {'page': 2})
    assert all('If-None-Match' not in item.headers for item in received)


def test_rest_cached_without_an_etag_stores_nothing(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    routes = {('GET', REST_PATH): [Canned(200, {'a': 1}), Canned(200, {'a': 2})]}

    async def scenario() -> tuple[object, object]:
        async with tests.fixtures.fetch.server.ReplayServer(routes) as server:
            async with make_fetcher(server) as fetcher:
                return (
                    await fetcher.rest_cached(REST_PATH, {}),
                    await fetcher.rest_cached(REST_PATH, {}),
                )

    assert asyncio.run(scenario()) == ({'a': 1}, {'a': 2})


# Repo listing and the skip rule


def test_a_two_page_listing_is_read_fully_and_stored(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello(), spoon()])
    upstream.owner_page_size = 1
    run = sync_once(make_fetcher, upstream)
    assert run.kinds[:2] == ['listing', 'listing']
    assert run.report.repos_listed == 2
    rows = run.cache.read_repos(OWNER)
    assert [row.name_with_owner for row in rows] == [HELLO, SPOON]
    assert rows[0] == listed(upstream, HELLO)


def test_forks_and_archived_repos_are_dropped_by_default(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream(
        [
            hello(),
            FakeRepo('octocat/Forked', history('f', 1), is_fork=True),
            FakeRepo('octocat/Old', history('o', 1), is_archived=True),
        ]
    )
    run = sync_once(make_fetcher, upstream)
    assert run.report.repos_listed == 1
    assert [row.name_with_owner for row in run.cache.read_repos(OWNER)] == [HELLO]
    assert stored(run.cache, 'octocat/Forked') == []


def test_forks_and_archived_repos_are_kept_when_the_settings_say_so(
    make_fetcher: tests.conftest.MakeFetcher, fetch_settings: wambatic.settings.FetchSettings
) -> None:
    upstream = Upstream(
        [
            hello(),
            FakeRepo('octocat/Forked', history('f', 1), is_fork=True),
            FakeRepo('octocat/Old', history('o', 1), is_archived=True),
        ]
    )
    settings = settings_with(fetch_settings, include_forks=True, include_archived=True)
    run = sync_once(make_fetcher, upstream, settings=settings)
    assert run.report.repos_listed == 3
    assert len(run.cache.read_repos(OWNER)) == 3


def test_repos_applies_the_current_settings_to_the_cache(
    make_fetcher: tests.conftest.MakeFetcher, fetch_settings: wambatic.settings.FetchSettings
) -> None:
    upstream = Upstream([hello(), FakeRepo('octocat/Forked', history('f', 1), is_fork=True)])
    wide = settings_with(fetch_settings, include_forks=True)
    run = sync_once(make_fetcher, upstream, settings=wide)

    async def names(settings: wambatic.settings.FetchSettings) -> list[str]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, settings, run.cache)
            return [repo.name_with_owner for repo in await fetcher.repos(OWNER)]

    assert asyncio.run(names(wide)) == ['octocat/Forked', HELLO]
    assert asyncio.run(names(fetch_settings)) == [HELLO]


def test_a_repo_that_leaves_the_listing_is_missing_but_keeps_its_commits(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello(), spoon()])
    first = sync_once(make_fetcher, upstream)
    del upstream.repos[SPOON]
    second = sync_once(make_fetcher, upstream, cache=first.cache)

    async def names() -> list[str]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            return [
                r.name_with_owner
                for r in await make_fetcher(server, cache=first.cache).repos(OWNER)
            ]

    assert second.report.repos_listed == 1
    assert asyncio.run(names()) == [HELLO]
    assert stored(first.cache, SPOON) == ['s1', 's2']
    spoon_row = first.cache.read_repos(
        wambatic.fetch.base.Subject('repo', 'octocat', 'Spoon-Knife')
    )
    assert [row.missing for row in spoon_row] == [True]


def test_repos_and_commits_make_no_request(make_fetcher: tests.conftest.MakeFetcher) -> None:
    upstream = Upstream([hello()])
    run = sync_once(make_fetcher, upstream)

    async def scenario() -> tuple[int, list[str], list[str]]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, cache=run.cache)
            repos = await fetcher.repos(OWNER)
            commits = [c.oid async for c in fetcher.commits(repos[0], None, None)]
            return len(server.received), [r.name_with_owner for r in repos], commits

    assert asyncio.run(scenario()) == (0, [HELLO], ['h1', 'h2', 'h3'])


@pytest.mark.parametrize(
    ('pushed_at', 'updated_at', 'expected'),
    [
        ('same', 'same', True),
        ('other', 'same', False),
        ('same', 'other', False),
        ('other', 'other', False),
    ],
)
def test_unchanged_compares_the_listed_values_with_the_stored_ones(
    make_fetcher: tests.conftest.MakeFetcher, pushed_at: str, updated_at: str, expected: bool
) -> None:
    upstream = Upstream([hello()])
    run = sync_once(make_fetcher, upstream)
    repo = listed(upstream)
    hour = datetime.timedelta(hours=1)
    changed = dataclasses.replace(
        repo,
        pushed_at=repo.pushed_at + hour
        if pushed_at == 'other' and repo.pushed_at
        else repo.pushed_at,
        updated_at=repo.updated_at + hour if updated_at == 'other' else repo.updated_at,
    )

    async def scenario() -> bool:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            return await make_fetcher(server, cache=run.cache).unchanged(changed, COMMITS)

    assert asyncio.run(scenario()) is expected


def test_unchanged_is_false_with_no_state(make_fetcher: tests.conftest.MakeFetcher) -> None:
    upstream = Upstream([hello()])

    async def scenario() -> bool:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            return await make_fetcher(server).unchanged(listed(upstream), COMMITS)

    assert asyncio.run(scenario()) is False


def test_unchanged_needs_every_requested_resource_synced(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello()])
    run = sync_once(make_fetcher, upstream)

    async def scenario(resources: frozenset[str]) -> bool:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            return await make_fetcher(server, cache=run.cache).unchanged(
                listed(upstream), resources
            )

    assert asyncio.run(scenario(COMMITS)) is True
    assert asyncio.run(scenario(frozenset({'commits', 'issues'}))) is False


def test_a_repo_subject_that_does_not_exist_raises_not_found(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    with pytest.raises(wambatic.fetch.errors.NotFoundError):
        sync_once(
            make_fetcher,
            Upstream([hello()]),
            wambatic.fetch.base.Subject('repo', 'octocat', 'nope'),
        )


def test_an_owner_that_does_not_exist_raises_not_found(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    routes = {('POST', '/graphql'): [Canned(200, tests.fixtures.fetch.responses.GRAPHQL_NOT_FOUND)]}

    async def scenario() -> None:
        async with tests.fixtures.fetch.server.ReplayServer(routes) as server:
            async with make_fetcher(server) as fetcher:
                await fetcher.sync(wambatic.fetch.base.Subject('user', 'nobody'), COMMITS)

    with pytest.raises(wambatic.fetch.errors.NotFoundError):
        asyncio.run(scenario())


def test_a_repo_subject_syncs_its_repo_and_keeps_forks(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello(is_fork=True), spoon()])
    subject = wambatic.fetch.base.Subject('repo', 'octocat', 'Hello-World')
    run = sync_once(make_fetcher, upstream, subject)

    async def repos() -> list[str]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, cache=run.cache)
            return [r.name_with_owner for r in await fetcher.repos(subject)]

    assert run.kinds == ['repository', 'history']
    assert run.report.repos_listed == 1
    assert asyncio.run(repos()) == [HELLO]
    assert stored(run.cache) == ['h1', 'h2', 'h3']
    assert stored(run.cache, SPOON) == []


def test_a_repo_subject_sync_does_not_mark_the_owners_other_repos_missing(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello(), spoon()])
    first = sync_once(make_fetcher, upstream)
    sync_once(
        make_fetcher,
        upstream,
        wambatic.fetch.base.Subject('repo', 'octocat', 'Hello-World'),
        cache=first.cache,
    )
    assert [row.missing for row in first.cache.read_repos(OWNER)] == [False, False]


# Commit backfill and commits()


def test_a_multi_page_history_is_stored_in_full(make_fetcher: tests.conftest.MakeFetcher) -> None:
    repo = FakeRepo(
        HELLO,
        [
            FakeCommit('h1', at(1), additions=5, deletions=0),
            FakeCommit('h2', at(2), login=None, additions=2, deletions=2),
            FakeCommit('h3', at(3), additions=0, deletions=0, parents=2),
            FakeCommit('h4', at(4), additions=7, deletions=3),
            FakeCommit('h5', at(5), additions=1, deletions=1),
        ],
    )
    upstream = Upstream([repo])
    upstream.history_page_size = 2
    run = sync_once(make_fetcher, upstream)
    assert run.kinds == ['listing', 'history', 'history', 'history']
    commits = run.cache.read_commits(HELLO, None, None)
    assert [c.oid for c in commits] == ['h1', 'h2', 'h3', 'h4', 'h5']
    assert [c.author_login for c in commits] == ['octocat', None, 'octocat', 'octocat', 'octocat']
    assert [c.is_merge for c in commits] == [False, False, True, False, False]
    assert [(c.additions, c.deletions) for c in commits] == [(5, 0), (2, 2), (0, 0), (7, 3), (1, 1)]
    assert all(c.authored_at.tzinfo is not None for c in commits)


def test_the_stored_state_records_the_listed_head_and_times(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello()])
    run = sync_once(make_fetcher, upstream)
    state = run.cache.sync_state(HELLO, 'commits')
    assert state is not None
    assert state.head_oid == 'h3'
    assert state.pushed_at == upstream.repos[HELLO].pushed_at
    assert state.updated_at == upstream.repos[HELLO].updated_at
    assert state.watermark is None
    assert state.synced_at == state.full_synced_at == tests.fixtures.fetch.responses.NOW


def store_synced(
    cache: wambatic.fetch.cache.Cache, name: str, hours: int | None, owner: str = 'octocat'
) -> None:
    """List `name`; unless `hours` is None, store a commits state `hours` after T0."""
    repo = wambatic.fetch.base.parse_repo(FakeRepo(name, history('c', 1)).node())
    cache.upsert_repos(owner, [repo], complete=False)
    if hours is not None:
        state = wambatic.fetch.base.SyncState(
            repo=name,
            resource='commits',
            watermark=None,
            head_oid=repo.head_oid,
            pushed_at=repo.pushed_at,
            updated_at=repo.updated_at,
            synced_at=T0 + datetime.timedelta(hours=hours),
            full_synced_at=T0,
        )
        cache.write_commits(name, [], state, replace=False)


def provenance_of(
    make_fetcher: tests.conftest.MakeFetcher,
    cache: wambatic.fetch.cache.Cache,
    resources: frozenset[str] = COMMITS,
    subject: wambatic.fetch.base.Subject = OWNER,
) -> tuple[dict[str, str], int]:
    async def scenario() -> tuple[dict[str, str], int]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, cache=cache)
            result = await fetcher.provenance(subject, resources)
            return result, len(server.received)

    return asyncio.run(scenario())


def test_provenance_fetched_at_is_the_earliest_sync_and_sends_no_request(
    make_fetcher: tests.conftest.MakeFetcher, tmp_path: pathlib.Path
) -> None:
    cache = wambatic.fetch.cache.Cache.open(tmp_path / 'prov.sqlite3')
    try:
        store_synced(cache, HELLO, 5)
        store_synced(cache, SPOON, 2)
        result, requests = provenance_of(make_fetcher, cache)
    finally:
        cache.close()
    assert result['fetched_at:commits'] == at(0).replace(hour=11).isoformat()
    assert requests == 0


def test_provenance_is_never_for_a_listed_repo_that_was_not_synced(
    make_fetcher: tests.conftest.MakeFetcher, tmp_path: pathlib.Path
) -> None:
    cache = wambatic.fetch.cache.Cache.open(tmp_path / 'prov.sqlite3')
    try:
        store_synced(cache, HELLO, 5)
        store_synced(cache, SPOON, None)
        result, _ = provenance_of(make_fetcher, cache, COMMITS | {'releases'})
    finally:
        cache.close()
    assert result['fetched_at:commits'] == 'never'
    assert result['fetched_at:releases'] == 'never'


def test_provenance_holds_the_identity_and_the_override(
    make_fetcher: tests.conftest.MakeFetcher,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / 'prov.sqlite3'
    wambatic.fetch.cache.Cache.open(path).close()
    monkeypatch.setattr(wambatic.fetch.cache, 'SCHEMA_VERSION', 2)
    cache = wambatic.fetch.cache.Cache.open(path, ignore_version=True)
    try:
        result, _ = provenance_of(make_fetcher, cache)
        override = cache.version_override_at()
    finally:
        cache.close()
    assert {'schema_version', 'wambatic_version', 'query:COMMIT_HISTORY'} <= result.keys()
    assert result['version_override_at'] == override


def test_provenance_has_no_override_key_for_a_matching_cache(
    make_fetcher: tests.conftest.MakeFetcher, tmp_path: pathlib.Path
) -> None:
    cache = wambatic.fetch.cache.Cache.open(tmp_path / 'prov.sqlite3')
    try:
        result, _ = provenance_of(make_fetcher, cache)
    finally:
        cache.close()
    assert 'version_override_at' not in result


def test_provenance_rejects_an_unknown_resource(
    make_fetcher: tests.conftest.MakeFetcher, tmp_path: pathlib.Path
) -> None:
    cache = wambatic.fetch.cache.Cache.open(tmp_path / 'prov.sqlite3')
    try:
        with pytest.raises(ValueError, match='bogus'):
            provenance_of(make_fetcher, cache, frozenset({'bogus'}))
    finally:
        cache.close()


def test_commits_yields_oldest_first_and_honours_the_bounds(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([FakeRepo(HELLO, [*history('h', 2, 3), *history('g', 2, 1)])])
    run = sync_once(make_fetcher, upstream)

    async def oids(since: int | None, until: int | None) -> list[str]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, cache=run.cache)
            return [
                c.oid
                async for c in fetcher.commits(
                    listed(upstream),
                    None if since is None else at(since),
                    None if until is None else at(until),
                )
            ]

    assert asyncio.run(oids(None, None)) == ['g1', 'g2', 'h3', 'h4']
    assert asyncio.run(oids(2, 4)) == ['g2', 'h3']
    assert asyncio.run(oids(4, None)) == ['h4']


def test_an_error_on_page_two_leaves_no_rows_and_no_state(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    responses = tests.fixtures.fetch.responses
    node = responses.repo_node(HELLO, head='h2', pushed_at=T0, updated_at=T0)
    page_one = responses.history_page(
        [responses.history_node('h2', at(2), 'octocat', 1, 0)], True, 'c1'
    )
    routes = {
        ('POST', '/graphql'): [
            Canned(200, responses.owner_page([node], False, 'x')),
            Canned(200, page_one),
            *[Canned(500, responses.SERVER_ERROR)] * 3,
        ]
    }
    cache_holder: list[wambatic.fetch.cache.Cache] = []

    async def scenario() -> None:
        async with tests.fixtures.fetch.server.ReplayServer(routes) as server:
            fetcher = make_fetcher(server)
            cache_holder.append(fetcher.cache)
            async with fetcher:
                await fetcher.sync(OWNER, COMMITS)

    with pytest.raises(aiohttp.ClientResponseError):
        asyncio.run(scenario())
    assert stored(cache_holder[0]) == []
    assert cache_holder[0].sync_state(HELLO, 'commits') is None


def test_an_empty_repository_stores_a_state_and_no_commits(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([FakeRepo(HELLO, [])])
    run = sync_once(make_fetcher, upstream)
    state = run.cache.sync_state(HELLO, 'commits')
    assert run.kinds == ['listing']
    assert state is not None
    assert state.head_oid is None
    assert stored(run.cache) == []
    assert run.cache.read_repos(OWNER)[0].default_branch is None


def test_an_empty_repository_is_skipped_next_time(make_fetcher: tests.conftest.MakeFetcher) -> None:
    upstream = Upstream([FakeRepo(HELLO, [])])
    first = sync_once(make_fetcher, upstream)
    second = sync_once(make_fetcher, upstream, cache=first.cache)
    assert second.report.repos_skipped == 1
    assert second.kinds == ['listing']


def test_an_empty_repository_that_gets_a_commit_is_read_in_full(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([FakeRepo(HELLO, [])])
    first = sync_once(make_fetcher, upstream)
    upstream.repos[HELLO].push(*history('h', 2))
    second = sync_once(make_fetcher, upstream, cache=first.cache)
    assert second.kinds == ['listing', 'history']
    assert stored(first.cache) == ['h1', 'h2']


# Incremental commits by compare


def test_a_second_run_with_nothing_new_sends_only_the_listing(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    second = sync_once(make_fetcher, upstream, cache=first.cache)
    assert second.kinds == ['listing']
    assert second.report == wambatic.fetch.base.SyncReport(1, 1, {'commits': 0}, ())


def test_a_changed_listing_with_the_same_head_sends_no_request_and_advances_the_state(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    upstream.repos[HELLO].pushed_at += datetime.timedelta(hours=1)
    second = sync_once(make_fetcher, upstream, cache=first.cache)
    third = sync_once(make_fetcher, upstream, cache=first.cache)
    assert second.kinds == ['listing']
    assert second.report.repos_skipped == 0
    assert second.report.rows_written == {'commits': 0}
    assert stored(first.cache) == ['h1', 'h2', 'h3']
    assert third.report.repos_skipped == 1


def test_new_commits_are_found_by_compare_including_merged_in_older_ones(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    synced_at = first.cache.sync_state(HELLO, 'commits')
    assert synced_at is not None
    upstream.repos[HELLO].push(
        FakeCommit('branch', T0 - datetime.timedelta(days=20), 'mona', 10, 4),
        FakeCommit('merge', at(10), 'octocat', 0, 0, parents=2),
    )
    second = sync_once(make_fetcher, upstream, cache=first.cache)
    assert second.kinds == ['listing', 'compare', 'nodes']
    assert second.report.rows_written == {'commits': 2}
    assert second.report.full_refetches == ()
    commits = {c.oid: c for c in first.cache.read_commits(HELLO, None, None)}
    assert set(commits) == {'h1', 'h2', 'h3', 'branch', 'merge'}
    assert commits['branch'].authored_at < synced_at.synced_at
    assert (commits['branch'].additions, commits['branch'].deletions) == (10, 4)
    assert commits['branch'].author_login == 'mona'
    assert commits['merge'].is_merge and not commits['branch'].is_merge
    state = first.cache.sync_state(HELLO, 'commits')
    assert state is not None and state.head_oid == 'merge'
    assert state.full_synced_at == synced_at.full_synced_at


def test_a_commit_with_no_account_is_stored_without_a_login(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    upstream.repos[HELLO].push(FakeCommit('anon', at(9), None, 2, 1))
    sync_once(make_fetcher, upstream, cache=first.cache)
    anon = [c for c in first.cache.read_commits(HELLO, None, None) if c.oid == 'anon']
    assert [c.author_login for c in anon] == [None]


def test_a_compare_spanning_two_pages_is_read_fully(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    upstream.repos[HELLO].push(*history('n', 150, 10))
    second = sync_once(make_fetcher, upstream, cache=first.cache)
    assert second.kinds == ['listing', 'compare', 'compare', 'nodes', 'nodes']
    assert second.report.rows_written == {'commits': 150}
    assert len(stored(first.cache)) == 153


def test_a_compare_of_exactly_one_page_stops_without_a_second_request(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    upstream.repos[HELLO].push(*history('n', 100, 10))
    second = sync_once(make_fetcher, upstream, cache=first.cache)
    assert second.kinds == ['listing', 'compare', 'nodes']
    assert len(stored(first.cache)) == 103


def test_an_identical_compare_advances_only_the_state(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    responses = tests.fixtures.fetch.responses
    upstream = Upstream([hello()])
    run = sync_once(make_fetcher, upstream)
    repo = dataclasses.replace(listed(upstream), head_oid='moved')
    old = run.cache.sync_state(HELLO, 'commits')
    assert old is not None
    routes = {
        ('GET', f'/repos/{HELLO}/compare/h3...moved'): [
            Canned(200, responses.compare_response('identical', []))
        ]
    }

    async def scenario() -> int | None:
        async with tests.fixtures.fetch.server.ReplayServer(routes) as server:
            async with make_fetcher(server, cache=run.cache) as fetcher:
                return await fetcher.update_commits(repo, old)

    assert asyncio.run(scenario()) == 0
    new = run.cache.sync_state(HELLO, 'commits')
    assert new is not None and new.head_oid == 'moved'
    assert stored(run.cache) == ['h1', 'h2', 'h3']


@pytest.mark.parametrize('case', ['diverged', 'behind', 'not found'])
def test_a_stored_head_that_is_not_an_ancestor_asks_for_a_refetch_and_writes_nothing(
    make_fetcher: tests.conftest.MakeFetcher, case: str
) -> None:
    upstream = Upstream([hello()])
    run = sync_once(make_fetcher, upstream)
    repo = listed(upstream)
    old = run.cache.sync_state(HELLO, 'commits')
    assert old is not None
    if case == 'behind':
        old = dataclasses.replace(old, head_oid='h3')
        repo = dataclasses.replace(repo, head_oid='h2')
    else:
        old = dataclasses.replace(old, head_oid='gone')
        upstream.unknown_base = case

    async def scenario() -> int | None:
        async with tests.fixtures.fetch.server.ReplayServer({}, default=upstream.respond) as server:
            async with make_fetcher(server, cache=run.cache) as fetcher:
                return await fetcher.update_commits(repo, old)

    before = run.cache.sync_state(HELLO, 'commits')
    assert asyncio.run(scenario()) is None
    assert stored(run.cache) == ['h1', 'h2', 'h3']
    assert run.cache.sync_state(HELLO, 'commits') == before


@pytest.mark.parametrize('side', ['stored', 'listed'])
def test_a_missing_head_asks_for_a_refetch_without_a_request(
    make_fetcher: tests.conftest.MakeFetcher, side: str
) -> None:
    upstream = Upstream([hello()])
    run = sync_once(make_fetcher, upstream)
    repo = listed(upstream)
    old = run.cache.sync_state(HELLO, 'commits')
    assert old is not None
    if side == 'stored':
        old = dataclasses.replace(old, head_oid=None)
    else:
        repo = dataclasses.replace(repo, head_oid=None)

    async def scenario() -> tuple[int | None, int]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            async with make_fetcher(server, cache=run.cache) as fetcher:
                return await fetcher.update_commits(repo, old), len(server.received)

    assert asyncio.run(scenario()) == (None, 0)


def test_a_commit_with_no_line_counts_stores_nothing_and_names_its_oid(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    before = first.cache.sync_state(HELLO, 'commits')
    upstream.repos[HELLO].push(*history('n', 2, 10))
    upstream.dropped_nodes = {'C_n11'}
    with pytest.raises(wambatic.fetch.errors.GraphQLError, match='n11'):
        sync_once(make_fetcher, upstream, cache=first.cache)
    assert stored(first.cache) == ['h1', 'h2', 'h3']
    assert first.cache.sync_state(HELLO, 'commits') == before


# Rewritten history and full refresh


@pytest.mark.parametrize('unknown_base', ['diverged', 'not found'])
def test_a_force_push_re_reads_the_history_and_drops_the_old_commits(
    make_fetcher: tests.conftest.MakeFetcher, unknown_base: str
) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    upstream.unknown_base = unknown_base
    upstream.repos[HELLO].history = [FakeCommit('h1', at(1)), *history('x', 2, 2)]
    upstream.repos[HELLO].push()
    second = sync_once(make_fetcher, upstream, cache=first.cache)
    assert second.kinds == ['listing', 'compare', 'history']
    assert second.report.full_refetches == (HELLO,)
    assert stored(first.cache) == ['h1', 'x2', 'x3']
    state = first.cache.sync_state(HELLO, 'commits')
    assert state is not None and state.head_oid == 'x3'


def test_a_rewrite_resets_the_full_sync_time(make_fetcher: tests.conftest.MakeFetcher) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    old = first.cache.sync_state(HELLO, 'commits')
    assert old is not None
    first.cache.write_commits(
        HELLO, [], dataclasses.replace(old, full_synced_at=at(-90)), replace=False
    )
    upstream.repos[HELLO].history = history('x', 2)
    upstream.repos[HELLO].push()
    sync_once(make_fetcher, upstream, cache=first.cache)
    state = first.cache.sync_state(HELLO, 'commits')
    assert state is not None
    assert state.full_synced_at == tests.fixtures.fetch.responses.NOW


def test_full_refresh_re_reads_a_repo_whose_head_is_unchanged(
    make_fetcher: tests.conftest.MakeFetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    calls: list[str] = []
    original = wambatic.fetch.base.Fetcher.update_commits

    async def counting(
        self: wambatic.fetch.base.Fetcher,
        repo: wambatic.fetch.base.Repo,
        state: wambatic.fetch.base.SyncState,
    ) -> int | None:
        calls.append(repo.name_with_owner)
        return await original(self, repo, state)

    monkeypatch.setattr(wambatic.fetch.base.Fetcher, 'update_commits', counting)
    second = sync_once(make_fetcher, upstream, cache=first.cache, full_refresh=True)
    assert second.kinds == ['listing', 'history']
    assert second.report.repos_skipped == 0
    assert second.report.full_refetches == (HELLO,)
    assert calls == []


def test_a_rewrite_runs_update_commits_once(
    make_fetcher: tests.conftest.MakeFetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    upstream = Upstream([hello()])
    first = sync_once(make_fetcher, upstream)
    upstream.unknown_base = 'diverged'
    upstream.repos[HELLO].history = history('x', 2)
    upstream.repos[HELLO].push()
    calls: list[str] = []
    original = wambatic.fetch.base.Fetcher.update_commits

    async def counting(
        self: wambatic.fetch.base.Fetcher,
        repo: wambatic.fetch.base.Repo,
        state: wambatic.fetch.base.SyncState,
    ) -> int | None:
        calls.append(repo.name_with_owner)
        return await original(self, repo, state)

    monkeypatch.setattr(wambatic.fetch.base.Fetcher, 'update_commits', counting)
    sync_once(make_fetcher, upstream, cache=first.cache)
    assert calls == [HELLO]


def test_each_full_refetch_is_logged_with_its_reason(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    messages: list[str] = []
    sink = loguru.logger.add(lambda message: messages.append(str(message)), level='INFO')
    try:
        upstream = Upstream([hello()])
        first = sync_once(make_fetcher, upstream)
        sync_once(make_fetcher, upstream, cache=first.cache, full_refresh=True)
        upstream.unknown_base = 'diverged'
        upstream.repos[HELLO].history = history('x', 2)
        upstream.repos[HELLO].push()
        sync_once(make_fetcher, upstream, cache=first.cache)
    finally:
        loguru.logger.remove(sink)
    reasons = [m for m in messages if HELLO in m]
    assert len(reasons) == 3
    assert 'no previous sync' in reasons[0]
    assert 'full refresh requested' in reasons[1]
    assert 'history rewritten' in reasons[2]


# sync() across repos


def test_the_first_report_counts_every_repo_and_row(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    run = sync_once(make_fetcher, Upstream([spoon(), hello()]))
    assert run.report == wambatic.fetch.base.SyncReport(2, 0, {'commits': 5}, (HELLO, SPOON))


def test_a_second_run_fetches_only_the_listing(make_fetcher: tests.conftest.MakeFetcher) -> None:
    upstream = Upstream([hello(), spoon()])
    first = sync_once(make_fetcher, upstream)
    second = sync_once(make_fetcher, upstream, cache=first.cache)
    assert second.kinds == ['listing']
    assert second.report == wambatic.fetch.base.SyncReport(2, 2, {'commits': 0}, ())


def test_an_interrupted_run_resumes_with_only_the_repo_that_failed(
    make_fetcher: tests.conftest.MakeFetcher, fetch_settings: wambatic.settings.FetchSettings
) -> None:
    upstream = Upstream([hello(), spoon()])
    upstream.failing_history = {SPOON}
    one_at_a_time = settings_with(fetch_settings, workers=1)
    caches: list[wambatic.fetch.cache.Cache] = []

    async def failing() -> None:
        async with tests.fixtures.fetch.server.ReplayServer({}, default=upstream.respond) as server:
            fetcher = make_fetcher(server, one_at_a_time)
            caches.append(fetcher.cache)
            async with fetcher:
                await fetcher.sync(OWNER, COMMITS)

    with pytest.raises(aiohttp.ClientResponseError):
        asyncio.run(failing())
    cache = caches[0]
    assert stored(cache) == ['h1', 'h2', 'h3']
    assert cache.sync_state(SPOON, 'commits') is None
    upstream.failing_history = set()
    second = sync_once(make_fetcher, upstream, cache=cache, settings=one_at_a_time)
    assert second.kinds == ['listing', 'history']
    assert second.report == wambatic.fetch.base.SyncReport(2, 1, {'commits': 2}, (SPOON,))
    assert stored(cache, SPOON) == ['s1', 's2']


def test_no_more_than_workers_repos_are_synced_at_once(
    make_fetcher: tests.conftest.MakeFetcher, fetch_settings: wambatic.settings.FetchSettings
) -> None:
    upstream = Upstream([FakeRepo(f'octocat/r{n}', history(f'r{n}-', 2)) for n in range(4)])
    upstream.history_delay = 0.05
    run = sync_once(make_fetcher, upstream, settings=settings_with(fetch_settings, workers=2))
    assert run.kinds.count('history') == 4
    assert run.max_in_flight == 2


def test_one_worker_syncs_one_repo_at_a_time(
    make_fetcher: tests.conftest.MakeFetcher, fetch_settings: wambatic.settings.FetchSettings
) -> None:
    upstream = Upstream([FakeRepo(f'octocat/r{n}', history(f'r{n}-', 2)) for n in range(3)])
    upstream.history_delay = 0.02
    run = sync_once(make_fetcher, upstream, settings=settings_with(fetch_settings, workers=1))
    assert run.max_in_flight == 1


def test_an_unknown_resource_raises_before_any_request(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    async def scenario() -> int:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            async with make_fetcher(server) as fetcher:
                with pytest.raises(ValueError, match='nonsense'):
                    await fetcher.sync(OWNER, frozenset({'nonsense'}))
            return len(server.received)

    assert asyncio.run(scenario()) == 0


@pytest.mark.parametrize(
    ('resource', 'step'),
    [
        ('issues', 6),
        ('pull_requests', 6),
        ('releases', 8),
        ('star_events', 8),
        ('workflow_runs', 8),
    ],
)
def test_a_resource_not_built_yet_raises_before_any_request(
    make_fetcher: tests.conftest.MakeFetcher, resource: str, step: int
) -> None:
    async def scenario() -> int:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            async with make_fetcher(server) as fetcher:
                with pytest.raises(NotImplementedError, match=f'{resource} \\(step {step}\\)'):
                    await fetcher.sync(OWNER, frozenset({'commits', resource}))
            return len(server.received)

    assert asyncio.run(scenario()) == 0


def test_a_failure_in_one_repo_propagates_as_its_own_exception(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = Upstream([hello(), spoon()])
    upstream.failing_history = {HELLO, SPOON}
    with pytest.raises(aiohttp.ClientResponseError):
        sync_once(make_fetcher, upstream)


def test_no_value_in_the_cache_file_holds_the_token(
    make_fetcher: tests.conftest.MakeFetcher, tmp_path: pathlib.Path
) -> None:
    upstream = Upstream([hello(), spoon()])
    run = sync_once(make_fetcher, upstream)
    upstream.repos[HELLO].push(*history('n', 2, 10))
    sync_once(make_fetcher, upstream, cache=run.cache)
    path = tmp_path / 'cache' / 'cache.sqlite3'
    connection = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        for table in tables:
            for row in connection.execute(f'SELECT * FROM {table}'):
                assert 'test-token' not in repr(row), table
    finally:
        connection.close()
    for candidate in tmp_path.rglob('cache.sqlite3*'):
        assert b'test-token' not in candidate.read_bytes(), candidate.name


def cache_rows(fetcher: wambatic.fetch.base.Fetcher) -> list[tuple[str, int]]:
    tables = [
        row[0]
        for row in fetcher.cache.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ]
    return [
        (table, fetcher.cache.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])
        for table in tables
    ]


@pytest.mark.parametrize(
    ('login', 'body', 'expected'),
    [
        ('octocat', tests.fixtures.fetch.responses.USER_OK, 'user'),
        ('github', tests.fixtures.fetch.responses.ORGANIZATION_OK, 'org'),
    ],
)
def test_owner_kind_reads_the_type_with_one_request_and_writes_no_cache_rows(
    make_fetcher: tests.conftest.MakeFetcher, login: str, body: dict[str, str], expected: str
) -> None:
    async def scenario() -> tuple[str, list[str], list[tuple[str, int]], list[tuple[str, int]]]:
        routes = {('GET', f'/users/{login}'): [Canned(200, body)]}
        async with tests.fixtures.fetch.server.ReplayServer(routes) as server:
            async with make_fetcher(server) as fetcher:
                before = cache_rows(fetcher)
                kind = await fetcher.owner_kind(login)
                paths = [f'{r.method} {r.path}' for r in server.received]
                return kind, paths, before, cache_rows(fetcher)

    kind, paths, before, after = asyncio.run(scenario())
    assert kind == expected
    assert paths == [f'GET /users/{login}']
    assert after == before


@pytest.mark.parametrize(
    'canned',
    [
        Canned(404, tests.fixtures.fetch.responses.NOT_FOUND),
        Canned(200, {'login': 'dependabot', 'type': 'Bot'}),
        Canned(200, {'login': 'octocat'}),
        Canned(200, ['not', 'an', 'object']),
    ],
)
def test_owner_kind_raises_not_found_for_anything_that_is_not_a_user_or_an_organisation(
    make_fetcher: tests.conftest.MakeFetcher, canned: Canned
) -> None:
    async def scenario() -> None:
        routes = {('GET', '/users/nobody'): [canned]}
        async with tests.fixtures.fetch.server.ReplayServer(routes) as server:
            async with make_fetcher(server) as fetcher:
                await fetcher.owner_kind('nobody')

    with pytest.raises(wambatic.fetch.errors.NotFoundError):
        asyncio.run(scenario())


def test_owner_kind_names_the_login_and_type_in_its_error(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    async def scenario() -> None:
        routes = {('GET', '/users/robot'): [Canned(200, {'login': 'robot', 'type': 'Bot'})]}
        async with tests.fixtures.fetch.server.ReplayServer(routes) as server:
            async with make_fetcher(server) as fetcher:
                await fetcher.owner_kind('robot')

    with pytest.raises(wambatic.fetch.errors.NotFoundError, match="robot.*'Bot'"):
        asyncio.run(scenario())
