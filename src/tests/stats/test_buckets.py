import datetime
import zoneinfo

import hypothesis
import hypothesis.strategies as st
import pytest

import gitstat.stats.base
import gitstat.stats.buckets

Granularity = gitstat.stats.base.Granularity
Bucket = gitstat.stats.base.Bucket
GRANULARITIES = [g for g in Granularity if g is not Granularity.TOTAL]
UTC = datetime.UTC
BERLIN = zoneinfo.ZoneInfo('Europe/Berlin')
LONDON = zoneinfo.ZoneInfo('Europe/London')


def date(text: str) -> datetime.date:
    return datetime.date.fromisoformat(text)


def utc(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ('granularity', 'start', 'label'),
    [
        (Granularity.YEAR, '2026-01-01', '2026'),
        (Granularity.MONTH, '2026-10-01', '2026-10'),
        (Granularity.WEEK, '2026-10-26', '2026-W44'),
        (Granularity.DAY, '2026-10-29', '2026-10-29'),
    ],
)
def test_labels_of_each_granularity(granularity: Granularity, start: str, label: str) -> None:
    bucket = gitstat.stats.buckets.bucket_for(utc(2026, 10, 29), granularity, UTC)
    assert bucket == Bucket(date(start), label)


@pytest.mark.parametrize(
    ('day', 'week_label', 'week_start'),
    [
        ('2026-12-31', '2026-W53', '2026-12-28'),
        ('2027-01-01', '2026-W53', '2026-12-28'),
        ('2027-01-04', '2027-W01', '2027-01-04'),
        ('2025-12-29', '2026-W01', '2025-12-29'),
    ],
)
def test_a_week_is_labelled_with_its_iso_year(day: str, week_label: str, week_start: str) -> None:
    when = datetime.datetime.combine(date(day), datetime.time(12), tzinfo=UTC)
    bucket = gitstat.stats.buckets.bucket_for(when, Granularity.WEEK, UTC)
    assert bucket == Bucket(date(week_start), week_label)


def test_a_commit_late_on_new_years_eve_is_january_in_berlin() -> None:
    when = utc(2026, 12, 31, 23, 30)
    assert gitstat.stats.buckets.bucket_for(when, Granularity.MONTH, UTC).label == '2026-12'
    assert gitstat.stats.buckets.bucket_for(when, Granularity.MONTH, BERLIN).label == '2027-01'


def test_a_commit_after_the_clocks_go_forward_in_london_is_on_the_next_date() -> None:
    summer = utc(2026, 3, 29, 23, 30)
    winter = utc(2026, 3, 28, 23, 30)
    assert gitstat.stats.buckets.bucket_for(summer, Granularity.DAY, LONDON).label == '2026-03-30'
    assert gitstat.stats.buckets.bucket_for(winter, Granularity.DAY, LONDON).label == '2026-03-28'


def test_bucket_for_rejects_total_and_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match='total'):
        gitstat.stats.buckets.bucket_for(utc(2026, 10, 1), Granularity.TOTAL, UTC)
    with pytest.raises(ValueError, match='aware'):
        gitstat.stats.buckets.bucket_for(datetime.datetime(2026, 10, 1), Granularity.MONTH, UTC)


def test_bucket_range_of_total_is_one_bucket() -> None:
    assert gitstat.stats.buckets.bucket_range(
        date('2026-10-03'), date('2027-02-01'), Granularity.TOTAL
    ) == [Bucket(date('2026-10-03'), 'total')]


def test_bucket_range_rejects_since_after_until() -> None:
    with pytest.raises(ValueError, match='after'):
        gitstat.stats.buckets.bucket_range(date('2026-10-02'), date('2026-10-01'), Granularity.DAY)


def test_bucket_range_across_a_year_boundary_by_month() -> None:
    buckets = gitstat.stats.buckets.bucket_range(
        date('2026-11-15'), date('2027-01-02'), Granularity.MONTH
    )
    assert [b.label for b in buckets] == ['2026-11', '2026-12', '2027-01']


def test_bucket_range_by_week_includes_the_iso_year_week() -> None:
    buckets = gitstat.stats.buckets.bucket_range(
        date('2026-12-28'), date('2027-01-04'), Granularity.WEEK
    )
    assert [b.label for b in buckets] == ['2026-W53', '2027-W01']


def test_a_one_day_range_at_year_granularity_is_one_partial_bucket() -> None:
    since = until = date('2026-10-29')
    buckets = gitstat.stats.buckets.bucket_range(since, until, Granularity.YEAR)
    assert gitstat.stats.buckets.partial_buckets(since, until, buckets) == buckets
    assert len(buckets) == 1


def test_a_range_of_whole_months_has_no_partial_bucket() -> None:
    since, until = date('2026-10-01'), date('2026-12-31')
    buckets = gitstat.stats.buckets.bucket_range(since, until, Granularity.MONTH)
    assert gitstat.stats.buckets.partial_buckets(since, until, buckets) == []


def test_partial_buckets_names_the_first_and_the_last() -> None:
    since, until = date('2026-10-15'), date('2026-12-10')
    buckets = gitstat.stats.buckets.bucket_range(since, until, Granularity.MONTH)
    assert gitstat.stats.buckets.partial_buckets(since, until, buckets) == [
        buckets[0],
        buckets[-1],
    ]


def test_partial_buckets_names_only_the_first_when_only_it_is_cut() -> None:
    since, until = date('2026-10-15'), date('2026-12-31')
    buckets = gitstat.stats.buckets.bucket_range(since, until, Granularity.MONTH)
    assert gitstat.stats.buckets.partial_buckets(since, until, buckets) == [buckets[0]]


def test_partial_buckets_of_total_is_empty() -> None:
    since, until = date('2026-10-15'), date('2026-10-20')
    buckets = gitstat.stats.buckets.bucket_range(since, until, Granularity.TOTAL)
    assert gitstat.stats.buckets.partial_buckets(since, until, buckets) == []


def test_partial_weeks() -> None:
    since, until = date('2026-10-28'), date('2026-11-01')
    buckets = gitstat.stats.buckets.bucket_range(since, until, Granularity.WEEK)
    assert gitstat.stats.buckets.partial_buckets(since, until, buckets) == [buckets[0]]


DATES = st.dates(min_value=date('1971-01-01'), max_value=date('2100-12-31'))


@st.composite
def ranges(draw: st.DrawFn) -> tuple[datetime.date, datetime.date]:
    first, second = sorted([draw(DATES), draw(DATES)])
    return first, second


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(ranges(), st.sampled_from(GRANULARITIES), st.data())
def test_buckets_partition_any_range(
    span: tuple[datetime.date, datetime.date], granularity: Granularity, data: st.DataObject
) -> None:
    since, until = span
    buckets = gitstat.stats.buckets.bucket_range(since, until, granularity)
    for a, b in zip(buckets, buckets[1:], strict=False):
        assert gitstat.stats.buckets.next_start(a.start, granularity) == b.start
    first, last = buckets[0], buckets[-1]
    assert first.start <= since < gitstat.stats.buckets.next_start(first.start, granularity)
    assert last.start <= until < gitstat.stats.buckets.next_start(last.start, granularity)
    assert len({b.label for b in buckets}) == len(buckets)
    assert [b.label for b in buckets] == [b.label for b in sorted(buckets, key=lambda b: b.start)]
    span_days = (until - since).days
    sample = [since, until] + [
        since + datetime.timedelta(days=data.draw(st.integers(0, span_days))) for _ in range(5)
    ]
    for day in sample:
        noon = datetime.datetime.combine(day, datetime.time(12), tzinfo=UTC)
        found = gitstat.stats.buckets.bucket_for(noon, granularity, UTC)
        containing = [
            b
            for b in buckets
            if b.start <= day < gitstat.stats.buckets.next_start(b.start, granularity)
        ]
        assert containing == [found]


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(
    st.datetimes(
        min_value=datetime.datetime(1971, 1, 2),
        max_value=datetime.datetime(2100, 12, 30),
        timezones=st.timezones(),
    ),
    st.timezones(),
    st.sampled_from(GRANULARITIES),
)
def test_bucket_for_contains_the_local_date(
    when: datetime.datetime, tz: datetime.tzinfo, granularity: Granularity
) -> None:
    bucket = gitstat.stats.buckets.bucket_for(when, granularity, tz)
    local = when.astimezone(tz).date()
    assert bucket.start <= local < gitstat.stats.buckets.next_start(bucket.start, granularity)
