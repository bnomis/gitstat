# Reports

**Version:** 1.2
**Status:** proposed
**Date:** 2026-10-29

The three ways a user sees a `StatsResult`: a terminal report, a self-contained static HTML report, and a local web app. All three render the same result object, so they never disagree. It also defines the `gitstat` command line.

**Prerequisites:** [Fetch and cache](../fetch-and-cache/spec.md) and [Stats](../stats/spec.md) are implemented (check: `python -c 'import gitstat.stats'`).

Version 1.2 settles what step 5 of the [implementation order](../implementation-order.md) (terminal report and CLI) needed; the gaps and the choices made are in [review-1.md](review-1.md).

## Module location

`src/gitstat/cli.py` (command line), `src/gitstat/__main__.py` (`python -m gitstat`), `src/gitstat/reports/`, with tests in `src/tests/reports/`, `src/tests/test_cli.py` and fixtures in `src/tests/fixtures/reports.py`:

| Module | Holds | Built in implementation step |
|--------|-------|------------------------------|
| `errors.py` | `UsageError` | 5 |
| `base.py` | `result_to_dict`, `render_json`; the `Renderer` protocol in 7 | 5 |
| `terminal.py` | `render_terminal`, `sparkline` | 5 |
| `figures.py` | `build_figures` | 7 |
| `html.py`, `templates/` | `render_html` | 7 |
| `web.py` | `serve` | 9 |

`gitstat.cli` is the composition root: it is the one module that imports every layer (settings, logs, fetch, stats, reports). `gitstat.reports` imports `gitstat.stats`, `gitstat.settings` and `gitstat.version` and nothing from `gitstat.fetch` until step 9's web app, which syncs per request; renderers read `result.subject` through `StatsResult` without importing it.

## API

```python
import pathlib
import typing

import rich.console

class Renderer(typing.Protocol):
    def render(self, result: StatsResult) -> None:
        """Present the result; terminal and html write out, web serves."""

def build_figures(result: StatsResult) -> list[Figure]:
    """One figure per metric group, shared by the html and web renderers."""

def render_terminal(result: StatsResult, console: rich.console.Console) -> None: ...
def result_to_dict(result: StatsResult) -> dict[str, object]:
    """The result as JSON-ready data (see JSON output); shared by --format json and /api/stats."""
def render_json(result: StatsResult, stream: typing.TextIO) -> None:
    """`json.dumps(result_to_dict(result), indent=2, ensure_ascii=False)` and a newline."""
def sparkline(values: list[float]) -> str:
    """One block character per value from U+2581 to U+2588, scaled from min to max; all-equal
    values give U+2581 throughout; an empty list gives ''."""
def render_html(result: StatsResult, out: pathlib.Path) -> pathlib.Path:
    """Write one self-contained HTML file and return its path."""

def serve(subject: Subject, request: StatsRequest, host: str, port: int) -> None:
    """Run the local web app until interrupted."""

def main(argv: list[str] | None = None) -> int:
    """Parse `argv` (default `sys.argv[1:]`), run the command, convert errors once (see Error
    handling) and return the exit status. Never calls `sys.exit`."""

def run() -> None:
    """The `gitstat` console script and `python -m gitstat`: `sys.exit(main())`."""

class UsageError(Exception):
    """A command line that parses but cannot be run; exit status 2."""
```

Command line (`gitstat <command> <target>`):

```text
gitstat [-v | -q] report <target> [--format terminal|html|json] [--out PATH]
                         [--by year|month|week|day|total] [--since DATE] [--until DATE]
                         [--groups activity,flow,delivery] [--by-author] [--tz ZONE]
                         [--full-refresh | --no-fetch] [--max-age DURATION]
                         [--ignore-cache-version]
gitstat [-v | -q] serve  <target> [--host 127.0.0.1] [--port 8000]
gitstat [-v | -q] cache  clear|info
```

The CLI is defined with [cappa](https://cappa.readthedocs.io/) dataclasses, as the shared Python rules require: a root command holding `-v`/`--verbose` and `-q`/`--quiet` and a `cappa.Subcommands` field of the `report`, `serve` and `cache` command classes. Step 5 builds `report` (without `--format html` and `--out`) and `cache`; `--format html` and `--out` arrive in step 7 and `serve` in step 9, so until then `--format html` (on the command line or as `report.format` in the config file) is a `UsageError` naming step 7, and `serve` is not a command.

**Flags.**

- `<target>` is `user:NAME`, `org:NAME` or `repo:OWNER/NAME`. Bare `OWNER/NAME` means a repo, and bare `NAME` is resolved with `Fetcher.owner_kind`, which asks GitHub whether the login is a user or an organisation (user and organisation logins share one namespace on GitHub, so a name is never both). A `NAME` or `OWNER` is 1 to 39 characters of ASCII letters, digits and `-`; a repo `NAME` is 1 to 100 characters of ASCII letters, digits, `.`, `_` and `-`. Anything else, including an empty part, an unknown prefix or more than one `/`, is a `UsageError`. Bare `NAME` with `--no-fetch` is a `UsageError` asking for `user:NAME` or `org:NAME`, since resolving it needs the network.
- `--by` maps to `StatsRequest.granularity` (`total` is `Granularity.TOTAL`); default `month`.
- `--since` and `--until` are local dates `YYYY-MM-DD` exactly (no other ISO forms), both inclusive, in the report timezone; anything else is a `UsageError`.
- `--groups` is a comma-separated list; default `activity,flow`, as `StatsRequest`. An unknown name is passed through to `compute`, which raises `UnknownGroupError`.
- `--by-author` sets `StatsRequest.by_author`; with a user target, after any bare-`NAME` resolution, it is a `UsageError`.
- `--tz` overrides `stats.timezone`; the zone is resolved with `zoneinfo.ZoneInfo`, and an unknown zone from either source is a `SettingsError` naming `stats.timezone`.
- `--format` overrides `report.format`; `--max-age` overrides `fetch.max_age` in the settings duration syntax (`30m`, `1d`), so a malformed value is a `SettingsError`. Flags reach `Settings` only through `load_settings(None, overrides)`.
- `--full-refresh` passes `full_refresh=True` to `Fetcher.sync` and ignores `--max-age`. `--no-fetch` skips the network entirely. The two together are a `UsageError`.
- `--ignore-cache-version` opens the cache with `Cache.open(..., ignore_version=True)`, as `CacheVersionError`'s message tells the user to; provenance then records it.
- `-v` sets the log level to `DEBUG`, `-q` to `WARNING`; the default is `INFO`. Both together are a `UsageError`. Logs go to stderr, as `{level}: {message}` at `INFO` and `WARNING` and in loguru's default format (time and source location) at `DEBUG`, through `gitstat.logs.configure_logging`; reports go to stdout.
- The config file is chosen as the system spec says (`GITSTAT_CONFIG`, else the default path); there is no `--config` flag.

**Running `report`.** In this order:

1. Configure logging, load settings with the flag overrides, parse the target, and check the flag combinations above; nothing touches the cache or the network before these pass.
2. Open the cache at `fetch.cache_path`.
3. Decide whether to sync. The resources are `resources_for(groups) & BUILT_RESOURCES` (fetch spec): resources whose step is not built are never synced, so the default groups run before step 6. There is no sync when `--no-fetch` is given, when the resources are empty, or when `fetch.max_age` is above zero, `--full-refresh` is absent and every `fetched_at:<resource>` in `Fetcher.provenance(subject, resources)` is a time less than `max_age` before now. Otherwise sync.
4. Only when a sync or a bare-`NAME` resolution is needed, resolve the token with `resolve_token()` and enter the `Fetcher` (which opens the aiohttp session). Otherwise the `Fetcher` is built with an empty token and never entered, so no session is opened and no request can be made; a warm cache with `--no-fetch` or a fresh `--max-age` needs no `GITHUB_TOKEN`.
5. Sync, logging one `info` line from the `SyncReport`: repositories listed, unchanged, commits written and any full refetches.
6. `compute`, then render to stdout with the selected format.

**`cache info`** prints, for `fetch.cache_path`, what `Cache.inspect` (fetch spec) returns: the path and size, the recorded identity and every key that differs from the running code (with both values), `version_override_at` when set, the number of repositories and commits, and the latest sync time. It opens the file read-only and never creates, migrates or stamps it, so it works on a cache that `report` refuses. A missing file prints that there is no cache at the path and exits 0.

**`cache clear`** deletes the cache file and its `-wal` and `-shm` files with `clear_cache` (fetch spec), logs each path removed at `info`, and exits 0 when there was nothing to remove. It does not prompt: the cache is derived data that the next `report` refetches.

## Error handling

`main` converts every error once, logging a one-line message with `loguru.logger.error` and no traceback unless stated:

| Raised | Exit status |
|--------|-------------|
| success, and `--help` | 0 |
| any `FetchError` (`AuthError`, `CacheVersionError`, `GraphQLError`, `NotFoundError`, `RateLimitError`, `StatsPendingError`) | 1 |
| any `StatsError` (`EmptySubjectError`, `InvalidRangeError`, `InvalidRequestError`, `UnknownGroupError`) | 1 |
| `OSError` writing `--out` (step 7) | 1 |
| any other exception: logged with `loguru.logger.exception` (traceback included) | 1 |
| `UsageError`, `SettingsError`, and a command line cappa cannot parse (cappa prints its own message) | 2 |
| `KeyboardInterrupt`: no message | 130 |

- Messages state the fix: `AuthError` says to set `GITHUB_TOKEN`, `RateLimitError` gives the reset time, `CacheVersionError` names `gitstat cache clear` and `--ignore-cache-version`, and `EmptySubjectError` with `--no-fetch` adds that the cache may only need a sync. These texts come from the errors themselves where they already carry them.
- No message repeats a token or a config value (system spec, Settings).
- `--out` (step 7) writes to a temporary file and renames it, so no partial file is left behind.
- The web app returns HTTP 400 for invalid query parameters and 502 with the upstream message when GitHub fails; it never shows a traceback.

## Implementation

**One result, three renderers.** Rendering is a pure function of `StatsResult`. Only `--format` and the command select a renderer; there is no per-renderer metric logic.

**Terminal.** [Rich](https://rich.readthedocs.io/) output, in this order; every table is a `rich.table.Table` and numbers are right-aligned with thousands separators (`1,234`), `lines_net` with an explicit sign (`+1,234`, `-56`, `0`), so nothing depends on colour:

1. A title line: the subject (`repo octocat/Hello-World`, `user octocat`, `org octo-org`), the resolved range (`2026-01-01 to 2026-10-29`), the granularity (`by month`, or `total`) and the timezone.
2. **Activity by period**: one row per bucket, columns Period, Commits, Contributors, Active days, Added, Deleted, Net, from the total series. A partial bucket's label (from `provenance['partial_buckets']`) ends in ` *` and the table's caption says `* partial period`. With more than one bucket a footer row `Total` sums commits, active days, added, deleted and net (all additive over disjoint buckets), and gives as contributors the number of `top_contributors` rows other than `unattributed` (contributors are not additive over buckets).
3. **Trends**: with more than one bucket, one line per total series, `<metric>  <sparkline>  <min> to <max>`; when there are more buckets than fit in `console.width` less the label and range columns, the line shows the latest buckets that fit and says `last N periods`.
4. **By repository** and **By author**: one table per `by_kind` present, columns Name, Commits, Added, Deleted, Net, each the sum of that breakdown series' points over the range; rows ordered by commits descending then name; rows whose four values are all zero are left out.
5. **Top contributors**: `tables['top_contributors']` in its own order, columns Login, Commits, Added, Deleted, Net, Active days; the first `TOP_CONTRIBUTORS_SHOWN = 20` rows, then a line `and N more` when there are more (the JSON output has every row).
6. **Unavailable**: `tables['unavailable']`, columns Metric and Reason, when not empty.
7. A provenance footer: `computed_at`, each `fetched_at:<resource>`, `gitstat_version` and `schema_version`; when `version_override_at` is present, a warning line that the cache was read with `--ignore-cache-version` at that time.

**JSON output.** `--format json` writes `render_json(result, sys.stdout)` (the one place output bypasses loguru). `result_to_dict` returns, in this key order:

- `format_version`: `1`, raised whenever a key below changes meaning, per the shared versions rule;
- `subject`: `{"kind", "login", "name"}`;
- `request`: `{"granularity", "groups" (sorted list), "since", "until" (ISO date or null, as requested), "by_author", "tz" (`str(tz)`), "settings"}`, where `settings` is every `StatsSettings` field with tuples as lists and durations as `"<total seconds>s"`, which the settings parser reads back;
- `since`, `until`: the resolved range as ISO dates;
- `series`: one object per series in result order, `{"metric", "unit", "by", "by_kind", "points"}`, with `points` a list of `{"label", "start", "value"}` in bucket order; a value whose unit is `count`, `days` or `lines` is an integer, any other a float;
- `tables` and `provenance`: as in the result.

**Static HTML.** [Plotly](https://plotly.com/python/) figures in one file, with plotly.js inlined once (`include_plotlyjs=True`, several MB) so the file works offline and can be hosted on GitHub Pages or attached to an issue. Layout: header with subject and range, summary tiles, one section per metric group, a granularity switch implemented client-side by embedding all four granularities' series and toggling traces, a provenance footer. Charts follow the colour and accessibility guidance of the shared dataviz skill: colour-blind-safe palette, direct labels, light and dark themes.

**Web app.** [FastAPI](https://fastapi.tiangolo.com/) with [uvicorn](https://www.uvicorn.org/), binding to localhost by default. `GET /` is a form for the target; `GET /report?target=&by=&since=&until=&groups=` returns the same HTML as `render_html`; `GET /api/stats?...` returns the `StatsResult` as JSON for custom front ends. Fetching runs in a worker thread with a progress endpoint (`GET /api/progress`) so large orgs do not block the page. The token comes from the server's environment only; the browser never sees it. Binding to a non-loopback host requires `--allow-remote` and prints a warning, since the server acts with the operator's token.

**Visualisation choices.** Line charts for trends, bars for per-bucket counts, stacked bars for added and deleted lines with net as an overlaid line, heat-map calendar for daily commit activity, horizontal bars for contributors and languages. Partial first and last buckets are hatched.

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `report.allow_remote` | `bool` | `False` | Permit the web app on non-loopback hosts |
| `report.format` | `Literal['html', 'json', 'terminal']` | `'terminal'` | Default report format |
| `report.html_theme` | `Literal['auto', 'dark', 'light']` | `'auto'` | HTML theme |
| `report.out_dir` | `Path` | `./gitstat-reports` | Default HTML output directory |
| `report.web_host` | `str` | `'127.0.0.1'` | Web app bind address |
| `report.web_port` | `int` | `8000` | Web app port |

Settings load from a JSON file (`~/.config/gitstat/config.json`) and are overridden by flags. The token is deliberately not a setting.

## External dependencies

- [Plotly](https://plotly.com/python/), [Rich](https://rich.readthedocs.io/), [FastAPI](https://fastapi.tiangolo.com/), [uvicorn](https://www.uvicorn.org/), [cappa](https://cappa.readthedocs.io/) (the shared Python rules name cappa for CLI definitions), `loguru`.
- Maintenance status of each is to be checked before `uv add`, per the shared tools-and-libraries rule; alternatives noted if a check fails: Altair for Plotly, Typer for cappa, stdlib `http.server` plus the HTML renderer for FastAPI.
