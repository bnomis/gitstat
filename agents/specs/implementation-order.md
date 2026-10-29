# Implementation order

**Version:** 1.3
**Status:** proposed
**Date:** 2026-10-29

The order in which gitstat is built, with what each step delivers, what it depends on and how to tell it is done. It sequences the components in the [system spec](system/spec.md) into steps that [taskdev](../../.agents/claude/skills/taskdev/SKILL.md) can break into tasks. Component detail stays in the component specs; this document only sequences them.

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
| 4 | Activity stats with bucketing | [stats](stats/spec.md) | 3 | planned: [tasks-1](../tasks/stats/tasks-1.md) |
| 5 | Terminal report and CLI | [reports](reports/spec.md) | 4 | not started |
| 6 | Flow data and stats (PRs, issues) | fetch-and-cache, stats | 3, 4 | not started |
| 7 | Static HTML report | [reports](reports/spec.md) | 5 | not started |
| 8 | Delivery data and stats (releases, Actions, DORA proxies) | fetch-and-cache, stats | 6 | not started |
| 9 | Local web app | [reports](reports/spec.md) | 7 | not started |

Steps 6 and 7 are independent and may be built in either order or in parallel once 5 is done.

## Step detail

### 1. Skeleton and settings

Deliver: `pyproject.toml` (Python 3.14, ruff, mypy, pytest, hypothesis, pre-commit config, `uv.lock`), `src/gitstat/` with `settings.py` (`load_settings` layering defaults, JSON file, flag overrides), loguru setup, `src/tests/` layout, and a CI workflow running ruff, mypy and pytest.
Done when: `pytest` passes with settings-layering tests, CI is green on an empty-feature PR, and the token is shown to be read only from the environment.

### 2. Fetch core

Deliver: `resolve_token`, the aiohttp transport `GitHubClient` (`__aenter__`/`__aexit__`) that `Fetcher` wraps in step 3, the GraphQL and REST request paths with ETag revalidation, `rateLimit` accounting, transient and secondary-limit backoff, the typed error classes except `CacheVersionError`, and token redaction in logs.
Done when: replayed fixtures cover 401, 404, primary and secondary rate limits and REST 202; an opt-in live test lists the repos of a small public account.

### 3. Cache and incremental sync (repos and commits)

Deliver: `Subject`, `Fetcher` wrapping the step 2 `GitHubClient`, the `fetch.workers` semaphore, the SQLite schema, `meta` identity and `CacheVersionError`, ETag storage, `sync_state` rows, `sync()` with `repos()` and `commits()` reading the cache, per-commit additions and deletions and merge flags, compare-based increments from the stored head, de-duplication, rewritten-history detection and atomic state advance, and `full_refresh` (the `--full-refresh` flag itself is step 5's CLI).
This is the highest-risk step; it proves the incremental design before anything depends on it.
Done when: a second run of the same fixture fetches nothing; an interrupted run resumes; a simulated force-push triggers a full refetch of that repo; and an opt-in live test's line totals match `stats/code_frequency` for a small repo.

### 4. Activity stats

Deliver: `Granularity`, `bucket_for` and `bucket_range` (ISO weeks, timezones, partial buckets), the stats errors, `Fetcher.provenance`, and `compute` for the `activity` group's commit metrics: commits, contributors, active days, lines added, deleted and net, per-repo and `by_author` breakdowns, and the top-contributors table. Groups and metrics not built yet are listed as `unavailable`; stars, forks, watchers and languages wait for step 8.
Done when: hypothesis tests show buckets partition any date range with no gaps or overlaps, and known-good fixture totals match by hand.

### 5. Terminal report and CLI

Deliver: `cli.main` with `report` and `cache` commands, `<target>` parsing, `--by`, `--since`, `--until`, `--tz`, `--format terminal|json`, `--no-fetch`, `--max-age`, and the single error-to-exit-status conversion.
Done when: `gitstat report repo:OWNER/NAME --by month` prints a correct report from a warm cache with no network, and every typed error maps to its documented exit status.

### 6. Flow data and stats

Deliver: `pull_requests()` and `issues()` with updated-at paging, the `flow` group (throughput, time to first review, merge and close, PR size).
Done when: incremental refresh updates a PR that changed and leaves unchanged ones untouched, and the full-refresh interval removes a deleted issue.

### 7. Static HTML report

Deliver: `figures.py`, the self-contained HTML renderer with the granularity switch, themes and provenance footer.
Done when: the file opens offline, shows all four granularities, and passes a headless-browser smoke test using the preinstalled Playwright.

### 8. Delivery data and stats

Deliver: `releases()`, `workflow_runs()`, `star_events()`, the `delivery` group, DORA proxies emitted only when configured, and the `activity` metrics step 4 left unavailable (stars, forks, watchers, languages; the fetch spec needs resources for forks, watchers and languages first).
Done when: unconfigured proxies are listed as `unavailable` with a reason, and in-progress runs are refreshed on the next sync.

### 9. Local web app

Deliver: FastAPI app with `/`, `/report`, `/api/stats`, `/api/progress`, loopback-only binding and `--allow-remote`.
Done when: a large-org fixture does not block the page, invalid parameters return 400, and a non-loopback bind without the flag refuses to start.

## Not in scope for this order

GitHub Enterprise Server, default-branch-only history changes, per-file line filtering and multi-timezone reports are listed as accepted limits in the system spec and have no step here.
