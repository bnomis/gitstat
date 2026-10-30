# Fetch and cache

**Version:** 1.9
**Status:** implemented
**Date:** 2026-10-30

Fetches raw data about a GitHub user, repository or organisation and stores it in a local SQLite cache so that repeated and incremental runs stay inside the API rate limits. It uses the [GraphQL API](https://docs.github.com/en/graphql) for almost everything and the [REST API](https://docs.github.com/en/rest) only where GraphQL has no equivalent (workflow runs, the `stats/*` endpoints, comparing two commits, and the list of a repository's forks). It knows nothing about metrics; [Stats](../stats/spec.md) consumes its output.

## Module location

`src/wambatic/fetch/`, with tests in `src/tests/fetch/` and fixtures in `src/tests/fixtures/fetch/`:

| Module | Holds | Built in implementation step |
|--------|-------|------------------------------|
| `errors.py` | `FetchError` and every typed error below | 2 (`CacheVersionError` in 3) |
| `auth.py` | `resolve_token`, `redact` | 2 |
| `ratelimit.py` | `RateLimitState`, `backoff_delay` | 2 |
| `client.py` | `GitHubClient`, `RestResponse`: the aiohttp transport | 2 |
| `queries.py` | GraphQL query texts | 2 (first query), 3 onwards |
| `cache.py` | `Cache`, `SCHEMA_VERSION`: SQLite schema, identity, watermarks, ETags; `CacheInfo`, `inspect_cache`, `clear_cache` | 3 (`CacheInfo`, `inspect_cache`, `clear_cache` in 5; the `pull_requests` and `issues` tables in 6; the `releases` and `workflow_runs` tables in 8; the `star_events` and `forks` tables and the `repos` popularity columns in 10) |
| `base.py` | `Subject`, `RESOURCES`, `BUILT_RESOURCES`, the record dataclasses (`Repo`, `Commit` and `SyncState` in 3, `PullRequest` and `Issue` in 6, `Release` and `WorkflowRun` in 8, `StarEvent` and `Fork` in 10), `SyncReport`, `SyncProgress`, `Fetcher` | 3 (`SyncProgress` in 9; `BUILT_RESOURCES`, `Fetcher.owner_kind` in 5; `pull_requests`, `issues` in 6; `releases`, `workflow_runs` in 8; `star_events`, `forks` and the `Repo` popularity fields in 10) |

`Fetcher` owns one `GitHubClient` and one `Cache`; its `__aenter__` enters the client and its `__aexit__` exits it. `Fetcher` is therefore built in step 3, when `Cache` exists; step 2 builds the client it wraps.

`Fetcher.sync` and `Fetcher.owner_kind` (added in 1.4 for the CLI's bare `NAME` target) are the only methods that reach the network. `repos`, `commits`, `pull_requests`, `issues`, `provenance` (added in 1.3 for the stats step) and the other record methods read the cache alone, so a caller syncs first and then reads, and a report from a warm cache makes no requests (system spec, Data flow step 3). A `Fetcher` that is never entered opens no aiohttp session, and the CLI relies on that to read a warm cache without a token.

Version 1.4 adds what step 5's CLI needs: `BUILT_RESOURCES`, `Fetcher.owner_kind`, and `inspect_cache` and `clear_cache` for the `cache` command. The choices are in the [reports review](../reports/review-1.md).

Version 1.5 adds what step 6 (flow data) needs: the `PullRequest` and `Issue` records and their tables, `Fetcher.pull_requests` and `Fetcher.issues`, the repo listing's newest pull request and issue update times that let a sync skip unchanged repos, the `Date` header as the server-side watermark (`GitHubClient.graphql_dated`), and `SCHEMA_VERSION` 2. The choices are in the [stats review 2](../stats/review-2.md).

Version 1.6 adds what step 8 (delivery data) needs: the `Release` and `WorkflowRun` records and their tables, `Fetcher.releases` and `Fetcher.workflow_runs`, the pull request fields `labels` and `first_commit_at` that the hotfix and lead-time proxies read, the repo listing's release probe and the `sync_state.probe` column it is compared with, `RestResponse.date`, and `SCHEMA_VERSION` 3. `star_events` moves to step 10 with the other popularity data (stars, forks, watchers, languages), which is specified then. The choices are in the [stats review 3](../stats/review-3.md).

Version 1.7 adds what step 9 (local web app) needs: `SyncProgress` and `Fetcher.sync`'s `progress` argument, so the web app can report a sync while it runs. Nothing else changes, and the cache schema stays 3. The choices are in the [reports review 3](../reports/review-3.md) (choice 4).

Version 1.8 adds what step 10 (popularity data) needs: the `StarEvent` and `Fork` records and their tables, the `forks` resource beside `star_events`, `Fetcher.star_events` and `Fetcher.forks`, the repo listing's star, fork and watcher counts and language sizes (the `Repo` popularity fields), the star and fork probes kept in `sync_state.probe`, and `SCHEMA_VERSION` 4. Watchers and languages are snapshots taken with the listing: GitHub records when a star or a fork was made but not when someone started watching, and keeps no history of a repository's languages. The choices are in the [stats review 4](../stats/review-4.md).

Version 1.9 settles what a star sync does when the token cannot see the stargazers: GitHub then lists none, or refuses with a `FORBIDDEN` error, while the listed star count says there are some. The repository gets a `sync_state` row for `star_events` whose `probe` is `STARS_HIDDEN` and no rows, `Fetcher.stars_hidden` reports it, and `Cache.write_state` writes a state alone. `SCHEMA_VERSION` does not change. The Testing paragraph now also describes the fake upstream's hidden-stargazers mode.

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

RESOURCES = frozenset({'commits', 'forks', 'issues', 'pull_requests', 'releases', 'star_events', 'workflow_runs'})
# The resources whose implementation step is built, which callers sync. Every resource is built
# since step 10; step 8 had every resource but 'forks' and 'star_events'.
BUILT_RESOURCES = RESOURCES

@dataclasses.dataclass(frozen=True, slots=True)
class Repo:
    name_with_owner: str             # 'owner/name'
    default_branch: str | None       # None for an empty repository
    head_oid: str | None             # default-branch head at listing time; None when empty
    is_archived: bool
    is_fork: bool
    pushed_at: datetime.datetime | None   # UTC, as GitHub reports it
    updated_at: datetime.datetime         # UTC, as GitHub reports it
    pull_requests_updated_at: datetime.datetime | None = None   # newest PR's updatedAt; None: no PRs
    issues_updated_at: datetime.datetime | None = None          # newest issue's updatedAt; None: no issues
    releases_count: int = 0                                     # releases totalCount, drafts included when visible
    releases_updated_at: datetime.datetime | None = None        # newest-created release's updatedAt; None: none
    stargazer_count: int = 0                                    # stargazerCount at listing time (step 10)
    fork_count: int = 0                                         # forkCount: forks in the whole network
    watcher_count: int = 0                                      # watchers totalCount: users subscribed
    languages: tuple[tuple[str, int], ...] = ()                 # (name, bytes), the 20 largest, largest first
    languages_size: int = 0                                     # bytes over every language, listed or not
    missing: bool = False            # gone from the owner's listing; rows kept

@dataclasses.dataclass(frozen=True, slots=True)
class Commit:
    repo: str                  # 'owner/name'
    oid: str
    authored_at: datetime.datetime   # UTC
    author_login: str | None         # None when the email maps to no account
    additions: int
    deletions: int
    is_merge: bool                   # more than one parent; Stats excludes these by default

@dataclasses.dataclass(frozen=True, slots=True)
class SyncReport:
    repos_listed: int                # repos in the subject's listing after the fork and archived filters
    repos_skipped: int               # unchanged for every requested resource, so no per-repo requests
    rows_written: dict[str, int]     # each requested resource -> rows inserted or replaced
    full_refetches: tuple[str, ...]  # 'owner/name' whose commits were re-read from scratch (commits only)

@dataclasses.dataclass(slots=True)
class SyncProgress:
    """Filled in by `Fetcher.sync` as it runs, on the event loop that runs it (step 9)."""
    repos_listed: int | None = None    # set once the listing is read and filtered
    repos_pending: int | None = None   # repos with a resource to sync, set with repos_listed
    repos_done: int = 0                # pending repos whose every needed resource is synced
    rows_written: dict[str, int] = dataclasses.field(default_factory=dict)  # so far, per resource

@dataclasses.dataclass(frozen=True, slots=True)
class PullRequest:
    repo: str
    number: int
    author_login: str | None         # REST form: a bot is 'name[bot]'; None for a deleted account
    created_at: datetime.datetime    # all times UTC
    updated_at: datetime.datetime
    merged_at: datetime.datetime | None   # None unless state is MERGED
    closed_at: datetime.datetime | None   # None while open; set when merged or closed
    first_review_at: datetime.datetime | None   # earliest submitted review by anyone but the
                                                # author and bots; None when there is none
    additions: int
    deletions: int
    labels: tuple[str, ...] = ()                     # the first 20 label names, as GitHub orders them
    first_commit_at: datetime.datetime | None = None # authoredDate of the pull request's first commit

@dataclasses.dataclass(frozen=True, slots=True)
class Issue:                         # issues only: GitHub's issues connection has no PRs
    repo: str
    number: int
    author_login: str | None         # as PullRequest
    created_at: datetime.datetime
    updated_at: datetime.datetime
    closed_at: datetime.datetime | None   # None unless state is CLOSED (a reopened issue is open)

@dataclasses.dataclass(frozen=True, slots=True)
class Release:                       # published releases only: drafts are not stored
    repo: str
    tag_name: str                    # unique per repository
    created_at: datetime.datetime
    published_at: datetime.datetime
    is_prerelease: bool

@dataclasses.dataclass(frozen=True, slots=True)
class WorkflowRun:                   # a GitHub Actions run, its latest attempt
    repo: str
    id: int
    workflow_path: str               # '.github/workflows/deploy.yml'
    name: str                        # the run's name (the workflow's name unless `run-name` sets it)
    event: str                       # 'push', 'pull_request', 'schedule', ...
    head_branch: str | None
    status: str                      # 'completed', 'in_progress', 'queued', ...
    conclusion: str | None           # 'success', 'failure', ...; None until completed
    created_at: datetime.datetime
    updated_at: datetime.datetime
    run_started_at: datetime.datetime | None   # start of the latest attempt
    run_attempt: int

@dataclasses.dataclass(frozen=True, slots=True)
class StarEvent:                     # a current stargazer of the repository (step 10)
    repo: str
    user_id: str                     # the stargazer's GraphQL node id: stable across renames, no login kept
    starred_at: datetime.datetime

@dataclasses.dataclass(frozen=True, slots=True)
class Fork:                          # a direct fork that still exists (step 10)
    repo: str                        # the repository forked, 'owner/name'
    id: int                          # the fork's REST repository id
    created_at: datetime.datetime

class Fetcher:
    def __init__(self, token: str, cache: Cache, settings: FetchSettings, *, client: GitHubClient | None = None) -> None:
        """`client` defaults to `GitHubClient(token, settings)`; tests pass one pointed at a replay server."""

    async def __aenter__(self) -> Fetcher: ...
    async def __aexit__(self, *exc_info: object) -> None:
        """Closes the aiohttp session."""

    async def sync(self, subject: Subject, resources: frozenset[str], full_refresh: bool = False,
                   *, progress: SyncProgress | None = None) -> SyncReport:
        """Bring the cache up to date for the subject: backfill on first use, otherwise only the delta.

        `resources` is a subset of RESOURCES; a name outside it raises ValueError.
        `progress`, when given, is updated as the sync runs: `repos_listed` and `repos_pending`
        once the unchanged repos are known, `rows_written` after each resource of a repo, and
        `repos_done` after each pending repo; at the end its counts equal the `SyncReport`'s."""

    async def repos(self, subject: Subject) -> list[Repo]:
        """From the cache: repositories owned by a user or org, excluding missing ones and
        applying the current fork and archived settings; a repo subject yields itself."""

    async def commits(self, repo: Repo, since: datetime.datetime | None, until: datetime.datetime | None) -> typing.AsyncIterator[Commit]:
        """From the cache: default-branch commits with `since <= authored_at < until`, oldest first."""

    async def provenance(self, subject: Subject, resources: frozenset[str]) -> dict[str, str]:
        """From the cache: `Cache.identity()`, `version_override_at` when recorded, and for each
        resource `fetched_at:<resource>`, the earliest `synced_at` (ISO UTC) over `repos(subject)`,
        or 'never' when one of them has no sync state for it. Stats copies it into
        `StatsResult.provenance`."""

    async def owner_kind(self, login: str) -> typing.Literal['user', 'org']:
        """Whether `login` is a user or an organisation: REST `GET /users/{login}`, whose
        `type` is `User` (-> 'user') or `Organization` (-> 'org'). A 404, or any other type,
        raises NotFoundError naming the login. Not ETag-cached and writes nothing."""

    async def pull_requests(self, repo: Repo, since: datetime.datetime | None) -> typing.AsyncIterator[PullRequest]:
        """From the cache: the repo's pull requests with `updated_at >= since` (all when None),
        by number. Every event of a pull request (created, reviewed, merged, closed) is at or
        before its `updated_at`, so this is a superset of those with an event since `since`."""
    async def issues(self, repo: Repo, since: datetime.datetime | None) -> typing.AsyncIterator[Issue]:
        """From the cache, as `pull_requests`."""
    async def releases(self, repo: Repo) -> typing.AsyncIterator[Release]:
        """From the cache: the repo's published releases, oldest `published_at` first (then
        `tag_name`). All of them: a release interval and a lead time reach before any range."""
    async def workflow_runs(self, repo: Repo, since: datetime.datetime | None) -> typing.AsyncIterator[WorkflowRun]:
        """From the cache: the repo's runs with `created_at >= since` (all when None), oldest
        `created_at` first (then `id`)."""
    async def star_events(self, repo: Repo) -> typing.AsyncIterator[StarEvent]:
        """From the cache: the repo's stargazers, oldest `starred_at` first (then `user_id`). All of
        them: a cumulative star count reaches back before any range."""
    async def stars_hidden(self, repo: Repo) -> bool:
        """From the cache: whether the repo's last star sync found its stargazers not visible to the token (its `star_events` state has the probe `STARS_HIDDEN`), so it has no star history (1.9)."""
    async def forks(self, repo: Repo) -> typing.AsyncIterator[Fork]:
        """From the cache: the repo's direct forks, oldest `created_at` first (then `id`), all of them."""

def resolve_token() -> str:
    """GITHUB_TOKEN from the environment, else `gh auth token`; raises AuthError if neither."""

def redact(text: str, token: str) -> str:
    """`text` with every occurrence of `token` replaced by `***`."""
```

The cache, used only inside `wambatic.fetch` and by the CLI's `cache` command. Its methods are synchronous; `Fetcher` calls them through `asyncio.to_thread`, and one `threading.Lock` serialises them on the cache's single connection (opened with `check_same_thread=False`):

```python
import pathlib

SCHEMA_VERSION: int = 4   # 2 from step 6: the pull_requests and issues tables; 3 from step 8, 4 from step 10: see Cache

# in base.py with the other records, so cache.py imports base.py and base.py needs cache.py
# only for annotations (under typing.TYPE_CHECKING): no import cycle
@dataclasses.dataclass(frozen=True, slots=True)
class SyncState:
    repo: str
    resource: str
    watermark: datetime.datetime | None   # unused for commits (see Incremental sync)
    head_oid: str | None                  # commits only
    pushed_at: datetime.datetime | None   # the repo's listed pushedAt this sync was made against
    updated_at: datetime.datetime         # the repo's listed updatedAt this sync was made against
    synced_at: datetime.datetime
    full_synced_at: datetime.datetime
    probe: str | None = None              # releases, star_events and forks: the listing's probe this sync was made against

class Cache:
    @classmethod
    def open(cls, path: pathlib.Path, *, ignore_version: bool = False) -> Cache:
        """Create the parent directory and file if absent, set WAL mode, create the schema,
        then check or write the identity; raises CacheVersionError on a mismatch unless
        `ignore_version`, which is recorded in `meta` as `version_override_at`."""
    def close(self) -> None: ...

    def identity(self) -> dict[str, str]:
        """The recorded `meta` rows except `version_override_at`."""
    def version_override_at(self) -> str | None:
        """The recorded `version_override_at`, or None when the identity matched."""
    def upsert_repos(self, owner: str, repos: list[Repo], *, complete: bool) -> None:
        """Insert or replace each repo; with `complete`, mark the owner's other repos missing."""
    def read_repos(self, subject: Subject) -> list[Repo]: ...
    def sync_state(self, repo: str, resource: str) -> SyncState | None: ...
    def write_commits(self, repo: str, commits: list[Commit], state: SyncState, *, replace: bool) -> int:
        """In one transaction: with `replace`, delete the repo's commits first; upsert by oid;
        write `state`. Returns the number of rows written."""
    def read_commits(self, repo: str, since: datetime.datetime | None, until: datetime.datetime | None) -> list[Commit]: ...
    def write_pull_requests(self, repo: str, pulls: list[PullRequest], state: SyncState, *, replace: bool) -> int:
        """As `write_commits`, upserting by number."""
    def read_pull_requests(self, repo: str, since: datetime.datetime | None) -> list[PullRequest]:
        """Rows with `updated_at >= since` (all when None), by number."""
    def write_issues(self, repo: str, issues: list[Issue], state: SyncState, *, replace: bool) -> int: ...
    def read_issues(self, repo: str, since: datetime.datetime | None) -> list[Issue]: ...
    def write_releases(self, repo: str, releases: list[Release], state: SyncState) -> int:
        """In one transaction: delete the repo's releases, insert these, write `state`. Every
        read of releases is a full read, so there is no `replace` flag."""
    def read_releases(self, repo: str) -> list[Release]: ...
    def write_workflow_runs(self, repo: str, runs: list[WorkflowRun], state: SyncState, *, replace: bool, gone: collections.abc.Collection[int] = ()) -> int:
        """As `write_commits`, upserting by `id`; also deletes the runs whose ids are in `gone`."""
    def read_workflow_runs(self, repo: str, since: datetime.datetime | None) -> list[WorkflowRun]:
        """Rows with `created_at >= since` (all when None), oldest first."""
    def unfinished_runs(self, repo: str) -> list[int]:
        """Ids of the repo's cached runs whose `status` is not `completed`, ascending."""
    def write_state(self, state: SyncState) -> None:
        """Write a `sync_state` row alone, in its own transaction (1.9)."""
    def write_star_events(self, repo: str, stars: list[StarEvent], state: SyncState, *, replace: bool) -> int:
        """As `write_commits`, upserting by `user_id` (step 10)."""
    def read_star_events(self, repo: str) -> list[StarEvent]:
        """Every row, oldest `starred_at` first, then `user_id`."""
    def write_forks(self, repo: str, forks: list[Fork], state: SyncState, *, replace: bool) -> int:
        """As `write_commits`, upserting by `id` (step 10)."""
    def read_forks(self, repo: str) -> list[Fork]:
        """Every row, oldest `created_at` first, then `id`."""
    def etag(self, url: str) -> tuple[str, object] | None:
        """The stored ETag and parsed body for a REST URL."""
    def store_etag(self, url: str, etag: str, body: object) -> None: ...

@dataclasses.dataclass(frozen=True, slots=True)
class CacheInfo:
    path: pathlib.Path
    size_bytes: int                                        # the file plus its -wal file
    identity: dict[str, str]                               # recorded `meta` rows, as Cache.identity()
    differences: dict[str, tuple[str | None, str | None]]  # key -> (recorded, running), as CacheVersionError
    version_override_at: str | None
    repos: int                                             # rows not marked missing
    commits: int
    pull_requests: int                                     # from step 6
    issues: int                                            # from step 6
    releases: int                                          # from step 8
    workflow_runs: int                                     # from step 8
    star_events: int                                       # from step 10
    forks: int                                             # from step 10
    last_synced_at: datetime.datetime | None               # latest `sync_state.synced_at`

def inspect_cache(path: pathlib.Path) -> CacheInfo | None:
    """None when `path` does not exist. Otherwise reads the file with plain SELECTs on its own
    connection: no schema creation, no identity check or write, no WAL pragma, so a cache that
    `Cache.open` refuses can still be inspected. A table absent from the file counts as 0 rows."""

def clear_cache(path: pathlib.Path) -> list[pathlib.Path]:
    """Delete `path` and its `-wal` and `-shm` files where present; return those deleted."""
```

The transport, used only inside `wambatic.fetch`:

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
    date: datetime.datetime | None = None   # the `Date` header, aware UTC; None when absent (1.6)

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

    async def graphql_dated(self, query: str, variables: collections.abc.Mapping[str, object]) -> tuple[dict[str, object], datetime.datetime]:
        """As `graphql`, with the response's `Date` header as an aware UTC datetime (added in 1.5
        for the watermark). A response without a parseable `Date` raises `GraphQLError`
        (`MALFORMED`). `graphql` returns the first item of this, so there is one request path."""

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
- `CacheVersionError`: the cache was written under a different schema or query version (see Cache). It names both versions and tells the user to run `wambatic cache clear` or pass `--ignore-cache-version`. It never warns and carries on, per the shared versions rule.
- REST `stats/*` returning 202 (still computing) is retried with backoff up to `fetch.stats_retries`, then raised as `StatsPendingError`.
- Transient failures (HTTP 500, 502, 503 and 504, `aiohttp.ClientConnectionError` and `TimeoutError`) are retried up to `fetch.max_retries` with the same backoff; when the retries run out the last exception propagates unchanged.
- Any other non-2xx status propagates as `aiohttp.ClientResponseError`.
- Unexpected exceptions propagate; only the above are caught.

## Implementation

**Transport.** One `aiohttp.ClientSession` per `Fetcher`, as the shared Python rules specify: a POST endpoint for GraphQL and conditional GETs for REST. Concurrency is bounded across repositories by an `asyncio.Semaphore` of `fetch.workers`, because GitHub asks clients to avoid concurrent request bursts ([best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)). SQLite calls run through `asyncio.to_thread` so the loop is never blocked. The CLI enters the loop once with `asyncio.run`.

**Requests, retries and rate limits.** Every request carries `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28` and `User-Agent: wambatic/<VERSION>`, with an `aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)` of 60 seconds. GitHub's documented handling ([REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit), [best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#handle-rate-limit-errors-appropriately)) is applied in this order to each response:

1. 401: `AuthError`.
2. 403 or 429 with a `retry-after` header: secondary limit; wait that many seconds, then retry.
3. 403 or 429 with `x-ratelimit-remaining: 0`: primary limit; handled as in step 6.
4. 403 or 429 whose JSON `message` contains `secondary rate limit`, with neither header: secondary limit; wait 60 seconds, then retry.
5. Any other 403: `AuthError`. 404: `NotFoundError`. Transient statuses: back off and retry.
6. *Primary limit.* The client keeps one `RateLimitState` for GraphQL and one for REST, each updated from the `x-ratelimit-*` headers of every response on its endpoint; a GraphQL response's `rateLimit` object, when present, then overrides the GraphQL state. If a primary-limit response leaves no `reset_at` to wait for, it is handled as a secondary limit with the 60-second wait. Before each request, and on a primary-limit response or a GraphQL `RATE_LIMITED` error, if the state is exhausted: with `fetch.on_rate_limit = 'fail'` raise `RateLimitError(reset_at)`; with `'wait'` log `ETA: GitHub rate limit resets in <duration>` at `info` and sleep until `reset_at` plus one second, then retry. Waiting for a primary reset does not count against `fetch.max_retries`. This is the whole of the pacing: there is no proactive slow-down while budget remains.

Backoff for transient failures and repeated secondary limits is full jitter ([AWS, Exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)) with `BACKOFF_BASE = 1.0` and `BACKOFF_CAP = 60.0` seconds; for a secondary limit the wait is the larger of the header or 60-second wait and the backoff delay. A REST 202 is retried after `backoff_delay` up to `fetch.stats_retries` times, then raises `StatsPendingError`. All waits go through the client's `sleep`.

Every query text in `queries.py` selects `rateLimit { cost remaining resetAt }`; a response with `data` and no `errors` that lacks it raises `GraphQLError`, so a query that forgot it fails its first test.

**GraphQL cost control.** Queries are built to stay under the 500,000-node cap and the 5,000-points/hour budget ([limits](https://docs.github.com/en/graphql/overview/rate-limits-and-node-limits-for-the-github-graphql-api)): 100 nodes per page, only requested fields, and `rateLimit { cost remaining resetAt }` on every query so the fetcher can pace itself. Per-commit `additions` and `deletions` come from the `Commit` object's history connection, or from `nodes(ids:)` for commits found by a compare; the REST `stats/code_frequency` endpoint is used only by the opt-in live test, as a cross-check of the summed line totals on a repo under 10,000 commits, and never at run time.

**Cache.** One SQLite file (`fetch.cache_path`, default `~/.cache/wambatic/cache.sqlite3`) in WAL mode. Tables: `meta(key, value)`, `repos`, `commits`, `pull_requests`, `issues`, `releases`, `workflow_runs`, `star_events`, `forks`, `etags(url, etag, body)`, and `sync_state(repo, resource, watermark, head_oid, pushed_at, updated_at, synced_at, full_synced_at)`. Each step creates only the tables its resources use; step 3 creates `meta`, `repos`, `commits`, `etags` and `sync_state`, and a later table is a `SCHEMA_VERSION` increase. Step 6 adds `pull_requests` and `issues` (primary key `(repo, number)`, indexed on `(repo, updated_at)`) and the `repos` columns `pull_requests_updated_at` and `issues_updated_at`, and sets `SCHEMA_VERSION` to 2, so a cache written before step 6 is refused once with the `CacheVersionError` message and is cleared and refetched; there is no migration. Step 8 adds `releases` (primary key `(repo, tag_name)`) and `workflow_runs` (primary key `(repo, id)`, indexed on `(repo, created_at)` and `(repo, status)`), the `pull_requests` columns `labels` (a JSON array of names) and `first_commit_at`, the `repos` columns `releases_count` and `releases_updated_at`, and the `sync_state` column `probe`, and sets `SCHEMA_VERSION` to 3, with the same refusal. Step 10 adds `star_events` (primary key `(repo, user_id)`, indexed on `(repo, starred_at)`) and `forks` (primary key `(repo, id)`, indexed on `(repo, created_at)`), the `repos` columns `stargazer_count`, `fork_count`, `watcher_count`, `languages` (a JSON array of `[name, bytes]` pairs, largest first) and `languages_size`, and sets `SCHEMA_VERSION` to 4, with the same refusal. Timestamps are stored as ISO 8601 UTC text. REST responses also store their `ETag` and are revalidated with `If-None-Match`, which does not count against the limit when answered 304; a 304 returns the stored body.

**Incremental sync.** The first query of a subject backfills everything; later queries fetch only what changed since the last successful sync. State is per repo and per resource, so asking for a new metric group later backfills only that resource.

1. *Subject level.* The repo list is always re-read (one cheap query per 100 repos, ordered by `PUSHED_AT` descending, selecting each repo's default branch and its head oid, and since 1.5 the `updatedAt` of its newest pull request and newest issue: `pullRequests(first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) { nodes { updatedAt } }` and the same for `issues`). A repo is skipped for a resource when that resource is unchanged by the rule below, and a repo skipped for every requested resource is skipped entirely, with no per-repo requests. `commits` is unchanged when the listed `pushedAt` and `updatedAt` equal the values recorded in its `sync_state` row. `pull_requests` and `issues` are unchanged when a `sync_state` row exists, no full re-read is due (step 5), and the listed newest `updatedAt` is `None` or earlier than `watermark - fetch.overlap`, the cutoff at which paging would stop on the first item. A repository's own `pushedAt` and `updatedAt` are not used for them, because nothing in GitHub's documentation says they move when an issue or a review changes. Since 1.6 the listing also selects `releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) { totalCount nodes { updatedAt } }`; its probe text is `"<totalCount> <updatedAt as ISO UTC, or none>"`. `releases` is unchanged when a `sync_state` row exists, no full re-read is due (step 5) and its `probe` equals the listed probe text: a release added or deleted changes the count, and publishing or editing the newest release (a draft kept by a release-drafting workflow is the usual newest) changes its `updatedAt`. An edit to an older release is seen at the next full re-read, an accepted limit. `workflow_runs` has no probe in GraphQL and is never unchanged: its first request is a conditional one that GitHub answers with 304 when nothing changed, which does not count against the rate limit, so a repo synced for `workflow_runs` is never skipped entirely, at no cost when it is unchanged. Since 1.8 the listing also selects `stargazerCount forkCount watchers { totalCount }` and `languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name } } }`, stored on the repo row as `stargazer_count`, `fork_count`, `watcher_count`, `languages` and `languages_size`, so the counts and the languages are refreshed by every sync, whatever its resources, at about one GraphQL point more per 100 repositories; a repository with more than 20 languages keeps the 20 largest, and the rest is `languages_size` less their sum. The star probe text is `str(stargazer_count)` and the fork probe text `str(fork_count)`. `star_events` (or `forks`) is unchanged when a `sync_state` row exists, no full re-read is due (step 5) and its `probe` equals the listed probe text. A star added and another removed between two syncs leave the count as it was, so that pair is seen at the next full re-read, an accepted limit; `forkCount` counts forks of forks as well, so it can change when no direct fork did, which costs one read that finds nothing. Comparing GitHub's values with GitHub's values avoids clock skew, and because those values are written in the same transaction as the rows (step 4 below), a repo whose sync was interrupted is never skipped. A repo not yet in the cache is backfilled; a repo gone from the list is marked `missing`, its rows kept. Forks and archived repos excluded by the current settings are neither listed nor synced. A repo subject reads its one repository with the same fields.
2. *Per resource.* Each resource has an incremental strategy that pages newest-first and stops at the watermark:
   - `commits`: immutable, so never refetched, and tracked by `head_oid` rather than a time watermark, because a time window misses commits that reach the default branch after their dates (a merge commit brings in branch commits with older committer dates, and `history(since:)` filters on those dates). The first sync, and any full refetch, pages the default branch's `history(first: 100)` from the head, selecting `oid`, `authoredDate`, `author { user { login } }`, `additions`, `deletions` and `parents { totalCount }`. When the listed head differs from the stored `head_oid`, REST `GET /repos/{owner}/{name}/compare/{stored}...{listed}` (paged with `per_page=100`) answers both questions at once: its `status` says whether the stored head is an ancestor (`ahead`), and its `commits` are exactly the commits reachable from the new head and not the old one, like `git log stored..listed`. Their `additions` and `deletions`, which the compare response does not carry per commit, come from one GraphQL `nodes(ids:)` query per 100 commits using each commit's `node_id`. A `status` of `diverged` or `behind`, or a 404 because the stored head no longer exists (force-push or rewritten history), fully refetches that repo's commits, replacing its rows. Rows are de-duplicated by `oid`. An empty repository (no default branch) is recorded with no commits and no `head_oid`.
   - `pull_requests` and `issues`: mutable. Paged ordered by `UPDATED_AT` descending, 100 per page, stopping at the first item whose `updatedAt` is earlier than `watermark - fetch.overlap` (with no watermark, or on a full re-read, every page is read); changed items are upserted by `(repo, number)`. Still-open items are therefore refreshed whenever they change. The queries are `PULL_REQUESTS` (`number state createdAt updatedAt mergedAt closedAt additions deletions author { __typename login }` and `reviews(first: 20, states: [APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED]) { nodes { submittedAt author { __typename login } } }`) and `ISSUES` (`number state createdAt updatedAt closedAt author { __typename login }`), each on `repository(owner:, name:)`. Since 1.6 `PULL_REQUESTS` also selects `labels(first: 20) { nodes { name } }` and `commits(first: 1) { nodes { commit { authoredDate } } }` (a pull request's commits are listed oldest first), stored as `labels` in GitHub's order and as `first_commit_at` (`None` when the list is empty); more than 20 labels keeps the first 20, an accepted limit. Adding or removing a label moves the pull request's `updatedAt`, so the incremental read sees it. An author whose `__typename` is `Bot` is stored as `<login>[bot]`, the form REST and `stats.bot_logins` use; a `null` author (a deleted account) is `None`. `merged_at` is kept only when `state` is `MERGED`, and `closed_at` only when `state` is not `OPEN`. `first_review_at` is the earliest `submittedAt` among the first 20 submitted reviews whose author is neither the pull request's author nor a `Bot`; a review whose author is `null` counts. More than 20 reviews by the author or bots before the first other review leaves it `None`, an accepted limit.
   - `releases`: mutable and few, so every read is a full read. The `RELEASES` query pages `repository(owner:, name:) { releases(first: 100, after:, orderBy: {field: CREATED_AT, direction: DESC}) { nodes { tagName createdAt publishedAt isDraft isPrerelease } } }` to the end and replaces the repo's rows with the releases that are not drafts and have a `publishedAt` (`Cache.write_releases`), in one transaction with a state whose `probe` is the listed probe text. Drafts are visible only to tokens with push access, so leaving them out makes the cache the same whoever's token fills it.
   - `workflow_runs`: REST `GET /repos/{owner}/{name}/actions/runs` with `per_page=100` and `exclude_pull_requests=true`, newest first, paged with `page`. No `created` filter is sent: GitHub's reference says a request filtered by `actor`, `branch`, `check_suite_id`, `created`, `event`, `head_sha` or `status` returns at most 1,000 results, and an unfiltered one has no such cap. The first page is requested through the ETag store (`Fetcher.rest_cached`), so an unchanged repo costs a free 304 whose stored body is processed again harmlessly; an incremental read stops at the first run whose `created_at` is earlier than `watermark - fetch.overlap`, and a first or full read reads every page. A 404 on the list (no Actions data for the repo) is read as an empty list, not `NotFoundError`, so one repo cannot fail an organisation's sync. Then each cached run that is not `completed` and was not in the pages read is re-read with `GET /repos/{owner}/{name}/actions/runs/{id}` (no ETag); a 404 there (the run was deleted) removes its row. The runs read, the re-read runs and the removed ids go in one transaction with the state (`Cache.write_workflow_runs`). A run's fields are `id`, `path` (as `workflow_path`), `name`, `event`, `head_branch`, `status`, `conclusion`, `created_at`, `updated_at`, `run_started_at` and `run_attempt`.
   - `star_events` (since 1.8): GraphQL, since the REST stargazer list gives a star's time only under a custom media type. The `STARGAZERS` query pages `repository(owner:, name:) { stargazers(first: 100, after:, orderBy: {field: STARRED_AT, direction: DESC}) { pageInfo { hasNextPage endCursor } edges { starredAt node { id } } } }`, newest first. Each edge is a `StarEvent` keyed by the stargazer's node id, so no login is stored and a renamed account stays one row. An incremental read stops at the first edge whose `starredAt` is earlier than `watermark - fetch.overlap` and upserts what it read. When the listed `stargazer_count` is lower than the count in the stored probe, a star was removed, which an incremental read cannot see, so the read is a full read that replaces the repo's rows (`replace=True`); a first sync, a full re-read (step 5) and `--full-refresh` are full reads too. The rows and a state whose `probe` is the listed probe text go in one transaction (`Cache.write_star_events`). *Hidden stargazers (since 1.9).* Whether a token can list a repository's stargazers depends on the token: a fine-grained token is refused, and a classic one lists them only for repositories it owns and gets an empty list, with no error, for anyone else's. A read of every star (no cutoff) that lists none for a repository whose listed `stargazer_count` is above zero, or whose first request GitHub refuses with a `FORBIDDEN` GraphQL error, is therefore not "no stars": no row is written or deleted, a warning is logged, and the repository's `star_events` state is written alone (`Cache.write_state`) with no watermark and the probe `STARS_HIDDEN`. That probe never equals a listed count, so the repository is not skipped as unchanged and the next sync, perhaps with another token, reads the stargazers again; a read that then lists them stores them and replaces the probe with the count as above. The count in a stored probe is read only when the probe is a number (`count_of_probe`), so `STARS_HIDDEN` is never read as a count that fell. A read that stops at a cutoff and lists no star is the normal case of no new star, not hidden stargazers.
   - `forks` (since 1.8): REST `GET /repos/{owner}/{name}/forks` with `sort=newest` and `per_page=100`, paged with `page`; each fork's `id` and `created_at` make a `Fork`. REST is used because the GraphQL `forks` connection filters by `ownerAffiliations`, defaulting to `OWNER` and `COLLABORATOR`, and its schema does not say what that filter keeps for another owner's forks, while the REST list is documented as the repository's forks. The probe has already said the forks changed, so the first page is a plain request, not through the ETag store. An incremental read stops at the first fork whose `created_at` is earlier than `watermark - fetch.overlap`; a listed `fork_count` lower than the stored probe's count makes it a full read that replaces the repo's rows, as for stars. A 404 on the list is read as no forks, as for workflow runs, so one repo cannot fail an organisation's sync. The rows and the state go in one transaction (`Cache.write_forks`).
   - Watchers and languages have no resource: they are the snapshot the listing carries (step 1). GitHub's `watchers` connection lists users with no time of watching, and a repository's languages have no history, so neither can be bucketed; REST's `watchers_count` is the star count under an older name and is not used.
3. *The watermark is a server-side timestamp* (for the time-windowed resources, from step 6) taken at the start of the sync, not the newest item seen, and the overlap (default one hour) absorbs clock skew and in-flight updates. For `pull_requests` and `issues` it is the `Date` header of the first page's response for that repo and resource (`GitHubClient.graphql_dated`): an item that changes while later pages are read has an `updatedAt` after it, so the next sync reads it. For `star_events` it is the `Date` header of the first `STARGAZERS` page (`graphql_dated`), and for `forks` that of the first REST page (`RestResponse.date`, with the same `MALFORMED` rule as `workflow_runs`). For `workflow_runs` it is the `Date` header of the first page's response, 200 or 304 (`RestResponse.date`; `Fetcher.rest_cached` returns it with the body); a response without a parseable `Date` raises `GraphQLError` (`MALFORMED`) as `graphql_dated` does, since there is no REST-specific malformed-response error.
4. *Atomic advance.* Rows and the new watermark are written in one SQLite transaction per repo and resource, only after the last page succeeds. An interrupted or rate-limited run leaves the old watermark, so the next run resumes from it and re-fetching is harmless because writes are upserts.
5. *Deletions cannot be seen incrementally* (deleted or transferred issues, removed stars, deleted forks, deleted releases). Each resource is therefore fully re-read when `now - full_synced_at > fetch.full_refresh_after`, or when the user passes `--full-refresh` (`sync(..., full_refresh=True)`). Commits are the exception to the interval: the compare above sees every rewrite, so they are fully re-read only on a rewrite or `--full-refresh`. Releases are always read in full (step 2), so for them the interval only forces a read the probe would skip. A full re-read of `workflow_runs` reads every page and replaces the repo's rows (`replace=True`), so a deleted run leaves the cache. A full re-read of `pull_requests` or `issues` reads every page and replaces the repo's rows in the same transaction as its state (`replace=True`), so an issue deleted or transferred on GitHub leaves the cache, and sets `full_synced_at` to now; an incremental read keeps the stored `full_synced_at`. `star_events` and `forks` follow the same rule, and are also read in full when their count falls (step 2).
6. *Offline and bounded.* `--no-fetch` renders from the cache alone; `--max-age` skips the network for a subject synced more recently than that.

**Cache identity.** `meta` records `schema_version` (`SCHEMA_VERSION` in `cache.py`), the wambatic version (`wambatic.version.VERSION`), and `query:<NAME>` = the SHA-256 hex digest of each query text constant in `queries.py`. A new file has its identity written; opening a file whose recorded identity differs in any key from the running code raises `CacheVersionError` naming each differing key with both values, unless `ignore_version` is passed. Provenance reads the same values from `Cache.identity()`.

**Secrets.** The token is read from the environment only, never written to the cache, logs or reports ([security rules](../../../.agents/claude/rules/security.md)). Requests are logged at `debug` as method, URL and status only, never headers. The client logs through `loguru.logger.patch(...)` with a patcher that applies `redact` to each record's message, so a token that reaches a message by any path is replaced by `***`.

**Testing.** Unit tests replay fixture responses from an `aiohttp.web.Application` served by `aiohttp.test_utils.TestServer`, which ships with aiohttp, and point `GitHubClient` at it with `api_url`; async tests run their body with `asyncio.run`, so no pytest async plugin is added. Fixture responses live in `src/tests/fixtures/fetch/` as Python modules. Successful responses are recorded once from the live API (date of recording in a comment, trimmed to the fields used, no token or personal data beyond public logins); error responses (401, 403, 404, 429, 202, `RATE_LIMITED`) are written from the shapes in GitHub's documentation, each with the page it came from. The opt-in live tests, skipped when `GITHUB_TOKEN` is unset and marked `live`, run one small query against the public `octocat` account, and sync `octocat/Hello-World` into a temporary cache and check that its summed non-merge additions and deletions equal the sums of REST `stats/code_frequency`. Sync tests drive `Fetcher` with a `GitHubClient` pointed at the replay server and a `Cache` in a temporary directory. `bin/record-fixtures.sh` makes the recordings: it sends wambatic's own queries and REST requests, trims REST bodies to the fields the fetcher reads (REST lists to a page of five), and writes `src/tests/fixtures/fetch/recorded.py` with the date, the wambatic version and the sha256 of each query text; a test fails when a query no longer matches its recorded hash, until the recorder is run again. The subjects are `octocat` (listing), `octocat/Hello-World` (repository, history, compare, commit nodes, REST repo), `miguelangellv/ha-gas-station-spain` (pull requests, issues, releases, workflow runs), the users `octocat` and `github`, one Copilot review page of `microsoft/vscode` (the type and login of an automatic reviewer), and a repository of the recording account for stargazers and forks, because a fine-grained token is refused the stargazers and a classic one lists only its own repositories' stargazers (an empty list elsewhere). The recording of 2026-10-30 confirmed that an automatic reviewer such as Copilot has the `Bot` type, that GraphQL gives a bot's login without `[bot]`, that a run's `path` is the short form (`.github/workflows/ci.yml`) with `name`, `status` and `run_started_at` present, that a repository with no recognised code has an empty `languages` connection (`totalSize` 0) rather than `null`, and that `forkCount` is larger than the REST list of direct forks. Variations no recording holds (a draft release, a queued run, a `null` languages connection) are built by the helpers in `responses.py` from the shapes in GitHub's documentation. The test upstream can serve a repository's stargazers as an empty list or as a `FORBIDDEN` error while its listed star count is unchanged. The opt-in live test also syncs `star_events` and `forks` for `octocat/Hello-World` and checks that rows are stored; it does not compare them with the listed counts, because the REST fork list of that repository holds more forks than its `forkCount`, and it skips the stars when the token is refused the stargazers (an Actions installation token).

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `fetch.cache_path` | `Path` | `~/.cache/wambatic/cache.sqlite3` | SQLite cache file |
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
