import dataclasses
import datetime
import zoneinfo

import hypothesis
import hypothesis.strategies as st
import pytest

import tests.fixtures.stats as fixture
import wambatic.fetch.base
import wambatic.settings
import wambatic.stats.activity
import wambatic.stats.base
import wambatic.stats.buckets

Granularity = wambatic.stats.base.Granularity
Series = wambatic.stats.base.Series
UTC = datetime.UTC
BERLIN = zoneinfo.ZoneInfo('Europe/Berlin')
SETTINGS = wambatic.settings.StatsSettings()
TOTALS = ('commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net')
BREAKDOWN = ('commits', 'lines_added', 'lines_deleted', 'lines_net')


def run(
    commits: list[wambatic.fetch.base.Commit] | None = None,
    granularity: Granularity = Granularity.MONTH,
    tz: datetime.tzinfo = UTC,
    settings: wambatic.settings.StatsSettings = SETTINGS,
    since: datetime.date = fixture.SINCE,
    until: datetime.date = fixture.UNTIL,
    *,
    by_author: bool = False,
    by_repo: bool = False,
) -> tuple[list[Series], dict[str, list[dict[str, object]]]]:
    buckets = wambatic.stats.buckets.bucket_range(since, until, granularity)
    return wambatic.stats.activity.aggregate(
        fixture.ORG_COMMITS if commits is None else commits,
        buckets,
        tz,
        settings,
        by_author=by_author,
        by_repo=by_repo,
    )


def pick(
    series: list[Series], metric: str, by: str | None = None, by_kind: str | None = None
) -> dict[str, float]:
    (found,) = [s for s in series if (s.metric, s.by, s.by_kind) == (metric, by, by_kind)]
    return {bucket.label: value for bucket, value in found.points.items()}


@pytest.mark.parametrize(
    ('tz', 'expected'),
    [(UTC, fixture.ORG_BY_MONTH_UTC), (BERLIN, fixture.ORG_BY_MONTH_BERLIN)],
)
def test_the_fixture_by_month_matches_the_hand_written_values(
    tz: datetime.tzinfo, expected: dict[str, dict[str, int]]
) -> None:
    series, _ = run(tz=tz)
    for metric in TOTALS:
        assert pick(series, metric) == {label: values[metric] for label, values in expected.items()}


@pytest.mark.parametrize(
    ('tz', 'expected'),
    [(UTC, fixture.ORG_TOTAL_UTC), (BERLIN, fixture.ORG_TOTAL_BERLIN)],
)
def test_the_fixture_as_one_bucket_matches_the_hand_written_totals(
    tz: datetime.tzinfo, expected: dict[str, int]
) -> None:
    series, _ = run(tz=tz, granularity=Granularity.TOTAL)
    for metric in TOTALS:
        assert pick(series, metric) == {'total': expected[metric]}


def test_series_come_in_the_specs_order_with_the_specs_units() -> None:
    series, _ = run()
    assert [(s.metric, s.unit) for s in series] == [
        ('commits', 'count'),
        ('contributors', 'count'),
        ('active_days', 'days'),
        ('lines_added', 'lines'),
        ('lines_deleted', 'lines'),
        ('lines_net', 'lines'),
    ]
    assert all(s.by is None and s.by_kind is None for s in series)


def test_an_empty_month_is_present_with_zeros() -> None:
    series, _ = run()
    for metric in TOTALS:
        assert pick(series, metric)['2026-11'] == 0
    assert all(list(s.points) == sorted(s.points) for s in series)


def test_merge_lines_are_added_when_the_setting_is_off() -> None:
    settings = dataclasses.replace(SETTINGS, exclude_merge_commits=False)
    series, _ = run(settings=settings)
    assert pick(series, 'lines_added')['2026-10'] == 173  # 73 + the merge's 100
    assert pick(series, 'lines_deleted')['2026-10'] == 89  # 39 + the merge's 50
    assert pick(series, 'lines_net')['2026-10'] == 84
    assert pick(series, 'commits')['2026-10'] == 7


def test_a_bot_counts_in_commits_and_lines_but_not_contributors() -> None:
    bot = [c for c in fixture.ORG_COMMITS if c.oid == 'b2']
    series, _ = run(bot)
    assert pick(series, 'commits')['2026-10'] == 1
    assert pick(series, 'lines_added')['2026-10'] == 30
    assert pick(series, 'contributors')['2026-10'] == 0
    assert pick(series, 'active_days')['2026-10'] == 1


def test_bot_logins_are_compared_case_insensitively() -> None:
    settings = dataclasses.replace(SETTINGS, bot_logins=('HUBOT',))
    series, _ = run(settings=settings)
    assert pick(series, 'contributors')['2026-12'] == 0


def test_two_spellings_of_a_login_are_one_contributor() -> None:
    octocats = [c for c in fixture.ORG_COMMITS if c.oid in ('a1', 'b1', 'a6')]
    assert {c.author_login for c in octocats} == {'Octocat', 'octocat'}
    series, _ = run(octocats)
    assert pick(series, 'contributors')['2026-10'] == 1
    assert pick(series, 'contributors')['2027-01'] == 1


def test_an_unattributed_commit_is_counted_but_is_no_contributor() -> None:
    series, _ = run([c for c in fixture.ORG_COMMITS if c.oid == 'b3'])
    assert pick(series, 'commits')['2026-10'] == 1
    assert pick(series, 'contributors')['2026-10'] == 0


def test_a_commit_outside_the_buckets_raises() -> None:
    early = fixture.commit(fixture.ALPHA, 'x', '2026-09-30T12:00', 'octocat', 1, 1)
    late = fixture.commit(fixture.ALPHA, 'y', '2027-02-01T00:00', 'octocat', 1, 1)
    with pytest.raises(ValueError, match='outside'):
        run([early])
    with pytest.raises(ValueError, match='outside'):
        run([late])


def test_the_local_date_decides_whether_a_commit_is_inside() -> None:
    edge = fixture.commit(fixture.ALPHA, 'x', '2026-09-30T23:30', 'octocat', 1, 1)
    series, _ = run([edge], tz=BERLIN)  # 2026-10-01 01:30 in Berlin
    assert pick(series, 'commits')['2026-10'] == 1


def test_no_commits_gives_zero_series_and_no_rows() -> None:
    series, tables = run([])
    assert pick(series, 'commits') == dict.fromkeys(fixture.LABELS, 0)
    assert tables == {'top_contributors': []}


# Breakdowns and top contributors


def test_the_per_repo_series_match_the_hand_written_values() -> None:
    series, _ = run(by_repo=True)
    for name, months in fixture.ORG_BY_REPO_UTC.items():
        for position, metric in enumerate(BREAKDOWN):
            assert pick(series, metric, name, 'repo') == {
                label: values[position] for label, values in months.items()
            }


def test_the_per_author_series_match_the_hand_written_values() -> None:
    series, _ = run(by_author=True)
    for login, months in fixture.ORG_BY_AUTHOR_UTC.items():
        for position, metric in enumerate(BREAKDOWN):
            assert pick(series, metric, login, 'author') == {
                label: values[position] for label, values in months.items()
            }


def test_octocat_in_two_cases_shares_one_series_named_for_the_first_spelling() -> None:
    series, _ = run(by_author=True)
    logins = {s.by for s in series if s.by_kind == 'author'}
    assert 'Octocat' in logins
    assert 'octocat' not in logins


def test_the_unattributed_commit_and_a_bot_have_series() -> None:
    series, _ = run(by_author=True)
    logins = {s.by for s in series if s.by_kind == 'author'}
    assert {'unattributed', 'dependabot[bot]'} <= logins


def test_the_top_contributors_match_the_hand_written_rows() -> None:
    for tz in (UTC, BERLIN):
        _, tables = run(tz=tz)
        assert tables['top_contributors'] == fixture.ORG_TOP_CONTRIBUTORS


def test_top_contributors_leave_out_the_bot_and_keep_unattributed() -> None:
    _, tables = run()
    logins = [row['login'] for row in tables['top_contributors']]
    assert 'dependabot[bot]' not in logins
    assert logins.count('unattributed') == 1
    assert logins.count('Octocat') == 1
    assert 'octocat' not in logins


def test_top_contributors_are_the_same_with_or_without_breakdowns() -> None:
    _, plain = run()
    _, broken_down = run(by_author=True, by_repo=True)
    assert plain == broken_down


def test_without_the_flags_there_are_no_breakdown_series() -> None:
    series, _ = run()
    assert not [s for s in series if s.by_kind is not None]
    only_repo, _ = run(by_repo=True)
    assert {s.by_kind for s in only_repo} == {None, 'repo'}
    only_author, _ = run(by_author=True)
    assert {s.by_kind for s in only_author} == {None, 'author'}


def test_breakdown_series_are_ordered_by_kind_then_by_then_metric() -> None:
    series, _ = run(by_author=True, by_repo=True)
    keys = [(s.by_kind, s.by, s.metric) for s in series if s.by_kind is not None]
    expected = [
        (kind, by, metric)
        for kind, by in (
            [('author', login) for login in sorted(fixture.ORG_BY_AUTHOR_UTC)]
            + [('repo', name) for name in sorted(fixture.ORG_BY_REPO_UTC)]
        )
        for metric in BREAKDOWN
    ]
    assert keys == expected
    assert [s.metric for s in series[:6]] == list(TOTALS)


def test_the_same_commits_give_the_same_series_order() -> None:
    first, _ = run(by_author=True, by_repo=True)
    second, _ = run(list(fixture.ORG_COMMITS), by_author=True, by_repo=True)
    assert [(s.metric, s.by, s.by_kind) for s in first] == [
        (s.metric, s.by, s.by_kind) for s in second
    ]


def test_the_spelling_is_the_first_seen_in_the_order_given() -> None:
    series, tables = run(list(reversed(fixture.ORG_COMMITS)), by_author=True)
    logins = {s.by for s in series if s.by_kind == 'author'}
    assert 'octocat' in logins
    assert 'Octocat' not in logins
    assert 'octocat' in [row['login'] for row in tables['top_contributors']]


def test_ties_in_top_contributors_are_ordered_by_login() -> None:
    commits = [
        fixture.commit(fixture.ALPHA, 'x', '2026-10-05T10:00', 'zed', 1, 0),
        fixture.commit(fixture.ALPHA, 'y', '2026-10-06T10:00', 'amy', 1, 0),
    ]
    _, tables = run(commits)
    assert [row['login'] for row in tables['top_contributors']] == ['amy', 'zed']


# Properties

LOGINS = st.sampled_from(['Octocat', 'octocat', 'hubot', 'dependabot[bot]', None])
REPO_NAMES = st.sampled_from([fixture.ALPHA, fixture.BETA])


@st.composite
def commit_lists(draw: st.DrawFn) -> list[wambatic.fetch.base.Commit]:
    commits = []
    for n in range(draw(st.integers(0, 25))):
        when = draw(
            st.datetimes(
                min_value=datetime.datetime(2026, 1, 1),
                max_value=datetime.datetime(2026, 12, 31, 23, 59),
            )
        )
        commits.append(
            wambatic.fetch.base.Commit(
                repo=draw(REPO_NAMES),
                oid=f'c{n}',
                authored_at=when.replace(tzinfo=UTC),
                author_login=draw(LOGINS),
                additions=draw(st.integers(0, 1000)),
                deletions=draw(st.integers(0, 1000)),
                is_merge=draw(st.booleans()),
            )
        )
    return commits


YEAR = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(commit_lists(), st.sampled_from(list(Granularity)))
def test_totals_agree_with_a_direct_sum(
    commits: list[wambatic.fetch.base.Commit], granularity: Granularity
) -> None:
    series, _ = run(commits, granularity, since=YEAR[0], until=YEAR[1])
    commit_points = pick(series, 'commits')
    assert sum(commit_points.values()) == len(commits)
    assert sum(pick(series, 'lines_added').values()) == sum(
        c.additions for c in commits if not c.is_merge
    )
    assert sum(pick(series, 'lines_deleted').values()) == sum(
        c.deletions for c in commits if not c.is_merge
    )
    added, deleted = pick(series, 'lines_added'), pick(series, 'lines_deleted')
    net = pick(series, 'lines_net')
    for label, count in commit_points.items():
        assert net[label] == added[label] - deleted[label]
        assert pick(series, 'contributors')[label] <= count
        assert pick(series, 'active_days')[label] <= count


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(commit_lists(), st.sampled_from(list(Granularity)))
def test_breakdowns_sum_to_the_totals(
    commits: list[wambatic.fetch.base.Commit], granularity: Granularity
) -> None:
    series, _ = run(
        commits, granularity, since=YEAR[0], until=YEAR[1], by_author=True, by_repo=True
    )
    for kind in ('author', 'repo'):
        parts = [s for s in series if s.by_kind == kind]
        for metric in BREAKDOWN:
            total = pick(series, metric)
            summed = dict.fromkeys(total, 0.0)
            for part in parts:
                if part.metric == metric:
                    assert list(part.points) == list(total_buckets(series, metric))
                    for bucket, value in part.points.items():
                        summed[bucket.label] += value
            assert summed == total


def total_buckets(series: list[Series], metric: str) -> list[wambatic.stats.base.Bucket]:
    (found,) = [s for s in series if s.metric == metric and s.by is None]
    return list(found.points)
