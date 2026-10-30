"""Canned GitHub responses.

Every body here is written from the shapes in GitHub's documentation, with the page it came
from beside it. None is recorded from the live API: the sandbox this was written in cannot
reach api.github.com/graphql (it answers 403 to Claude Code sessions). Replace the
OWNER_REPOSITORIES_OK, REPOSITORY_OK, COMMIT_HISTORY_OK, COMPARE_AHEAD, COMMIT_NODES_OK and REPO
stand-ins with recordings from the live API (spec, Testing) when a session with network access
is available. Their commit ids are synthetic.

The step 6 stand-ins to re-record are the listing probe fields of OWNER_REPOSITORIES_OK and
REPOSITORY_OK, PULL_REQUESTS_OK and ISSUES_OK. The recording should confirm that an automatic
reviewer such as Copilot has the `Bot` type, and that GraphQL gives a bot's login without the
`[bot]` suffix.

The step 8 stand-ins to re-record are the release probe of the listing nodes, RELEASES_OK, the
labels and first commits of PULL_REQUESTS_OK, WORKFLOW_RUNS_OK and WORKFLOW_RUN_OK. Their shapes
were checked against GitHub's published schemas (`@octokit/graphql-schema` 15.26.1 and
`@octokit/openapi` 24.0.0), which describe a run's `path` in two forms (`.github/workflows/ci.yml`
and `owner/repo/.github/workflows/ci.yml@main`); the recording should confirm which one the API
gives and that `name`, `status` and `run_started_at` are present on every run.
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
    pull_requests_updated_at: datetime.datetime | None = None,
    issues_updated_at: datetime.datetime | None = None,
    releases_count: int = 0,
    releases_updated_at: datetime.datetime | None = None,
) -> dict[str, object]:
    """A repository node as `OWNER_REPOSITORIES` and `REPOSITORY` select it."""
    return {
        'nameWithOwner': name_with_owner,
        'isArchived': is_archived,
        'isFork': is_fork,
        'pushedAt': None if pushed_at is None else iso(pushed_at),
        'updatedAt': iso(updated_at),
        'defaultBranchRef': None if head is None else {'name': branch, 'target': {'oid': head}},
        'pullRequests': probe_connection(pull_requests_updated_at),
        'issues': probe_connection(issues_updated_at),
        'releases': {**probe_connection(releases_updated_at), 'totalCount': releases_count},
    }


def probe_connection(updated_at: datetime.datetime | None) -> dict[str, object]:
    """The newest-item connection a listing selects: no nodes when there is no item."""
    return {'nodes': [] if updated_at is None else [{'updatedAt': iso(updated_at)}]}


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


def actor(login: str | None, *, bot: bool = False) -> dict[str, object] | None:
    """An `Actor` as `author` selects it; GraphQL gives a bot's login without `[bot]`."""
    return None if login is None else {'__typename': 'Bot' if bot else 'User', 'login': login}


# https://docs.github.com/en/graphql/reference/objects#pullrequestreview
def review_node(
    submitted_at: datetime.datetime | None, login: str | None, *, bot: bool = False
) -> dict[str, object]:
    return {
        'submittedAt': None if submitted_at is None else iso(submitted_at),
        'author': actor(login, bot=bot),
    }


# https://docs.github.com/en/graphql/reference/objects#pullrequest
def pull_request_node(
    number: int,
    *,
    state: str = 'OPEN',
    created_at: datetime.datetime = NOW,
    updated_at: datetime.datetime = NOW,
    merged_at: datetime.datetime | None = None,
    closed_at: datetime.datetime | None = None,
    additions: int = 5,
    deletions: int = 2,
    login: str | None = 'octocat',
    bot: bool = False,
    reviews: list[dict[str, object]] | None = None,
    labels: tuple[str, ...] = (),
    first_commit_at: datetime.datetime | None = None,
) -> dict[str, object]:
    """A node of `Repository.pullRequests` as `PULL_REQUESTS` selects it."""
    return {
        'number': number,
        'state': state,
        'createdAt': iso(created_at),
        'updatedAt': iso(updated_at),
        'mergedAt': None if merged_at is None else iso(merged_at),
        'closedAt': None if closed_at is None else iso(closed_at),
        'additions': additions,
        'deletions': deletions,
        'author': actor(login, bot=bot),
        'reviews': {'nodes': reviews or []},
        # https://docs.github.com/en/graphql/reference/objects#label
        'labels': {'nodes': [{'name': name} for name in labels]},
        # https://docs.github.com/en/graphql/reference/objects#pullrequestcommit
        'commits': {
            'nodes': []
            if first_commit_at is None
            else [{'commit': {'authoredDate': iso(first_commit_at)}}]
        },
    }


# https://docs.github.com/en/graphql/reference/objects#issue
def issue_node(
    number: int,
    *,
    state: str = 'OPEN',
    created_at: datetime.datetime = NOW,
    updated_at: datetime.datetime = NOW,
    closed_at: datetime.datetime | None = None,
    login: str | None = 'octocat',
    bot: bool = False,
) -> dict[str, object]:
    """A node of `Repository.issues` as `ISSUES` selects it."""
    return {
        'number': number,
        'state': state,
        'createdAt': iso(created_at),
        'updatedAt': iso(updated_at),
        'closedAt': None if closed_at is None else iso(closed_at),
        'author': actor(login, bot=bot),
    }


# https://docs.github.com/en/graphql/reference/objects#pullrequestconnection
def pull_requests_page(
    nodes: list[dict[str, object]], has_next: bool, cursor: str
) -> dict[str, object]:
    return connection_page('pullRequests', nodes, has_next, cursor)


# https://docs.github.com/en/graphql/reference/objects#issueconnection
def issues_page(nodes: list[dict[str, object]], has_next: bool, cursor: str) -> dict[str, object]:
    return connection_page('issues', nodes, has_next, cursor)


def connection_page(
    name: str, nodes: list[dict[str, object]], has_next: bool, cursor: str
) -> dict[str, object]:
    return {
        'data': {
            'repository': {
                name: {
                    'pageInfo': {'hasNextPage': has_next, 'endCursor': cursor},
                    'nodes': nodes,
                }
            },
            'rateLimit': RATE_LIMIT,
        }
    }


# https://docs.github.com/en/graphql/reference/objects#release
def release_node(
    tag_name: str,
    *,
    created_at: datetime.datetime = NOW,
    published_at: datetime.datetime | None = NOW,
    is_draft: bool = False,
    is_prerelease: bool = False,
) -> dict[str, object]:
    """A node of `Repository.releases` as `RELEASES` selects it."""
    return {
        'tagName': tag_name,
        'createdAt': iso(created_at),
        'publishedAt': None if published_at is None else iso(published_at),
        'isDraft': is_draft,
        'isPrerelease': is_prerelease,
    }


# https://docs.github.com/en/graphql/reference/objects#releaseconnection
def releases_page(nodes: list[dict[str, object]], has_next: bool, cursor: str) -> dict[str, object]:
    return connection_page('releases', nodes, has_next, cursor)


# https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run
def workflow_run_object(
    run_id: int,
    *,
    path: str = '.github/workflows/ci.yml',
    name: str | None = 'CI',
    event: str = 'push',
    head_branch: str | None = 'main',
    status: str | None = 'completed',
    conclusion: str | None = 'success',
    created_at: datetime.datetime = NOW,
    updated_at: datetime.datetime | None = None,
    run_started_at: datetime.datetime | None = NOW,
    run_attempt: int = 1,
) -> dict[str, object]:
    """A run of the REST list, trimmed to the fields the fetcher reads."""
    return {
        'id': run_id,
        'name': name,
        'path': path,
        'event': event,
        'head_branch': head_branch,
        'status': status,
        'conclusion': conclusion,
        'created_at': iso(created_at),
        'updated_at': iso(
            created_at + datetime.timedelta(minutes=5) if updated_at is None else updated_at
        ),
        'run_started_at': None if run_started_at is None else iso(run_started_at),
        'run_attempt': run_attempt,
    }


# https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository
def workflow_runs_response(
    runs: list[dict[str, object]], total: int | None = None
) -> dict[str, object]:
    return {'total_count': len(runs) if total is None else total, 'workflow_runs': runs}


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
HELLO_PULL_REQUESTS_UPDATED_AT = datetime.datetime(2026, 10, 19, 9, 0, tzinfo=datetime.UTC)
HELLO_RELEASED_AT = datetime.datetime(2026, 10, 18, 9, 0, tzinfo=datetime.UTC)
HELLO_NODE = repo_node(
    'octocat/Hello-World',
    head=HELLO_NEW,
    pushed_at=HELLO_PUSHED_AT,
    updated_at=HELLO_UPDATED_AT,
    branch='master',
    pull_requests_updated_at=HELLO_PULL_REQUESTS_UPDATED_AT,
    issues_updated_at=HELLO_PULL_REQUESTS_UPDATED_AT,
    releases_count=4,
    releases_updated_at=HELLO_RELEASED_AT,
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
PULL_REQUESTS_OK = pull_requests_page(
    [
        pull_request_node(
            2,
            state='MERGED',
            created_at=HELLO_PULL_REQUESTS_UPDATED_AT - datetime.timedelta(days=2),
            updated_at=HELLO_PULL_REQUESTS_UPDATED_AT,
            merged_at=HELLO_PULL_REQUESTS_UPDATED_AT,
            closed_at=HELLO_PULL_REQUESTS_UPDATED_AT,
            labels=('bug', 'Hotfix'),
            first_commit_at=HELLO_PULL_REQUESTS_UPDATED_AT - datetime.timedelta(days=3),
            reviews=[
                review_node(HELLO_PULL_REQUESTS_UPDATED_AT - datetime.timedelta(days=1), 'hubot')
            ],
        ),
        pull_request_node(1, state='OPEN', login='dependabot', bot=True),
    ],
    False,
    'Y3Vyc29yOjI=',
)
ISSUES_OK = issues_page(
    [
        issue_node(
            3,
            state='CLOSED',
            updated_at=HELLO_PULL_REQUESTS_UPDATED_AT,
            closed_at=HELLO_PULL_REQUESTS_UPDATED_AT,
        ),
        issue_node(1, state='OPEN', login=None),
    ],
    False,
    'Y3Vyc29yOjI=',
)
RELEASES_OK = releases_page(
    [
        release_node('v1.1.0', created_at=HELLO_RELEASED_AT, published_at=HELLO_RELEASED_AT),
        release_node(
            'v1.1.0-rc.1',
            created_at=HELLO_RELEASED_AT - datetime.timedelta(days=3),
            published_at=HELLO_RELEASED_AT - datetime.timedelta(days=2),
            is_prerelease=True,
        ),
        release_node(
            'v1.2.0',
            created_at=HELLO_RELEASED_AT + datetime.timedelta(days=1),
            published_at=None,
            is_draft=True,
        ),
        release_node(
            'v1.0.0', created_at=HELLO_RELEASED_AT - datetime.timedelta(days=9), published_at=None
        ),
    ],
    False,
    'Y3Vyc29yOjQ=',
)
WORKFLOW_RUNS_OK = workflow_runs_response(
    [
        workflow_run_object(103, status='in_progress', conclusion=None, created_at=HELLO_PUSHED_AT),
        workflow_run_object(
            102,
            conclusion='failure',
            created_at=HELLO_PUSHED_AT - datetime.timedelta(days=1),
        ),
        workflow_run_object(
            101,
            path='.github/workflows/deploy.yml',
            name='Deploy',
            created_at=HELLO_PUSHED_AT - datetime.timedelta(days=2),
        ),
        workflow_run_object(
            100,
            status='queued',
            conclusion=None,
            created_at=HELLO_PUSHED_AT - datetime.timedelta(days=3),
            run_started_at=None,
        ),
    ]
)
WORKFLOW_RUN_OK = workflow_run_object(
    103, created_at=HELLO_PUSHED_AT, updated_at=HELLO_PUSHED_AT + datetime.timedelta(minutes=7)
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

# Hand-written stand-ins for GET /users/octocat and GET /users/github, trimmed to the two fields
# `owner_kind` reads; to be re-recorded from the live API.
# https://docs.github.com/en/rest/users/users#get-a-user
USER_OK = {'login': 'octocat', 'type': 'User'}
ORGANIZATION_OK = {'login': 'github', 'type': 'Organization'}
