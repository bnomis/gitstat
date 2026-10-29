# Fetch and cache

**Version:** 1.1
**Status:** proposed
**Date:** 2026-10-29

Fetches raw data about a GitHub user, repository or organisation and stores it in a local SQLite cache so that repeated and incremental runs stay inside the API rate limits. It uses the [GraphQL API](https://docs.github.com/en/graphql) for almost everything and the [REST API](https://docs.github.com/en/rest) only where GraphQL has no equivalent (workflow runs, the `stats/*` endpoints). It knows nothing about metrics; [Stats](../stats/spec.md) consumes its output.

## Module location

`src/gitstat/fetch/`, with tests in `src/tests/fetch/` and fixtures in `src/tests/fixtures/fetch/`:

| Module | Holds | Built in implementation step |
|--------|-------|------------------------------|
| `errors.py` | `FetchError` and every typed error below | 2 (`CacheVersionError` in 3) |
| `auth.py` | `resolve_token`, `redact` | 2 |
| `ratelimit.py` | `RateLimitState`, `backoff_delay` | 2 |
| `client.py` | `GitHubClient`, `RestResponse`: the aiohttp transport | 2 |
| `queries.py` | GraphQL query texts | 2 (first query), 3 onwards |
| `cache.py` | `Cache`: SQLite schema, identity, watermarks | 3 |
| `base.py` | `Subject`, the record dataclasses, `Fetcher` | 3 |

`Fetcher` owns one `GitHubClient` and one `Cache`; its `__aenter__` enters the client and its `__aexit__` exits it. `Fetcher` is therefore built in step 3, when `Cache` exists; step 2 builds the client it wraps.

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

    async def __aenter__(self) -> Fetcher: ...
    async def __aexit__(self, *exc_info: object) -> None:
        """Closes the aiohttp session."""

    async def sync(self, subject: Subject, resources: frozenset[str], full_refresh: bool = False) -> SyncReport:
        """Bring the cache up to date for the subject: backfill on first use, otherwise only the delta since each watermark."""

    async def repos(self, subject: Subject) -> list[Repo]:
        """Repositories owned by a user or org (forks and archived per settings); a repo subject yields itself."""

    async def commits(self, repo: Repo, since: datetime.datetime | None, until: datetime.datetime | None) -> typing.AsyncIterator[Commit]:
        """Default-branch commits, paginated 100 at a time, with per-commit additions and deletions."""

    async def pull_requests(self, repo: Repo, since: datetime.datetime | None) -> typing.AsyncIterator[PullRequest]: ...
    async def issues(self, repo: Repo, since: datetime.datetime | None) -> typing.AsyncIterator[Issue]: ...
    async def releases(self, repo: Repo) -> typing.AsyncIterator[Release]: ...
    async def workflow_runs(self, repo: Repo, since: datetime.datetime | None) -> typing.AsyncIterator[WorkflowRun]: ...
    async def star_events(self, repo: Repo) -> typing.AsyncIterator[StarEvent]: ...

def resolve_token() -> str:
    """GITHUB_TOKEN from the environment, else `gh auth token`; raises AuthError if neither."""

def redact(text: str, token: str) -> str:
    """`text` with every occurrence of `token` replaced by `***`."""
```

The transport, used only inside `gitstat.fetch`:

```python
import collections.abc

@dataclasses.dataclass(frozen=True, slots=True)
class RateLimitState:
    remaining: int | None = None              # None until the first response is seen
    reset_at: datetime.datetime | None = None # UTC

    @classmethod
    def from_headers(cls, headers: collections.abc.Mapping[str, str]) -> RateLimitState:
        """From `x-ratelimit-remaining` and `x-ratelimit-reset` (epoch seconds); empty state if absent."""

    @classmethod
    def from_graphql(cls, rate_limit: collections.abc.Mapping[str, object]) -> RateLimitState:
        """From a query's `rateLimit { cost remaining resetAt }` object."""

    def exhausted(self, now: datetime.datetime) -> bool:
        """True when `remaining == 0` and `reset_at` is later than `now`."""

def backoff_delay(attempt: int, rng: random.Random) -> float:
    """Full-jitter backoff: uniform in [0, min(BACKOFF_CAP, BACKOFF_BASE * 2 ** attempt)] seconds."""

@dataclasses.dataclass(frozen=True, slots=True)
class RestResponse:
    status: int                    # 200 or 304
    data: object | None            # parsed JSON; None on 304
    etag: str | None
    next_url: str | None           # rel="next" from the Link header

class GitHubClient:
    def __init__(
        self,
        token: str,
        settings: FetchSettings,
        *,
        api_url: str = 'https://api.github.com',
        sleep: collections.abc.Callable[[float], collections.abc.Awaitable[None]] = asyncio.sleep,
        clock: collections.abc.Callable[[], datetime.datetime] = utc_now,
        rng: random.Random | None = None,
    ) -> None: ...

    async def __aenter__(self) -> GitHubClient:
        """Opens the one aiohttp.ClientSession."""
    async def __aexit__(self, *exc_info: object) -> None:
        """Closes it."""

    async def graphql(self, query: str, variables: collections.abc.Mapping[str, object]) -> dict[str, object]:
        """POST `{api_url}/graphql`; returns `data`; raises the typed errors below."""

    async def rest_get(self, path: str, params: collections.abc.Mapping[str, str] | None = None, etag: str | None = None) -> RestResponse:
        """GET `{api_url}{path}` with `If-None-Match: etag` when given; retries 202 per `fetch.stats_retries`."""

    @property
    def graphql_limit(self) -> RateLimitState: ...
    @property
    def rest_limit(self) -> RateLimitState: ...
```

`api_url`, `sleep`, `clock` and `rng` exist so tests can point the client at a local server and run without real waits; production code passes none of them. `utc_now` returns `datetime.datetime.now(datetime.UTC)`.

## Error handling

- `FetchError(Exception)`: base class of every error below, so the edge can catch the fetch layer's errors in one clause.
- `AuthError`: no token found, or GitHub returns 401. The message says to set `GITHUB_TOKEN` and never echoes a token. A 403 that is not a rate limit (see Requests, retries and rate limits) is also `AuthError`; its message names the scopes from GitHub's `x-accepted-oauth-scopes` header when present.
- `RateLimitError`: primary limit exhausted (`x-ratelimit-remaining: 0` or a GraphQL `RATE_LIMITED` error) and `fetch.on_rate_limit` is `fail`. Carries the reset time. With `wait` the fetcher sleeps until reset, logging an `ETA:` line.
- Secondary rate limits (HTTP 403/429, see Requests, retries and rate limits) are always honoured, then retried up to `fetch.max_retries` with exponential backoff and jitter. When the retries run out, `RateLimitError` is raised whatever `fetch.on_rate_limit` says, with `reset_at` set to the time the last wait would have ended.
- `GraphQLError`: a GraphQL response whose `errors` contain a type other than `NOT_FOUND` and `RATE_LIMITED`. It carries each error's `type` and `message`; partial `data` is discarded.
- `NotFoundError`: user, org or repo does not exist or is not visible to the token: REST 404, or a GraphQL error of type `NOT_FOUND`.
- `CacheVersionError`: the cache was written under a different schema or query version (see Cache). It names both versions and tells the user to run `gitstat cache clear` or pass `--ignore-cache-version`. It never warns and carries on, per the shared versions rule.
- REST `stats/*` returning 202 (still computing) is retried with backoff up to `fetch.stats_retries`, then raised as `StatsPendingError`.
- Transient failures (HTTP 500, 502, 503 and 504, `aiohttp.ClientConnectionError` and `TimeoutError`) are retried up to `fetch.max_retries` with the same backoff; when the retries run out the last exception propagates unchanged.
- Any other non-2xx status propagates as `aiohttp.ClientResponseError`.
- Unexpected exceptions propagate; only the above are caught.

## Implementation

**Transport.** One `aiohttp.ClientSession` per `Fetcher`, as the shared Python rules specify: a POST endpoint for GraphQL and conditional GETs for REST. Concurrency is bounded across repositories by an `asyncio.Semaphore` of `fetch.workers`, because GitHub asks clients to avoid concurrent request bursts ([best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)). SQLite calls run through `asyncio.to_thread` so the loop is never blocked. The CLI enters the loop once with `asyncio.run`.

**Requests, retries and rate limits.** Every request carries `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28` and `User-Agent: gitstat/<VERSION>`, with an `aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)` of 60 seconds. GitHub's documented handling ([REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit), [best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#handle-rate-limit-errors-appropriately)) is applied in this order to each response:

1. 401: `AuthError`.
2. 403 or 429 with a `retry-after` header: secondary limit; wait that many seconds, then retry.
3. 403 or 429 with `x-ratelimit-remaining: 0`: primary limit; handled as in step 6.
4. 403 or 429 whose JSON `message` contains `secondary rate limit`, with neither header: secondary limit; wait 60 seconds, then retry.
5. Any other 403: `AuthError`. 404: `NotFoundError`. Transient statuses: back off and retry.
6. *Primary limit.* The client keeps one `RateLimitState` for GraphQL and one for REST, each updated from the `x-ratelimit-*` headers of every response on its endpoint; a GraphQL response's `rateLimit` object, when present, then overrides the GraphQL state. If a primary-limit response leaves no `reset_at` to wait for, it is handled as a secondary limit with the 60-second wait. Before each request, and on a primary-limit response or a GraphQL `RATE_LIMITED` error, if the state is exhausted: with `fetch.on_rate_limit = 'fail'` raise `RateLimitError(reset_at)`; with `'wait'` log `ETA: GitHub rate limit resets in <duration>` at `info` and sleep until `reset_at` plus one second, then retry. Waiting for a primary reset does not count against `fetch.max_retries`. This is the whole of the pacing: there is no proactive slow-down while budget remains.

Backoff for transient failures and repeated secondary limits is full jitter ([AWS, Exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)) with `BACKOFF_BASE = 1.0` and `BACKOFF_CAP = 60.0` seconds; for a secondary limit the wait is the larger of the header or 60-second wait and the backoff delay. A REST 202 is retried after `backoff_delay` up to `fetch.stats_retries` times, then raises `StatsPendingError`. All waits go through the client's `sleep`.

Every query text in `queries.py` selects `rateLimit { cost remaining resetAt }`; a response with `data` and no `errors` that lacks it raises `GraphQLError`, so a query that forgot it fails its first test.

**GraphQL cost control.** Queries are built to stay under the 500,000-node cap and the 5,000-points/hour budget ([limits](https://docs.github.com/en/graphql/overview/rate-limits-and-node-limits-for-the-github-graphql-api)): 100 nodes per page, only requested fields, and `rateLimit { cost remaining resetAt }` on every query so the fetcher can pace itself. Per-commit `additions` and `deletions` come from the `Commit` object's history connection; the REST `stats/code_frequency` and `stats/contributors` endpoints are used only as a cheap cross-check on repos under 10,000 commits.

**Cache.** One SQLite file (`fetch.cache_path`, default `~/.cache/gitstat/cache.sqlite3`) in WAL mode. Tables: `meta(key, value)`, `repos`, `commits`, `pull_requests`, `issues`, `releases`, `workflow_runs`, `star_events`, and `sync_state(repo, resource, watermark, head_oid, synced_at, full_synced_at)`. REST responses also store their `ETag` and are revalidated with `If-None-Match`, which does not count against the limit when answered 304.

**Incremental sync.** The first query of a subject backfills everything; later queries fetch only what changed since the last successful sync. State is per repo and per resource, so asking for a new metric group later backfills only that resource.

1. *Subject level.* The repo list is always re-read (one cheap query per 100 repos, ordered by `pushedAt`). A repo whose `pushedAt` and `updatedAt` are not newer than its stored `synced_at` is skipped entirely, with no per-repo requests. A repo not yet in the cache is backfilled; a repo gone from the list is marked `missing`, its rows kept.
2. *Per resource.* Each resource has an incremental strategy that pages newest-first and stops at the watermark:
   - `commits`: immutable, so never refetched. History is read with `since = watermark - fetch.overlap` and rows are de-duplicated by `oid`. `head_oid` is stored; if the stored head is not an ancestor of the new head (force-push or rewritten history), that repo's commits are fully refetched.
   - `pull_requests` and `issues`: mutable. Paged ordered by `UPDATED_AT` descending, stopping at the first item older than `watermark - fetch.overlap`; changed items are upserted by number. Still-open items are therefore refreshed whenever they change.
   - `releases` and `star_events`: paged newest-first (`CREATED_AT`, `STARRED_AT`), stopping at the first known id.
   - `workflow_runs`: REST with `created=>watermark - fetch.overlap`, plus a refetch of any cached run whose status is not `completed`.
3. *The watermark is a server-side timestamp* taken at the start of the sync, not the newest item seen, and the overlap (default one hour) absorbs clock skew and in-flight updates.
4. *Atomic advance.* Rows and the new watermark are written in one SQLite transaction per repo and resource, only after the last page succeeds. An interrupted or rate-limited run leaves the old watermark, so the next run resumes from it and re-fetching is harmless because writes are upserts.
5. *Deletions cannot be seen incrementally* (deleted or transferred issues, unstarred repos, deleted releases). Each resource is therefore fully re-read when `now - full_synced_at > fetch.full_refresh_after`, or when the user passes `--full-refresh`.
6. *Offline and bounded.* `--no-fetch` renders from the cache alone; `--max-age` skips the network for a subject synced more recently than that.

**Cache identity.** `meta` records `schema_version`, the hash of each query text, and the gitstat version. Opening a cache whose recorded identity differs from the running code raises `CacheVersionError`.

**Secrets.** The token is read from the environment only, never written to the cache, logs or reports ([security rules](../../../.agents/claude/rules/security.md)). Requests are logged at `debug` as method, URL and status only, never headers. The client logs through `loguru.logger.patch(...)` with a patcher that applies `redact` to each record's message, so a token that reaches a message by any path is replaced by `***`.

**Testing.** Unit tests replay fixture responses from an `aiohttp.web.Application` served by `aiohttp.test_utils.TestServer`, which ships with aiohttp, and point `GitHubClient` at it with `api_url`; async tests run their body with `asyncio.run`, so no pytest async plugin is added. Fixture responses live in `src/tests/fixtures/fetch/` as Python modules. Successful responses are recorded once from the live API (date of recording in a comment, trimmed to the fields used, no token or personal data beyond public logins); error responses (401, 403, 404, 429, 202, `RATE_LIMITED`) are written from the shapes in GitHub's documentation, each with the page it came from. The opt-in live test, skipped when `GITHUB_TOKEN` is unset and marked `live`, runs one small query against the public `octocat` account.

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `fetch.cache_path` | `Path` | `~/.cache/gitstat/cache.sqlite3` | SQLite cache file |
| `fetch.include_forks` | `bool` | `False` | Include forked repos for user/org subjects |
| `fetch.full_refresh_after` | `timedelta` | `30 days` | Age of the last full read after which a resource is fully re-read to catch deletions |
| `fetch.include_archived` | `bool` | `False` | Include archived repos |
| `fetch.max_age` | `timedelta` | `0` | Skip the network if the subject was synced more recently than this |
| `fetch.max_retries` | `int` | `5` | Retries for transient and secondary-limit errors |
| `fetch.on_rate_limit` | `Literal['wait', 'fail']` | `'wait'` | Behaviour on primary limit exhaustion |
| `fetch.overlap` | `timedelta` | `1 hour` | Safety margin subtracted from the watermark |
| `fetch.stats_retries` | `int` | `6` | Retries while a REST stats endpoint returns 202 |
| `fetch.workers` | `int` | `4` | Concurrent repo fetches |

## External dependencies

- GitHub GraphQL and REST APIs; a token with `public_repo` (or `repo` for private repos, `read:org` for private org membership).
- `aiohttp` ([docs](https://docs.aiohttp.org/en/stable/)), `loguru`, stdlib `sqlite3`.
- Each library is to be checked for maintenance status before it is added with `uv add`, per the shared tools-and-libraries rule.
