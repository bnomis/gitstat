import collections.abc
import datetime
import statistics

import wambatic.fetch.base
import wambatic.stats.base
import wambatic.stats.buckets

FLOW_METRICS = (
    ('prs_opened', 'count'),
    ('prs_merged', 'count'),
    ('issues_opened', 'count'),
    ('issues_closed', 'count'),
    ('time_to_first_review_p50', 'hours'),
    ('time_to_first_review_p90', 'hours'),
    ('time_to_merge_p50', 'hours'),
    ('time_to_merge_p90', 'hours'),
    ('time_to_close_p50', 'hours'),
    ('time_to_close_p90', 'hours'),
    ('pr_size_p50', 'lines'),
)
COUNT_METRICS = tuple(name for name, unit in FLOW_METRICS if unit == 'count')
TIME_METRICS = tuple(name for name, unit in FLOW_METRICS if unit == 'hours')
SIZE_METRIC = 'pr_size_p50'
DURATIONS = tuple(dict.fromkeys(name.rpartition('_')[0] for name in TIME_METRICS))
SECONDS_PER_HOUR = 3600


def hours(start: datetime.datetime, end: datetime.datetime) -> float:
    return (end - start).total_seconds() / SECONDS_PER_HOUR


def p90(values: collections.abc.Sequence[float]) -> float:
    """The 90th percentile, which stays inside `values` and accepts a single value."""
    return statistics.quantiles(list(values), n=10, method='inclusive')[8]


def has_event_in_range(
    pull_requests: collections.abc.Iterable[wambatic.fetch.base.PullRequest],
    issues: collections.abc.Iterable[wambatic.fetch.base.Issue],
    tz: datetime.tzinfo,
    since: datetime.date,
    until: datetime.date,
) -> bool:
    """Whether any record has an event that a flow series counts, on a local date in the range."""
    moments: list[datetime.datetime | None] = []
    for pull in pull_requests:
        moments += [pull.created_at, pull.first_review_at, pull.merged_at]
    for issue in issues:
        moments += [issue.created_at, issue.closed_at]
    return any(
        moment is not None and since <= moment.astimezone(tz).date() <= until for moment in moments
    )


def aggregate(
    pull_requests: collections.abc.Iterable[wambatic.fetch.base.PullRequest],
    issues: collections.abc.Iterable[wambatic.fetch.base.Issue],
    buckets: list[wambatic.stats.base.Bucket],
    tz: datetime.tzinfo,
    since: datetime.date,
    until: datetime.date,
) -> list[wambatic.stats.base.Series]:
    """The flow series for the records, each event placed by its own local date in `tz` and
    ignored when that date is outside `since` to `until` (the buckets may reach beyond it).

    Counts are zero in an empty bucket; the percentiles and the size have no point there."""
    starts = [bucket.start for bucket in buckets]
    end = wambatic.stats.buckets.bucket_end(buckets)
    counts = {name: [0] * len(buckets) for name in COUNT_METRICS}
    spans: dict[str, list[list[float]]] = {name: [[] for _ in buckets] for name in DURATIONS}
    sizes: list[list[float]] = [[] for _ in buckets]

    def place(moment: datetime.datetime | None) -> int | None:
        if moment is None:
            return None
        day = moment.astimezone(tz).date()
        if not since <= day <= until:
            return None
        return wambatic.stats.buckets.locate(day, starts, end)

    for pull in pull_requests:
        if (index := place(pull.created_at)) is not None:
            counts['prs_opened'][index] += 1
        if (index := place(pull.merged_at)) is not None and pull.merged_at is not None:
            counts['prs_merged'][index] += 1
            spans['time_to_merge'][index].append(hours(pull.created_at, pull.merged_at))
            sizes[index].append(pull.additions + pull.deletions)
        if (index := place(pull.first_review_at)) is not None and pull.first_review_at is not None:
            spans['time_to_first_review'][index].append(
                hours(pull.created_at, pull.first_review_at)
            )
    for issue in issues:
        if (index := place(issue.created_at)) is not None:
            counts['issues_opened'][index] += 1
        if (index := place(issue.closed_at)) is not None and issue.closed_at is not None:
            counts['issues_closed'][index] += 1
            spans['time_to_close'][index].append(hours(issue.created_at, issue.closed_at))

    series: list[wambatic.stats.base.Series] = []
    for name, unit in FLOW_METRICS:
        values: collections.abc.Sequence[collections.abc.Sequence[float]]
        summary: collections.abc.Callable[[collections.abc.Sequence[float]], float]
        if name in counts:
            points: dict[wambatic.stats.base.Bucket, float] = dict(
                zip(buckets, counts[name], strict=True)
            )
            series.append(wambatic.stats.base.Series(name, unit, points))
            continue
        if name == SIZE_METRIC:
            values, summary = sizes, statistics.median_low
        else:
            base, _, percentile = name.rpartition('_')
            values, summary = spans[base], statistics.median if percentile == 'p50' else p90
        points = {
            bucket: summary(found) for bucket, found in zip(buckets, values, strict=True) if found
        }
        series.append(wambatic.stats.base.Series(name, unit, points))
    return series
