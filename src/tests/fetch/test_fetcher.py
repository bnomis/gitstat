import asyncio
import dataclasses
import datetime
import email.utils
import pathlib
import sqlite3
import threading
import typing

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
FakeIssue = tests.fixtures.fetch.upstream.FakeIssue
FakePull = tests.fixtures.fetch.upstream.FakePull
FakeFork = tests.fixtures.fetch.upstream.FakeFork
FakeRepo = tests.fixtures.fetch.upstream.FakeRepo
FakeStar = tests.fixtures.fetch.upstream.FakeStar
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
                first, _ = await fetcher.rest_cached(REST_PATH, {'b': '2', 'a': '1'})
                second, _ = await fetcher.rest_cached(REST_PATH, {'a': '1', 'b': '2'})
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
                first, _ = await fetcher.rest_cached(REST_PATH, {'page': '1'})
                second, _ = await fetcher.rest_cached(REST_PATH, {'page': '2'})
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
                    (await fetcher.rest_cached(REST_PATH, {}))[0],
                    (await fetcher.rest_cached(REST_PATH, {}))[0],
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
            return await make_fetcher(server, cache=run.cache).unchanged(changed, 'commits')

    assert asyncio.run(scenario()) is expected


def test_unchanged_is_false_with_no_state(make_fetcher: tests.conftest.MakeFetcher) -> None:
    upstream = Upstream([hello()])

    async def scenario() -> bool:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            return await make_fetcher(server).unchanged(listed(upstream), 'commits')

    assert asyncio.run(scenario()) is False


def test_unchanged_is_decided_per_resource(make_fetcher: tests.conftest.MakeFetcher) -> None:
    upstream = Upstream([hello()])
    run = sync_once(make_fetcher, upstream)

    async def scenario(resource: str) -> bool:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            return await make_fetcher(server, cache=run.cache).unchanged(listed(upstream), resource)

    assert asyncio.run(scenario('commits')) is True
    assert asyncio.run(scenario('issues')) is False
    assert asyncio.run(scenario('pull_requests')) is False


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
    monkeypatch.setattr(
        wambatic.fetch.cache, 'SCHEMA_VERSION', wambatic.fetch.cache.SCHEMA_VERSION + 1
    )
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


def test_progress_ends_equal_to_the_report(make_fetcher: tests.conftest.MakeFetcher) -> None:
    upstream = Upstream([hello(), spoon(), FakeRepo('octocat/Third', history('t', 2))])
    first = sync_once(make_fetcher, upstream)
    upstream.repos[HELLO].push(*history('h', 1, start=4))
    upstream.repos[SPOON].push(*history('s', 1, start=3))
    progress = wambatic.fetch.base.SyncProgress()

    async def scenario() -> wambatic.fetch.base.SyncReport:
        async with tests.fixtures.fetch.server.ReplayServer({}, default=upstream.respond) as server:
            async with make_fetcher(server, cache=first.cache) as fetcher:
                return await fetcher.sync(OWNER, COMMITS, progress=progress)

    report = asyncio.run(scenario())
    assert report.repos_skipped == 1
    assert progress.repos_listed == report.repos_listed
    assert progress.repos_pending == report.repos_listed - report.repos_skipped
    assert progress.repos_done == progress.repos_pending
    assert progress.rows_written == report.rows_written


def test_progress_is_readable_while_the_sync_runs(
    make_fetcher: tests.conftest.MakeFetcher, fetch_settings: wambatic.settings.FetchSettings
) -> None:
    upstream = Upstream([FakeRepo(f'octocat/r{n}', history(f'r{n}-', 2)) for n in range(4)])
    upstream.history_delay = 0.05
    progress = wambatic.fetch.base.SyncProgress()
    seen: list[tuple[int | None, int | None, int]] = []

    async def watch(done: asyncio.Event) -> None:
        while not done.is_set():
            seen.append((progress.repos_listed, progress.repos_pending, progress.repos_done))
            await asyncio.sleep(0.01)

    async def scenario() -> None:
        done = asyncio.Event()
        async with tests.fixtures.fetch.server.ReplayServer({}, default=upstream.respond) as server:
            fetcher = make_fetcher(server, settings=settings_with(fetch_settings, workers=1))
            async with fetcher:
                watcher = asyncio.create_task(watch(done))
                await fetcher.sync(OWNER, COMMITS, progress=progress)
                done.set()
                await watcher

    asyncio.run(scenario())
    assert any(listed_ == 4 and done < 4 for listed_, _, done in seen)


def test_a_sync_without_progress_is_unchanged(make_fetcher: tests.conftest.MakeFetcher) -> None:
    run = sync_once(make_fetcher, Upstream([hello(), spoon()]))
    assert run.report == wambatic.fetch.base.SyncReport(2, 0, {'commits': 5}, (HELLO, SPOON))


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


# Pull requests and issues of one repo

SERVER_DATE = datetime.datetime(2026, 10, 29, 12, 34, 56, tzinfo=datetime.UTC)
CLOCK = tests.fixtures.fetch.responses.NOW


@dataclasses.dataclass
class FlowRun:
    written: int
    kinds: list[str]
    cache: wambatic.fetch.cache.Cache


def flow_repo(pulls: int = 3, issues: int = 3) -> FakeRepo:
    return FakeRepo(
        HELLO,
        history('h', 1),
        pulls=[FakePull(n, at(n)) for n in range(1, pulls + 1)],
        issues=[FakeIssue(n, at(n)) for n in range(1, issues + 1)],
    )


def flow_upstream(**repo_changes: int) -> Upstream:
    upstream = Upstream([flow_repo(**repo_changes)])
    upstream.now = SERVER_DATE
    return upstream


def sync_flow(
    make_fetcher: tests.conftest.MakeFetcher,
    upstream: Upstream,
    resource: str,
    *,
    full_refresh: bool = False,
    cache: wambatic.fetch.cache.Cache | None = None,
    **kwargs: object,
) -> FlowRun:
    async def scenario() -> FlowRun:
        async with tests.fixtures.fetch.server.ReplayServer({}, default=upstream.respond) as server:
            fetcher = make_fetcher(server, cache=cache, **kwargs)
            async with fetcher:
                written = await fetcher.sync_updated(listed(upstream), resource, full_refresh)
            return FlowRun(written, upstream.requests(server), fetcher.cache)

    return asyncio.run(scenario())


def numbers(run: FlowRun, resource: str) -> list[int]:
    read = run.cache.read_pull_requests if resource == 'pull_requests' else run.cache.read_issues
    return [record.number for record in read(HELLO, None)]


def age_full_sync(cache: wambatic.fetch.cache.Cache, resource: str, days: int) -> None:
    with cache.connection:
        cache.connection.execute(
            'UPDATE sync_state SET full_synced_at = ? WHERE repo = ? AND resource = ?',
            (wambatic.fetch.cache.to_text(CLOCK - datetime.timedelta(days=days)), HELLO, resource),
        )


def test_a_first_sync_reads_every_page_and_stores_the_first_pages_date(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = flow_upstream()
    upstream.flow_page_size = 2
    run = sync_flow(make_fetcher, upstream, 'pull_requests')
    assert run.kinds == ['pull_requests', 'pull_requests']
    assert run.written == 3
    assert numbers(run, 'pull_requests') == [1, 2, 3]
    state = run.cache.sync_state(HELLO, 'pull_requests')
    assert state is not None
    assert state.watermark == SERVER_DATE
    assert state.watermark != CLOCK
    assert state.head_oid is None
    assert state.full_synced_at == CLOCK


def test_the_watermark_is_the_date_of_the_first_page_not_a_later_one(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = flow_upstream()
    upstream.flow_page_size = 2
    dates = iter([SERVER_DATE, SERVER_DATE + datetime.timedelta(minutes=5)])
    respond = upstream.respond

    def later(received: tests.fixtures.fetch.server.Received) -> Canned:
        canned = respond(received)
        date = email.utils.format_datetime(next(dates), usegmt=True)
        return dataclasses.replace(canned, headers={**canned.headers, 'Date': date})

    async def scenario() -> wambatic.fetch.cache.Cache:
        async with tests.fixtures.fetch.server.ReplayServer({}, default=later) as server:
            fetcher = make_fetcher(server)
            async with fetcher:
                await fetcher.sync_updated(listed(upstream), 'issues', False)
            return fetcher.cache

    state = asyncio.run(scenario()).sync_state(HELLO, 'issues')
    assert state is not None
    assert state.watermark == SERVER_DATE


def test_a_changed_pull_request_is_updated_and_unchanged_ones_are_untouched(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = flow_upstream()
    upstream.flow_page_size = 2
    first = sync_flow(make_fetcher, upstream, 'pull_requests')
    before = {pull.number: pull for pull in first.cache.read_pull_requests(HELLO, None)}
    changed = upstream.repos[HELLO].pulls[1]
    changed.state = 'MERGED'
    changed.merged_at = changed.closed_at = SERVER_DATE - datetime.timedelta(minutes=10)
    changed.updated_at = SERVER_DATE - datetime.timedelta(minutes=10)
    second = sync_flow(make_fetcher, upstream, 'pull_requests', cache=first.cache)
    assert second.kinds == ['pull_requests']
    assert second.written == 1
    after = {pull.number: pull for pull in second.cache.read_pull_requests(HELLO, None)}
    assert after[2].merged_at == changed.merged_at
    assert after[1] == before[1]
    assert after[3] == before[3]
    assert sorted(after) == [1, 2, 3]


def test_an_item_inside_the_overlap_is_read_again_and_rewritten_harmlessly(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = flow_upstream()
    inside = SERVER_DATE - datetime.timedelta(minutes=30)
    upstream.repos[HELLO].issues.append(FakeIssue(4, inside))
    first = sync_flow(make_fetcher, upstream, 'issues')
    before = first.cache.read_issues(HELLO, None)
    second = sync_flow(make_fetcher, upstream, 'issues', cache=first.cache)
    assert second.written == 1
    assert second.cache.read_issues(HELLO, None) == before


def test_a_failing_second_page_leaves_the_old_rows_and_state(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = flow_upstream()
    first = sync_flow(make_fetcher, upstream, 'pull_requests')
    state = first.cache.sync_state(HELLO, 'pull_requests')
    before = first.cache.read_pull_requests(HELLO, None)
    upstream.repos[HELLO].pulls.append(FakePull(9, at(9)))
    upstream.flow_page_size = 2
    upstream.failing_flow_cursors = {'2'}
    upstream.now = SERVER_DATE + datetime.timedelta(hours=3)
    with pytest.raises(aiohttp.ClientResponseError):
        sync_flow(make_fetcher, upstream, 'pull_requests', full_refresh=True, cache=first.cache)
    assert first.cache.read_pull_requests(HELLO, None) == before
    assert first.cache.sync_state(HELLO, 'pull_requests') == state


def test_the_full_refresh_interval_removes_a_deleted_issue(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = flow_upstream()
    first = sync_flow(make_fetcher, upstream, 'issues')
    assert numbers(first, 'issues') == [1, 2, 3]
    del upstream.repos[HELLO].issues[1]
    incremental = sync_flow(make_fetcher, upstream, 'issues', cache=first.cache)
    assert numbers(incremental, 'issues') == [1, 2, 3]
    age_full_sync(first.cache, 'issues', 31)
    upstream.flow_page_size = 1
    full = sync_flow(make_fetcher, upstream, 'issues', cache=first.cache)
    assert full.kinds == ['issues', 'issues']
    assert numbers(full, 'issues') == [1, 3]
    state = full.cache.sync_state(HELLO, 'issues')
    assert state is not None
    assert state.full_synced_at == CLOCK


def test_full_refresh_reads_everything_and_replaces_the_rows_at_once(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = flow_upstream()
    first = sync_flow(make_fetcher, upstream, 'pull_requests')
    del upstream.repos[HELLO].pulls[0]
    forced = sync_flow(
        make_fetcher, upstream, 'pull_requests', full_refresh=True, cache=first.cache
    )
    assert numbers(forced, 'pull_requests') == [2, 3]
    assert forced.written == 2


def test_an_incremental_sync_keeps_the_stored_full_sync_time(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = flow_upstream()
    first = sync_flow(make_fetcher, upstream, 'issues')
    age_full_sync(first.cache, 'issues', 3)
    sync_flow(make_fetcher, upstream, 'issues', cache=first.cache)
    state = first.cache.sync_state(HELLO, 'issues')
    assert state is not None
    assert state.full_synced_at == CLOCK - datetime.timedelta(days=3)
    assert state.synced_at == CLOCK


def test_a_state_with_no_watermark_is_read_in_full(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = flow_upstream()
    first = sync_flow(make_fetcher, upstream, 'issues')
    with first.cache.connection:
        first.cache.connection.execute('UPDATE sync_state SET watermark = NULL')
    upstream.flow_page_size = 1
    again = sync_flow(make_fetcher, upstream, 'issues', cache=first.cache)
    assert again.kinds == ['issues'] * 3
    assert again.written == 3


@pytest.mark.parametrize(
    ('days', 'expected'),
    [(29, False), (30, False), (31, True)],
)
def test_full_read_due_is_true_after_the_refresh_interval(
    make_fetcher: tests.conftest.MakeFetcher, days: int, expected: bool
) -> None:
    run = sync_flow(make_fetcher, flow_upstream(), 'issues')
    age_full_sync(run.cache, 'issues', days)
    state = run.cache.sync_state(HELLO, 'issues')

    async def scenario() -> tuple[bool, bool]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, cache=run.cache)
            return fetcher.full_read_due(state, CLOCK), fetcher.full_read_due(None, CLOCK)

    assert asyncio.run(scenario()) == (expected, True)


def test_the_read_methods_return_the_cached_rows_from_since(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = flow_upstream()
    run = sync_flow(make_fetcher, upstream, 'pull_requests')
    sync_flow(make_fetcher, upstream, 'issues', cache=run.cache)

    async def scenario() -> tuple[list[int], list[int], list[int], list[int]]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, cache=run.cache)
            repo = listed(upstream)
            since = at(2)
            return (
                [pull.number async for pull in fetcher.pull_requests(repo, since)],
                [item.number async for item in fetcher.issues(repo, since)],
                [pull.number async for pull in fetcher.pull_requests(repo, None)],
                [item.number async for item in fetcher.issues(repo, None)],
            )

    assert asyncio.run(scenario()) == ([2, 3], [2, 3], [1, 2, 3], [1, 2, 3])


# Syncing pull requests and issues for a subject

FLOW = frozenset({'commits', 'issues', 'pull_requests'})
HOUR = datetime.timedelta(hours=1)


def two_repo_upstream() -> Upstream:
    upstream = Upstream(
        [
            FakeRepo(
                HELLO,
                history('h', 2),
                pulls=[FakePull(1, at(1)), FakePull(2, at(2))],
                issues=[FakeIssue(1, at(1))],
            ),
            FakeRepo(
                SPOON,
                history('s', 2),
                pulls=[FakePull(1, at(1))],
                issues=[FakeIssue(1, at(1)), FakeIssue(2, at(2))],
            ),
        ]
    )
    upstream.now = SERVER_DATE
    return upstream


def requests_of(
    make_fetcher: tests.conftest.MakeFetcher,
    upstream: Upstream,
    cache: wambatic.fetch.cache.Cache,
    **kwargs: object,
) -> tuple[wambatic.fetch.base.SyncReport, list[tuple[str, str]]]:
    """Sync `FLOW` once more and return the report and each per-repo request as (kind, repo)."""

    async def scenario() -> tuple[wambatic.fetch.base.SyncReport, list[tuple[str, str]]]:
        async with tests.fixtures.fetch.server.ReplayServer({}, default=upstream.respond) as server:
            fetcher = make_fetcher(server, cache=cache)
            async with fetcher:
                report = await fetcher.sync(OWNER, FLOW, **kwargs)  # type: ignore[arg-type]
            kinds = upstream.requests(server)
            repos = [
                f'{r.json["variables"]["owner"]}/{r.json["variables"]["name"]}'  # type: ignore[index]
                if kind != 'listing'
                else ''
                for kind, r in zip(kinds, server.received, strict=True)
            ]
            return report, [pair for pair in zip(kinds, repos, strict=True) if pair[0] != 'listing']

    return asyncio.run(scenario())


def test_syncing_all_three_resources_backfills_each_and_reports_rows_for_each(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    run = sync_once(make_fetcher, two_repo_upstream(), resources=FLOW)
    assert run.report == wambatic.fetch.base.SyncReport(
        2, 0, {'commits': 4, 'issues': 3, 'pull_requests': 3}, (HELLO, SPOON)
    )
    assert run.kinds.count('pull_requests') == 2
    assert run.kinds.count('issues') == 2


def test_a_second_sync_with_nothing_newer_sends_only_the_listing_query(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = two_repo_upstream()
    first = sync_once(make_fetcher, upstream, resources=FLOW)
    second = sync_once(make_fetcher, upstream, resources=FLOW, cache=first.cache)
    assert second.kinds == ['listing']
    assert second.report == wambatic.fetch.base.SyncReport(
        2, 2, {'commits': 0, 'issues': 0, 'pull_requests': 0}, ()
    )


def test_a_newer_probe_on_one_repo_syncs_only_that_resource_of_that_repo(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = two_repo_upstream()
    first = sync_once(make_fetcher, upstream, resources=FLOW)
    upstream.repos[SPOON].issues.append(FakeIssue(3, SERVER_DATE - datetime.timedelta(minutes=5)))
    report, requests = requests_of(make_fetcher, upstream, first.cache)
    assert requests == [('issues', SPOON)]
    assert report.rows_written == {'commits': 0, 'issues': 1, 'pull_requests': 0}
    assert (report.repos_listed, report.repos_skipped) == (2, 1)


def test_a_repo_with_no_pull_requests_and_a_state_is_skipped_for_them(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = two_repo_upstream()
    upstream.repos[HELLO].pulls.clear()
    first = sync_once(make_fetcher, upstream, resources=FLOW)
    assert first.cache.sync_state(HELLO, 'pull_requests') is not None
    report, requests = requests_of(make_fetcher, upstream, first.cache)
    assert requests == []
    assert report.repos_skipped == 2


def test_full_refresh_reads_every_resource_of_every_repo(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = two_repo_upstream()
    first = sync_once(make_fetcher, upstream, resources=FLOW)
    report, requests = requests_of(make_fetcher, upstream, first.cache, full_refresh=True)
    assert sorted(requests) == sorted(
        (kind, name) for name in (HELLO, SPOON) for kind in ('history', 'issues', 'pull_requests')
    )
    assert report.repos_skipped == 0


def test_a_due_full_read_makes_flow_changed_even_with_an_old_probe(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = two_repo_upstream()
    first = sync_once(make_fetcher, upstream, resources=FLOW)
    age_full_sync(first.cache, 'issues', 31)
    report, requests = requests_of(make_fetcher, upstream, first.cache)
    assert requests == [('issues', HELLO)]
    assert report.rows_written['issues'] == 1


def test_no_more_than_workers_repos_run_when_each_repo_syncs_three_resources(
    make_fetcher: tests.conftest.MakeFetcher, fetch_settings: wambatic.settings.FetchSettings
) -> None:
    upstream = Upstream(
        [
            FakeRepo(f'octocat/r{n}', history(f'r{n}-', 2), pulls=[FakePull(1, at(1))])
            for n in range(4)
        ]
    )
    upstream.history_delay = 0.05
    run = sync_once(
        make_fetcher,
        upstream,
        resources=FLOW,
        settings=settings_with(fetch_settings, workers=2),
    )
    assert run.kinds.count('pull_requests') == 4
    assert run.max_in_flight == 2


def unchanged_for(
    make_fetcher: tests.conftest.MakeFetcher,
    cache: wambatic.fetch.cache.Cache,
    repo: wambatic.fetch.base.Repo,
    resource: str,
) -> bool:
    async def scenario() -> bool:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            return await make_fetcher(server, cache=cache).unchanged(repo, resource)

    return asyncio.run(scenario())


@pytest.mark.parametrize('resource', ['issues', 'pull_requests'])
def test_unchanged_for_a_flow_resource_follows_the_probe_the_state_and_the_interval(
    make_fetcher: tests.conftest.MakeFetcher, resource: str
) -> None:
    upstream = two_repo_upstream()
    run = sync_once(make_fetcher, upstream, resources=FLOW)
    repo = listed(upstream)
    probe = f'{resource}_updated_at'
    cutoff = SERVER_DATE - HOUR

    def check(**changes: datetime.datetime | None) -> bool:
        changed = dataclasses.replace(repo, **changes)  # type: ignore[arg-type]
        return unchanged_for(make_fetcher, run.cache, changed, resource)

    assert check() is True
    assert check(**{probe: None}) is True
    assert check(**{probe: cutoff - datetime.timedelta(seconds=1)}) is True
    assert check(**{probe: cutoff}) is False
    assert check(**{probe: SERVER_DATE}) is False
    age_full_sync(run.cache, resource, 31)
    assert check(**{probe: None}) is False
    assert (
        unchanged_for(
            make_fetcher,
            run.cache,
            dataclasses.replace(repo, name_with_owner='octocat/none'),
            resource,
        )
        is False
    )
    with run.cache.connection:
        run.cache.connection.execute('UPDATE sync_state SET watermark = NULL')
    age_full_sync(run.cache, resource, 0)
    assert check(**{probe: None}) is False


# Releases and workflow runs of one repo

FakeRelease = tests.fixtures.fetch.upstream.FakeRelease
FakeRun = tests.fixtures.fetch.upstream.FakeRun
DELIVERY = frozenset({'releases', 'workflow_runs'})
RUNS_FROM = SERVER_DATE - datetime.timedelta(days=60)


@dataclasses.dataclass
class DeliveryRun:
    written: int
    kinds: list[str]
    received: list[tests.fixtures.fetch.server.Received]
    cache: wambatic.fetch.cache.Cache
    rest_remaining: int | None


def delivery_repo(releases: int = 3, runs: int = 5) -> FakeRepo:
    return FakeRepo(
        HELLO,
        history('h', 1),
        releases=[
            FakeRelease(f'v{n}', at(n), published_at=at(n) + datetime.timedelta(minutes=5))
            for n in range(1, releases + 1)
        ],
        runs=[FakeRun(n, RUNS_FROM + datetime.timedelta(hours=n)) for n in range(1, runs + 1)],
    )


def delivery_upstream(**repo_changes: int) -> Upstream:
    upstream = Upstream([delivery_repo(**repo_changes)])
    upstream.now = SERVER_DATE
    return upstream


def sync_delivery(
    make_fetcher: tests.conftest.MakeFetcher,
    upstream: Upstream,
    method: str,
    *,
    full_refresh: bool = False,
    cache: wambatic.fetch.cache.Cache | None = None,
    **kwargs: object,
) -> DeliveryRun:
    """Run `Fetcher.sync_releases` or `Fetcher.sync_workflow_runs` against the upstream."""

    async def scenario() -> DeliveryRun:
        async with tests.fixtures.fetch.server.ReplayServer({}, default=upstream.respond) as server:
            fetcher = make_fetcher(server, cache=cache, **kwargs)
            async with fetcher:
                written = await getattr(fetcher, method)(listed(upstream), full_refresh)
            return DeliveryRun(
                written,
                upstream.requests(server),
                server.received,
                fetcher.cache,
                fetcher.client.rest_limit.remaining,
            )

    return asyncio.run(scenario())


def tags(cache: wambatic.fetch.cache.Cache) -> list[str]:
    return [release.tag_name for release in cache.read_releases(HELLO)]


def run_ids(cache: wambatic.fetch.cache.Cache) -> list[int]:
    return [run.id for run in cache.read_workflow_runs(HELLO, None)]


def test_a_first_release_sync_stores_the_published_releases_and_not_the_draft(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    upstream.repos[HELLO].releases.append(FakeRelease('v9', at(9), is_draft=True))
    run = sync_delivery(make_fetcher, upstream, 'sync_releases')
    assert run.written == 3
    assert tags(run.cache) == ['v1', 'v2', 'v3']
    state = run.cache.sync_state(HELLO, 'releases')
    assert state is not None
    assert state.probe == wambatic.fetch.base.release_probe(listed(upstream))
    assert (state.head_oid, state.watermark, state.full_synced_at) == (None, None, CLOCK)


def test_a_second_sync_with_the_same_probe_makes_no_releases_request(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    first = sync_once(make_fetcher, upstream, resources=frozenset({'releases'}))
    assert first.kinds == ['listing', 'releases']
    second = sync_once(make_fetcher, upstream, resources=frozenset({'releases'}), cache=first.cache)
    assert second.kinds == ['listing']
    assert second.report.repos_skipped == 1
    assert tags(second.cache) == ['v1', 'v2', 'v3']


def test_a_changed_release_count_reads_every_page_and_a_deleted_release_leaves(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    upstream.release_page_size = 2
    first = sync_delivery(make_fetcher, upstream, 'sync_releases')
    assert first.kinds == ['releases', 'releases']
    del upstream.repos[HELLO].releases[0]
    upstream.repos[HELLO].releases.append(FakeRelease('v4', at(4), published_at=at(4)))
    second = sync_once(make_fetcher, upstream, resources=frozenset({'releases'}), cache=first.cache)
    assert second.kinds == ['listing', 'releases', 'releases']
    assert tags(second.cache) == ['v2', 'v3', 'v4']


def test_publishing_the_newest_draft_is_picked_up_by_its_changed_update_time(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream(releases=0)
    draft = FakeRelease('v1', at(1), is_draft=True)
    upstream.repos[HELLO].releases.append(draft)
    first = sync_once(make_fetcher, upstream, resources=frozenset({'releases'}))
    assert tags(first.cache) == []
    draft.is_draft = False
    draft.published_at = at(5)
    draft.updated_at = at(5)
    second = sync_once(make_fetcher, upstream, resources=frozenset({'releases'}), cache=first.cache)
    assert second.kinds == ['listing', 'releases']
    assert tags(second.cache) == ['v1']


def test_a_passed_full_refresh_interval_reads_releases_again_with_an_equal_probe(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    first = sync_once(make_fetcher, upstream, resources=frozenset({'releases'}))
    age_full_sync(first.cache, 'releases', 31)
    second = sync_once(make_fetcher, upstream, resources=frozenset({'releases'}), cache=first.cache)
    assert second.kinds == ['listing', 'releases']
    state = second.cache.sync_state(HELLO, 'releases')
    assert state is not None
    assert state.full_synced_at == CLOCK


def test_an_interrupted_release_read_leaves_the_old_rows_and_state(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    first = sync_delivery(make_fetcher, upstream, 'sync_releases')
    state = first.cache.sync_state(HELLO, 'releases')
    upstream.repos[HELLO].releases.append(FakeRelease('v4', at(4), published_at=at(4)))
    upstream.release_page_size = 2
    upstream.failing_release_cursors = {'2'}
    with pytest.raises(aiohttp.ClientResponseError):
        sync_delivery(make_fetcher, upstream, 'sync_releases', cache=first.cache)
    assert tags(first.cache) == ['v1', 'v2', 'v3']
    assert first.cache.sync_state(HELLO, 'releases') == state


def test_fetcher_releases_reads_the_cache_oldest_first(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    first = sync_delivery(make_fetcher, upstream, 'sync_releases')

    async def scenario() -> list[str]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, cache=first.cache)
            return [release.tag_name async for release in fetcher.releases(listed(upstream))]

    assert asyncio.run(scenario()) == ['v1', 'v2', 'v3']


def test_a_first_run_sync_reads_every_page_stores_every_run_and_sends_no_created_filter(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream(runs=205)
    run = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    assert run.kinds == ['runs', 'runs', 'runs']
    assert run.written == 205
    assert run_ids(run.cache) == list(range(1, 206))
    assert all('created' not in item.query for item in run.received)
    assert all(item.query['exclude_pull_requests'] == 'true' for item in run.received)
    state = run.cache.sync_state(HELLO, 'workflow_runs')
    assert state is not None
    assert state.watermark == SERVER_DATE
    assert (state.head_oid, state.full_synced_at) == (None, CLOCK)


def test_an_unchanged_second_run_sync_is_one_conditional_request_answered_304(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    before = first.cache.read_workflow_runs(HELLO, None)
    second = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs', cache=first.cache)
    assert second.kinds == ['runs']
    assert second.received[0].headers['If-None-Match'].startswith('"')
    assert second.rest_remaining is None
    assert first.rest_remaining is not None
    assert second.cache.read_workflow_runs(HELLO, None) == before
    state = second.cache.sync_state(HELLO, 'workflow_runs')
    assert state is not None
    assert state.watermark == SERVER_DATE


def test_a_new_run_on_the_first_page_stops_paging_at_the_cutoff(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream(runs=205)
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    upstream.repos[HELLO].runs.append(FakeRun(500, SERVER_DATE - datetime.timedelta(minutes=10)))
    second = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs', cache=first.cache)
    assert second.kinds == ['runs']
    assert second.written == 1
    assert 500 in run_ids(second.cache)
    assert len(run_ids(second.cache)) == 206


def test_a_run_inside_the_overlap_window_is_read_again_and_rewritten_harmlessly(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream(runs=0)
    inside = SERVER_DATE - datetime.timedelta(minutes=30)
    upstream.repos[HELLO].runs.append(FakeRun(1, inside))
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    before = first.cache.read_workflow_runs(HELLO, None)
    second = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs', cache=first.cache)
    assert second.written == 1
    assert second.cache.read_workflow_runs(HELLO, None) == before


def unfinished_upstream() -> Upstream:
    upstream = delivery_upstream(runs=0)
    upstream.repos[HELLO].runs.extend(
        [
            FakeRun(1, at(1), status='in_progress', conclusion=None),
            FakeRun(2, at(5)),
        ]
    )
    return upstream


def test_an_unfinished_run_not_on_the_pages_read_is_read_again_by_id_and_completes(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = unfinished_upstream()
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    assert first.cache.unfinished_runs(HELLO) == [1]
    finished = upstream.repos[HELLO].runs[0]
    finished.status, finished.conclusion = 'completed', 'failure'
    second = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs', cache=first.cache)
    assert second.kinds == ['runs', 'run']
    assert second.received[1].path.endswith('/actions/runs/1')
    assert 'If-None-Match' not in second.received[1].headers
    assert second.cache.unfinished_runs(HELLO) == []
    rerun = second.cache.read_workflow_runs(HELLO, None)[0]
    assert (rerun.id, rerun.status, rerun.conclusion) == (1, 'completed', 'failure')


def test_an_unfinished_run_that_github_no_longer_has_is_removed(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = unfinished_upstream()
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    del upstream.repos[HELLO].runs[0]
    second = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs', cache=first.cache)
    assert second.kinds == ['runs', 'run']
    assert run_ids(second.cache) == [2]


def test_no_actions_data_is_an_empty_list_with_no_watermark_from_the_local_clock(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    upstream.repos[HELLO].has_actions = False
    run = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    assert (run.written, run.kinds) == (0, ['runs'])
    state = run.cache.sync_state(HELLO, 'workflow_runs')
    assert state is not None
    assert state.watermark is None
    assert state.synced_at == CLOCK


def test_a_missing_list_later_keeps_the_rows_and_the_previous_watermark(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    upstream.repos[HELLO].has_actions = False
    upstream.now = SERVER_DATE + datetime.timedelta(hours=5)
    second = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs', cache=first.cache)
    assert second.written == 0
    assert run_ids(second.cache) == [1, 2, 3, 4, 5]
    state = second.cache.sync_state(HELLO, 'workflow_runs')
    assert state is not None
    assert state.watermark == SERVER_DATE


def test_full_refresh_reads_every_page_and_drops_a_run_github_no_longer_lists(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream(runs=205)
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    del upstream.repos[HELLO].runs[0]
    incremental = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs', cache=first.cache)
    assert incremental.kinds == ['runs']
    assert 1 in run_ids(incremental.cache)
    forced = sync_delivery(
        make_fetcher, upstream, 'sync_workflow_runs', full_refresh=True, cache=first.cache
    )
    assert forced.kinds == ['runs', 'runs', 'runs']
    assert run_ids(forced.cache) == list(range(2, 206))


def test_the_full_refresh_interval_reads_every_page_of_runs(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream(runs=205)
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    del upstream.repos[HELLO].runs[0]
    age_full_sync(first.cache, 'workflow_runs', 31)
    second = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs', cache=first.cache)
    assert second.kinds == ['runs', 'runs', 'runs']
    assert 1 not in run_ids(second.cache)
    state = second.cache.sync_state(HELLO, 'workflow_runs')
    assert state is not None
    assert state.full_synced_at == CLOCK


def test_a_list_response_without_a_date_is_malformed(
    make_fetcher: tests.conftest.MakeFetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wambatic.fetch.client, 'header_date', lambda response: None)
    with pytest.raises(wambatic.fetch.errors.GraphQLError, match='Date'):
        sync_delivery(make_fetcher, delivery_upstream(), 'sync_workflow_runs')


def test_an_interrupted_run_read_keeps_the_old_rows_and_watermark(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream(runs=205)
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    state = first.cache.sync_state(HELLO, 'workflow_runs')
    upstream.repos[HELLO].runs.append(FakeRun(900, at(30)))
    upstream.failing_run_pages = {2}
    upstream.now = SERVER_DATE + datetime.timedelta(hours=3)
    with pytest.raises(aiohttp.ClientResponseError):
        sync_delivery(
            make_fetcher, upstream, 'sync_workflow_runs', full_refresh=True, cache=first.cache
        )
    assert run_ids(first.cache) == list(range(1, 206))
    assert first.cache.sync_state(HELLO, 'workflow_runs') == state


def test_sync_of_releases_and_runs_reports_rows_for_both_and_never_skips_a_repo(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    first = sync_once(make_fetcher, upstream, resources=DELIVERY)
    assert first.report.rows_written == {'releases': 3, 'workflow_runs': 5}
    assert first.kinds == ['listing', 'releases', 'runs']
    second = sync_once(make_fetcher, upstream, resources=DELIVERY, cache=first.cache)
    assert second.kinds == ['listing', 'runs']
    assert second.report.repos_skipped == 0
    assert second.report.rows_written['releases'] == 0


def test_fetcher_workflow_runs_reads_the_cache_from_since_oldest_first(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')

    async def scenario() -> list[int]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, cache=first.cache)
            since = RUNS_FROM + datetime.timedelta(hours=3)
            return [run.id async for run in fetcher.workflow_runs(listed(upstream), since)]

    assert asyncio.run(scenario()) == [3, 4, 5]


def test_workflow_runs_are_never_unchanged(make_fetcher: tests.conftest.MakeFetcher) -> None:
    upstream = delivery_upstream()
    first = sync_delivery(make_fetcher, upstream, 'sync_workflow_runs')
    assert unchanged_for(make_fetcher, first.cache, listed(upstream), 'workflow_runs') is False


def test_releases_are_unchanged_only_for_an_equal_probe_inside_the_interval(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = delivery_upstream()
    first = sync_delivery(make_fetcher, upstream, 'sync_releases')
    repo = listed(upstream)
    assert unchanged_for(make_fetcher, first.cache, repo, 'releases') is True
    more = dataclasses.replace(repo, releases_count=repo.releases_count + 1)
    assert unchanged_for(make_fetcher, first.cache, more, 'releases') is False
    later = dataclasses.replace(repo, releases_updated_at=at(20))
    assert unchanged_for(make_fetcher, first.cache, later, 'releases') is False
    age_full_sync(first.cache, 'releases', 31)
    assert unchanged_for(make_fetcher, first.cache, repo, 'releases') is False


# Stars

STARS = frozenset({'star_events'})
DAY = datetime.timedelta(days=1)


def popularity_repo(stars: int = 5, forks: int = 0) -> FakeRepo:
    return FakeRepo(
        HELLO,
        history('h', 1),
        stars=[FakeStar(f'U_{n}', SERVER_DATE - n * DAY) for n in range(1, stars + 1)],
        forks=[FakeFork(100 + n, SERVER_DATE - n * DAY) for n in range(1, forks + 1)],
    )


def popularity_upstream(**repo_changes: int) -> Upstream:
    upstream = Upstream([popularity_repo(**repo_changes)])
    upstream.now = SERVER_DATE
    return upstream


def star_ids(cache: wambatic.fetch.cache.Cache) -> list[str]:
    return sorted(star.user_id for star in cache.read_star_events(HELLO))


def test_a_first_star_sync_reads_every_page_and_stores_every_star(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    upstream.star_page_size = 2
    run = sync_once(make_fetcher, upstream, resources=STARS)
    assert run.kinds == ['listing', 'stargazers', 'stargazers', 'stargazers']
    assert run.report.rows_written == {'star_events': 5}
    assert star_ids(run.cache) == ['U_1', 'U_2', 'U_3', 'U_4', 'U_5']
    state = run.cache.sync_state(HELLO, 'star_events')
    assert state is not None
    assert state.probe == '5'
    assert (state.watermark, state.head_oid, state.full_synced_at) == (SERVER_DATE, None, CLOCK)


def test_an_unchanged_star_count_makes_no_stargazers_request(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    first = sync_once(make_fetcher, upstream, resources=STARS)
    second = sync_once(make_fetcher, upstream, resources=STARS, cache=first.cache)
    assert second.kinds == ['listing']
    assert second.report.repos_skipped == 1
    assert star_ids(second.cache) == star_ids(first.cache)


def test_a_higher_star_count_reads_the_first_page_and_stops_at_the_cutoff(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    upstream.star_page_size = 2
    first = sync_once(make_fetcher, upstream, resources=STARS)
    upstream.repos[HELLO].stars.append(
        FakeStar('U_new', SERVER_DATE - datetime.timedelta(minutes=10))
    )
    second = sync_once(make_fetcher, upstream, resources=STARS, cache=first.cache)
    assert second.kinds == ['listing', 'stargazers']
    assert second.report.rows_written == {'star_events': 1}
    assert star_ids(second.cache) == ['U_1', 'U_2', 'U_3', 'U_4', 'U_5', 'U_new']
    state = second.cache.sync_state(HELLO, 'star_events')
    assert state is not None
    assert state.probe == '6'
    assert state.full_synced_at == CLOCK


def test_a_lower_star_count_reads_every_page_and_a_removed_star_leaves_the_cache(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    upstream.star_page_size = 2
    first = sync_once(make_fetcher, upstream, resources=STARS)
    del upstream.repos[HELLO].stars[2]
    second = sync_once(make_fetcher, upstream, resources=STARS, cache=first.cache)
    assert second.kinds == ['listing', 'stargazers', 'stargazers']
    assert star_ids(second.cache) == ['U_1', 'U_2', 'U_4', 'U_5']


def test_a_removed_and_an_added_star_leave_the_count_alone_until_the_full_read(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    first = sync_once(make_fetcher, upstream, resources=STARS)
    stars = upstream.repos[HELLO].stars
    del stars[4]
    stars.append(FakeStar('U_new', SERVER_DATE - 2 * datetime.timedelta(hours=1)))
    second = sync_once(make_fetcher, upstream, resources=STARS, cache=first.cache)
    assert second.kinds == ['listing']
    age_full_sync(first.cache, 'star_events', 31)
    third = sync_once(make_fetcher, upstream, resources=STARS, cache=first.cache)
    assert third.kinds == ['listing', 'stargazers']
    assert star_ids(third.cache) == ['U_1', 'U_2', 'U_3', 'U_4', 'U_new']


def test_a_passed_full_refresh_interval_reads_every_page_of_stars_with_an_equal_count(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    upstream.star_page_size = 2
    first = sync_once(make_fetcher, upstream, resources=STARS)
    age_full_sync(first.cache, 'star_events', 31)
    second = sync_once(make_fetcher, upstream, resources=STARS, cache=first.cache)
    assert second.kinds == ['listing', 'stargazers', 'stargazers', 'stargazers']
    state = second.cache.sync_state(HELLO, 'star_events')
    assert state is not None
    assert state.full_synced_at == CLOCK


def test_full_refresh_reads_every_page_of_stars_of_an_unchanged_repo(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    first = sync_once(make_fetcher, upstream, resources=STARS)
    second = sync_once(
        make_fetcher, upstream, resources=STARS, cache=first.cache, full_refresh=True
    )
    assert second.kinds == ['listing', 'stargazers']


@pytest.mark.parametrize('hidden', ['empty', 'forbidden'])
def test_stargazers_the_token_cannot_see_are_recorded_as_hidden_not_as_no_stars(
    make_fetcher: tests.conftest.MakeFetcher, hidden: typing.Literal['empty', 'forbidden']
) -> None:
    upstream = popularity_upstream()
    upstream.repos[HELLO].hidden_stars = hidden
    run = sync_once(make_fetcher, upstream, resources=STARS)
    assert run.kinds == ['listing', 'stargazers']
    assert run.report.rows_written == {'star_events': 0}
    assert star_ids(run.cache) == []
    state = run.cache.sync_state(HELLO, 'star_events')
    assert state is not None
    assert state.probe == wambatic.fetch.base.STARS_HIDDEN
    assert state.watermark is None
    assert asyncio.run(run.fetcher.stars_hidden(listed(upstream)))


def test_hidden_stargazers_are_read_again_at_every_sync_and_stored_once_visible(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    upstream.repos[HELLO].hidden_stars = 'empty'
    first = sync_once(make_fetcher, upstream, resources=STARS)
    again = sync_once(make_fetcher, upstream, resources=STARS, cache=first.cache)
    assert again.kinds == ['listing', 'stargazers']
    upstream.repos[HELLO].hidden_stars = None
    visible = sync_once(make_fetcher, upstream, resources=STARS, cache=first.cache)
    assert star_ids(visible.cache) == ['U_1', 'U_2', 'U_3', 'U_4', 'U_5']
    state = visible.cache.sync_state(HELLO, 'star_events')
    assert state is not None
    assert state.probe == '5'
    assert not asyncio.run(visible.fetcher.stars_hidden(listed(upstream)))


def test_a_repository_with_no_stars_is_not_hidden(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(stars=0)
    run = sync_once(make_fetcher, upstream, resources=STARS)
    state = run.cache.sync_state(HELLO, 'star_events')
    assert state is not None
    assert state.probe == '0'
    assert not asyncio.run(run.fetcher.stars_hidden(listed(upstream)))


def test_an_interrupted_star_read_leaves_the_old_rows_and_state(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    first = sync_once(make_fetcher, upstream, resources=STARS)
    state = first.cache.sync_state(HELLO, 'star_events')
    del upstream.repos[HELLO].stars[0]
    upstream.star_page_size = 2
    upstream.failing_star_cursors = {'2'}
    with pytest.raises(aiohttp.ClientResponseError):
        sync_once(make_fetcher, upstream, resources=STARS, cache=first.cache)
    assert star_ids(first.cache) == ['U_1', 'U_2', 'U_3', 'U_4', 'U_5']
    assert first.cache.sync_state(HELLO, 'star_events') == state


def test_fetcher_star_events_reads_the_cache_oldest_first(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    first = sync_once(make_fetcher, upstream, resources=STARS)

    async def scenario() -> list[str]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, cache=first.cache)
            return [star.user_id async for star in fetcher.star_events(listed(upstream))]

    assert asyncio.run(scenario()) == ['U_5', 'U_4', 'U_3', 'U_2', 'U_1']


def test_a_star_is_stored_without_a_login(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    first = sync_once(make_fetcher, upstream, resources=STARS)
    columns = [row[1] for row in first.cache.connection.execute('PRAGMA table_info(star_events)')]
    assert columns == ['repo', 'user_id', 'starred_at']


def test_star_events_are_unchanged_only_for_an_equal_count_inside_the_interval(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream()
    first = sync_once(make_fetcher, upstream, resources=STARS)
    repo = listed(upstream)
    assert unchanged_for(make_fetcher, first.cache, repo, 'star_events') is True
    more = dataclasses.replace(repo, stargazer_count=repo.stargazer_count + 1)
    assert unchanged_for(make_fetcher, first.cache, more, 'star_events') is False
    fewer = dataclasses.replace(repo, stargazer_count=repo.stargazer_count - 1)
    assert unchanged_for(make_fetcher, first.cache, fewer, 'star_events') is False
    age_full_sync(first.cache, 'star_events', 31)
    assert unchanged_for(make_fetcher, first.cache, repo, 'star_events') is False


# Forks

FORKS = frozenset({'forks'})


def fork_ids(cache: wambatic.fetch.cache.Cache) -> list[int]:
    return sorted(fork.id for fork in cache.read_forks(HELLO))


def fork_requests(server: tests.fixtures.fetch.server.ReplayServer) -> list[str]:
    return [received.path for received in server.received if received.path.endswith('/forks')]


def test_a_first_fork_sync_reads_every_page_and_stores_every_fork(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=101)
    run = sync_once(make_fetcher, upstream, resources=FORKS)
    assert run.kinds == ['listing', 'forks', 'forks']
    assert run.report.rows_written == {'forks': 101}
    assert fork_ids(run.cache) == list(range(101, 202))
    state = run.cache.sync_state(HELLO, 'forks')
    assert state is not None
    assert state.probe == '101'
    assert (state.watermark, state.head_oid, state.full_synced_at) == (SERVER_DATE, None, CLOCK)


def test_the_fork_list_is_requested_newest_first_100_at_a_time_without_an_etag(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=101)
    first = sync_once(make_fetcher, upstream, resources=FORKS)

    async def scenario() -> list[tests.fixtures.fetch.server.Received]:
        async with tests.fixtures.fetch.server.ReplayServer({}, default=upstream.respond) as server:
            async with make_fetcher(server, cache=first.cache) as fetcher:
                await fetcher.sync_forks(listed(upstream), True)
            return [r for r in server.received if r.path.endswith('/forks')]

    received = asyncio.run(scenario())
    assert [r.query for r in received] == [
        {'sort': 'newest', 'per_page': '100', 'page': '1'},
        {'sort': 'newest', 'per_page': '100', 'page': '2'},
    ]
    assert not any('If-None-Match' in r.headers for r in received)
    assert first.cache.connection.execute('SELECT COUNT(*) FROM etags').fetchone() == (0,)


def test_an_unchanged_fork_count_makes_no_fork_request(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=3)
    first = sync_once(make_fetcher, upstream, resources=FORKS)
    second = sync_once(make_fetcher, upstream, resources=FORKS, cache=first.cache)
    assert second.kinds == ['listing']
    assert second.report.repos_skipped == 1


def test_a_higher_fork_count_stops_at_the_cutoff(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=3)
    first = sync_once(make_fetcher, upstream, resources=FORKS)
    upstream.repos[HELLO].forks.append(FakeFork(999, SERVER_DATE - datetime.timedelta(minutes=10)))
    second = sync_once(make_fetcher, upstream, resources=FORKS, cache=first.cache)
    assert second.kinds == ['listing', 'forks']
    assert second.report.rows_written == {'forks': 1}
    assert fork_ids(second.cache) == [101, 102, 103, 999]


def test_a_lower_fork_count_reads_every_page_and_a_deleted_fork_leaves(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=3)
    first = sync_once(make_fetcher, upstream, resources=FORKS)
    del upstream.repos[HELLO].forks[1]
    second = sync_once(make_fetcher, upstream, resources=FORKS, cache=first.cache)
    assert second.kinds == ['listing', 'forks']
    assert fork_ids(second.cache) == [101, 103]


def test_a_fork_of_a_fork_changes_the_count_and_costs_one_read_that_finds_nothing(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=2)
    first = sync_once(make_fetcher, upstream, resources=FORKS)
    upstream.repos[HELLO].forks_of_forks = 1
    second = sync_once(make_fetcher, upstream, resources=FORKS, cache=first.cache)
    assert second.kinds == ['listing', 'forks']
    assert second.report.rows_written == {'forks': 0}
    assert fork_ids(second.cache) == [101, 102]


def test_full_refresh_reads_every_page_of_forks_of_an_unchanged_repo(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=3)
    first = sync_once(make_fetcher, upstream, resources=FORKS)
    second = sync_once(
        make_fetcher, upstream, resources=FORKS, cache=first.cache, full_refresh=True
    )
    assert second.kinds == ['listing', 'forks']


def test_a_missing_fork_list_writes_no_forks_and_does_not_raise(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=3)
    upstream.repos[HELLO].has_forks = False
    run = sync_once(make_fetcher, upstream, resources=FORKS)
    assert run.report.rows_written == {'forks': 0}
    state = run.cache.sync_state(HELLO, 'forks')
    assert state is not None
    assert (state.watermark, state.probe) == (None, '3')


def test_a_missing_fork_list_later_keeps_the_rows_and_the_previous_watermark(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=3)
    first = sync_once(make_fetcher, upstream, resources=FORKS)
    upstream.repos[HELLO].has_forks = False
    upstream.repos[HELLO].forks.append(FakeFork(999, SERVER_DATE))
    second = sync_once(make_fetcher, upstream, resources=FORKS, cache=first.cache)
    assert fork_ids(second.cache) == [101, 102, 103]
    state = second.cache.sync_state(HELLO, 'forks')
    assert state is not None
    assert state.watermark == SERVER_DATE


def test_a_fork_list_response_without_a_date_is_malformed(
    make_fetcher: tests.conftest.MakeFetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wambatic.fetch.client, 'header_date', lambda response: None)
    with pytest.raises(wambatic.fetch.errors.GraphQLError, match='Date'):
        sync_once(make_fetcher, popularity_upstream(forks=3), resources=FORKS)


def test_an_interrupted_fork_read_keeps_the_old_rows_and_watermark(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=101)
    first = sync_once(make_fetcher, upstream, resources=FORKS)
    state = first.cache.sync_state(HELLO, 'forks')
    del upstream.repos[HELLO].forks[0]
    upstream.failing_fork_pages = {2}
    with pytest.raises(aiohttp.ClientResponseError):
        sync_once(make_fetcher, upstream, resources=FORKS, cache=first.cache)
    assert len(fork_ids(first.cache)) == 101
    assert first.cache.sync_state(HELLO, 'forks') == state


def test_fetcher_forks_reads_the_cache_oldest_first(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=3)
    first = sync_once(make_fetcher, upstream, resources=FORKS)

    async def scenario() -> list[int]:
        async with tests.fixtures.fetch.server.ReplayServer({}) as server:
            fetcher = make_fetcher(server, cache=first.cache)
            return [fork.id async for fork in fetcher.forks(listed(upstream))]

    assert asyncio.run(scenario()) == [103, 102, 101]


def test_forks_are_unchanged_only_for_an_equal_count_inside_the_interval(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(forks=3)
    first = sync_once(make_fetcher, upstream, resources=FORKS)
    repo = listed(upstream)
    assert unchanged_for(make_fetcher, first.cache, repo, 'forks') is True
    more = dataclasses.replace(repo, fork_count=repo.fork_count + 1)
    assert unchanged_for(make_fetcher, first.cache, more, 'forks') is False
    age_full_sync(first.cache, 'forks', 31)
    assert unchanged_for(make_fetcher, first.cache, repo, 'forks') is False


def test_stars_and_forks_of_an_unchanged_repo_cost_only_the_listing(
    make_fetcher: tests.conftest.MakeFetcher,
) -> None:
    upstream = popularity_upstream(stars=3, forks=3)
    both = frozenset({'star_events', 'forks'})
    first = sync_once(make_fetcher, upstream, resources=both)
    assert first.kinds == ['listing', 'forks', 'stargazers']
    second = sync_once(make_fetcher, upstream, resources=both, cache=first.cache)
    assert second.kinds == ['listing']
    assert second.report.repos_skipped == 1
    assert second.report.rows_written == {'forks': 0, 'star_events': 0}


def test_every_resource_is_built() -> None:
    assert wambatic.fetch.base.BUILT_RESOURCES == wambatic.fetch.base.RESOURCES
