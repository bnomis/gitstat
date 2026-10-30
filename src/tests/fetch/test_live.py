import asyncio
import os
import pathlib

import pytest

import wambatic.fetch.base
import wambatic.fetch.cache
import wambatic.fetch.client
import wambatic.fetch.errors
import wambatic.fetch.queries
import wambatic.settings

TOKEN = os.environ.get('GITHUB_TOKEN', '')


@pytest.mark.live
@pytest.mark.skipif(not TOKEN, reason='GITHUB_TOKEN is not set')
def test_lists_octocat_repositories() -> None:
    async def scenario() -> tuple[list[str], int | None]:
        async with wambatic.fetch.client.GitHubClient(
            TOKEN, wambatic.settings.FetchSettings()
        ) as client:
            data = await client.graphql(
                wambatic.fetch.queries.OWNER_REPOSITORIES, {'login': 'octocat', 'cursor': None}
            )
            return repository_names(data), client.graphql_limit.remaining

    names, remaining = asyncio.run(scenario())
    assert 'octocat/Hello-World' in names
    assert isinstance(remaining, int)


@pytest.mark.live
@pytest.mark.skipif(not TOKEN, reason='GITHUB_TOKEN is not set')
def test_line_totals_match_code_frequency(tmp_path: pathlib.Path) -> None:
    subject = wambatic.fetch.base.Subject('repo', 'octocat', 'Hello-World')

    async def scenario() -> tuple[tuple[int, int], tuple[int, int]]:
        cache = wambatic.fetch.cache.Cache.open(tmp_path / 'cache.sqlite3')
        try:
            async with wambatic.fetch.base.Fetcher(
                TOKEN, cache, wambatic.settings.FetchSettings()
            ) as fetcher:
                await fetcher.sync(subject, frozenset({'commits'}))
                response = await fetcher.client.rest_get(
                    '/repos/octocat/Hello-World/stats/code_frequency'
                )
            commits = [
                commit
                for commit in cache.read_commits(subject.full_name, None, None)
                if not commit.is_merge
            ]
        finally:
            cache.close()
        assert isinstance(response.data, list)
        weekly = (
            sum(week[1] for week in response.data),
            -sum(week[2] for week in response.data),
        )
        return (sum(c.additions for c in commits), sum(c.deletions for c in commits)), weekly

    summed, weekly = asyncio.run(scenario())
    assert summed == weekly


@pytest.mark.live
@pytest.mark.skipif(not TOKEN, reason='GITHUB_TOKEN is not set')
@pytest.mark.parametrize('resource', ['star_events', 'forks'])
def test_stars_and_forks_are_cached(tmp_path: pathlib.Path, resource: str) -> None:
    """Some rows are stored. They are not compared with the listed counts: the REST fork list of
    octocat/Hello-World holds more forks than its `forkCount`, so the counts are only the probes."""
    subject = wambatic.fetch.base.Subject('repo', 'octocat', 'Hello-World')

    async def scenario() -> int:
        cache = wambatic.fetch.cache.Cache.open(tmp_path / 'cache.sqlite3')
        try:
            async with wambatic.fetch.base.Fetcher(
                TOKEN, cache, wambatic.settings.FetchSettings()
            ) as fetcher:
                await fetcher.sync(subject, frozenset({resource}))
            state = cache.sync_state(subject.full_name, resource)
            if state is not None and state.probe == wambatic.fetch.base.STARS_HIDDEN:
                # The Actions token is an installation token: GitHub lists it no stargazers.
                pytest.skip('this token cannot read stargazers (recorded as hidden)')
            rows = (
                cache.read_star_events(subject.full_name)
                if resource == 'star_events'
                else cache.read_forks(subject.full_name)
            )
            return len(rows)
        finally:
            cache.close()

    assert asyncio.run(scenario()) > 0


def repository_names(data: dict[str, object]) -> list[str]:
    owner = data['repositoryOwner']
    assert isinstance(owner, dict)
    return [node['nameWithOwner'] for node in owner['repositories']['nodes']]
