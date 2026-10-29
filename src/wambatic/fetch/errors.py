import datetime

NO_TOKEN_MESSAGE = 'No GitHub token found: set GITHUB_TOKEN or run `gh auth login`'


class FetchError(Exception):
    """Base class of every error the fetch layer raises."""


class AuthError(FetchError):
    pass


class GraphQLError(FetchError):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors = errors
        super().__init__('; '.join(f'{kind}: {message}' for kind, message in errors))


class NotFoundError(FetchError):
    pass


class RateLimitError(FetchError):
    def __init__(self, reset_at: datetime.datetime) -> None:
        self.reset_at = reset_at
        stamp = reset_at.astimezone(datetime.UTC).isoformat()
        super().__init__(f'GitHub rate limit exhausted; resets at {stamp}')


class StatsPendingError(FetchError):
    pass


class CacheVersionError(FetchError):
    """The cache was written under a different schema, wambatic or query version.

    `differences` maps each differing key to its (recorded, running) values; None means the key
    is absent on that side.
    """

    def __init__(self, differences: dict[str, tuple[str | None, str | None]]) -> None:
        self.differences = differences
        lines = '; '.join(
            f'{key}: cache has {recorded or "nothing"}, this wambatic has {running or "nothing"}'
            for key, (recorded, running) in sorted(differences.items())
        )
        super().__init__(
            f'The cache was written by a different version ({lines}). Run `wambatic cache clear` '
            'to start again, or pass `--ignore-cache-version` for this run'
        )
