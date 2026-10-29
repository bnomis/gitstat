# Tasks: Fetch and cache

**Spec:** `agents/specs/fetch-and-cache/spec.md`
**Created:** 2026-10-29
**Version:** 1

This list builds step 2 of the [implementation order](../../specs/implementation-order.md), "Fetch core": the typed errors, token resolution and redaction, rate-limit accounting and backoff, and the aiohttp transport `GitHubClient` with its GraphQL and REST request paths. It is written against version 1.1 of the spec, which settled the gaps version 1.0 left for this step (where `Fetcher` and `Cache` arrive, the error for other GraphQL errors and for a 403 that is not a rate limit, which failures are transient, the backoff curve, what pacing means, how logs are redacted and how tests replay responses). The rest of the spec is delivered by the step 3 list and later ones, as mapped below.

## Spec coverage

| Spec section | Covered by |
|--------------|------------|
| Module location | Task 1 (test layout); Tasks 2, 3, 4, 5 and 7 (`errors.py`, `auth.py`, `ratelimit.py`, `client.py`, `queries.py`); `cache.py` and `base.py` in the step 3 list |
| API: `resolve_token`, `redact` | Task 3 |
| API: `RateLimitState`, `backoff_delay` | Task 4 |
| API: `GitHubClient`, `RestResponse` | Tasks 5 to 11 |
| API: `Subject`, records, `Fetcher` and its methods | step 3 list onwards (`Fetcher` wraps `GitHubClient`) |
| Error handling: `FetchError`, `AuthError`, `NotFoundError`, `RateLimitError`, `StatsPendingError`, `GraphQLError` | Task 2 (classes); Tasks 6, 7, 9, 10 and 11 (raised) |
| Error handling: transient failures, other statuses | Task 6 |
| Error handling: `CacheVersionError` | step 3 list |
| Implementation: Transport (one session, POST GraphQL, conditional GET REST) | Tasks 5, 7 and 8 |
| Implementation: Transport (`fetch.workers` semaphore, `asyncio.to_thread`) | step 3 list |
| Implementation: Requests, retries and rate limits | Tasks 4, 5, 6, 9, 10 and 11 |
| Implementation: GraphQL cost control (`rateLimit` on every query) | Task 7; page sizes and the `stats/*` cross-check in the step 3 list |
| Implementation: Cache, Incremental sync, Cache identity | step 3 list onwards |
| Implementation: Secrets | Tasks 3 and 5 |
| Implementation: Testing | Tasks 1, 5, 7, 8 and 12 |
| Settings: `max_retries`, `on_rate_limit`, `stats_retries` | Tasks 6, 9, 10 and 11 |
| Settings: the other `fetch.*` settings | step 3 list onwards |
| External dependencies: aiohttp | Task 1 |

The spec's `**Status:**` is not changed by this list: most of the spec is built by later lists, and the last of them sets it to `implemented`.

## Conventions for every task

- Async tests are plain `def test_...() -> None` functions whose body calls `asyncio.run(...)` on an inner coroutine; no pytest async plugin is added (spec, Testing).
- Tests never really sleep: they pass a recording fake `sleep` and a fixed `clock` to `GitHubClient`, and a seeded `random.Random` as `rng`.
- Tests never print, log or assert on the real token. Use the literal `'test-token'` in unit tests.
- Error fixtures written from GitHub's documentation carry a comment with the documentation URL they came from.

---

## Task 1: Add aiohttp and the fetch test layout

**Status:** done
**Priority:** high
**Complexity:** small
**Spec Reference:** External dependencies; Module location; Implementation (Testing)

**Technical Goal:** Make aiohttp available and create the test packages every later task writes into.

**Subtasks:**

- [ ] Check aiohttp's maintenance status per `.agents/claude/rules/tools-and-libraries.md`: latest PyPI release and date, GitHub archived or deprecated flags, open security advisories for the version to be locked, and support for Python 3.14; stop for the user if any check fails
- [ ] `uv add aiohttp`; commit the updated `pyproject.toml` and `uv.lock`
- [ ] Confirm `mypy src` still passes with aiohttp's bundled type hints (no stub package needed)
- [ ] Create `src/tests/fetch/__init__.py` and `src/tests/fixtures/fetch/__init__.py`
- [ ] Register a `live` marker in `[tool.pytest.ini_options] markers` in `pyproject.toml`, described as "calls the real GitHub API; skipped without GITHUB_TOKEN"
- [ ] Add `'not live'` to the CI pytest selection in `.github/workflows/ci.yml` so it reads `pytest -m 'not slow and not live'`

**Acceptance Criteria:**

- [ ] `source bin/activate.sh && python -c 'import aiohttp, aiohttp.test_utils'` succeeds
- [ ] `uv sync --locked` succeeds
- [ ] `pytest --co -q src/tests/fetch` runs without a collection error

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_package.py` passes

**Notes:**

- Depends on `agents/tasks/system/tasks-1.md` (step 1), done
- Changing `uv.lock` here is the explicit instruction the shared coding standards require.
- `aiohttp.test_utils.TestServer` ships with aiohttp, so no test dependency is added (spec, Testing).
- Key files: `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `src/tests/fetch/__init__.py`, `src/tests/fixtures/fetch/__init__.py`

---

## Task 2: Typed fetch errors

**Status:** done
**Priority:** high
**Complexity:** small
**Spec Reference:** Error handling; Module location (`errors.py`)

**Technical Goal:** Define the fetch layer's error classes once, so every request path raises the same types and the edge can catch them with one `FetchError` clause.

**Subtasks:**

- [ ] Add `src/wambatic/fetch/errors.py` with `FetchError(Exception)` and its subclasses `AuthError`, `GraphQLError`, `NotFoundError`, `RateLimitError` and `StatsPendingError`
- [ ] `RateLimitError.__init__(self, reset_at: datetime.datetime)` keeps `reset_at` as an attribute and builds its own message stating the reset time in UTC ISO format, so every call site is `RateLimitError(reset_at)`
- [ ] `GraphQLError.__init__(self, errors: list[tuple[str, str]])` keeps `errors` as `(type, message)` pairs and joins them into the message
- [ ] `AuthError` has a module constant `NO_TOKEN_MESSAGE` telling the user to set `GITHUB_TOKEN` or run `gh auth login`
- [ ] Write `src/tests/fetch/test_errors.py`: every class is a `FetchError`; `RateLimitError` exposes `reset_at` and names it in `str()`; `GraphQLError` exposes its pairs and names each type in `str()`

**Acceptance Criteria:**

- [ ] `issubclass(cls, wambatic.fetch.errors.FetchError)` for each error class
- [ ] `CacheVersionError` is not defined here (step 3 list)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_errors.py` passes

**Notes:**

- Depends on Task 1
- `errors.py` imports nothing from wambatic, so every other fetch module can import it without a cycle.
- Key files: `src/wambatic/fetch/errors.py`, `src/tests/fetch/test_errors.py`

---

## Task 3: Token resolution and redaction

**Status:** done
**Priority:** high
**Complexity:** small
**Spec Reference:** API (`resolve_token`, `redact`); Error handling (`AuthError`); Implementation (Secrets)

**User Story:** As a wambatic user, I want my token found from `GITHUB_TOKEN` or my `gh` login and never shown anywhere, so that I can run wambatic without putting a secret in a config file or a log.

**Subtasks:**

- [ ] Add `src/wambatic/fetch/auth.py` with `resolve_token() -> str`: return `os.environ['GITHUB_TOKEN']` stripped when it is set and non-blank; otherwise run `subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, timeout=10, check=False)` and return its stripped stdout when the exit status is 0 and stdout is non-blank; otherwise raise `AuthError(NO_TOKEN_MESSAGE)`
- [ ] Treat `FileNotFoundError` (no `gh`) and `subprocess.TimeoutExpired` as "no token" and raise `AuthError` from them; never include stdout or stderr in any message or log
- [ ] Add `redact(text: str, token: str) -> str` replacing every occurrence of `token` with `***`; an empty `token` returns `text` unchanged
- [ ] Write `src/tests/fetch/test_auth.py`: environment token wins and `gh` is not called (monkeypatch `subprocess.run` to fail the test if called); blank `GITHUB_TOKEN` falls through to `gh`; `gh` success returns its token; `gh` missing, failing, timing out or printing nothing each raise `AuthError`, and the error text contains neither the fake `gh` output nor stderr
- [ ] Write a hypothesis test (`@settings(max_examples=20, deadline=10000)`) that for any non-empty token and any text containing it, `redact` leaves no occurrence of the token and changes nothing when the token is absent

**Acceptance Criteria:**

- [ ] `resolve_token` reads only `GITHUB_TOKEN` and `gh auth token`
- [ ] No test or code path logs or prints a token value

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_auth.py` passes

**Notes:**

- Depends on Task 2
- The autouse fixture in `src/tests/conftest.py` already removes `GITHUB_TOKEN`; tests set it with `monkeypatch.setenv`.
- Key files: `src/wambatic/fetch/auth.py`, `src/tests/fetch/test_auth.py`

---

## Task 4: Rate-limit state and backoff

**Status:** done
**Priority:** high
**Complexity:** small
**Spec Reference:** API (`RateLimitState`, `backoff_delay`); Implementation (Requests, retries and rate limits)

**Technical Goal:** Keep the pure parts of rate limiting - parsing GitHub's limit signals and computing backoff delays - in one module with no I/O, so they are tested exhaustively without a server.

**Subtasks:**

- [ ] Add `src/wambatic/fetch/ratelimit.py` with `BACKOFF_BASE = 1.0`, `BACKOFF_CAP = 60.0`, `SECONDARY_WAIT = 60.0`, `utc_now()`, and the frozen, slotted `RateLimitState(remaining: int | None = None, reset_at: datetime.datetime | None = None)`
- [ ] `RateLimitState.from_headers(headers)` reads `x-ratelimit-remaining` (int) and `x-ratelimit-reset` (epoch seconds, to an aware UTC datetime); either header absent gives `None` for that field
- [ ] `RateLimitState.from_graphql(rate_limit)` reads `remaining` and `resetAt` (ISO 8601 with `Z`) from the `rateLimit` object
- [ ] `RateLimitState.exhausted(now)` is true only when `remaining == 0` and `reset_at` is later than `now`
- [ ] `backoff_delay(attempt, rng)` returns `rng.uniform(0, min(BACKOFF_CAP, BACKOFF_BASE * 2 ** attempt))`; `attempt` counts from 0
- [ ] Write `src/tests/fetch/test_ratelimit.py`: known-good header and `rateLimit` inputs parse to the expected state; missing headers give an empty state; `exhausted` is false for an empty state, for `remaining > 0`, and for a reset already passed
- [ ] Write a hypothesis test (`@settings(max_examples=20, deadline=10000)`) that for any `attempt` in `0..30` and any seed, `0 <= backoff_delay(attempt, random.Random(seed)) <= min(BACKOFF_CAP, BACKOFF_BASE * 2 ** attempt)`

**Acceptance Criteria:**

- [ ] `ratelimit.py` performs no I/O and does not import aiohttp
- [ ] Every `reset_at` produced is timezone-aware UTC

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_ratelimit.py` passes

**Notes:**

- Depends on Task 1
- Full jitter is from [AWS, Exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/); header semantics from [GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
- Key files: `src/wambatic/fetch/ratelimit.py`, `src/tests/fetch/test_ratelimit.py`

---

## Task 5: Replay server and `GitHubClient` lifecycle

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`GitHubClient`); Implementation (Transport; Requests, retries and rate limits: headers and timeout; Secrets; Testing)

**Technical Goal:** Build the client shell that owns the one aiohttp session, sends GitHub's required headers and logs only redacted text, plus the replay server every later client test uses.

**Subtasks:**

- [ ] Add `src/tests/fixtures/fetch/server.py` with a `ReplayServer` helper: built from an ordered list of canned responses (status, headers, JSON body) per `(method, path)`, served by `aiohttp.test_utils.TestServer` around an `aiohttp.web.Application`, recording each received request's method, path, query, headers and JSON body; exposes `url` for `api_url`; fails the test on a request with no canned response left
- [ ] Add fixtures for it to `src/tests/conftest.py` per the shared testing rule
- [ ] Add `src/wambatic/fetch/client.py` with `REQUEST_TIMEOUT = 60.0` and `GitHubClient.__init__(token, settings, *, api_url, sleep, clock, rng)` exactly as the spec's API, storing them; `rng` defaults to a new `random.Random()`
- [ ] `__aenter__` creates one `aiohttp.ClientSession` with `aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)` and default headers `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `User-Agent: wambatic/<wambatic.version.VERSION>`; `__aexit__` closes it
- [ ] Using `graphql` or `rest_get` outside `async with` raises `RuntimeError`
- [ ] Create the client's logger as `loguru.logger.patch(...)` with a patcher that sets `record['message'] = redact(record['message'], token)`; log each request at `debug` as method, URL and status only
- [ ] Add `graphql_limit` and `rest_limit` properties returning the current `RateLimitState` (empty until the first response)
- [ ] Add a minimal internal `send(method, path, *, json=None, params=None, headers=None)` that performs one request and returns status, headers and parsed JSON (or `None` for an empty body); response classification is Task 6
- [ ] Write `src/tests/fetch/test_client.py`: against the replay server, one request carries each required header with the right value; the session is closed after `async with` exits (`session.closed`); use outside the context raises `RuntimeError`
- [ ] Write a redaction test: add a list sink at `DEBUG` with `loguru.logger.add`, run a request cycle and also log a message containing the token through the client's logger, then assert `'test-token'` appears in no captured record; remove the sink afterwards

**Acceptance Criteria:**

- [ ] One `aiohttp.ClientSession` per client instance
- [ ] No captured log record contains the token or an `Authorization` header

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_client.py` passes

**Notes:**

- Depends on Task 3, Task 4
- `client.py` may import `wambatic.settings` and `wambatic.version`; `src/tests/test_layering.py` enforces that it imports nothing else from wambatic outside `wambatic.fetch`.
- Key files: `src/wambatic/fetch/client.py`, `src/tests/fetch/test_client.py`, `src/tests/fixtures/fetch/server.py`, `src/tests/conftest.py`

---

## Task 6: Response classification and transient retries

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** Error handling (`AuthError`, `NotFoundError`, transient failures, other statuses); Implementation (Requests, retries and rate limits, steps 1 and 5)

**Technical Goal:** Turn each HTTP outcome into exactly one of: success, a typed error, a retry, or a propagated exception, so the GraphQL and REST paths share one classification.

**Subtasks:**

- [ ] In `GitHubClient`, wrap `send` in a retry loop that classifies each response in the spec's order; this task implements 401 to `AuthError`, a 403 that is not a rate limit to `AuthError` naming `x-accepted-oauth-scopes` when present, 404 to `NotFoundError`, and statuses 500, 502, 503 and 504 as transient
- [ ] Treat `aiohttp.ClientConnectionError` and `TimeoutError` raised by `send` as transient
- [ ] On a transient failure wait `backoff_delay(attempt, rng)` through `sleep` and retry, up to `settings.max_retries` retries; after the last, re-raise the last exception, or raise `aiohttp.ClientResponseError` for the last status
- [ ] Any other non-2xx, non-304 status raises `aiohttp.ClientResponseError` at once, with no retry
- [ ] Leave hooks for the 403/429 rate-limit branches (Tasks 9 and 10) and the 202 branch (Task 11) so they slot into the same order
- [ ] Add error fixtures to `src/tests/fixtures/fetch/responses.py` for 401, 403 with `x-accepted-oauth-scopes`, 404, 500 and 502, written from [GitHub's REST troubleshooting](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api) shapes with that URL in a comment
- [ ] Write tests in `src/tests/fetch/test_client.py`: each status maps to its type; the `AuthError` text contains neither the token nor any request header; 502 then 200 succeeds after one recorded `sleep`; 502 repeated `max_retries + 1` times raises `aiohttp.ClientResponseError` after exactly `max_retries` sleeps; a connection error then 200 succeeds; 422 raises at once with no sleep

**Acceptance Criteria:**

- [ ] Retry count never exceeds `settings.max_retries`
- [ ] Every recorded wait is within `backoff_delay`'s bounds

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_client.py` passes

**Notes:**

- Depends on Task 5
- Construct settings with `dataclasses.replace(wambatic.settings.FetchSettings(), max_retries=2)` to keep tests short.
- Key files: `src/wambatic/fetch/client.py`, `src/tests/fetch/test_client.py`, `src/tests/fixtures/fetch/responses.py`

---

## Task 7: GraphQL request path and the first query

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`GitHubClient.graphql`); Error handling (`NotFoundError`, `GraphQLError`); Implementation (Transport; GraphQL cost control; Requests, retries and rate limits: the `rateLimit` rule; Testing)

**User Story:** As a wambatic developer, I want one GraphQL call that returns `data` or a typed error and keeps the rate-limit budget current, so that every later query gets error handling and accounting for free.

**Subtasks:**

- [ ] Implement `graphql(query, variables)`: POST `{api_url}/graphql` with `{'query': query, 'variables': variables}` through the Task 6 loop
- [ ] On every GraphQL response, update the GraphQL `RateLimitState` from its `x-ratelimit-*` headers, then from `data['rateLimit']` when present
- [ ] Map `errors`: any `NOT_FOUND` type raises `NotFoundError`; `RATE_LIMITED` is left to Task 9 (raise `GraphQLError` until then); any other type raises `GraphQLError` with every `(type, message)` pair, discarding partial `data`
- [ ] A response with `data` and no `errors` that lacks `data['rateLimit']` raises `GraphQLError`
- [ ] Return `data` as `dict[str, object]`
- [ ] Add `src/wambatic/fetch/queries.py` with `OWNER_REPOSITORIES`: `repositoryOwner(login: $login)` with `repositories(first: 100, after: $cursor, ownerAffiliations: OWNER)` selecting `pageInfo { hasNextPage endCursor }` and `nodes { nameWithOwner }`, plus `rateLimit { cost remaining resetAt }`
- [ ] Record one real response to `OWNER_REPOSITORIES` for `login: 'octocat'` once, first checking `[ -n "${GITHUB_TOKEN:-}" ]` and printing only yes or no (shared security rule); if no token is available, stop the task as `blocked`, naming the missing token. Trim it to the selected fields, note the recording date in a comment, and save it in `src/tests/fixtures/fetch/responses.py`; never write the token or response headers other than `x-ratelimit-*` into the fixture
- [ ] Add `NOT_FOUND` and an `INTERNAL` error fixture written from [GitHub's GraphQL docs](https://docs.github.com/en/graphql/overview/rate-limits-and-node-limits-for-the-github-graphql-api) shapes
- [ ] Write `src/tests/fetch/test_queries.py`: every query constant in `queries.py` contains `rateLimit { cost remaining resetAt }` (iterate the module's string constants, so a new query is checked automatically)
- [ ] Write tests in `src/tests/fetch/test_client.py`: the recorded response returns its `data` and sets `graphql_limit` to its `rateLimit`; the request body carries the query and variables; `NOT_FOUND` raises `NotFoundError`; `INTERNAL` raises `GraphQLError` with that type; `data` without `rateLimit` raises `GraphQLError`

**Acceptance Criteria:**

- [ ] `graphql_limit` reflects the latest response after every call
- [ ] Partial `data` is never returned alongside errors

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_client.py src/tests/fetch/test_queries.py` passes

**Notes:**

- Depends on Task 6
- `OWNER_REPOSITORIES` is a probe for this step's live test; the step 3 list extends or replaces it with the repo fields, forks and archived filters `repos()` needs.
- Deviation, 2026-10-29: the build session could not reach the live GraphQL API (the sandbox proxy refuses GraphQL), so the `OWNER_REPOSITORIES_OK` fixture is hand-written from GitHub's documented shapes, not recorded. Record it from a session with network access and replace it.
- Key files: `src/wambatic/fetch/client.py`, `src/wambatic/fetch/queries.py`, `src/tests/fetch/test_client.py`, `src/tests/fetch/test_queries.py`, `src/tests/fixtures/fetch/responses.py`

---

## Task 8: REST request path with ETag revalidation

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`GitHubClient.rest_get`, `RestResponse`); Implementation (Transport: conditional GETs; Cache: `If-None-Match`)

**Technical Goal:** One REST GET that revalidates with an ETag, reports the next page and keeps the REST budget current, so later steps can store ETags and page through REST endpoints.

**Subtasks:**

- [ ] Add the frozen, slotted `RestResponse(status, data, etag, next_url)` to `src/wambatic/fetch/client.py`
- [ ] Implement `rest_get(path, params=None, etag=None)` through the Task 6 loop, sending `If-None-Match: etag` when given
- [ ] Update the REST `RateLimitState` from the `x-ratelimit-*` headers of every response
- [ ] 200 returns parsed JSON, the response `ETag` and `next_url`; 304 returns `data=None` with the request's `etag`
- [ ] Parse `next_url` from the `Link` header's `rel="next"` entry with a small pure function `next_link(header: str | None) -> str | None` ([GitHub pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api))
- [ ] Record one real `GET /repos/octocat/Hello-World` response once, with the same token check and stop as Task 7; keep only `ETag`, `x-ratelimit-*` and a few body fields, with the recording date in a comment
- [ ] Write tests in `src/tests/fetch/test_client.py`: 200 returns data and `ETag`; a request with `etag` sends `If-None-Match` and a 304 returns `data=None`; `rest_limit` tracks headers; `next_link` returns the next URL for a multi-entry `Link` header and `None` when there is no `next` or no header; REST 404 raises `NotFoundError`

**Acceptance Criteria:**

- [ ] A 304 is not an error and is not retried
- [ ] `rest_limit` reflects the latest REST response after every call

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_client.py` passes

**Notes:**

- Depends on Task 6
- Storing ETags in SQLite is the step 3 list's; this task only sends and returns them.
- Deviation, 2026-10-29: as Task 7, the `REPO` fixture is hand-written, not recorded.
- Key files: `src/wambatic/fetch/client.py`, `src/tests/fetch/test_client.py`, `src/tests/fixtures/fetch/responses.py`

---

## Task 9: Primary rate limit: wait or fail

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** Error handling (`RateLimitError`); Implementation (Requests, retries and rate limits, steps 3 and 6); Settings (`fetch.on_rate_limit`)

**User Story:** As a wambatic user, I want a run that hits GitHub's hourly limit to either wait for the reset with an ETA or stop at once with the reset time, as I configured, so that a large org report neither fails silently nor hammers the API.

**Subtasks:**

- [ ] Before each request, check the endpoint's `RateLimitState.exhausted(clock())`
- [ ] Treat a 403 or 429 with `x-ratelimit-remaining: 0`, and a GraphQL `RATE_LIMITED` error, as exhaustion after updating the state from the response
- [ ] On exhaustion with `on_rate_limit = 'fail'`, raise `RateLimitError(reset_at)`
- [ ] On exhaustion with `'wait'`, log `ETA: GitHub rate limit resets in <duration>` at `info` and `sleep` until `reset_at` plus one second, then retry; these waits do not count against `max_retries`
- [ ] If a primary-limit response leaves no `reset_at`, handle it as a secondary limit (Task 10)
- [ ] Add fixtures for a REST 403 with `x-ratelimit-remaining: 0` and a GraphQL `RATE_LIMITED` response, written from [GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit) and [GraphQL rate limits](https://docs.github.com/en/graphql/overview/rate-limits-and-node-limits-for-the-github-graphql-api#exceeding-the-rate-limit)
- [ ] Write tests in `src/tests/fetch/test_client.py`, with a fixed `clock`: `'fail'` raises `RateLimitError` with the fixture's reset time for both fixtures; `'wait'` records one `sleep` of the expected seconds then succeeds on the next canned 200; a pre-exhausted state with `'fail'` raises before any request reaches the server; with `'wait'` the `ETA:` line is logged at `info` (capture with a list sink)

**Acceptance Criteria:**

- [ ] `'fail'` never sleeps; `'wait'` never raises `RateLimitError` for a primary limit with a known reset
- [ ] The `ETA:` line follows the shared logging rule's format

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_client.py` passes

**Notes:**

- Depends on Task 7, Task 8
- The ETA line format is in `.agents/claude/rules/python/logging.md`.
- Key files: `src/wambatic/fetch/client.py`, `src/tests/fetch/test_client.py`, `src/tests/fixtures/fetch/responses.py`

---

## Task 10: Secondary rate limits

**Status:** done
**Priority:** high
**Complexity:** small
**Spec Reference:** Error handling (secondary rate limits); Implementation (Requests, retries and rate limits, steps 2 and 4, backoff); Settings (`fetch.max_retries`)

**Technical Goal:** Always honour GitHub's secondary-limit signals, back off on repeats, and stop with `RateLimitError` when retries run out.

**Subtasks:**

- [ ] A 403 or 429 with `retry-after` waits `max(retry_after, backoff_delay(attempt, rng))` seconds and retries
- [ ] A 403 or 429 whose JSON `message` contains `secondary rate limit`, with neither `retry-after` nor `x-ratelimit-remaining: 0`, waits `max(SECONDARY_WAIT, backoff_delay(attempt, rng))` and retries
- [ ] Count these retries against `settings.max_retries`, sharing the counter with transient retries in the same call
- [ ] When the retries run out, raise `RateLimitError` with `reset_at = clock() + the last wait`, whatever `on_rate_limit` says
- [ ] Add 429-with-`retry-after` and 403-secondary-message fixtures from [GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit)
- [ ] Write tests in `src/tests/fetch/test_client.py`: `retry-after: 3` then 200 records one sleep of at least 3 seconds; the message-only 403 records one sleep of at least 60 seconds; repeated 429s raise `RateLimitError` after exactly `max_retries` sleeps, with `on_rate_limit` set to `'wait'`; a 403 without any limit signal still raises `AuthError` (Task 6)

**Acceptance Criteria:**

- [ ] A secondary limit is never retried before its `retry-after`
- [ ] A secondary limit never raises before `max_retries` retries

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_client.py` passes

**Notes:**

- Depends on Task 9
- Key files: `src/wambatic/fetch/client.py`, `src/tests/fetch/test_client.py`, `src/tests/fixtures/fetch/responses.py`

---

## Task 11: REST 202 and `StatsPendingError`

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** Error handling (`StatsPendingError`); Implementation (Requests, retries and rate limits: REST 202); Settings (`fetch.stats_retries`)

**Technical Goal:** Wait for GitHub to finish computing a `stats/*` response, within a bound, instead of returning an empty body as data.

**Subtasks:**

- [ ] In `rest_get`, a 202 waits `backoff_delay(attempt, rng)` and retries, up to `settings.stats_retries` retries, counted separately from `max_retries`
- [ ] When they run out, raise `StatsPendingError` naming the path
- [ ] Add a 202 fixture from [GitHub repository statistics](https://docs.github.com/en/rest/metrics/statistics#a-word-about-caching)
- [ ] Write tests in `src/tests/fetch/test_client.py`: 202, 202, 200 returns the 200 body after two sleeps; 202 repeated `stats_retries + 1` times raises `StatsPendingError` after exactly `stats_retries` sleeps

**Acceptance Criteria:**

- [ ] A 202 body is never returned as data

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_client.py` passes

**Notes:**

- Depends on Task 8
- Key files: `src/wambatic/fetch/client.py`, `src/tests/fetch/test_client.py`, `src/tests/fixtures/fetch/responses.py`

---

## Task 12: Opt-in live test

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** Implementation (Testing); implementation order step 2 ("an opt-in live test lists the repos of a small public account")

**Technical Goal:** Prove once against the real API that authentication, headers and the GraphQL path work, without making the normal test run depend on the network.

**Subtasks:**

- [ ] Write `src/tests/fetch/test_live.py` marked `@pytest.mark.live` and `@pytest.mark.skipif` on `GITHUB_TOKEN` being unset. The autouse fixture in `src/tests/conftest.py` clears `GITHUB_TOKEN` before each test, so read it once at import time into a module constant that is used only to build the client and never printed or put in an assertion message
- [ ] The test opens a `GitHubClient` with default `api_url`, `sleep` and `clock`, runs `OWNER_REPOSITORIES` for `octocat`, and asserts `octocat/Hello-World` is among the names and `graphql_limit.remaining` is an int
- [ ] Run it once with a token present and record the date and outcome in the task's Notes; if no token is available, record that it was skipped and why

**Acceptance Criteria:**

- [ ] `pytest -m 'not live' src/tests/fetch/test_live.py` selects nothing
- [ ] Without `GITHUB_TOKEN` the test is skipped, not failed

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_live.py` passes or skips

**Notes:**

- Depends on Task 7
- CI deselects `live` (Task 1) and has no token, so it never runs there.
- Run 2026-10-29 with `pytest -m live`: failed with `AuthError` (HTTP 401) because the sandbox's `GITHUB_TOKEN` is not accepted by `api.github.com/graphql`. The request path reached the API and was classified correctly; the pass is still to be shown from a session with a real token.
- Key files: `src/tests/fetch/test_live.py`

---

## Task 13: Package exports and closing checks

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** Module location; API; implementation order step 2 ("Done when")

**Technical Goal:** Expose the step 2 names from `wambatic.fetch`, confirm the layering still holds, run every test this list can affect, and mark the step done.

**Subtasks:**

- [ ] In `src/wambatic/fetch/__init__.py`, re-export `AuthError`, `FetchError`, `GitHubClient`, `GraphQLError`, `NotFoundError`, `RateLimitError`, `StatsPendingError` and `resolve_token` and list them in `__all__`, alphabetically; `wambatic.__all__` is not extended (system API re-exports `Subject` and `Fetcher`, from the step 3 list)
- [ ] Extend `src/tests/test_package.py` to check that each name in `wambatic.fetch.__all__` resolves
- [ ] Confirm `src/tests/test_layering.py` passes with the new modules
- [ ] Check the implementation order's "Done when" for step 2: fixtures cover 401 (Task 6), 404 (Tasks 6 and 7), primary limits (Task 9), secondary limits (Task 10) and REST 202 (Task 11); the live test exists (Task 12)
- [ ] Run every test that imports a changed module directly or transitively: `pytest src/tests/fetch src/tests/test_package.py src/tests/test_layering.py`
- [ ] In `agents/specs/implementation-order.md`, set step 2's Status to `done`

**Acceptance Criteria:**

- [ ] `import wambatic.fetch; wambatic.fetch.resolve_token; wambatic.fetch.GitHubClient` works
- [ ] Every step 2 "Done when" item is met

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch src/tests/test_package.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Tasks 2 to 12
- The project has no affected-tests tool; the command above names every test file that reaches a module this list changed (`wambatic.fetch` is imported only by `src/tests/test_package.py` outside `src/tests/fetch/`).
- Key files: `src/wambatic/fetch/__init__.py`, `src/tests/test_package.py`, `agents/specs/implementation-order.md`

---
