"""A small set of commits, pull requests and issues with every statistic worked out by hand.

Commits are named for their repo (`a` alpha, `b` beta, `g` gamma) and listed oldest first within
each repo. The expected figures below are literals: each comment shows the sum it came from, so
nothing here is computed by the code under test. Merge commits are left out of line counts.

Pull requests are `p1`, `p2`, ... and issues `i1`, `i2`, ... in the comments, in the numbering
order of their repo's list; `g1` and `gi1` are gamma's. Pull request times are written
`created / first review / merged` as UTC instants.
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


def moment(when: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(when).replace(tzinfo=UTC)


def pull(
    repo_name: str,
    number: int,
    login: str | None,
    created: str,
    *,
    review: str | None = None,
    merged: str | None = None,
    closed: str | None = None,
    updated: str | None = None,
    size: tuple[int, int] = (1, 1),
) -> wambatic.fetch.base.PullRequest:
    """A pull request; `closed` defaults to `merged`, and `updated` to its last event."""
    events = [created, review, merged, closed]
    last = max(event for event in events if event is not None)
    return wambatic.fetch.base.PullRequest(
        repo=repo_name,
        number=number,
        author_login=login,
        created_at=moment(created),
        updated_at=moment(updated or last),
        merged_at=None if merged is None else moment(merged),
        closed_at=None if (closed or merged) is None else moment(str(closed or merged)),
        first_review_at=None if review is None else moment(review),
        additions=size[0],
        deletions=size[1],
    )


def issue(
    repo_name: str,
    number: int,
    login: str | None,
    created: str,
    closed: str | None = None,
) -> wambatic.fetch.base.Issue:
    return wambatic.fetch.base.Issue(
        repo=repo_name,
        number=number,
        author_login=login,
        created_at=moment(created),
        updated_at=moment(closed or created),
        closed_at=None if closed is None else moment(closed),
    )


PULL_REQUESTS = [
    # alpha
    pull(
        ALPHA,
        1,
        'hubot',
        '2026-10-05T10:00',
        review='2026-10-05T14:00',
        merged='2026-10-06T10:00',
        size=(10, 5),
    ),  # review 4h, merge 24h, size 15
    pull(
        ALPHA,
        2,
        'Octocat',
        '2026-10-10T08:00',
        review='2026-10-10T20:00',
        merged='2026-10-12T08:00',
        size=(30, 10),
    ),  # review 12h, merge 48h, size 40
    pull(
        ALPHA,
        3,
        'hubot',
        '2026-10-20T09:00',
        review='2026-10-21T09:00',
        merged='2026-10-23T09:00',
        size=(8, 2),
    ),  # review 24h, merge 72h, size 10
    pull(ALPHA, 4, 'octocat', '2026-10-25T09:00', closed='2026-10-26T09:00'),  # closed unmerged
    # created in September: merged in October, but reviewed (and created) outside the range
    pull(
        ALPHA,
        5,
        'monalisa',
        '2026-09-28T12:00',
        review='2026-09-29T12:00',
        merged='2026-10-02T12:00',
        size=(50, 50),
    ),  # merge 96h, size 100
    pull(ALPHA, 6, 'hubot', '2026-11-10T09:00'),  # open all through November
    # merged at 23:30 UTC on 12-31, which is 00:30 on 01-01 in Berlin
    pull(
        ALPHA,
        7,
        'hubot',
        '2026-12-30T10:00',
        review='2026-12-30T12:00',
        merged='2026-12-31T23:30',
        size=(4, 1),
    ),  # review 2h, merge 37.5h, size 5
    pull(ALPHA, 8, 'dependabot[bot]', '2027-01-10T09:00'),  # open, a bot's
    # fully before the range, so never read
    pull(
        ALPHA, 9, 'hubot', '2026-08-01T09:00', review='2026-08-02T09:00', merged='2026-08-05T09:00'
    ),
    # beta
    pull(
        BETA, 1, None, '2026-10-15T09:00', merged='2026-10-15T15:00', size=(3, 1)
    ),  # no review; 6h
    pull(
        BETA,
        2,
        'octocat',
        '2027-01-12T09:00',
        review='2027-01-12T10:00',
        merged='2027-01-13T09:00',
        size=(12, 3),
    ),  # review 1h, merge 24h, size 15
    # created and reviewed inside the range, merged the day after it ends
    pull(
        BETA,
        3,
        'hubot',
        '2027-01-30T09:00',
        review='2027-01-31T09:00',
        merged='2027-02-01T08:00',
        size=(7, 7),
    ),  # review 24h
    # gamma, owned by the user octocat
    pull(
        GAMMA,
        1,
        'Octocat',
        '2026-10-10T09:00',
        review='2026-10-10T11:00',
        merged='2026-10-11T09:00',
        size=(6, 4),
    ),  # review 2h, merge 24h, size 10
    pull(
        GAMMA,
        2,
        'monalisa',
        '2026-10-12T09:00',
        review='2026-10-13T09:00',
        merged='2026-10-14T09:00',
        size=(20, 5),
    ),  # review 24h, merge 48h, size 25
]

ISSUES = [
    # alpha
    issue(ALPHA, 1, 'octocat', '2026-10-03T09:00', '2026-10-04T09:00'),  # close 24h
    issue(ALPHA, 2, 'hubot', '2026-10-07T09:00'),  # closed and reopened: open
    issue(ALPHA, 3, 'monalisa', '2026-10-08T09:00', '2026-10-18T09:00'),  # close 240h
    # beta
    issue(BETA, 1, 'octocat', '2026-11-02T10:00', '2026-11-02T22:00'),  # close 12h
    issue(BETA, 2, None, '2026-09-30T12:00', '2026-10-02T12:00'),  # opened in September; close 48h
    issue(BETA, 3, 'hubot', '2027-01-05T09:00'),
    # gamma
    issue(GAMMA, 1, 'octocat', '2026-11-05T09:00', '2026-11-08T09:00'),  # close 72h
    issue(GAMMA, 2, 'monalisa', '2026-10-15T09:00'),
]

FLOW_METRICS = (
    'prs_opened',
    'prs_merged',
    'issues_opened',
    'issues_closed',
    'time_to_first_review_p50',
    'time_to_first_review_p90',
    'time_to_merge_p50',
    'time_to_merge_p90',
    'time_to_close_p50',
    'time_to_close_p90',
    'pr_size_p50',
)

# The org (alpha and beta) by month in UTC: metric -> label -> value, a month with no value left
# out. Checked by hand on 2026-10-30. Percentiles are statistics.median and
# statistics.quantiles(n=10, method='inclusive')[8], which for sorted values v0..vk (m = k) is
# (v[j] * (10 - d) + v[j + 1] * d) / 10 with j, d = divmod(9 * m, 10).
ORG_FLOW_BY_MONTH_UTC: dict[str, dict[str, float]] = {
    # opened by creation date. Oct: p1 p2 p3 p4 beta-p1 (alpha-p5 was created in September).
    # Nov: alpha-p6. Dec: alpha-p7. Jan: alpha-p8, beta-p2, beta-p3 (alpha-p9 is in August)
    'prs_opened': {'2026-10': 5, '2026-11': 1, '2026-12': 1, '2027-01': 3},
    # merged by merge date. Oct: p1 p2 p3 p5 beta-p1. Dec: alpha-p7 (23:30 on 12-31).
    # Jan: beta-p2 (beta-p3 merges on 02-01, after the range)
    'prs_merged': {'2026-10': 5, '2026-11': 0, '2026-12': 1, '2027-01': 1},
    # Oct: alpha-i1 i2 i3. Nov: beta-i1. Jan: beta-i3 (beta-i2 was opened in September)
    'issues_opened': {'2026-10': 3, '2026-11': 1, '2026-12': 0, '2027-01': 1},
    # Oct: alpha-i1 i3 beta-i2 (alpha-i2 was reopened). Nov: beta-i1
    'issues_closed': {'2026-10': 3, '2026-11': 1, '2026-12': 0, '2027-01': 0},
    # by review date. Oct values [4, 12, 24]: p50 12, p90 (12 * 2 + 24 * 8) / 10 = 21.6
    # (alpha-p5 was reviewed in September; beta-p1 has no review).
    # Dec: alpha-p7 2. Jan values [1, 24] (beta-p2, beta-p3): p50 (1 + 24) / 2 = 12.5,
    # p90 (1 * 1 + 24 * 9) / 10 = 21.7
    'time_to_first_review_p50': {'2026-10': 12.0, '2026-12': 2.0, '2027-01': 12.5},
    'time_to_first_review_p90': {'2026-10': 21.6, '2026-12': 2.0, '2027-01': 21.7},
    # by merge date. Oct values [6, 24, 48, 72, 96]: p50 48, p90 (72 * 4 + 96 * 6) / 10 = 86.4.
    # Dec: 37.5 (23:30 on 12-31 less 10:00 on 12-30). Jan: 24 (beta-p2)
    'time_to_merge_p50': {'2026-10': 48.0, '2026-12': 37.5, '2027-01': 24.0},
    'time_to_merge_p90': {'2026-10': 86.4, '2026-12': 37.5, '2027-01': 24.0},
    # by close date, issues. Oct values [24, 48, 240]: p50 48, p90 (48 * 2 + 240 * 8) / 10 = 201.6.
    # Nov: 12
    'time_to_close_p50': {'2026-10': 48.0, '2026-11': 12.0},
    'time_to_close_p90': {'2026-10': 201.6, '2026-11': 12.0},
    # merged sizes. Oct [4, 10, 15, 40, 100]: median_low 15. Dec [5]. Jan [15]
    'pr_size_p50': {'2026-10': 15, '2026-12': 5, '2027-01': 15},
}

# In Europe/Berlin alpha-p7's merge (23:30 UTC on 12-31) is on 2027-01-01, so only the series
# built on the merge date move. Jan merge values [24, 37.5]: p50 (24 + 37.5) / 2 = 30.75,
# p90 (24 * 1 + 37.5 * 9) / 10 = 36.15; sizes [5, 15]: median_low 5. December has no merge.
ORG_FLOW_BY_MONTH_BERLIN: dict[str, dict[str, float]] = {
    'prs_merged': {'2026-10': 5, '2026-11': 0, '2026-12': 0, '2027-01': 2},
    'time_to_merge_p50': {'2026-10': 48.0, '2027-01': 30.75},
    'time_to_merge_p90': {'2026-10': 86.4, '2027-01': 36.15},
    'pr_size_p50': {'2026-10': 15, '2027-01': 5},
}

# The user octocat's own items in gamma as one bucket: gamma-p1 (authored 'Octocat') and
# gamma-i1; gamma-p2 and gamma-i2 are other people's. Times as the comments above.
USER_FLOW_TOTAL_UTC: dict[str, float] = {
    'prs_opened': 1,
    'prs_merged': 1,
    'issues_opened': 1,
    'issues_closed': 1,
    'time_to_first_review_p50': 2.0,
    'time_to_first_review_p90': 2.0,
    'time_to_merge_p50': 24.0,
    'time_to_merge_p90': 24.0,
    'time_to_close_p50': 72.0,
    'time_to_close_p90': 72.0,
    'pr_size_p50': 10,
}
