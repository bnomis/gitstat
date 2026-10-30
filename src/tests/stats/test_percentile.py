import datetime
import statistics

import hypothesis
import hypothesis.strategies as st
import pytest

import wambatic.stats.percentile

UTC = datetime.UTC


def test_hours_is_the_elapsed_time_in_hours() -> None:
    start = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    assert wambatic.stats.percentile.hours(start, start + datetime.timedelta(minutes=90)) == 1.5


def test_p90_accepts_a_single_value_and_interpolates_between_two() -> None:
    assert wambatic.stats.percentile.p90([7.0]) == 7.0
    assert wambatic.stats.percentile.p90([1.0, 24.0]) == pytest.approx(21.7)


def test_the_summary_follows_the_suffix() -> None:
    assert wambatic.stats.percentile.summary('p50') is statistics.median
    assert wambatic.stats.percentile.summary('p90') is wambatic.stats.percentile.p90


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(st.lists(st.floats(0, 1e6), min_size=1, max_size=30))
def test_p90_stays_inside_the_values_and_is_at_least_the_median(values: list[float]) -> None:
    result = wambatic.stats.percentile.p90(values)
    assert min(values) - 1e-6 <= result <= max(values) + 1e-6
    assert result >= statistics.median(values) - 1e-6
