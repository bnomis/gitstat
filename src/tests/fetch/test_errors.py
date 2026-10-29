import datetime

import pytest

import gitstat.fetch.errors


@pytest.mark.parametrize(
    'cls',
    [
        gitstat.fetch.errors.AuthError,
        gitstat.fetch.errors.CacheVersionError,
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


def test_cache_version_error_names_each_key_with_both_values_and_the_remedies() -> None:
    error = gitstat.fetch.errors.CacheVersionError(
        {
            'schema_version': ('1', '2'),
            'query:NEW': (None, 'abc'),
            'query:OLD': ('def', None),
        }
    )
    message = str(error)
    assert 'schema_version: cache has 1, this gitstat has 2' in message
    assert 'query:NEW: cache has nothing, this gitstat has abc' in message
    assert 'query:OLD: cache has def, this gitstat has nothing' in message
    assert 'gitstat cache clear' in message
    assert '--ignore-cache-version' in message
    assert error.differences['schema_version'] == ('1', '2')
