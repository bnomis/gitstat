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
    labels: tuple[str, ...] = (),
    first_commit: str | None = None,
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
        labels=labels,
        first_commit_at=None if first_commit is None else moment(first_commit),
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
        first_commit='2026-10-04T10:00',
    ),  # review 4h, merge 24h, size 15
    pull(
        ALPHA,
        2,
        'Octocat',
        '2026-10-10T08:00',
        review='2026-10-10T20:00',
        merged='2026-10-12T08:00',
        size=(30, 10),
        labels=('bug', 'Hotfix'),  # a hotfix, matched whatever its case
    ),  # review 12h, merge 48h, size 40
    pull(
        ALPHA,
        3,
        'hubot',
        '2026-10-20T09:00',
        review='2026-10-21T09:00',
        merged='2026-10-23T09:00',
        size=(8, 2),
        first_commit='2026-10-19T09:00',
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
        first_commit='2026-09-27T12:00',
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
        first_commit='2027-01-11T09:00',
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
        labels=('hotfix',),  # restored on 02-01, after the range
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


def release(
    repo_name: str, tag: str, published: str, *, prerelease: bool = False
) -> wambatic.fetch.base.Release:
    """A release created an hour before it was published."""
    when = moment(published)
    return wambatic.fetch.base.Release(
        repo=repo_name,
        tag_name=tag,
        created_at=when - datetime.timedelta(hours=1),
        published_at=when,
        is_prerelease=prerelease,
    )


RELEASES = [
    # alpha
    release(ALPHA, 'v0.9.0', '2026-09-20T10:00'),  # before the range
    release(ALPHA, 'v1.0.0', '2026-10-06T12:00'),
    release(ALPHA, 'v1.1.0-rc1', '2026-10-20T12:00', prerelease=True),
    release(ALPHA, 'v1.1.0', '2026-10-25T10:00'),
    release(ALPHA, 'v1.2.0', '2026-12-31T23:45'),  # 2027-01-01 00:45 in Berlin
    # beta
    release(BETA, 'b1.0', '2026-10-15T16:00'),
    release(BETA, 'b1.1', '2027-01-14T12:00'),
    # gamma, owned by the user octocat
    release(GAMMA, 'g1.0', '2026-10-12T12:00'),
]

WORKFLOW_PATHS = {
    'ci': ('.github/workflows/ci.yml', 'CI'),
    'deploy': ('.github/workflows/deploy.yml', 'Deploy'),
}


def run(
    repo_name: str,
    run_id: int,
    created: str,
    conclusion: str | None,
    minutes: int,
    *,
    status: str = 'completed',
    started: bool = True,
    workflow: str = 'ci',
) -> wambatic.fetch.base.WorkflowRun:
    """A run that started when it was created (unless `started` is false) and last updated
    `minutes` later."""
    when = moment(created)
    path, name = WORKFLOW_PATHS[workflow]
    return wambatic.fetch.base.WorkflowRun(
        repo=repo_name,
        id=run_id,
        workflow_path=path,
        name=name,
        event='push',
        head_branch='main',
        status=status,
        conclusion=conclusion,
        created_at=when,
        updated_at=when + datetime.timedelta(minutes=minutes),
        run_started_at=when if started else None,
        run_attempt=1,
    )


WORKFLOW_RUNS = [
    # alpha
    run(ALPHA, 101, '2026-10-05T10:00', 'success', 6),
    run(ALPHA, 102, '2026-10-05T15:00', 'failure', 10),
    run(ALPHA, 103, '2026-10-20T09:00', 'success', 12),
    run(ALPHA, 104, '2026-10-20T09:30', 'cancelled', 1),  # not an outcome of the code
    run(ALPHA, 105, '2026-10-06T12:00', 'success', 8, workflow='deploy'),
    run(ALPHA, 106, '2026-10-25T10:00', 'skipped', 2),  # not an outcome of the code
    run(ALPHA, 107, '2026-12-31T23:30', None, 10, status='in_progress'),  # 01-01 in Berlin
    run(ALPHA, 108, '2027-01-10T09:00', None, 0, status='queued', started=False),
    run(ALPHA, 109, '2027-01-12T10:00', 'timed_out', 30),
    run(ALPHA, 110, '2027-01-12T11:00', 'startup_failure', 0, started=False),
    run(ALPHA, 111, '2026-09-30T12:00', 'success', 3),  # before the range
    # beta
    run(BETA, 201, '2026-10-15T09:00', 'success', 4),
    run(BETA, 202, '2027-01-14T12:00', 'success', 20, workflow='deploy'),
    run(BETA, 203, '2027-01-31T23:30', 'success', 5),  # 02-01 in Berlin, after the range
    # gamma, owned by the user octocat
    run(GAMMA, 301, '2026-10-10T09:00', 'success', 5),
    run(GAMMA, 302, '2026-11-05T09:00', 'failure', 9),
]

# The org (alpha and beta) by month in UTC, the Actions and release series: metric -> label ->
# value, a month with no value left out. Checked by hand on 2026-10-30. Percentiles are as in
# ORG_FLOW_BY_MONTH_UTC: median, and (v[j] * (10 - d) + v[j + 1] * d) / 10 with
# j, d = divmod(9 * m, 10) for the 90th, m being the last index of the sorted values.
ORG_DELIVERY_BY_MONTH_UTC: dict[str, dict[str, float]] = {
    # by creation date. Oct: 101 102 103 104 105 106 201 (111 is on 09-30). Dec: 107.
    # Jan: 108 109 110 202 203
    'workflow_runs': {'2026-10': 7, '2026-11': 0, '2026-12': 1, '2027-01': 5},
    # completed runs that are a success, failure, timed_out or startup_failure.
    # Oct: 101 s, 102 f, 103 s, 105 s, 201 s (104 cancelled and 106 skipped are left out): 4 / 5.
    # Dec: 107 is in progress. Jan: 109 f, 110 f, 202 s, 203 s (108 is queued): 2 / 4
    'workflow_success_rate': {'2026-10': 4 / 5, '2027-01': 2 / 4},
    # completed runs that started, updated_at less run_started_at in minutes.
    # Oct [6, 10, 12, 1, 8, 2, 4] sorted [1, 2, 4, 6, 8, 10, 12]: p50 6, p90 (10 * 6 + 12 * 4) / 10
    # = 10.8. Jan 109 30, 202 20, 203 5 (110 never started) sorted [5, 20, 30]: p50 20,
    # p90 (20 * 2 + 30 * 8) / 10 = 28
    'workflow_duration_p50': {'2026-10': 6.0, '2027-01': 20.0},
    'workflow_duration_p90': {'2026-10': 10.8, '2027-01': 28.0},
    # by publication date, the prerelease included. Oct: v1.0.0 v1.1.0-rc1 v1.1.0 b1.0.
    # Dec: v1.2.0. Jan: b1.1 (v0.9.0 is on 09-20)
    'release_count': {'2026-10': 4, '2026-11': 0, '2026-12': 1, '2027-01': 1},
    # whole days since the repo's previous release, by the later one. alpha: v0.9.0 -> v1.0.0
    # 16 days 2 h; -> rc1 14 days; -> v1.1.0 4 days 22 h; -> v1.2.0 67 days 13 h 45 min.
    # beta: b1.0 -> b1.1 90 days 20 h. Oct [16, 14, 4]: median_low 14. Dec [67]. Jan [90]
    'release_interval_p50': {'2026-10': 14, '2026-12': 67, '2027-01': 90},
}

# In Europe/Berlin run 107 (23:30 UTC on 12-31) and v1.2.0 (23:45) are on 2027-01-01 and run 203
# (23:30 UTC on 01-31) is on 02-01, after the range. Jan runs: 107 108 109 110 202.
ORG_DELIVERY_BY_MONTH_BERLIN: dict[str, dict[str, float]] = {
    'workflow_runs': {'2026-10': 7, '2026-11': 0, '2026-12': 0, '2027-01': 5},
    # Jan 109 f, 110 f, 202 s: 1 / 3
    'workflow_success_rate': {'2026-10': 4 / 5, '2027-01': 1 / 3},
    # Jan [30, 20] sorted [20, 30]: p50 25, p90 (20 * 1 + 30 * 9) / 10 = 29
    'workflow_duration_p50': {'2026-10': 6.0, '2027-01': 25.0},
    'workflow_duration_p90': {'2026-10': 10.8, '2027-01': 29.0},
    'release_count': {'2026-10': 4, '2026-11': 0, '2026-12': 0, '2027-01': 2},  # v1.2.0 b1.1
    # Jan [67, 90]: median_low 67
    'release_interval_p50': {'2026-10': 14, '2027-01': 67},
}

# DORA proxies of the org by month in UTC, with the releases that are not prereleases as the
# deployments: v1.0.0, v1.1.0, v1.2.0, b1.0, b1.1 (and v0.9.0 before the range).
ORG_DORA_RELEASES_BY_MONTH_UTC: dict[str, dict[str, float]] = {
    'deployments': {'2026-10': 3, '2026-11': 0, '2026-12': 1, '2027-01': 1},  # v1.0.0 v1.1.0 b1.0
    # merged pull requests to the first later deployment of their repo, in hours, from the first
    # commit (the creation when there is none), by the deployment's date:
    # alpha-p1 10-04T10:00 -> v1.0.0 10-06T12:00: 50. alpha-p2 10-10T08:00 -> v1.1.0 (the rc is
    # not a deployment) 10-25T10:00: 362. alpha-p3 10-19T09:00 -> v1.1.0: 145. alpha-p5
    # 09-27T12:00 -> v1.0.0: 216. beta-p1 10-15T09:00 -> b1.0 10-15T16:00: 7.
    # alpha-p7 12-30T10:00 -> v1.2.0 12-31T23:45: 37.75. beta-p2 01-11T09:00 -> b1.1
    # 01-14T12:00: 75. alpha-p9 (merged 08-05) -> v0.9.0 on 09-20, before the range. alpha-p4 was
    # not merged, alpha-p6 and p8 are open and beta-p3 merged after the last deployment.
    # Oct [7, 50, 145, 216, 362]: p50 145, p90 (216 * 4 + 362 * 6) / 10 = 303.6
    'lead_time_p50': {'2026-10': 145.0, '2026-12': 37.75, '2027-01': 75.0},
    'lead_time_p90': {'2026-10': 303.6, '2026-12': 37.75, '2027-01': 75.0},
    # the hotfix pull requests are alpha-p2 (label Hotfix, opened 10-10T08:00) and beta-p3
    # (opened 01-30T09:00). v1.0.0 (10-06T12:00) is followed by alpha-p2 within 7 days; v1.1.0
    # and b1.0 are not (no later hotfix of their repo); v1.2.0 (window ends 01-07) and b1.1
    # (window ends 01-21) are followed by none: Oct 1 / 3, Dec 0 / 1, Jan 0 / 1
    'change_failure_rate': {'2026-10': 1 / 3, '2026-12': 0.0, '2027-01': 0.0},
    # hotfix pull requests, opened to merged, by merge date. alpha-p2 10-10T08:00 -> 10-12T08:00:
    # 48 in Oct. beta-p3 merges on 02-01, after the range
    'time_to_restore_p50': {'2026-10': 48.0},
    'time_to_restore_p90': {'2026-10': 48.0},
}

# In Berlin v1.2.0 is a deployment of 2027-01-01 (Jan: v1.2.0, b1.1), so alpha-p7's lead time
# moves to January: [37.75, 75], p50 56.375, p90 (37.75 * 1 + 75 * 9) / 10 = 71.275
ORG_DORA_RELEASES_BY_MONTH_BERLIN: dict[str, dict[str, float]] = {
    'deployments': {'2026-10': 3, '2026-11': 0, '2026-12': 0, '2027-01': 2},
    'lead_time_p50': {'2026-10': 145.0, '2027-01': 56.375},
    'lead_time_p90': {'2026-10': 303.6, '2027-01': 71.275},
    'change_failure_rate': {'2026-10': 1 / 3, '2027-01': 0.0},  # Jan 0 / 2
    'time_to_restore_p50': {'2026-10': 48.0},
    'time_to_restore_p90': {'2026-10': 48.0},
}

# With `deploy_workflow` set to deploy.yml (or Deploy), the deployments are the successful
# completed runs of that workflow, at updated_at: run 105 at 10-06T12:08 (alpha) and run 202 at
# 01-14T12:20 (beta).
ORG_DORA_WORKFLOW_BY_MONTH_UTC: dict[str, dict[str, float]] = {
    'deployments': {'2026-10': 1, '2026-11': 0, '2026-12': 0, '2027-01': 1},
    # alpha-p1 10-04T10:00 -> 10-06T12:08: 50 h 8 min. alpha-p5 09-27T12:00 -> 10-06T12:08:
    # 216 h 8 min. alpha-p9 08-01T09:00 -> 10-06T12:08: 66 days 3 h 8 min = 1587 h 8 min (no
    # earlier deployment). beta-p1 10-15T09:00 -> 01-14T12:20: 91 days 3 h 20 min = 2187 h 20 min.
    # beta-p2 01-11T09:00 -> 01-14T12:20: 75 h 20 min. alpha-p2, p3 and p7 merge after run 105 and
    # beta-p3 after run 202: no deployment follows them.
    # Oct [50.1333, 216.1333, 1587.1333]: p50 216.1333, p90 (216.1333 * 2 + 1587.1333 * 8) / 10
    # = 1312.9333. Jan [75.3333, 2187.3333]: p50 1131.3333, p90 (75.3333 + 2187.3333 * 9) / 10
    # = 1976.1333
    'lead_time_p50': {'2026-10': 216 + 8 / 60, '2027-01': (75 + 20 / 60 + 2187 + 20 / 60) / 2},
    'lead_time_p90': {
        '2026-10': ((216 + 8 / 60) * 2 + (1587 + 8 / 60) * 8) / 10,
        '2027-01': ((75 + 20 / 60) + (2187 + 20 / 60) * 9) / 10,
    },
    # run 105 is followed by alpha-p2 within 7 days: Oct 1 / 1. Run 202: Jan 0 / 1
    'change_failure_rate': {'2026-10': 1.0, '2027-01': 0.0},
    'time_to_restore_p50': {'2026-10': 48.0},
    'time_to_restore_p90': {'2026-10': 48.0},
}

# The user octocat's delivery over the whole range as one bucket, which counts every item of
# gamma whoever made it. Runs 301 s, 302 f: 1 / 2; minutes [5, 9]: p50 7, p90 (5 + 9 * 9) / 10
# = 8.6. One release, so no interval. gamma-p1 10-10T09:00 -> g1.0 10-12T12:00: 51 h; gamma-p2
# merges after it. No pull request has a hotfix label.
USER_DELIVERY_TOTAL_UTC: dict[str, float] = {
    'workflow_runs': 2,
    'workflow_success_rate': 0.5,
    'workflow_duration_p50': 7.0,
    'workflow_duration_p90': 8.6,
    'release_count': 1,
    'deployments': 1,
    'lead_time_p50': 51.0,
    'lead_time_p90': 51.0,
}

UNAVAILABLE_NO_HOTFIX: list[dict[str, str]] = [
    {
        'metric': metric,
        'reason': 'no pull request in the cache has a label in stats.hotfix_labels',
    }
    for metric in ('change_failure_rate', 'time_to_restore_p50', 'time_to_restore_p90')
]
