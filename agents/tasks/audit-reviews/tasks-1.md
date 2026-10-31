# Tasks: Audit review 1

**Source:** `agents/audit-reviews/review-1.md`
**Created:** 2026-10-31
**Version:** 1

This list fixes everything the first audit found and the user approved on 2026-10-31: findings F1-F19 and M1 of [review-1.md](../../audit-reviews/review-1.md), with option B chosen for all five of its decisions and the follow-up choices recorded under its Answers. It also puts gates in place so that the same failures cannot come back unnoticed, as the user asked on 2026-10-31: ruff rules that match the coding standards on every commit, and the audit sweep as a `pre-push` hook and a CI job (Tasks 1 and 15).

The redesign behind finding F8 (Decision 3) is specified first: version 1.6 of the [stats spec](../../specs/stats/spec.md) (`read_records`, `aggregate`, `compute_all`) and version 1.9 of the [reports spec](../../specs/reports/spec.md) (`build_results` reads once; the HTML page builds each figure once), both written 2026-10-31 and set to `proposed` until Task 15.

Decisions carried into this list, in the user's words of the review page and follow-ups:

- Decision 1 (B): every one of the 445 script hits under `src/tests/` is fixed in code; none is accepted with a marker and no skill change is requested.
- Decision 2 (B): every stdlib raise in a package with domain errors becomes a domain error, and the four spec passages that name `ValueError` are amended.
- Decision 3 (B): read once, build once, per the amended specs.
- Decision 4 (B): each subpackage `__all__` is trimmed to what `system/spec.md:23` promises; the top-level `wambatic` surface stays.
- Decision 5 (B): property tests for every area T2 lists, and tests for `bin/record-fixtures.py`.
- F9: the delivery failure window and the hidden-stargazer rule keep the code's behaviour and the specs are amended; `cache info` becomes read-only in code.
- F10: the Languages table always ends in one `Other` row.
- Gates: audit sweep on `pre-push` and in CI through a read-only deploy key the user adds.

A task that meets a case none of these names stops for the user instead of choosing. Hit counts and line numbers below were measured by the audit on 2026-10-31; earlier tasks move lines, so each task works from a fresh `bin/audit-check.sh` run, not from these figures.

## Coverage

| Finding or decision | Covered by |
|---|---|
| Gates (ruff rules per commit, audit check script) | Task 1 |
| F1 | Task 2 |
| F2, F3, F4 | Task 3 |
| F5 / Decision 2, F7, `missing-raises-section`, `mixed-raise-types`, `sibling-errors-no-common-base` | Task 4 |
| F6 | Task 5 |
| F8 / Decision 3, F12, P1 hits | Task 6 |
| F13, F14, `mutable-store-without-copy` | Task 7 |
| F15, F16, A17 / Decision 4 | Task 8 |
| M1 (script hits in `src/wambatic` and `bin`) | Task 9 |
| Decision 1, test-tree hits other than literals and ordering | Task 10 |
| Decision 1, test-tree `literal-duplication`, `non-alphabetical-*`, `mutable-module-level-exported` | Task 11 |
| F17 / Decision 5, fetch, settings, CLI and `bin` tests | Task 12 |
| F17 / Decision 5, stats and reports tests | Task 13 |
| F9, F10, F11, F18, F19 | Task 14 |
| Gates (pre-push hook, CI job), closing the audit | Task 15 |

There is no `TODO.md` in this repository, so no item moves to `DONE.md`.

---

## Task 1: Gate the coding standards on every commit and add the audit check script

**Status:** done
**Priority:** high
**Complexity:** small
**Source Reference:** user request of 2026-10-31 (gates); review-1 Automatic checks

**Technical Goal:** Make the rules a tool can check run on every commit, and give every later task a command that says whether its audit rules are clear, so no task depends on following the rules from memory.

**Subtasks:**

- [x] Add `PLC0415`, `T20`, `BLE001`, `RUF022` and `TID252` to `[tool.ruff.lint] select` in `pyproject.toml` (keep the list alphabetical); set `[tool.ruff.lint.flake8-tidy-imports] ban-relative-imports = 'all'` with a per-file ignore of `TID252` for `**/__init__.py`, and a per-file ignore of `T20` for `src/wambatic/cli.py` and `bin/record-fixtures.py` (the CLI entry points the coding standard lets print)
- [x] Fix every hit the new rules report (`ruff check --select PLC0415,T20,BLE001,RUF022,TID252 src bin` showed 1, 2, 3, 0 and 0 on 2026-10-31); where `BLE001` fires on a handler review-1 says stays (`reports/web.py:146`, `:402`), add `# noqa: BLE001` with the reason, the same reason as its audit marker in Task 9
- [x] Write `bin/audit-check.py` and its wrapper `bin/audit-check.sh` (utilities rule: dashes, wrapper sources `bin/activate.sh`): it runs `python3 .agents/claude/skills/auditme/checks/audit.py <repo root>`, prints each `accepted: false` hit as `path:line rule variant`, and exits 1 when there is one; `--rule NAME` (repeatable) and `--path PREFIX` (repeatable) restrict which hits count; it exits 2 with a message naming `git submodule update --init` when `.agents` is empty
- [x] Use argparse with the one-argument-per-line trailing-comma layout (argparse rule)
- [x] Add tests in `src/tests/test_audit_check.py` that run the script's filter and exit-status logic on a fixed JSONL sample (no checker run), including the empty-submodule message

**Acceptance Criteria:**

- [x] `ruff check` passes with the new rules selected
- [x] `bin/audit-check.sh --rule typing-deprecated-alias --path src/wambatic` lists the six `typing-deprecated-alias` hits in `src/wambatic` and exits 1 (they are fixed in Task 9)
- [x] `bin/audit-check.sh` with `.agents` empty exits 2 and names the command that fills it

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] The task's commit passes its pre-commit hooks (`ruff-check`, `ruff-format`, `mypy`, end-of-file and whitespace; never `--no-verify`)
- [x] `pytest src/tests/test_audit_check.py src/tests/reports/test_web.py src/tests/test_cli.py` passes

**Notes:**

- Key files: `pyproject.toml`, `bin/audit-check.py`, `bin/audit-check.sh`
- `.agents` must be initialised (`git submodule update --init`); it was on 2026-10-31 at `ec0d8ca`, whose checker digest matches the audit's (`4d7de71f...`)
- The hook that runs `bin/audit-check.sh` is added in Task 15, once the hits are gone; adding it now would fail every push

---

## Task 2: Redact the web server's error log

**Status:** done
**Priority:** high
**Complexity:** small
**Source Reference:** F1 (Sec5, S4)

**User Story:** As someone running `wambatic serve`, I want an unexpected error's log line to hide my GitHub token, so that the server log never holds a secret.

**Subtasks:**

- [x] Move the CLI's redaction (`redact_exception` and `redact_environment_token`, `cli.py:403-405`) into one helper in `reports/service.py` that returns the redacted message and strips the token from the exception's args
- [x] Use it in `reports/web.py` `error_response` before `loguru.logger.exception`, and in `cli.main`
- [x] Add a regression test in `src/tests/reports/test_web.py` that makes a route raise an exception whose message holds a fake token set as `GITHUB_TOKEN`, and asserts the captured log has the message without the token

**Acceptance Criteria:**

- [x] The new test fails on the current `error_response` and passes after the change (checked both ways)
- [x] The CLI's existing redaction tests still pass unchanged

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [x] `pytest src/tests/reports/test_web.py src/tests/reports/test_service.py src/tests/test_cli.py` passes

**Notes:**

- Key files: `src/wambatic/reports/web.py:71-78`, `src/wambatic/cli.py:397-406`, `src/wambatic/reports/service.py:251`

---

## Task 3: Translate failures at each boundary into domain errors

**Status:** todo
**Priority:** high
**Complexity:** large
**Source Reference:** F2 (A1, A2), F3 and F4 (Sec2)

**User Story:** As a CLI user, I want a dropped network, a locked cache or an unreadable config to give me one line saying what failed, so that I am not handed a traceback for an everyday failure.

**Subtasks:**

- [ ] `fetch/client.py`: after the retries run out, raise `FetchError` (with the cause chained) for aiohttp `ClientError` and `TimeoutError` at `:211` and `:290`, and replace the `aiohttp.ClientResponseError` of `status_error` (`:327`, `:333`) with a `FetchError` naming the status; wrap `session.close()` (`:133`)
- [ ] `fetch/errors.py`: add `CacheError(FetchError)`; `fetch/cache.py`: translate `sqlite3.Error` and `OSError` into `CacheError` through one context manager used by every `Cache` method and by `inspect_cache`/`clear_cache` (each A1 row from `cache.py:372` to `:962`), with the path in the message
- [ ] Widen the narrow handlers: `settings.py:146` to `OSError` and `UnicodeDecodeError`, `fetch/auth.py:12` to `OSError` and `UnicodeDecodeError`, `fetch/cache.py:961` to `OSError`, `reports/service.py:82` to add `OSError`, `cli.py:231` to add `UnicodeDecodeError`; `reports/html.py:125` (`read_template`) and `:597` (`get_plotlyjs`) raise `OutputError` on `OSError`/`UnicodeDecodeError`
- [ ] `version.py:3`: fall back to `'0+unknown'` on `importlib.metadata.PackageNotFoundError`, with a test
- [ ] `reports/web.py:573`: translate `OSError` from `uvicorn.Server.run` into `ServeError`
- [ ] `cli.py:400`: guard `os.open`/`os.dup2` in the `BrokenPipeError` handler with `OSError`
- [ ] `bin/record-fixtures.py:108`, `:109`, `:235`, `:236`: translate into one `RecordingError` defined in the script, caught in `main` with a one-line message and exit 1
- [ ] F3: `settings.parse_duration` raises `SettingsError` on `OverflowError`; test with `99999999999d`
- [ ] F4: `service.make_request` rejects `since` before 2008-01-01 or `until` after tomorrow in `tz` with `UsageError` naming the bound; tests through the CLI (exit 2) and `/report` (400)
- [ ] One test per translated error: a fake aiohttp failure after retries, a locked SQLite file, a non-UTF-8 config file, a `gh` that cannot be executed, an unwritable cache file

**Acceptance Criteria:**

- [ ] With the network unreachable, `wambatic report <target>` prints one error line naming the failure and exits 1 with no traceback (test with the fake upstream closed)
- [ ] `--max-age 99999999999d` exits 2 with a settings message
- [ ] `/report?since=0001-01-01` answers 400
- [ ] `bin/audit-check.sh --rule filesystem-op-without-envelope` exits 0

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/fetch/test_client.py src/tests/fetch/test_cache.py src/tests/fetch/test_auth.py src/tests/test_settings.py src/tests/test_cli.py src/tests/reports/test_service.py src/tests/reports/test_web.py src/tests/reports/test_html.py src/tests/test_package.py` passes

**Notes:**

- Depends on Task 1
- The README's exit-status table (exit 1 for fetch failures, 2 for usage) must stay true; update it if a message it quotes changes
- `cli.main` maps `FetchError` to exit 1 already, so `CacheError` needs no new mapping

---

## Task 4: Raise domain errors everywhere and make enum chains exhaustive

**Status:** todo
**Priority:** high
**Complexity:** medium
**Source Reference:** F5 / Decision 2 (B), F7 (A11), script rules `layer-has-domain-error-raises-stdlib`, `mixed-raise-types`, `sibling-errors-no-common-base`, `missing-raises-section`, `assert-never-missing`

**Technical Goal:** Every raise in `fetch`, `stats`, `reports` and `settings` uses the package's own error family, every chain over an enum or literal ends in `typing.assert_never`, and each function's docstring says what it raises.

**Subtasks:**

- [ ] `reports/errors.py`: add `ReportsError(Exception)` as the base of `OutputError`, `ServeError` and `UsageError`; catch it in `cli.main` where the three are caught today
- [ ] Convert each of the 23 A3 sites in review-1 (`settings.py:110`; `fetch/client.py:209`, `:222`; `fetch/cache.py:206`, `:541`; `fetch/base.py:36`, `:38`, `:43`, `:689`, `:1248`; `stats/base.py:36`; `stats/buckets.py:23`, `:40`, `:64`, `:75`, `:128`; `reports/html.py:108`, `:110`, `:115`, `:118`, `:120`; `reports/figures.py:549`, `:564`): `SettingsError`; `FetchError` (a new `InvalidRequestError(FetchError)` in `fetch/errors.py` for caller mistakes such as unknown resources and bad subjects); `stats` `InvalidRangeError` for `since` after `until`, `InvalidRequestError` for the others; `UsageError` in `reports`
- [ ] Update every test that expects `ValueError`, `TypeError` or `RuntimeError` from these sites
- [ ] Amend the spec passages that name `ValueError`: `stats/spec.md` (`bucket_start`, the `Raises ValueError for Granularity.TOTAL` docstring), `reports/spec.md` (the `build_calendar` and `html_document` docstrings, and the system and reports error lists, which also gain `OutputError`, `ServeError` and `ReportsError`), `fetch-and-cache/spec.md` (the unknown-resources docstring); bump each spec's minor version with a sentence citing review-1 Decision 2
- [ ] F7: `stats/buckets.py:22`, `:39` handle `Granularity.TOTAL` in its own `case` (raising the domain error) and end in `case _: typing.assert_never(granularity)`; `fetch/base.py:1272`, `:1276`, `:1278` end their chains on `resource` in `else: typing.assert_never(resource)`, with `resource` typed as the resources literal
- [ ] Add a `Raises:` section to each of the 23 `missing-raises-section` functions, naming the domain errors it raises or lets through from its own package

**Acceptance Criteria:**

- [ ] `grep -rn "raise ValueError\|raise TypeError\|raise RuntimeError" src/wambatic` finds nothing
- [ ] `bin/audit-check.sh --rule layer-has-domain-error-raises-stdlib --rule mixed-raise-types --rule sibling-errors-no-common-base --rule missing-raises-section --rule assert-never-missing` exits 0
- [ ] `mypy src` passes, which now proves the chains exhaustive

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/test_settings.py src/tests/fetch src/tests/stats/test_buckets.py src/tests/stats/test_base.py src/tests/reports/test_html.py src/tests/reports/test_figures.py src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 3 (it adds `CacheError` and touches the same handlers)
- Key files: `src/wambatic/*/errors.py`, the 23 sites above, `agents/specs/*/spec.md`

---

## Task 5: Give every setting one owner

**Status:** todo
**Priority:** medium
**Complexity:** medium
**Source Reference:** F6 (A5)

**Technical Goal:** Remove the five pairs of values that can disagree, so which value wins never depends on the call site.

**Subtasks:**

- [ ] `StatsRequest`: keep `tz` as the single zone; remove `timezone` from what `reports/base.py:57-61` writes from `settings`, or write `tz` there, so the JSON output holds one zone; record which in `reports/spec.md` (JSON output)
- [ ] `service.make_request`: take no separate `tz` when it can resolve it from `settings` and the `--tz`/`tz` override, so `tz` and `settings.stats.timezone` cannot disagree
- [ ] `service.build_results` and `sync_target`: drop the `by_author` parameter and read `requests[0].by_author`; `web.Query` drops its own `by_author`; `cli.py:257-262` follows
- [ ] `web.make_app`: derive `check_host` from `settings.report.allow_remote` inside `make_app`; drop the parameter; `serve` and the tests follow
- [ ] `fetch.base.Fetcher.__init__`: when a `client` is injected, raise the fetch `InvalidRequestError` if `client.settings is not settings` (a caller bug), and document that the two are one object
- [ ] Tests for each: the JSON output's zone, a disagreeing `client.settings`, `make_app` with `allow_remote` on and off

**Acceptance Criteria:**

- [ ] No public function takes both a value and a settings object that holds the same value
- [ ] The API sections of the stats and reports specs match the new signatures

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/reports/test_service.py src/tests/reports/test_web.py src/tests/reports/test_base.py src/tests/test_cli.py src/tests/fetch/test_fetcher.py src/tests/stats` passes

**Notes:**

- Depends on Task 4 (it uses the fetch `InvalidRequestError`)
- Key files: `src/wambatic/stats/base.py:46-49`, `src/wambatic/reports/service.py:88-117`, `:170`, `:210-221`, `src/wambatic/reports/web.py:220-227`, `:298-303`, `src/wambatic/fetch/base.py:529-540`

---

## Task 6: Read the cache once and build each figure once

**Status:** todo
**Priority:** medium
**Complexity:** large
**Source Reference:** F8 / Decision 3 (B), A14, P1, P3; F12 (P2); stats spec 1.6 "Reading once for several requests"; reports spec 1.9 "Built once"

**User Story:** As a user of the HTML report or the web app, I want a report built from one read of the cache, with no figure built twice, and a server that does not stall while `gh` runs, so that large organisations' reports come back quickly.

**Subtasks:**

- [ ] `stats/compute.py`: implement `CachedRecords`, `read_records`, `aggregate` and `compute_all` as stats spec 1.6 gives them; `compute` becomes `read_records` then `aggregate`; `resources_for(request.groups)` is called once per read; export them as the spec's API says
- [ ] `reports/service.py` `build_results`: call `wambatic.stats.compute_all`
- [ ] `reports/html.py`: build each period's figures, the range figures and the calendar once in `html_document` and pass them to `period_figures`, `sections_html` and `page_data`; build each section's table once and reuse it for the presence test
- [ ] `reports/rows.py`, `figures.py`, `terminal.py`: derive `total_series` and `bucket_list` once per function and pass them on (the P3 rows `rows.py:233-311`, `figures.py:395-404`, `terminal.py:137-138`, `:337`)
- [ ] `fetch/base.py:652`: pass the `SyncState` `unchanged()` read to the `sync_*` methods instead of re-reading it (`:839`, `:905`, `:977`, `:1035`, `:1098`)
- [ ] P1: `stats/delivery.py:183` finds the hotfixes in each deployment's window with `bisect` over each repo's sorted `opened` times; `reports/terminal.py:147` finds how many buckets fit in one pass; `stats/activity.py:99-109` keeps per-author and per-repo tallies only for buckets with records
- [ ] F12: `reports/service.py:183`, `:198` call `resolve_token` through `asyncio.to_thread`; `reports/html.py` `read_template` gets `functools.cache` (templates are package data, fixed for the process)
- [ ] Tests: `compute_all` returns what five `compute` calls return for the same requests (hypothesis over granularities and ranges against the fixture cache); `compute_all` reads each record once (a counting fake fetcher); `compute_all` raises `InvalidRequestError` for requests that differ in more than granularity, and for an empty list; `html_document` output is unchanged byte for byte against the existing fixtures

**Acceptance Criteria:**

- [ ] A five-period HTML report calls each `Fetcher` read method once per repository (counting fake)
- [ ] Every existing HTML, terminal, JSON and web test passes unchanged
- [ ] The P1 rewrites give the same results as before on the hypothesis inputs

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/stats src/tests/reports src/tests/fetch/test_fetcher.py src/tests/test_cli.py src/tests/test_package.py` passes
- [ ] `pytest -m browser src/tests/reports` passes (the page's script reads the same data)

**Notes:**

- Depends on Task 5 (it changes the `build_results` and `make_request` signatures this task calls)
- The specs for this task were amended first (stats 1.6, reports 1.9, 2026-10-31); follow them, and stop for the user if the code needs something they do not say

---

## Task 7: Freeze shared constants and give each record one field list

**Status:** todo
**Priority:** low
**Complexity:** medium
**Source Reference:** F13 (A20), F14 (A15, A13), script rules `mutable-module-level-exported` (in `src/wambatic`) and `mutable-store-without-copy`

**Technical Goal:** No caller can change a shared constant, and adding a field to a record means editing one place.

**Subtasks:**

- [ ] `stats/delivery.py:36` `UNITS` and `reports/figures.py:40` `PALETTE`: wrap in `types.MappingProxyType`; the four `__all__` lists become tuples
- [ ] `fetch/errors.py:16` `GraphQLError.errors` stores `tuple(errors)`; `CacheVersionError.differences` stores `types.MappingProxyType(dict(differences))`
- [ ] `fetch/cache.py`: derive each `*_COLUMNS` tuple, the repos and `sync_state` INSERT and SELECT column lists, and each row writer from `dataclasses.fields(<Record>)`, so the column list exists once per record (the A15 rows `cache.py:173-177`, `:433-461`, `:481-505`, `:598-765`)
- [ ] `fetch/cache.py` row readers build each record with `Record(**dict(zip(columns, row)))` plus the conversions, so a new field fails a test if a converter is missing
- [ ] A13: `reports/html.py:438` uses a named `PopularityRow.empty()` factory; `fetch/client.py:189-196` builds `RestResponse` by keyword
- [ ] A test that adding a field to a record without a cache column fails (schema built from the fields)

**Acceptance Criteria:**

- [ ] `bin/audit-check.sh --rule mutable-module-level-exported --rule mutable-store-without-copy --path src/wambatic` exits 0
- [ ] The cache schema version is unchanged (the derived columns equal today's, in order), so no existing cache needs a refresh

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/fetch src/tests/stats/test_delivery.py src/tests/reports src/tests/test_package.py` passes

**Notes:**

- Depends on Task 6 (both edit `reports/html.py` and `figures.py`)
- If the derived column order differs from the stored schema, stop: changing it would need a schema version bump and a cache refresh, which no decision covers

---

## Task 8: Smaller architecture, naming and package-surface fixes

**Status:** todo
**Priority:** low
**Complexity:** medium
**Source Reference:** F15 (A8, A9, A17, A19, A22, A23), F16 (S2, S4), Decision 4 (B)

**Technical Goal:** Names say what functions do, the package surfaces hold only what the spec promises, and each remaining review note is closed.

**Subtasks:**

- [ ] A9: rename `reports/service.build_results` to `sync_and_compute` and `reports/web.check_bind` to `warn_on_bind`, with every caller, test and spec mention
- [ ] A8: add a comment at `stats/activity.py` `Tally` and `reports/web.py` `SyncJob` saying they are mutable accumulators by design
- [ ] A19: add a comment at `fetch/cache.py:380` and `reports/html.py:617` saying the handler cleans up and re-raises (no audit marker is needed: the script has no hit there)
- [ ] A22: `fetch/base.py:757` logs the 404 as the reason (`compare returned 404`) before the full re-read
- [ ] A23: replace `self.plan_full_read(...)` in `sync_releases` (`fetch/base.py:978`) with a `log_full_read` that returns nothing
- [ ] Decision 4 (B): cut `fetch/__init__.py`, `stats/__init__.py` and `reports/__init__.py` `__all__` to the names `system/spec.md:23` lists for them (none for a subpackage that the spec does not list); keep `wambatic/__init__.py`; update `src/tests/test_package.py`
- [ ] S2: rename `cli.py:32` `GRANULARITIES` to `Granularities` and `:33` `FORMATS` to `Formats`; `src/tests/fetch/test_cache.py:497` `instants`, `:502` `commit_lists`, `src/tests/reports/test_base.py:174` `durations`, `:175` `words` to UPPER_SNAKE
- [ ] S4: move `restore_logger` (`src/tests/test_cli.py:821`, `src/tests/test_logs.py:10`) and `cache_path`/`cache` (`src/tests/fetch/test_cache.py:26`, `:31`) into `src/tests/conftest.py`; `src/tests/reports/test_terminal.py:209` fills its template with `string.Template` instead of `.format()`; add `src/tests/reports/test_errors.py` for the error hierarchy; move the `Fetcher` sync tests of `src/tests/fetch/test_fetcher.py` into `src/tests/fetch/test_base.py` or name the module in AGENTS.md as the deliberate exception (it is 1000+ lines; keep it separate and record that)
- [ ] S4 (`cli.py:385`, `:393`): keep `loguru.logger.error` for expected domain errors, with a comment citing review-1 F16

**Acceptance Criteria:**

- [ ] `src/tests/test_package.py` checks exactly the names the system spec lists
- [ ] No module-level type alias is UPPER_SNAKE and no module-level hypothesis strategy is lower_snake

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/test_package.py src/tests/test_cli.py src/tests/test_logs.py src/tests/fetch/test_cache.py src/tests/fetch/test_base.py src/tests/fetch/test_fetcher.py src/tests/reports` passes

**Notes:**

- Depends on Task 7
- F16 also proposes changing the shared coding standard to "use `logger.exception` for unexpected errors only". That is a change to the shared `agents` repository, not this one: it is not a task here, and it was reported to the user on 2026-10-31

---

## Task 9: Clear the script hits in src/wambatic and bin

**Status:** todo
**Priority:** low
**Complexity:** medium
**Source Reference:** M1 (review-1 Mechanical findings, every hit outside `src/tests/`)

**Technical Goal:** `bin/audit-check.sh --path src/wambatic --path bin` exits 0.

**Subtasks:**

- [ ] `typing-deprecated-alias` (6): `collections.abc` forms
- [ ] `reexport-in-non-init` (3): full paths at each use
- [ ] `literal-duplication` (16 in `src/wambatic`, 2 in `bin`): name each repeated literal once and reuse it
- [ ] `non-alphabetical-literal` (22 + 4) and `non-alphabetical-dict-keys` (5): sort where order means nothing; where it does (display order, column order, argv), add `# auditme: accept[<rule>] <why the order matters>`
- [ ] `passthrough-shim` (4): inline the shim, or accept with a scoped marker where it names a domain concept (`fetch/cache.py:214` `from_text`)
- [ ] `except-interpolation` (6): keep messages categorical, or accept with a scoped marker where the exception text is the payload
- [ ] `silent-broad-except` (`reports/web.py:146`, `:402`): `# auditme: accept[silent-broad-except] logged by error_response()`
- [ ] `subprocess-without-memoisation` (`fetch/auth.py:13`): `# auditme: accept[subprocess-without-memoisation] runs once per sync; a cached token would outlive gh auth changes in the long-running server`
- [ ] `duplicated-word` (`stats/buckets.py:73`): reword
- [ ] Any hit of a rule not listed here: stop for the user

**Acceptance Criteria:**

- [ ] `bin/audit-check.sh --path src/wambatic --path bin` exits 0
- [ ] Every accept marker is the scoped form `accept[<rule>]` with a reason

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests` for the test modules of each changed source module, named in the commit message, passes

**Notes:**

- Depends on Task 8 (Tasks 3-8 remove some of these hits, and the counts above are from 2026-10-31; work from a fresh `bin/audit-check.sh --path src/wambatic --path bin`)

---

## Task 10: Clear the test-tree script hits other than literals and ordering

**Status:** todo
**Priority:** low
**Complexity:** medium
**Source Reference:** Decision 1 (B): `aliased-imports`, `typing-deprecated-alias`, `reexport-in-non-init`, `in-function-import`, `except-interpolation`, `build-name-has-side-effect`, `passthrough-shim`, `paired-sibling-helpers`, `duplicate-call-sequence` under `src/tests/`

**Technical Goal:** The test tree follows the same import and naming rules as the source, fixed in code, with no accept markers.

**Subtasks:**

- [ ] `aliased-imports` (25): `import tests.fixtures.fetch.responses` and full paths at each use
- [ ] `typing-deprecated-alias` (18): `collections.abc` forms
- [ ] `reexport-in-non-init` (69): `datetime.UTC`, `wambatic.stats.base.Granularity` and so on at each use
- [ ] `in-function-import` (`src/tests/reports/test_html.py:197`): move to the top of the module
- [ ] `except-interpolation` (2), `build-name-has-side-effect` (2), `passthrough-shim` (9): fix in code (rename `compute_stats`/`build_with` to `run_*`; call the wrapped function directly)
- [ ] `paired-sibling-helpers` (6), `duplicate-call-sequence` (2): one shared helper each (the Playwright page opener into `src/tests/reports/conftest.py`)

**Acceptance Criteria:**

- [ ] `bin/audit-check.sh --path src/tests --rule aliased-imports --rule typing-deprecated-alias --rule reexport-in-non-init --rule in-function-import --rule except-interpolation --rule build-name-has-side-effect --rule passthrough-shim --rule paired-sibling-helpers --rule duplicate-call-sequence` exits 0
- [ ] No `# auditme: accept` marker is added under `src/tests/`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest` on every test module the task edits passes, and `pytest -m browser src/tests/reports` passes

**Notes:**

- Depends on Task 9

---

## Task 11: Clear the test-tree literal, ordering and fixture-constant hits

**Status:** todo
**Priority:** low
**Complexity:** large
**Source Reference:** Decision 1 (B): `literal-duplication` (254), `non-alphabetical-literal` (24), `non-alphabetical-dict-keys` (17), `mutable-module-level-exported` (16) under `src/tests/`

**Technical Goal:** Fix every remaining test-tree hit in code, as Decision 1 option B chose.

**Subtasks:**

- [ ] `literal-duplication`: name each repeated literal once (in the test module, or in `src/tests/fixtures/` when several modules share it) and reuse it
- [ ] `non-alphabetical-literal` and `non-alphabetical-dict-keys`: sort; where a canned response or expected output must keep GitHub's or the renderer's order, stop for the user before adding a marker (Decision 1 B chose no markers)
- [ ] `mutable-module-level-exported` (`src/tests/fixtures/fetch/recorded.py`, `responses.py` and the rest): freeze with `types.MappingProxyType`/tuples, and make the tests that change a fixture copy it first (`copy.deepcopy`); `bin/record-fixtures.py`'s `module_text` writes the frozen form, so a re-recording keeps it

**Acceptance Criteria:**

- [ ] `bin/audit-check.sh --path src/tests` exits 0
- [ ] `bin/record-fixtures.py`'s output for the recorded data passes the same check (the module it writes is frozen)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest` on every test module the task edits passes, and `pytest -m browser src/tests/reports` passes

**Notes:**

- Depends on Task 10
- Fixture modules are read by many tests: change a fixture's type only together with every test that reads it

---

## Task 12: Property tests for fetch, settings and the CLI, and tests for record-fixtures

**Status:** todo
**Priority:** low
**Complexity:** large
**Source Reference:** F17 / Decision 5 (B): T1, T2 (fetch, settings, CLI, service rows), T3

**Technical Goal:** The data boundaries and the developer script have tests that would have caught the F3 overflow.

**Subtasks:**

- [ ] Hypothesis round-trips through the cache for every record type (`repo_from_row` and the rows at `fetch/cache.py:227`, `:281`, `:301`, `:313`, `:324`, `:342`, `:349`)
- [ ] Hypothesis tests for the GraphQL and REST parsers (`fetch/base.py` `parse_repo`, `parse_languages`, `parse_pull_request`, `parse_issue`, `parse_release`, `parse_workflow_run`, `parse_star_edge`, `parse_fork`, `parse_history_node`, `parse_compare_commit`): valid shapes parse, malformed ones raise the fetch domain error
- [ ] Hypothesis tests for `timestamp`, `actor_login`, `count_of_probe`, `RateLimitState.from_headers`/`from_graphql`, `next_link`, `error_types`, `header_date`
- [ ] Hypothesis tests for `settings.convert`/`apply_layer` (arbitrary values and unknown keys raise `SettingsError`), `parse_duration` limits, `service.parse_date`, `cli.check_report` flag combinations
- [ ] `bin/record-fixtures.py`: unit tests for `Recorder.send` (with and without `params` and `body`), `Recorder.graphql`'s error branch, `pick`, `compare_commit`, and a `main` run against the fake upstream that writes to a temporary path (add an `--out` option for it, argparse rule layout)
- [ ] Every hypothesis test uses `@settings(max_examples=20, deadline=10000)`

**Acceptance Criteria:**

- [ ] The `parse_duration` test fails on the code before Task 3 (checked once by reverting the fix locally)
- [ ] A test exercises every branch T1 names in `bin/record-fixtures.py`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/fetch src/tests/test_settings.py src/tests/test_cli.py src/tests/reports/test_service.py src/tests/test_record_fixtures.py` passes

**Notes:**

- Depends on Task 11 (it edits the same test modules and fixtures)

---

## Task 13: Property tests for stats and reports

**Status:** todo
**Priority:** low
**Complexity:** medium
**Source Reference:** F17 / Decision 5 (B): T2 (stats and reports rows)

**Technical Goal:** Every pure aggregation and rendering function the audit listed has a property test.

**Subtasks:**

- [ ] `stats/delivery.py` `aggregate` DORA proxies (`deployments_by_repo`, `hotfixes`, `missing_inputs`): deployments and failures never exceed the runs or releases they come from; the failure window counts only events inside the range (the behaviour kept on 2026-10-31)
- [ ] `stats/compute.py` `resources_for`: union of the groups' resources for every subset of `GROUPS`
- [ ] `reports/rows.py` table builders: rows sum to the `Total` row where the spec says columns add up; rows are in bucket order
- [ ] `reports/figures.py` `build_figures`/`build_range_figures`: every figure validates with `plotly.graph_objects.Figure`, has at most three series and no colour
- [ ] `reports/html.py` `report_filename` (safe over arbitrary logins) and `first_difference`; `reports/web.py` `parse_query` and `reload_path`; `reports/terminal.py` `format_number`
- [ ] Every hypothesis test uses `@settings(max_examples=20, deadline=10000)`

**Acceptance Criteria:**

- [ ] Each function T2 lists for stats and reports is named in at least one hypothesis test

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/stats src/tests/reports` passes

**Notes:**

- Depends on Task 12

---

## Task 14: Bring the specs, README and AGENTS.md in line, and fix the two behaviour rows

**Status:** todo
**Priority:** medium
**Complexity:** medium
**Source Reference:** F9 (Doc4), F10 (Doc5), F11 (Doc1-Doc3), F18 (D2), F19 (spec review)

**User Story:** As a reader of the specs and README, I want them to say what the code does, so that I can trust their uncheckable parts too.

**Subtasks:**

- [ ] F9 code: `fetch/cache.py:911` `inspect_cache` opens `file:<path>?mode=ro` with `uri=True`; test that `cache info` leaves the file's modification time unchanged
- [ ] F9 specs: fix each stale Doc4 row of review-1 (`system/spec.md:48`, `:83`, `:92`; `reports/spec.md:19`, `:117`, `:208-209`, `:213`; `fetch-and-cache/spec.md:365`, `:396`, `:426`, `:448`; `stats/spec.md:122`, `:134`, `:138`, `:213`, `:217`); amend `stats/spec.md:174` to measure the failure window to the end of the range and `fetch-and-cache/spec.md:436` to treat a `FORBIDDEN` on any page as hidden (both chosen 2026-10-31)
- [ ] F10 code: the Languages table (`reports/terminal.py:312-333`) and chart (`reports/figures.py:525-527`) show the top `TOP_LANGUAGES_SHOWN - 1` languages and then one `Other` row summing the rest, whenever there are more than `TOP_LANGUAGES_SHOWN`; tests for 9, 10 and 11 languages
- [ ] F10 README: Trends only with more than one period (`README.md:41`); the Languages cap and the `Other` row (`:172`); `-h/--help` and `--completion` in the global options table (`:222-227`)
- [ ] F11: add a Layout section (`src/wambatic/{fetch,stats,reports}`, `src/tests`, `bin`, `agents/specs`, `agents/tasks`, `agents/audit-reviews`) and a Tools section (runtime: aiohttp, cappa, fastapi, loguru, plotly, rich, uvicorn; dev: hypothesis, httpx, mypy, playwright, pre-commit, pytest, ruff; uv) to `AGENTS.md`; say in AGENTS.md that `git submodule update --init` must run before the hooks work; `pyproject.toml` `readme = 'README.md'`; `README.md:325` points contributors at AGENTS.md for the layout and at `.agents` for the shared rules
- [ ] F18: no change (dev tools are declared so `uv sync` installs them)
- [ ] F19: add a Type column to `system/spec.md:100-103`; in `implementation-order.md` link step 1's task list, link the specs of steps 6, 8 and 10, and put step 9's detail before step 10's
- [ ] Bump the minor version of each spec changed, citing review-1

**Acceptance Criteria:**

- [ ] Each Doc4 and Doc5 row of review-1 is fixed (checked one by one against the code)
- [ ] `cache info` on a read-only cache file succeeds

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/fetch/test_cache.py src/tests/reports/test_terminal.py src/tests/reports/test_figures.py src/tests/reports/test_rows.py src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 13 (it describes the code as the earlier tasks leave it)
- `fetch-and-cache/spec.md` is 469 lines; F19's split is left for when it next changes, as review-1 recommends

---

## Task 15: Turn on the audit gates and close the audit

**Status:** todo
**Priority:** high
**Complexity:** medium
**Source Reference:** user request of 2026-10-31 (gates: pre-push and CI with a deploy key); review-1 steps 8b and the audit's convergence rule

**Technical Goal:** No push and no pull request can carry an unaccepted audit hit, and the audit is recorded as resolved.

**Subtasks:**

- [ ] `.pre-commit-config.yaml`: add a local hook `audit` with `entry: bin/audit-check.sh`, `language: system`, `pass_filenames: false`, `always_run: true`, `stages: [pre-push]`; set `default_install_hook_types: [pre-commit, pre-push]`; run `pre-commit install --hook-type pre-commit --hook-type pre-push`
- [ ] Stop the task as `blocked` until the operator has added a read-only deploy key: generate a key pair (`ssh-keygen -t ed25519 -N '' -f agents_deploy_key`), add the public half to `bnomis/agents` as a read-only deploy key, and store the private half in `bnomis/wambatic` as the Actions secret `AGENTS_DEPLOY_KEY`. Check: `gh secret list -R bnomis/wambatic` lists `AGENTS_DEPLOY_KEY`. Write these steps in the task's blocked note so the operator can follow them
- [ ] `.github/workflows/ci.yml`: add an `audit` job that checks out with `submodules: false` (actions/checkout pinned as the other jobs are), loads `${{ secrets.AGENTS_DEPLOY_KEY }}` into an ssh-agent (webfactory/ssh-agent pinned by commit hash, or `ssh-add` from a temporary file deleted at the end of the step), fills the submodule with `git -c url."git@github.com:".insteadOf=https://github.com/ submodule update --init .agents`, then runs `uv sync --locked` and `bin/audit-check.sh`
- [ ] Keep `.gitmodules` on `https://github.com/bnomis/agents`: Claude Code cloud sessions fill the submodule from that URL in `.claude/hooks/session-start.sh` and have no SSH key, so switching it would break them. Say in AGENTS.md that an SSH-only checkout sets `git config submodule..agents.url git@github.com:bnomis/agents.git` locally
- [ ] AGENTS.md: a Checks section naming what runs on commit (ruff with the rules of Task 1, ruff format, mypy), on push (`bin/audit-check.sh`) and in CI (all of them), and that `--no-verify` is never used
- [ ] Run the audit (`/auditme`) as review-2 on the finished branch and confirm the script reports no unaccepted hit; any Phase B finding goes to the user, not into this list
- [ ] `agents/audit-reviews/summary.md`: move review-1's resolved findings to Recently resolved (audit skill step 8b)
- [ ] Set the `**Status:**` of the stats spec (1.6) and the reports spec (1.9) back to `implemented`

**Acceptance Criteria:**

- [ ] A push with a deliberately added unaccepted hit (a `typing.Callable` in a scratch commit) is refused by the pre-push hook, then the scratch commit is dropped
- [ ] The CI `audit` job passes on the branch's pull request
- [ ] `bin/audit-check.sh` exits 0

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `pre-commit run --all-files` passes
- [ ] `pre-commit run --hook-stage pre-push --all-files` passes
- [ ] `bin/audit-check.sh` exits 0
- [ ] `pytest -m 'not slow and not live and not browser'` passes: the list changes every source package, so every test module imports a changed module (this is the importer set, not a routine full run)
- [ ] `pytest -m browser` passes

**Notes:**

- Depends on Task 14
- The deploy key is the user's step on GitHub; this task never creates or reads a secret itself
