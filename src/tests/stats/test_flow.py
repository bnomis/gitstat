import datetime
import zoneinfo

import hypothesis
import hypothesis.strategies as st
import pytest

import tests.fixtures.stats as fixture
import wambatic.fetch.base
import wambatic.stats.base
import wambatic.stats.buckets
import wambatic.stats.flow

Granularity = wambatic.stats.base.Granularity
Series = wambatic.stats.base.Series
UTC = datetime.UTC
BERLIN = zoneinfo.ZoneInfo('Europe/Berlin')
ORG_PULLS = [p for p in fixture.PULL_REQUESTS if p.repo != fixture.GAMMA]
ORG_ISSUES = [i for i in fixture.ISSUES if i.repo != fixture.GAMMA]
UNITS = {
    'count': {'prs_opened', 'prs_merged', 'issues_opened', 'issues_closed'},
    'hours': {
        'time_to_first_review_p50',
        'time_to_first_review_p90',
        'time_to_merge_p50',
        'time_to_merge_p90',
        'time_to_close_p50',
        'time_to_close_p90',
    },
    'lines': {'pr_size_p50'},
}


def run(
    pulls: list[wambatic.fetch.base.PullRequest] | None = None,
    issues: list[wambatic.fetch.base.Issue] | None = None,
    granularity: Granularity = Granularity.MONTH,
    tz: datetime.tzinfo = UTC,
    since: datetime.date = fixture.SINCE,
    until: datetime.date = fixture.UNTIL,
) -> list[Series]:
    buckets = wambatic.stats.buckets.bucket_range(since, until, granularity)
    return wambatic.stats.flow.aggregate(
        ORG_PULLS if pulls is None else pulls,
        ORG_ISSUES if issues is None else issues,
        buckets,
        tz,
        since,
        until,
    )


def pick(series: list[Series], metric: str) -> dict[str, float]:
    (found,) = [s for s in series if s.metric == metric]
    return {bucket.label: value for bucket, value in found.points.items()}


def pull(created: str, **changes: str | None) -> wambatic.fetch.base.PullRequest:
    return fixture.pull(fixture.ALPHA, 1, 'octocat', created, **changes)  # type: ignore[arg-type]


def test_the_fixture_by_month_in_utc_matches_the_hand_written_values() -> None:
    series = run()
    for metric, expected in fixture.ORG_FLOW_BY_MONTH_UTC.items():
        assert pick(series, metric) == pytest.approx(expected), metric


def test_the_fixture_by_month_in_berlin_moves_only_what_the_late_merge_moves() -> None:
    series = run(tz=BERLIN)
    for metric, expected in fixture.ORG_FLOW_BY_MONTH_UTC.items():
        expected = fixture.ORG_FLOW_BY_MONTH_BERLIN.get(metric, expected)
        assert pick(series, metric) == pytest.approx(expected), metric


def test_the_user_fixture_as_one_bucket_matches_the_hand_written_values() -> None:
    own_pulls = [p for p in fixture.PULL_REQUESTS if p.repo == fixture.GAMMA][:1]
    own_issues = [i for i in fixture.ISSUES if i.repo == fixture.GAMMA][:1]
    series = run(own_pulls, own_issues, Granularity.TOTAL)
    for metric, expected in fixture.USER_FLOW_TOTAL_UTC.items():
        assert pick(series, metric) == pytest.approx({'total': expected}), metric


def test_total_gives_one_bucket_whose_counts_equal_the_events_in_range() -> None:
    series = run(granularity=Granularity.TOTAL)
    assert pick(series, 'prs_opened') == {'total': 10}  # 5 + 1 + 1 + 3
    assert pick(series, 'prs_merged') == {'total': 7}  # 5 + 0 + 1 + 1
    assert pick(series, 'issues_opened') == {'total': 5}
    assert pick(series, 'issues_closed') == {'total': 4}
    assert sum(len(s.points) for s in series if s.metric == 'time_to_merge_p50') == 1


def test_series_come_in_flow_metrics_order_with_the_listed_units() -> None:
    series = run()
    assert [(s.metric, s.unit) for s in series] == list(wambatic.stats.flow.FLOW_METRICS)
    for unit, metrics in UNITS.items():
        assert {s.metric for s in series if s.unit == unit} == metrics
    assert all(s.by is None and s.by_kind is None for s in series)


def test_a_closed_unmerged_pull_request_is_in_prs_opened_only() -> None:
    closed = pull('2026-10-25T09:00', closed='2026-10-26T09:00')
    series = run([closed], [])
    assert pick(series, 'prs_opened')['2026-10'] == 1
    assert sum(pick(series, 'prs_merged').values()) == 0
    for metric in UNITS['hours'] | UNITS['lines']:
        assert pick(series, metric) == {}


def test_a_reopened_issue_is_not_closed_and_has_no_time_to_close() -> None:
    reopened = fixture.issue(fixture.ALPHA, 1, 'octocat', '2026-10-07T09:00')
    series = run([], [reopened])
    assert pick(series, 'issues_opened')['2026-10'] == 1
    assert sum(pick(series, 'issues_closed').values()) == 0
    assert pick(series, 'time_to_close_p50') == {}


def test_a_pull_request_with_no_review_is_merged_but_has_no_time_to_first_review() -> None:
    merged = pull('2026-10-15T09:00', merged='2026-10-15T15:00')
    series = run([merged], [])
    assert pick(series, 'prs_merged')['2026-10'] == 1
    assert pick(series, 'time_to_first_review_p50') == {}
    assert pick(series, 'time_to_merge_p50') == {'2026-10': 6.0}


def test_one_value_gives_the_same_p50_and_p90() -> None:
    merged = pull('2026-10-15T09:00', merged='2026-10-17T09:00', review='2026-10-15T10:00')
    series = run([merged], [])
    assert (
        pick(series, 'time_to_merge_p50') == pick(series, 'time_to_merge_p90') == {'2026-10': 48.0}
    )
    assert pick(series, 'time_to_first_review_p50') == pick(series, 'time_to_first_review_p90')


def test_events_outside_the_range_are_ignored_but_the_others_of_the_item_count() -> None:
    created_early = pull('2026-09-30T12:00', review='2026-10-01T12:00', merged='2026-10-02T12:00')
    merged_late = pull('2027-01-30T09:00', review='2027-01-31T09:00', merged='2027-02-01T08:00')
    series = run([created_early, merged_late], [])
    assert pick(series, 'prs_opened') == {'2026-10': 0, '2026-11': 0, '2026-12': 0, '2027-01': 1}
    assert pick(series, 'prs_merged') == {'2026-10': 1, '2026-11': 0, '2026-12': 0, '2027-01': 0}
    assert pick(series, 'time_to_first_review_p50') == {'2026-10': 24.0, '2027-01': 24.0}
    assert pick(series, 'time_to_merge_p50') == {'2026-10': 48.0}


def test_an_event_after_until_in_the_last_partial_bucket_is_ignored() -> None:
    merged = pull('2027-01-02T09:00', merged='2027-01-25T09:00')
    until = datetime.date(2027, 1, 20)
    series = run([merged], [], since=datetime.date(2027, 1, 1), until=until)
    assert pick(series, 'prs_opened') == {'2027-01': 1}
    assert pick(series, 'prs_merged') == {'2027-01': 0}


def test_an_event_after_until_does_not_land_in_the_total_bucket() -> None:
    merged = pull('2027-01-02T09:00', merged='2027-01-25T09:00')
    series = run([merged], [], Granularity.TOTAL, until=datetime.date(2027, 1, 20))
    assert pick(series, 'prs_merged') == {'total': 0}
    assert pick(series, 'time_to_merge_p50') == {}


def test_a_week_bucket_holds_the_events_of_its_local_dates() -> None:
    merged = pull('2026-12-28T09:00', merged='2026-12-31T23:30')
    series = run([merged], [], Granularity.WEEK, since=datetime.date(2026, 12, 28))
    assert pick(series, 'prs_merged')['2026-W53'] == 1
    berlin = run([merged], [], Granularity.WEEK, BERLIN, since=datetime.date(2026, 12, 28))
    assert pick(berlin, 'prs_merged')['2026-W53'] == 1  # 2027-01-01 is still ISO week 53
    assert pick(berlin, 'prs_merged').get('2027-W01', 0) == 0


# Properties

TIMES = st.datetimes(
    min_value=datetime.datetime(2026, 1, 1), max_value=datetime.datetime(2026, 12, 31, 12, 0)
)
YEAR = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))


@st.composite
def pull_lists(draw: st.DrawFn) -> list[wambatic.fetch.base.PullRequest]:
    pulls = []
    for number in range(draw(st.integers(0, 20))):
        created = draw(TIMES).replace(tzinfo=UTC)
        review = created + datetime.timedelta(hours=draw(st.integers(0, 500)))
        merged = review + datetime.timedelta(hours=draw(st.integers(0, 500)))
        pulls.append(
            wambatic.fetch.base.PullRequest(
                repo=fixture.ALPHA,
                number=number,
                author_login='octocat',
                created_at=created,
                updated_at=merged,
                merged_at=merged if draw(st.booleans()) else None,
                closed_at=None,
                first_review_at=review if draw(st.booleans()) else None,
                additions=draw(st.integers(0, 500)),
                deletions=draw(st.integers(0, 500)),
            )
        )
    return pulls


def in_year(moment: datetime.datetime | None) -> bool:
    return moment is not None and moment.year == 2026


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(pull_lists(), st.sampled_from(list(Granularity)))
def test_each_count_summed_over_the_buckets_equals_its_events_in_range(
    pulls: list[wambatic.fetch.base.PullRequest], granularity: Granularity
) -> None:
    series = run(pulls, [], granularity, since=YEAR[0], until=YEAR[1])
    assert sum(pick(series, 'prs_opened').values()) == sum(in_year(p.created_at) for p in pulls)
    assert sum(pick(series, 'prs_merged').values()) == sum(in_year(p.merged_at) for p in pulls)


def bucket_of(
    moment: datetime.datetime | None, granularity: Granularity
) -> wambatic.stats.base.Bucket | None:
    """The bucket holding `moment` in the year-long range, or None outside it."""
    if moment is None or not in_year(moment):
        return None
    if granularity is Granularity.TOTAL:
        return wambatic.stats.base.Bucket(YEAR[0], 'total')
    return wambatic.stats.buckets.bucket_for(moment, granularity, UTC)


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(pull_lists(), st.sampled_from(list(Granularity)))
def test_every_duration_point_lies_between_the_minimum_and_maximum_of_its_bucket(
    pulls: list[wambatic.fetch.base.PullRequest], granularity: Granularity
) -> None:
    series = run(pulls, [], granularity, since=YEAR[0], until=YEAR[1])
    buckets = wambatic.stats.buckets.bucket_range(YEAR[0], YEAR[1], granularity)
    for label, end in (('time_to_merge', 'merged_at'), ('time_to_first_review', 'first_review_at')):
        p50, p90 = pick(series, f'{label}_p50'), pick(series, f'{label}_p90')
        assert p50.keys() == p90.keys()
        for bucket in buckets:
            values = [
                wambatic.stats.flow.hours(p.created_at, getattr(p, end))
                for p in pulls
                if bucket_of(getattr(p, end), granularity) == bucket
            ]
            if not values:
                assert bucket.label not in p50
                continue
            assert min(values) <= p50[bucket.label] <= p90[bucket.label] <= max(values)


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(pull_lists(), st.sampled_from(list(Granularity)))
def test_pr_size_p50_is_always_one_of_the_sizes(
    pulls: list[wambatic.fetch.base.PullRequest], granularity: Granularity
) -> None:
    sizes = {p.additions + p.deletions for p in pulls if p.merged_at is not None}
    series = run(pulls, [], granularity, since=YEAR[0], until=YEAR[1])
    assert set(pick(series, 'pr_size_p50').values()) <= sizes
