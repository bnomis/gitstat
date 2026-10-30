import collections.abc
import datetime
import statistics

SECONDS_PER_HOUR = 3600
Summary = collections.abc.Callable[[collections.abc.Sequence[float]], float]


def hours(start: datetime.datetime, end: datetime.datetime) -> float:
    return (end - start).total_seconds() / SECONDS_PER_HOUR


def p90(values: collections.abc.Sequence[float]) -> float:
    """The 90th percentile, which stays inside `values` and accepts a single value."""
    return statistics.quantiles(list(values), n=10, method='inclusive')[8]


def summary(suffix: str) -> Summary:
    """The summary a series name's `p50` or `p90` suffix asks for."""
    return statistics.median if suffix == 'p50' else p90
