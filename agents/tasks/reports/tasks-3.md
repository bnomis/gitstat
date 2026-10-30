# Tasks: Reports

**Spec:** `agents/specs/reports/spec.md`
**Created:** 2026-10-30
**Version:** 3

This list builds step 9 of the [implementation order](../../specs/implementation-order.md), "Local web app": `SyncProgress` in the fetcher, the CLI's sync-then-compute code moved to `reports/service.py` and the five-result HTML build to `html.py`, the `fastapi` and `uvicorn` dependencies (and `httpx` for tests), the sync jobs, a FastAPI app with `/`, `/report`, `/api/stats` and `/api/progress`, its pages, the `Host` check, the `serve` command on uvicorn with loopback-only binding and `--allow-remote`, and the README's web app section. It is written against version 1.6 of the reports spec and 1.7 of the fetch-and-cache spec, which settled what 1.5 left open for this step; the gaps and the choices made are in [review-3.md](../../specs/reports/review-3.md). It follows the option you chose for that review's decision 1 on 2026-10-30, FastAPI with uvicorn (the review recommended `aiohttp.web`; the Answers section records the choice). The step 7 list, [tasks-2.md](tasks-2.md), built the HTML page that `/report` returns, and the step 8 list, [stats/tasks-3.md](../stats/tasks-3.md), the delivery group it shows.

## Spec coverage

| Spec section | Covered by |
|--------------|------------|
| Module location (`service.py`; the five-result build in `html.py`) | Task 2 |
| Module location (`web.py`, `templates/` pages) | Tasks 3, 4 and 5 |
| Module location (layering: only `service` and `web` import `fetch`) | Tasks 2 and 9 |
| API: `period_requests`, `html_report`, the `service.py` functions | Task 2 |
| API: `SyncJob`, `Jobs` | Task 3 |
| API: `make_app` | Tasks 4 and 5 |
| API: `is_loopback`, `check_bind`, `serve` | Task 6 |
| Command line: `serve` and its flags | Task 6 |
| Error handling (web statuses, redaction, JSON and page forms) | Tasks 4 and 5 |
| Error handling (binding `OSError`, Ctrl-C exit 130, `CacheVersionError` at start-up) | Task 6 |
| Implementation: Web app (routes, parameters) | Tasks 4 and 5 |
| Implementation: Web app (sync jobs, progress page) | Tasks 3 and 5 |
| Implementation: Web app (security: loopback, `Host` check, no CORS) | Tasks 4 and 6 |
| Implementation: Web app (logging, stopping) | Tasks 4 and 6 |
| Implementation: Web app (pages) | Task 5 |
| Implementation: Web app (testing: large org, browser) | Tasks 4, 5 and 7 |
| Settings (`allow_remote`, `web_host`, `web_port`) | Task 6 |
| External dependencies (`fastapi`, `uvicorn`; `httpx` for tests) | Task 3 |
| Fetch spec 1.7: `SyncProgress`, `Fetcher.sync(progress=)` | Task 1 |
| User guide (shared user-guides rule) | Task 8 |
| Implementation order step 9 "Done when" | Tasks 4, 6 and 7; checked in Task 9 |

The reports spec's `**Status:**` is not changed by this list: step 10 adds the languages chart to it, and the step 10 list sets it to `implemented` (review-3.md choice 16).

## Conventions for every task

- Async code is driven as in the earlier lists: plain `def test_...() -> None` functions whose body calls `asyncio.run(...)`; no pytest async plugin. The web tests build the app with `make_app` and drive it with `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8000')` inside that `asyncio.run`, entering `app.router.lifespan_context(app)` themselves, since `ASGITransport` does not run the lifespan. Starlette's synchronous `TestClient` is not used: it runs the app on its own thread and loop, which a test that also drives a `Fetcher` cannot share.
- Every file a test writes lives under pytest's `tmp_path`; tests that run `main` set `fetch.cache_path` and `report.out_dir` there through a config file named by `WAMBATIC_CONFIG` (monkeypatched). The autouse `isolated_environment` fixture already removes `GITHUB_TOKEN` and `WAMBATIC_CONFIG`.
- No test reaches the network. Fresh-cache tests use the stats fixtures' cache (`stats_cache`, `stats_fetcher`, numbers in `tests.fixtures.stats`); sync tests use the `Upstream` fake GitHub in `tests.fixtures.fetch.upstream` served by `ReplayServer`, reached by monkeypatching `wambatic.reports.service.make_fetcher`, as `test_cli.py` patches `wambatic.cli.make_fetcher` today.
- No test binds a real port except the browser test (Task 7), which binds `127.0.0.1` on a free port chosen by the OS. No test calls the real `uvicorn.Server.run` otherwise.
- `wambatic.reports` modules import nothing from wambatic outside `wambatic.reports`, `wambatic.stats`, `wambatic.settings` and `wambatic.version`, except `wambatic.reports.service` and `wambatic.reports.web`, which may also import `wambatic.fetch`; only `wambatic.reports.html` imports `plotly` (Task 2 changes the layering test, Task 9 checks it).
- Every value from a request or the data reaches a page through `html.escape`; no response carries the token or a traceback.
- The project has no affected-tests tool, so each task names its test files literally; Task 9 runs every test the list can reach.
- The local environment may lack the exact Python patch release `pyproject.toml` requires (`>=3.14.7`); if `uv sync` cannot find it, say so in the task's Notes and work around it as tasks-2.md Task 1 did (lower `requires-python` for that one command, then restore `pyproject.toml` and the `requires-python` and `revision` lines of `uv.lock`), never by committing a changed `requires-python`.
- Hypothesis tests use `@hypothesis.settings(max_examples=20, deadline=10000)` (shared testing rule).

---

## Task 1: Report sync progress from `Fetcher.sync`

**Status:** done
**Priority:** high
**Complexity:** small
**Spec Reference:** fetch-and-cache spec 1.7 (`SyncProgress`, `Fetcher.sync`); review-3.md choice 4

**Technical Goal:** Let a caller watch a sync while it runs, so the web app's progress endpoint has counts to show, without changing what a sync does or returns.

**Subtasks:**

- [ ] Add the `SyncProgress` dataclass (`slots=True`, not frozen) to `src/wambatic/fetch/base.py` with the fields and defaults of the fetch spec, and export it from `wambatic.fetch`
- [ ] Give `Fetcher.sync` the keyword-only `progress: SyncProgress | None = None`; when given, set `repos_listed` and `repos_pending` once `pending` is known, add each resource's rows to `rows_written` as soon as that resource of a repo is written, and add one to `repos_done` when a pending repo's last needed resource is done
- [ ] Write tests in `src/tests/fetch/test_fetcher.py`: after a sync of the `Upstream` fake with two changed repos and one unchanged, the progress counts equal the `SyncReport`'s (`repos_listed`, `repos_listed - repos_skipped`, `rows_written`) and `repos_done` equals `repos_pending`; with `Upstream.history_delay` set, a task reading the progress while the sync runs sees `repos_listed` set and `repos_done` below `repos_pending` at least once; a sync without `progress` behaves exactly as before

**Acceptance Criteria:**

- [ ] Every existing test in `src/tests/fetch/` passes unchanged
- [ ] `SyncProgress` is importable as `wambatic.fetch.SyncProgress`, checked by a line added to `src/tests/test_package.py`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_fetcher.py src/tests/fetch/test_base.py src/tests/test_package.py` passes

**Notes:**

- Depends on stats/tasks-3.md Task 13 (step 8), done
- Key files: `src/wambatic/fetch/base.py`, `src/wambatic/fetch/__init__.py`, `src/tests/fetch/test_fetcher.py`
- The progress object is written and read on one event loop, so it needs no lock; do not update it from the `Cache` worker threads.
- Done. `SyncProgress` is updated in `Fetcher.sync` on the event loop only, never from the `Cache` worker threads.

---

## Task 2: Move the sync-then-compute pipeline to `reports/service.py`

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** Module location (`service.py`, layering); API (`period_requests`, `html_report`, the `service.py` functions); review-3.md choices 2 and 3

**Technical Goal:** Give the CLI and the web app one copy of target parsing, request building, freshness, syncing and computing, and of the five-result HTML build, without the web app importing `wambatic.cli`; the CLI's behaviour does not change.

**Subtasks:**

- [ ] Add `src/wambatic/reports/service.py` and move into it from `cli.py`, unchanged in behaviour: `LOGIN`, `REPO_NAME`, `DATE`, `PREFIXES`, `TARGET_FORMS`, `parse_target`, `parse_date`, `check_by_author`, `resolve_tz`, `make_fetcher`, `needs_sync`, `log_sync`, `redact_environment_token`
- [ ] Add `service.make_request(by, since, until, groups, by_author, tz, settings)` holding the body of `cli.build_request`, and make `cli.build_request` call it with the `Report` flags
- [ ] Move `cli.build_result` to `service.build_results` with the spec's signature (keyword `by_author`, `full_refresh`, `no_fetch`, `sync`, `progress`, `clock` in place of the `Report` dataclass); `sync=None` keeps today's `needs_sync` decision, `True` and `False` force it, and `progress` is passed to `Fetcher.sync`; `cli.run_report` calls it
- [ ] Add `html.period_requests(request)` and `html.html_report(results, initial)` from the code in `cli.run_report` and `cli.render_html_report`, and make the CLI use them
- [ ] Keep `cli.py` free of copies: it imports each moved name from `wambatic.reports.service`; `redact_exception` stays in `cli.py` and calls `service.redact_environment_token`
- [ ] Change `src/tests/test_layering.py` so `wambatic.reports.service` and `wambatic.reports.web` may import `wambatic.fetch` and every other reports module still may not, with a test like `test_detects_reports_importing_fetch_or_the_cli` showing that `wambatic.reports.terminal` importing `wambatic.fetch` is still a violation
- [ ] In `src/tests/test_cli.py`, change only the references to moved names (`wambatic.cli.make_fetcher` becomes `wambatic.reports.service.make_fetcher`, and so on); move the unit tests of the moved functions to `src/tests/reports/test_service.py` unchanged apart from the module they call
- [ ] Add to `src/tests/reports/test_service.py`: `period_requests` gives TOTAL, YEAR, MONTH, WEEK, DAY with every other field equal; `html_report` of those five results equals the `org_report` fixture's `HtmlReport`; `build_results(..., sync=False)` makes no request and `sync=True` syncs even with a fresh `--max-age`

**Acceptance Criteria:**

- [ ] `git diff` of `src/tests/test_cli.py` shows only changed module references and removed (moved) unit tests; every CLI behaviour test passes unchanged
- [ ] `grep -n 'def parse_target\|def needs_sync\|def make_fetcher' src/wambatic/cli.py` finds nothing
- [ ] `test_layering` passes

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_service.py src/tests/reports/test_html.py src/tests/test_cli.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Task 1 (`build_results` passes `progress` to `sync`)
- Key files: `src/wambatic/reports/service.py`, `src/wambatic/reports/html.py`, `src/wambatic/cli.py`, `src/tests/reports/test_service.py`, `src/tests/test_cli.py`, `src/tests/test_layering.py`
- A refactor commit of its own (`refactor(reports): ...`), before any web code, so a change in CLI behaviour would show in its diff alone.
- `parse_target` raises `wambatic.reports.errors.UsageError` and returns a `wambatic.fetch.base.Subject`, which is why `service.py` needs the layering exception.
- Done. One deviation from the spec's signature: the sync half of `build_results` is also a function of its own, `service.sync_target(settings, cache, target, groups, ...)`, which resolves a bare NAME and syncs and returns the `Subject`; `build_results` calls it and then computes. The web app's job calls it directly because `build_results(..., requests=[])` has no groups to derive the resources from. `service.make_request` also turns an unknown `by` into a `UsageError`, since the web app passes it a string from the query.
- `Fetcher.sync` is called with `progress=` only when a progress object is given, so the CLI's existing tests, whose spy has no such parameter, pass unchanged.

---

## Task 3: Add FastAPI and uvicorn, and the sync jobs

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`SyncJob`, `Jobs`); Web app (Sync jobs); External dependencies (FastAPI, uvicorn, httpx); implementation order Principles (dependencies are checked, not assumed); review-3.md decision 1 and choices 5 and 6

**Technical Goal:** Add the server libraries after the maintenance check the shared tools-and-libraries rule requires, and run the web app's syncs as asyncio tasks on the server's loop, one at a time, with a state and progress any request can read, so no request waits for a sync.

**Subtasks:**

- [ ] Re-run the maintenance check for `fastapi`, `uvicorn` and `httpx` on the day: the release the project's 14-day `exclude-newer` window resolves and its date, licence, the repository not archived; record the result with the date in this task's Notes (review-3.md has the 2026-10-30 result, including that `httpx`'s latest release is from 2024-12-06)
- [ ] If any fails the check, stop the list and tell the user; do not substitute a library
- [ ] `uv add fastapi uvicorn` and `uv add --dev httpx` (a deliberate dependency change, which decision 1 sanctions; never hand-edit `uv.lock`). Not `uvicorn[standard]` or `fastapi[standard]`: their extras add `uvloop`, `httptools`, `watchfiles` and the FastAPI CLI, none of which the app uses
- [ ] Check that the resolved `fastapi`, `starlette`, `uvicorn` and `httpx` each ship `py.typed` (they did on 2026-10-30); if one does not, stop and tell the user rather than adding a mypy override
- [ ] Add `src/wambatic/reports/web.py` with `SyncJob` and `Jobs` as the spec's API: `start` returns the key's job when it is `queued`, `listing` or `syncing`, else creates one with a fresh id (`secrets.token_hex(8)`), replaces the key's previous job, and runs `run(job)` in an `asyncio.Task` that waits for the one `asyncio.Lock` before setting `listing`
- [ ] A job that raises gets `state='failed'`, `error` from `service.redact_environment_token(str(e))` and `status` from one mapping function `error_status(e)` shared with Task 4's middleware (400, 404, 502 or 500 as the spec's Error handling; 500 errors also logged with `loguru.logger.exception` and their message replaced by `internal error; see the server log`); `forget(job)` drops a job if it is still its key's latest; `close()` cancels every running and queued task and waits for them
- [ ] `state` moves from `listing` to `syncing` once `progress.repos_listed` is set (the job's `run` checks it, or `SyncJob.state` is a property reading the progress; pick one and say which in Notes)
- [ ] Write `src/tests/reports/test_web.py` tests for `Jobs` with plain coroutines as `run`: a second `start` with the same key while running returns the same job; jobs for two keys run one after the other (the second is `queued` until the first ends); a raising `run` gives `failed` with the mapped status and a redacted message (a `GITHUB_TOKEN` set by the test does not appear); after `done`, `start` creates a new job; `close` cancels a running job

**Acceptance Criteria:**

- [ ] No job's `run` starts while another job's `run` is running
- [ ] `error_status` maps each error class the spec names to its status (a parametrised test over `UsageError`, `SettingsError`, `UnknownGroupError`, `InvalidRangeError`, `InvalidRequestError`, `NotFoundError`, `EmptySubjectError`, `AuthError`, `RateLimitError`, `GraphQLError`, `StatsPendingError` and `RuntimeError`)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `uv sync --locked` succeeds (or, where this environment lacks Python 3.14.7, say so in Notes; the `check` job in CI runs it)
- [ ] `pytest src/tests/reports/test_web.py src/tests/test_layering.py src/tests/test_package.py` passes

**Notes:**

- Depends on Task 2
- Key files: `src/wambatic/reports/web.py`, `src/tests/reports/test_web.py`
- Key files also: `pyproject.toml`, `uv.lock`
- Docs: [FastAPI](https://fastapi.tiangolo.com/), [uvicorn](https://www.uvicorn.org/), [HTTPX](https://www.python-httpx.org/), [asyncio tasks](https://docs.python.org/3.14/library/asyncio-task.html)
- Record the versions actually locked, and any new transitive packages, in Notes.
- Keep a reference to every task (`Jobs` holds them), since the event loop keeps only weak references to tasks.
- Done. Maintenance check on 2026-10-30, PyPI: `fastapi` 0.162.0 (MIT, released 2026-10-23), `uvicorn` 0.54.0 (BSD-3-Clause, 2026-09-25), `starlette` 1.10.0 (BSD-3-Clause, 2026-10-24) and `httpx` 0.28.1 (BSD-3-Clause; later releases are only 1.0 development releases, which `prerelease = "disallow"` excludes). The archived flags of the repositories could not be read: this session's GitHub access covers only the two project repositories.
- Locked: `fastapi` 0.143.2, `starlette` 1.8.0, `uvicorn` 0.54.0, `httpx` 0.28.1 (with `httpcore` 1.0.9 and `certifi`), `pydantic` 2.14.1, `pydantic-core` 2.50.1, `anyio` 4.15.1, `click` 8.5.0, `h11` 0.16.0, `opentelemetry-api` 1.45.1, `annotated-doc`, `annotated-types` and `typing-inspection` as new packages. Each of `fastapi`, `starlette`, `uvicorn` and `httpx` ships `py.typed`.
- `SyncJob.state` is a property over a stored `phase` (`queued`, `running`, `done`, `failed`): it reads `listing` until `progress.repos_listed` is set and `syncing` after, so nothing has to poll the progress to update a field.
- The local Python is older than 3.14.7, so `uv sync` and `uv add` ran with `requires-python` lowered to 3.14.6 for those commands; `pyproject.toml` and the `requires-python` and `revision` lines of `uv.lock` were restored before the commit.

---

## Task 4: The app, its parameters, errors, `Host` check and the JSON routes

**Status:** done
**Priority:** high
**Complexity:** large
**Spec Reference:** API (`make_app`); Web app (routes `/api/stats` and `/api/progress`, Parameters, Sync jobs, Security, Logging, Testing); Error handling (web); review-3.md choices 5, 7, 8, 11 and 12

**User Story:** As someone building my own front end, I want `/api/stats` to give me the same JSON as `--format json` and `/api/progress` to tell me how a sync is going, so that I can show wambatic's numbers without waiting on a blocked request.

**Subtasks:**

- [ ] Add `make_app(settings, cache, *, default_target=None, check_host=True, clock=utc_now)` to `web.py`: a `fastapi.FastAPI` whose route functions are closures over the settings, the cache, the clock and one `Jobs` (so nothing untyped lives on `app.state`), with a lifespan that calls `Jobs.close` on shutdown, and the routes `/api/stats` and `/api/progress` (the HTML routes come in Task 5)
- [ ] Declare every query parameter as `typing.Annotated[str | None, fastapi.Query(description=...)] = None`, so the OpenAPI page lists them and FastAPI's own validation can reject nothing, then parse them in one function for both data routes: `target` (required; missing is a `UsageError`), `by` (default `month`), `since`, `until`, `groups`, `by_author` (`1`, `true` or `on`), `tz` (overriding `stats.timezone`, resolved as `service.resolve_tz` does), `job`; through `service.parse_target` and `service.make_request`, so messages match the CLI's
- [ ] `/api/stats`: compute with `service.build_results(..., sync=False)` when the `job` parameter names a `done` job with the request's key, or when the target is a `Subject` and `service.needs_sync` (on `Fetcher.provenance`, `full_refresh` and `no_fetch` false) is false; else `Jobs.start` a job running `build_results(..., sync=True, progress=job.progress, requests=[])` that records the resolved subject, and answer 202 `{"job", "progress"}`; a `job` naming a `failed` job answers its status and error, then `forget`s it
- [ ] `/api/progress?job=ID`: the spec's JSON; 404 `{"error": "no such job"}` for an unknown id
- [ ] One `@app.middleware('http')` error middleware: every exception a route raises becomes `error_status(e)` and `{"error": message}` JSON (Task 5 adds the page form for HTML routes); not an exception handler for `Exception`, which Starlette runs in `ServerErrorMiddleware` and then re-raises. Also register a handler turning FastAPI's `RequestValidationError` into 400 `{"error": ...}`, so no route can answer 422
- [ ] A `Host` middleware, active when `check_host`: 403 `{"error": "unexpected Host header"}` unless `Host` is `localhost`, `127.0.0.1` or `[::1]`, then `:` and the port the request arrived on (the ASGI scope's `server` port). Not Starlette's `TrustedHostMiddleware`: it answers 400, ignores the port and splits `[::1]:8000` at the first `:`
- [ ] A logging middleware: one `loguru.logger.debug` line per request with method, path, status and milliseconds; no query string, no headers
- [ ] Write tests in `src/tests/reports/test_web.py`: `/api/stats?target=org:...` on the fresh stats cache with a `max_age` the cache is younger than equals `result_to_dict` of the same request computed directly (status 200); each invalid parameter (`target=a/b/c`, `by=hour`, `since=2026-1-1`, `groups=nope`, `tz=Mars/Base`, `until` before `since`) answers 400 with the CLI's message; a stale cache answers 202, the job runs against the `Upstream` fake, `/api/progress` reaches `done`, and `/api/stats?...&job=ID` answers 200 without a second sync (the replay server's request count does not grow); a 404 from the fake's listing answers 404; no `GITHUB_TOKEN` answers 502 naming `GITHUB_TOKEN`; a handler raising `RuntimeError` answers 500 with no traceback in the body; `Host: evil.example:8000` answers 403 and `Host: localhost:8000` does not; responses carry no `Access-Control-Allow-Origin`; `/openapi.json` lists `/api/stats` with every query parameter

**Acceptance Criteria:**

- [ ] Implementation order step 9 "Done when": invalid parameters return 400 (the tests above)
- [ ] No response body in the tests contains the test's `GITHUB_TOKEN` value or the word `Traceback`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_web.py src/tests/reports/test_service.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Task 3
- Key files: `src/wambatic/reports/web.py`, `src/tests/reports/test_web.py`
- Docs: [FastAPI middleware](https://fastapi.tiangolo.com/tutorial/middleware/), [handling errors](https://fastapi.tiangolo.com/tutorial/handling-errors/), [lifespan events](https://fastapi.tiangolo.com/advanced/events/), [async tests](https://fastapi.tiangolo.com/advanced/async-tests/), [HTTPX ASGI transport](https://www.python-httpx.org/advanced/transports/#asgi-transport)
- The request's key is `(the target text as given, resources_for(groups) & BUILT_RESOURCES)`, so `octocat` and `user:octocat` are different jobs; that is harmless and keeps the key known before resolution.
- The tests' `base_url` of `http://127.0.0.1:8000` gives the scope that `Host` and port, so the default `check_host=True` holds in tests; the 403 test sets the header explicitly.
- Done. Middleware order, outermost first: request log, `Host` check, error conversion. A `job` parameter that names no known job is ignored, so the request goes through the freshness check as if it had none. A form submits empty fields as empty strings, which the parameter parsing treats as left out. `/api/progress` reports `rows_written` as the total over all resources, and `repos_done` as null until `repos_pending` is known.
- Tests that start a sync without `GITHUB_TOKEN` also replace `subprocess.run`, because `resolve_token` falls back to `gh auth token`, which would find a real token and reach the network.

---

## Task 5: The form, `/report` and the progress page

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** Web app (routes `/` and `/report`, Sync jobs, Pages); Error handling (page form); review-3.md choices 5, 8 and 14

**User Story:** As a user running `wambatic serve`, I want to type a target into a form and get the same report page `--format html` writes, with a progress page while a large org syncs, so that I can explore any account from the browser.

**Subtasks:**

- [ ] Add `templates/form.html`, `templates/progress.html`, `templates/progress.js` and `templates/message.html`, read with `importlib.resources` and filled with `string.Template` like the report's templates; the pages use the report's CSS variables for colours (inline the shared `report.css`, or a small subset of it with a comment naming the source, never a second palette) and load nothing from outside the server
- [ ] `/`: the form of the spec, with `default_target` (escaped) as the target field's value
- [ ] `/report`: the same freshness and job logic as `/api/stats` (one shared function, not a copy), computing the five `html.period_requests` and answering `html.html_document(html.html_report(results, initial), settings.report.html_theme)` as a `fastapi.responses.HTMLResponse` with 200 and `text/html; charset=utf-8`; `/` and `/report` are left out of the OpenAPI schema (`include_in_schema=False`); `by=total` is a 400; a sync answers 202 with `progress.html`, which embeds the job id and the reload URL (the request's URL with `job=ID` set) as escaped JSON in `<script type="application/json">`, as the report page embeds its data
- [ ] `progress.js`: poll `/api/progress?job=ID` once a second, write the state and counts into the page, `location.replace` the reload URL on `done`, show the error on `failed`, and stop polling on either
- [ ] Extend the error middleware: for `/` and `/report`, errors render `message.html` (status, escaped message, link to `/`) instead of JSON
- [ ] Write tests in `src/tests/reports/test_web.py`: `/` contains a form to `/report` and the escaped default target (a target containing `<` is escaped); `/report` on a fresh cache equals `html_document` of the `org_report` fixture's report with the same theme; `/report?...&by=total` answers 400 as `message.html`; a stale cache answers 202 with the job id in the page's JSON; after the job is done, `/report?...&job=ID` answers 200 with the report and no second sync; an unknown target's job ends `failed` and `/report?...&job=ID` answers 404 as `message.html`, after which a new request starts a new job

**Acceptance Criteria:**

- [ ] `/report` serves byte-for-byte the document `report --format html` would write for the same request and cache (the test above)
- [ ] `node --check` passes on `templates/progress.js` where `node` is available (say in Notes if it is not)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_web.py src/tests/reports/test_html.py` passes

**Notes:**

- Depends on Task 4
- Key files: `src/wambatic/reports/web.py`, `src/wambatic/reports/templates/form.html`, `progress.html`, `progress.js`, `message.html`, `src/tests/reports/test_web.py`
- Templates are package data already (`report.html` is read the same way); check that `uv_build` includes the new files by `python -c 'import importlib.resources; print(importlib.resources.files("wambatic.reports") / "templates" / "progress.js")'` reading it.
- Done. `node --check` passes on `templates/progress.js`. The pages inline the report's own stylesheet through `html.stylesheet()` and `html.theme_attribute()`, so there is no second palette.
- Found while testing the default form (no `since`): `html_document` refused every report without a requested start, because each period result begins at its own bucket start and `first_difference` compared the resolved starts. This was already so for `report --format html` without `--since`. The comparison now skips the resolved start when none was requested, with a regression test in `test_html.py`.

---

## Task 6: The `serve` command

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`is_loopback`, `check_bind`, `serve`); Command line (`serve` and its flags); Web app (Security, Logging, Stopping); Error handling (binding `OSError`, Ctrl-C, `CacheVersionError`); Settings (`allow_remote`, `web_host`, `web_port`); review-3.md choices 9, 10, 12 and 13

**User Story:** As a user, I want `wambatic serve octocat` to start the web app on my machine only, and to refuse a public address unless I say so, so that nobody else can use my GitHub token through it.

**Subtasks:**

- [ ] Add `is_loopback` and `check_bind` to `web.py` as the spec says (`ipaddress.ip_address` on the host with any `[` `]` stripped; `localhost` exactly; nothing resolved); `check_bind` raises `UsageError` naming `--allow-remote` and `report.allow_remote`, and with `allow_remote` logs the warning
- [ ] Add `serve(settings, *, default_target, ignore_cache_version)`: `check_bind`, parse `default_target` with `service.parse_target` when given, open the cache (`Cache.open(..., ignore_version=ignore_cache_version)`), bind the listening socket itself with `socket.create_server((host, port))` (an `OSError` here becomes exit 1 with `cannot listen on HOST:PORT: reason`; add a `ServeError` to `reports/errors.py` only if `OutputError`'s name would mislead, and say which in Notes), log the listening line and the target's report URL, and run `make_app(..., check_host=not remote)` with `uvicorn.Server(uvicorn.Config(app, loop='asyncio', lifespan='on', log_config=None, access_log=False, log_level='warning')).run(sockets=[sock])`; close the socket and the cache in a `finally`, whether `run` returns or raises
- [ ] Add the cappa `Serve` command to `cli.py` (`target` optional, `--host`, `--port`, `--allow-remote`, `--max-age`, `--ignore-cache-version`) in `Wambatic.command`'s subcommands; its flags reach settings through `load_settings(None, overrides)` (`report.web_host`, `report.web_port`, `report.allow_remote`, `fetch.max_age`); a port outside 1 to 65535 is a `UsageError`; `execute` dispatches to `web.serve`
- [ ] Write tests: `is_loopback` is true for `localhost`, `127.0.0.1`, `127.1.2.3`, `::1`, `[::1]` and false for `0.0.0.0`, `::`, `192.168.1.2`, `localhost.example`, `example.com`, `` (empty); a hypothesis test over `ipaddress.IPv4Address` values agrees with `.is_loopback`; `main(['serve', '--host', '0.0.0.0'])` returns 2 and never binds or calls `uvicorn.Server.run` (both monkeypatched to record calls); `--allow-remote` with the same host calls `run` with an app whose `Host` check is off and logs the warning; `serve --port 0` and `--port 70000` return 2; `serve 'a/b/c'` returns 2; a cache written by another version returns 1 before binding; `socket.create_server` raising `OSError` (`EADDRINUSE`) returns 1 with the reason; `run` raising `KeyboardInterrupt` (what uvicorn re-raises after a Ctrl-C shutdown) returns 130 and the cache and socket are closed; `run` returning returns 0; `wambatic serve --help` lists every flag

**Acceptance Criteria:**

- [ ] Implementation order step 9 "Done when": a non-loopback bind without the flag refuses to start (the `0.0.0.0` test)
- [ ] `wambatic --help` lists `serve`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_web.py src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 5
- Key files: `src/wambatic/reports/web.py`, `src/wambatic/cli.py`, `src/tests/reports/test_web.py`, `src/tests/test_cli.py`
- Docs: [uvicorn settings](https://www.uvicorn.org/settings/), [uvicorn programmatic use](https://www.uvicorn.org/deployment/#running-programmatically), [ipaddress](https://docs.python.org/3.14/library/ipaddress.html)
- The socket is bound by `serve`, not by uvicorn, because uvicorn logs a bind failure and calls `sys.exit(1)` itself, which would bypass `main`'s error conversion (review-3.md choice 19). Confirm this in the resolved uvicorn's `Server.startup` and note what was found.
- uvicorn's own stdlib logging is left unconfigured (`log_config=None`) at `warning`, so only its warnings and errors reach stderr, through Python's last-resort handler; wambatic's lines go through loguru. Confirm on the day that the resolved uvicorn re-raises the captured SIGINT after a graceful shutdown (it has since 0.29); if it returns instead, Ctrl-C is exit 0, and say so in Notes and the README.
- `serve` blocks; tests never call the real `uvicorn.Server.run` (Task 7's browser test runs a real `uvicorn.Server` in a thread instead).
- Done. A `ServeError` in `reports/errors.py` carries the bind failure, since `OutputError`'s name would mislead; `main` treats it as status 1. The port range is checked in `serve`, so a bad `report.web_port` in the config file is caught as well as the flag. Checked against the resolved uvicorn 0.54.0: `Server.run(sockets=[...])` does not bind, `Server.serve` re-raises the captured signals after a graceful shutdown (`signal.raise_signal`), and a real `wambatic serve` stopped by SIGINT from a Python parent exits 130. (From a non-interactive shell's background job, where SIGINT is ignored, it exits 0, which is the shell's doing.)

---

## Task 7: A large org does not block the page, end to end

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** Web app (Testing); implementation order step 9 "Done when"; review-3.md choice 15

**Technical Goal:** Show that a long sync leaves the app responsive, and that the progress page turns into the report in a real browser.

**Subtasks:**

- [ ] Add to `tests.fixtures.fetch.upstream` (or `tests.fixtures.reports`) a generator of a large org: a few hundred `FakeRepo`s with one or two commits each, generated, not written out; name the count as a constant used by the test, not in prose
- [ ] Write a test in `src/tests/reports/test_web.py`: with `Upstream.history_delay` set so the sync takes several seconds, `/report` answers 202 within a second; while the job is `syncing`, `/` and `/api/progress` each answer within a second (time them with `time.monotonic`), and two `/api/progress` reads a delay apart show `repos_done` rising; the job ends `done` and `/report?...&job=ID` answers 200
- [ ] Write `src/tests/reports/test_web_browser.py` (marker `browser`, launching Chromium as `test_html_browser.py` does, reusing its launch helper rather than copying it): bind `127.0.0.1` port 0 with `socket.create_server`, run a real `uvicorn.Server` for `make_app` on that socket in a thread (`server.run(sockets=[sock])`, stopped by setting `server.should_exit`), against the `Upstream` fake with a short `history_delay`; open `/report?target=...` and check that the progress text appears, then that the page becomes the report with every chart drawn, with no console error, no page error and no request to any host but the server
- [ ] Build the app's fixtures before launching the browser, as the step 7 notes require (Playwright's sync API cannot share a thread with `asyncio.run`)

**Acceptance Criteria:**

- [ ] Implementation order step 9 "Done when": a large-org fixture does not block the page (the first test)
- [ ] `pytest -m browser -rs src/tests/reports/test_web_browser.py` passes, not skipped, in an environment with Chromium

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_web.py` passes
- [ ] `pytest -m browser -rs src/tests/reports/test_web_browser.py src/tests/reports/test_html_browser.py` passes (not skipped)

**Notes:**

- Depends on Task 6
- Key files: `src/tests/reports/test_web.py`, `src/tests/reports/test_web_browser.py`, `src/tests/fixtures/fetch/upstream.py`
- If the timing test takes more than ten seconds, lower the repo count or the delay rather than marking it `slow`: the step's check must run in the `check` CI job.
- CI's `browser` job already runs every `browser` test, so no workflow change is needed.
- Done. The `chromium` fixture moved from `test_html_browser.py` to `src/tests/reports/conftest.py` so both browser modules share it. The large-org test takes several seconds; it is not marked `slow`. The browser test runs the replay GitHub and the uvicorn server on one event loop in one thread (`uvicorn.Server.serve`), stopped by `should_exit`.

---

## Task 8: README web app section

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** shared user-guides rule; Command line (`serve`); Web app; review-3.md choice 17

**User Story:** As a user, I want the README to tell me how to start the web app, what it can reach and how to keep it private, so that I can run it safely.

**Subtasks:**

- [ ] Add a `## The web app` section after `## The HTML report`: a first command (`wambatic serve octocat`, then open the printed URL), the form and the progress page, `--max-age` (and why the default re-syncs on every page), `/api/stats` and `/api/progress` with one `curl` example each and the 202-then-`job` flow, the generated API page at `/docs` (and that it loads Swagger UI from jsDelivr, so it needs a network connection where the other pages do not), and the security notes (loopback only by default, `--allow-remote` and what it exposes, the `Host` check, the token never sent to the browser)
- [ ] Add a `## wambatic serve options` table like the report options table
- [ ] In the config file table, drop "not built yet" from `report.allow_remote`, `report.web_host` and `report.web_port` and describe each; in Exit statuses add `serve`'s (2 for a non-loopback host without `--allow-remote`, 1 for a port that cannot be bound, 130 on Ctrl-C as for `report`); in Limits drop the web app from the "not built yet" line

**Acceptance Criteria:**

- [ ] Every `serve` flag and every web setting appears in the README with its default
- [ ] `grep -n 'not built yet' README.md` no longer mentions the web app or `serve`

**Definition of Done:**

- [ ] `pre-commit run --all-files` passes

**Notes:**

- Depends on Task 7
- Key files: `README.md`
- Follow the shared markdown rule (ASCII punctuation) and the counts-in-prose rule (no counts of routes or flags).
- Done.

---

## Task 9: Exports, layering and closing checks

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** Module location (layering); API; implementation order step 9 "Done when"

**Technical Goal:** Expose the step 9 names, confirm the import rules, remove what the new modules duplicate, run every test this list can reach, and mark the step done.

**Subtasks:**

- [ ] In `src/wambatic/reports/__init__.py`, import and list in `__all__`: `Jobs`, `SyncJob`, `check_bind`, `html_report`, `is_loopback`, `make_app`, `period_requests`, `serve`, keeping the existing order convention; the `service.py` names are not exported (they are the CLI's and the web app's shared internals, reached as `wambatic.reports.service.*`)
- [ ] Extend `src/tests/test_package.py` so every new name resolves, and check `src/tests/test_layering.py` passes with only `service` and `web` importing `wambatic.fetch`
- [ ] Hoist anything the new modules duplicate to a single owner: grep the tree for each literal collection, constant and one-line helper `service.py`, `web.py`, the new templates and the `cli.py` changes define (target forms and patterns, the loopback names, the error-to-status mapping, the escaped-JSON embedding that `html.py` already does, template loading, the CSS variables), and import rather than copy, choosing the owner from the existing import graph (prefer `service.py`, `html.py` or `rows.py`, which the web app already imports)
- [ ] Check the implementation order's "Done when" for step 9: a large-org fixture does not block the page (Task 7), invalid parameters return 400 (Task 4), a non-loopback bind without the flag refuses to start (Task 6); record where each is shown in this task's Notes
- [ ] Run every test that imports a changed module directly or transitively: `pytest src/tests/fetch src/tests/stats src/tests/reports src/tests/test_cli.py src/tests/test_package.py src/tests/test_layering.py -m 'not browser and not live'`, and `pytest -m browser -rs src/tests/reports`
- [ ] In `agents/specs/implementation-order.md`, set step 9's Status to `done: [tasks-3](../tasks/reports/tasks-3.md)`

**Acceptance Criteria:**

- [ ] `python -c 'import wambatic.reports, wambatic.cli'` works and `wambatic serve --help` lists every flag
- [ ] Every step 9 "Done when" item is met, or its gap is recorded in the task that owns it

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch src/tests/stats src/tests/reports src/tests/test_cli.py src/tests/test_package.py src/tests/test_layering.py -m 'not browser and not live'` passes
- [ ] `pytest -m browser -rs src/tests/reports` passes (not skipped)

**Notes:**

- Depends on Tasks 1 to 8
- The project has no affected-tests tool; the commands above name every test directory that reaches a module this list changed: `wambatic.fetch.base` (Task 1) is imported by the fetch, stats and reports tests, `wambatic.reports` by the reports and CLI tests, and the package and layering tests check the whole tree.
- The reports spec's `**Status:**` stays `proposed` (see the header).
- Key files: `src/wambatic/reports/__init__.py`, `src/tests/test_package.py`, `src/tests/test_layering.py`, `agents/specs/implementation-order.md`
- Done. Where each "Done when" item is shown: a large-org fixture does not block the page, `test_a_large_orgs_sync_does_not_block_the_pages` and the browser test `test_the_progress_page_becomes_the_report_with_every_chart_drawn`; invalid parameters return 400, `test_invalid_parameters_answer_400_with_the_cli_message`; a non-loopback bind without the flag refuses to start, `test_serve_refuses_a_public_host_before_binding`.
- `web.py` builds its error-class tuple inside `error_status` rather than at module level, because `wambatic.reports.errors` cannot be reached through the `wambatic.reports` attribute while the package's `__init__` is still importing `web`.
- Duplicates checked: the HTML theme attribute, the CSS, the escaped-JSON embedding and the template loader are the report's own (`html.theme_attribute`, `html.stylesheet`, `html.json_for_script`, `html.read_template`); target forms, patterns and the error redaction are `service.py`'s; the error-to-status mapping is `web.error_status`.
