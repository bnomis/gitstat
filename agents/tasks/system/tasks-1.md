# Tasks: System

**Spec:** `agents/specs/system/spec.md`
**Created:** 2026-10-29
**Version:** 1

This list builds step 1 of the [implementation order](../../specs/implementation-order.md), "Skeleton and settings": the project tooling, the package layout, the version identity, logging, layered settings, the public API entry point, a guard on the one-way layering and CI. The rest of the system spec is delivered by the component task lists, as mapped below.

## Spec coverage

| Spec section | Covered by |
|--------------|------------|
| Module location | Task 1, Task 7 |
| API | Task 7 (`Settings`, `load_settings`); `Subject`, `Fetcher` from the fetch-and-cache lists; `StatsRequest`, `StatsResult`, `compute` from the stats lists |
| Architecture: one-way layers | Task 7 |
| Architecture: pure core, one result many views | stats and reports lists |
| Architecture: provenance | Task 2 (version identity); recording and checking in the fetch-and-cache and stats lists |
| Architecture: secrets stay in the environment | Task 6 (no token setting); `resolve_token` and log redaction in the fetch-and-cache lists |
| Data flow | fetch-and-cache, stats and reports lists |
| Error handling | Task 3 (logging set-up), Task 5 (`SettingsError`); the typed errors in each component list; conversion at the edge in the reports lists |
| Implementation: stack | Task 1 (tooling), Task 3 (loguru); runtime libraries are added by the component lists that first use them |
| Implementation: build order | this list is step 1 |
| Implementation: testing | Task 1 (pytest, hypothesis, `slow` marker, fixtures layout); the opt-in integration test in the fetch-and-cache lists |
| Settings (config file, overrides, values, errors, version identity) | Tasks 2, 4, 5 and 6 |
| External dependencies | Task 1, Task 8 |

The spec's `**Status:**` is not changed by this list: the API section is complete only when the component lists have re-exported their names, so the last of those lists sets it to `implemented`.

---

## Task 1: Project tooling and package skeleton

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** Module location; Implementation (Stack, Testing); External dependencies

**Technical Goal:** Create the Python project so that every later task has uv, ruff, mypy, pytest, hypothesis and pre-commit to run, and the `src/gitstat/` and `src/tests/` layout the shared Python rules require.

**Subtasks:**

- [ ] Check the maintenance status of ruff, mypy, pytest, hypothesis, pre-commit and loguru per `.agents/claude/rules/tools-and-libraries.md` (PyPI latest release, GitHub archived or deprecated flags, open advisories); stop for the user if any check fails
- [ ] `uv init --lib` equivalent by hand: `pyproject.toml` with `name = 'gitstat'`, `requires-python = '>=3.14'`, src layout build backend, and `.python-version` pinned with `uv python pin 3.14`
- [ ] `uv add loguru`; `uv add --dev hypothesis mypy pre-commit pytest ruff`; commit the generated `uv.lock`
- [ ] Add `[tool.ruff]` (line length, single quotes in `[tool.ruff.format]`, isort with `known-first-party = ['gitstat']`, rule set including `I`, `UP`, `B`, `ANN`)
- [ ] Add `[tool.mypy]` with `strict = true` and `mypy_path = 'src'`
- [ ] Add `[tool.pytest.ini_options]` with `testpaths = ['src/tests']`, `pythonpath = ['src']` and the `slow` marker registered
- [ ] Add `.pre-commit-config.yaml` with ruff (check and format), mypy and the standard whitespace and end-of-file hooks
- [ ] Add `bin/activate.sh` that activates `.venv` and prepends `src/` to `PYTHONPATH`, per `.agents/claude/rules/python/environment.md`
- [ ] Create `src/gitstat/__init__.py` (empty `__all__`), `src/gitstat/fetch/__init__.py`, `src/gitstat/stats/__init__.py`, `src/gitstat/reports/__init__.py`, `src/tests/__init__.py`, `src/tests/conftest.py` and `src/tests/fixtures/__init__.py`
- [ ] Write `src/tests/test_package.py` asserting that `gitstat`, `gitstat.fetch`, `gitstat.stats` and `gitstat.reports` import
- [ ] Add `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/` and `.hypothesis/` to `.gitignore`
- [ ] Run `pre-commit install`

**Acceptance Criteria:**

- [ ] `uv sync` on a fresh clone creates `.venv` with no resolver errors
- [ ] `source bin/activate.sh && python -c 'import gitstat'` succeeds from the repository root
- [ ] `pytest --co -q src/tests/test_package.py` collects the test and it passes

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_package.py` passes

**Notes:**

- Creating `uv.lock` and `.pre-commit-config.yaml` is the explicit instruction the shared coding standards require before those files are touched.
- Runtime libraries other than loguru (aiohttp, Rich, Plotly, FastAPI, uvicorn, cappa) are added by the component task lists that first use them, each after its own maintenance check.
- Key files: `pyproject.toml`, `.python-version`, `uv.lock`, `.pre-commit-config.yaml`, `bin/activate.sh`, `src/gitstat/`, `src/tests/`

---

## Task 2: Single source of the gitstat version

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** Architecture ("Provenance travels with the data"); Settings (Version identity)

**Technical Goal:** Give the cache identity and `StatsResult.provenance` one place to read the gitstat version from, so both record the same value, as the shared versions rule requires.

**Subtasks:**

- [ ] Add `src/gitstat/version.py` with `VERSION: str` read from `importlib.metadata.version('gitstat')`; the module imports nothing from gitstat
- [ ] Write `src/tests/test_version.py`: `VERSION` equals the `[project] version` in `pyproject.toml` (read with `tomllib`; this is the packaging file, not the user config) and is a non-empty string

**Acceptance Criteria:**

- [ ] `gitstat.version.VERSION` matches `pyproject.toml`
- [ ] `src/gitstat/version.py` has no `import gitstat` statement

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_version.py` passes

**Notes:**

- Depends on Task 1
- The spec makes `settings` and `version` leaves that any layer may import (Architecture; Settings, Version identity).
- Key files: `src/gitstat/version.py`, `src/tests/test_version.py`

---

## Task 3: Logging set-up

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** Error handling ("Unexpected exceptions propagate and are logged with `loguru.logger.exception`"); Implementation (Stack)

**Technical Goal:** One function that configures loguru for every front end, so the CLI and the web app log in the same format and level.

**Subtasks:**

- [ ] Add `src/gitstat/logs.py` with `configure_logging(level: str) -> None` that removes loguru's default sink and adds one stderr sink at `level`
- [ ] Write `src/tests/test_logs.py`: after `configure_logging('WARNING')`, an `info` message does not reach the sink and a `warning` does (capture with a list sink or `capsys`)

**Acceptance Criteria:**

- [ ] Calling `configure_logging` twice leaves exactly one gitstat sink
- [ ] No module imports stdlib `logging`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_logs.py` passes

**Notes:**

- Depends on Task 1
- Token redaction in log records belongs to the fetch-and-cache lists (implementation order step 2); this task adds no filter.
- `cli.main` calls `configure_logging`; that call is added by the reports lists.
- Key files: `src/gitstat/logs.py`, `src/tests/test_logs.py`

---

## Task 4: Settings dataclasses with defaults

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** API (`Settings`); Settings; fetch-and-cache, stats and reports spec Settings tables

**Technical Goal:** Define `Settings`, `FetchSettings`, `StatsSettings` and `ReportSettings` as frozen, slotted dataclasses whose defaults are exactly the component specs' tables.

**Subtasks:**

- [ ] Add `src/gitstat/settings.py` with `FetchSettings` (`cache_path`, `full_refresh_after`, `include_archived`, `include_forks`, `max_age`, `max_retries`, `on_rate_limit`, `overlap`, `stats_retries`, `workers`), `StatsSettings` (`bot_logins`, `deploy_workflow`, `exclude_merge_commits`, `failure_window`, `hotfix_labels`, `timezone`) and `ReportSettings` (`allow_remote`, `format`, `html_theme`, `out_dir`, `web_host`, `web_port`), each `@dataclasses.dataclass(frozen=True, slots=True)`, fields in alphabetical order
- [ ] Use `tuple[str, ...]` for the two list settings so the frozen dataclass stays hashable and immutable, defaulting through `dataclasses.field(default=...)`
- [ ] Add `Settings` with `fetch`, `report` and `stats` fields defaulting via `default_factory`
- [ ] Write `src/tests/test_settings.py` with one known-good test per component asserting every default against the spec tables

**Acceptance Criteria:**

- [ ] `Settings()` builds with no arguments and every value equals the corresponding spec table default
- [ ] Assigning to any field raises `dataclasses.FrozenInstanceError`
- [ ] No field holds or names a token

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_settings.py` passes

**Notes:**

- Depends on Task 1
- The stats spec types `bot_logins` and `hotfix_labels` as `list[str]`; a tuple is the immutable equivalent in a frozen dataclass and loads from a JSON array unchanged.
- `settings.py` imports nothing from gitstat, so `fetch` may import it.
- Key files: `src/gitstat/settings.py`, `src/tests/test_settings.py`

---

## Task 5: `load_settings` layering

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`load_settings`); Settings (Config file, Overrides, Values, Errors)

**User Story:** As a gitstat user, I want defaults, my config file and my command-line flags layered with the later one winning, so that I set a preference once and override it for a single run.

**Subtasks:**

- [ ] Add `SettingsError(Exception)` to `src/gitstat/settings.py`
- [ ] Implement `load_settings(config_path, overrides)` in `src/gitstat/settings.py`: resolve the file as `config_path`, else `GITSTAT_CONFIG`, else `~/.config/gitstat/config.json`; read it with `json.load`; a missing default file means defaults, a missing file named by `config_path` or `GITSTAT_CONFIG` raises `SettingsError`; apply its `fetch`, `stats` and `report` objects; then merge `overrides`, which has the same nested shape (`{'fetch': {'workers': 8}}`), section by section
- [ ] Add `parse_duration(text: str) -> datetime.timedelta` accepting a non-negative integer and one unit from `s`, `m`, `h`, `d`, `w` (`'30d'`, `'1h'`, `'0s'`), raising `SettingsError` otherwise; it is public so the CLI flags reuse it
- [ ] Convert values to field types: durations with `parse_duration`, JSON arrays of strings to tuples, `Path` with `expanduser()` only (no `$VAR` expansion, relative paths left relative), and `Literal` values checked against their allowed set; any wrong type raises `SettingsError` naming the key, never echoing the value
- [ ] Write tests in `src/tests/test_settings.py`: a known-good JSON fixture in `src/tests/fixtures/settings.py` loads to the expected `Settings`; a missing default file yields defaults; a missing named file raises `SettingsError`; `GITSTAT_CONFIG` is honoured (via `monkeypatch.setenv`); an invalid `Literal` value, a wrong type and a malformed duration (`'30'`, `'1.5h'`, `'-1d'`, `'3y'`) each raise `SettingsError`; `'~/x'` becomes `Path.home() / 'x'` and `'$HOME/x'` stays literal
- [ ] Write a hypothesis test (`@settings(max_examples=20, deadline=10000)`) that for any generated `fetch.workers` values in file and override, the override wins, and with no override the file wins
- [ ] Write a hypothesis test (`@settings(max_examples=20, deadline=10000)`) that `parse_duration(f'{n}{unit}')` equals the expected `timedelta` for any non-negative `n` and unit

**Acceptance Criteria:**

- [ ] Defaults, then file, then overrides; later wins, for every section
- [ ] `GITSTAT_CONFIG` selects the file when `config_path` is `None`
- [ ] A value outside a `Literal` set raises `SettingsError` naming the key and the allowed values
- [ ] A missing named config file raises `SettingsError`; a missing default file does not

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_settings.py` passes

**Notes:**

- Depends on Task 4
- `SettingsError` lives in `settings.py`, not with `UsageError` in `reports`, because `fetch` imports `settings`; `cli.main` maps it to exit status 2 (reports lists).
- Key files: `src/gitstat/settings.py`, `src/tests/test_settings.py`, `src/tests/fixtures/settings.py`, `src/tests/conftest.py`

---

## Task 6: Keep the token out of settings

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** Architecture ("Secrets stay in the environment"); Settings ("The token is never a setting")

**Technical Goal:** Show that no layer of configuration can carry the GitHub token, so it can never be written to the cache, a report or the browser by way of `Settings`.

**Subtasks:**

- [ ] Make `load_settings` raise `SettingsError` for any section or key not defined on the section dataclasses, so `token` or `github_token` in the JSON file or in `overrides` is refused
- [ ] Ensure the rejection message names the key but never echoes its value
- [ ] Write tests in `src/tests/test_settings.py`: a JSON fixture with `{"fetch": {"token": "..."}}` raises; an override `{'fetch': {'token': '...'}}` raises; the raised message does not contain the value; `GITHUB_TOKEN` set in the environment changes nothing in the loaded `Settings`

**Acceptance Criteria:**

- [ ] No `Settings` field, at any depth, has a name containing `token`
- [ ] A token supplied through the file or overrides is refused, and the value is absent from the error text

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_settings.py` passes

**Notes:**

- Depends on Task 5
- `resolve_token` (reading `GITHUB_TOKEN`, else `gh auth token`) belongs to the fetch-and-cache lists.
- Key files: `src/gitstat/settings.py`, `src/tests/test_settings.py`

---

## Task 7: Public API entry point and layering guard

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** Module location; API; Architecture ("Three layers with one-way dependencies")

**Technical Goal:** Re-export the system-level names from `gitstat`, and make the one-way layering a test so a later task cannot quietly break it.

**Subtasks:**

- [ ] In `src/gitstat/__init__.py`, re-export `Settings` and `load_settings` from `.settings` and list them in `__all__`, alphabetically
- [ ] Write `src/tests/test_layering.py` that parses every module under `src/gitstat/` with `ast` and collects its `gitstat.*` imports, then asserts: `fetch` imports only `gitstat.fetch`, `gitstat.settings` and `gitstat.version`; `stats` imports nothing from `gitstat.reports`; `settings` and `version` import nothing from gitstat
- [ ] Add to `src/tests/test_package.py` a check that `gitstat.__all__` contains `Settings` and `load_settings` and that each name resolves

**Acceptance Criteria:**

- [ ] `import gitstat; gitstat.Settings; gitstat.load_settings` works
- [ ] Adding `import gitstat.reports` to a module under `src/gitstat/fetch/` makes `src/tests/test_layering.py` fail (check once by hand, then revert)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_package.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Task 2, Task 5
- `Subject`, `Fetcher`, `StatsRequest`, `StatsResult` and `compute` are re-exported by the component task lists that define them; each of those lists extends the `__all__` check in `src/tests/test_package.py`.
- Key files: `src/gitstat/__init__.py`, `src/tests/test_layering.py`, `src/tests/test_package.py`

---

## Task 8: Continuous integration

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** Implementation (Stack, Testing); implementation order step 1 ("CI is green on an empty-feature PR")

**Technical Goal:** Run the project's checks on every push and pull request so each later step's PR is gated the same way.

**Subtasks:**

- [ ] Check the maintenance status of `actions/checkout` and `astral-sh/setup-uv`; pin each to a full commit SHA with the version in a comment
- [ ] Add `.github/workflows/ci.yml` on `push` and `pull_request`: checkout with `submodules: false`, set up uv, `uv sync --locked`, then `ruff check`, `ruff format --check`, `mypy src` and `pytest -m 'not slow'`
- [ ] Set `permissions: contents: read` at workflow level
- [ ] Run every test this list added, as the last-task check: `pytest src/tests/test_package.py src/tests/test_version.py src/tests/test_logs.py src/tests/test_settings.py src/tests/test_layering.py`
- [ ] Open the step 1 PR and confirm the CI job is green on it

**Acceptance Criteria:**

- [ ] The CI job runs on the PR and passes
- [ ] The workflow fails if `uv.lock` is out of date with `pyproject.toml` (`--locked`)
- [ ] The workflow never needs `GITHUB_TOKEN` for tests: the opt-in integration test is skipped

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_package.py src/tests/test_version.py src/tests/test_logs.py src/tests/test_settings.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Task 7
- The CI test run covers the whole suite because the user's spec asks CI to run pytest; the shared "scope tests" rule governs local done-checks, not CI.
- The repository's separate Copilot code-scanning check fails for a reason unrelated to the content; it is not this workflow and does not block this task.
- Key files: `.github/workflows/ci.yml`

---
