import datetime

import wambatic.stats.base


def bucket_start(day: datetime.date, granularity: wambatic.stats.base.Granularity) -> datetime.date:
    """First local date of the bucket holding `day`."""
    match granularity:
        case wambatic.stats.base.Granularity.YEAR:
            return datetime.date(day.year, 1, 1)
        case wambatic.stats.base.Granularity.MONTH:
            return datetime.date(day.year, day.month, 1)
        case wambatic.stats.base.Granularity.WEEK:
            iso = day.isocalendar()
            return datetime.date.fromisocalendar(iso.year, iso.week, 1)
        case wambatic.stats.base.Granularity.DAY:
            return day
        case _:
            raise ValueError(f'{granularity} has no bucket start; its bucket depends on the range')


def next_start(start: datetime.date, granularity: wambatic.stats.base.Granularity) -> datetime.date:
    """First local date of the bucket after the one starting at `start`."""
    match granularity:
        case wambatic.stats.base.Granularity.YEAR:
            return datetime.date(start.year + 1, 1, 1)
        case wambatic.stats.base.Granularity.MONTH:
            if start.month == 12:
                return datetime.date(start.year + 1, 1, 1)
            return datetime.date(start.year, start.month + 1, 1)
        case wambatic.stats.base.Granularity.WEEK:
            return start + datetime.timedelta(days=7)
        case wambatic.stats.base.Granularity.DAY:
            return start + datetime.timedelta(days=1)
        case _:
            raise ValueError(f'{granularity} has no next bucket')


def label(start: datetime.date, granularity: wambatic.stats.base.Granularity) -> str:
    match granularity:
        case wambatic.stats.base.Granularity.YEAR:
            return f'{start.year:04d}'
        case wambatic.stats.base.Granularity.MONTH:
            return f'{start.year:04d}-{start.month:02d}'
        case wambatic.stats.base.Granularity.WEEK:
            iso = start.isocalendar()
            return f'{iso.year:04d}-W{iso.week:02d}'
        case wambatic.stats.base.Granularity.DAY:
            return start.isoformat()
        case _:
            return 'total'


def bucket_for(
    when: datetime.datetime, granularity: wambatic.stats.base.Granularity, tz: datetime.tzinfo
) -> wambatic.stats.base.Bucket:
    """Bucket containing `when` (an aware datetime) in `tz`; weeks are ISO 8601 weeks starting
    Monday. Raises ValueError for Granularity.TOTAL, whose one bucket depends on the range."""
    if when.tzinfo is None:
        raise ValueError('when must be timezone-aware')
    start = bucket_start(when.astimezone(tz).date(), granularity)
    return wambatic.stats.base.Bucket(start, label(start, granularity))


def bucket_range(
    since: datetime.date, until: datetime.date, granularity: wambatic.stats.base.Granularity
) -> list[wambatic.stats.base.Bucket]:
    """The buckets covering the local dates `since` to `until`, both inclusive, in order.
    For TOTAL, the one bucket Bucket(since, 'total')."""
    if since > until:
        raise ValueError('since is after until')
    if granularity is wambatic.stats.base.Granularity.TOTAL:
        return [wambatic.stats.base.Bucket(since, 'total')]
    buckets: list[wambatic.stats.base.Bucket] = []
    start = bucket_start(since, granularity)
    while start <= until:
        buckets.append(wambatic.stats.base.Bucket(start, label(start, granularity)))
        start = next_start(start, granularity)
    return buckets


def partial_buckets(
    since: datetime.date, until: datetime.date, buckets: list[wambatic.stats.base.Bucket]
) -> list[wambatic.stats.base.Bucket]:
    """The first and last of `buckets` when the range starts after the first's start or ends
    before the last's end; never a TOTAL bucket."""
    if not buckets or buckets[0].label == 'total':
        return []
    granularity = bucket_granularity(buckets[0])
    partial: list[wambatic.stats.base.Bucket] = []
    if since > buckets[0].start:
        partial.append(buckets[0])
    last = buckets[-1]
    if until < next_start(last.start, granularity) - datetime.timedelta(days=1) and (
        not partial or last is not partial[0]
    ):
        partial.append(last)
    return partial


def bucket_granularity(bucket: wambatic.stats.base.Bucket) -> wambatic.stats.base.Granularity:
    """The granularity a bucket's label belongs to."""
    if 'W' in bucket.label:
        return wambatic.stats.base.Granularity.WEEK
    return {
        4: wambatic.stats.base.Granularity.YEAR,
        7: wambatic.stats.base.Granularity.MONTH,
        10: wambatic.stats.base.Granularity.DAY,
    }[len(bucket.label)]
