import dataclasses
import datetime

import pytest

import gitstat.settings
import gitstat.stats.base

Bucket = gitstat.stats.base.Bucket
Series = gitstat.stats.base.Series


def test_groups_are_the_three_metric_groups() -> None:
    assert gitstat.stats.base.GROUPS == {'activity', 'delivery', 'flow'}


def test_granularity_has_the_five_values() -> None:
    assert {g.value for g in gitstat.stats.base.Granularity} == {
        'day',
        'month',
        'total',
        'week',
        'year',
    }


def test_a_default_request_is_monthly_activity_and_flow_in_utc() -> None:
    request = gitstat.stats.base.StatsRequest()
    assert request.granularity is gitstat.stats.base.Granularity.MONTH
    assert request.groups == {'activity', 'flow'}
    assert request.since is None
    assert request.until is None
    assert request.by_author is False
    assert request.tz is datetime.UTC
    assert request.settings == gitstat.settings.StatsSettings()


def test_a_request_is_hashable() -> None:
    assert hash(gitstat.stats.base.StatsRequest()) == hash(gitstat.stats.base.StatsRequest())


def test_buckets_sort_by_start() -> None:
    later = Bucket(datetime.date(2026, 11, 1), '2026-11')
    earlier = Bucket(datetime.date(2026, 10, 1), '2026-10')
    assert sorted([later, earlier]) == [earlier, later]


def test_records_are_immutable() -> None:
    bucket = Bucket(datetime.date(2026, 10, 1), '2026-10')
    with pytest.raises(dataclasses.FrozenInstanceError):
        bucket.label = 'x'  # type: ignore[misc]
    series = Series('commits', 'count', {bucket: 1})
    with pytest.raises(dataclasses.FrozenInstanceError):
        series.metric = 'x'  # type: ignore[misc]
    request = gitstat.stats.base.StatsRequest()
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.by_author = True  # type: ignore[misc]


def test_a_series_with_both_or_neither_key_is_valid() -> None:
    assert Series('commits', 'count', {}).by is None
    assert Series('commits', 'count', {}, by='octocat', by_kind='author').by == 'octocat'


@pytest.mark.parametrize('by, by_kind', [('octocat', None), (None, 'author')])
def test_a_series_with_only_one_key_is_rejected(by: str | None, by_kind: str | None) -> None:
    with pytest.raises(ValueError, match='by_kind'):
        Series('commits', 'count', {}, by=by, by_kind=by_kind)  # type: ignore[arg-type]
