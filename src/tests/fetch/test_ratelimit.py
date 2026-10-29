import datetime
import random

import hypothesis
import hypothesis.strategies

import wambatic.fetch.ratelimit

NOW = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)
LATER = datetime.datetime(2026, 10, 29, 13, 0, tzinfo=datetime.UTC)


def test_from_headers() -> None:
    state = wambatic.fetch.ratelimit.RateLimitState.from_headers(
        {'x-ratelimit-remaining': '4999', 'x-ratelimit-reset': str(int(LATER.timestamp()))}
    )
    assert state == wambatic.fetch.ratelimit.RateLimitState(4999, LATER)
    assert state.reset_at is not None
    assert state.reset_at.utcoffset() == datetime.timedelta(0)


def test_missing_headers_give_empty_state() -> None:
    assert wambatic.fetch.ratelimit.RateLimitState.from_headers(
        {}
    ) == wambatic.fetch.ratelimit.RateLimitState(None, None)


def test_from_graphql() -> None:
    state = wambatic.fetch.ratelimit.RateLimitState.from_graphql(
        {'cost': 1, 'remaining': 4998, 'resetAt': '2026-10-29T13:00:00Z'}
    )
    assert state == wambatic.fetch.ratelimit.RateLimitState(4998, LATER)


def test_exhausted() -> None:
    state = wambatic.fetch.ratelimit.RateLimitState
    assert not state().exhausted(NOW)
    assert not state(5, LATER).exhausted(NOW)
    assert not state(0, NOW).exhausted(LATER)
    assert not state(0, LATER).exhausted(LATER)
    assert state(0, LATER).exhausted(NOW)


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(
    attempt=hypothesis.strategies.integers(0, 30),
    seed=hypothesis.strategies.integers(),
)
def test_backoff_delay_bounds(attempt: int, seed: int) -> None:
    delay = wambatic.fetch.ratelimit.backoff_delay(attempt, random.Random(seed))
    ceiling = min(
        wambatic.fetch.ratelimit.BACKOFF_CAP, wambatic.fetch.ratelimit.BACKOFF_BASE * 2**attempt
    )
    assert 0 <= delay <= ceiling
