# Reports

**Version:** 1.5
**Status:** proposed
**Date:** 2026-10-30

The three ways a user sees a `StatsResult`: a terminal report, a self-contained static HTML report, and a local web app. All three render the same result object, so they never disagree. It also defines the `wambatic` command line.

**Prerequisites:** [Fetch and cache](../fetch-and-cache/spec.md) and [Stats](../stats/spec.md) are implemented (check: `python -c 'import wambatic.stats'`).

Version 1.2 settles what step 5 of the [implementation order](../implementation-order.md) (terminal report and CLI) needed; the gaps and the choices made are in [review-1.md](review-1.md). Version 1.3 adds the terminal's flow sections for step 6 (flow data and stats); the choices are in the [stats review 2](../stats/review-2.md). Version 1.4 settles what step 7 (static HTML report) needed: the figure type, the results the page is built from, the page layout, themes and palette, the output path and the browser test; the choices are in [review-2.md](review-2.md). Version 1.5 adds the delivery sections of the terminal and the HTML page, and the release and workflow-run counts of `cache info`, for step 8 (delivery data and stats); the choices are in the [stats review 3](../stats/review-3.md).

## Module location

`src/wambatic/cli.py` (command line), `src/wambatic/__main__.py` (`python -m wambatic`), `src/wambatic/reports/`, with tests in `src/tests/reports/` (the headless-browser test in `src/tests/reports/test_html_browser.py`), `src/tests/test_cli.py` and fixtures in `src/tests/fixtures/reports.py`:

| Module | Holds | Built in implementation step |
|--------|-------|------------------------------|
| `errors.py` | `UsageError` | 5 |
| `base.py` | `result_to_dict`, `render_json` | 5 |
| `terminal.py` | `render_terminal`, `sparkline` | 5 |
| `rows.py` | the table rows both the terminal and the HTML page show (moved out of `terminal.py`) | 7 |
| `figures.py` | `Figure`, `build_figures`, `build_range_figures`, `build_calendar`, `PALETTE` | 7 |
| `html.py`, `templates/` (`report.html`, `report.css`, `report.js`) | `HtmlReport`, `html_document`, `render_html`, `report_filename` | 7 |
| `web.py` | `serve` | 9 |

`wambatic.cli` is the composition root: it is the one module that imports every layer (settings, logs, fetch, stats, reports). `wambatic.reports` imports `wambatic.stats`, `wambatic.settings` and `wambatic.version` and nothing from `wambatic.fetch` until step 9's web app, which syncs per request; renderers read `result.subject` through `StatsResult` without importing it. Of the third-party libraries, only `html.py` imports `plotly`, and only for the plotly.js it bundles (`plotly.offline.get_plotlyjs()`); figures are plain Plotly JSON built by wambatic's own typed code (review-2.md decision 1).

## API

```python
import dataclasses
import pathlib
import typing

import rich.console

@dataclasses.dataclass(frozen=True, slots=True)
class Figure:
    key: str                          # unique in the page and the chart element's id: 'activity-commits'
    group: typing.Literal['activity', 'delivery', 'flow']
    title: str                        # shown above the chart: 'Commits per period'
    description: str                  # one sentence, the chart's aria-label
    data: list[dict[str, object]]     # Plotly traces as plotly.js JSON; colours left to the theme
    layout: dict[str, object]         # Plotly layout as plotly.js JSON; colours left to the theme

def build_figures(result: StatsResult) -> list[Figure]:
    """The per-period charts of the result's total series, in page order; [] for a TOTAL result."""
def build_range_figures(total: StatsResult) -> list[Figure]:
    """The whole-range charts of a TOTAL result: top contributors, by repository, by author."""
def build_calendar(day: StatsResult) -> Figure | None:
    """The daily-commits heat-map of a DAY result; None without activity series.
    Raises ValueError for any other granularity."""

@dataclasses.dataclass(frozen=True, slots=True)
class HtmlReport:
    total: StatsResult                       # Granularity.TOTAL: tiles, whole-range charts and tables
    periods: dict[Granularity, StatsResult]  # exactly YEAR, MONTH, WEEK and DAY
    initial: Granularity                     # the granularity shown on load; a key of `periods`

def html_document(report: HtmlReport, theme: typing.Literal['auto', 'dark', 'light']) -> str:
    """The whole self-contained page; pure. Raises ValueError when the five results differ in
    anything but granularity (subject, groups, since, until as requested, by_author, tz, settings)."""
def report_filename(subject: Subject) -> str:
    """'repo-OWNER-NAME.html', 'user-NAME.html' or 'org-NAME.html'."""

def render_terminal(result: StatsResult, console: rich.console.Console) -> None: ...
def result_to_dict(result: StatsResult) -> dict[str, object]:
    """The result as JSON-ready data (see JSON output); shared by --format json and /api/stats."""
def render_json(result: StatsResult, stream: typing.TextIO) -> None:
    """`json.dumps(result_to_dict(result), indent=2, ensure_ascii=False)` and a newline."""
def sparkline(values: list[float]) -> str:
    """One block character per value from U+2581 to U+2588, scaled from min to max; all-equal
    values give U+2581 throughout; an empty list gives ''."""
def render_html(
    report: HtmlReport, out: pathlib.Path, theme: typing.Literal['auto', 'dark', 'light']
) -> pathlib.Path:
    """Write `html_document(report, theme)` to `out` atomically and return `out`."""

def serve(subject: Subject, request: StatsRequest, host: str, port: int) -> None:
    """Run the local web app until interrupted."""

def main(argv: list[str] | None = None) -> int:
    """Parse `argv` (default `sys.argv[1:]`), run the command, convert errors once (see Error
    handling) and return the exit status. Never calls `sys.exit`."""

def run() -> None:
    """The `wambatic` console script and `python -m wambatic`: `sys.exit(main())`."""

class UsageError(Exception):
    """A command line that parses but cannot be run; exit status 2."""
```

Command line (`wambatic <command> <target>`):

```text
wambatic [-v | -q] report <target> [--format terminal|html|json] [--out PATH]
                         [--by year|month|week|day|total] [--since DATE] [--until DATE]
                         [--groups activity,flow,delivery] [--by-author] [--tz ZONE]
                         [--full-refresh | --no-fetch] [--max-age DURATION]
                         [--ignore-cache-version]
wambatic [-v | -q] serve  <target> [--host 127.0.0.1] [--port 8000]
wambatic [-v | -q] cache  clear|info
```

The CLI is defined with [cappa](https://cappa.readthedocs.io/) dataclasses, as the shared Python rules require: a root command holding `-v`/`--verbose` and `-q`/`--quiet` and a `cappa.Subcommands` field of the `report`, `serve` and `cache` command classes. Step 5 built `report` (without `--format html` and `--out`) and `cache`; step 7 adds `--format html` and `--out`, and `serve` arrives in step 9, so until then `serve` is not a command.

**Flags.**

- `<target>` is `user:NAME`, `org:NAME` or `repo:OWNER/NAME`. Bare `OWNER/NAME` means a repo, and bare `NAME` is resolved with `Fetcher.owner_kind`, which asks GitHub whether the login is a user or an organisation (user and organisation logins share one namespace on GitHub, so a name is never both). A `NAME` or `OWNER` is 1 to 39 characters of ASCII letters, digits and `-`; a repo `NAME` is 1 to 100 characters of ASCII letters, digits, `.`, `_` and `-`. Anything else, including an empty part, an unknown prefix or more than one `/`, is a `UsageError`. Bare `NAME` with `--no-fetch` is a `UsageError` asking for `user:NAME` or `org:NAME`, since resolving it needs the network.
- `--by` maps to `StatsRequest.granularity` (`total` is `Granularity.TOTAL`); default `month`. With `--format html` it picks the granularity the page shows on load, and `total` is a `UsageError` (the page's summary tiles are the totals; its switch offers year, month, week and day).
- `--since` and `--until` are local dates `YYYY-MM-DD` exactly (no other ISO forms), both inclusive, in the report timezone; anything else is a `UsageError`.
- `--groups` is a comma-separated list; default `activity,flow`, as `StatsRequest`. An unknown name is passed through to `compute`, which raises `UnknownGroupError`.
- `--by-author` sets `StatsRequest.by_author`; with a user target, after any bare-`NAME` resolution, it is a `UsageError`.
- `--tz` overrides `stats.timezone`; the zone is resolved with `zoneinfo.ZoneInfo`, and an unknown zone from either source is a `SettingsError` naming `stats.timezone`.
- `--out PATH` is where `--format html` writes: a file path, or an existing directory to write `report_filename(subject)` into. Without it the file is `report.out_dir / report_filename(subject)`. Missing parent directories are created and an existing file is replaced. `--out` with a format other than `html` (after the config file) is a `UsageError`.
- `--format` overrides `report.format`; `--max-age` overrides `fetch.max_age` in the settings duration syntax (`30m`, `1d`), so a malformed value is a `SettingsError`. Flags reach `Settings` only through `load_settings(None, overrides)`.
- `--full-refresh` passes `full_refresh=True` to `Fetcher.sync` and ignores `--max-age`. `--no-fetch` skips the network entirely. The two together are a `UsageError`.
- `--ignore-cache-version` opens the cache with `Cache.open(..., ignore_version=True)`, as `CacheVersionError`'s message tells the user to; provenance then records it.
- `-v` sets the log level to `DEBUG`, `-q` to `WARNING`; the default is `INFO`. Both together are a `UsageError`. Logs go to stderr, as `{level}: {message}` at `INFO` and `WARNING` and in loguru's default format (time and source location) at `DEBUG`, through `wambatic.logs.configure_logging`; reports go to stdout.
- The config file is chosen as the system spec says (`WAMBATIC_CONFIG`, else the default path); there is no `--config` flag.

**Running `report`.** In this order:

1. Configure logging, load settings with the flag overrides, parse the target, and check the flag combinations above; nothing touches the cache or the network before these pass.
2. Open the cache at `fetch.cache_path`.
3. Decide whether to sync. The resources are `resources_for(groups) & BUILT_RESOURCES` (fetch spec): resources whose step is not built are never synced, so the default groups run before step 6. There is no sync when `--no-fetch` is given, when the resources are empty, or when `fetch.max_age` is above zero, `--full-refresh` is absent and every `fetched_at:<resource>` in `Fetcher.provenance(subject, resources)` is a time less than `max_age` before now. Otherwise sync.
4. Only when a sync or a bare-`NAME` resolution is needed, resolve the token with `resolve_token()` and enter the `Fetcher` (which opens the aiohttp session). Otherwise the `Fetcher` is built with an empty token and never entered, so no session is opened and no request can be made; a warm cache with `--no-fetch` or a fresh `--max-age` needs no `GITHUB_TOKEN`.
5. Sync, logging one `info` line from the `SyncReport`: repositories listed, unchanged, the rows written for each resource synced (`commits 12, issues 3, pull_requests 5`) and any full refetches.
6. `compute`, then render to stdout with the selected format. For `html`, `compute` runs five times on the one synced cache, with the request's granularity set to `TOTAL`, `YEAR`, `MONTH`, `WEEK` and `DAY` and everything else unchanged, giving the `HtmlReport`; `render_html` writes the file with `report.html_theme`, and the path written is printed to stdout as one line (the report itself is the file).

**`cache info`** prints, for `fetch.cache_path`, what `Cache.inspect` (fetch spec) returns: the path and size, the recorded identity and every key that differs from the running code (with both values), `version_override_at` when set, the number of repositories, commits, pull requests, issues, releases and workflow runs, and the latest sync time. It opens the file read-only and never creates, migrates or stamps it, so it works on a cache that `report` refuses. A missing file prints that there is no cache at the path and exits 0.

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

- Messages state the fix: `AuthError` says to set `GITHUB_TOKEN`, `RateLimitError` gives the reset time, `CacheVersionError` names `wambatic cache clear` and `--ignore-cache-version`, and `EmptySubjectError` with `--no-fetch` adds that the cache may only need a sync. These texts come from the errors themselves where they already carry them.
- No message repeats a token or a config value (system spec, Settings).
- `--out` (step 7), and the default HTML path, are written to a temporary file in the target's directory and moved into place with `os.replace`, so no partial file is left behind; the temporary file is removed when the write fails.
- The web app returns HTTP 400 for invalid query parameters and 502 with the upstream message when GitHub fails; it never shows a traceback.

## Implementation

**One result, three renderers.** Rendering is a pure function of `StatsResult` (for HTML, of the five results of one request that differ only in granularity). Only `--format` and the command select a renderer; there is no per-renderer metric logic, and the table rows the terminal and HTML share are built once in `rows.py`. There is no `Renderer` protocol: the CLI dispatches on the format, and the HTML renderer takes several results, so a one-result protocol would have no caller (review-2.md).

**Terminal.** [Rich](https://rich.readthedocs.io/) output, in this order; every table is a `rich.table.Table` and numbers are right-aligned with thousands separators (`1,234`), `lines_net` with an explicit sign (`+1,234`, `-56`, `0`), so nothing depends on colour. Items 2, 4 and 5 appear when the result has `activity` series, items 6 and 7 when it has `flow` series, item 8 when it has `delivery` series and item 9 when it has a DORA proxy series, and item 3 when it has any series with a trend line, so `--groups flow` prints no activity tables but does print the flow trend lines:

1. A title line: the subject (`repo octocat/Hello-World`, `user octocat`, `org octo-org`), the resolved range (`2026-01-01 to 2026-10-29`), the granularity (`by month`, or `total`) and the timezone.
2. **Activity by period**: one row per bucket, columns Period, Commits, Contributors, Active days, Added, Deleted, Net, from the total series. A partial bucket's label (from `provenance['partial_buckets']`) ends in ` *` and the table's caption says `* partial period`. With more than one bucket a footer row `Total` sums commits, active days, added, deleted and net (all additive over disjoint buckets), and gives as contributors the number of `top_contributors` rows other than `unattributed` (contributors are not additive over buckets).
3. **Trends**: with more than one bucket, one line per total series that has a value in every bucket (the activity metrics, then the flow counts `prs_opened`, `prs_merged`, `issues_opened` and `issues_closed`, then the delivery counts `workflow_runs`, `release_count` and `deployments`), `<metric>  <sparkline>  <min> to <max>`; the duration and size medians (`*_p50`, `*_p90`) and the ratios have no trend line, because their empty buckets have no value; when there are more buckets than fit in `console.width` less the label and range columns, the line shows the latest buckets that fit and says `last N periods`.
4. **By repository** and **By author**: one table per `by_kind` present, columns Name, Commits, Added, Deleted, Net, each the sum of that breakdown series' points over the range; rows ordered by commits descending then name; rows whose four values are all zero are left out.
5. **Top contributors**: `tables['top_contributors']` in its own order, columns Login, Commits, Added, Deleted, Net, Active days; the first `TOP_CONTRIBUTORS_SHOWN = 20` rows, then a line `and N more` when there are more (the JSON output has every row).
6. **Flow by period**: one row per bucket, columns Period, PRs opened, PRs merged, Issues opened, Issues closed, from the flow count series, with partial marks as in item 2 and, with more than one bucket, a `Total` footer row summing each column.
7. **Flow times by period**: one row per bucket, columns Period, Review p50, Review p90, Merge p50, Merge p90, Close p50, Close p90 (hours, one decimal place) and PR size p50 (lines), from the duration and size series; a bucket with no value shows `-`. There is no `Total` row, because medians do not add up over buckets; the caption says `hours; - no data`.
8. **Delivery by period**: one row per bucket, columns Period, Runs, Success (the success rate as a percentage with one decimal place, `87.5%`), Duration p50, Duration p90 (minutes, one decimal place), Releases and Release interval p50 (days), from the Actions and release series, with partial marks as in item 2; a bucket with no value shows `-`. With more than one bucket a `Total` footer row sums Runs and Releases and shows `-` in the other columns, which do not add up over buckets. The caption says `minutes and days; - no data`.
9. **DORA proxies by period**: one row per bucket, columns Period, Deployments, Lead time p50, Lead time p90 (hours), Change failure (percentage), Restore p50 and Restore p90 (hours), holding only the columns of the proxies the result has; a `Total` footer row sums Deployments as in item 8. The caption says `proxies: see the README; hours; - no data`. Proxies that are not emitted are in item 10.
10. **Unavailable**: `tables['unavailable']`, columns Metric and Reason, when not empty.
11. A provenance footer: `computed_at`, each `fetched_at:<resource>`, `wambatic_version` and `schema_version`; when `version_override_at` is present, a warning line that the cache was read with `--ignore-cache-version` at that time.

**JSON output.** `--format json` writes `render_json(result, sys.stdout)` (the one place output bypasses loguru). `result_to_dict` returns, in this key order:

- `format_version`: `1`, raised whenever a key below changes meaning, per the shared versions rule;
- `subject`: `{"kind", "login", "name"}`;
- `request`: `{"granularity", "groups" (sorted list), "since", "until" (ISO date or null, as requested), "by_author", "tz" (`str(tz)`), "settings"}`, where `settings` is every `StatsSettings` field with tuples as lists and durations as `"<total seconds>s"`, which the settings parser reads back;
- `since`, `until`: the resolved range as ISO dates;
- `series`: one object per series in result order, `{"metric", "unit", "by", "by_kind", "points"}`, with `points` a list of `{"label", "start", "value"}` in bucket order; a value whose unit is `count`, `days` or `lines` is an integer, any other a float;
- `tables` and `provenance`: as in the result.

**Static HTML.** One self-contained file built by `html_document` from an `HtmlReport` (review-2.md has the reasons for each choice below).

- *Self-contained and offline.* plotly.js is inlined once, in one `<script>`, from `plotly.offline.get_plotlyjs()` (several MB); MathJax is not included. The page's CSS and script come from `templates/report.css` and `templates/report.js`, inlined; no attribute (`src`, `href`, `url(...)`) refers to anything outside the file, and no web font is used (system sans: `system-ui, -apple-system, "Segoe UI", sans-serif`). The file opens from disk with no network, and can be hosted on GitHub Pages or attached to an issue. The templates are read with `importlib.resources` and filled with stdlib `string.Template`; no templating library is added.
- *Escaping.* Every text from the data (logins, repository names, labels) reaches the page through `html.escape`. The figures and the client script's data are one JSON object in `<script type="application/json" id="wambatic-data">`, written with `json.dumps(..., ensure_ascii=False)` and then `<`, `>` and `&` replaced by `\u003c`, `\u003e` and `\u0026`, so no data can close the script element.
- *Layout*, in this order; a section appears only when the result has its group's series, as in the terminal:
  1. A header: `wambatic` and the subject (`repo octocat/Hello-World`), the range of the `TOTAL` result, the timezone, and the granularity switch: a radio group Year, Month, Week, Day with `initial` checked.
  2. Summary tiles from the `TOTAL` result: Commits, Contributors (top-contributors rows other than `unattributed`), Lines added, Lines deleted and Net lines (signed) for `activity`; PRs opened, PRs merged, Issues opened, Issues closed and Median time to merge (hours, one decimal place; `-` with no value) for `flow`; Workflow runs, Success rate, Releases, and Deployments and Median lead time when those proxies are emitted, for `delivery`. Numbers are formatted as in the terminal.
  3. Activity: the per-period charts of `build_figures` for `activity`, the Commits by day calendar from the `DAY` result (not switched), the whole-range charts of `build_range_figures`, then the tables: Activity by period (one per granularity, all but the shown one `hidden`), By repository, By author and Top contributors (every row; the chart shows the first `TOP_CONTRIBUTORS_SHOWN`).
  4. Flow: the per-period charts of `build_figures` for `flow`, then Flow by period and Flow times by period, one table per granularity as above.
  5. Delivery: the per-period charts of `build_figures` for `delivery`, then Delivery by period and, when a proxy is emitted, DORA proxies by period, one table per granularity as above, with a line under the section heading that the DORA figures are proxies and how each is measured is in the README.
  6. Unavailable, when `tables['unavailable']` is not empty.
  7. A provenance footer: the terminal's items, the plotly.js version (`plotly.offline.get_plotlyjs_version()`), and the `--ignore-cache-version` warning when `version_override_at` is present.
  Tables hold the same rows and columns as the terminal's, from `rows.py`, so the two never disagree; they are the page's data view and work without script.
- *Granularity switch.* All four period results are embedded as figures and pre-rendered tables. Choosing a granularity calls `Plotly.react` on each per-period chart with that granularity's figure and toggles the `hidden` attribute of the period tables; nothing is recomputed in the browser. Only total series are embedded per period (never the per-repo or per-author breakdowns, which would grow with repos times days); the breakdown charts and tables come from the `TOTAL` result.
- *Charts* (`build_figures`, per period, in this order): Commits, Contributors and Active days per period (bars, one each), Lines added and deleted per period (added as bars above zero and deleted as negative bars below it with `barmode='relative'`, net as a line on the same axis); Pull requests per period (grouped bars, opened and merged), Issues per period (grouped bars, opened and closed), Time to first review, Time to merge and Time to close (each a p50 and a p90 line, hours, a gap where a bucket has no value), PR size (p50 line, lines); Workflow runs per period (bars), Workflow success rate (line, 0 to 100 per cent on a fixed axis), Workflow duration (p50 and p90 lines, minutes), Releases per period (bars), Release interval (p50 line, days), then, each only when its series is present, Deployments per period (bars), Lead time (p50 and p90 lines, hours), Change failure rate (line, per cent on a fixed 0 to 100 axis) and Time to restore (p50 and p90 lines, hours). Ratios are shown as percentages, the series' 0 to 1 values multiplied by 100. `build_range_figures`: Top contributors (horizontal bars of commits, first `TOP_CONTRIBUTORS_SHOWN`, largest at the top), By repository and By author (horizontal bars of commits, each when that breakdown is present, all-zero rows left out as in the terminal). `build_calendar`: a heat-map of commits by day, one column per ISO week (x is the week's Monday) and one row per weekday, Monday at the top. Every chart has one y-axis; there are no dual axes.
- *Partial buckets.* Bars of a bucket in `provenance['partial_buckets']` carry a diagonal hatch (`marker.pattern.shape` `'/'`); line points in such a bucket have open markers; a chart with a partial bucket has the caption `hatched or open: partial period`.
- *Palette and themes.* Colours follow the validated reference palette of the dataviz skill (read 2026-10-30), held as `PALETTE` in `figures.py`: categorical slots 1 to 3, light `#2a78d6`, `#eb6834`, `#1baf7a`, dark `#3987e5`, `#d95926`, `#199e70` (no chart has more than three series, the most the palette validates for every pair); the heat-map's sequential blue ramp `#cde2fb`, `#86b6ef`, `#3987e5`, `#256abf`, `#0d366b` on light and `#104281`, `#1c5cab`, `#3987e5`, `#6da7ec`, `#b7d3f6` on dark (low to high, so more commits are brighter on the dark surface); chart surface `#fcfcfb` / `#1a1a19`, page `#f9f9f7` / `#0d0d0d`, primary ink `#0b0b0b` / `#f0efec`, secondary ink `#52514e` / `#c3c2b7`, gridlines `#e1e0d9` / `#2c2c2a`. Figures carry no colours: each trace has `meta: {"slot": n}` and the client script fills trace colours and layout colours from the active theme before each `Plotly.react`. `report.html_theme` `light` or `dark` sets `data-theme` on `<html>`; `auto` follows `prefers-color-scheme` and re-themes the charts when it changes. Text never wears a series colour.
- *Labels and hover.* A chart with one series has no legend (its title names it); with two or three it has a legend and each line is labelled at its last point. Hover shows each point's value (`hovermode='x unified'` on per-period charts). Each chart's element has `role="img"` and its `description` as `aria-label`.
- *Testing.* Unit tests validate every figure with `plotly.graph_objects.Figure(data=..., layout=...)`, which rejects an unknown property. A headless-browser test (`src/tests/reports/test_html_browser.py`, marker `browser`) opens the file from disk with [Playwright for Python](https://playwright.dev/python/) and Chromium, aborts and records every request that is not the file itself, and checks there is none, no console error and no page error, that every chart rendered, that each of the four granularities shows its own number of buckets, and that dark and light themes apply. It launches Playwright's own Chromium, else the cloud environment's preinstalled `/opt/pw-browsers/chromium`, else skips with that reason; CI's `browser` job installs Chromium with `playwright install --with-deps chromium` and runs it.

**Web app.** [FastAPI](https://fastapi.tiangolo.com/) with [uvicorn](https://www.uvicorn.org/), binding to localhost by default. `GET /` is a form for the target; `GET /report?target=&by=&since=&until=&groups=` returns the same HTML as `render_html`; `GET /api/stats?...` returns the `StatsResult` as JSON for custom front ends. Fetching runs in a worker thread with a progress endpoint (`GET /api/progress`) so large orgs do not block the page. The token comes from the server's environment only; the browser never sees it. Binding to a non-loopback host requires `--allow-remote` and prints a warning, since the server acts with the operator's token.

**Visualisation choices.** Line charts for trends, bars for per-bucket counts, stacked bars for added and deleted lines with net as an overlaid line, heat-map calendar for daily commit activity, horizontal bars for contributors and languages (languages in step 10). Partial first and last buckets are hatched. The Static HTML paragraph above settles each for step 7.

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `report.allow_remote` | `bool` | `False` | Permit the web app on non-loopback hosts |
| `report.format` | `Literal['html', 'json', 'terminal']` | `'terminal'` | Default report format |
| `report.html_theme` | `Literal['auto', 'dark', 'light']` | `'auto'` | HTML theme; `auto` follows the viewer's system setting |
| `report.out_dir` | `Path` | `./wambatic-reports` | Default HTML output directory, used when `--out` is absent |
| `report.web_host` | `str` | `'127.0.0.1'` | Web app bind address |
| `report.web_port` | `int` | `8000` | Web app port |

Settings load from a JSON file (`~/.config/wambatic/config.json`) and are overridden by flags. The token is deliberately not a setting.

## External dependencies

- [Plotly](https://plotly.com/python/), [Rich](https://rich.readthedocs.io/), [FastAPI](https://fastapi.tiangolo.com/), [uvicorn](https://www.uvicorn.org/), [cappa](https://cappa.readthedocs.io/) (the shared Python rules name cappa for CLI definitions), `loguru`.
- Plotly ships no type information (no `py.typed`, checked on 7.1.0 on 2026-10-30), so `pyproject.toml` gains a mypy override with `ignore_missing_imports` for `plotly` and `plotly.*` only, and the one call `html.py` makes is wrapped in `str(...)` (review-2.md decision 1).
- Development only: [Playwright for Python](https://playwright.dev/python/) for the headless-browser test (step 7).
- Maintenance status of each is to be checked before `uv add`, per the shared tools-and-libraries rule; alternatives noted if a check fails: Altair for Plotly, Typer for cappa, stdlib `http.server` plus the HTML renderer for FastAPI.
