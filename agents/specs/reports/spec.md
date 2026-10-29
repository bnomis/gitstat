# Reports

**Version:** 1.0
**Status:** proposed
**Date:** 2026-10-29

The three ways a user sees a `StatsResult`: a terminal report, a self-contained static HTML report, and a local web app. All three render the same result object, so they never disagree. It also defines the `gitstat` command line.

**Prerequisites:** [Fetch and cache](../fetch-and-cache/spec.md) and [Stats](../stats/spec.md) are implemented (check: `python -c 'import gitstat.stats'`).

## Module location

`src/gitstat/cli.py` (command line), `src/gitstat/reports/` (`base.py`, `terminal.py`, `html.py`, `web.py`, `figures.py`, `templates/`), with tests in `src/tests/reports/` and `src/tests/test_cli.py`.

## API

```python
import pathlib
import typing

class Renderer(typing.Protocol):
    def render(self, result: StatsResult) -> None:
        """Present the result; terminal and html write out, web serves."""

def build_figures(result: StatsResult) -> list[Figure]:
    """One figure per metric group, shared by the html and web renderers."""

def render_terminal(result: StatsResult, console: Console) -> None: ...
def render_html(result: StatsResult, out: pathlib.Path) -> pathlib.Path:
    """Write one self-contained HTML file and return its path."""

def serve(subject: Subject, request: StatsRequest, host: str, port: int) -> None:
    """Run the local web app until interrupted."""

def main(argv: list[str] | None = None) -> int: ...
```

Command line (`gitstat <command> <target>`):

```text
gitstat report  <target> [--format terminal|html|json] [--out PATH]
                         [--by year|month|week|day|total] [--since DATE] [--until DATE]
                         [--groups activity,flow,delivery] [--by-author] [--tz ZONE]
gitstat serve   <target> [--host 127.0.0.1] [--port 8000]
gitstat cache   clear|info
```

`<target>` is `user:NAME`, `org:NAME` or `repo:OWNER/NAME`. Bare `OWNER/NAME` means a repo and bare `NAME` is resolved against the API as a user or org, and rejected as ambiguous if it is both.

## Error handling

- `UsageError` (bad target, bad date, `--by-author` with a user target): exit status 2 with a one-line message.
- `AuthError`, `CacheVersionError`, `EmptySubjectError`, `InvalidRangeError`, `NotFoundError`, `RateLimitError`, `StatsPendingError`, `UnknownGroupError`: caught at `main`, logged with `loguru.logger.error`, exit status 1. The message states the fix (set `GITHUB_TOKEN`, wait until the reset time, clear the cache).
- `OSError` writing `--out`: exit status 1, no partial file left behind (write to a temp file, then rename).
- The web app returns HTTP 400 for invalid query parameters and 502 with the upstream message when GitHub fails; it never shows a traceback.
- `KeyboardInterrupt` exits 130 quietly.

## Implementation

**One result, three renderers.** Rendering is a pure function of `StatsResult`. Only `--format` and the command select a renderer; there is no per-renderer metric logic.

**Terminal.** [Rich](https://rich.readthedocs.io/) tables for summary and top-contributor tables and Unicode sparklines or bar charts per series; with `--by` the series are printed as period rows. `--format json` dumps the result, including provenance, to stdout for piping (the one place `print` is allowed).

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

Settings load from a TOML file (`~/.config/gitstat/config.toml`) and are overridden by flags. The token is deliberately not a setting.

## External dependencies

- [Plotly](https://plotly.com/python/), [Rich](https://rich.readthedocs.io/), [FastAPI](https://fastapi.tiangolo.com/), [uvicorn](https://www.uvicorn.org/), [cappa](https://cappa.readthedocs.io/) (the shared Python rules name cappa for CLI definitions), `loguru`.
- Maintenance status of each is to be checked before `uv add`, per the shared tools-and-libraries rule; alternatives noted if a check fails: Altair for Plotly, Typer for cappa, stdlib `http.server` plus the HTML renderer for FastAPI.
