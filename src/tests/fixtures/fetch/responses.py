"""Canned GitHub responses.

Every body here is written from the shapes in GitHub's documentation, with the page it came
from beside it. None is recorded from the live API: the sandbox this was written in cannot
reach api.github.com/graphql (it answers 403 to Claude Code sessions). Replace the
OWNER_REPOSITORIES_OK, REPOSITORY_OK, COMMIT_HISTORY_OK, COMPARE_AHEAD, COMMIT_NODES_OK and REPO
stand-ins with recordings from the live API (spec, Testing) when a session with network access
is available. Their commit ids are synthetic.
"""

import datetime

import tests.fixtures.fetch.server

NOW = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)
RESET = NOW + datetime.timedelta(hours=1)
RESET_EPOCH = str(int(RESET.timestamp()))
RESET_ISO = RESET.strftime('%Y-%m-%dT%H:%M:%SZ')

Canned = tests.fixtures.fetch.server.Canned

RATE_HEADERS = {'x-ratelimit-remaining': '4990', 'x-ratelimit-reset': RESET_EPOCH}


def iso(moment: datetime.datetime) -> str:
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


RATE_LIMIT = {'cost': 1, 'remaining': 4999, 'resetAt': RESET_ISO}


def repo_node(
    name_with_owner: str,
    *,
    head: str | None,
    pushed_at: datetime.datetime | None,
    updated_at: datetime.datetime,
    branch: str = 'main',
    is_fork: bool = False,
    is_archived: bool = False,
) -> dict[str, object]:
    """A repository node as `OWNER_REPOSITORIES` and `REPOSITORY` select it."""
    return {
        'nameWithOwner': name_with_owner,
        'isArchived': is_archived,
        'isFork': is_fork,
        'pushedAt': None if pushed_at is None else iso(pushed_at),
        'updatedAt': iso(updated_at),
        'defaultBranchRef': None if head is None else {'name': branch, 'target': {'oid': head}},
    }


# https://docs.github.com/en/graphql/reference/objects#repositoryconnection
def owner_page(repos: list[dict[str, object]], has_next: bool, cursor: str) -> dict[str, object]:
    return {
        'data': {
            'repositoryOwner': {
                'repositories': {
                    'pageInfo': {'hasNextPage': has_next, 'endCursor': cursor},
                    'nodes': repos,
                }
            },
            'rateLimit': RATE_LIMIT,
        }
    }


# https://docs.github.com/en/graphql/reference/queries#repository
def repository_response(node: dict[str, object] | None) -> dict[str, object]:
    return {'data': {'repository': node, 'rateLimit': RATE_LIMIT}}


def history_node(
    oid: str,
    authored_at: datetime.datetime,
    login: str | None,
    additions: int,
    deletions: int,
    parents: int = 1,
) -> dict[str, object]:
    """A node of `Commit.history` as `COMMIT_HISTORY` selects it."""
    return {
        'oid': oid,
        'authoredDate': iso(authored_at),
        'author': {'user': None if login is None else {'login': login}},
        'additions': additions,
        'deletions': deletions,
        'parents': {'totalCount': parents},
    }


# https://docs.github.com/en/graphql/reference/objects#commithistoryconnection
def history_page(
    commits: list[dict[str, object]], has_next: bool, cursor: str
) -> dict[str, object]:
    return {
        'data': {
            'repository': {
                'defaultBranchRef': {
                    'target': {
                        'history': {
                            'pageInfo': {'hasNextPage': has_next, 'endCursor': cursor},
                            'nodes': commits,
                        }
                    }
                }
            },
            'rateLimit': RATE_LIMIT,
        }
    }


# https://docs.github.com/en/graphql/reference/queries#nodes
def nodes_response(commits: list[dict[str, object] | None]) -> dict[str, object]:
    return {'data': {'nodes': commits, 'rateLimit': RATE_LIMIT}}


def compare_commit(
    sha: str, authored_at: datetime.datetime, login: str | None, parents: int = 1
) -> dict[str, object]:
    """A commit of a compare response, as the fetcher reads it."""
    return {
        'sha': sha,
        'node_id': f'C_{sha}',
        'commit': {'author': {'name': 'Mona', 'date': iso(authored_at)}},
        'author': None if login is None else {'login': login},
        'parents': [{'sha': f'{sha[:-1]}0'}] * parents,
    }


# https://docs.github.com/en/rest/commits/commits#compare-two-commits
def compare_response(
    status: str, commits: list[dict[str, object]], total: int | None = None
) -> dict[str, object]:
    return {
        'status': status,
        'ahead_by': len(commits) if status in ('ahead', 'diverged') else 0,
        'behind_by': 0,
        'total_commits': len(commits) if total is None else total,
        'commits': commits,
    }


# Synthetic stand-ins for recordings of octocat/Hello-World, which has a short history.
HELLO_OLD = 'a' * 40
HELLO_NEW = 'b' * 40
HELLO_PUSHED_AT = datetime.datetime(2026, 10, 20, 9, 0, tzinfo=datetime.UTC)
HELLO_UPDATED_AT = datetime.datetime(2026, 10, 21, 9, 0, tzinfo=datetime.UTC)
HELLO_NODE = repo_node(
    'octocat/Hello-World',
    head=HELLO_NEW,
    pushed_at=HELLO_PUSHED_AT,
    updated_at=HELLO_UPDATED_AT,
    branch='master',
)
SPOON_NODE = repo_node(
    'octocat/Spoon-Knife',
    head='c' * 40,
    pushed_at=HELLO_PUSHED_AT,
    updated_at=HELLO_UPDATED_AT,
    branch='main',
)
OWNER_REPOSITORIES_OK = owner_page([HELLO_NODE, SPOON_NODE], False, 'Y3Vyc29yOjg=')
REPOSITORY_OK = repository_response(HELLO_NODE)
COMMIT_HISTORY_OK = history_page(
    [
        history_node(HELLO_NEW, HELLO_PUSHED_AT, 'octocat', 3, 1),
        history_node(HELLO_OLD, HELLO_PUSHED_AT - datetime.timedelta(days=2), None, 5, 0),
    ],
    False,
    'Y3Vyc29yOjI=',
)
COMPARE_AHEAD = compare_response('ahead', [compare_commit(HELLO_NEW, HELLO_PUSHED_AT, 'octocat')])
COMMIT_NODES_OK = nodes_response([{'oid': HELLO_NEW, 'additions': 3, 'deletions': 1}])
GRAPHQL_NOT_FOUND = {
    'data': {
        'repositoryOwner': None,
        'rateLimit': {'cost': 1, 'remaining': 4998, 'resetAt': RESET_ISO},
    },
    'errors': [
        {
            'type': 'NOT_FOUND',
            'path': ['repositoryOwner'],
            'message': "Could not resolve to a RepositoryOwner with the login of 'nobody'.",
        }
    ],
}
GRAPHQL_REPOSITORY_NOT_FOUND = {
    'data': {'repository': None, 'rateLimit': RATE_LIMIT},
    'errors': [
        {
            'type': 'NOT_FOUND',
            'path': ['repository'],
            'message': "Could not resolve to a Repository with the name 'octocat/nope'.",
        }
    ],
}
GRAPHQL_INTERNAL = {'errors': [{'type': 'INTERNAL', 'message': 'Something went wrong'}]}
GRAPHQL_NO_RATE_LIMIT = {'data': {'repositoryOwner': {'login': 'octocat'}}}
GRAPHQL_RATE_LIMITED = {
    'errors': [{'type': 'RATE_LIMITED', 'message': 'API rate limit exceeded for user ID 1.'}]
}

# https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api
BAD_CREDENTIALS = {
    'message': 'Bad credentials',
    'documentation_url': 'https://docs.github.com/rest',
}
FORBIDDEN = {'message': 'Resource not accessible by personal access token'}
NOT_FOUND = {'message': 'Not Found', 'documentation_url': 'https://docs.github.com/rest'}
SERVER_ERROR = {'message': 'Server Error'}
UNPROCESSABLE = {'message': 'Validation Failed'}

# https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit
PRIMARY_LIMIT = {'message': 'API rate limit exceeded for user ID 1.'}
PRIMARY_LIMIT_HEADERS = {'x-ratelimit-remaining': '0', 'x-ratelimit-reset': RESET_EPOCH}
SECONDARY_LIMIT = {
    'message': (
        'You have exceeded a secondary rate limit. Please wait a few minutes before you try again.'
    )
}

# Hand-written stand-in for GET /repos/octocat/Hello-World
# https://docs.github.com/en/rest/repos/repos#get-a-repository
REPO = {'id': 1296269, 'full_name': 'octocat/Hello-World', 'default_branch': 'master'}
REPO_ETAG = '"670f8b5e6ec1ff7a0e8f1d4d2e1ab2c4"'

# https://docs.github.com/en/rest/metrics/statistics#a-word-about-caching
STATS_PENDING = Canned(202)
