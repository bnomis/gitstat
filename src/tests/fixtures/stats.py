"""A small set of commits with every statistic worked out by hand.

Commits are named for their repo (`a` alpha, `b` beta, `g` gamma) and listed oldest first within
each repo. The expected figures below are literals: each comment shows the sum it came from, so
nothing here is computed by the code under test. Merge commits are left out of line counts.
"""

import datetime
import typing

import wambatic.fetch.base

UTC = datetime.UTC
NOW = datetime.datetime(2027, 1, 20, 12, 0, tzinfo=UTC)
ALPHA_SYNCED_AT = datetime.datetime(2027, 2, 1, 10, 0, tzinfo=UTC)
BETA_SYNCED_AT = datetime.datetime(2027, 2, 1, 12, 0, tzinfo=UTC)
GAMMA_SYNCED_AT = datetime.datetime(2027, 2, 1, 11, 0, tzinfo=UTC)

ORG = wambatic.fetch.base.Subject('org', 'octo-org')
USER = wambatic.fetch.base.Subject('user', 'octocat')
ALPHA = 'octo-org/alpha'
BETA = 'octo-org/beta'
GAMMA = 'octocat/gamma'

# The month buckets of the range 2026-10-01 to 2027-01-31
SINCE = datetime.date(2026, 10, 1)
UNTIL = datetime.date(2027, 1, 31)
LABELS = ('2026-10', '2026-11', '2026-12', '2027-01')


def repo(name: str, hours: int) -> wambatic.fetch.base.Repo:
    pushed = datetime.datetime(2027, 1, 16, hours, 0, tzinfo=UTC)
    return wambatic.fetch.base.Repo(
        name_with_owner=name,
        default_branch='main',
        head_oid=f'{name}-head',
        is_archived=False,
        is_fork=False,
        pushed_at=pushed,
        updated_at=pushed,
    )


REPOS = [repo(ALPHA, 9), repo(BETA, 10), repo(GAMMA, 11)]


def commit(
    repo_name: str,
    oid: str,
    when: str,
    login: str | None,
    additions: int,
    deletions: int,
    *,
    merge: bool = False,
) -> wambatic.fetch.base.Commit:
    return wambatic.fetch.base.Commit(
        repo=repo_name,
        oid=oid,
        authored_at=datetime.datetime.fromisoformat(when).replace(tzinfo=UTC),
        author_login=login,
        additions=additions,
        deletions=deletions,
        is_merge=merge,
    )


COMMITS = [
    # alpha
    commit(ALPHA, 'a1', '2026-10-05T10:00', 'Octocat', 10, 2),
    commit(ALPHA, 'a2', '2026-10-05T15:00', 'Octocat', 4, 1),  # same day as a1
    commit(ALPHA, 'a3', '2026-10-20T09:00', 'hubot', 20, 5),
    commit(ALPHA, 'a4', '2026-10-21T09:00', 'monalisa', 100, 50, merge=True),
    commit(ALPHA, 'a5', '2026-12-31T23:30', 'hubot', 7, 3),  # December in UTC, January in Berlin
    commit(ALPHA, 'a6', '2027-01-01T08:00', 'octocat', 2, 2),  # 2026-W53 with a5
    # beta
    commit(BETA, 'b1', '2026-10-20T12:00', 'octocat', 6, 0),  # same person as Octocat
    commit(BETA, 'b2', '2026-10-25T10:00', 'dependabot[bot]', 30, 30),
    commit(BETA, 'b3', '2026-10-26T10:00', None, 3, 1),  # unattributed
    commit(BETA, 'b4', '2027-01-15T10:00', 'hubot', 8, 4),
    # gamma, owned by the user octocat
    commit(GAMMA, 'g1', '2026-10-10T10:00', 'Octocat', 5, 1),
    commit(GAMMA, 'g2', '2026-10-11T10:00', 'monalisa', 9, 9),
]

ORG_COMMITS = [c for c in COMMITS if c.repo != GAMMA]

# The org (alpha and beta) by month in UTC. November has no commits.
ORG_BY_MONTH_UTC = {
    '2026-10': {
        'commits': 7,  # a1 a2 a3 a4 b1 b2 b3
        # octocat (a1 a2 b1), hubot (a3), monalisa (a4); b2 is a bot and b3 has no login
        'contributors': 3,
        'active_days': 5,  # 10-05 (a1 a2), 10-20 (a3 b1), 10-21 (a4), 10-25 (b2), 10-26 (b3)
        'lines_added': 73,  # 10 + 4 + 20 + 6 + 30 + 3; the merge a4 is left out
        'lines_deleted': 39,  # 2 + 1 + 5 + 0 + 30 + 1
        'lines_net': 34,  # 73 - 39
    },
    '2026-11': {
        'commits': 0,
        'contributors': 0,
        'active_days': 0,
        'lines_added': 0,
        'lines_deleted': 0,
        'lines_net': 0,
    },
    '2026-12': {
        'commits': 1,  # a5
        'contributors': 1,  # hubot
        'active_days': 1,  # 12-31
        'lines_added': 7,
        'lines_deleted': 3,
        'lines_net': 4,  # 7 - 3
    },
    '2027-01': {
        'commits': 2,  # a6 b4
        'contributors': 2,  # octocat (a6), hubot (b4)
        'active_days': 2,  # 01-01, 01-15
        'lines_added': 10,  # 2 + 8
        'lines_deleted': 6,  # 2 + 4
        'lines_net': 4,  # 10 - 6
    },
}

# The same range by month in Europe/Berlin (UTC+1 in winter): a5 is on 2027-01-01 at 00:30 there.
ORG_BY_MONTH_BERLIN = {
    '2026-10': ORG_BY_MONTH_UTC['2026-10'],  # every October commit is mid-day, so unchanged
    '2026-11': ORG_BY_MONTH_UTC['2026-11'],
    '2026-12': {
        'commits': 0,  # a5 has moved to January
        'contributors': 0,
        'active_days': 0,
        'lines_added': 0,
        'lines_deleted': 0,
        'lines_net': 0,
    },
    '2027-01': {
        'commits': 3,  # a5 a6 b4
        'contributors': 2,  # hubot (a5 b4), octocat (a6)
        'active_days': 2,  # 01-01 (a5 a6), 01-15
        'lines_added': 17,  # 7 + 2 + 8
        'lines_deleted': 9,  # 3 + 2 + 4
        'lines_net': 8,  # 17 - 9
    },
}

# The whole range as one bucket
ORG_TOTAL_UTC = {
    'commits': 10,  # 7 + 0 + 1 + 2
    'contributors': 3,  # octocat, hubot, monalisa
    'active_days': 8,  # 5 + 0 + 1 + 2, no date repeats across months
    'lines_added': 90,  # 73 + 0 + 7 + 10
    'lines_deleted': 48,  # 39 + 0 + 3 + 6
    'lines_net': 42,  # 90 - 48
}
ORG_TOTAL_BERLIN = {
    **ORG_TOTAL_UTC,
    'active_days': 7,  # 5 + 0 + 0 + 2: 12-31 became 01-01, which a6 shares
}

# Breakdowns by month in UTC: label -> (commits, lines_added, lines_deleted, lines_net)
ORG_BY_REPO_UTC = {
    ALPHA: {
        '2026-10': (4, 34, 8, 26),  # a1 a2 a3 a4; 10 + 4 + 20, 2 + 1 + 5, merge left out
        '2026-11': (0, 0, 0, 0),
        '2026-12': (1, 7, 3, 4),  # a5
        '2027-01': (1, 2, 2, 0),  # a6
    },
    BETA: {
        '2026-10': (3, 39, 31, 8),  # b1 b2 b3; 6 + 30 + 3, 0 + 30 + 1
        '2026-11': (0, 0, 0, 0),
        '2026-12': (0, 0, 0, 0),
        '2027-01': (1, 8, 4, 4),  # b4
    },
}
# `by` is the spelling of the first commit seen, so octocat is 'Octocat'
ORG_BY_AUTHOR_UTC = {
    'Octocat': {
        '2026-10': (3, 20, 3, 17),  # a1 a2 b1; 10 + 4 + 6, 2 + 1 + 0
        '2026-11': (0, 0, 0, 0),
        '2026-12': (0, 0, 0, 0),
        '2027-01': (1, 2, 2, 0),  # a6
    },
    'dependabot[bot]': {
        '2026-10': (1, 30, 30, 0),  # b2
        '2026-11': (0, 0, 0, 0),
        '2026-12': (0, 0, 0, 0),
        '2027-01': (0, 0, 0, 0),
    },
    'hubot': {
        '2026-10': (1, 20, 5, 15),  # a3
        '2026-11': (0, 0, 0, 0),
        '2026-12': (1, 7, 3, 4),  # a5
        '2027-01': (1, 8, 4, 4),  # b4
    },
    'monalisa': {
        '2026-10': (1, 0, 0, 0),  # a4 is a merge, so no lines
        '2026-11': (0, 0, 0, 0),
        '2026-12': (0, 0, 0, 0),
        '2027-01': (0, 0, 0, 0),
    },
    'unattributed': {
        '2026-10': (1, 3, 1, 2),  # b3
        '2026-11': (0, 0, 0, 0),
        '2026-12': (0, 0, 0, 0),
        '2027-01': (0, 0, 0, 0),
    },
}

# The org's top contributors over the whole range, in UTC or Berlin: commits descending, then
# login. The bot is left out. monalisa and unattributed tie on one commit.
ORG_TOP_CONTRIBUTORS: list[dict[str, typing.Any]] = [
    {
        'login': 'Octocat',
        'commits': 4,  # a1 a2 b1 a6
        'lines_added': 22,  # 10 + 4 + 6 + 2
        'lines_deleted': 5,  # 2 + 1 + 0 + 2
        'lines_net': 17,
        'active_days': 3,  # 10-05, 10-20, 2027-01-01
    },
    {
        'login': 'hubot',
        'commits': 3,  # a3 a5 b4
        'lines_added': 35,  # 20 + 7 + 8
        'lines_deleted': 12,  # 5 + 3 + 4
        'lines_net': 23,
        'active_days': 3,  # 10-20, then 12-31 and 01-15 in UTC or 01-01 and 01-15 in Berlin
    },
    {
        'login': 'monalisa',
        'commits': 1,  # a4, a merge
        'lines_added': 0,
        'lines_deleted': 0,
        'lines_net': 0,
        'active_days': 1,  # 10-21
    },
    {
        'login': 'unattributed',
        'commits': 1,  # b3
        'lines_added': 3,
        'lines_deleted': 1,
        'lines_net': 2,
        'active_days': 1,  # 10-26
    },
]
