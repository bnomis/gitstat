import asyncio
import os
import pathlib

import pytest

import gitstat.fetch.base
import gitstat.fetch.cache
import gitstat.fetch.client
import gitstat.fetch.queries
import gitstat.settings

TOKEN = os.environ.get('GITHUB_TOKEN', '')


@pytest.mark.live
@pytest.mark.skipif(not TOKEN, reason='GITHUB_TOKEN is not set')
def test_lists_octocat_repositories() -> None:
    async def scenario() -> tuple[list[str], int | None]:
        async with gitstat.fetch.client.GitHubClient(
            TOKEN, gitstat.settings.FetchSettings()
        ) as client:
            data = await client.graphql(
                gitstat.fetch.queries.OWNER_REPOSITORIES, {'login': 'octocat', 'cursor': None}
            )
            return repository_names(data), client.graphql_limit.remaining

    names, remaining = asyncio.run(scenario())
    assert 'octocat/Hello-World' in names
    assert isinstance(remaining, int)


@pytest.mark.live
@pytest.mark.skipif(not TOKEN, reason='GITHUB_TOKEN is not set')
def test_line_totals_match_code_frequency(tmp_path: pathlib.Path) -> None:
    subject = gitstat.fetch.base.Subject('repo', 'octocat', 'Hello-World')

    async def scenario() -> tuple[tuple[int, int], tuple[int, int]]:
        cache = gitstat.fetch.cache.Cache.open(tmp_path / 'cache.sqlite3')
        try:
            async with gitstat.fetch.base.Fetcher(
                TOKEN, cache, gitstat.settings.FetchSettings()
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


def repository_names(data: dict[str, object]) -> list[str]:
    owner = data['repositoryOwner']
    assert isinstance(owner, dict)
    return [node['nameWithOwner'] for node in owner['repositories']['nodes']]
