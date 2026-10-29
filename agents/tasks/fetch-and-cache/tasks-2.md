# Tasks: Fetch and cache

**Spec:** `agents/specs/fetch-and-cache/spec.md`
**Created:** 2026-10-29
**Version:** 2

This list builds step 3 of the [implementation order](../../specs/implementation-order.md), "Cache and incremental sync for repos and commits": the `Subject`, `Repo`, `Commit` and `SyncReport` records, the SQLite `Cache` with its identity check and `CacheVersionError`, ETag storage, `sync_state`, and `Fetcher` with `sync()`, `repos()` and `commits()`. It is written against version 1.2 of the spec, which settled what 1.1 left open for this step; the gaps, the choices made and the two decisions are in [review-1.md](../../specs/fetch-and-cache/review-1.md). Step 2's list, [tasks-1.md](tasks-1.md), built the `GitHubClient` transport this list wraps.

## Spec coverage

| Spec section | Covered by |
|--------------|------------|
| Module location (`cache.py`, `base.py`, `CacheVersionError` in `errors.py`) | Tasks 1, 2 and 5 |
| API: `Subject`, `RESOURCES`, `Repo`, `Commit`, `SyncState`, `SyncReport` | Task 1 |
| API: `Cache`, `SCHEMA_VERSION` | Tasks 2 and 3 |
| API: `Fetcher.__init__`, `__aenter__`, `__aexit__` | Task 5 |
| API: `Fetcher.sync` | Tasks 6 to 10 |
| API: `Fetcher.repos`, `Fetcher.commits` | Tasks 6 and 7 |
| API: `pull_requests`, `issues`, `releases`, `workflow_runs`, `star_events` and their records | steps 6 and 8 (`sync` raises `NotImplementedError` for them, Task 10) |
| Error handling: `CacheVersionError` | Task 2 |
| Implementation: Transport (`fetch.workers` semaphore, `asyncio.to_thread`) | Tasks 5 and 10 |
| Implementation: GraphQL cost control (100 per page, `nodes(ids:)`, `stats/code_frequency` only in the live test) | Tasks 4, 8 and 11 |
| Implementation: Cache (tables, WAL, ETags) | Tasks 2, 3 and 5 |
| Implementation: Incremental sync 1 (subject level) | Task 6 |
| Implementation: Incremental sync 2 (`commits`) | Tasks 7, 8 and 9 |
| Implementation: Incremental sync 2 (other resources), 3 (time watermark) | steps 6 and 8 |
| Implementation: Incremental sync 4 (atomic advance) | Tasks 3, 7 and 10 |
| Implementation: Incremental sync 5 (`full_refresh`) | Task 9 |
| Implementation: Incremental sync 6 (`--no-fetch`, `--max-age`) | step 5 (CLI) |
| Implementation: Cache identity | Task 2 |
| Implementation: Secrets (no token in the cache) | Tasks 2 and 3 |
| Implementation: Testing | Tasks 4, 5 and 11 |
| Settings: `cache_path`, `include_forks`, `include_archived`, `workers` | Tasks 5, 6 and 10 |
| Settings: `full_refresh_after`, `overlap`, `max_age` | steps 5, 6 and 8 (commits do not use them, spec 1.2) |
| Implementation order step 3 "Done when" | Tasks 9, 10 and 11; checked in Task 12 |

The spec's `**Status:**` is not changed by this list: pull requests, issues, releases, workflow runs and star events are built by the step 6 and step 8 lists, and the last of them sets it to `implemented`.

## Conventions for every task

- Async tests are plain `def test_...() -> None` functions whose body calls `asyncio.run(...)` on an inner coroutine; no pytest async plugin is added (spec, Testing).
- Tests never really sleep: `GitHubClient` gets the recording fake `sleep`, a fixed `clock` and a seeded `rng`, as the `make_client` fixture in `src/tests/conftest.py` already does.
- Every cache in a test lives under pytest's `tmp_path`; no test touches `~/.cache`.
- Tests never print, log or assert on the real token. Use the literal `'test-token'` in unit tests.
- Fixtures written from GitHub's documentation carry a comment with the documentation URL they came from; recorded ones carry the recording date.
- Times are timezone-aware UTC everywhere; the cache stores them as ISO 8601 text and reads them back aware.
- `gitstat.fetch` modules import nothing from gitstat outside `gitstat.fetch`, `gitstat.settings` and `gitstat.version`; `src/tests/test_layering.py` enforces it.

---

## Task 1: Records and subject

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** API (`Subject`, `RESOURCES`, `Repo`, `Commit`, `SyncReport`); Module location (`base.py`)

**Technical Goal:** Define the frozen record types every later task passes between the cache, the fetcher and Stats.

**Subtasks:**

- [ ] Add `src/gitstat/fetch/base.py` with `Subject`, `RESOURCES`, `Repo`, `Commit`, `SyncState` and `SyncReport` exactly as the spec's API (frozen, slotted dataclasses; field names, types and defaults as written)
- [ ] `Subject.__post_init__` raises `ValueError` when `kind == 'repo'` and `name` is `None`, or when `kind != 'repo'` and `name` is not `None`
- [ ] Add a `Subject.full_name` property returning `'login/name'` for a repo subject and raising `ValueError` otherwise
- [ ] Write `src/tests/fetch/test_base.py`: valid subjects of each kind construct; the invalid combinations raise `ValueError`; records are immutable (`dataclasses.FrozenInstanceError`); `RESOURCES` holds exactly the six names in the spec

**Acceptance Criteria:**

- [ ] `base.py` performs no I/O and imports nothing from gitstat (`Fetcher` and its imports are added in Task 5)
- [ ] `Commit` has `is_merge`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_base.py` passes

**Notes:**

- Depends on tasks-1.md Task 13 (step 2), done
- Key files: `src/gitstat/fetch/base.py`, `src/tests/fetch/test_base.py`

---

## Task 2: Cache file, schema and identity

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`Cache.open`, `close`, `identity`, `SCHEMA_VERSION`); Error handling (`CacheVersionError`); Implementation (Cache; Cache identity; Transport: one connection, `threading.Lock`)

**User Story:** As a gitstat user, I want gitstat to refuse a cache written by a different version of itself and tell me how to fix it, so that a report never silently mixes data fetched under two query or schema versions.

**Subtasks:**

- [ ] Add `CacheVersionError(FetchError)` to `src/gitstat/fetch/errors.py`, built from a `dict[str, tuple[str | None, str]]` of differing keys to (recorded, running) values; the message names each key with both values and says to run `gitstat cache clear` or pass `--ignore-cache-version`
- [ ] Add `src/gitstat/fetch/cache.py` with `SCHEMA_VERSION = 1` and `Cache` holding one `sqlite3.Connection` opened with `check_same_thread=False` and a `threading.Lock` taken by every public method
- [ ] `Cache.open(path, *, ignore_version=False)`: create the parent directory, connect, `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, create `meta(key TEXT PRIMARY KEY, value TEXT)`, `repos`, `commits`, `etags` and `sync_state` with `CREATE TABLE IF NOT EXISTS`
- [ ] Table columns: `repos(name_with_owner PRIMARY KEY, owner, default_branch, head_oid, is_archived, is_fork, pushed_at, updated_at, missing)`; `commits(repo, oid, authored_at, author_login, additions, deletions, is_merge, PRIMARY KEY (repo, oid))` with an index on `(repo, authored_at)`; `etags(url PRIMARY KEY, etag, body)` with `body` as JSON text; `sync_state(repo, resource, watermark, head_oid, pushed_at, updated_at, synced_at, full_synced_at, PRIMARY KEY (repo, resource))`
- [ ] `expected_identity()`: `schema_version`, `gitstat_version` from `gitstat.version.VERSION`, and `query:<NAME>` = `hashlib.sha256(text.encode()).hexdigest()` for every module-level `str` constant in `gitstat.fetch.queries`, iterated the same way `src/tests/fetch/test_queries.py` iterates them
- [ ] On open: an empty `meta` gets the expected identity written in one transaction; otherwise compare every key in either set and raise `CacheVersionError` on any difference, closing the connection first; with `ignore_version=True`, write `version_override_at` (UTC ISO now) to `meta` and continue
- [ ] `identity()` returns the recorded `meta` rows except `version_override_at`
- [ ] Write `src/tests/fetch/test_cache.py`: a new file is created in WAL mode with the expected identity; reopening succeeds; a changed `schema_version`, `gitstat_version` or query hash (monkeypatch the module constant or add a query constant) raises `CacheVersionError` naming that key and both values; `ignore_version=True` opens and records `version_override_at`; no column or `meta` value contains `'test-token'` after a test that ran a fetcher with that token (move this assertion to Task 10 if no fetcher exists yet, and say so in that task)

**Acceptance Criteria:**

- [ ] A mismatch is never a warning: it raises, or opens only with the explicit override, which is recorded
- [ ] Adding a query constant to `queries.py` changes the expected identity without editing `cache.py`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_cache.py src/tests/fetch/test_errors.py` passes

**Notes:**

- Depends on Task 1
- The override and error follow `.agents/claude/rules/versions.md`: record, check where saved work meets the running code, refuse a mismatch.
- `sqlite3` is stdlib; no dependency is added.
- Key files: `src/gitstat/fetch/cache.py`, `src/gitstat/fetch/errors.py`, `src/tests/fetch/test_cache.py`, `src/tests/fetch/test_errors.py`

---

## Task 3: Cache reads and atomic writes

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`Cache.upsert_repos`, `read_repos`, `sync_state`, `write_commits`, `read_commits`, `etag`, `store_etag`); Implementation (Incremental sync 1 and 4; Cache: ETags)

**Technical Goal:** Give the fetcher one cache call per unit of work, each a single transaction, so rows and their sync state advance together or not at all.

**Subtasks:**

- [ ] `upsert_repos(owner, repos, *, complete)`: insert or replace each repo with `missing = 0`; with `complete=True`, set `missing = 1` on the owner's other rows; one transaction
- [ ] `read_repos(subject)`: a repo subject returns its one row (or `[]`); a user or org subject returns the rows whose `owner` is `subject.login`, ordered by `name_with_owner`; rows map back to `Repo` with aware datetimes and bools
- [ ] `sync_state(repo, resource)` returns a `SyncState` or `None`
- [ ] `write_commits(repo, commits, state, *, replace)`: in one transaction, with `replace` delete the repo's commit rows, then `INSERT ... ON CONFLICT (repo, oid) DO UPDATE` each commit, then insert or replace the `sync_state` row; return the number of commits written
- [ ] `read_commits(repo, since, until)`: rows with `since <= authored_at < until` (either bound optional), ordered by `authored_at` then `oid`
- [ ] `etag(url)` and `store_etag(url, etag, body)` with `body` stored as JSON text
- [ ] Write tests in `src/tests/fetch/test_cache.py`: repos round-trip exactly; `complete=True` marks absent repos missing and keeps their commits; commit upsert by `oid` is idempotent (writing the same list twice leaves one row per oid); `replace=True` removes commits not in the new list; an exception raised mid-write (monkeypatch the state insert to raise) leaves both the commit rows and the previous `sync_state` unchanged; `read_commits` respects half-open bounds; ETag round-trips
- [ ] Write a hypothesis test (`@settings(max_examples=20, deadline=10000)`) that for any list of commits with repeated oids, `write_commits` followed by `read_commits(repo, None, None)` returns one commit per distinct oid, equal to the last written for that oid

**Acceptance Criteria:**

- [ ] Every write method is one SQLite transaction
- [ ] No method blocks on a lock held by another method for longer than its own query (no nested lock acquisition)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_cache.py` passes

**Notes:**

- Depends on Task 2
- `sqlite3` connections used as context managers commit or roll back the transaction ([sqlite3 docs](https://docs.python.org/3.14/library/sqlite3.html#sqlite3-connection-context-manager)); they do not close the connection.
- Key files: `src/gitstat/fetch/cache.py`, `src/tests/fetch/test_cache.py`

---

## Task 4: Queries and fixtures for repos and commits

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** Implementation (GraphQL cost control; Incremental sync 1 and 2: the fields read; Testing)

**Technical Goal:** Write every query step 3 sends and the canned responses its tests replay, so Tasks 6 to 10 only parse.

**Subtasks:**

- [ ] In `src/gitstat/fetch/queries.py`, extend `OWNER_REPOSITORIES` to order by `{field: PUSHED_AT, direction: DESC}` and select per node `nameWithOwner isArchived isFork pushedAt updatedAt defaultBranchRef { name target { oid } }`, keeping `pageInfo` and `rateLimit`
- [ ] Add `REPOSITORY`: `repository(owner: $owner, name: $name)` selecting the same node fields, plus `rateLimit { cost remaining resetAt }`
- [ ] Add `COMMIT_HISTORY`: `repository(owner:, name:) { defaultBranchRef { target { ... on Commit { history(first: 100, after: $cursor) { pageInfo { hasNextPage endCursor } nodes { oid authoredDate author { user { login } } additions deletions parents { totalCount } } } } } } }` plus `rateLimit`
- [ ] Add `COMMIT_NODES`: `nodes(ids: $ids) { ... on Commit { oid additions deletions } }` plus `rateLimit`
- [ ] Update `src/tests/fetch/test_live.py` only if the `OWNER_REPOSITORIES` variables change (they should not)
- [ ] First check `[ -n "${GITHUB_TOKEN:-}" ]`, printing only yes or no (shared security rule). If a token is set and `api.github.com/graphql` answers, record one response each for `OWNER_REPOSITORIES` (`login: 'octocat'`), `REPOSITORY` and `COMMIT_HISTORY` (`octocat/Hello-World`), one REST `GET /repos/octocat/Hello-World/compare/{base}...{head}` between two real commits of it, and one `COMMIT_NODES` for those commits; trim to the selected fields, put the recording date in a comment, replace the hand-written `OWNER_REPOSITORIES_OK` and `REPO` stand-ins, and update the module docstring of `src/tests/fixtures/fetch/responses.py`
- [ ] If no token is set or GraphQL is refused (the cloud sandbox refuses it, see tasks-1.md Task 7), write those fixtures from the shapes in GitHub's documentation ([GraphQL objects](https://docs.github.com/en/graphql/reference/objects#commit), [compare two commits](https://docs.github.com/en/rest/commits/commits#compare-two-commits)) with the URL in a comment, record the deviation and date in this task's Notes, and leave the module docstring saying the stand-ins still need recording
- [ ] In `src/tests/fixtures/fetch/responses.py`, add builders that the sync tests need and that a recording cannot supply: `history_page(commits, has_next, cursor)`, `compare_response(status, commits)` and `owner_page(repos, has_next, cursor)`, each producing the same shape as the recorded or documented response
- [ ] Extend `src/tests/fetch/test_queries.py`: every new constant contains `rateLimit { cost remaining resetAt }` (already automatic) and every `history` or `repositories` connection asks for `first: 100`

**Acceptance Criteria:**

- [ ] No query requests a field the fetcher does not read
- [ ] Every fixture states whether it was recorded (with date) or written from documentation (with URL)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_queries.py src/tests/fetch/test_client.py` passes

**Notes:**

- Depends on Task 1
- Changing a query text changes the cache identity (Task 2); that is intended.
- `test_client.py` replays `OWNER_REPOSITORIES_OK`; keep its assertions passing when the fixture gains fields.
- GitHub documentation was not reachable from the planning session, so the field names above are from the documentation as known; a recorded response or a GraphQL error naming an unknown field settles any difference, and the query is corrected to match.
- Key files: `src/gitstat/fetch/queries.py`, `src/tests/fixtures/fetch/responses.py`, `src/tests/fetch/test_queries.py`

---

## Task 5: `Fetcher` shell and cached REST

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** API (`Fetcher.__init__`, `__aenter__`, `__aexit__`); Implementation (Transport: one session, `asyncio.to_thread`, `fetch.workers`; Cache: ETag revalidation)

**Technical Goal:** Build the object that owns the client and the cache, so every sync task adds a method to it rather than plumbing.

**Subtasks:**

- [ ] Add `Fetcher` to `src/gitstat/fetch/base.py` with the spec's `__init__(token, cache, settings, *, client=None)`; build `GitHubClient(token, settings)` when `client` is `None`; hold an `asyncio.Semaphore(settings.workers)`
- [ ] `__aenter__` enters the client and returns `self`; `__aexit__` exits it; the cache is the caller's to close
- [ ] Add an internal `db(fn, *args, **kwargs)` coroutine that runs a `Cache` method through `asyncio.to_thread`
- [ ] Add an internal `rest_cached(path, params)` that sends the stored ETag for the URL (path plus sorted query string) through `client.rest_get`, stores a 200's ETag and body, and returns the stored body on a 304
- [ ] Add a `fetcher` fixture factory to `src/tests/conftest.py` that builds a `Cache` under `tmp_path` and a `Fetcher` around `make_client(server)`
- [ ] Write `src/tests/fetch/test_fetcher.py`: entering and leaving the fetcher opens and closes the client session; `rest_cached` sends no `If-None-Match` the first time, sends the stored ETag the second time, and returns the first body when the server answers 304

**Acceptance Criteria:**

- [ ] `Fetcher` never calls a `Cache` method on the event loop thread
- [ ] A 304 costs no rate limit and returns the stored body

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_fetcher.py src/tests/fetch/test_base.py` passes

**Notes:**

- Depends on Task 3
- `cache.py` imports `gitstat.fetch.base` for the records; `base.py` imports `gitstat.fetch.cache` only under `typing.TYPE_CHECKING` (it receives a `Cache`, never builds one), and imports `gitstat.fetch.client` at run time. This keeps the import graph acyclic (spec 1.2, the comment on `SyncState`).
- Key files: `src/gitstat/fetch/base.py`, `src/tests/fetch/test_fetcher.py`, `src/tests/conftest.py`

---

## Task 6: Repo listing and the skip rule

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`Fetcher.repos`); Implementation (Incremental sync 1); Settings (`include_forks`, `include_archived`); Error handling (`NotFoundError`)

**User Story:** As a gitstat user reporting on an organisation, I want each run to re-read the repo list cheaply and skip repos that have not changed, so that a large org costs a few requests when nothing happened.

**Subtasks:**

- [ ] Add an internal `list_repos(subject) -> list[Repo]`: for a user or org, page `OWNER_REPOSITORIES` until `hasNextPage` is false; for a repo subject, one `REPOSITORY` query; map each node to `Repo` (`head_oid` and `default_branch` `None` when `defaultBranchRef` is null)
- [ ] Drop forks unless `settings.include_forks` and archived repos unless `settings.include_archived`
- [ ] Store the listing with `upsert_repos(owner, repos, complete=True)` for a user or org subject and `complete=False` for a repo subject
- [ ] A `NotFoundError` from either query propagates unchanged (step 2 raises it)
- [ ] Add an internal `unchanged(repo, resources) -> bool`: true when every resource has a `sync_state` whose `pushed_at` and `updated_at` equal the listed repo's
- [ ] Implement `repos(subject)` from `Cache.read_repos`, excluding `missing` rows and applying the current fork and archived settings; no network
- [ ] Write tests in `src/tests/fetch/test_fetcher.py`: a two-page owner listing is read fully and stored; forks and archived repos are dropped by default and kept when the settings say so; a repo absent from a later listing is marked missing and absent from `repos()` while its commits stay in the cache; `repos()` makes no request (the replay server records none); `unchanged` is false with no state, true when both values match, and false when either differs; a repo subject that does not exist raises `NotFoundError`

**Acceptance Criteria:**

- [ ] The skip rule compares only values GitHub reported, never the local clock
- [ ] `repos()` reaches no network

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_fetcher.py` passes

**Notes:**

- Depends on Task 4, Task 5
- Missing repos are left out of `repos()` per review-1.md choice 6.
- Key files: `src/gitstat/fetch/base.py`, `src/tests/fetch/test_fetcher.py`

---

## Task 7: Commit backfill and `commits()`

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`Fetcher.commits`); Implementation (Incremental sync 2, `commits`: first sync; 4 atomic advance); Implementation (GraphQL cost control)

**User Story:** As a gitstat user, I want the first run on a repo to read its whole default-branch history with lines added and deleted per commit, so that every later report has complete totals.

**Subtasks:**

- [ ] Add an internal `backfill_commits(repo) -> int`: page `COMMIT_HISTORY` from the head until `hasNextPage` is false, mapping each node to `Commit` (`authored_at` from `authoredDate`, `author_login` from `author.user.login` or `None`, `is_merge = parents.totalCount > 1`), collecting pages in memory
- [ ] After the last page, call `write_commits(repo, commits, state, replace=True)` once, with `state.head_oid = repo.head_oid` (the head listed before paging), the listed `pushed_at` and `updated_at`, `watermark=None`, and `synced_at` and `full_synced_at` from the client's clock
- [ ] An empty repository (`default_branch is None`) writes no commits and a state with `head_oid=None`, without a history request
- [ ] Implement `commits(repo, since, until)` as an async iterator over `Cache.read_commits`; no network
- [ ] Write tests in `src/tests/fetch/test_fetcher.py`: a three-page history is stored in full with the right `is_merge` flags and author logins (one `None`); `commits()` yields them oldest first and honours `since`/`until`; an error on page two (canned 500 repeated past `max_retries`) leaves no commit rows and no `sync_state`; an empty repo stores a state and no commits

**Acceptance Criteria:**

- [ ] Rows and state are written only after the last page succeeds
- [ ] `commits()` reaches no network

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_fetcher.py` passes

**Notes:**

- Depends on Task 6
- The head is taken from the listing, not from the history's first node, so a push during paging is caught as a changed head on the next run (Task 8) rather than lost.
- Key files: `src/gitstat/fetch/base.py`, `src/tests/fetch/test_fetcher.py`

---

## Task 8: Incremental commits by compare

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** Implementation (Incremental sync 2, `commits`: compare from the stored head; GraphQL cost control: `nodes(ids:)`)

**Technical Goal:** Fetch exactly the commits that reached the default branch since the last sync, including merged-in commits with older dates, at one REST and one GraphQL request per 100 new commits.

**Subtasks:**

- [ ] Add an internal `update_commits(repo, state) -> int | None`: when `repo.head_oid == state.head_oid`, write nothing and return 0
- [ ] Otherwise page `rest_cached(f'/repos/{name_with_owner}/compare/{state.head_oid}...{repo.head_oid}', {'per_page': '100', 'page': str(n)})` until a page returns fewer than 100 commits or `total_commits` are collected; the compare `status` comes from the first page
- [ ] On `status == 'identical'` write only the new state; on `'ahead'` map each compare commit to a partial record (`oid`, `node_id`, `commit.author.date`, `author.login` or `None`, `is_merge = len(parents) > 1`)
- [ ] Fill `additions` and `deletions` with one `COMMIT_NODES` query per 100 `node_id`s; a node missing from the response raises `GraphQLError` naming the oid, so no commit is stored with invented counts
- [ ] Write the new commits with `write_commits(..., replace=False)` and a state carrying the new `head_oid`, listed `pushed_at`/`updated_at`, the old `full_synced_at` and a new `synced_at`
- [ ] Return `None` (meaning "refetch") on `status` `diverged` or `behind`, and on `NotFoundError` from the compare; Task 9 acts on it
- [ ] Write tests in `src/tests/fetch/test_fetcher.py`: an unchanged head sends no request; an `ahead` compare with two new commits, one dated before the previous sync (a merged-in branch commit), stores both with their line counts; a compare spanning two pages is read fully; `identical` advances only the state; `diverged`, `behind` and a 404 each return `None` and write nothing

**Acceptance Criteria:**

- [ ] A commit dated before the last sync but new to the branch is stored (the case review-1.md Decision 1 is about)
- [ ] No commit is stored without its additions and deletions

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_fetcher.py` passes

**Notes:**

- Depends on Task 7
- Implements review-1.md Decision 1, answered A (compare from the stored head) on 2026-10-29.
- `rest_get` takes a path, so the `page` parameter is passed explicitly rather than following `next_url`.
- Key files: `src/gitstat/fetch/base.py`, `src/tests/fetch/test_fetcher.py`

---

## Task 9: Rewritten history and full refresh

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** Implementation (Incremental sync 2, `commits`: rewritten history; 5 `full_refresh`); implementation order step 3 "Done when" (a simulated force-push triggers a full refetch)

**User Story:** As a gitstat user whose team force-pushes the default branch, I want gitstat to notice and re-read that repo's history, so that commits that no longer exist stop counting.

**Subtasks:**

- [ ] Add an internal `sync_commits(repo, full_refresh) -> tuple[int, bool]` returning rows written and whether a full refetch happened: with no state or `full_refresh`, backfill (Task 7); otherwise `update_commits` (Task 8), and backfill when it returns `None`
- [ ] Log each full refetch at `info` with the repo name and the reason (`no previous sync`, `full refresh requested`, `history rewritten`)
- [ ] Write tests in `src/tests/fetch/test_fetcher.py`: a simulated force-push (stored head `A`, listed head `B`, compare answers `diverged`) re-reads the history and leaves only the new history's commits; a 404 compare (old head gone) does the same; `full_refresh=True` re-reads a repo whose head is unchanged; neither path runs `update_commits` twice

**Acceptance Criteria:**

- [ ] After a rewrite, commits only in the old history are gone from the cache
- [ ] A rewrite is never handled by appending

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_fetcher.py` passes

**Notes:**

- Depends on Task 8
- Commits are not re-read on the `fetch.full_refresh_after` interval (spec 1.2, Incremental sync 5).
- Key files: `src/gitstat/fetch/base.py`, `src/tests/fetch/test_fetcher.py`

---

## Task 10: `sync()` across repos

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`Fetcher.sync`, `SyncReport`); Implementation (Transport: `fetch.workers` semaphore; Incremental sync 1 and 4); implementation order step 3 "Done when" (a second run fetches nothing; an interrupted run resumes)

**User Story:** As a gitstat user, I want one call to bring a user, repo or org up to date, with bounded concurrency and a summary of what it did, so that a second run right after the first costs only the repo listing.

**Subtasks:**

- [ ] Implement `sync(subject, resources, full_refresh=False)`: a name outside `RESOURCES` raises `ValueError` naming it; any resource other than `commits` raises `NotImplementedError` naming the step that builds it, before any request
- [ ] List repos (Task 6); for each listed repo that is not `unchanged` (or every repo when `full_refresh`), run `sync_commits` under the semaphore with `asyncio.TaskGroup`
- [ ] Return a `SyncReport` with repos listed, repos skipped, `rows_written={'commits': n}` and the names fully refetched, in alphabetical order
- [ ] An exception in one repo's sync propagates (the task group cancels the rest); repos already written keep their new state and rows
- [ ] Write tests in `src/tests/fetch/test_fetcher.py`:
  - [ ] Second run: sync an owner with two repos from fixtures, then sync again with the same listing; the second run's server log holds only the listing query and the report says both were skipped
  - [ ] Interrupted run: the first sync fails on repo B's history (repeated 500 past `max_retries`); the second sync, with B's history now answering, fetches only B, and A is skipped
  - [ ] Concurrency: with `workers=2` and four repos whose history responses are delayed, no more than two history requests are in flight at once (count in the replay handler)
  - [ ] `ValueError` for `'nonsense'`, `NotImplementedError` for `'issues'`, both with no request sent
  - [ ] No `meta`, `repos`, `commits`, `etags` or `sync_state` value contains `'test-token'` after a sync (moved here from Task 2 if that task could not run it)
- [ ] If the replay server cannot delay or count in-flight requests, add that to `src/tests/fixtures/fetch/server.py` (a per-canned-response `delay` field) with a test in a new `src/tests/fetch/test_server.py`

**Acceptance Criteria:**

- [ ] A repeat sync with no upstream change sends only the listing request(s)
- [ ] At most `fetch.workers` repos are synced at once

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_fetcher.py` passes, plus `src/tests/fetch/test_server.py` if written

**Notes:**

- Depends on Task 9
- "A second run fetches nothing" in the implementation order means no per-repo requests: the spec re-reads the repo list on every sync.
- Key files: `src/gitstat/fetch/base.py`, `src/tests/fetch/test_fetcher.py`, `src/tests/fixtures/fetch/server.py`

---

## Task 11: Live check of line totals

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** Implementation (Testing: the opt-in live tests; GraphQL cost control: `stats/code_frequency` in the live test only); implementation order step 3 "Done when" (line totals match `stats/code_frequency`)

**Technical Goal:** Show once against the real API that per-commit line counts summed over a small repo agree with GitHub's own weekly totals.

**Subtasks:**

- [ ] Add `test_line_totals_match_code_frequency` to `src/tests/fetch/test_live.py`, marked `live` and skipped without a token like the existing test: open a `Cache` under `tmp_path`, sync `Subject('repo', 'octocat', 'Hello-World')` for `commits`, sum `additions` and `deletions` over non-merge commits, and compare with the sums of columns 1 and 2 (column 2 negated) of `rest_get('/repos/octocat/Hello-World/stats/code_frequency')`
- [ ] Run `pytest -m live -rs src/tests/fetch/test_live.py` once. If it skips or GraphQL is refused, record that with the date in this task's Notes; the CI `live` job runs it with the workflow token on the PR
- [ ] If the totals differ, do not loosen the assertion: stop the task as `blocked`, recording both pairs of totals and the repo's merge commits in this task's Notes, for the user to decide whether the endpoint counts merges differently

**Acceptance Criteria:**

- [ ] The test compares exact totals
- [ ] `pytest -m 'not live' src/tests/fetch/test_live.py` selects nothing

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_live.py` passes or skips
- [ ] the PR's CI `live` job passes

**Notes:**

- Depends on Task 10
- Implements review-1.md Decision 2, answered A (live test only) on 2026-10-29.
- GitHub returns 202 while it computes the statistics; step 2's `stats_retries` handling waits for it.
- Key files: `src/tests/fetch/test_live.py`

---

## Task 12: Exports and closing checks

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** Module location; API; system spec API (`Subject`, `Fetcher` re-exported from `gitstat`); implementation order step 3 "Done when"

**Technical Goal:** Expose the step 3 names, confirm the layering still holds, run every test this list can affect, and mark the step done.

**Subtasks:**

- [ ] In `src/gitstat/fetch/__init__.py`, add `Cache`, `CacheVersionError`, `Commit`, `Fetcher`, `RESOURCES`, `Repo`, `Subject` and `SyncReport` to the imports and `__all__`, alphabetically
- [ ] In `src/gitstat/__init__.py`, re-export `Fetcher` and `Subject` and add them to `__all__` (system spec, API)
- [ ] Extend `src/tests/test_package.py` to check that every name in `gitstat.__all__` and `gitstat.fetch.__all__` resolves
- [ ] Confirm `src/tests/test_layering.py` passes with the new modules
- [ ] Check the implementation order's "Done when" for step 3: second run (Task 10), interrupted run (Task 10), simulated force-push (Task 9), live line totals (Task 11, or its recorded skip and the CI `live` result)
- [ ] Run every test that imports a changed module directly or transitively: `pytest src/tests/fetch src/tests/test_package.py src/tests/test_layering.py`
- [ ] In `agents/specs/implementation-order.md`, set step 3's Status to `done: [tasks-2](../tasks/fetch-and-cache/tasks-2.md)`

**Acceptance Criteria:**

- [ ] `import gitstat; gitstat.Fetcher; gitstat.Subject` works
- [ ] Every step 3 "Done when" item is met, or its gap is recorded in the task that owns it

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch src/tests/test_package.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Tasks 1 to 11
- The project has no affected-tests tool; the command above names every test file that reaches a module this list changed (outside `src/tests/fetch/`, `gitstat` and `gitstat.fetch` are imported only by `src/tests/test_package.py` and checked by `src/tests/test_layering.py`).
- The fetch spec's `**Status:**` stays `proposed` (see the header).
- Key files: `src/gitstat/fetch/__init__.py`, `src/gitstat/__init__.py`, `src/tests/test_package.py`, `agents/specs/implementation-order.md`

---
