# Audit Summary

**Last updated:** 2026-10-31
**Last review:** review-1
**Total reviews conducted:** 1
**Last script run hit count:** 570 (0 accepted)
**Script version:** `4d7de71faa4067b7b05e53afe41973ffdfdc298f80d249b86f5085cfd7bac365` (from `find -L ~/.claude/skills/auditme/checks -name '*.py' | sort | xargs cat | shasum -a 256`)

## Unresolved findings

### Mechanical hits (checks/audit.py)

- **Rule or category:** every script rule family listed in [review-1](review-1.md#mechanical-findings-from-checksauditpy)
- **Severity:** low to medium (per rule in review-1)
- **Location:** 570 sites in review-1; 445 of them under `src/tests/`
- **First raised:** review-1 (2026-10-31)
- **Description:** no hit is fixed or accepted yet.
- **Recommendation:** per rule in review-1; the test-tree hits are to be fixed in code (Decision 1, option B, answered 2026-10-31).

### F1: Web server logs unexpected errors without redacting the token

- **Rule or category:** Sec / S / Sec5, S4 (security.md)
- **Severity:** high
- **Location:** `src/wambatic/reports/web.py:76`
- **First raised:** review-1 (2026-10-31)
- **Description:** `error_response` logs `f'Unexpected error: {error}'` and the traceback with `logger.exception`. The CLI path calls `redact_exception(e)` and `redact_environment_token(...)` first (`cli.py:403-405`); the web path does neither. An unexpected exception whose message carries the token (an aiohttp error quoting a request header, say) would write it to the server log. `diagnose=False` (`logs.py`) keeps locals out of tracebacks, but not exception messages.
- **Recommendation:** Redact in `error_response` the same way as `cli.main`, preferably through one shared helper, and add a regression test that raises an exception containing the token through the web app and checks the log.

### F2: Third-party errors escape as tracebacks instead of domain errors

- **Rule or category:** A / A1, A2
- **Severity:** medium
- **Location:** `src/wambatic/fetch/client.py:211`, `:290`, `:327`, `:333`; `src/wambatic/fetch/cache.py:372-962` (each `execute`/`connect`/`unlink`); `src/wambatic/settings.py:146-147`; `src/wambatic/fetch/auth.py:12-13`; `src/wambatic/reports/service.py:82-83`; `src/wambatic/reports/html.py:125`, `:597`; `src/wambatic/cli.py:231`; `src/wambatic/version.py:3`; `bin/record-fixtures.py:108-109`, `:235-236`
- **First raised:** review-1 (2026-10-31)
- **Description:** When the retries run out on a network error, `GitHubClient` re-raises the aiohttp `ClientConnectionError`/`TimeoutError`, or raises `aiohttp.ClientResponseError` for an unclassified status. Every `sqlite3.Error` from the cache (a locked or corrupt file, a full disc) escapes untranslated. The config read, `gh auth token`, the cache unlink and the tz lookup each catch only `FileNotFoundError` (or a near equivalent), not `OSError`/`UnicodeDecodeError`. Each of these reaches `cli.main`'s `except Exception`, which prints "Unexpected error" with a traceback and exits 1 instead of a one-line message. This is the case the user is most likely to meet: the network going down mid-sync.
- **Recommendation:** Translate at each layer's boundary: in `GitHubClient.send`/`request`, wrap aiohttp errors in `FetchError` after the retries; in `Cache`, wrap `sqlite3.Error` and `OSError` in a new `CacheError(FetchError)` through one context manager used by every method; widen the four narrow `except` tuples to `OSError` (+ `UnicodeDecodeError` where text is decoded). `bin/record-fixtures.py` is a developer script and can stay as it is (scoped accept markers).

### F3: Settings validation lets an `OverflowError` through

- **Rule or category:** Sec / Sec2
- **Severity:** medium
- **Location:** `src/wambatic/settings.py:74`
- **First raised:** review-1 (2026-10-31)
- **Description:** `parse_duration('99999999999d')` raises `OverflowError` (checked on 2026-10-31), not `SettingsError`, so `--max-age`/`fetch.max_age` with a huge value exits 1 with a traceback instead of exit 2 with a usage message.
- **Recommendation:** Catch `OverflowError` in `parse_duration` and raise `SettingsError`; add a hypothesis case with very large counts.

### F4: The web report accepts an unbounded date range

- **Rule or category:** Sec / Sec2
- **Severity:** medium
- **Location:** `src/wambatic/reports/web.py:259-267`, `src/wambatic/reports/service.py:111-112`, `src/wambatic/stats/buckets.py:80-82`
- **First raised:** review-1 (2026-10-31)
- **Description:** `since`/`until` from the query string accept any date from 0001 to 9999. `/report` always computes the DAY period, so one GET builds about 3.6 million buckets per metric. The server binds to loopback by default, which limits who can send that GET, but a stray link can still pin a CPU.
- **Recommendation:** Bound the range at the boundary (for example no earlier than GitHub's founding in 2008 and no later than tomorrow) with a `UsageError` (HTTP 400), in `make_request` so the CLI shares it.

### F5: Stdlib exceptions raised in packages that define domain errors

- **Rule or category:** A / A3 (and the script's `layer-has-domain-error-raises-stdlib`, `mixed-raise-types`)
- **Severity:** medium
- **Location:** the 23 A3 sites listed above
- **First raised:** review-1 (2026-10-31)
- **Description:** Some of these are reachable from user input and are wrong: `buckets.py:75` (`since` after `until`; `InvalidRangeError` exists for it), `html.py:108-120` (`check_report`), `settings.py:110`, `cache.py:541`, `client.py:222`. Others are caller-mistake guards that the specs themselves specify as `ValueError` (`stats/spec.md:65`, `reports/spec.md:54` and `:63`, `fetch-and-cache/spec.md:178`). See Decision 2.
- **Recommendation:** Convert every site to a domain error and amend the four spec passages (Decision 2, option B, answered 2026-10-31).

### F6: Two sources of truth for the same setting

- **Rule or category:** A / A5
- **Severity:** medium
- **Location:** `src/wambatic/fetch/base.py:529-540`; `src/wambatic/stats/base.py:46-49`; `src/wambatic/reports/service.py:88-117`, `:170`, `:210-221`; `src/wambatic/reports/web.py:298-303`
- **First raised:** review-1 (2026-10-31)
- **Description:** `Fetcher.settings` versus an injected client's `settings`; `StatsRequest.tz` versus `settings.timezone` (both written into the JSON output, so they can disagree there); `by_author` passed beside the request that already holds it; `make_app(check_host=...)` versus `settings.report.allow_remote`. In each case which value wins depends on the call site, and nothing checks that the two agree.
- **Recommendation:** Give each value one owner: derive `tz` from settings (or drop `settings.timezone` from the request), read `by_author` from the request, derive `check_host` inside `make_app`, and make `Fetcher` take its settings from the client when one is injected (or refuse a mismatch).

### F7: `match`/`if` chains over enums and literals end in `raise`, not `assert_never`

- **Rule or category:** A / A11 (and the script's `assert-never-missing`)
- **Severity:** medium
- **Location:** `src/wambatic/stats/buckets.py:22`, `:39`; `src/wambatic/fetch/base.py:1272`, `:1276`, `:1278`
- **First raised:** review-1 (2026-10-31)
- **Description:** A wildcard `case _: raise ValueError` or a fall-through `else` means mypy cannot tell when a new `Granularity` member or resource name is left unhandled.
- **Recommendation:** Handle `TOTAL` explicitly and end with `typing.assert_never(...)`.

### F8: Repeated computation across the five periods of an HTML report

- **Rule or category:** A / P / A14, P3
- **Severity:** medium
- **Location:** `src/wambatic/stats/compute.py:137`, `:155`, `:167`, `:251`; `src/wambatic/reports/service.py:240`; `src/wambatic/reports/html.py:371`, `:491-494`, `:561`, `:577`; `src/wambatic/reports/rows.py:237`; `src/wambatic/reports/figures.py:404`; `src/wambatic/reports/terminal.py:337`; `src/wambatic/fetch/base.py:652`
- **First raised:** review-1 (2026-10-31)
- **Description:** Each of the five `compute()` calls re-reads every cached record from SQLite, plus repos, provenance and sync state. Then `html.py` builds the initial period's figures, the calendar and the range figures twice each. No measurement shows whether this matters at real sizes. See Decision 3.
- **Recommendation:** Restructure: read the cache once per report and build each figure once; amend `reports/spec.md:81-85` (Decision 3, option B, answered 2026-10-31).

### F9: Spec and code disagree

- **Rule or category:** Doc / Doc4
- **Severity:** medium
- **Location:** the 17 Doc4 rows above
- **First raised:** review-1 (2026-10-31)
- **Description:** Most are stale spec text: the layering rule in `system/spec.md:48`, which `reports/spec.md:28` later relaxed; the missing `OutputError`/`ServeError`; `SyncJob.state` versus `phase`; the `probe` column; `list` versus `tuple` types; the 1.11 note about a hand-derived fixture, now re-recorded. Three describe behaviour, and in each the code or the spec has to change: the delivery failure window is measured from the end of `until`, not from "now" (`stats/spec.md:174`); `cache info` opens the database read-write, not read-only (`reports/spec.md:195`); and stargazers count as hidden when *any* page is refused, not only the first (`fetch-and-cache/spec.md:436`).
- **Recommendation:** Update the spec text for the stale rows. For the three behavioural rows, decide which side is right; the read-only `cache info` is a cheap code fix (`sqlite3.connect(f'file:{path}?mode=ro', uri=True)`).

### F10: README drift

- **Rule or category:** Doc / Doc5
- **Severity:** medium
- **Location:** `README.md:41`, `:172`, `:222-227`
- **First raised:** review-1 (2026-10-31)
- **Description:** Trends is listed as always printed, but it is skipped for `--by total`. The Languages table is capped at `TOP_LANGUAGES_SHOWN` rows, which can cut the `Other` row, and the README does not say so. The global options table leaves out `--help` and `--completion`.
- **Recommendation:** Update the three passages. For Languages, either document the cap or always keep `Other` as the last row.

### F11: AGENTS.md has no structure or tools section, and its links do not resolve here

- **Rule or category:** Doc / Doc1, Doc2, Doc3
- **Severity:** medium
- **Location:** `AGENTS.md:1-19`, `README.md:325`, `pyproject.toml:5`
- **First raised:** review-1 (2026-10-31)
- **Description:** AGENTS.md is a pointer to the shared rules and nothing else: it has no project layout and no tools list. In this checkout its submodule links are dangling, because `.agents` is not initialised. `README.md:325` sends contributors to AGENTS.md for rules it does not hold. `pyproject.toml` declares `readme = 'AGENTS.md'`, so the package's long description is the agent instructions, not the user guide.
- **Recommendation:** Run `git submodule update --init`. Add a short layout section (`src/wambatic/{fetch,stats,reports}`, `src/tests`, `bin`, `agents/specs`, `agents/tasks`) and a tools list to AGENTS.md. Point `readme` at `README.md`.

### F12: Blocking calls on the event loop

- **Rule or category:** P / P2
- **Severity:** medium
- **Location:** `src/wambatic/reports/service.py:183`, `:198` (`resolve_token`, up to 10 s); `src/wambatic/reports/web.py:310`, `:312`, `:466` (template reads)
- **First raised:** review-1 (2026-10-31)
- **Description:** In the web server, each sync job runs `gh auth token` with `subprocess.run` on the server's event loop, which stalls every other request for as long as `gh` takes. The template reads are small but repeated on every response.
- **Recommendation:** Run `resolve_token` through `asyncio.to_thread`. Read the templates once (`functools.cache` on `read_template`).

### F13: Mutable module-level containers read from other modules

- **Rule or category:** A / A20 (and the script's `mutable-module-level-exported`)
- **Severity:** low
- **Location:** `src/wambatic/stats/delivery.py:36` (`UNITS`), `src/wambatic/reports/figures.py:40` (`PALETTE`), the four `__all__` lists
- **First raised:** review-1 (2026-10-31)
- **Description:** A caller can mutate `UNITS` or `PALETTE` and change every later report in the process, which matters in the long-running server.
- **Recommendation:** Wrap in `types.MappingProxyType`. Make the `__all__` lists tuples (ruff accepts either).

### F14: Duplicated record construction between the parsers and the cache

- **Rule or category:** A / A15, A13
- **Severity:** low
- **Location:** the A15 rows (mainly `fetch/base.py` parsers against `fetch/cache.py` row readers and column tuples)
- **First raised:** review-1 (2026-10-31)
- **Description:** Every record type is assembled once from GraphQL in `base.py` and again from a SQLite row in `cache.py`, and the column lists are written out again in the INSERT statements and write lambdas. Adding a field means editing four places, and missing one fails only at run time.
- **Recommendation:** Derive the column tuples and the row writers from `dataclasses.fields(...)`, so each record's field list exists once.

### F15: Smaller architecture findings

- **Rule or category:** A / A8, A9, A17, A19, A22, A23
- **Severity:** low
- **Location:** the rows above
- **First raised:** review-1 (2026-10-31)
- **Description:** Accumulator and job-state dataclasses are mutated after construction (A8: `Tally`, `SyncJob`, both deliberate). Some `resolve_`/`check_`/`parse_`/`build_` functions do I/O (A9). The subpackage `__all__` surfaces have no consumers outside their package (A17; Decision 4, option B, answered 2026-10-31: trim each subpackage `__all__` to the names `system/spec.md:23` promises). The `except BaseException` clean-up-and-re-raise handlers do not log (A19); that is the right shape, so accept them with a scoped marker. A 404 from `compare` is logged as "history rewritten" (A22). `sync_releases` discards `plan_full_read`'s result (A23); that is harmless, because every releases read is a full one, but the call is made only for its log line.
- **Recommendation:** A8: no change; record the reason in a comment. A9: rename `build_results` to `sync_and_compute` (or similar) and `check_bind` to `warn_on_bind`; the others do I/O inside a library and can stay. A19: scoped accept markers. A22: log the 404 as the reason. A23: `_ = self.plan_full_read(...)`, or a `log_full_read` that returns nothing.

### F16: Standards findings

- **Rule or category:** S / S2, S4
- **Severity:** low
- **Location:** the S2 and S4 rows above
- **First raised:** review-1 (2026-10-31)
- **Description:** The type aliases `GRANULARITIES` and `FORMATS` are UPPER_SNAKE where every other alias is PascalCase. Four test strategies are lower_snake. Expected domain errors are logged with `logger.error` (`cli.py:385`, `:393`); the coding standard says to always use `logger.exception`, but a traceback for a usage error would be the wrong output for the user. Some test fixtures live in test modules, not in `conftest.py`, and some test and fixture file names do not mirror a source module.
- **Recommendation:** Rename the aliases and strategies. Keep `logger.error` for expected domain errors, and propose a change to the shared coding standard ("exception for unexpected errors only"); this is the rule conflict A19 already describes. Move `restore_logger` (defined twice) and the cache fixtures into `conftest.py`. Leave the `fixtures/fetch/*` names as they are: they mirror the fake GitHub, not a source module.

### F17: Test coverage gaps

- **Rule or category:** T / T1, T2, T3
- **Severity:** low
- **Location:** the T rows above
- **First raised:** review-1 (2026-10-31)
- **Description:** `bin/record-fixtures.py` has no tests at all (T1, T3). Many pure parsers, row round-trips and table builders have example tests but no property tests (T2).
- **Recommendation:** Add `bin/record-fixtures.py` tests and hypothesis tests for every T2 area (Decision 5, option B, answered 2026-10-31).

### F18: Dev tools declared but never imported

- **Rule or category:** D / D2
- **Severity:** low
- **Location:** `pyproject.toml:24`, `:26`, `:28`
- **First raised:** review-1 (2026-10-31)
- **Description:** `mypy`, `pre-commit` and `ruff` are command-line tools, so no code imports them. They are declared so that `uv sync` installs them for CI and pre-commit.
- **Recommendation:** No change. This is expected for tools in a dev group.

### F19: Spec template gaps

- **Rule or category:** Doc / spec review
- **Severity:** low
- **Location:** `agents/specs/fetch-and-cache/spec.md` (469 lines), `reports/spec.md` (315), `stats/spec.md` (225), `system/spec.md:100-103`, `implementation-order.md:7`, `:20`, `:25-29`, `:65-73`
- **First raised:** review-1 (2026-10-31)
- **Description:** Three specs are over the specdev size guide of about 200 lines. The environment-variable table has no Type column. `implementation-order.md` has inconsistent links and puts step 10 before step 9. Two links into `.agents` do not resolve in this checkout (F11).
- **Recommendation:** Split `fetch-and-cache/spec.md` (fetch and cache are natural halves) when it next changes. Fix the table and the ordering now.

## Recently resolved

| Finding | Severity | Raised in | Resolved in |
|---------|----------|-----------|-------------|
| (none yet) | | | |

## Recurring patterns

- (none yet: one review so far)

## Checker changes since the last review

- (none: first review)
