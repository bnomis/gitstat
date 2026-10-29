import collections.abc
import dataclasses
import datetime
import random

BACKOFF_BASE = 1.0
BACKOFF_CAP = 60.0
SECONDARY_WAIT = 60.0


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


@dataclasses.dataclass(frozen=True, slots=True)
class RateLimitState:
    remaining: int | None = None
    reset_at: datetime.datetime | None = None

    @classmethod
    def from_headers(cls, headers: collections.abc.Mapping[str, str]) -> RateLimitState:
        """From `x-ratelimit-remaining` and `x-ratelimit-reset` (epoch seconds)."""
        remaining = headers.get('x-ratelimit-remaining')
        reset = headers.get('x-ratelimit-reset')
        return cls(
            remaining=int(remaining) if remaining is not None else None,
            reset_at=(
                datetime.datetime.fromtimestamp(int(reset), datetime.UTC)
                if reset is not None
                else None
            ),
        )

    @classmethod
    def from_graphql(cls, rate_limit: collections.abc.Mapping[str, object]) -> RateLimitState:
        """From a query's `rateLimit { cost remaining resetAt }` object."""
        remaining = rate_limit.get('remaining')
        reset = rate_limit.get('resetAt')
        return cls(
            remaining=remaining if isinstance(remaining, int) else None,
            reset_at=(
                datetime.datetime.fromisoformat(reset).astimezone(datetime.UTC)
                if isinstance(reset, str)
                else None
            ),
        )

    def exhausted(self, now: datetime.datetime) -> bool:
        """True when `remaining == 0` and `reset_at` is later than `now`."""
        return self.remaining == 0 and self.reset_at is not None and self.reset_at > now


def backoff_delay(attempt: int, rng: random.Random) -> float:
    """Full-jitter backoff: uniform in [0, min(CAP, BASE * 2 ** attempt)] seconds."""
    return rng.uniform(0, min(BACKOFF_CAP, BACKOFF_BASE * 2**attempt))
