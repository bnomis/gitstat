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
