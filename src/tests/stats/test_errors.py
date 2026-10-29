import pytest

import gitstat.fetch.errors
import gitstat.stats.errors


@pytest.mark.parametrize(
    'error',
    [
        gitstat.stats.errors.EmptySubjectError,
        gitstat.stats.errors.InvalidRangeError,
        gitstat.stats.errors.InvalidRequestError,
        gitstat.stats.errors.UnknownGroupError,
    ],
)
def test_every_error_is_a_stats_error_and_not_a_fetch_error(error: type[Exception]) -> None:
    assert issubclass(error, gitstat.stats.errors.StatsError)
    assert not issubclass(error, gitstat.fetch.errors.FetchError)
    assert str(error('why')) == 'why'


def test_stats_error_is_not_a_fetch_error() -> None:
    assert not issubclass(gitstat.stats.errors.StatsError, gitstat.fetch.errors.FetchError)
    assert not issubclass(gitstat.fetch.errors.FetchError, gitstat.stats.errors.StatsError)
