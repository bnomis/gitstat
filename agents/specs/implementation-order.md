# Implementation order

**Version:** 1.0
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

| # | Step | Specs | Depends on |
|---|------|-------|------------|
| 1 | Skeleton and settings | [system](system/spec.md) | none |
| 2 | Fetch core: auth, aiohttp client, rate limits | [fetch-and-cache](fetch-and-cache/spec.md) | 1 |
| 3 | Cache and incremental sync for repos and commits | [fetch-and-cache](fetch-and-cache/spec.md) | 2 |
| 4 | Activity stats with bucketing | [stats](stats/spec.md) | 3 |
| 5 | Terminal report and CLI | [reports](reports/spec.md) | 4 |
| 6 | Flow data and stats (PRs, issues) | fetch-and-cache, stats | 3, 4 |
| 7 | Static HTML report | [reports](reports/spec.md) | 5 |
| 8 | Delivery data and stats (releases, Actions, DORA proxies) | fetch-and-cache, stats | 6 |
| 9 | Local web app | [reports](reports/spec.md) | 7 |

Steps 6 and 7 are independent and may be built in either order or in parallel once 5 is done.

## Step detail

### 1. Skeleton and settings

Deliver: `pyproject.toml` (Python 3.14, ruff, mypy, pytest, hypothesis, pre-commit config, `uv.lock`), `src/gitstat/` with `settings.py` (`load_settings` layering defaults, TOML file, flag overrides), loguru setup, `src/tests/` layout, and a CI workflow running ruff, mypy and pytest.
Done when: `pytest` passes with settings-layering tests, CI is green on an empty-feature PR, and the token is shown to be read only from the environment.

### 2. Fetch core

Deliver: `resolve_token`, the aiohttp `Fetcher` shell (`__aenter__`/`__aexit__`), the GraphQL and REST request paths, `rateLimit` accounting, secondary-limit backoff, the typed error classes, and token redaction in logs.
Done when: replayed fixtures cover 401, 404, primary and secondary rate limits and REST 202; an opt-in live test lists the repos of a small public account.

### 3. Cache and incremental sync (repos and commits)

Deliver: the SQLite schema, `meta` identity and `CacheVersionError`, `sync_state` watermarks, `repos()` and `commits()` with per-commit additions and deletions, overlap, de-duplication, rewritten-history detection and atomic watermark advance, and `--full-refresh`.
This is the highest-risk step; it proves the incremental design before anything depends on it.
Done when: a second run of the same fixture fetches nothing; an interrupted run resumes; a simulated force-push triggers a full refetch of that repo; and an opt-in live test's line totals match `stats/code_frequency` for a small repo.

### 4. Activity stats

Deliver: `Granularity`, `bucket_for` (ISO weeks, timezones, partial buckets), `compute` for the `activity` group including lines added, deleted and net and `by_author`.
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

Deliver: `releases()`, `workflow_runs()`, `star_events()`, the `delivery` group, and DORA proxies emitted only when configured.
Done when: unconfigured proxies are listed as `unavailable` with a reason, and in-progress runs are refreshed on the next sync.

### 9. Local web app

Deliver: FastAPI app with `/`, `/report`, `/api/stats`, `/api/progress`, loopback-only binding and `--allow-remote`.
Done when: a large-org fixture does not block the page, invalid parameters return 400, and a non-loopback bind without the flag refuses to start.

## Not in scope for this order

GitHub Enterprise Server, default-branch-only history changes, per-file line filtering and multi-timezone reports are listed as accepted limits in the system spec and have no step here.
