class StatsError(Exception):
    """Base class of every error `gitstat.stats` raises itself."""


class EmptySubjectError(StatsError):
    """Nothing to report: no repositories, no records in range, or no group built yet."""


class InvalidRangeError(StatsError):
    """`since` is after `until`."""


class InvalidRequestError(StatsError):
    """A combination of request fields that has no meaning, such as `by_author` for a user."""


class UnknownGroupError(StatsError):
    """The request names a metric group outside `GROUPS`."""
