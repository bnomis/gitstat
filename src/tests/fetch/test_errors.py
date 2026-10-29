import datetime

import pytest

import wambatic.fetch.errors


@pytest.mark.parametrize(
    'cls',
    [
        wambatic.fetch.errors.AuthError,
        wambatic.fetch.errors.CacheVersionError,
        wambatic.fetch.errors.GraphQLError,
        wambatic.fetch.errors.NotFoundError,
        wambatic.fetch.errors.RateLimitError,
        wambatic.fetch.errors.StatsPendingError,
    ],
)
def test_every_class_is_a_fetch_error(cls: type[Exception]) -> None:
    assert issubclass(cls, wambatic.fetch.errors.FetchError)


def test_rate_limit_error_names_reset() -> None:
    reset = datetime.datetime(2026, 10, 29, 17, 0, tzinfo=datetime.UTC)
    error = wambatic.fetch.errors.RateLimitError(reset)
    assert error.reset_at == reset
    assert '2026-10-29T17:00:00+00:00' in str(error)


def test_graphql_error_exposes_pairs() -> None:
    pairs = [('INTERNAL', 'boom'), ('FORBIDDEN', 'no')]
    error = wambatic.fetch.errors.GraphQLError(pairs)
    assert error.errors == pairs
    assert 'INTERNAL' in str(error)
    assert 'FORBIDDEN' in str(error)


def test_cache_version_error_names_each_key_with_both_values_and_the_remedies() -> None:
    error = wambatic.fetch.errors.CacheVersionError(
        {
            'schema_version': ('1', '2'),
            'query:NEW': (None, 'abc'),
            'query:OLD': ('def', None),
        }
    )
    message = str(error)
    assert 'schema_version: cache has 1, this wambatic has 2' in message
    assert 'query:NEW: cache has nothing, this wambatic has abc' in message
    assert 'query:OLD: cache has def, this wambatic has nothing' in message
    assert 'wambatic cache clear' in message
    assert '--ignore-cache-version' in message
    assert error.differences['schema_version'] == ('1', '2')
