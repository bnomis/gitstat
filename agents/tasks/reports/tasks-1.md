# Tasks: Reports

**Spec:** `agents/specs/reports/spec.md`
**Created:** 2026-10-29
**Version:** 1

This list builds step 5 of the [implementation order](../../specs/implementation-order.md), "Terminal report and CLI": the `rich` and `cappa` dependencies, the terminal renderer and JSON output, the `gitstat report` and `gitstat cache` commands with every step 5 flag, the single conversion of errors to exit statuses, the `gitstat` console script and a README user guide. It is written against version 1.2 of the reports spec, which settled what 1.1 left open for this step; the gaps and the choices made are in [review-1.md](../../specs/reports/review-1.md). It also adds `BUILT_RESOURCES`, `Fetcher.owner_kind`, `inspect_cache` and `clear_cache` from version 1.4 of the [fetch spec](../../specs/fetch-and-cache/spec.md). The step 4 list, [stats/tasks-1.md](../stats/tasks-1.md), built the `compute` and `resources_for` this list calls.

## Spec coverage

| Spec section | Covered by |
|--------------|------------|
| Module location (`errors.py`, `base.py`, `terminal.py`, `cli.py`, `__main__.py`) | Tasks 4, 5, 7 and 10 |
| Module location (`figures.py`, `html.py`, `templates/`; `web.py`) | steps 7 and 9 |
| Module location (layering: `cli` as composition root, `reports` clear of `fetch`) | Task 12 |
| API: `render_terminal`, `sparkline` | Tasks 5 and 6 |
| API: `result_to_dict`, `render_json` | Task 4 |
| API: `main`, `run`, `UsageError` | Tasks 4 and 10 |
| API: `Renderer`, `build_figures`, `render_html`; `serve` | step 7 (review-1.md choice 19); step 9 |
| Command line: command classes, `-v`/`-q`, `--format html` and `serve` deferred | Task 7 |
| Command line: Flags (target, `--by`, dates, `--groups`, `--by-author`, `--tz`, `--format`, `--max-age`, `--full-refresh`, `--no-fetch`, `--ignore-cache-version`) | Tasks 7 and 8 |
| Command line: Running `report` (order, sync decision, token only when needed, sync summary) | Task 8 |
| Command line: `cache info`, `cache clear` | Tasks 3 and 9 |
| Error handling (exit status table, messages) | Task 10 |
| Error handling (`--out` temp file; web app 400 and 502) | steps 7 and 9 |
| Implementation: Terminal (items 1, 2, 3, 7) | Task 5 |
| Implementation: Terminal (items 4, 5, 6) | Task 6 |
| Implementation: JSON output | Task 4 |
| Implementation: Static HTML, Web app, Visualisation choices | steps 7 and 9 |
| Settings (`report.format`) | Tasks 7 and 8 |
| Settings (`allow_remote`, `html_theme`, `out_dir`, `web_host`, `web_port`) | steps 7 and 9 (they already load, from step 1) |
| External dependencies (`rich`, `cappa`) | Task 1 |
| External dependencies (Plotly, FastAPI, uvicorn) | steps 7 and 9 |
| Fetch spec 1.4: `BUILT_RESOURCES`, `Fetcher.owner_kind` | Task 2 |
| Fetch spec 1.4: `CacheInfo`, `inspect_cache`, `clear_cache` | Task 3 |
| User guide (shared user-guides rule) | Task 11 |
| Implementation order step 5 "Done when" | Tasks 8 and 10; checked in Task 12 |

The spec's `**Status:**` is not changed by this list: the HTML report and the web app are built by the step 7 and step 9 lists, and the last of them sets it to `implemented`.

## Conventions for every task

- Async tests are plain `def test_...() -> None` functions whose body calls `asyncio.run(...)` on an inner coroutine; no pytest async plugin is added (as in the fetch and stats tests).
- Every cache in a test lives under pytest's `tmp_path`, and every test that runs `main` sets `fetch.cache_path` there through a config file named by `GITSTAT_CONFIG` (monkeypatched); no test touches `~/.cache` or `~/.config`. The autouse `isolated_environment` fixture in `src/tests/conftest.py` already removes `GITHUB_TOKEN` and `GITSTAT_CONFIG`.
- No test reaches the network: a test that needs GitHub uses the replay server (`tests.fixtures.fetch.server.ReplayServer`) through the existing `make_client`/`make_fetcher` fixtures, and the CLI tests swap in such a fetcher by monkeypatching `gitstat.cli.make_fetcher` (Task 8).
- Renderer tests print to `rich.console.Console(file=io.StringIO(), width=120, color_system=None, legacy_windows=False)` so output is plain text at a fixed width.
- Hand-written GitHub responses carry a comment naming the documentation page their shape comes from, as the fetch spec's Testing paragraph requires.
- `gitstat.reports` modules import nothing from gitstat outside `gitstat.reports`, `gitstat.stats`, `gitstat.settings` and `gitstat.version`; they reach `Subject` only as `result.subject`. Task 12 makes `src/tests/test_layering.py` enforce it.
- Messages never echo a token or a config value (system spec, Settings).
- The project has no affected-tests tool, so each task names its test files literally; Task 12 runs every test the list can reach.
- The local environment may lack the exact Python patch release `pyproject.toml` requires (`>=3.14.7`); if `uv sync` cannot find it, say so in the task's Notes and use what the step 4 list did, never by editing `requires-python`.

---

## Task 1: Add `rich` and `cappa`

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** External dependencies (`rich`, `cappa`); implementation order Principles (dependencies are checked, not assumed)

**Technical Goal:** Add the two runtime libraries step 5 needs, after the maintenance check the shared tools-and-libraries rule requires, so later tasks can import them.

**Subtasks:**

- [ ] Re-run the maintenance check for `rich` and `cappa` on the day: latest PyPI release and date, licence, the GitHub repository not archived; record the result with the date in this task's Notes (review-1.md has the 2026-10-29 result)
- [ ] If either fails the check, stop the list and tell the user, naming the alternative from the reports spec (Typer for cappa); do not substitute a library
- [ ] `uv add rich cappa` (this updates `pyproject.toml` and `uv.lock` as a deliberate dependency change, which the implementation order sanctions; never hand-edit `uv.lock`)
- [ ] Check that both resolve to a release older than the `exclude-newer` window and that `uv sync --locked` succeeds
- [ ] Check that mypy finds types for both (`rich` and `cappa` ship `py.typed`); if one does not, stop and tell the user rather than adding an `ignore_missing_imports` override

**Acceptance Criteria:**

- [ ] `python -c 'import rich.console, cappa'` succeeds in the project environment
- [ ] `pyproject.toml` lists `cappa` and `rich` in `dependencies`, alphabetically with the others

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `uv sync --locked` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_package.py` passes

**Notes:**

- Depends on stats/tasks-1.md Task 8 (step 4), done
- Key files: `pyproject.toml`, `uv.lock`
- Docs: [Rich](https://rich.readthedocs.io/en/stable/), [cappa](https://cappa.readthedocs.io/en/latest/)

---

## Task 2: `BUILT_RESOURCES` and `Fetcher.owner_kind`

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** fetch spec 1.4 (API: `BUILT_RESOURCES`, `Fetcher.owner_kind`; Module location); reports spec Command line (Flags: bare `NAME`); review-1.md choices 1 and 2

**Technical Goal:** Let the CLI sync only resources that are built, and turn a bare `NAME` target into a user or org subject from a positive signal (GitHub's own `type` field) without changing the cache identity.

**Subtasks:**

- [ ] In `src/gitstat/fetch/base.py`, add `BUILT_RESOURCES = frozenset({'commits'})` beside `RESOURCES`, and make `sync` raise `NotImplementedError` for `resources - BUILT_RESOURCES` (today it hard-codes `{'commits'}`); keep `UNBUILT_RESOURCE_STEPS` for the message
- [ ] Add `Fetcher.owner_kind(login)`: `self.client.rest_get(f'/users/{login}')`; `type` `'User'` gives `'user'`, `'Organization'` gives `'org'`; any other `type`, or a body that is not an object with a string `type`, raises `NotFoundError` naming the login and the type; a 404 already raises `NotFoundError` in the client. It does not use `rest_cached` and writes nothing to the cache
- [ ] Add `USER_OK` and `ORGANIZATION_OK` to `src/tests/fixtures/fetch/responses.py`, trimmed to `login` and `type`, hand-written from the shape in [Get a user](https://docs.github.com/en/rest/users/users#get-a-user) with that link in a comment and a note that they are to be re-recorded from the live API
- [ ] Tests in `src/tests/fetch/test_fetcher.py`: `owner_kind` returns `'user'` and `'org'` for the two fixtures and requests `GET /users/<login>` once; a 404 and a `type` of `'Bot'` raise `NotFoundError`; the cache file has no new rows after the call; `sync` with `{'issues'}` still raises `NotImplementedError` naming step 6
- [ ] Test in `src/tests/fetch/test_base.py`: `BUILT_RESOURCES <= RESOURCES`, and is exactly `{'commits'}`
- [ ] Export `BUILT_RESOURCES` from `gitstat.fetch` (`__init__.py` and `__all__`, keeping the existing order convention)

**Acceptance Criteria:**

- [ ] `Cache` identity is unchanged: no new query constant in `queries.py` (check `git diff --stat src/gitstat/fetch/queries.py` is empty)
- [ ] `owner_kind` makes exactly one request and no cache write

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_fetcher.py src/tests/fetch/test_base.py src/tests/test_package.py` passes

**Notes:**

- Depends on Task 1 (only so the environment is synced; no import of the new libraries)
- Key files: `src/gitstat/fetch/base.py`, `src/gitstat/fetch/__init__.py`, `src/tests/fixtures/fetch/responses.py`, `src/tests/fetch/test_fetcher.py`, `src/tests/fetch/test_base.py`
- User and organisation logins share one namespace on GitHub, so the spec drops 1.1's "ambiguous if both" (review-1.md choice 2).

---

## Task 3: `inspect_cache` and `clear_cache`

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** fetch spec 1.4 (API: `CacheInfo`, `inspect_cache`, `clear_cache`); reports spec Command line (`cache info`, `cache clear`); review-1.md choices 12 and 13

**Technical Goal:** Give the `cache` command a way to describe a cache that `Cache.open` would refuse, and to remove one completely, without the CLI knowing SQLite's file layout.

**Subtasks:**

- [ ] In `src/gitstat/fetch/cache.py`, add the frozen, slotted `CacheInfo` dataclass with the spec's fields
- [ ] Add `inspect_cache(path)`: `None` when `path` does not exist (checked before connecting, so the file is never created); otherwise its own `sqlite3.connect(path)` used only for `SELECT`s (no `SCHEMA`, no `PRAGMA journal_mode`, no `check_identity`), closed in a `finally`. `identity` excludes `version_override_at` as `Cache.identity()` does; `differences` compares it with `expected_identity()` exactly as `check_identity` does (hoist the comparison into one helper both use rather than copying it); `repos` counts rows with `missing = 0`; `commits` counts rows; `last_synced_at` is `MAX(synced_at)` parsed with `from_text`, or `None`; a table absent from `sqlite_master` counts 0 rows and gives no `last_synced_at`; `size_bytes` is the file's size plus its `-wal` file's when present
- [ ] Add `clear_cache(path)`: unlink `path`, `path` + `-wal` and `path` + `-shm` where each exists, returning the deleted paths in that order; `[]` when none exists
- [ ] Tests in `src/tests/fetch/test_cache.py`: a missing path gives `None` and creates nothing; a cache written by `Cache.open` plus the stats fixture rows (reuse the `stats_cache` fixture) reports its repo and commit counts, its identity with no differences and the latest sync time; a cache whose `meta` has a different `schema_version` (written directly with `sqlite3`) is inspected with that one difference while `Cache.open` on the same file raises `CacheVersionError`; inspecting does not change the file's `meta` rows; an empty SQLite file (no tables) inspects with zero counts; `clear_cache` removes the file and its `-wal` and `-shm` files and a second call returns `[]`
- [ ] Export `CacheInfo`, `clear_cache` and `inspect_cache` from `gitstat.fetch`

**Acceptance Criteria:**

- [ ] `inspect_cache` never creates, migrates or stamps a file
- [ ] One identity-comparison helper serves both `check_identity` and `inspect_cache`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_cache.py src/tests/test_package.py` passes

**Notes:**

- Depends on Task 2 (both edit `gitstat.fetch.__init__`)
- Key files: `src/gitstat/fetch/cache.py`, `src/gitstat/fetch/__init__.py`, `src/tests/fetch/test_cache.py`
- A plain connection to a WAL-mode file may create its `-wal` and `-shm` files; that changes no data and is acceptable. A `mode=ro` URI connection is avoided because SQLite cannot always open a WAL database read-only when its `-shm` file is absent ([SQLite WAL, read-only databases](https://www.sqlite.org/wal.html#readonly)).

---

## Task 4: `UsageError` and JSON output

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** Module location (`errors.py`, `base.py`); API (`UsageError`, `result_to_dict`, `render_json`); Implementation (JSON output); review-1.md choice 15

**User Story:** As a gitstat user, I want `--format json` to give me the whole result, versioned and in a fixed shape, so that I can pipe it into other tools and know when the shape changes.

**Subtasks:**

- [ ] Add `src/gitstat/reports/errors.py` with `UsageError(Exception)`
- [ ] Add `src/gitstat/reports/base.py` with `FORMAT_VERSION = 1`, `result_to_dict(result)` and `render_json(result, stream)` exactly as the spec's JSON output: key order, `groups` sorted, `request.since`/`until` as requested (ISO or `None`), resolved `since`/`until`, `tz` as `str(tz)`, `settings` from `dataclasses.fields(StatsSettings)` with tuples as lists and `timedelta` as `f'{int(td.total_seconds())}s'`, `points` as `[{'label', 'start', 'value'}]` in bucket order, integer values for units `count`, `days` and `lines`, floats otherwise
- [ ] Add a `org_result` pytest fixture in `src/tests/conftest.py`: `asyncio.run(gitstat.stats.compute(ORG, stats_fetcher, StatsRequest(since=SINCE, until=UNTIL, by_author=True), clock=lambda: NOW))` from `tests.fixtures.stats`, and a `repo_total_result` fixture for `repo:octo-org/alpha` with `Granularity.TOTAL`; both reuse the step 4 fixture data, so later renderer tests check numbers already hand-checked there
- [ ] Write `src/tests/reports/__init__.py` and `src/tests/reports/test_base.py`: top-level keys in the spec's order; `format_version` is 1; `json.loads` of `render_json` output equals `result_to_dict`; a series' points are in bucket order with `label` and `start` matching the buckets; count values are `int`; `settings.failure_window` is `'604800s'` and `gitstat.settings.parse_duration` reads it back to 7 days; output ends with one newline; non-ASCII logins are written as is (`ensure_ascii=False`)
- [ ] Add a hypothesis test: for any `StatsSettings` built from strategies over its field types, `result_to_dict(...)['request']['settings']` survives `json.dumps` and every duration parses back with `parse_duration`

**Acceptance Criteria:**

- [ ] `result_to_dict` performs no I/O and imports nothing from `gitstat.fetch`
- [ ] The JSON shape matches the spec exactly, shown by the key-order test

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_base.py` passes

**Notes:**

- Depends on Task 1
- Key files: `src/gitstat/reports/errors.py`, `src/gitstat/reports/base.py`, `src/tests/conftest.py`, `src/tests/reports/test_base.py`
- `src/gitstat/reports/__init__.py` exists and is empty; exports are added in Task 12.
- Hypothesis tests use `@hypothesis.settings(max_examples=20, deadline=10000)` (shared testing rule).

---

## Task 5: Terminal renderer: title, periods, trends and provenance

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`render_terminal`, `sparkline`); Implementation (Terminal, items 1, 2, 3 and 7); review-1.md choices 9 and 14

**User Story:** As a gitstat user, I want a readable table of commits, contributors, active days and lines per period with partial periods marked, a trend line per metric and where the data came from, so that I can read the activity of a repo, user or org at a glance in my terminal.

**Subtasks:**

- [ ] Add `src/gitstat/reports/terminal.py` with `sparkline(values)` as the spec's API: blocks U+2581 to U+2588, scaled linearly from min to max with the top value at U+2588, all-equal giving U+2581, empty giving `''`
- [ ] A number formatter: thousands separators, `lines_net` with an explicit sign (`+1,234`, `-56`, `0`)
- [ ] `render_terminal(result, console)` printing, in order: the title line (item 1); the Activity by period table (item 2) from the total series (`by is None`), labels from `provenance['partial_buckets']` suffixed ` *` with the caption `* partial period`, and with more than one bucket a `Total` footer row whose contributors value is the number of `top_contributors` rows whose login is not `unattributed`; the Trends block (item 3) with more than one bucket, cropping to the latest buckets that fit `console.width` and saying `last N periods`; the provenance footer (item 7) with the override warning when `version_override_at` is present
- [ ] Leave hooks (empty functions called in order) for items 4 to 6, which Task 6 fills
- [ ] Write `src/tests/reports/test_terminal.py`: `sparkline` known cases (`[0, 7]` is `'▁█'`, `[3, 3, 3]` is `'▁▁▁'`, `[]` is `''`, negative values scale), and a hypothesis test that its length equals the input's and every character is in the block range; for `org_result` the period table's rows and Total row equal the step 4 fixture's monthly totals (`tests.fixtures.stats.ORG_BY_MONTH_UTC`) and the partial marks match `provenance['partial_buckets']`; `repo_total_result` prints one row, no Total row and no Trends; at width 40 with day buckets the Trends lines say `last N periods` and fit the width; a result whose provenance has `version_override_at` prints the warning; `--ignore-cache-version` is named in that warning

**Acceptance Criteria:**

- [ ] Output carries no metric logic beyond summing additive series and counting top-contributor rows, as the spec allows
- [ ] Nothing in the output depends on colour (signs and ` *` carry the meaning)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_terminal.py` passes

**Notes:**

- Depends on Task 4 (fixtures)
- Key files: `src/gitstat/reports/terminal.py`, `src/tests/reports/test_terminal.py`
- Rich: [Table](https://rich.readthedocs.io/en/stable/tables.html) (`show_footer`, `caption`), [Console](https://rich.readthedocs.io/en/stable/console.html) (`width`).

---

## Task 6: Terminal renderer: breakdowns, top contributors and unavailable

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** Implementation (Terminal, items 4, 5 and 6); review-1.md choice 14

**User Story:** As a gitstat user looking at an org or a user, I want to see which repositories and which authors the activity came from, who contributed most and which metrics are not available yet, so that I can tell where the work happened and what the report leaves out.

**Subtasks:**

- [ ] Fill the By repository and By author tables (item 4): one table per `by_kind` present, totals per `by` summed over the series' points, ordered by commits descending then name, all-zero rows left out
- [ ] Fill Top contributors (item 5): `TOP_CONTRIBUTORS_SHOWN = 20` rows in the table's own order, then `and N more` when longer
- [ ] Fill Unavailable (item 6) when `tables['unavailable']` is not empty
- [ ] Add a known-good rendering of `org_result` at width 120 as `ORG_MONTH_TERMINAL` in `src/tests/fixtures/reports.py` (generated once from the renderer, then checked by hand against the step 4 fixture totals and the spec's layout, with the date of the check in a comment), and a test that the renderer reproduces it exactly
- [ ] Tests in `src/tests/reports/test_terminal.py`: the By repository rows for `org_result` sum to the Total row; By author appears only with `by_author`; a result with 25 top contributors (built by replacing the table with `dataclasses.replace`) shows 20 rows and `and 5 more`; Unavailable lists `flow` and the four activity metrics for the default groups and is absent when the table is empty

**Acceptance Criteria:**

- [ ] Every number in the known-good rendering was checked by hand against the step 4 fixtures
- [ ] Breakdown totals add up to the period table's Total row for commits and lines

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_terminal.py` passes

**Notes:**

- Depends on Task 5
- Key files: `src/gitstat/reports/terminal.py`, `src/tests/fixtures/reports.py`, `src/tests/reports/test_terminal.py`
- Shared testing rule: include at least one known-good input/output pair; this is it for the renderer.

---

## Task 7: Command line parsing

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** Command line (cappa command classes, Flags, `--format html` and `serve` deferred); Settings (`report.format`); review-1.md choices 6, 7, 8 and 10

**User Story:** As a gitstat user, I want a mistyped target, date or flag combination rejected at once with a one-line reason, so that I never wait for a sync to find out I asked for the wrong thing.

**Subtasks:**

- [ ] Add `src/gitstat/cli.py` with the cappa dataclasses: a root command (`-v`/`--verbose`, `-q`/`--quiet`, `command: cappa.Subcommands[Report | CacheCommand]`), `Report` with every step 5 flag of the spec (`target`, `--format terminal|json`, `--by`, `--since`, `--until`, `--groups`, `--by-author`, `--tz`, `--full-refresh`, `--no-fetch`, `--max-age`, `--ignore-cache-version`), and `CacheCommand` named `cache` with a positional `action: typing.Literal['clear', 'info']`; `--format` accepts `html` too so it can be rejected with the step 7 message below
- [ ] `parse_target(text) -> Subject | str`: `user:`, `org:`, `repo:` prefixes and bare `OWNER/NAME` give a `Subject`; bare `NAME` gives the login string for Task 8 to resolve; the spec's character and length rules; `UsageError` otherwise, naming the accepted forms
- [ ] `parse_date(text) -> datetime.date` for exactly `YYYY-MM-DD` (a regular expression before `date.fromisoformat`); `UsageError` otherwise
- [ ] `overrides(report) -> dict[str, object]` giving the nested `load_settings` overrides for `--format`, `--max-age` and `--tz` only when each is given
- [ ] `check_report(report, settings)`: `UsageError` for `--full-refresh` with `--no-fetch`, for a `report.format` of `html` (naming step 7), and for a bare `NAME` with `--no-fetch`; and the `-v`/`-q` clash on the root command
- [ ] `resolve_tz(settings) -> zoneinfo.ZoneInfo`, raising `SettingsError` naming `stats.timezone` for an unknown zone (catch `zoneinfo.ZoneInfoNotFoundError` and `ValueError`; never echo the value)
- [ ] `build_request(report, settings, tz) -> StatsRequest`: granularity from `--by` (default `month`), groups split on `,` and stripped (default `StatsRequest`'s), dates, `by_author`, `tz`, `settings.stats`
- [ ] Write `src/tests/test_cli.py` with parsing tests: every target form, including `REPO:x` (prefixes are lower case only), `user:`, `a/b/c`, a 40-character login and a repo name with `.`; dates `2026-10-29` accepted and `20261029`, `2026-W44-1` and `2026-02-30` rejected; overrides only for given flags; `--max-age 1x` gives `SettingsError` through `load_settings`; `--tz Mars/Base` gives `SettingsError` naming `stats.timezone`; `--groups activity, flow` parses to both; every `UsageError` combination above. Add hypothesis tests that every login matching the spec's rule round-trips through `parse_target` for each prefix and every string with a character outside it is rejected

**Acceptance Criteria:**

- [ ] All parsing and checks are pure functions with no cache or network access, so they run before anything else
- [ ] The CLI is defined only through cappa dataclasses (shared Python rules)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Tasks 1 and 4
- Key files: `src/gitstat/cli.py`, `src/tests/test_cli.py`
- cappa: [subcommands](https://cappa.readthedocs.io/en/latest/subcommand.html), [arguments](https://cappa.readthedocs.io/en/latest/arg.html). Check in cappa's docs for 0.33 how a `Literal` option, a boolean flag and a short alias are declared before writing the classes; do not guess the API.
- GitHub's login rule (letters, digits and single hyphens, up to 39 characters) is stricter than the spec's; the spec's looser check is enough to reject typos, and GitHub answers anything else with a 404.

---

## Task 8: Running `report`

**Status:** todo
**Priority:** high
**Complexity:** large
**Spec Reference:** Command line (Running `report`; Flags: `--full-refresh`, `--no-fetch`, `--max-age`, `--ignore-cache-version`, bare `NAME`, `--by-author` with a user); implementation order step 5 "Done when" (warm cache, no network); review-1.md choices 1 to 5 and 9

**User Story:** As a gitstat user, I want `gitstat report` to bring the cache up to date only when it needs to and then print the report, and to print it from the cache alone with `--no-fetch` or a fresh `--max-age`, even without a token, so that repeat runs are fast and work offline.

**Subtasks:**

- [ ] `make_fetcher(token, cache, settings) -> Fetcher` in `cli.py`, the one place a `Fetcher` is built, so tests monkeypatch it to return a replay-server fetcher
- [ ] `needs_sync(provenance, resources, settings, full_refresh, no_fetch, now) -> bool` as the spec's step 3: `False` for `no_fetch` or empty resources; `True` for `full_refresh`; `False` when `max_age > 0` and every `fetched_at:<resource>` is an ISO time less than `max_age` before `now`; `True` otherwise (`never` is never fresh)
- [ ] `async run_report(report, settings, console, stdout, *, clock) -> None` following the spec's order: open the cache with `Cache.open(settings.fetch.cache_path, ignore_version=report.ignore_cache_version)` and close it in a `finally`; resolve a bare `NAME` with `owner_kind` (entering the fetcher), then raise `UsageError` for `--by-author` with a user subject; compute `resources = resources_for(groups) & BUILT_RESOURCES`; call `resolve_token()` and enter the fetcher only when a sync or a resolution is needed, otherwise build it with `''` and never enter it; sync with `full_refresh`, logging the `SyncReport` summary at `info`; `compute`; then `render_terminal(result, console)` or `render_json(result, stdout)` by `settings.report.format`
- [ ] When `compute` raises `EmptySubjectError` and no sync ran because of `--no-fetch`, re-raise it with the hint that the cache may only need a sync (spec, Error handling)
- [ ] Tests in `src/tests/test_cli.py` (driving `run_report` directly; `main` comes in Task 10): with the `stats_cache` file as `fetch.cache_path`, `repo:octo-org/alpha --by month --no-fetch` prints the report with no `GITHUB_TOKEN` set and with `make_fetcher` returning a fetcher whose client raises on `__aenter__` (proving no session); the same with `--max-age 30d` and a clock 1 day after the fixture's sync times, and with a clock 31 days after it syncing through the replay server; `--full-refresh` syncs even when fresh and passes `full_refresh=True`; the default groups sync only `commits` (the replay server records no request for issues or pull requests) and the output lists `flow` as unavailable; a bare `octocat` resolves through `GET /users/octocat` to a user, and with `--by-author` then raises `UsageError`; `--format json` writes parseable JSON to the given stream and nothing else to it; `--ignore-cache-version` on a cache with a different `schema_version` prints the report with the override warning, and without it raises `CacheVersionError`; `--groups flow` syncs nothing and raises `EmptySubjectError`
- [ ] Tests of `needs_sync` covering each branch, including a resource whose provenance is `never`

**Acceptance Criteria:**

- [ ] A report from a warm cache with `--no-fetch`, or a `--max-age` the cache is younger than, opens no aiohttp session and needs no token: shown by the raising-client test
- [ ] Only resources in `BUILT_RESOURCES` are ever passed to `Fetcher.sync`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Tasks 2, 6 and 7
- Key files: `src/gitstat/cli.py`, `src/tests/test_cli.py`
- The sync-then-compute sequence lives in `cli.py` for now; step 9's web app needs the same sequence and will hoist it to one owner then (the shared taskdev rule on components modelled on a sibling).
- `stats_cache`'s sync times are `tests.fixtures.stats.ALPHA_SYNCED_AT` and its siblings; the replay sync needs the repository listing for `octo-org/alpha`, written in `tests.fixtures.fetch.responses`' style with the same repo fields so it is reported unchanged.

---

## Task 9: The `cache` command

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** Command line (`cache info`, `cache clear`); review-1.md choices 12 and 13

**User Story:** As a gitstat user, I want `gitstat cache info` to tell me what my cache holds and why it is refused, and `gitstat cache clear` to remove it, so that I can recover from a version mismatch without finding the file by hand.

**Subtasks:**

- [ ] `run_cache(command, settings, console) -> None` in `cli.py`: `info` prints the `inspect_cache(settings.fetch.cache_path)` fields as a two-column Rich table (path, size, each identity key, each difference as `recorded -> running`, the override time, repos, commits, last synced), or `no cache at <path>` when it returns `None`; `clear` calls `clear_cache` and logs each removed path at `info`, or logs `no cache at <path>` when nothing was removed
- [ ] Tests in `src/tests/test_cli.py`: `info` on the `stats_cache` file lists its counts and no differences; `info` on a cache with a different `schema_version` shows that difference and leaves the file's `meta` unchanged; `info` on a missing path prints `no cache at` and creates nothing; `clear` removes the file and its `-wal` and `-shm` files and a second `clear` reports nothing to remove

**Acceptance Criteria:**

- [ ] `cache info` works on a cache that `report` refuses
- [ ] Neither action touches the network or needs a token

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Tasks 3 and 7
- Key files: `src/gitstat/cli.py`, `src/tests/test_cli.py`

---

## Task 10: `main`, exit statuses and the console script

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`main`, `run`); Error handling (exit status table, messages); Command line (`-v`/`-q`, log format); Module location (`__main__.py`); implementation order step 5 "Done when" (every typed error maps to its documented exit status); review-1.md choices 10, 11 and 17

**User Story:** As a gitstat user, I want every failure to end with one line that says what to do and a predictable exit status, and `gitstat` to be on my path after `uv sync`, so that I can use it by hand and in scripts.

**Subtasks:**

- [ ] Extend `gitstat.logs.configure_logging(level)` so that below `DEBUG` the sink's format is `'{level}: {message}'`, and at `DEBUG` loguru's default format; keep the one-sink behaviour its tests check, and add a test for each format to `src/tests/test_logs.py`
- [ ] `main(argv=None) -> int` in `cli.py`: parse with cappa (`argv` default `sys.argv[1:]`); configure logging from `-v`/`-q`; load settings with the overrides; dispatch to `run_report` (under one `asyncio.run`) or `run_cache`; convert exactly as the spec's table, one `except` per row, `UsageError` and `SettingsError` before the broad clauses; `KeyboardInterrupt` returns 130 with no message; never call `sys.exit`
- [ ] Convert cappa's exits into return values: check in cappa's docs and with a test how it signals `--help` and a parse failure (`SystemExit` or `cappa.Exit`), and return its code (0 for help, 2 for a parse failure) instead of letting it exit
- [ ] `run() -> None`: `sys.exit(main())`; `src/gitstat/__main__.py` calling `gitstat.cli.run()`; `[project.scripts] gitstat = 'gitstat.cli:run'` in `pyproject.toml`, then `uv sync` so `.venv/bin/gitstat` exists
- [ ] Tests in `src/tests/test_cli.py`, through `main([...])`: a parametrised test with one case per row of the spec's table and per named error class (`AuthError`, `CacheVersionError`, `GraphQLError`, `NotFoundError`, `RateLimitError`, `StatsPendingError`, `EmptySubjectError`, `InvalidRangeError`, `InvalidRequestError`, `UnknownGroupError`, `UsageError`, `SettingsError`, a `RuntimeError`, `KeyboardInterrupt`), raised from a monkeypatched `run_report`, asserting the status, that stderr has exactly one `ERROR:` line for the typed errors and a traceback only for `RuntimeError`, and nothing for `KeyboardInterrupt`; `--help` returns 0; `--by fortnight` returns 2; a missing `GITSTAT_CONFIG` file returns 2; the warm-cache report through `main([... '--no-fetch'])` returns 0 and prints the period table; `-v -q` returns 2
- [ ] Test that `python -m gitstat --help` and `.venv/bin/gitstat --help` exit 0 (`subprocess.run` with the project's interpreter, no network)

**Acceptance Criteria:**

- [ ] Every typed error maps to its documented exit status: shown by the parametrised test
- [ ] No error message contains the value of `GITHUB_TOKEN` (a test sets a recognisable token and raises `AuthError` and a `RuntimeError` whose text includes it, and checks stderr; the fetch client's redaction already covers its own logs, so if `main`'s traceback can carry it, redact there with `gitstat.fetch.auth.redact` and test it)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `uv sync --locked` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_cli.py src/tests/test_logs.py` passes

**Notes:**

- Depends on Tasks 8 and 9
- Key files: `src/gitstat/cli.py`, `src/gitstat/__main__.py`, `src/gitstat/logs.py`, `pyproject.toml`, `src/tests/test_cli.py`, `src/tests/test_logs.py`
- Python's [`sys.exit`](https://docs.python.org/3.14/library/sys.html#sys.exit) and the shell convention of 128 + signal number give 130 for SIGINT.

---

## Task 11: README user guide

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** shared user-guides rule (keep guides in sync with code); Command line; Error handling; system spec Settings; review-1.md choice 18

**User Story:** As someone trying gitstat for the first time, I want a README that gets me from install to a first report and explains the flags, config file and exit statuses, so that I do not have to read the specs.

**Subtasks:**

- [ ] Write `README.md`: what gitstat does; install (`uv sync`, Python 3.14) with a check (`gitstat --help`); the token (`GITHUB_TOKEN` or `gh auth login`, the scopes from the fetch spec's External dependencies, and that it is never written anywhere); a first report (`gitstat report repo:octocat/Hello-World --by month`) and common workflows (`--no-fetch`, `--max-age 1d`, `--format json | jq`, `--by-author` on an org, `--tz`); targets; every `report` flag; `cache info` and `cache clear` and when to use them (a `CacheVersionError`); the config file with every setting, its default and trade-off, taken from the specs' settings tables; exit statuses; accepted limits from the system spec; and that HTML (step 7) and `serve` (step 9) are not built yet
- [ ] Run every example command in the README that needs no network against the `stats_cache`-style cache or with `--help`, and check its output matches what the README says
- [ ] Keep counts out of the prose (shared counts-in-prose rule) and use British spelling

**Acceptance Criteria:**

- [ ] Every flag in `gitstat report --help` and every setting in `gitstat.settings` appears in the README (check with a short script listing both, or by hand, recorded in Notes)
- [ ] Links to the specs are relative

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 10
- Key files: `README.md`
- `pyproject.toml`'s `readme` stays `AGENTS.md` (review-1.md choice 18).

---

## Task 12: Exports, layering and closing checks

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** Module location (layering); API; system spec Architecture (`gitstat.cli` as composition root); implementation order step 5 "Done when"; review-1.md choice 16

**Technical Goal:** Expose the step 5 names, enforce the reports layer's imports, run every test this list can reach, and mark the step done.

**Subtasks:**

- [ ] In `src/gitstat/reports/__init__.py`, import and list in `__all__`: `UsageError`, `render_json`, `render_terminal`, `result_to_dict`, `sparkline`
- [ ] Extend `src/tests/test_package.py`: every name in `gitstat.reports.__all__` and the new `gitstat.fetch` names (`BUILT_RESOURCES`, `CacheInfo`, `clear_cache`, `inspect_cache`) resolve, and `gitstat.cli.main` is callable
- [ ] Extend `violations` in `src/tests/test_layering.py`: a `gitstat.reports` module importing anything outside `gitstat.reports`, `gitstat.stats`, `gitstat.settings` and `gitstat.version` is a violation (this includes `gitstat.fetch` and `gitstat.cli`), and no module other than `gitstat.cli` and `gitstat.__main__` may import `gitstat.cli`; add a test like `test_detects_stats_importing_reports_or_the_logs_module` for each rule
- [ ] Check the implementation order's "Done when" for step 5: the warm-cache report with no network and no token (Tasks 8 and 10) and the exit status table (Task 10); record where each is shown in this task's Notes
- [ ] Run every test that imports a changed module directly or transitively: `pytest src/tests/fetch src/tests/stats src/tests/reports src/tests/test_cli.py src/tests/test_logs.py src/tests/test_package.py src/tests/test_layering.py`
- [ ] Hoist anything the new modules duplicate to a single owner: grep the tree for each literal collection, constant and one-line helper `cli.py`, `reports/` and the new fetch functions define (number formatting, duration formatting, ISO date handling, the identity comparison), and import rather than copy, choosing the owner from the existing import graph
- [ ] In `agents/specs/implementation-order.md`, set step 5's Status to `done: [tasks-1](../tasks/reports/tasks-1.md)`

**Acceptance Criteria:**

- [ ] `python -c 'import gitstat.reports, gitstat.cli'` works and `gitstat --help` lists `report` and `cache`
- [ ] Every step 5 "Done when" item is met, or its gap is recorded in the task that owns it

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch src/tests/stats src/tests/reports src/tests/test_cli.py src/tests/test_logs.py src/tests/test_package.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Tasks 1 to 11
- The project has no affected-tests tool; the command above names every test file that reaches a module this list changed (`gitstat.fetch` is reached by the fetch and stats tests, `gitstat.reports` and `gitstat.cli` by the reports and CLI tests, `gitstat.logs` by its own tests, and the package and layering tests check the whole tree).
- The reports spec's `**Status:**` stays `proposed` (see the header).
- Key files: `src/gitstat/reports/__init__.py`, `src/tests/test_package.py`, `src/tests/test_layering.py`, `agents/specs/implementation-order.md`

---
