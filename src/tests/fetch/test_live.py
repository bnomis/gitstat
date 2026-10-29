import asyncio
import os

import pytest

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


def repository_names(data: dict[str, object]) -> list[str]:
    owner = data['repositoryOwner']
    assert isinstance(owner, dict)
    return [node['nameWithOwner'] for node in owner['repositories']['nodes']]
