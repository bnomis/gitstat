import pytest

import wambatic.fetch.errors
import wambatic.stats.errors


@pytest.mark.parametrize(
    'error',
    [
        wambatic.stats.errors.EmptySubjectError,
        wambatic.stats.errors.InvalidRangeError,
        wambatic.stats.errors.InvalidRequestError,
        wambatic.stats.errors.UnknownGroupError,
    ],
)
def test_every_error_is_a_stats_error_and_not_a_fetch_error(error: type[Exception]) -> None:
    assert issubclass(error, wambatic.stats.errors.StatsError)
    assert not issubclass(error, wambatic.fetch.errors.FetchError)
    assert str(error('why')) == 'why'


def test_stats_error_is_not_a_fetch_error() -> None:
    assert not issubclass(wambatic.stats.errors.StatsError, wambatic.fetch.errors.FetchError)
    assert not issubclass(wambatic.fetch.errors.FetchError, wambatic.stats.errors.StatsError)
