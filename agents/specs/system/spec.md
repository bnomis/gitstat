# System

**Version:** 1.6
**Status:** proposed
**Date:** 2026-10-30

wambatic reports statistics from github.com for a user, a repository or an organisation, as a terminal report, a static HTML report or a local web app, with the numbers bucketed by year, month, week or day. This spec is the top of the set: it fixes the architecture, the boundaries between components, the data flow, the stack and the build order. The detail of each component is in its own spec; where this spec and a component spec differ, the component spec wins and this one is amended.

## Module location

`src/wambatic/` is the package. `src/wambatic/__init__.py` re-exports the public API listed below; `src/tests/` mirrors the source layout; `bin/` holds entry-point scripts.

| Component | Package | Spec |
|-----------|---------|------|
| Fetch and cache | `src/wambatic/fetch/` | [fetch-and-cache](../fetch-and-cache/spec.md) |
| Stats | `src/wambatic/stats/` | [stats](../stats/spec.md) |
| Reports and CLI | `src/wambatic/reports/`, `src/wambatic/cli.py` | [reports](../reports/spec.md) |
| Settings | `src/wambatic/settings.py` | this spec |
| Version identity | `src/wambatic/version.py` | this spec |

## API

The public surface other code and the three front ends may rely on, re-exported from `wambatic`:

- `Subject`: a user, repo or org target
- `Fetcher`: GitHub access plus cache
- `StatsRequest`: granularity, groups, range, timezone
- `StatsResult`: series, tables, provenance
- `compute`: `async (Subject, Fetcher, StatsRequest) -> StatsResult`
- `Settings`: layered configuration

```python
import dataclasses
import pathlib

@dataclasses.dataclass(frozen=True, slots=True)
class Settings:
    fetch: FetchSettings
    report: ReportSettings
    stats: StatsSettings

def load_settings(config_path: pathlib.Path | None, overrides: dict[str, object]) -> Settings:
    """Defaults, then the JSON file, then command-line overrides; later wins."""
```

## Architecture

Three layers with one-way dependencies: `reports` imports `stats`, `stats` imports `fetch`, and `fetch` imports nothing from wambatic except `settings` and `version`. `settings` and `version` are leaves: they import nothing from wambatic, and any layer may import them. No layer reaches around the one beneath it. `wambatic.cli` sits above the three as the composition root: it builds the `Cache` and `Fetcher`, syncs, calls `compute` and a renderer, so it alone imports every layer (and `wambatic.logs`).

```text
GitHub GraphQL / REST
        |  aiohttp
   [ fetch ]  -- reads/writes -->  SQLite cache (local file)
        |  typed records (Commit, PullRequest, Issue, Release, WorkflowRun, StarEvent)
   [ stats ]  -- pure computation, no I/O
        |  StatsResult (series, tables, provenance)
   [ reports ]  -->  terminal | static HTML file | local web app | JSON
```

Rules that hold across the system:

- **One result, many views.** All renderers take a `StatsResult`; no metric logic lives in a renderer.
- **Pure core.** The aggregation functions in `stats` perform no I/O, so every metric is testable from fixture records; only `compute` awaits the fetcher, then hands the records to them.
- **Cache is the only state.** Everything else is derived and reproducible from the cache plus the request.
- **Provenance travels with the data.** Every `StatsResult` carries wambatic version, cache schema version, query hashes and fetch times. The cache refuses a mismatch rather than mixing versions, per the shared versions rule.
- **Secrets stay in the environment.** The token is read from `GITHUB_TOKEN` (or `gh auth token`) and never reaches the cache, logs, reports or the browser.

## Data flow

1. The CLI or web handler parses `<target>` into a `Subject` and the flags into a `StatsRequest`.
2. Unless `--no-fetch` applies, the front end calls `Fetcher.sync` for the resources the requested groups need (`stats.resources_for`: commits for activity, pull requests and issues for flow, releases, workflow runs and pull requests for delivery; star events, with the other popularity data, from step 10).
3. `Fetcher` backfills everything on a subject's first sync and afterwards fetches only the delta since each per-repo, per-resource watermark, and writes it back atomically. `compute` then asks `Fetcher` for the subject's repositories and their typed records, which come from the cache alone; `compute` never syncs.
4. `compute` normalises timestamps to the request timezone, assigns each record to a bucket, aggregates per group, and returns the `StatsResult`.
5. A renderer presents the result. The web app repeats steps 1 to 5 per request; the cache makes repeats cheap.

## Error handling

Errors are typed in the layer that detects them and presented only at the edge:

- `settings` raises `SettingsError`.
- `fetch` raises `AuthError`, `NotFoundError`, `RateLimitError`, `StatsPendingError`, `GraphQLError`, `CacheVersionError`, all subclasses of `FetchError`.
- `stats` raises `InvalidRangeError`, `InvalidRequestError`, `UnknownGroupError`, `EmptySubjectError`, all subclasses of `StatsError`.
- `reports` raises `UsageError` and converts all of the above once, in `cli.main` (exit status 1, or 2 for `UsageError` and `SettingsError`) and in the web app's error middleware (HTTP 400, 404, 502 or 500, as the reports spec lists).
- Unexpected exceptions propagate and are logged with `loguru.logger.exception`.

## Implementation

**Stack.** Python 3.14 (as in the shared Python rules), managed with [uv](https://docs.astral.sh/uv/) and a committed `uv.lock`; ruff and pre-commit as in the shared rules; pytest and hypothesis for tests; mypy for type checking. Runtime libraries are proposals pending a maintenance check before each `uv add`: [aiohttp](https://docs.aiohttp.org/en/stable/), [loguru](https://loguru.readthedocs.io/), [Rich](https://rich.readthedocs.io/), [Plotly](https://plotly.com/python/), [cappa](https://cappa.readthedocs.io/). The local web app uses aiohttp's server (`aiohttp.web`) rather than FastAPI with uvicorn, since aiohttp is already a dependency (reports review 3, decision 1, 2026-10-30). The stdlib covers `sqlite3`, `datetime`, `zoneinfo`, `statistics` and `json`.

**Build order.** The sequence of steps, with deliverables, dependencies and done criteria, is in [Implementation order](../implementation-order.md).

**Testing.** Unit tests run on recorded fixture responses and never touch the network. One opt-in integration test, skipped without `GITHUB_TOKEN`, fetches a small public repository and checks line totals against the REST `stats/code_frequency` endpoint. Tests are scoped to changed modules, as the shared rules require.

**Limits accepted for the first release.** Default-branch history only; line counts are not filtered for generated files; one timezone per report; GitHub Enterprise Server is out of scope.

## Settings

Layered, later wins: built-in defaults, `~/.config/wambatic/config.json`, command-line flags. Component settings are defined in the component specs under the `fetch.`, `stats.` and `report.` prefixes. The token is never a setting: it is read from the environment only. The two environment variables the system reads are:

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | none | API token |
| `WAMBATIC_CONFIG` | `~/.config/wambatic/config.json` | Config file path |

**Config file.** A JSON object with optional `fetch`, `stats` and `report` objects whose keys are the setting names without their prefix, for example `{"fetch": {"workers": 8}}`. The file is chosen as `config_path`, else `WAMBATIC_CONFIG`, else the default path. A missing default file means built-in defaults; a missing file named by `config_path` or `WAMBATIC_CONFIG` raises `SettingsError`.

**Overrides.** `overrides` has the same nested shape as the file, for example `{"fetch": {"workers": 8}}`, and is merged section by section over it.

**Values.** A `timedelta` setting is written as a string of a non-negative integer and one unit, `s`, `m`, `h`, `d` or `w` (`"30d"`, `"1h"`, `"0s"`); command-line flags take the same syntax. A list setting is a JSON array of strings. A `Path` setting has a leading `~` expanded with `Path.expanduser()`; environment variables are not expanded, and relative paths stay relative to the working directory.

**Errors.** An unknown section or key, a token-like key among them, a value of the wrong type, a malformed duration or a value outside a `Literal` set raises `SettingsError`. The message names the key and, for a `Literal`, the allowed values; it never echoes the value, so a token put in the wrong place is not repeated in logs.

**Version identity.** `src/wambatic/version.py` defines `VERSION`, read once from the installed package metadata. The cache identity and `StatsResult.provenance` both take the version from it.

## External dependencies

- The GitHub [GraphQL](https://docs.github.com/en/graphql) and [REST](https://docs.github.com/en/rest) APIs.
- The libraries named under Implementation, each declared in `pyproject.toml`.
- The shared rules and skills from the agents repository, linked as the `.agents/` submodule.
