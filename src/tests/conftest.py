import asyncio
import dataclasses
import datetime
import pathlib
import random
import typing

import pytest

import tests.fixtures.fetch.responses
import tests.fixtures.fetch.server
import tests.fixtures.settings
import tests.fixtures.stats
import wambatic.fetch.base
import wambatic.fetch.cache
import wambatic.fetch.client
import wambatic.settings
import wambatic.stats
import wambatic.stats.base

MakeClient = typing.Callable[..., wambatic.fetch.client.GitHubClient]
MakeFetcher = typing.Callable[..., wambatic.fetch.base.Fetcher]


@pytest.fixture
def config_file(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / 'config.json'
    path.write_text(tests.fixtures.settings.CONFIG_JSON)
    return path


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setattr(
        wambatic.settings, 'DEFAULT_CONFIG_PATH', tmp_path / 'default' / 'config.json'
    )
    monkeypatch.delenv('WAMBATIC_CONFIG', raising=False)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)


class Sleeps(list[float]):
    async def __call__(self, seconds: float) -> None:
        self.append(seconds)


@pytest.fixture
def sleeps() -> Sleeps:
    return Sleeps()


@pytest.fixture
def fetch_settings() -> wambatic.settings.FetchSettings:
    return dataclasses.replace(wambatic.settings.FetchSettings(), max_retries=2, stats_retries=2)


@pytest.fixture
def make_client(sleeps: Sleeps, fetch_settings: wambatic.settings.FetchSettings) -> MakeClient:
    def make(
        server: tests.fixtures.fetch.server.ReplayServer,
        settings: wambatic.settings.FetchSettings = fetch_settings,
    ) -> wambatic.fetch.client.GitHubClient:
        return wambatic.fetch.client.GitHubClient(
            'test-token',
            settings,
            api_url=server.url,
            sleep=sleeps,
            clock=lambda: tests.fixtures.fetch.responses.NOW,
            rng=random.Random(0),
        )

    return make


@pytest.fixture
def make_fetcher(
    tmp_path: pathlib.Path,
    make_client: MakeClient,
    fetch_settings: wambatic.settings.FetchSettings,
) -> typing.Iterator[MakeFetcher]:
    caches: list[wambatic.fetch.cache.Cache] = []

    def make(
        server: tests.fixtures.fetch.server.ReplayServer,
        settings: wambatic.settings.FetchSettings = fetch_settings,
        cache: wambatic.fetch.cache.Cache | None = None,
    ) -> wambatic.fetch.base.Fetcher:
        if cache is None:
            cache = wambatic.fetch.cache.Cache.open(tmp_path / 'cache' / 'cache.sqlite3')
            caches.append(cache)
        return wambatic.fetch.base.Fetcher(
            'test-token', cache, settings, client=make_client(server, settings)
        )

    yield make
    for cache in caches:
        cache.close()


def store_commits(
    cache: wambatic.fetch.cache.Cache, repo: wambatic.fetch.base.Repo, synced_at: datetime.datetime
) -> None:
    commits = [c for c in tests.fixtures.stats.COMMITS if c.repo == repo.name_with_owner]
    state = wambatic.fetch.base.SyncState(
        repo=repo.name_with_owner,
        resource='commits',
        watermark=None,
        head_oid=repo.head_oid,
        pushed_at=repo.pushed_at,
        updated_at=repo.updated_at,
        synced_at=synced_at,
        full_synced_at=synced_at,
    )
    cache.write_commits(repo.name_with_owner, commits, state, replace=True)


def store_flow(
    cache: wambatic.fetch.cache.Cache, repo: wambatic.fetch.base.Repo, synced_at: datetime.datetime
) -> None:
    """Write the repo's fixture pull requests and issues with a sync state for each."""

    def state(resource: str) -> wambatic.fetch.base.SyncState:
        return wambatic.fetch.base.SyncState(
            repo=repo.name_with_owner,
            resource=resource,
            watermark=synced_at,
            head_oid=None,
            pushed_at=repo.pushed_at,
            updated_at=repo.updated_at,
            synced_at=synced_at,
            full_synced_at=synced_at,
        )

    name = repo.name_with_owner
    pulls = [p for p in tests.fixtures.stats.PULL_REQUESTS if p.repo == name]
    issues = [i for i in tests.fixtures.stats.ISSUES if i.repo == name]
    cache.write_pull_requests(name, pulls, state('pull_requests'), replace=True)
    cache.write_issues(name, issues, state('issues'), replace=True)


@pytest.fixture
def stats_cache(tmp_path: pathlib.Path) -> typing.Iterator[wambatic.fetch.cache.Cache]:
    """A cache holding the stats fixture's repositories, commits, pull requests and issues."""
    fixture = tests.fixtures.stats
    cache = wambatic.fetch.cache.Cache.open(tmp_path / 'stats' / 'cache.sqlite3')
    alpha, beta, gamma = fixture.REPOS
    cache.upsert_repos('octo-org', [alpha, beta], complete=True)
    cache.upsert_repos('octocat', [gamma], complete=True)
    store_commits(cache, alpha, fixture.ALPHA_SYNCED_AT)
    store_commits(cache, beta, fixture.BETA_SYNCED_AT)
    store_commits(cache, gamma, fixture.GAMMA_SYNCED_AT)
    store_flow(cache, alpha, fixture.ALPHA_SYNCED_AT)
    store_flow(cache, beta, fixture.BETA_SYNCED_AT)
    store_flow(cache, gamma, fixture.GAMMA_SYNCED_AT)
    yield cache
    cache.close()


@pytest.fixture
def stats_cache_path(stats_cache: wambatic.fetch.cache.Cache) -> pathlib.Path:
    return pathlib.Path(stats_cache.connection.execute('PRAGMA database_list').fetchone()[2])


@pytest.fixture
def stats_fetcher(stats_cache: wambatic.fetch.cache.Cache) -> wambatic.fetch.base.Fetcher:
    """A fetcher over `stats_cache`, never entered, so any request fails."""
    return wambatic.fetch.base.Fetcher('test-token', stats_cache, wambatic.settings.FetchSettings())


def compute_stats(
    fetcher: wambatic.fetch.base.Fetcher,
    subject: wambatic.fetch.base.Subject,
    request: wambatic.stats.base.StatsRequest,
) -> wambatic.stats.base.StatsResult:
    return asyncio.run(
        wambatic.stats.compute(subject, fetcher, request, clock=lambda: tests.fixtures.stats.NOW)
    )


@pytest.fixture
def org_result(stats_fetcher: wambatic.fetch.base.Fetcher) -> wambatic.stats.base.StatsResult:
    """The stats fixture's org by month with an author breakdown, from the default groups."""
    request = wambatic.stats.base.StatsRequest(
        since=tests.fixtures.stats.SINCE, until=tests.fixtures.stats.UNTIL, by_author=True
    )
    return compute_stats(stats_fetcher, tests.fixtures.stats.ORG, request)


@pytest.fixture
def repo_total_result(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> wambatic.stats.base.StatsResult:
    """The stats fixture's repo octo-org/alpha as one bucket."""
    request = wambatic.stats.base.StatsRequest(
        granularity=wambatic.stats.base.Granularity.TOTAL,
        since=tests.fixtures.stats.SINCE,
        until=tests.fixtures.stats.UNTIL,
    )
    subject = wambatic.fetch.base.Subject('repo', 'octo-org', 'alpha')
    return compute_stats(stats_fetcher, subject, request)


@pytest.fixture
def org_total_result(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> wambatic.stats.base.StatsResult:
    """The stats fixture's org as one bucket with an author breakdown."""
    request = wambatic.stats.base.StatsRequest(
        granularity=wambatic.stats.base.Granularity.TOTAL,
        since=tests.fixtures.stats.SINCE,
        until=tests.fixtures.stats.UNTIL,
        by_author=True,
    )
    return compute_stats(stats_fetcher, tests.fixtures.stats.ORG, request)


@pytest.fixture
def org_day_result(stats_fetcher: wambatic.fetch.base.Fetcher) -> wambatic.stats.base.StatsResult:
    """The stats fixture's org by day."""
    request = wambatic.stats.base.StatsRequest(
        granularity=wambatic.stats.base.Granularity.DAY,
        since=tests.fixtures.stats.SINCE,
        until=tests.fixtures.stats.UNTIL,
    )
    return compute_stats(stats_fetcher, tests.fixtures.stats.ORG, request)
