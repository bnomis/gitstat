# Implementation order

**Version:** 1.7
**Status:** proposed
**Date:** 2026-10-30

The order in which wambatic is built, with what each step delivers, what it depends on and how to tell it is done. It sequences the components in the [system spec](system/spec.md) into steps that [taskdev](../../.agents/claude/skills/taskdev/SKILL.md) can break into tasks. Component detail stays in the component specs; this document only sequences them.

## Principles

- **Vertical slices.** From step 4 on, every step ends with something runnable end to end, not a layer with nothing using it.
- **Cheapest risk first.** The riskiest unknowns are GitHub's rate limits, per-commit line counts and incremental sync correctness. They are tackled in steps 2 to 4, before any rendering work.
- **Tests first on fixtures.** Each step records small real API responses as fixtures once, then every later test replays them offline.
- **One step, one PR.** Each step is a branch and a PR that passes `ruff check`, `ruff format --check`, `pre-commit run --all-files` and the tests for the changed modules.
- **Dependencies are checked, not assumed.** Before a step adds a library, it checks maintenance status as the shared tools-and-libraries rule requires.

## Steps

| # | Step | Specs | Depends on | Status |
|---|------|-------|------------|--------|
| 1 | Skeleton and settings | [system](system/spec.md) | none | done |
| 2 | Fetch core: auth, aiohttp client, rate limits | [fetch-and-cache](fetch-and-cache/spec.md) | 1 | done: [tasks-1](../tasks/fetch-and-cache/tasks-1.md) |
| 3 | Cache and incremental sync for repos and commits | [fetch-and-cache](fetch-and-cache/spec.md) | 2 | done: [tasks-2](../tasks/fetch-and-cache/tasks-2.md) |
| 4 | Activity stats with bucketing | [stats](stats/spec.md) | 3 | done: [tasks-1](../tasks/stats/tasks-1.md) |
| 5 | Terminal report and CLI | [reports](reports/spec.md) | 4 | done: [tasks-1](../tasks/reports/tasks-1.md) |
| 6 | Flow data and stats (PRs, issues) | fetch-and-cache, stats | 3, 4 | done: [tasks-2](../tasks/stats/tasks-2.md) |
| 7 | Static HTML report | [reports](reports/spec.md) | 5 | done: [tasks-2](../tasks/reports/tasks-2.md) |
| 8 | Delivery data and stats (releases, Actions, DORA proxies) | fetch-and-cache, stats, reports | 6, 7 | done: [tasks-3](../tasks/stats/tasks-3.md) |
| 9 | Local web app | [reports](reports/spec.md) | 7 | not started |
| 10 | Popularity data and stats (stars, forks, watchers, languages) | fetch-and-cache, stats, reports | 7 | not specified |

Steps 6 and 7 are independent and may be built in either order or in parallel once 5 is done. Step 10 was split from step 8 on 2026-10-30 (stats review 3): its fetch resources are not specified yet, and the two together were more than one task list. Steps 9 and 10 are independent of each other.

## Step detail

### 1. Skeleton and settings

Deliver: `pyproject.toml` (Python 3.14, ruff, mypy, pytest, hypothesis, pre-commit config, `uv.lock`), `src/wambatic/` with `settings.py` (`load_settings` layering defaults, JSON file, flag overrides), loguru setup, `src/tests/` layout, and a CI workflow running ruff, mypy and pytest.
Done when: `pytest` passes with settings-layering tests, CI is green on an empty-feature PR, and the token is shown to be read only from the environment.

### 2. Fetch core

Deliver: `resolve_token`, the aiohttp transport `GitHubClient` (`__aenter__`/`__aexit__`) that `Fetcher` wraps in step 3, the GraphQL and REST request paths with ETag revalidation, `rateLimit` accounting, transient and secondary-limit backoff, the typed error classes except `CacheVersionError`, and token redaction in logs.
Done when: replayed fixtures cover 401, 404, primary and secondary rate limits and REST 202; an opt-in live test lists the repos of a small public account.

### 3. Cache and incremental sync (repos and commits)

Deliver: `Subject`, `Fetcher` wrapping the step 2 `GitHubClient`, the `fetch.workers` semaphore, the SQLite schema, `meta` identity and `CacheVersionError`, ETag storage, `sync_state` rows, `sync()` with `repos()` and `commits()` reading the cache, per-commit additions and deletions and merge flags, compare-based increments from the stored head, de-duplication, rewritten-history detection and atomic state advance, and `full_refresh` (the `--full-refresh` flag itself is step 5's CLI).
This is the highest-risk step; it proves the incremental design before anything depends on it.
Done when: a second run of the same fixture fetches nothing; an interrupted run resumes; a simulated force-push triggers a full refetch of that repo; and an opt-in live test's line totals match `stats/code_frequency` for a small repo.

### 4. Activity stats

Deliver: `Granularity`, `bucket_for` and `bucket_range` (ISO weeks, timezones, partial buckets), the stats errors, `Fetcher.provenance`, and `compute` for the `activity` group's commit metrics: commits, contributors, active days, lines added, deleted and net, per-repo and `by_author` breakdowns, and the top-contributors table. Groups and metrics not built yet are listed as `unavailable`; stars, forks, watchers and languages wait for step 10.
Done when: hypothesis tests show buckets partition any date range with no gaps or overlaps, and known-good fixture totals match by hand.

### 5. Terminal report and CLI

Deliver: the `rich` and `cappa` dependencies, `cli.main` with `report` and `cache` commands, `<target>` parsing (bare `NAME` through `Fetcher.owner_kind`), `--by`, `--since`, `--until`, `--groups`, `--by-author`, `--tz`, `--format terminal|json`, `--full-refresh`, `--no-fetch`, `--max-age`, `--ignore-cache-version`, `-v`/`-q`, the terminal renderer and JSON output, `BUILT_RESOURCES`, `inspect_cache` and `clear_cache`, the `wambatic` console script, a README user guide, and the single error-to-exit-status conversion. `--format html` and `--out` wait for step 7 and `serve` for step 9.
Done when: `wambatic report repo:OWNER/NAME --by month --no-fetch` (or with a `--max-age` the cache is younger than) prints a correct report from a warm cache with no network and no `GITHUB_TOKEN`, and every typed error maps to its documented exit status. Without either flag the report syncs first, since `fetch.max_age` defaults to zero.

### 6. Flow data and stats

Deliver: the `PullRequest` and `Issue` records and tables (cache schema 2), `pull_requests()` and `issues()` with updated-at paging from a `Date`-header watermark, the repo listing's newest pull request and issue update times so unchanged repos are skipped, `issues` and `pull_requests` in `BUILT_RESOURCES`, the `flow` group (throughput, time to first review, merge and close, PR size) in `compute`, the terminal's Flow by period and Flow times tables, and the README's flow section. Fetch spec 1.5, stats spec 1.2 and reports spec 1.3; the choices are in the [stats review 2](stats/review-2.md).
Done when: incremental refresh updates a PR that changed and leaves unchanged ones untouched, the full-refresh interval removes a deleted issue, a repo whose newest PR and issue are older than the watermark costs no per-repo request, and the default report (`activity,flow`) lists nothing as unavailable for `flow`.

### 7. Static HTML report

Deliver: the `plotly` dependency (used only for its bundled plotly.js) and Playwright for Python as a development dependency, the table rows moved from `terminal.py` to `rows.py`, `figures.py` (`Figure`, `build_figures`, `build_range_figures`, `build_calendar`, the palette), `html.py` and its templates (`HtmlReport`, `html_document`, `render_html`, `report_filename`) with the summary tiles, granularity switch, data tables, themes and provenance footer, `--format html` and `--out` with an atomic write, a `browser` CI job, and the README's HTML section. Reports spec 1.4; the choices are in the [reports review 2](reports/review-2.md).
Done when: the file opens offline with no network request, shows all four granularities, and passes a headless-browser smoke test (Playwright for Python with the preinstalled Chromium here, and Playwright's own Chromium in CI).

### 8. Delivery data and stats

Deliver: the `Release` and `WorkflowRun` records and tables, the `PullRequest` fields `labels` and `first_commit_at`, the listing's release probe and `sync_state.probe` (cache schema 3), `releases()` (full read when the probe changes) and `workflow_runs()` (REST, a free 304 when unchanged, in-progress runs re-read), `releases` and `workflow_runs` in `BUILT_RESOURCES`, the `delivery` group (Actions and release metrics, and the DORA proxies emitted only when their inputs exist), the terminal's Delivery by period and DORA proxies by period tables, the HTML page's delivery tiles, charts and tables, the release and run counts in `cache info`, and the README's delivery section. Fetch spec 1.6, stats spec 1.3 and reports spec 1.5; the choices are in the [stats review 3](stats/review-3.md).
Done when: unconfigured proxies are listed as `unavailable` with a reason, in-progress runs are refreshed on the next sync, an unchanged repo's workflow runs cost one 304 and its releases no request, and `--groups delivery` renders in the terminal, JSON and HTML formats.

### 10. Popularity data and stats

Deliver: fetch resources for stars (`star_events`), forks, watchers and languages, specified first (GitHub records when a star or a fork was made but not when someone started watching, so watchers can be a current count only; the counts and languages can come with the repo listing, the star and fork histories cost a request per 100 per repo), the `activity` metrics step 4 left unavailable, or a group of their own if the spec moves them there, and the languages chart (reports spec, Visualisation choices).
Done when: specified with its task list.

### 9. Local web app

Deliver: FastAPI app with `/`, `/report`, `/api/stats`, `/api/progress`, loopback-only binding and `--allow-remote`.
Done when: a large-org fixture does not block the page, invalid parameters return 400, and a non-loopback bind without the flag refuses to start.

## Not in scope for this order

GitHub Enterprise Server, default-branch-only history changes, per-file line filtering and multi-timezone reports are listed as accepted limits in the system spec and have no step here.
