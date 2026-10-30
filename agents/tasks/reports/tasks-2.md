# Tasks: Reports

**Spec:** `agents/specs/reports/spec.md`
**Created:** 2026-10-30
**Version:** 2

This list builds step 7 of the [implementation order](../../specs/implementation-order.md), "Static HTML report": the `plotly` dependency (for its bundled plotly.js only) and Playwright for Python for the browser test, the table rows moved from `terminal.py` to a shared `rows.py`, `figures.py`, `html.py` with its templates, `--format html` and `--out` with an atomic write, a `browser` CI job and the README's HTML section. It is written against version 1.4 of the reports spec, which settled what 1.3 left open for this step; the gaps and the choices made are in [review-2.md](../../specs/reports/review-2.md). It follows the option recommended for that review's decision 1 (own JSON figures, plotly.js only); if another option is chosen, the tasks the review names under it change before the list runs. The step 5 list, [tasks-1.md](tasks-1.md), built the terminal renderer, JSON output and CLI this list extends, and the step 6 list, [stats/tasks-2.md](../stats/tasks-2.md), the flow series and tables.

## Spec coverage

| Spec section | Covered by |
|--------------|------------|
| Module location (`rows.py`) | Task 2 |
| Module location (`figures.py`) | Tasks 3 and 4 |
| Module location (`html.py`, `templates/`) | Tasks 5 and 6 |
| Module location (only `html.py` imports `plotly`; `reports` clear of `fetch`) | Task 10 |
| Module location (`web.py`) | step 9 |
| API: `Figure`, `build_figures` | Task 3 |
| API: `build_range_figures`, `build_calendar` | Task 4 |
| API: `HtmlReport`, `html_document`, `report_filename` | Task 5 |
| API: `render_html` | Task 6 |
| API: `Renderer` (dropped), `serve` | review-2.md choice 14; step 9 |
| Command line: `--format html`, `--out`, `--by` with html | Task 7 |
| Command line: Running `report` step 6 (five results, path on stdout) | Task 7 |
| Error handling (`OSError` writing `--out`; atomic write) | Tasks 6 and 7 |
| Error handling (web app 400 and 502) | step 9 |
| Implementation: One result, three renderers (shared rows, no protocol) | Tasks 2 and 10 |
| Implementation: Static HTML (self-contained, escaping, layout, tables) | Task 5 |
| Implementation: Static HTML (switch, themes in the browser) | Task 6 |
| Implementation: Static HTML (charts, partial buckets, palette, labels) | Tasks 3 and 4 |
| Implementation: Static HTML (testing: validators, browser test, CI job) | Tasks 3, 4 and 8 |
| Implementation: Visualisation choices (languages) | step 8 |
| Settings (`report.format` html, `report.html_theme`, `report.out_dir`) | Tasks 6 and 7 |
| Settings (`allow_remote`, `web_host`, `web_port`) | step 9 |
| External dependencies (Plotly, mypy override, Playwright) | Task 1 |
| External dependencies (FastAPI, uvicorn) | step 9 |
| User guide (shared user-guides rule) | Task 9 |
| Implementation order step 7 "Done when" | Tasks 6, 7 and 8; checked in Task 10 |

The spec's `**Status:**` is not changed by this list: the web app is built by the step 9 list, which sets it to `implemented`.

## Conventions for every task

- Async code is driven as in the earlier lists: plain `def test_...() -> None` functions whose body calls `asyncio.run(...)`; no pytest async plugin.
- Every file a test writes lives under pytest's `tmp_path`; tests that run `main` or `run_report` set `fetch.cache_path` and `report.out_dir` there through a config file named by `WAMBATIC_CONFIG` (monkeypatched). The autouse `isolated_environment` fixture already removes `GITHUB_TOKEN` and `WAMBATIC_CONFIG`.
- No test reaches the network. The HTML tests use the step 4 and step 6 fixture data through the `stats_fetcher` fixture and `tests.conftest.compute_stats`, so every number they check was already worked by hand in `tests.fixtures.stats` (`ORG_BY_MONTH_UTC`, `ORG_FLOW_BY_MONTH_UTC`).
- `wambatic.reports` modules import nothing from wambatic outside `wambatic.reports`, `wambatic.stats`, `wambatic.settings` and `wambatic.version`, and only `wambatic.reports.html` imports `plotly` (Task 10 enforces both).
- Every string from the data reaches the page through `html.escape`, and embedded JSON is escaped as the spec's Escaping paragraph says.
- The project has no affected-tests tool, so each task names its test files literally; Task 10 runs every test the list can reach.
- The local environment may lack the exact Python patch release `pyproject.toml` requires (`>=3.14.7`); if `uv sync` or `uv add` cannot find it, say so in the task's Notes and work around it as tasks-1.md Task 1 did (lower `requires-python` for that one command, then restore `pyproject.toml` and the `requires-python` and `revision` lines of `uv.lock`), never by committing a changed `requires-python`.
- Hypothesis tests use `@hypothesis.settings(max_examples=20, deadline=10000)` (shared testing rule).

---

## Task 1: Add `plotly` and Playwright for Python

**Status:** done
**Priority:** high
**Complexity:** small
**Spec Reference:** External dependencies (Plotly, the mypy override, Playwright); Static HTML (Testing); implementation order Principles (dependencies are checked, not assumed); review-2.md decision 1 and choice 15

**Technical Goal:** Add the runtime library the HTML report needs and the development library its browser test needs, after the maintenance check the shared tools-and-libraries rule requires, and make mypy accept the untyped `plotly` import without loosening any other check.

**Subtasks:**

- [ ] Re-run the maintenance check for `plotly` and `playwright` on the day: latest PyPI release and its date, licence, the GitHub repository not archived; record the result with the date in this task's Notes (review-2.md has the 2026-10-30 result)
- [ ] If either fails the check, stop the list and tell the user, naming the alternative from the reports spec (Altair for Plotly); do not substitute a library
- [ ] `uv add plotly` and `uv add --dev playwright` (a deliberate dependency change, which the implementation order sanctions; never hand-edit `uv.lock`)
- [ ] Check whether the resolved `plotly` ships `py.typed`. If it does, skip the next subtask and say so in Notes. If it does not, add to `pyproject.toml` one `[[tool.mypy.overrides]]` table with `module = ['plotly', 'plotly.*']` and `ignore_missing_imports = true`, and nothing else; no other module gets an override
- [ ] Check that `playwright` ships `py.typed` (it does in recent releases); if it does not, stop and tell the user rather than adding an override for it
- [ ] Register the `browser` marker in `[tool.pytest.ini_options] markers`: `'browser: opens a page in headless Chromium; skipped when no Chromium can be launched'`, alphabetically with the others
- [ ] Do not run `playwright install`: Task 8 decides which Chromium the test launches

**Acceptance Criteria:**

- [ ] `python -c 'import plotly.offline, playwright.sync_api; print(plotly.offline.get_plotlyjs_version())'` succeeds in the project environment
- [ ] `pyproject.toml` lists `plotly` in `dependencies` and `playwright` in the `dev` group, each alphabetically with the others
- [ ] `mypy src` passes with a file that imports `plotly.offline` (checked with a scratch module, then removed)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `uv sync --locked` succeeds (or, where this environment lacks Python 3.14.7, say so in Notes; the `check` job in CI runs it)
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_package.py` passes

**Notes:**

- Depends on stats/tasks-2.md Task 12 (step 6), done
- Key files: `pyproject.toml`, `uv.lock`
- Docs: [plotly.py](https://plotly.com/python/), [plotly.js reference](https://plotly.com/javascript/reference/), [Playwright for Python](https://playwright.dev/python/docs/intro), [mypy per-module options](https://mypy.readthedocs.io/en/stable/config_file.html#per-module-and-global-options)
- The project's `exclude-newer = "14 days"` may resolve an older release than PyPI's latest; record the version actually locked.
- Maintenance check, 2026-10-30, PyPI: `plotly` 7.1.0 (MIT, released 2026-09-15) and `playwright` 1.64.1 (Apache 2.0, released 2026-10-22), both releasing within the last two months. This session's GitHub access covers only the two project repositories, so the archived flag of `plotly/plotly.py` and `microsoft/playwright-python` could not be read; review-2.md's 2026-10-30 check of the same two is the record for it.
- Locked: `plotly` 7.1.0 (bundles plotly.js 4.1.1 by `plotly.offline.get_plotlyjs_version()`) and `playwright` 1.64.0 (1.64.1 is inside the 14-day window), with `narwhals`, `packaging` and `pyee` as new transitive packages.
- `plotly` has no `py.typed`, so the single mypy override for `plotly` and `plotly.*` is in place. `playwright` ships `py.typed`.
- The local Python is older than 3.14.7, so `uv sync` and `uv add` ran with `requires-python` lowered to 3.14.6 for those commands; `pyproject.toml` and the `requires-python` and `revision` lines of `uv.lock` were restored before the commit.

---

## Task 2: Move the table rows into `rows.py`

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** Module location (`rows.py`); Implementation (One result, three renderers); Static HTML (Layout: tables hold the terminal's rows); review-2.md choice 12

**Technical Goal:** Build every table's rows once, as plain values, so the terminal and the HTML page show the same numbers from the same code; the terminal's output does not change.

**Subtasks:**

- [ ] Add `src/wambatic/reports/rows.py` holding, as plain data (labels and numbers, no Rich objects and no formatting): the period rows and the Total row of Activity by period, the rows and Total row of Flow by period, the rows of Flow times by period (`None` for no data), the By repository and By author rows (summed, ordered and filtered as the spec's terminal item 4), the top-contributors rows, the unavailable rows, the partial labels and the contributor count, each as one public function of a `StatsResult`
- [ ] Move the constants these need from `terminal.py` (`TOTAL_METRICS`, `FLOW_COUNTS`, `FLOW_TIMES`, `UNATTRIBUTED`, `TOP_CONTRIBUTORS_SHOWN`, `PARTIAL_MARK` if a row carries it) to `rows.py`, and make `terminal.py` import them and format the rows from `rows.py`; keep `format_number` where it is and export it for the HTML renderer (it is already public)
- [ ] Write `src/tests/reports/test_rows.py`: for `org_result` the activity period rows and Total row equal `tests.fixtures.stats.ORG_BY_MONTH_UTC` and its sums; the flow rows equal `ORG_FLOW_BY_MONTH_UTC`; the By repository rows sum to the Total row for commits and lines; a flow-times bucket with no value is `None`; `repo_total_result` has one period row and no Total row
- [ ] Keep `src/tests/reports/test_terminal.py` passing unchanged, including the exact `ORG_MONTH_TERMINAL` rendering

**Acceptance Criteria:**

- [ ] `git diff src/tests/reports/test_terminal.py src/tests/fixtures/reports.py` is empty: the terminal output is byte-for-byte as before
- [ ] `terminal.py` holds no summing, ordering or filtering of rows; it only formats what `rows.py` returns
- [ ] `rows.py` imports nothing from Rich

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_rows.py src/tests/reports/test_terminal.py src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 1 (only so the environment is synced)
- Key files: `src/wambatic/reports/rows.py`, `src/wambatic/reports/terminal.py`, `src/tests/reports/test_rows.py`
- A refactor commit of its own (`refactor(reports): ...`), before any HTML code, so a change in terminal output would show in its diff alone.
- `rows.py` also holds what both renderers need beyond the tables' rows: the column headers, `subject_text` and `provenance_lines` (so the page's header and footer are the terminal's), and the series helpers (`total_series`, `bucket_list`). The period tables are one `PeriodTable` type (rows, headers, metrics, optional total), so the terminal builds all three the same way; `terminal.format_cell` is the one place a cell is formatted, for the HTML page too.
- `terminal.TOP_CONTRIBUTORS_SHOWN` stays readable through a module `__getattr__`, because `test_terminal.py` must not change and `wambatic.reports` is still being imported when `terminal.py` loads, so the constant cannot be copied at import time.
- The org fixture has no partial buckets in its provenance (its range is whole months); a test of the marks sets `provenance['partial_buckets']`.

---

## Task 3: `Figure`, the palette and the per-period charts

**Status:** done
**Priority:** high
**Complexity:** large
**Spec Reference:** API (`Figure`, `build_figures`); Static HTML (Charts, Partial buckets, Palette and themes, Labels and hover, Testing: validators); review-2.md decision 1 and choices 5, 6, 8, 9, 10 and 11

**User Story:** As a wambatic user opening the HTML report, I want a chart per measure for each period, with partial periods marked and colours that I can tell apart whatever my colour vision, so that I can see how activity and flow changed over time.

**Subtasks:**

- [ ] Add `src/wambatic/reports/figures.py` with the frozen, slotted `Figure` dataclass of the spec's API
- [ ] Add `PALETTE`: for `'light'` and `'dark'`, the three categorical slots, the five sequential steps and the chrome colours (chart surface, page, primary and secondary ink, gridlines), with the values in the spec's Palette and themes paragraph and a comment naming where they come from and the date read
- [ ] `build_figures(result)`: from the total series only (`by is None`), in the spec's order and only for the groups present: `activity-commits`, `activity-contributors`, `activity-active-days` (bars), `activity-lines` (added above zero, deleted as negative bars, `barmode='relative'`, net as a line), `flow-pull-requests` (grouped bars opened and merged), `flow-issues` (grouped bars opened and closed), `flow-review-time`, `flow-merge-time`, `flow-close-time` (p50 and p90 lines in hours, `None` for a bucket with no value so the line has a gap), `flow-pr-size` (p50 line); `[]` for a `TOTAL` result. x values are bucket labels in bucket order
- [ ] Each trace has `meta: {'slot': n}` (1 to 3) and no colour; layouts carry no colour; one y-axis each, titled with the unit
- [ ] Partial buckets from `provenance['partial_buckets']`: bars get `marker.pattern.shape` `'/'` on those points (`''` elsewhere), line points get `marker.symbol` `'circle-open'` there (`'circle'` elsewhere); a figure with any partial bucket says `hatched or open: partial period` in its layout's caption annotation
- [ ] One series: `showlegend` false. Two or three: a legend, and each line labelled at its last point with an annotation; per-period charts use `hovermode='x unified'`
- [ ] Write `src/tests/reports/test_figures.py`: for `org_result` the figure keys are in the spec's order; the commits, lines and flow-count traces' y values equal `ORG_BY_MONTH_UTC` and `ORG_FLOW_BY_MONTH_UTC` month by month; deleted values are negated; a duration bucket with no value is `None`; partial buckets (from provenance) and only they are hatched; `--groups flow` gives flow figures only; `repo_total_result` gives `[]`; no figure has more than three traces carrying a slot, and every slot is in 1 to 3; no `color` key appears anywhere in any figure (recursive check); every figure passes `plotly.graph_objects.Figure(data=f.data, layout=f.layout)` without error; every `PALETTE` value is a `#rrggbb` string
- [ ] Add a known-good pair: the `activity-commits` and `flow-merge-time` figures of `org_result` as JSON in `src/tests/fixtures/reports.py` (`ORG_MONTH_FIGURES`), generated once from the builder, then checked by hand against the stats fixtures with the date of the check in a comment, and a test that the builder reproduces them exactly

**Acceptance Criteria:**

- [ ] Figures hold only JSON values (`json.dumps` of every `data` and `layout` succeeds without a `default`)
- [ ] No metric logic: every plotted value is a series point, or its negation for deleted lines

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_figures.py` passes

**Notes:**

- Depends on Task 2 (for the partial labels and metric names from `rows.py`)
- Key files: `src/wambatic/reports/figures.py`, `src/tests/reports/test_figures.py`, `src/tests/fixtures/reports.py`
- plotly.js: [bar](https://plotly.com/javascript/reference/bar/) (`marker.pattern`), [scatter](https://plotly.com/javascript/reference/scatter/) (`connectgaps`, `marker.symbol`), [layout](https://plotly.com/javascript/reference/layout/) (`barmode`, `hovermode`, `annotations`), [`meta`](https://plotly.com/javascript/reference/scatter/#scatter-meta)
- `figures.py` does not import `plotly`; only the tests do, to validate (review-2.md decision 1).
- Choices the spec left open: a chart whose series have no value in any bucket is left out (an empty chart says nothing), and the caption sits below the plot as a layout annotation named `caption`, at paper coordinates, so the page script can find it. A line is labelled at its last bucket that has a value, not at a gap.
- `PALETTE` holds a `Theme` dataclass per theme (`dataclasses.asdict` gives the page script its JSON). `wambatic.reports` is still being imported while its modules load, so `figures.py` reaches `wambatic.reports.rows` and `base` only inside functions.
- The org fixture has no partial buckets, so its known-good figures carry none; a test sets `provenance['partial_buckets']` for the hatch, open-marker and caption checks.
- The `activity-lines` test failed first because deleted lines were not negated; fixed in the builder.

---

## Task 4: Whole-range charts and the calendar

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`build_range_figures`, `build_calendar`); Static HTML (Charts; Layout item 3); review-2.md choices 5, 6 and 8

**User Story:** As a wambatic user looking at an org, I want to see who contributed most, which repositories and authors the work came from, and on which days work happened, so that I can tell where and when the activity was.

**Subtasks:**

- [ ] `build_range_figures(total)`: raise `ValueError` unless the result's granularity is `TOTAL`; `activity-top-contributors` (horizontal bars of commits for the first `TOP_CONTRIBUTORS_SHOWN` top-contributors rows, largest at the top), `activity-by-repository` and `activity-by-author` (horizontal bars of commits from the `rows.py` breakdown rows, each only when that `by_kind` is present); `[]` without activity series
- [ ] `build_calendar(day)`: raise `ValueError` unless the granularity is `DAY`; `None` without activity series; otherwise `activity-calendar`, one heat-map trace with x the Monday of each ISO week in the range, y the weekdays Monday to Sunday (Monday at the top), z the day's commits, `None` for days outside the range so they are blank; the colourscale is left to the theme (the trace's `meta` says `{'scale': 'sequential'}`)
- [ ] Tests in `src/tests/reports/test_figures.py`: `build_range_figures` on a `TOTAL` org result with `by_author` gives the three figures with bar values equal to the `rows.py` rows; a repo subject has no by-repository figure; 25 top contributors (via `dataclasses.replace`) give 20 bars; a `MONTH` result raises `ValueError`; `build_calendar` on the org's `DAY` result puts each fixture commit day's count at its (week, weekday) cell and the cell totals sum to the commits total; days before `since` and after `until` are `None`; a `MONTH` result raises `ValueError`; `--groups flow` gives `None`; every figure passes `plotly.graph_objects.Figure(...)`; no `color` key appears

**Acceptance Criteria:**

- [ ] Breakdown bars equal the terminal's breakdown rows, shown by comparing with `rows.py`
- [ ] The calendar's cells sum to the result's total commits

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_figures.py` passes

**Notes:**

- Depends on Task 3
- Key files: `src/wambatic/reports/figures.py`, `src/tests/reports/test_figures.py`, `src/tests/conftest.py` (add `org_total_result` and `org_day_result` fixtures beside `org_result`, through `compute_stats`)
- plotly.js: [heatmap](https://plotly.com/javascript/reference/heatmap/) (`xgap`, `ygap` give the cell gaps), [bar](https://plotly.com/javascript/reference/bar/) (`orientation='h'`, `yaxis.autorange='reversed'`)

---

## Task 5: The HTML document

**Status:** todo
**Priority:** high
**Complexity:** large
**Spec Reference:** API (`HtmlReport`, `html_document`, `report_filename`); Static HTML (Self-contained and offline, Escaping, Layout, Granularity switch: pre-rendered tables); review-2.md decision 1 and choices 2, 6, 7, 12 and 13

**User Story:** As a wambatic user, I want one HTML file holding the summary, every chart and every table for my subject, readable even without script, so that I can open it offline, host it or attach it to an issue.

**Subtasks:**

- [ ] Add `src/wambatic/reports/html.py` with the frozen, slotted `HtmlReport`, `report_filename(subject)` and `html_document(report, theme)`; validate that `periods` has exactly the four period granularities, that `total` is `TOTAL`, that `initial` is a key of `periods`, and that the five results agree in subject and in every request field but granularity, raising `ValueError` naming the first difference
- [ ] Add `src/wambatic/reports/templates/report.html`, `report.css` and `report.js` (the script's behaviour is Task 6; here it may be a stub that does nothing), read with `importlib.resources.files('wambatic.reports')` and filled with `string.Template.substitute` (so a missing placeholder raises); the CSS defines the light and dark tokens of `PALETTE` as custom properties on `:root`, for `[data-theme="dark"]` and for `prefers-color-scheme: dark` when no `data-theme` is set
- [ ] The page in the spec's order: header (subject text as the terminal's title, the `TOTAL` range, timezone, the switch as a `<fieldset>` of four radio inputs with `initial` checked), tiles, the Activity and Flow sections (a `<figure>` per `Figure` with `id` = key, `role="img"`, `aria-label` = description and a `<figcaption>` with the title), the tables from `rows.py` formatted with `format_number` (period tables once per granularity with `data-granularity` and `hidden` on all but `initial`), Unavailable, and the provenance footer with the plotly.js version
- [ ] Embed plotly.js once in a `<script>` from `str(plotly.offline.get_plotlyjs())`, and the data object `{"initial", "theme", "palette", "periods": {granularity: [figures]}, "range": [figures], "calendar": figure or null}` in `<script type="application/json" id="wambatic-data">` escaped as the spec says
- [ ] `<html data-theme="light">` or `"dark"` for those themes and no `data-theme` for `auto`
- [ ] Write `src/tests/reports/test_html.py` (with `org_report` and `repo_report` fixtures building an `HtmlReport` from the stats fixture through `compute_stats`): every figure key has its element; the period tables appear once per granularity with only `initial` visible; the tiles show the `TOTAL` result's commits, contributors and lines and `-` for a median with no data; the document holds exactly one copy of plotly.js (count a marker string from `get_plotlyjs()`); no `src`, `href` or CSS `url(` refers to `http:`, `https:` or `//`; a login `<b>&"'</script>` (put into `top_contributors` with `dataclasses.replace`) appears only escaped in the HTML and round-trips through the parsed JSON block; the JSON block parses with `json.loads`; `report_filename` for each subject kind; mismatched results (different `since`, a non-`TOTAL` total, a missing granularity) raise `ValueError`; each theme sets `data-theme` as above; the templates are found through `importlib.resources`

**Acceptance Criteria:**

- [ ] `html_document` is pure: no file or network access beyond reading its own templates
- [ ] No data string reaches the page unescaped, shown by the hostile-login test
- [ ] With script disabled the initial granularity's tables, the tiles and the footer are readable (they are plain HTML)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_html.py src/tests/reports/test_figures.py src/tests/reports/test_rows.py` passes

**Notes:**

- Depends on Tasks 2, 3 and 4
- Key files: `src/wambatic/reports/html.py`, `src/wambatic/reports/templates/`, `src/tests/reports/test_html.py`, `src/tests/conftest.py`
- `string.Template` uses `$name`; CSS and the script contain no `$`, or escape it as `$$` (Python [string.Template](https://docs.python.org/3.14/library/string.html#template-strings)).
- Check that `uv build` puts `templates/` in the wheel (list it with `python -m zipfile -l`); if not, configure the build backend to include it and record how in Notes.

---

## Task 6: The page script and `render_html`

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`render_html`); Static HTML (Granularity switch, Palette and themes, Labels and hover); Error handling (`--out` atomic write); Settings (`report.html_theme`); review-2.md choices 4, 7 and 11

**User Story:** As a wambatic user, I want to switch the report between years, months, weeks and days, and have it follow my light or dark setting, so that one file answers questions at every scale and is comfortable to read.

**Subtasks:**

- [ ] Write `templates/report.js` (plain script, no modules or framework): read `wambatic-data`; a `themed(figure, theme)` function that copies a figure and fills each trace's colour from `palette[theme].categorical[slot - 1]` (bars `marker.color`, lines `line.color` and `marker.color`), the heat-map's colourscale from the sequential steps, and the layout's `paper_bgcolor`, `plot_bgcolor`, `font.color` and axis `gridcolor` from the chrome colours; draw every chart with `Plotly.newPlot` at load (`responsive: true`, `displaylogo: false`); on a switch change, `Plotly.react` each per-period chart with that granularity's figure and set `hidden` on the period tables; the active theme is `data-theme` when set, else `matchMedia('(prefers-color-scheme: dark)')`, and a change of the media query re-themes every chart
- [ ] `render_html(report, out, theme)` in `html.py`: build the document first, then create `out.parent` (`parents=True, exist_ok=True`), write to `tempfile.NamedTemporaryFile(dir=out.parent, delete=False, suffix='.tmp')` with UTF-8, `os.replace` it onto `out`, and unlink the temporary file if anything fails before the replace; return `out`
- [ ] Tests in `src/tests/reports/test_html.py`: `render_html` writes the file and returns its path; a second call replaces it; when `os.replace` is monkeypatched to raise `OSError`, the error propagates, `out` is unchanged (absent, or the earlier file) and no `.tmp` file is left in the directory; missing parents are created; the script file has no `$` that `string.Template` would read

**Acceptance Criteria:**

- [ ] No partial file is ever left at `out` or beside it
- [ ] The switch and the themes need no network and no data beyond the embedded JSON (checked in the browser by Task 8)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_html.py` passes

**Notes:**

- Depends on Task 5
- Key files: `src/wambatic/reports/templates/report.js`, `src/wambatic/reports/html.py`, `src/tests/reports/test_html.py`
- plotly.js: [`Plotly.newPlot` and `Plotly.react`](https://plotly.com/javascript/plotlyjs-function-reference/); [`matchMedia` change events](https://developer.mozilla.org/en-US/docs/Web/API/MediaQueryList/change_event); Python [`os.replace`](https://docs.python.org/3.14/library/os.html#os.replace) is atomic on POSIX within one file system, which the same-directory temporary file guarantees.

---

## Task 7: `--format html` and `--out` in the CLI

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** Command line (`--format html`, `--out`, `--by` with html; Running `report` step 6); Error handling (`OSError` writing `--out` exits 1); Settings (`report.format`, `report.out_dir`, `report.html_theme`); review-2.md choices 2, 3 and 4

**User Story:** As a wambatic user, I want `wambatic report org:NAME --format html` to write the report to a file and tell me where, so that I can open it in a browser or pass it on.

**Subtasks:**

- [ ] Add `--out` (`str | None`) to `Report` and accept `html` in `--format`'s help text; remove the step 7 `UsageError` from `check_report` and add the new ones: `--out` when the effective format is not `html`, and `--by total` with `html`
- [ ] `output_path(out, settings, subject) -> pathlib.Path`: `--out` as given, or inside it with `report_filename(subject)` when it is an existing directory; else `settings.report.out_dir / report_filename(subject)`
- [ ] In `run_report`, for `html`: after the one sync, compute the `TOTAL` result and the four period results with `dataclasses.replace(request, granularity=...)` against the same reader, build the `HtmlReport` with `initial` from `--by`, call `render_html` with `settings.report.html_theme`, and write the path and a newline to `stdout`; the cache stays open until all five are computed and is closed in the `finally` as now
- [ ] Tests in `src/tests/test_cli.py`: with the `stats_cache` file and `--no-fetch`, `org:octo-org --format html` writes `<out_dir>/org-octo-org.html` (out_dir under `tmp_path` via the config file), prints exactly that path, and the file parses as HTML containing the org's subject text; `--out FILE` and `--out DIR` (existing) write where the spec says; `report.format` `html` from the config file works without `--format`; `--out` with `--format json` and `--by total` with html each raise `UsageError` before the cache is opened; `--format html` syncs once (count `Fetcher.sync` calls through the replay server, as Task 8 of tasks-1.md did) while computing five times; through `main`, an `--out` whose parent is a regular file returns 1 with one `ERROR:` line and leaves no `.tmp` file
- [ ] Update the `--format` choices test that checks the CLI against `ReportSettings.format`

**Acceptance Criteria:**

- [ ] One sync, five computes, one file, one line on stdout
- [ ] Every new usage error is raised before the cache or network is touched

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_cli.py src/tests/reports/test_html.py` passes

**Notes:**

- Depends on Task 6
- Key files: `src/wambatic/cli.py`, `src/tests/test_cli.py`
- The five-result build lives in `cli.py` for now; step 9's web app needs the same and will hoist it then (review-2.md, Open for a later step).

---

## Task 8: Headless-browser smoke test and the `browser` CI job

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** Static HTML (Testing: the browser test and CI job); implementation order step 7 "Done when" (opens offline, all four granularities, headless-browser smoke test); review-2.md choice 15

**Technical Goal:** Prove in a real browser that the file works offline, renders every chart, switches between the four granularities and applies both themes, and make that check run in CI.

**Subtasks:**

- [ ] A session-scoped `chromium` fixture in `src/tests/reports/test_html_browser.py`: `playwright.sync_api.sync_playwright()`, launch Playwright's own Chromium; on `playwright.sync_api.Error`, launch with `executable_path='/opt/pw-browsers/chromium'` when that file exists (the Claude Code cloud environment's preinstalled Chromium; say so in a comment); otherwise `pytest.skip` with the reason. Every test in the module is marked `browser`
- [ ] Render the org `HtmlReport` (Task 5's fixture) to a file under `tmp_path` with theme `auto`, open it as a `file://` URL in a new context with `page.route('**/*', ...)` that lets only the file's own URL through and aborts and records every other request
- [ ] Check: no request was recorded; no `console` message of type `error` and no `pageerror`; every per-period, range and calendar figure's element contains a rendered plot (`.main-svg`); for each of Year, Month, Week and Day, clicking its radio makes the first per-period chart's first trace have as many x values as that granularity's result has buckets, and makes only that granularity's period tables visible
- [ ] Check themes: with `page.emulate_media(color_scheme='dark')` the chart's `paper_bgcolor` is the dark chart surface and with `'light'` the light one; a file rendered with theme `light` stays light under a dark `color_scheme`
- [ ] In `.github/workflows/ci.yml`: change the `check` job's pytest to `-m 'not slow and not live and not browser'`; add a `browser` job like `check` (same pinned actions) that runs `uv sync --locked`, `uv run playwright install --with-deps chromium` and `uv run pytest -m browser -rs`
- [ ] Run the test here and record in Notes which Chromium it launched and that it passed

**Acceptance Criteria:**

- [ ] The test passes in this environment with no network access from the page
- [ ] The test fails if plotly.js is not inlined (check once by hand: render with the plotly.js `<script>` removed and see it fail, then restore; record in Notes)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest -m browser -rs src/tests/reports/test_html_browser.py` passes (not skipped)
- [ ] `pytest -m 'not browser' src/tests/reports/test_html.py` passes

**Notes:**

- Depends on Task 7 (the file under test is what the CLI writes; the test builds it through `render_html` directly)
- Key files: `src/tests/reports/test_html_browser.py`, `.github/workflows/ci.yml`
- Playwright for Python: [network routing](https://playwright.dev/python/docs/network#abort-requests), [`emulate_media`](https://playwright.dev/python/docs/api/class-page#page-emulate-media), [console events](https://playwright.dev/python/docs/api/class-page#page-event-console), [installing browsers in CI](https://playwright.dev/python/docs/ci)
- If the preinstalled Chromium is too old for the locked Playwright, stop and record the error rather than pinning an older Playwright.

---

## Task 9: README: the HTML report

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** shared user-guides rule (keep guides in sync with code); Command line (`--format html`, `--out`); Settings (`report.format`, `report.html_theme`, `report.out_dir`); review-2.md choice 16

**User Story:** As a wambatic user, I want the README to show how to make and share the HTML report, so that I do not have to read the spec to find the flags and settings.

**Subtasks:**

- [ ] Add an HTML report section to `README.md`: a first example (`wambatic report org:NAME --format html`), where the file goes (`--out`, `report.out_dir`, `report_filename`), the path printed on stdout, the granularity switch and `--by`'s role with html, themes (`report.html_theme`), that the file works offline and is several MB because plotly.js is inlined, and that the page's tables are the same as the terminal's
- [ ] Update the `--format` row and the `report.format`, `report.html_theme` and `report.out_dir` rows; add an `--out` row; remove "HTML report" from the not-built-yet list
- [ ] Mention the `browser` test marker in the README only if it already documents test markers; otherwise leave it to `pyproject.toml`
- [ ] Run each new example that needs no network against a cache built from the stats fixtures (`--no-fetch`) and check the output matches what the README says
- [ ] Keep counts out of the prose (shared counts-in-prose rule) and use British spelling

**Acceptance Criteria:**

- [ ] Every flag in `wambatic report --help` and every setting in `wambatic.settings` appears in the README (the same check as tasks-1.md Task 11; record the result in Notes)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 7
- Key files: `README.md`

---

## Task 10: Exports, layering and closing checks

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** Module location (layering; only `html.py` imports `plotly`); API; implementation order step 7 "Done when"; review-2.md decision 1 and choice 14

**Technical Goal:** Expose the step 7 names, enforce the new import rule, remove what the new modules duplicate, run every test this list can reach, and mark the step done.

**Subtasks:**

- [ ] In `src/wambatic/reports/__init__.py`, import and list in `__all__`: `Figure`, `HtmlReport`, `build_calendar`, `build_figures`, `build_range_figures`, `html_document`, `render_html`, `report_filename`, keeping the existing order convention
- [ ] Extend `src/tests/test_package.py`: every name in `wambatic.reports.__all__` resolves
- [ ] Extend `src/tests/test_layering.py`: a module other than `wambatic.reports.html` importing `plotly` is a violation (in `src/wambatic` only; tests may import it to validate), with a test like `test_detects_reports_importing_fetch_or_the_cli` for it
- [ ] Hoist anything the new modules duplicate to a single owner: grep the tree for each literal collection, constant and one-line helper `rows.py`, `figures.py`, `html.py` and the `cli.py` changes define (metric names and order, the subject text, number and hour formatting, partial labels, the unattributed login, `TOP_CONTRIBUTORS_SHOWN`), and import rather than copy, choosing the owner from the existing import graph (prefer `rows.py` or the stats modules, which every renderer already imports)
- [ ] Check the implementation order's "Done when" for step 7: offline with no request, all four granularities, the headless-browser smoke test (Task 8); record where each is shown in this task's Notes
- [ ] Run every test that imports a changed module directly or transitively: `pytest src/tests/reports src/tests/test_cli.py src/tests/test_package.py src/tests/test_layering.py`, and `pytest -m browser -rs src/tests/reports/test_html_browser.py`
- [ ] In `agents/specs/implementation-order.md`, set step 7's Status to `done: [tasks-2](../tasks/reports/tasks-2.md)`

**Acceptance Criteria:**

- [ ] `python -c 'import wambatic.reports, wambatic.cli'` works and `wambatic report --help` lists `--out` and `html`
- [ ] Every step 7 "Done when" item is met, or its gap is recorded in the task that owns it

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports src/tests/test_cli.py src/tests/test_package.py src/tests/test_layering.py` passes
- [ ] `pytest -m browser -rs src/tests/reports/test_html_browser.py` passes (not skipped)

**Notes:**

- Depends on Tasks 1 to 9
- The project has no affected-tests tool; the commands above name every test file that reaches a module this list changed (`wambatic.reports` is reached by the reports and CLI tests, `wambatic.cli` by the CLI tests, and the package and layering tests check the whole tree). No fetch or stats module changes, so their tests are not needed.
- The reports spec's `**Status:**` stays `proposed` (see the header).
- Key files: `src/wambatic/reports/__init__.py`, `src/tests/test_package.py`, `src/tests/test_layering.py`, `agents/specs/implementation-order.md`
