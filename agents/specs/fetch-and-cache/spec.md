# Fetch and cache

**Version:** 1.0
**Status:** proposed
**Date:** 2026-10-29

Fetches raw data about a GitHub user, repository or organisation and stores it in a local SQLite cache so that repeated and incremental runs stay inside the API rate limits. It uses the [GraphQL API](https://docs.github.com/en/graphql) for almost everything and the [REST API](https://docs.github.com/en/rest) only where GraphQL has no equivalent (workflow runs, the `stats/*` endpoints). It knows nothing about metrics; [Stats](../stats/spec.md) consumes its output.

## Module location

`src/gitstat/fetch/` (`client.py`, `queries.py`, `cache.py`, `base.py`), with tests in `src/tests/fetch/`.

## API

```python
import dataclasses
import datetime
import typing

@dataclasses.dataclass(frozen=True, slots=True)
class Subject:
    kind: typing.Literal['user', 'repo', 'org']
    login: str                 # user or org login, or repo owner
    name: str | None = None    # repo name when kind == 'repo'

@dataclasses.dataclass(frozen=True, slots=True)
class Commit:
    repo: str                  # 'owner/name'
    oid: str
    authored_at: datetime.datetime   # UTC
    author_login: str | None         # None when the email maps to no account
    additions: int
    deletions: int

@dataclasses.dataclass(frozen=True, slots=True)
class PullRequest:
    repo: str
    number: int
    author_login: str | None
    created_at: datetime.datetime
    merged_at: datetime.datetime | None
    closed_at: datetime.datetime | None
    first_review_at: datetime.datetime | None
    additions: int
    deletions: int

class Fetcher:
    def __init__(self, token: str, cache: Cache, settings: FetchSettings) -> None: ...

    def repos(self, subject: Subject) -> list[Repo]:
        """Repositories owned by a user or org (forks and archived per settings); a repo subject yields itself."""

    def commits(self, repo: Repo, since: datetime.datetime | None, until: datetime.datetime | None) -> typing.Iterator[Commit]:
        """Default-branch commits, paginated 100 at a time, with per-commit additions and deletions."""

    def pull_requests(self, repo: Repo, since: datetime.datetime | None) -> typing.Iterator[PullRequest]: ...
    def issues(self, repo: Repo, since: datetime.datetime | None) -> typing.Iterator[Issue]: ...
    def releases(self, repo: Repo) -> typing.Iterator[Release]: ...
    def workflow_runs(self, repo: Repo, since: datetime.datetime | None) -> typing.Iterator[WorkflowRun]: ...
    def star_events(self, repo: Repo) -> typing.Iterator[StarEvent]: ...

def resolve_token() -> str:
    """GITHUB_TOKEN from the environment, else `gh auth token`; raises AuthError if neither."""
```

## Error handling

- `AuthError`: no token found, or GitHub returns 401. The message says to set `GITHUB_TOKEN` and never echoes a token.
- `RateLimitError`: primary limit exhausted (`x-ratelimit-remaining: 0` or a GraphQL `RATE_LIMITED` error) and `fetch.on_rate_limit` is `fail`. Carries the reset time. With `wait` the fetcher sleeps until reset, logging an `ETA:` line.
- Secondary rate limits (HTTP 403/429 with `retry-after`) are always honoured, then retried up to `fetch.max_retries` with exponential backoff and jitter.
- `NotFoundError`: user, org or repo does not exist or is not visible to the token.
- `CacheVersionError`: the cache was written under a different schema or query version (see Cache). It names both versions and tells the user to run `gitstat cache clear` or pass `--ignore-cache-version`. It never warns and carries on, per the shared versions rule.
- REST `stats/*` returning 202 (still computing) is retried with backoff up to `fetch.stats_retries`, then raised as `StatsPendingError`.
- Unexpected exceptions propagate; only the above are caught.

## Implementation

**Transport.** Synchronous `httpx.Client` with HTTP/2, one POST endpoint for GraphQL and conditional GETs for REST. Concurrency is a bounded thread pool across repositories (`fetch.workers`), because GitHub asks clients to avoid concurrent request bursts ([best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)).

**GraphQL cost control.** Queries are built to stay under the 500,000-node cap and the 5,000-points/hour budget ([limits](https://docs.github.com/en/graphql/overview/rate-limits-and-node-limits-for-the-github-graphql-api)): 100 nodes per page, only requested fields, and `rateLimit { cost remaining resetAt }` on every query so the fetcher can pace itself. Per-commit `additions` and `deletions` come from the `Commit` object's history connection; the REST `stats/code_frequency` and `stats/contributors` endpoints are used only as a cheap cross-check on repos under 10,000 commits.

**Cache.** One SQLite file (`fetch.cache_path`, default `~/.cache/gitstat/cache.sqlite3`) in WAL mode. Tables: `meta(key, value)`, `repos`, `commits`, `pull_requests`, `issues`, `releases`, `workflow_runs`, `star_events`, `sync_state(repo, resource, cursor, synced_at)`. Immutable rows (commits) are never refetched; mutable resources are refetched when `now - synced_at > fetch.ttl_*` and only from the stored `since` cursor onwards. REST responses also store their `ETag` and are revalidated with `If-None-Match`, which does not count against the limit when answered 304.

**Cache identity.** `meta` records `schema_version`, the hash of each query text, and the gitstat version. Opening a cache whose recorded identity differs from the running code raises `CacheVersionError`.

**Secrets.** The token is read from the environment only, never written to the cache, logs or reports ([security rules](../../../.agents/claude/rules/security.md)). Requests are logged with the token redacted.

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `fetch.cache_path` | `Path` | `~/.cache/gitstat/cache.sqlite3` | SQLite cache file |
| `fetch.include_forks` | `bool` | `False` | Include forked repos for user/org subjects |
| `fetch.include_archived` | `bool` | `False` | Include archived repos |
| `fetch.max_retries` | `int` | `5` | Retries for transient and secondary-limit errors |
| `fetch.on_rate_limit` | `Literal['wait', 'fail']` | `'wait'` | Behaviour on primary limit exhaustion |
| `fetch.stats_retries` | `int` | `6` | Retries while a REST stats endpoint returns 202 |
| `fetch.ttl_open_items` | `timedelta` | `1 hour` | Refresh age for open PRs, issues, runs |
| `fetch.workers` | `int` | `4` | Concurrent repo fetches |

## External dependencies

- GitHub GraphQL and REST APIs; a token with `public_repo` (or `repo` for private repos, `read:org` for private org membership).
- `httpx` ([docs](https://www.python-httpx.org/)), `loguru`, stdlib `sqlite3`.
- Each library is to be checked for maintenance status before it is added with `uv add`, per the shared tools-and-libraries rule.
