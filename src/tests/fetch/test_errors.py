import datetime

import pytest

import gitstat.fetch.errors


@pytest.mark.parametrize(
    'cls',
    [
        gitstat.fetch.errors.AuthError,
        gitstat.fetch.errors.GraphQLError,
        gitstat.fetch.errors.NotFoundError,
        gitstat.fetch.errors.RateLimitError,
        gitstat.fetch.errors.StatsPendingError,
    ],
)
def test_every_class_is_a_fetch_error(cls: type[Exception]) -> None:
    assert issubclass(cls, gitstat.fetch.errors.FetchError)


def test_rate_limit_error_names_reset() -> None:
    reset = datetime.datetime(2026, 10, 29, 17, 0, tzinfo=datetime.UTC)
    error = gitstat.fetch.errors.RateLimitError(reset)
    assert error.reset_at == reset
    assert '2026-10-29T17:00:00+00:00' in str(error)


def test_graphql_error_exposes_pairs() -> None:
    pairs = [('INTERNAL', 'boom'), ('FORBIDDEN', 'no')]
    error = gitstat.fetch.errors.GraphQLError(pairs)
    assert error.errors == pairs
    assert 'INTERNAL' in str(error)
    assert 'FORBIDDEN' in str(error)
