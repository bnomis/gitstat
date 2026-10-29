"""Canned GitHub responses.

Every body here is written from the shapes in GitHub's documentation, with the page it came
from beside it. None is recorded from the live API: the sandbox this was written in cannot
reach api.github.com. Replace the OWNER_REPOSITORIES_OK and REPO stand-ins with recordings
from the live API (spec, Testing) when a session with network access is available.
"""

import datetime

import tests.fixtures.fetch.server

NOW = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)
RESET = NOW + datetime.timedelta(hours=1)
RESET_EPOCH = str(int(RESET.timestamp()))
RESET_ISO = RESET.strftime('%Y-%m-%dT%H:%M:%SZ')

Canned = tests.fixtures.fetch.server.Canned

RATE_HEADERS = {'x-ratelimit-remaining': '4990', 'x-ratelimit-reset': RESET_EPOCH}

# https://docs.github.com/en/graphql/overview/rate-limits-and-node-limits-for-the-github-graphql-api
OWNER_REPOSITORIES_OK = {
    'data': {
        'repositoryOwner': {
            'repositories': {
                'pageInfo': {'hasNextPage': False, 'endCursor': 'Y3Vyc29yOjg='},
                'nodes': [
                    {'nameWithOwner': 'octocat/Hello-World'},
                    {'nameWithOwner': 'octocat/Spoon-Knife'},
                ],
            }
        },
        'rateLimit': {'cost': 1, 'remaining': 4999, 'resetAt': RESET_ISO},
    }
}
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
