"""Successful GitHub responses recorded from the live API on 2026-10-31.

Written by bin/record-fixtures.sh; do not edit by hand, re-run it. The subjects are
octocat (the listing), octocat/Hello-World (repository, history,
compare, commit nodes, REST repo), miguelangellv/ha-gas-station-spain (pull requests, issues,
releases, workflow runs), bnomis/ab2cb (stargazers, forks), the users
octocat and github, and one review page of
microsoft/vscode#345267 (BOT_REVIEWS_OK). REST bodies
are trimmed to the fields the fetcher reads.
"""

# ruff: noqa: E501

RECORDED_AT = '2026-10-31T08:48:12Z'
WAMBATIC_VERSION = '0.1.0'
# sha256 of each wambatic.fetch.queries text the recording was made with
QUERY_SHA256 = {
    'COMMIT_HISTORY': 'e390724dbc61a80de490efc8274d16854c3abef5819a7986b68d56ab1f120343',
    'COMMIT_NODES': 'd76d136f6271d0589251490b8770f0ecf8a165ba80afc0614967bfa7e02b331b',
    'ISSUES': '87fb57221f946898f3c0af75d81b9f185cf21bed79b29bb7de6aae89030e3ac6',
    'OWNER_REPOSITORIES': '22b8714cf7d24254eddebf0abdf4fc0149ffeca75e182b7447c4a8b046f406bd',
    'PULL_REQUESTS': '62deaf3e0eb3a441fb6045ac15ec73c73ef3c0963a10f0b396a70e8f33b4fe40',
    'RELEASES': '1cca9af9dde6afb968139e2986222a6851a9740ca525a3b539f7afdde7bbde1d',
    'REPOSITORY': '22a88d7159c26245cf9668499732da631c4f471a943f1413393bac4a651ed7fa',
    'STARGAZERS': 'f633a1b189dd56d4d825e2291c85d14c3a35c03b35282d35fcaa5d3779ba3f94',
}

OWNER_REPOSITORIES_OK = {
    'data': {
        'repositoryOwner': {
            'repositories': {
                'pageInfo': {
                    'hasNextPage': False,
                    'endCursor': 'Y3Vyc29yOnYyOpK0MjAyNC0wMy0wN1QxMTozNzoyN1rOA1qhPA==',
                },
                'nodes': [
                    {
                        'nameWithOwner': 'octocat/Spoon-Knife',
                        'isArchived': False,
                        'isFork': False,
                        'pushedAt': '2024-08-21T15:25:42Z',
                        'updatedAt': '2026-10-31T04:01:27Z',
                        'defaultBranchRef': {
                            'name': 'main',
                            'target': {'oid': 'd0dd1f61b33d64e29d8bc1372a94ef6a2fee76a9'},
                        },
                        'pullRequests': {'nodes': [{'updatedAt': '2026-10-31T08:30:40Z'}]},
                        'issues': {'nodes': [{'updatedAt': '2026-10-30T03:20:20Z'}]},
                        'releases': {'totalCount': 0, 'nodes': []},
                        'stargazerCount': 14148,
                        'forkCount': 160746,
                        'watchers': {'totalCount': 910},
                        'languages': {
                            'totalSize': 611,
                            'edges': [
                                {'size': 355, 'node': {'name': 'HTML'}},
                                {'size': 256, 'node': {'name': 'CSS'}},
                            ],
                        },
                    },
                    {
                        'nameWithOwner': 'octocat/Hello-World',
                        'isArchived': False,
                        'isFork': False,
                        'pushedAt': '2024-08-20T23:54:42Z',
                        'updatedAt': '2026-10-31T07:48:54Z',
                        'defaultBranchRef': {
                            'name': 'master',
                            'target': {'oid': '7fd1a60b01f91b314f59955a4e4d4e80d8edf11d'},
                        },
                        'pullRequests': {'nodes': [{'updatedAt': '2026-10-31T08:27:15Z'}]},
                        'issues': {'nodes': [{'updatedAt': '2026-10-30T20:11:28Z'}]},
                        'releases': {'totalCount': 0, 'nodes': []},
                        'stargazerCount': 3879,
                        'forkCount': 7311,
                        'watchers': {'totalCount': 1735},
                        'languages': {'totalSize': 0, 'edges': []},
                    },
                    {
                        'nameWithOwner': 'octocat/linguist',
                        'isArchived': False,
                        'isFork': True,
                        'pushedAt': '2024-08-14T07:35:16Z',
                        'updatedAt': '2026-10-30T21:37:09Z',
                        'defaultBranchRef': {
                            'name': 'master',
                            'target': {'oid': '64a44011ca0ee0693b1c1767c96d1fba25d5be7d'},
                        },
                        'pullRequests': {'nodes': [{'updatedAt': '2026-10-26T05:58:44Z'}]},
                        'issues': {'nodes': []},
                        'releases': {'totalCount': 0, 'nodes': []},
                        'stargazerCount': 774,
                        'forkCount': 288,
                        'watchers': {'totalCount': 68},
                        'languages': {
                            'totalSize': 205775,
                            'edges': [
                                {'size': 204865, 'node': {'name': 'Ruby'}},
                                {'size': 910, 'node': {'name': 'Shell'}},
                            ],
                        },
                    },
                    {
                        'nameWithOwner': 'octocat/octocat.github.io',
                        'isArchived': False,
                        'isFork': False,
                        'pushedAt': '2024-08-11T11:57:01Z',
                        'updatedAt': '2026-10-30T21:37:08Z',
                        'defaultBranchRef': {
                            'name': 'master',
                            'target': {'oid': '3a9796cf19902af0f7e677391b340f1ae4128433'},
                        },
                        'pullRequests': {'nodes': [{'updatedAt': '2026-10-30T12:48:46Z'}]},
                        'issues': {'nodes': [{'updatedAt': '2026-10-27T06:01:24Z'}]},
                        'releases': {'totalCount': 0, 'nodes': []},
                        'stargazerCount': 1192,
                        'forkCount': 597,
                        'watchers': {'totalCount': 118},
                        'languages': {
                            'totalSize': 18725,
                            'edges': [
                                {'size': 14694, 'node': {'name': 'CSS'}},
                                {'size': 3983, 'node': {'name': 'HTML'}},
                                {'size': 48, 'node': {'name': 'JavaScript'}},
                            ],
                        },
                    },
                    {
                        'nameWithOwner': 'octocat/git-consortium',
                        'isArchived': False,
                        'isFork': False,
                        'pushedAt': '2024-07-12T15:04:33Z',
                        'updatedAt': '2026-10-30T21:34:54Z',
                        'defaultBranchRef': {
                            'name': 'master',
                            'target': {'oid': 'b33a9c7c02ad93f621fa38f0e9fc9e867e12fa0e'},
                        },
                        'pullRequests': {'nodes': [{'updatedAt': '2026-10-25T08:51:25Z'}]},
                        'issues': {'nodes': [{'updatedAt': '2026-10-09T12:37:49Z'}]},
                        'releases': {'totalCount': 0, 'nodes': []},
                        'stargazerCount': 621,
                        'forkCount': 201,
                        'watchers': {'totalCount': 42},
                        'languages': {'totalSize': 0, 'edges': []},
                    },
                    {
                        'nameWithOwner': 'octocat/boysenberry-repo-1',
                        'isArchived': False,
                        'isFork': True,
                        'pushedAt': '2024-05-26T07:02:05Z',
                        'updatedAt': '2026-10-30T21:37:10Z',
                        'defaultBranchRef': {
                            'name': 'master',
                            'target': {'oid': 'd09e445076bbcd163fc9abfbe6d2fce09a611281'},
                        },
                        'pullRequests': {'nodes': [{'updatedAt': '2026-09-28T17:33:11Z'}]},
                        'issues': {'nodes': []},
                        'releases': {'totalCount': 0, 'nodes': []},
                        'stargazerCount': 486,
                        'forkCount': 28,
                        'watchers': {'totalCount': 18},
                        'languages': {'totalSize': 0, 'edges': []},
                    },
                    {
                        'nameWithOwner': 'octocat/hello-worId',
                        'isArchived': False,
                        'isFork': False,
                        'pushedAt': '2024-05-06T10:29:56Z',
                        'updatedAt': '2026-10-30T21:50:31Z',
                        'defaultBranchRef': {
                            'name': 'master',
                            'target': {'oid': '7e068727fdb347b685b658d2981f8c85f7bf0585'},
                        },
                        'pullRequests': {'nodes': [{'updatedAt': '2026-10-11T16:38:14Z'}]},
                        'issues': {'nodes': [{'updatedAt': '2026-09-26T06:13:37Z'}]},
                        'releases': {'totalCount': 0, 'nodes': []},
                        'stargazerCount': 827,
                        'forkCount': 308,
                        'watchers': {'totalCount': 83},
                        'languages': {'totalSize': 0, 'edges': []},
                    },
                    {
                        'nameWithOwner': 'octocat/test-repo1',
                        'isArchived': False,
                        'isFork': False,
                        'pushedAt': '2024-03-07T11:37:27Z',
                        'updatedAt': '2026-10-30T16:21:48Z',
                        'defaultBranchRef': {
                            'name': 'gh-pages',
                            'target': {'oid': '57523742631876181d95bc268e09fb3fd1a4d85e'},
                        },
                        'pullRequests': {'nodes': [{'updatedAt': '2026-10-21T15:41:36Z'}]},
                        'issues': {'nodes': []},
                        'releases': {
                            'totalCount': 1,
                            'nodes': [{'updatedAt': '2018-08-10T17:09:48Z'}],
                        },
                        'stargazerCount': 497,
                        'forkCount': 53,
                        'watchers': {'totalCount': 11},
                        'languages': {'totalSize': 0, 'edges': []},
                    },
                ],
            }
        },
        'rateLimit': {'cost': 4, 'remaining': 4760, 'resetAt': '2026-10-31T09:13:32Z'},
    }
}

REPOSITORY_OK = {
    'data': {
        'repository': {
            'nameWithOwner': 'octocat/Hello-World',
            'isArchived': False,
            'isFork': False,
            'pushedAt': '2024-08-20T23:54:42Z',
            'updatedAt': '2026-10-31T07:48:54Z',
            'defaultBranchRef': {
                'name': 'master',
                'target': {'oid': '7fd1a60b01f91b314f59955a4e4d4e80d8edf11d'},
            },
            'pullRequests': {'nodes': [{'updatedAt': '2026-10-31T08:27:15Z'}]},
            'issues': {'nodes': [{'updatedAt': '2026-10-30T20:11:28Z'}]},
            'releases': {'totalCount': 0, 'nodes': []},
            'stargazerCount': 3879,
            'forkCount': 7311,
            'watchers': {'totalCount': 1735},
            'languages': {'totalSize': 0, 'edges': []},
        },
        'rateLimit': {'cost': 1, 'remaining': 4930, 'resetAt': '2026-10-31T09:13:32Z'},
    }
}

COMMIT_HISTORY_OK = {
    'data': {
        'repository': {
            'defaultBranchRef': {
                'target': {
                    'history': {
                        'pageInfo': {
                            'hasNextPage': False,
                            'endCursor': '7fd1a60b01f91b314f59955a4e4d4e80d8edf11d 2',
                        },
                        'nodes': [
                            {
                                'oid': '7fd1a60b01f91b314f59955a4e4d4e80d8edf11d',
                                'authoredDate': '2012-03-06T23:06:50Z',
                                'author': {'user': {'login': 'octocat'}},
                                'additions': 1,
                                'deletions': 1,
                                'parents': {'totalCount': 2},
                            },
                            {
                                'oid': '762941318ee16e59dabbacb1b4049eec22f0d303',
                                'authoredDate': '2011-09-14T04:42:41Z',
                                'author': {'user': {'login': 'Spaceghost'}},
                                'additions': 1,
                                'deletions': 1,
                                'parents': {'totalCount': 1},
                            },
                            {
                                'oid': '553c2077f0edc3d5dc5d17262f6aa498e69d6f8e',
                                'authoredDate': '2011-01-26T19:06:08Z',
                                'author': {'user': {'login': 'Cameron423698'}},
                                'additions': 1,
                                'deletions': 0,
                                'parents': {'totalCount': 0},
                            },
                        ],
                    }
                }
            }
        },
        'rateLimit': {'cost': 1, 'remaining': 4931, 'resetAt': '2026-10-31T09:13:32Z'},
    }
}

COMPARE_AHEAD = {
    'status': 'ahead',
    'ahead_by': 2,
    'behind_by': 0,
    'total_commits': 2,
    'commits': [
        {
            'sha': '762941318ee16e59dabbacb1b4049eec22f0d303',
            'node_id': 'MDY6Q29tbWl0MTI5NjI2OTo3NjI5NDEzMThlZTE2ZTU5ZGFiYmFjYjFiNDA0OWVlYzIyZjBkMzAz',
            'commit': {'author': {'date': '2011-09-14T04:42:41Z'}},
            'author': {'login': 'Spaceghost'},
            'parents': [{'sha': '553c2077f0edc3d5dc5d17262f6aa498e69d6f8e'}],
        },
        {
            'sha': '7fd1a60b01f91b314f59955a4e4d4e80d8edf11d',
            'node_id': 'MDY6Q29tbWl0MTI5NjI2OTo3ZmQxYTYwYjAxZjkxYjMxNGY1OTk1NWE0ZTRkNGU4MGQ4ZWRmMTFk',
            'commit': {'author': {'date': '2012-03-06T23:06:50Z'}},
            'author': {'login': 'octocat'},
            'parents': [
                {'sha': '553c2077f0edc3d5dc5d17262f6aa498e69d6f8e'},
                {'sha': '762941318ee16e59dabbacb1b4049eec22f0d303'},
            ],
        },
    ],
}

COMMIT_NODES_OK = {
    'data': {
        'nodes': [
            {'oid': '762941318ee16e59dabbacb1b4049eec22f0d303', 'additions': 1, 'deletions': 1},
            {'oid': '7fd1a60b01f91b314f59955a4e4d4e80d8edf11d', 'additions': 1, 'deletions': 1},
        ],
        'rateLimit': {'cost': 1, 'remaining': 4759, 'resetAt': '2026-10-31T09:13:32Z'},
    },
    'extensions': {
        'warnings': [
            {
                'type': 'DEPRECATION',
                'message': 'The id '
                'MDY6Q29tbWl0MTI5NjI2OTo3NjI5NDEzMThlZTE2ZTU5ZGFiYmFjYjFiNDA0OWVlYzIyZjBkMzAz '
                'is deprecated. Update your cache to use the '
                'next_global_id from the data payload.',
                'data': {
                    'legacy_global_id': 'MDY6Q29tbWl0MTI5NjI2OTo3NjI5NDEzMThlZTE2ZTU5ZGFiYmFjYjFiNDA0OWVlYzIyZjBkMzAz',
                    'next_global_id': 'C_kwDOABPHjdoAKDc2Mjk0MTMxOGVlMTZlNTlkYWJiYWNiMWI0MDQ5ZWVjMjJmMGQzMDM',
                },
                'link': 'https://docs.github.com',
            },
            {
                'type': 'DEPRECATION',
                'message': 'The id '
                'MDY6Q29tbWl0MTI5NjI2OTo3ZmQxYTYwYjAxZjkxYjMxNGY1OTk1NWE0ZTRkNGU4MGQ4ZWRmMTFk '
                'is deprecated. Update your cache to use the '
                'next_global_id from the data payload.',
                'data': {
                    'legacy_global_id': 'MDY6Q29tbWl0MTI5NjI2OTo3ZmQxYTYwYjAxZjkxYjMxNGY1OTk1NWE0ZTRkNGU4MGQ4ZWRmMTFk',
                    'next_global_id': 'C_kwDOABPHjdoAKDdmZDFhNjBiMDFmOTFiMzE0ZjU5OTU1YTRlNGQ0ZTgwZDhlZGYxMWQ',
                },
                'link': 'https://docs.github.com',
            },
        ]
    },
}

REPO = {'id': 1296269, 'full_name': 'octocat/Hello-World', 'default_branch': 'master'}

REPO_ETAG = '"81d27e64fd51178f939244d9a69538c9abfe45761826af80bf5e7f8808c8c5f0"'

USER_OK = {'login': 'octocat', 'type': 'User'}

ORGANIZATION_OK = {'login': 'github', 'type': 'Organization'}

PULL_REQUESTS_OK = {
    'data': {
        'repository': {
            'pullRequests': {
                'pageInfo': {
                    'hasNextPage': False,
                    'endCursor': 'Y3Vyc29yOnYyOpK0MjAyNC0wMS0wNVQyMDozMzo1MVrOY1hunQ==',
                },
                'nodes': [
                    {
                        'number': 57,
                        'state': 'MERGED',
                        'createdAt': '2026-10-20T15:05:02Z',
                        'updatedAt': '2026-10-20T16:01:49Z',
                        'mergedAt': '2026-10-20T16:01:49Z',
                        'closedAt': '2026-10-20T16:01:49Z',
                        'additions': 0,
                        'deletions': 0,
                        'author': {'__typename': 'User', 'login': 'frenck'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-10-20T15:04:53Z'}}]
                        },
                    },
                    {
                        'number': 54,
                        'state': 'MERGED',
                        'createdAt': '2026-04-04T18:29:10Z',
                        'updatedAt': '2026-04-04T18:30:30Z',
                        'mergedAt': '2026-04-04T18:30:30Z',
                        'closedAt': '2026-04-04T18:30:30Z',
                        'additions': 8,
                        'deletions': 4,
                        'author': {'__typename': 'Bot', 'login': 'github-actions'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': [{'name': 'release'}]},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-04-04T18:29:09Z'}}]
                        },
                    },
                    {
                        'number': 39,
                        'state': 'MERGED',
                        'createdAt': '2025-10-31T07:06:38Z',
                        'updatedAt': '2026-04-04T18:28:46Z',
                        'mergedAt': '2025-10-31T07:07:57Z',
                        'closedAt': '2025-10-31T07:07:57Z',
                        'additions': 977,
                        'deletions': 737,
                        'author': {'__typename': 'User', 'login': 'miguelangellv'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2025-10-31T06:31:37Z'}}]
                        },
                    },
                    {
                        'number': 53,
                        'state': 'MERGED',
                        'createdAt': '2026-04-04T18:24:16Z',
                        'updatedAt': '2026-04-04T18:25:40Z',
                        'mergedAt': '2026-04-04T18:25:39Z',
                        'closedAt': '2026-04-04T18:25:39Z',
                        'additions': 29,
                        'deletions': 36,
                        'author': {'__typename': 'User', 'login': 'miguelangellv'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-04-04T18:12:05Z'}}]
                        },
                    },
                    {
                        'number': 51,
                        'state': 'MERGED',
                        'createdAt': '2026-04-04T17:58:48Z',
                        'updatedAt': '2026-04-04T18:12:58Z',
                        'mergedAt': '2026-04-04T18:12:28Z',
                        'closedAt': '2026-04-04T18:12:28Z',
                        'additions': 362,
                        'deletions': 16,
                        'author': {'__typename': 'User', 'login': 'miguelangellv'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-04-04T17:58:30Z'}}]
                        },
                    },
                    {
                        'number': 52,
                        'state': 'MERGED',
                        'createdAt': '2026-04-04T18:12:14Z',
                        'updatedAt': '2026-04-04T18:12:45Z',
                        'mergedAt': '2026-04-04T18:12:40Z',
                        'closedAt': '2026-04-04T18:12:40Z',
                        'additions': 603,
                        'deletions': 0,
                        'author': {'__typename': 'User', 'login': 'miguelangellv'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-04-04T18:12:05Z'}}]
                        },
                    },
                    {
                        'number': 50,
                        'state': 'MERGED',
                        'createdAt': '2026-04-02T14:00:08Z',
                        'updatedAt': '2026-04-02T15:49:25Z',
                        'mergedAt': '2026-04-02T15:49:19Z',
                        'closedAt': '2026-04-02T15:49:19Z',
                        'additions': 3179,
                        'deletions': 168,
                        'author': {'__typename': 'User', 'login': 'miguelangellv'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-04-02T13:47:30Z'}}]
                        },
                    },
                    {
                        'number': 47,
                        'state': 'MERGED',
                        'createdAt': '2026-02-28T14:54:25Z',
                        'updatedAt': '2026-02-28T14:55:45Z',
                        'mergedAt': '2026-02-28T14:55:45Z',
                        'closedAt': '2026-02-28T14:55:45Z',
                        'additions': 1,
                        'deletions': 1,
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-02-28T14:53:49Z'}}]
                        },
                    },
                    {
                        'number': 46,
                        'state': 'MERGED',
                        'createdAt': '2026-02-24T21:06:20Z',
                        'updatedAt': '2026-02-28T14:15:03Z',
                        'mergedAt': '2026-02-28T14:15:03Z',
                        'closedAt': '2026-02-28T14:15:03Z',
                        'additions': 5,
                        'deletions': 6,
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-02-24T21:06:07Z'}}]
                        },
                    },
                    {
                        'number': 44,
                        'state': 'CLOSED',
                        'createdAt': '2026-01-16T22:35:16Z',
                        'updatedAt': '2026-02-25T18:10:52Z',
                        'mergedAt': None,
                        'closedAt': '2026-02-24T21:11:43Z',
                        'additions': 93,
                        'deletions': 69,
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                        'reviews': {
                            'nodes': [
                                {
                                    'submittedAt': '2026-02-24T19:26:28Z',
                                    'author': {
                                        '__typename': 'Bot',
                                        'login': 'copilot-pull-request-reviewer',
                                    },
                                }
                            ]
                        },
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-01-16T22:35:02Z'}}]
                        },
                    },
                    {
                        'number': 45,
                        'state': 'CLOSED',
                        'createdAt': '2026-02-24T19:34:07Z',
                        'updatedAt': '2026-02-24T21:11:33Z',
                        'mergedAt': None,
                        'closedAt': '2026-02-24T21:11:33Z',
                        'additions': 42,
                        'deletions': 17,
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                        'reviews': {
                            'nodes': [
                                {
                                    'submittedAt': '2026-02-24T19:48:22Z',
                                    'author': {'__typename': 'User', 'login': 'sheaur'},
                                }
                            ]
                        },
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-02-24T19:33:38Z'}}]
                        },
                    },
                    {
                        'number': 43,
                        'state': 'CLOSED',
                        'createdAt': '2026-01-16T22:27:11Z',
                        'updatedAt': '2026-01-16T22:34:07Z',
                        'mergedAt': None,
                        'closedAt': '2026-01-16T22:34:07Z',
                        'additions': 7,
                        'deletions': 9,
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-01-16T22:26:58Z'}}]
                        },
                    },
                    {
                        'number': 42,
                        'state': 'CLOSED',
                        'createdAt': '2026-01-16T20:25:56Z',
                        'updatedAt': '2026-01-16T22:25:09Z',
                        'mergedAt': None,
                        'closedAt': '2026-01-16T22:25:09Z',
                        'additions': 31,
                        'deletions': 14,
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                        'reviews': {
                            'nodes': [
                                {
                                    'submittedAt': '2026-01-16T21:50:18Z',
                                    'author': {'__typename': 'User', 'login': 'sheaur'},
                                }
                            ]
                        },
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-01-16T20:25:22Z'}}]
                        },
                    },
                    {
                        'number': 41,
                        'state': 'CLOSED',
                        'createdAt': '2026-01-15T17:34:22Z',
                        'updatedAt': '2026-01-16T11:16:48Z',
                        'mergedAt': None,
                        'closedAt': '2026-01-16T11:16:48Z',
                        'additions': 87,
                        'deletions': 59,
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                        'reviews': {
                            'nodes': [
                                {
                                    'submittedAt': '2026-01-15T17:53:28Z',
                                    'author': {'__typename': 'User', 'login': 'sheaur'},
                                },
                                {
                                    'submittedAt': '2026-01-15T17:57:15Z',
                                    'author': {'__typename': 'User', 'login': 'sheaur'},
                                },
                                {
                                    'submittedAt': '2026-01-15T18:04:32Z',
                                    'author': {'__typename': 'User', 'login': 'sheaur'},
                                },
                                {
                                    'submittedAt': '2026-01-15T18:11:59Z',
                                    'author': {'__typename': 'User', 'login': 'sheaur'},
                                },
                                {
                                    'submittedAt': '2026-01-15T18:16:41Z',
                                    'author': {'__typename': 'User', 'login': 'sheaur'},
                                },
                            ]
                        },
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2026-01-15T17:33:58Z'}}]
                        },
                    },
                    {
                        'number': 28,
                        'state': 'MERGED',
                        'createdAt': '2025-03-17T11:28:18Z',
                        'updatedAt': '2025-03-17T14:47:53Z',
                        'mergedAt': '2025-03-17T14:47:42Z',
                        'closedAt': '2025-03-17T14:47:42Z',
                        'additions': 2421,
                        'deletions': 283,
                        'author': {'__typename': 'User', 'login': 'miguelangellv'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2025-03-16T21:39:49Z'}}]
                        },
                    },
                    {
                        'number': 27,
                        'state': 'MERGED',
                        'createdAt': '2025-03-16T21:40:37Z',
                        'updatedAt': '2025-03-16T22:05:50Z',
                        'mergedAt': '2025-03-16T22:05:45Z',
                        'closedAt': '2025-03-16T22:05:45Z',
                        'additions': 2513,
                        'deletions': 379,
                        'author': {'__typename': 'User', 'login': 'miguelangellv'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2025-03-16T21:39:49Z'}}]
                        },
                    },
                    {
                        'number': 22,
                        'state': 'MERGED',
                        'createdAt': '2025-01-04T16:48:27Z',
                        'updatedAt': '2025-01-22T14:35:36Z',
                        'mergedAt': '2025-01-22T14:34:49Z',
                        'closedAt': '2025-01-22T14:34:49Z',
                        'additions': 1,
                        'deletions': 1,
                        'author': {'__typename': 'User', 'login': 'JoseRMorales'},
                        'reviews': {
                            'nodes': [
                                {
                                    'submittedAt': '2025-01-22T14:17:44Z',
                                    'author': {'__typename': 'User', 'login': 'polamoros'},
                                }
                            ]
                        },
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2025-01-04T16:27:34Z'}}]
                        },
                    },
                    {
                        'number': 14,
                        'state': 'MERGED',
                        'createdAt': '2024-05-09T23:29:07Z',
                        'updatedAt': '2024-12-19T20:03:24Z',
                        'mergedAt': '2024-12-19T20:03:23Z',
                        'closedAt': '2024-12-19T20:03:23Z',
                        'additions': 5,
                        'deletions': 5,
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2024-05-09T01:40:54Z'}}]
                        },
                    },
                    {
                        'number': 15,
                        'state': 'CLOSED',
                        'createdAt': '2024-05-10T00:59:15Z',
                        'updatedAt': '2024-12-19T20:03:12Z',
                        'mergedAt': None,
                        'closedAt': '2024-12-19T20:03:12Z',
                        'additions': 2,
                        'deletions': 2,
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2024-05-10T00:58:13Z'}}]
                        },
                    },
                    {
                        'number': 10,
                        'state': 'MERGED',
                        'createdAt': '2024-01-10T10:58:02Z',
                        'updatedAt': '2024-01-10T11:00:01Z',
                        'mergedAt': '2024-01-10T10:59:54Z',
                        'closedAt': '2024-01-10T10:59:54Z',
                        'additions': 53,
                        'deletions': 0,
                        'author': {'__typename': 'User', 'login': 'ViPeR5000'},
                        'reviews': {'nodes': []},
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2024-01-10T10:57:57Z'}}]
                        },
                    },
                    {
                        'number': 8,
                        'state': 'MERGED',
                        'createdAt': '2024-01-05T20:01:07Z',
                        'updatedAt': '2024-01-05T20:33:51Z',
                        'mergedAt': '2024-01-05T20:33:50Z',
                        'closedAt': '2024-01-05T20:33:50Z',
                        'additions': 1,
                        'deletions': 1,
                        'author': {'__typename': 'User', 'login': 'JNP2020'},
                        'reviews': {
                            'nodes': [
                                {
                                    'submittedAt': '2024-01-05T20:33:42Z',
                                    'author': {'__typename': 'User', 'login': 'miguelangellv'},
                                }
                            ]
                        },
                        'labels': {'nodes': []},
                        'commits': {
                            'nodes': [{'commit': {'authoredDate': '2024-01-05T20:00:09Z'}}]
                        },
                    },
                ],
            }
        },
        'rateLimit': {'cost': 3, 'remaining': 4756, 'resetAt': '2026-10-31T09:13:32Z'},
    }
}

ISSUES_OK = {
    'data': {
        'repository': {
            'issues': {
                'pageInfo': {
                    'hasNextPage': False,
                    'endCursor': 'Y3Vyc29yOnYyOpK0MjAyMy0xMC0wOVQxMToxNTo0M1rOczB6Jw==',
                },
                'nodes': [
                    {
                        'number': 56,
                        'state': 'OPEN',
                        'createdAt': '2026-08-18T10:26:03Z',
                        'updatedAt': '2026-08-18T11:06:20Z',
                        'closedAt': None,
                        'author': {'__typename': 'User', 'login': 'githchema'},
                    },
                    {
                        'number': 48,
                        'state': 'CLOSED',
                        'createdAt': '2026-03-12T22:19:42Z',
                        'updatedAt': '2026-04-16T11:02:50Z',
                        'closedAt': '2026-04-16T11:02:50Z',
                        'author': {'__typename': 'User', 'login': 'JAIMEHVLOFT'},
                    },
                    {
                        'number': 55,
                        'state': 'CLOSED',
                        'createdAt': '2026-04-15T04:54:00Z',
                        'updatedAt': '2026-04-16T11:02:23Z',
                        'closedAt': '2026-04-16T11:02:23Z',
                        'author': {'__typename': 'User', 'login': 'franito16'},
                    },
                    {
                        'number': 49,
                        'state': 'CLOSED',
                        'createdAt': '2026-03-21T09:45:20Z',
                        'updatedAt': '2026-04-02T09:39:07Z',
                        'closedAt': '2026-04-02T09:39:07Z',
                        'author': {'__typename': 'User', 'login': 'GeiserX'},
                    },
                    {
                        'number': 40,
                        'state': 'CLOSED',
                        'createdAt': '2026-01-12T14:36:58Z',
                        'updatedAt': '2026-02-28T14:41:09Z',
                        'closedAt': '2026-02-28T14:41:09Z',
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                    },
                    {
                        'number': 36,
                        'state': 'CLOSED',
                        'createdAt': '2025-08-29T08:56:17Z',
                        'updatedAt': '2025-11-16T17:52:41Z',
                        'closedAt': '2025-10-31T07:09:24Z',
                        'author': {'__typename': 'User', 'login': 'ibratos'},
                    },
                    {
                        'number': 9,
                        'state': 'OPEN',
                        'createdAt': '2024-01-06T03:31:58Z',
                        'updatedAt': '2025-11-13T13:51:08Z',
                        'closedAt': None,
                        'author': {'__typename': 'User', 'login': 'cnecrea'},
                    },
                    {
                        'number': 35,
                        'state': 'CLOSED',
                        'createdAt': '2025-07-22T10:59:04Z',
                        'updatedAt': '2025-11-04T08:37:41Z',
                        'closedAt': '2025-11-04T08:37:41Z',
                        'author': {'__typename': 'User', 'login': 'buckiebass'},
                    },
                    {
                        'number': 37,
                        'state': 'CLOSED',
                        'createdAt': '2025-09-04T09:09:56Z',
                        'updatedAt': '2025-10-31T07:09:54Z',
                        'closedAt': '2025-10-31T07:09:54Z',
                        'author': {'__typename': 'User', 'login': 'marioJR1979'},
                    },
                    {
                        'number': 38,
                        'state': 'CLOSED',
                        'createdAt': '2025-10-29T16:11:17Z',
                        'updatedAt': '2025-10-31T07:09:34Z',
                        'closedAt': '2025-10-31T07:09:34Z',
                        'author': {'__typename': 'User', 'login': 'DelBierzo'},
                    },
                    {
                        'number': 33,
                        'state': 'CLOSED',
                        'createdAt': '2025-07-07T22:31:37Z',
                        'updatedAt': '2025-07-15T06:00:47Z',
                        'closedAt': '2025-07-15T06:00:47Z',
                        'author': {'__typename': 'User', 'login': 'ggonmar'},
                    },
                    {
                        'number': 34,
                        'state': 'CLOSED',
                        'createdAt': '2025-07-15T05:57:47Z',
                        'updatedAt': '2025-07-15T05:59:48Z',
                        'closedAt': '2025-07-15T05:59:48Z',
                        'author': {'__typename': 'User', 'login': 'jflorido94'},
                    },
                    {
                        'number': 32,
                        'state': 'CLOSED',
                        'createdAt': '2025-06-09T17:18:11Z',
                        'updatedAt': '2025-06-18T05:47:15Z',
                        'closedAt': '2025-06-18T05:47:15Z',
                        'author': {'__typename': 'User', 'login': 'davidpassola'},
                    },
                    {
                        'number': 31,
                        'state': 'CLOSED',
                        'createdAt': '2025-05-22T07:08:18Z',
                        'updatedAt': '2025-05-22T09:12:23Z',
                        'closedAt': '2025-05-22T07:10:22Z',
                        'author': {'__typename': 'User', 'login': 'Drums7'},
                    },
                    {
                        'number': 30,
                        'state': 'CLOSED',
                        'createdAt': '2025-04-29T07:32:51Z',
                        'updatedAt': '2025-04-29T07:36:08Z',
                        'closedAt': '2025-04-29T07:36:07Z',
                        'author': {'__typename': 'User', 'login': 'acopen'},
                    },
                    {
                        'number': 29,
                        'state': 'CLOSED',
                        'createdAt': '2025-03-21T13:46:30Z',
                        'updatedAt': '2025-03-25T21:13:19Z',
                        'closedAt': '2025-03-25T21:13:18Z',
                        'author': {'__typename': 'User', 'login': 'ldsmovil'},
                    },
                    {
                        'number': 24,
                        'state': 'CLOSED',
                        'createdAt': '2025-02-21T07:42:24Z',
                        'updatedAt': '2025-03-17T22:53:53Z',
                        'closedAt': '2025-03-17T14:49:20Z',
                        'author': {'__typename': 'User', 'login': 'Phrana'},
                    },
                    {
                        'number': 26,
                        'state': 'CLOSED',
                        'createdAt': '2025-03-12T12:49:38Z',
                        'updatedAt': '2025-03-17T22:46:38Z',
                        'closedAt': '2025-03-17T14:48:56Z',
                        'author': {'__typename': 'User', 'login': 'marioJR1979'},
                    },
                    {
                        'number': 23,
                        'state': 'CLOSED',
                        'createdAt': '2025-02-11T10:23:44Z',
                        'updatedAt': '2025-03-17T15:00:25Z',
                        'closedAt': '2025-03-17T15:00:24Z',
                        'author': {'__typename': 'User', 'login': 'reagnon'},
                    },
                    {
                        'number': 20,
                        'state': 'CLOSED',
                        'createdAt': '2025-01-02T08:32:43Z',
                        'updatedAt': '2025-03-17T14:51:24Z',
                        'closedAt': '2025-03-17T14:51:23Z',
                        'author': {'__typename': 'User', 'login': 'ramonLoureiro'},
                    },
                    {
                        'number': 21,
                        'state': 'CLOSED',
                        'createdAt': '2025-01-02T08:37:43Z',
                        'updatedAt': '2025-03-17T14:50:26Z',
                        'closedAt': '2025-03-17T14:50:25Z',
                        'author': {'__typename': 'User', 'login': 'ramonLoureiro'},
                    },
                    {
                        'number': 25,
                        'state': 'CLOSED',
                        'createdAt': '2025-02-25T18:54:24Z',
                        'updatedAt': '2025-03-17T14:49:09Z',
                        'closedAt': '2025-03-17T14:49:09Z',
                        'author': {'__typename': 'User', 'login': 'kitopopo'},
                    },
                    {
                        'number': 19,
                        'state': 'CLOSED',
                        'createdAt': '2025-01-01T18:55:38Z',
                        'updatedAt': '2025-01-14T17:02:50Z',
                        'closedAt': '2025-01-14T17:02:50Z',
                        'author': {'__typename': 'User', 'login': 'ivanhuert'},
                    },
                    {
                        'number': 18,
                        'state': 'CLOSED',
                        'createdAt': '2024-12-15T22:31:19Z',
                        'updatedAt': '2024-12-19T20:00:26Z',
                        'closedAt': '2024-12-18T18:05:45Z',
                        'author': {'__typename': 'User', 'login': 'kitopopo'},
                    },
                    {
                        'number': 11,
                        'state': 'CLOSED',
                        'createdAt': '2024-01-13T01:46:25Z',
                        'updatedAt': '2024-12-19T06:50:58Z',
                        'closedAt': '2024-12-18T18:05:44Z',
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                    },
                    {
                        'number': 17,
                        'state': 'CLOSED',
                        'createdAt': '2024-12-12T19:42:50Z',
                        'updatedAt': '2024-12-14T13:11:59Z',
                        'closedAt': '2024-12-12T20:54:05Z',
                        'author': {'__typename': 'User', 'login': 'kitopopo'},
                    },
                    {
                        'number': 16,
                        'state': 'CLOSED',
                        'createdAt': '2024-10-03T20:43:55Z',
                        'updatedAt': '2024-12-13T08:37:53Z',
                        'closedAt': '2024-12-13T08:37:53Z',
                        'author': {'__typename': 'User', 'login': 'ppnacho'},
                    },
                    {
                        'number': 13,
                        'state': 'CLOSED',
                        'createdAt': '2024-02-12T18:15:15Z',
                        'updatedAt': '2024-03-23T05:28:21Z',
                        'closedAt': '2024-03-23T05:28:21Z',
                        'author': {'__typename': 'User', 'login': 'sergey08'},
                    },
                    {
                        'number': 12,
                        'state': 'CLOSED',
                        'createdAt': '2024-01-29T20:27:13Z',
                        'updatedAt': '2024-01-29T20:49:58Z',
                        'closedAt': '2024-01-29T20:40:21Z',
                        'author': {'__typename': 'User', 'login': 'PeteLawler'},
                    },
                    {
                        'number': 7,
                        'state': 'CLOSED',
                        'createdAt': '2024-01-02T16:19:53Z',
                        'updatedAt': '2024-01-10T11:00:12Z',
                        'closedAt': '2024-01-10T11:00:12Z',
                        'author': {'__typename': 'User', 'login': 'franlauma'},
                    },
                    {
                        'number': 6,
                        'state': 'CLOSED',
                        'createdAt': '2023-12-01T04:50:40Z',
                        'updatedAt': '2023-12-01T07:33:40Z',
                        'closedAt': '2023-12-01T07:33:40Z',
                        'author': {'__typename': 'User', 'login': 'sheaur'},
                    },
                    {
                        'number': 5,
                        'state': 'CLOSED',
                        'createdAt': '2023-10-09T17:48:35Z',
                        'updatedAt': '2023-10-17T19:58:07Z',
                        'closedAt': '2023-10-15T16:40:50Z',
                        'author': {'__typename': 'User', 'login': 'cbolumar'},
                    },
                    {
                        'number': 1,
                        'state': 'CLOSED',
                        'createdAt': '2023-10-08T14:12:14Z',
                        'updatedAt': '2023-10-16T18:06:42Z',
                        'closedAt': '2023-10-15T16:40:58Z',
                        'author': {'__typename': 'User', 'login': 'tergontor'},
                    },
                    {
                        'number': 4,
                        'state': 'CLOSED',
                        'createdAt': '2023-10-09T17:37:39Z',
                        'updatedAt': '2023-10-09T17:39:41Z',
                        'closedAt': '2023-10-09T17:38:52Z',
                        'author': {'__typename': 'User', 'login': 'cbolumar'},
                    },
                    {
                        'number': 2,
                        'state': 'CLOSED',
                        'createdAt': '2023-10-09T08:31:36Z',
                        'updatedAt': '2023-10-09T11:15:43Z',
                        'closedAt': '2023-10-09T11:15:43Z',
                        'author': {'__typename': 'User', 'login': 'sergey08'},
                    },
                ],
            }
        },
        'rateLimit': {'cost': 1, 'remaining': 4755, 'resetAt': '2026-10-31T09:13:32Z'},
    }
}

RELEASES_OK = {
    'data': {
        'repository': {
            'releases': {
                'pageInfo': {
                    'hasNextPage': False,
                    'endCursor': 'Y3Vyc29yOnYyOpK0MjAyMy0wNi0xOVQxNDo1OTo0MFrOBoDwiQ==',
                },
                'nodes': [
                    {
                        'tagName': 'v2.3.1',
                        'createdAt': '2026-04-04T18:30:38Z',
                        'publishedAt': '2026-04-04T18:30:39Z',
                        'isDraft': False,
                        'isPrerelease': False,
                    },
                    {
                        'tagName': 'V2.3',
                        'createdAt': '2026-04-02T15:49:19Z',
                        'publishedAt': '2026-04-02T15:50:48Z',
                        'isDraft': False,
                        'isPrerelease': False,
                    },
                    {
                        'tagName': 'V2.2',
                        'createdAt': '2026-02-28T14:55:45Z',
                        'publishedAt': '2026-02-28T14:56:41Z',
                        'isDraft': False,
                        'isPrerelease': False,
                    },
                    {
                        'tagName': 'V2.1',
                        'createdAt': '2025-10-31T07:07:57Z',
                        'publishedAt': '2025-10-31T07:09:03Z',
                        'isDraft': False,
                        'isPrerelease': False,
                    },
                    {
                        'tagName': 'V2.0',
                        'createdAt': '2025-03-17T14:47:42Z',
                        'publishedAt': '2025-03-17T14:48:27Z',
                        'isDraft': False,
                        'isPrerelease': False,
                    },
                    {
                        'tagName': 'V2.0-Beta',
                        'createdAt': '2025-03-17T11:28:04Z',
                        'publishedAt': '2025-03-17T11:29:53Z',
                        'isDraft': False,
                        'isPrerelease': True,
                    },
                    {
                        'tagName': 'V1.4',
                        'createdAt': '2024-12-18T18:03:54Z',
                        'publishedAt': '2024-12-18T18:04:59Z',
                        'isDraft': False,
                        'isPrerelease': False,
                    },
                    {
                        'tagName': 'V1.3',
                        'createdAt': '2023-10-14T06:03:13Z',
                        'publishedAt': '2023-10-15T16:43:20Z',
                        'isDraft': False,
                        'isPrerelease': False,
                    },
                    {
                        'tagName': 'V1.2',
                        'createdAt': '2023-10-09T17:41:23Z',
                        'publishedAt': '2023-10-09T17:42:44Z',
                        'isDraft': False,
                        'isPrerelease': False,
                    },
                    {
                        'tagName': '1.1',
                        'createdAt': '2023-10-09T11:13:53Z',
                        'publishedAt': '2023-10-09T11:15:12Z',
                        'isDraft': False,
                        'isPrerelease': False,
                    },
                    {
                        'tagName': '1.0',
                        'createdAt': '2023-06-19T14:59:40Z',
                        'publishedAt': '2023-06-19T15:00:19Z',
                        'isDraft': False,
                        'isPrerelease': False,
                    },
                ],
            }
        },
        'rateLimit': {'cost': 1, 'remaining': 4929, 'resetAt': '2026-10-31T09:13:32Z'},
    }
}

WORKFLOW_RUNS_OK = {
    'total_count': 214,
    'workflow_runs': [
        {
            'id': 39453803857,
            'name': 'Create Release and Tag',
            'path': '.github/workflows/create-release.yml',
            'event': 'pull_request',
            'head_branch': 'frenck/add-brand-assets-gas_station_spain',
            'status': 'completed',
            'conclusion': 'skipped',
            'created_at': '2026-10-20T16:01:52Z',
            'updated_at': '2026-10-20T16:01:58Z',
            'run_started_at': '2026-10-20T16:01:52Z',
            'run_attempt': 1,
        },
        {
            'id': 39453802041,
            'name': 'Tests',
            'path': '.github/workflows/tests.yml',
            'event': 'push',
            'head_branch': 'main',
            'status': 'completed',
            'conclusion': 'success',
            'created_at': '2026-10-20T16:01:51Z',
            'updated_at': '2026-10-20T16:02:22Z',
            'run_started_at': '2026-10-20T16:01:51Z',
            'run_attempt': 1,
        },
        {
            'id': 39445158088,
            'name': 'Tests',
            'path': '.github/workflows/tests.yml',
            'event': 'pull_request',
            'head_branch': 'frenck/add-brand-assets-gas_station_spain',
            'status': 'completed',
            'conclusion': 'success',
            'created_at': '2026-10-20T15:05:07Z',
            'updated_at': '2026-10-20T16:00:50Z',
            'run_started_at': '2026-10-20T16:00:22Z',
            'run_attempt': 2,
        },
        {
            'id': 39445157312,
            'name': 'Validate Release PR',
            'path': '.github/workflows/validate-release-pr.yml',
            'event': 'pull_request',
            'head_branch': 'frenck/add-brand-assets-gas_station_spain',
            'status': 'completed',
            'conclusion': 'skipped',
            'created_at': '2026-10-20T15:05:07Z',
            'updated_at': '2026-10-20T16:00:31Z',
            'run_started_at': '2026-10-20T16:00:22Z',
            'run_attempt': 2,
        },
        {
            'id': 39445156073,
            'name': 'Ruff',
            'path': '.github/workflows/ruff.yaml',
            'event': 'pull_request',
            'head_branch': 'frenck/add-brand-assets-gas_station_spain',
            'status': 'completed',
            'conclusion': 'success',
            'created_at': '2026-10-20T15:05:07Z',
            'updated_at': '2026-10-20T16:00:46Z',
            'run_started_at': '2026-10-20T16:00:22Z',
            'run_attempt': 2,
        },
    ],
}

WORKFLOW_RUN_OK = {
    'id': 39453803857,
    'name': 'Create Release and Tag',
    'path': '.github/workflows/create-release.yml',
    'event': 'pull_request',
    'head_branch': 'frenck/add-brand-assets-gas_station_spain',
    'status': 'completed',
    'conclusion': 'skipped',
    'created_at': '2026-10-20T16:01:52Z',
    'updated_at': '2026-10-20T16:01:58Z',
    'run_started_at': '2026-10-20T16:01:52Z',
    'run_attempt': 1,
}

STARGAZERS_OK = {
    'data': {
        'repository': {
            'stargazers': {
                'pageInfo': {
                    'hasNextPage': False,
                    'endCursor': 'Y3Vyc29yOnYyOpK0MjAxNS0wNi0zMFQwODowNTo1NlrOAlFqQg==',
                },
                'edges': [
                    {'starredAt': '2025-03-21T22:32:32Z', 'node': {'id': 'MDQ6VXNlcjE4NTkwMg=='}},
                    {'starredAt': '2024-11-11T17:04:44Z', 'node': {'id': 'MDQ6VXNlcjQ2OTQ0Mjg3'}},
                    {'starredAt': '2023-09-21T00:41:41Z', 'node': {'id': 'MDQ6VXNlcjY1OTMzMzQw'}},
                    {'starredAt': '2023-07-16T23:59:24Z', 'node': {'id': 'MDQ6VXNlcjI4OTUwNzM2'}},
                    {'starredAt': '2023-02-07T07:46:17Z', 'node': {'id': 'U_kgDOBlkIcw'}},
                    {'starredAt': '2022-05-15T14:39:56Z', 'node': {'id': 'MDQ6VXNlcjg0NDEwNTU1'}},
                    {'starredAt': '2022-03-20T17:59:21Z', 'node': {'id': 'MDQ6VXNlcjg1NjQ1OTE2'}},
                    {'starredAt': '2021-08-14T13:53:11Z', 'node': {'id': 'MDQ6VXNlcjQ5MTQ1OA=='}},
                    {'starredAt': '2020-11-29T11:59:31Z', 'node': {'id': 'MDQ6VXNlcjE1NzMwMzQ='}},
                    {'starredAt': '2020-10-29T00:11:30Z', 'node': {'id': 'MDQ6VXNlcjM3NTg5NTE='}},
                    {'starredAt': '2020-08-24T15:35:22Z', 'node': {'id': 'MDQ6VXNlcjUxMTA1Mg=='}},
                    {'starredAt': '2019-09-27T09:02:42Z', 'node': {'id': 'MDQ6VXNlcjI3ODc5MA=='}},
                    {'starredAt': '2019-07-10T04:40:12Z', 'node': {'id': 'MDQ6VXNlcjUwMDI0NTM='}},
                    {'starredAt': '2018-12-12T20:17:52Z', 'node': {'id': 'MDQ6VXNlcjMyNDY5MDgy'}},
                    {'starredAt': '2018-11-16T14:30:19Z', 'node': {'id': 'MDQ6VXNlcjUzOTg1NTc='}},
                    {'starredAt': '2018-11-05T17:16:17Z', 'node': {'id': 'MDQ6VXNlcjgxMjAzNw=='}},
                    {'starredAt': '2018-06-13T15:59:01Z', 'node': {'id': 'MDQ6VXNlcjI1MzY5Mzcy'}},
                    {'starredAt': '2018-04-21T03:23:51Z', 'node': {'id': 'MDQ6VXNlcjEzMzY4ODE='}},
                    {'starredAt': '2018-03-21T03:04:55Z', 'node': {'id': 'MDQ6VXNlcjY0MzcyNDM='}},
                    {'starredAt': '2017-12-13T06:46:50Z', 'node': {'id': 'MDQ6VXNlcjUxODM0Nzc='}},
                    {'starredAt': '2017-08-27T19:05:01Z', 'node': {'id': 'MDQ6VXNlcjUyMjI4MQ=='}},
                    {'starredAt': '2017-08-02T12:39:43Z', 'node': {'id': 'MDQ6VXNlcjg0Mjg4NTI='}},
                    {'starredAt': '2017-01-18T13:26:02Z', 'node': {'id': 'MDQ6VXNlcjcyMzQ1MQ=='}},
                    {'starredAt': '2016-04-21T02:05:49Z', 'node': {'id': 'MDQ6VXNlcjc1MzcyOTY='}},
                    {'starredAt': '2015-11-15T08:20:18Z', 'node': {'id': 'MDQ6VXNlcjE2Nzc3OTA='}},
                    {'starredAt': '2015-10-26T13:10:50Z', 'node': {'id': 'MDQ6VXNlcjE2Nzg1NzU='}},
                    {'starredAt': '2015-10-26T12:29:16Z', 'node': {'id': 'MDQ6VXNlcjU0MDQxNTI='}},
                    {'starredAt': '2015-10-26T06:51:45Z', 'node': {'id': 'MDQ6VXNlcjM1OTk2ODI='}},
                    {'starredAt': '2015-10-01T09:52:55Z', 'node': {'id': 'MDQ6VXNlcjExNTM0NzM='}},
                    {'starredAt': '2015-09-29T01:25:42Z', 'node': {'id': 'MDQ6VXNlcjc3NTAxMw=='}},
                    {'starredAt': '2015-09-27T01:42:43Z', 'node': {'id': 'MDQ6VXNlcjMzNTcxOQ=='}},
                    {'starredAt': '2015-09-27T01:21:13Z', 'node': {'id': 'MDQ6VXNlcjExNDg2MDE='}},
                    {'starredAt': '2015-09-26T22:56:26Z', 'node': {'id': 'MDQ6VXNlcjE4NDI0OQ=='}},
                    {'starredAt': '2015-09-23T02:50:19Z', 'node': {'id': 'MDQ6VXNlcjM5NTM0MA=='}},
                    {'starredAt': '2015-09-22T19:52:33Z', 'node': {'id': 'MDQ6VXNlcjI5OTQzNTY='}},
                    {'starredAt': '2015-09-21T05:57:11Z', 'node': {'id': 'MDQ6VXNlcjEyMDkxNTk='}},
                    {'starredAt': '2015-09-18T16:01:11Z', 'node': {'id': 'MDQ6VXNlcjczMzEzMA=='}},
                    {'starredAt': '2015-09-17T18:47:56Z', 'node': {'id': 'MDQ6VXNlcjg5NTU1Mw=='}},
                    {'starredAt': '2015-09-13T00:06:37Z', 'node': {'id': 'MDQ6VXNlcjEzNjEzODE='}},
                    {'starredAt': '2015-09-09T07:35:01Z', 'node': {'id': 'MDQ6VXNlcjIyOTgzMjU='}},
                    {'starredAt': '2015-09-01T05:50:48Z', 'node': {'id': 'MDQ6VXNlcjM0MjA5NQ=='}},
                    {'starredAt': '2015-08-30T00:37:43Z', 'node': {'id': 'MDQ6VXNlcjI2OTkw'}},
                    {'starredAt': '2015-08-06T15:46:37Z', 'node': {'id': 'MDQ6VXNlcjI3MjcyNzk='}},
                    {'starredAt': '2015-08-02T14:19:31Z', 'node': {'id': 'MDQ6VXNlcjI5MTE0Mg=='}},
                    {'starredAt': '2015-07-28T00:04:38Z', 'node': {'id': 'MDQ6VXNlcjY5NDY3NzI='}},
                    {'starredAt': '2015-07-20T17:23:46Z', 'node': {'id': 'MDQ6VXNlcjI0NDcwNA=='}},
                    {'starredAt': '2015-07-15T10:24:33Z', 'node': {'id': 'MDQ6VXNlcjE3MDY2OTU='}},
                    {'starredAt': '2015-07-10T08:48:01Z', 'node': {'id': 'MDQ6VXNlcjE2ODc0MTg='}},
                    {'starredAt': '2015-07-10T03:14:04Z', 'node': {'id': 'MDQ6VXNlcjQ2NTY1'}},
                    {'starredAt': '2015-06-30T08:05:56Z', 'node': {'id': 'MDQ6VXNlcjIwMTgwNA=='}},
                ],
            }
        },
        'rateLimit': {'cost': 1, 'remaining': 4754, 'resetAt': '2026-10-31T09:13:32Z'},
    }
}

FORKS_OK = [
    {'id': 905394408, 'created_at': '2024-12-18T18:28:36Z'},
    {'id': 694414618, 'created_at': '2023-09-21T00:41:43Z'},
    {'id': 416090426, 'created_at': '2021-10-11T21:21:18Z'},
    {'id': 314475023, 'created_at': '2020-11-20T07:12:17Z'},
    {'id': 199967649, 'created_at': '2019-08-01T03:13:58Z'},
]

BOT_REVIEWS_OK = {
    'data': {
        'repository': {
            'pullRequest': {
                'reviews': {
                    'nodes': [
                        {
                            'submittedAt': '2026-10-30T20:43:14Z',
                            'author': {
                                '__typename': 'Bot',
                                'login': 'copilot-pull-request-reviewer',
                            },
                        },
                        {
                            'submittedAt': '2026-10-31T04:36:53Z',
                            'author': {'__typename': 'User', 'login': 'jruales'},
                        },
                    ]
                }
            }
        },
        'rateLimit': {'cost': 1, 'remaining': 4753, 'resetAt': '2026-10-31T09:13:32Z'},
    }
}
