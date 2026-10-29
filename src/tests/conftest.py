import asyncio
import dataclasses
import datetime
import pathlib
import random
import typing

import pytest

import gitstat.fetch.base
import gitstat.fetch.cache
import gitstat.fetch.client
import gitstat.settings
import gitstat.stats
import gitstat.stats.base
import tests.fixtures.fetch.responses
import tests.fixtures.fetch.server
import tests.fixtures.settings
import tests.fixtures.stats

MakeClient = typing.Callable[..., gitstat.fetch.client.GitHubClient]
MakeFetcher = typing.Callable[..., gitstat.fetch.base.Fetcher]


@pytest.fixture
def config_file(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / 'config.json'
    path.write_text(tests.fixtures.settings.CONFIG_JSON)
    return path


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setattr(
        gitstat.settings, 'DEFAULT_CONFIG_PATH', tmp_path / 'default' / 'config.json'
    )
    monkeypatch.delenv('GITSTAT_CONFIG', raising=False)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)


class Sleeps(list[float]):
    async def __call__(self, seconds: float) -> None:
        self.append(seconds)


@pytest.fixture
def sleeps() -> Sleeps:
    return Sleeps()


@pytest.fixture
def fetch_settings() -> gitstat.settings.FetchSettings:
    return dataclasses.replace(gitstat.settings.FetchSettings(), max_retries=2, stats_retries=2)


@pytest.fixture
def make_client(sleeps: Sleeps, fetch_settings: gitstat.settings.FetchSettings) -> MakeClient:
    def make(
        server: tests.fixtures.fetch.server.ReplayServer,
        settings: gitstat.settings.FetchSettings = fetch_settings,
    ) -> gitstat.fetch.client.GitHubClient:
        return gitstat.fetch.client.GitHubClient(
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
    fetch_settings: gitstat.settings.FetchSettings,
) -> typing.Iterator[MakeFetcher]:
    caches: list[gitstat.fetch.cache.Cache] = []

    def make(
        server: tests.fixtures.fetch.server.ReplayServer,
        settings: gitstat.settings.FetchSettings = fetch_settings,
        cache: gitstat.fetch.cache.Cache | None = None,
    ) -> gitstat.fetch.base.Fetcher:
        if cache is None:
            cache = gitstat.fetch.cache.Cache.open(tmp_path / 'cache' / 'cache.sqlite3')
            caches.append(cache)
        return gitstat.fetch.base.Fetcher(
            'test-token', cache, settings, client=make_client(server, settings)
        )

    yield make
    for cache in caches:
        cache.close()


def store_commits(
    cache: gitstat.fetch.cache.Cache, repo: gitstat.fetch.base.Repo, synced_at: datetime.datetime
) -> None:
    commits = [c for c in tests.fixtures.stats.COMMITS if c.repo == repo.name_with_owner]
    state = gitstat.fetch.base.SyncState(
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


@pytest.fixture
def stats_cache(tmp_path: pathlib.Path) -> typing.Iterator[gitstat.fetch.cache.Cache]:
    """A cache holding the stats fixture's repositories and commits."""
    fixture = tests.fixtures.stats
    cache = gitstat.fetch.cache.Cache.open(tmp_path / 'stats' / 'cache.sqlite3')
    alpha, beta, gamma = fixture.REPOS
    cache.upsert_repos('octo-org', [alpha, beta], complete=True)
    cache.upsert_repos('octocat', [gamma], complete=True)
    store_commits(cache, alpha, fixture.ALPHA_SYNCED_AT)
    store_commits(cache, beta, fixture.BETA_SYNCED_AT)
    store_commits(cache, gamma, fixture.GAMMA_SYNCED_AT)
    yield cache
    cache.close()


@pytest.fixture
def stats_cache_path(stats_cache: gitstat.fetch.cache.Cache) -> pathlib.Path:
    return pathlib.Path(stats_cache.connection.execute('PRAGMA database_list').fetchone()[2])


@pytest.fixture
def stats_fetcher(stats_cache: gitstat.fetch.cache.Cache) -> gitstat.fetch.base.Fetcher:
    """A fetcher over `stats_cache`, never entered, so any request fails."""
    return gitstat.fetch.base.Fetcher('test-token', stats_cache, gitstat.settings.FetchSettings())


def compute_stats(
    fetcher: gitstat.fetch.base.Fetcher,
    subject: gitstat.fetch.base.Subject,
    request: gitstat.stats.base.StatsRequest,
) -> gitstat.stats.base.StatsResult:
    return asyncio.run(
        gitstat.stats.compute(subject, fetcher, request, clock=lambda: tests.fixtures.stats.NOW)
    )


@pytest.fixture
def org_result(stats_fetcher: gitstat.fetch.base.Fetcher) -> gitstat.stats.base.StatsResult:
    """The stats fixture's org by month with an author breakdown, from the default groups."""
    request = gitstat.stats.base.StatsRequest(
        since=tests.fixtures.stats.SINCE, until=tests.fixtures.stats.UNTIL, by_author=True
    )
    return compute_stats(stats_fetcher, tests.fixtures.stats.ORG, request)


@pytest.fixture
def repo_total_result(stats_fetcher: gitstat.fetch.base.Fetcher) -> gitstat.stats.base.StatsResult:
    """The stats fixture's repo octo-org/alpha as one bucket."""
    request = gitstat.stats.base.StatsRequest(
        granularity=gitstat.stats.base.Granularity.TOTAL,
        since=tests.fixtures.stats.SINCE,
        until=tests.fixtures.stats.UNTIL,
    )
    subject = gitstat.fetch.base.Subject('repo', 'octo-org', 'alpha')
    return compute_stats(stats_fetcher, subject, request)
