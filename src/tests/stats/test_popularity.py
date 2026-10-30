import datetime
import zoneinfo

import hypothesis
import hypothesis.strategies as st
import pytest

import tests.fixtures.stats as fixture
import wambatic.fetch.base
import wambatic.stats.base
import wambatic.stats.buckets
import wambatic.stats.popularity

Granularity = wambatic.stats.base.Granularity
Series = wambatic.stats.base.Series
UTC = datetime.UTC
BERLIN = zoneinfo.ZoneInfo('Europe/Berlin')
ORG = {fixture.ALPHA, fixture.BETA}
ORG_STARS = [s for s in fixture.STAR_EVENTS if s.repo in ORG]
ORG_FORKS = [f for f in fixture.FORKS if f.repo in ORG]
ORG_REPOS = [r for r in fixture.REPOS if r.name_with_owner in ORG]
METRICS = ['stars_added', 'stars_total', 'forks_added', 'forks_total']


def run(
    stars: list[wambatic.fetch.base.StarEvent] | None = None,
    forks: list[wambatic.fetch.base.Fork] | None = None,
    repos: list[wambatic.fetch.base.Repo] | None = None,
    granularity: Granularity = Granularity.MONTH,
    tz: datetime.tzinfo = UTC,
    since: datetime.date = fixture.SINCE,
    until: datetime.date = fixture.UNTIL,
) -> tuple[list[Series], dict[str, list[dict[str, object]]]]:
    buckets = wambatic.stats.buckets.bucket_range(since, until, granularity)
    return wambatic.stats.popularity.aggregate(
        ORG_STARS if stars is None else stars,
        ORG_FORKS if forks is None else forks,
        ORG_REPOS if repos is None else repos,
        buckets,
        tz,
        since,
        until,
    )


def pick(series: list[Series], metric: str) -> dict[str, float]:
    (found,) = [s for s in series if s.metric == metric]
    return {bucket.label: value for bucket, value in found.points.items()}


def check(series: list[Series], expected: dict[str, dict[str, float]]) -> None:
    for metric in METRICS:
        assert pick(series, metric) == {
            label: values[metric] for label, values in expected.items()
        }, metric


def test_the_fixture_by_month_in_utc_matches_the_hand_written_values() -> None:
    series, _ = run()
    check(series, fixture.ORG_POPULARITY_BY_MONTH_UTC)


def test_the_fixture_by_month_in_berlin_moves_the_star_at_midnight_into_january() -> None:
    series, _ = run(tz=BERLIN)
    check(series, fixture.ORG_POPULARITY_BY_MONTH_BERLIN)


def test_the_user_fixture_counts_every_star_and_fork_of_its_repo() -> None:
    gamma = [r for r in fixture.REPOS if r.name_with_owner == fixture.GAMMA]
    stars = [s for s in fixture.STAR_EVENTS if s.repo == fixture.GAMMA]
    forks = [f for f in fixture.FORKS if f.repo == fixture.GAMMA]
    series, _ = run(stars, forks, gamma)
    check(series, fixture.USER_POPULARITY_BY_MONTH_UTC)


def test_series_come_in_the_listed_order_with_unit_count_and_whole_numbers() -> None:
    series, _ = run()
    assert [(s.metric, s.unit) for s in series] == [(name, 'count') for name in METRICS]
    assert all(s.by is None and s.by_kind is None for s in series)
    assert all(isinstance(value, int) for s in series for value in s.points.values())


def test_the_total_bucket_gives_the_counts_over_the_range_and_the_totals_at_until() -> None:
    for (tz,) in ((UTC,), (BERLIN,)):
        series, _ = run(granularity=Granularity.TOTAL, tz=tz)
        for metric in METRICS:
            assert list(pick(series, metric)) == ['total']
            assert pick(series, metric)['total'] == fixture.ORG_POPULARITY_TOTAL[metric]


def test_events_after_until_count_in_nothing_and_events_before_since_only_in_the_totals() -> None:
    series, _ = run(since=datetime.date(2026, 11, 1), until=datetime.date(2026, 11, 30))
    assert pick(series, 'stars_added') == {'2026-11': 0}
    assert pick(series, 'stars_total') == {'2026-11': 5}  # a1 b1 a2 a3 b2
    assert pick(series, 'forks_added') == {'2026-11': 1}
    assert pick(series, 'forks_total') == {'2026-11': 3}  # 1001 1002 1003


def test_the_tables_match_the_hand_written_values() -> None:
    _, tables = run()
    assert tables['popularity'] == fixture.ORG_POPULARITY_TABLE
    languages = tables['languages']
    assert [(row['language'], row['bytes']) for row in languages] == [
        (row['language'], row['bytes']) for row in fixture.ORG_LANGUAGES_TABLE
    ]
    assert [row['share'] for row in languages] == pytest.approx(
        [row['share'] for row in fixture.ORG_LANGUAGES_TABLE]
    )


def test_a_user_with_no_language_has_an_empty_languages_table() -> None:
    gamma = [r for r in fixture.REPOS if r.name_with_owner == fixture.GAMMA]
    _, tables = run([], [], gamma)
    assert tables['languages'] == []
    assert tables['popularity'] == fixture.USER_POPULARITY_TABLE


def test_other_is_left_out_when_the_listed_languages_cover_the_size_and_is_last_when_biggest() -> (
    None
):
    covered = wambatic.fetch.base.Repo(
        'o/a', None, None, False, False, None, fixture.NOW, languages=(('C', 5),), languages_size=5
    )
    _, tables = run([], [], [covered])
    assert [row['language'] for row in tables['languages']] == ['C']
    huge = wambatic.fetch.base.Repo(
        'o/b',
        None,
        None,
        False,
        False,
        None,
        fixture.NOW,
        languages=(('C', 5),),
        languages_size=500,
    )
    _, tables = run([], [], [huge])
    assert [row['language'] for row in tables['languages']] == ['C', 'Other']
    assert tables['languages'][1]['share'] == pytest.approx(495 / 500)


def test_the_popularity_table_is_ordered_by_stars_then_name() -> None:
    def repo(name: str, stars: int) -> wambatic.fetch.base.Repo:
        return wambatic.fetch.base.Repo(
            name, None, None, False, False, None, fixture.NOW, stargazer_count=stars
        )

    _, tables = run([], [], [repo('o/b', 2), repo('o/a', 2), repo('o/c', 9)])
    assert [row['repo'] for row in tables['popularity']] == ['o/c', 'o/a', 'o/b']


def test_has_event_in_range_uses_local_dates() -> None:
    star = fixture.star(fixture.ALPHA, 'U_x', '2026-12-31T23:30')
    in_utc = wambatic.stats.popularity.has_event_in_range
    december = (datetime.date(2026, 12, 1), datetime.date(2026, 12, 31))
    assert in_utc([star], [], UTC, *december) is True
    assert in_utc([star], [], BERLIN, *december) is False
    assert in_utc([], [], UTC, *december) is False
    fork = fixture.fork(fixture.ALPHA, 1, '2026-12-05T10:00')
    assert in_utc([], [fork], UTC, *december) is True


TIMES = st.datetimes(
    min_value=datetime.datetime(2025, 6, 1), max_value=datetime.datetime(2027, 6, 1)
).map(lambda t: t.replace(tzinfo=UTC))
YEAR = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(
    st.lists(TIMES, max_size=40),
    st.sampled_from(list(Granularity)),
    st.sampled_from([UTC, BERLIN]),
)
def test_added_sums_to_the_stars_in_range_and_the_total_never_falls_to_the_stars_until(
    moments: list[datetime.datetime], granularity: Granularity, tz: datetime.tzinfo
) -> None:
    stars = [
        wambatic.fetch.base.StarEvent('o/a', f'U_{n}', moment) for n, moment in enumerate(moments)
    ]
    series, _ = run(stars, [], [], granularity, tz, *YEAR)
    local = [moment.astimezone(tz).date() for moment in moments]
    added = pick(series, 'stars_added')
    totals = list(pick(series, 'stars_total').values())
    assert sum(added.values()) == sum(1 for day in local if YEAR[0] <= day <= YEAR[1])
    assert totals == sorted(totals)
    assert totals[-1] == sum(1 for day in local if day <= YEAR[1])
