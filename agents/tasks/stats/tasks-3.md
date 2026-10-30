# Tasks: Stats

**Spec:** `agents/specs/stats/spec.md`
**Created:** 2026-10-30
**Version:** 3

This list builds step 8 of the [implementation order](../../specs/implementation-order.md), "Delivery data and stats (releases, Actions, DORA proxies)": the `Release` and `WorkflowRun` records and their cache tables (schema 3), the pull request fields `labels` and `first_commit_at`, the release and workflow-run syncs, the `delivery` group in `compute` with its Actions and release metrics and the DORA proxies, the delivery sections of the terminal and the HTML page, and the README's delivery section. It is written against version 1.3 of the stats spec, 1.6 of the [fetch spec](../../specs/fetch-and-cache/spec.md) and 1.5 of the [reports spec](../../specs/reports/spec.md); the gaps and the choices made are in [review-3.md](../../specs/stats/review-3.md). There is no decision in that review; a choice flagged there changes the task it names before the list runs. Stars, forks, watchers and languages are not in this list: they moved to step 10, which is specified with its own list (review-3.md choice 1). The step 6 list, [tasks-2.md](tasks-2.md), built the pull request sync and the `flow` group this list is modelled on, and the step 7 list, [reports/tasks-2.md](../reports/tasks-2.md), the HTML page it extends.

## Spec coverage

| Spec section | Covered by |
|--------------|------------|
| Fetch: Module location, API records (`Repo` probe fields, `PullRequest.labels` and `first_commit_at`, `Release`, `WorkflowRun`, `SyncState.probe`) | Task 1 |
| Fetch: API `Cache` (`SCHEMA_VERSION` 3, release and run methods), `CacheInfo`; Implementation, Cache | Task 1 |
| Fetch: API `RestResponse.date` | Task 2 |
| Fetch: Incremental sync step 1 (release probe; runs never skipped) | Tasks 2, 3 and 4 |
| Fetch: Incremental sync step 2 (`PULL_REQUESTS` labels and first commit) | Task 2 |
| Fetch: Incremental sync step 2 (`releases`) and step 5 (full reads) | Task 3 |
| Fetch: Incremental sync step 2 (`workflow_runs`), step 3 (watermark) and step 5 | Task 4 |
| Fetch: API `BUILT_RESOURCES`, `Fetcher.releases`, `Fetcher.workflow_runs` | Tasks 3 and 4 |
| Fetch: `star_events` | step 10 |
| Fetch: Testing (hand-written step 8 responses) | Tasks 2 to 4 |
| Stats: API (`resources_for`, unit `minutes`) | Task 8 |
| Stats: Range, Reading the cache (delivery) | Task 8 |
| Stats: Groups not built yet (step 10 reasons) | Task 8 |
| Stats: Metric groups, delivery (Actions, releases) | Task 6 |
| Stats: Metric groups, delivery (DORA proxies) | Task 7 |
| Stats: Metric groups, activity (`stars`, `forks`, `watchers`, `languages`) | step 10 |
| Stats: Aggregation (user subject, no delivery breakdowns, series order) | Tasks 6 to 8 |
| Stats: Error handling (`EmptySubjectError` with delivery) | Task 8 |
| Stats: Settings (`deploy_workflow`, `failure_window`, `hotfix_labels`) | Tasks 7 and 12 |
| Stats: Module location (`delivery.py`) | Task 6 |
| Reports: `Figure.group` `'delivery'`; Static HTML (tiles, layout, charts) | Task 11 |
| Reports: Terminal items 3 and 8 to 11 | Task 9 |
| Reports: `cache info` counts | Task 10 |
| Reports: JSON output (unit `minutes` as a float) | Task 9 |
| System: Data flow step 2 | Task 8 |
| User guide (shared user-guides rule) | Task 12 |
| Implementation order step 8 "Done when" | Tasks 4, 7, 10 and 11; checked in Task 13 |

No spec's `**Status:**` changes in this list: the stats and fetch specs still have step 10's popularity data to build, and the reports spec has step 9's web app.

## Conventions for every task

- Async tests are plain `def test_...() -> None` functions whose body calls `asyncio.run(...)` on an inner coroutine; no pytest async plugin is added (as in the earlier lists).
- Every cache and file a test writes lives under pytest's `tmp_path`; the autouse `isolated_environment` fixture in `src/tests/conftest.py` already removes `GITHUB_TOKEN` and `WAMBATIC_CONFIG`. No test reaches the network: GitHub is the replay server (`tests.fixtures.fetch.server.ReplayServer`) through the existing `make_client`/`make_fetcher` fixtures.
- Hand-written GitHub responses carry a comment naming the documentation page their shape comes from (review-3.md, Automatic checks, lists the schema facts already checked), and are added to the re-record list in the module docstring of `src/tests/fixtures/fetch/responses.py`.
- Times are aware UTC `datetime`s everywhere below `compute`; the cache stores them with `wambatic.fetch.cache.to_text`, so text order is time order.
- The `delivery` aggregation is pure, like `activity` and `flow`: no I/O, records in, series and unavailable rows out.
- Messages never echo a token or a config value (system spec, Settings).
- The project has no affected-tests tool, so each task names its test files literally; Task 13 runs every test the list can reach.
- The local environment may lack the exact Python patch release `pyproject.toml` requires; if `uv sync` cannot find it, say so in the task's Notes and do what the step 5 list did (resolve with the patch release lowered for that one command, then put `pyproject.toml` and `uv.lock` back), never by committing a changed `requires-python`. This list adds no dependency.
- A choice in review-3.md that is flagged before a task runs changes that task first; a task never extends a choice to a case it does not name, and stops for the user instead.

---

## Task 1: Records and cache schema 3

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** fetch spec 1.6 (Module location; API: `Repo`, `PullRequest`, `Release`, `WorkflowRun`, `SyncState`, `Cache`, `SCHEMA_VERSION`, `CacheInfo`; Implementation, Cache); review-3.md choices 3, 4, 5, 8 and 9

**Technical Goal:** Give the cache somewhere to keep releases, workflow runs, pull request labels and first-commit times, and the release probe, so the sync tasks can write them and stats can read them.

**Subtasks:**

- [x] In `src/wambatic/fetch/base.py`, add the frozen, slotted `Release` and `WorkflowRun` dataclasses with the spec's fields and comments; add `labels: tuple[str, ...] = ()` and `first_commit_at: datetime.datetime | None = None` at the end of `PullRequest`; add `releases_count: int = 0` and `releases_updated_at: datetime.datetime | None = None` to `Repo` before `missing`; add `probe: str | None = None` at the end of `SyncState`
- [x] In `src/wambatic/fetch/cache.py`, set `SCHEMA_VERSION = 3`; add to `SCHEMA` the `releases` table (`repo`, `tag_name`, `created_at`, `published_at`, `is_prerelease`, primary key `(repo, tag_name)`) and the `workflow_runs` table (`repo`, `id`, `workflow_path`, `name`, `event`, `head_branch`, `status`, `conclusion`, `created_at`, `updated_at`, `run_started_at`, `run_attempt`, primary key `(repo, id)`, indexed on `(repo, created_at)` and `(repo, status)`); add the `pull_requests` columns `labels` (JSON array text, `'[]'` for none) and `first_commit_at`, the `repos` columns `releases_count` and `releases_updated_at`, and the `sync_state` column `probe`
- [x] Extend the row conversions and `upsert_repos`, `read_repos`, `sync_state`, the state write, `write_pull_requests` and `read_pull_requests` for the new fields; labels round-trip through `json.dumps`/`json.loads` as a tuple in GitHub's order
- [x] Add `write_releases` (one transaction: delete the repo's releases, insert these, write the state), `read_releases` (oldest `published_at` first, then `tag_name`), `write_workflow_runs` (as `write_commits`, upserting by `id`, also deleting the ids in `gone`), `read_workflow_runs` (`created_at >= since` when given, oldest first, then `id`) and `unfinished_runs` (ids whose `status` is not `completed`, ascending); each write raises `ValueError` when a record or the state belongs to another repo, before writing anything
- [x] Add `releases` and `workflow_runs` to `CacheInfo` and count them in `inspect_cache` (0 for an absent table)
- [x] Export `Release` and `WorkflowRun` from `wambatic.fetch` (`__init__.py` and `__all__`, keeping the existing order)
- [x] Tests in `src/tests/fetch/test_cache.py`: round trip of each new record and of a pull request with labels (including a non-ASCII label and an empty tuple) and `first_commit_at` `None`; `write_releases` replaces the repo's rows and leaves another repo's alone; `write_workflow_runs` with `replace=False` keeps an unlisted run, with `replace=True` removes it, and removes the ids in `gone` either way; `read_workflow_runs` with `since` keeps exactly the rows at or after it; `unfinished_runs` lists `queued` and `in_progress` runs and not `completed` ones; `SyncState.probe` and the `Repo` probe fields round-trip; a record for another repo raises `ValueError` and writes nothing (not even the state); a cache stamped with `schema_version` 2 raises `CacheVersionError` naming `schema_version` with `('2', '3')`; `inspect_cache` counts releases and runs, and gives 0 on a schema 2 file that lacks the tables
- [x] Test in `src/tests/fetch/test_base.py`: `Release` and `WorkflowRun` are frozen and slotted; a `PullRequest`, `Repo` or `SyncState` built without the new fields has their defaults
- [x] Check every test that pins `SCHEMA_VERSION` or `schema_version` reads `wambatic.fetch.cache.SCHEMA_VERSION` (step 6 made them do so; grep `src/tests` for `'2'` beside `schema_version` to be sure)

**Acceptance Criteria:**

- [x] A cache written before this task is refused with `CacheVersionError`, never read or migrated silently
- [x] Each write method is one transaction: a failing write leaves the rows and the state as they were (shown by the other-repo test)

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/fetch/test_cache.py src/tests/fetch/test_base.py src/tests/test_package.py src/tests/test_cli.py` passes

**Notes:**

- Depends on tasks-2.md (step 6) and reports/tasks-2.md (step 7), done
- Key files: `src/wambatic/fetch/base.py`, `src/wambatic/fetch/cache.py`, `src/wambatic/fetch/__init__.py`, `src/tests/fetch/test_cache.py`, `src/tests/fetch/test_base.py`
- `src/tests/test_cli.py` is in the Definition of Done because it reads the recorded `schema_version` and prints `cache info`.
- Reuse the step 6 write helpers (the upsert pattern, the other-repo check); Task 13 checks for duplication again.

---

## Task 2: Queries, parsing and `RestResponse.date`

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** fetch spec 1.6 (API: `RestResponse`; Implementation: Incremental sync steps 1 to 3; Testing); review-3.md choices 3 to 6

**Technical Goal:** Ask GitHub for the release probe, release pages, pull request labels and first commits, and parse those and the REST workflow runs into records, so the sync tasks only page and write.

**Subtasks:**

- [x] In `src/wambatic/fetch/queries.py`, add to `OWNER_REPOSITORIES` and `REPOSITORY` `releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) { totalCount nodes { updatedAt } }`; add to `PULL_REQUESTS` `labels(first: 20) { nodes { name } }` and `commits(first: 1) { nodes { commit { authoredDate } } }`; add `RELEASES` paging `repository(owner:, name:) { releases(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) { pageInfo { hasNextPage endCursor } nodes { tagName createdAt publishedAt isDraft isPrerelease } } }` with `rateLimit { cost remaining resetAt }`
- [x] In `src/wambatic/fetch/base.py`, extend `parse_repo` with `releases_count` and `releases_updated_at`, and add `release_probe(repo) -> str` giving `"<count> <updatedAt ISO UTC or none>"`; extend `parse_pull_request` with `labels` and `first_commit_at`; add `parse_release(repo, node) -> Release | None` (None for a draft or a node without `publishedAt`) and `parse_workflow_run(repo, node) -> WorkflowRun` from a REST run object, with the existing `mapping`/`text`/`integer`/`timestamp` helpers so a malformed shape raises `GraphQLError` (`MALFORMED`)
- [x] In `src/wambatic/fetch/client.py`, add `date: datetime.datetime | None = None` to `RestResponse`, filled from the `Date` header (parsed as `graphql_dated` does, sharing its parser) on 200 and 304; absent or unparseable leaves `None`
- [x] Hand-write the responses in `src/tests/fixtures/fetch/responses.py`: listing pages with the release probe, `RELEASES` pages (a draft, a prerelease, a release without `publishedAt`), `PULL_REQUESTS` pages with labels and first commits (including one with no commits), and REST workflow-run list pages and single runs (one `completed`/`success`, one `completed`/`failure`, one `in_progress` with `conclusion` null, one `queued` with `run_started_at` null); add each to the re-record list
- [x] Tests in `src/tests/fetch/test_queries.py`: every query text still selects `rateLimit`, and `RELEASES` orders by `CREATED_AT`; in `src/tests/fetch/test_base.py`: each parser on the fixtures, a draft giving `None`, labels in order, `first_commit_at` `None` for an empty commit list, `release_probe` text for a repo with and without releases, and a malformed run raising `GraphQLError`; in `src/tests/fetch/test_client.py`: `RestResponse.date` from a canned `Date` on a 200 and a 304, and `None` without one

**Acceptance Criteria:**

- [x] Every new or changed query text changes its `query:<NAME>` hash, so a schema 2 cache is refused for that reason as well
- [x] No draft release reaches a `Release`

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/fetch/test_queries.py src/tests/fetch/test_base.py src/tests/fetch/test_client.py src/tests/fetch/test_fetcher.py` passes

**Notes:**

- Depends on Task 1
- Key files: `src/wambatic/fetch/queries.py`, `src/wambatic/fetch/base.py`, `src/wambatic/fetch/client.py`, `src/tests/fixtures/fetch/responses.py`
- `src/tests/fetch/test_fetcher.py` is in the Definition of Done because its pull request and listing fixtures change shape.
- Field names and enum values were checked against `@octokit/graphql-schema` 15.26.1 and `@octokit/openapi` 24.0.0 (review-3.md, Automatic checks); `docs.github.com` was not reachable from the planning session.

---

## Task 3: Syncing releases

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** fetch spec 1.6 (API: `Fetcher.releases`; Implementation: Incremental sync steps 1, 2, 4 and 5); review-3.md choice 5

**Technical Goal:** Keep each repo's published releases current with a full read only when the listing's release probe changed or the full-refresh interval passed, and read them back from the cache.

**Subtasks:**

- [x] In `Fetcher.unchanged`, add the `releases` rule: a `sync_state` row exists, `full_read_due` is false and `state.probe == release_probe(repo)`
- [x] Add `sync_releases(repo, full_refresh) -> int`: page `RELEASES` to the end with `pages`, keep the non-`None` results of `parse_release`, and write them with `Cache.write_releases` and a state from `new_state` with `probe=release_probe(repo)`, `head_oid=None` and `full_synced_at` now (every read is full); log the reason at `info` as `sync_updated` does when the read is the first or forced by the interval or `--full-refresh`
- [x] Dispatch `releases` to it in `sync`'s `sync_one`; do not add `releases` to `BUILT_RESOURCES` yet (Task 4 adds both, so `sync` never runs half of step 8)
- [x] Add `Fetcher.releases(repo)` reading `Cache.read_releases`
- [x] Tests in `src/tests/fetch/test_fetcher.py`, calling `sync_releases`/`unchanged` directly or `sync` with `BUILT_RESOURCES` monkeypatched to include `releases`: a first sync stores the published releases and not the draft; a second sync with the same probe makes no `RELEASES` request; a probe whose count or `updatedAt` changed reads every page again and a release gone from GitHub leaves the cache; a passed `fetch.full_refresh_after` reads again with an equal probe; an interrupted read (an error on the second page) leaves the old rows and state; `Fetcher.releases` returns them oldest first

**Acceptance Criteria:**

- [x] A repo whose release probe is unchanged costs no per-repo request for releases (the implementation order's "Done when")
- [x] Publishing the newest draft is picked up on the next sync (shown by a probe whose `updatedAt` changed)

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/fetch/test_fetcher.py src/tests/fetch/test_cache.py` passes

**Notes:**

- Depends on Tasks 1 and 2
- Key files: `src/wambatic/fetch/base.py`, `src/tests/fetch/test_fetcher.py`
- The replay server counts requests per query; use that, as the step 6 skip tests do, to show "no request".

---

## Task 4: Syncing workflow runs, and `BUILT_RESOURCES`

**Status:** done
**Priority:** high
**Complexity:** large
**Spec Reference:** fetch spec 1.6 (API: `BUILT_RESOURCES`, `Fetcher.workflow_runs`; Implementation: Incremental sync steps 1 to 5); review-3.md choices 6 and 7

**Technical Goal:** Keep each repo's Actions runs current through the unfiltered REST list, at the cost of one free 304 when nothing changed, with every unfinished run re-read until it completes, then mark both step 8 resources built.

**Subtasks:**

- [x] Make `Fetcher.rest_cached` return the body and the response's `date` (on a 304, the body stored with the ETag and the 304's own `date`); update `compare`, its one caller, to take the body
- [x] Add `sync_workflow_runs(repo, full_refresh) -> int`: decide a full read as `sync_updated` does (no state, `--full-refresh`, or `full_read_due`); request `/repos/{owner}/{name}/actions/runs` with `per_page=100`, `exclude_pull_requests=true` and `page`, the first page through `rest_cached` and later pages through `client.rest_get`; take the watermark from the first response's `date`, raising `GraphQLError` (`MALFORMED`) when it is `None`; parse each run with `parse_workflow_run`; stop at the first run whose `created_at` is earlier than `watermark - fetch.overlap` unless the read is full; stop at an empty or short page
- [x] A `NotFoundError` on the first list page is read as no runs: write no runs and a state that keeps the previous watermark (none on a first sync), never one from the local clock; log it at `debug`
- [x] Then re-read each id in `Cache.unfinished_runs(repo)` that the pages did not return with `GET /repos/{owner}/{name}/actions/runs/{id}` (plain `rest_get`, no ETag); a `NotFoundError` adds the id to `gone`
- [x] Write the runs read and re-read, `gone`, and the state (`watermark` set, `head_oid` `None`, `full_synced_at` now on a full read and kept otherwise) with `Cache.write_workflow_runs(..., replace=full)`
- [x] Dispatch `workflow_runs` to it in `sync_one`; `Fetcher.unchanged` returns false for `workflow_runs` always
- [x] Add `Fetcher.workflow_runs(repo, since)` reading `Cache.read_workflow_runs`
- [x] Set `BUILT_RESOURCES` to `{'commits', 'issues', 'pull_requests', 'releases', 'workflow_runs'}` and `UNBUILT_RESOURCE_STEPS` to `{'star_events': 10}`
- [x] Tests in `src/tests/fetch/test_fetcher.py`: a first sync reads every page and stores every run; a second sync answered 304 writes nothing new, makes no further list request and costs no rate limit (the replay server's 304 carries no rate headers that would lower `remaining`); a second sync with a new run on page 1 stops at the cutoff and does not request page 2; an `in_progress` run cached earlier and not on the pages read is re-read and stored `completed`; a re-read 404 removes the run; a 404 on the list writes no runs and does not raise; `--full-refresh` reads every page and drops a run GitHub no longer lists; a list response without `Date` raises `GraphQLError`; an interrupted read keeps the old rows and watermark; `sync` with `{'releases', 'workflow_runs'}` reports rows for both and `repos_skipped` counts no repo (runs are never skipped); `sync` with `{'star_events'}` still raises `NotImplementedError` naming step 10
- [x] Update the test in `src/tests/fetch/test_fetcher.py` or `src/tests/test_package.py` that pins `BUILT_RESOURCES`

**Acceptance Criteria:**

- [x] In-progress runs are refreshed on the next sync (the implementation order's "Done when")
- [x] An unchanged repo's workflow runs cost one conditional request answered 304
- [x] No request carries a `created` filter

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/fetch/test_fetcher.py src/tests/fetch/test_client.py src/tests/fetch/test_cache.py src/tests/test_package.py src/tests/test_cli.py` passes

**Notes:**

- Depends on Tasks 1 to 3
- Key files: `src/wambatic/fetch/base.py`, `src/tests/fetch/test_fetcher.py`, `src/tests/fixtures/fetch/server.py`
- The 404-on-list subtask must not fall back to the local clock for a watermark (fetch spec, Incremental sync step 3); keeping the previous watermark is enough, because the next sync reads from it again.
- If the replay server cannot answer 304 to a matching `If-None-Match`, add that as an option on `Canned` rather than a second server; the compare tests may already use it.
- `src/tests/test_cli.py` is in the Definition of Done because `BUILT_RESOURCES` decides what `report` syncs.

---

## Task 5: Delivery fixture data for stats

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** stats spec 1.3 (Metric groups, delivery; Aggregation); review-3.md choices 10 to 16

**Technical Goal:** Give the delivery tests a small, hand-checked set of releases, runs and pull requests, with the expected value of every delivery series written out, so the aggregation is tested against arithmetic done by hand rather than against itself.

**Subtasks:**

- [x] In `src/tests/fixtures/stats.py`, add releases and workflow runs for `ALPHA`, `BETA` and `GAMMA` over the existing `SINCE` to `UNTIL` months, and give some existing pull requests `labels` (one `Hotfix`, to show case-insensitive matching) and `first_commit_at`; include a prerelease, two releases in one month of one repo, a release before `SINCE` (so an interval and a lead time reach back), runs of each conclusion the success rate counts and of `cancelled` and `skipped` (which it leaves out), an unfinished run, a run without `run_started_at`, a deploy workflow (`.github/workflows/deploy.yml`, name `Deploy`), and a run whose local date differs between UTC and `Europe/Berlin`
- [x] Write the expected series per month in UTC as module constants (`ORG_DELIVERY_BY_MONTH_UTC` and a release-based and a workflow-based `ORG_DORA_BY_MONTH_UTC`), each value with a comment showing the arithmetic, and the expected `unavailable` rows for a subject with no hotfix pull request
- [x] Tests in `src/tests/stats/test_fixtures.py`: the fixture records are internally consistent (each run's repo is in `REPOS`, `published_at >= created_at`, every completed run has a conclusion)

**Acceptance Criteria:**

- [x] Every delivery series name in the stats spec has an expected value in at least one month, and at least one month with no value for each percentile and ratio

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/stats/test_fixtures.py src/tests/stats/test_flow.py src/tests/stats/test_compute.py` passes

**Notes:**

- Depends on Task 1 (the records)
- Key files: `src/tests/fixtures/stats.py`, `src/tests/stats/test_fixtures.py`
- The flow and compute tests are in the Definition of Done because they read the same pull requests; adding labels must not change a flow value.

---

## Task 6: The pure `delivery` aggregation: Actions and releases

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** stats spec 1.3 (Module location; Metric groups, delivery: Actions and Releases; Aggregation); review-3.md choices 10, 11 and 17

**Technical Goal:** Turn runs and releases into the Actions and release series, each event placed by its own local date, as `flow.py` does for pull requests.

**Subtasks:**

- [x] Create `src/wambatic/stats/delivery.py` with `DELIVERY_METRICS` (name and unit in the spec's series order), the success and outcome conclusion sets, and `aggregate(runs, releases, pull_requests, buckets, tz, since, until, settings) -> tuple[list[Series], list[dict[str, str]]]`; this task fills the Actions and release series and returns no unavailable rows yet
- [x] `workflow_runs`, `workflow_success_rate`, `workflow_duration_p50`/`p90` (minutes) and `release_count`, `release_interval_p50` (per repo, `median_low` of whole days, bucketed by the later release) exactly as the spec defines them; counts are zero in an empty bucket, percentiles and ratios have no point there
- [x] Add `has_event_in_range(runs, releases, tz, since, until)` for `compute`'s empty check, as `flow.has_event_in_range` does
- [x] Use `flow.p90`, `flow.hours`-style helpers and `buckets.locate` rather than copies; if a helper must move to a shared owner (for example a percentile helper in `buckets.py` or a new private module), move it here and point `flow.py` at it
- [x] Tests in `src/tests/stats/test_delivery.py`: the Task 5 expectations for every Actions and release series by month in UTC and in `Europe/Berlin`; a bucket with only cancelled runs has no success rate; a run without `run_started_at` is left out of durations; a release before `since` gives an interval but no count; hypothesis: for any list of runs, `workflow_runs` summed over the buckets equals the runs whose local date is in range, and every success rate is within 0 to 1

**Acceptance Criteria:**

- [x] The JSON output's integer rule holds: `release_interval_p50` is always a whole number of days
- [x] `delivery.py` imports nothing from `wambatic.reports` or `wambatic.cli` (the layering test)

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/stats/test_delivery.py src/tests/stats/test_flow.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Task 5
- Key files: `src/wambatic/stats/delivery.py`, `src/tests/stats/test_delivery.py`
- Hypothesis is already a development dependency (shared tools-and-libraries rule).

---

## Task 7: DORA proxies

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** stats spec 1.3 (Metric groups, delivery: DORA proxies; Settings); review-3.md choices 12 to 15

**Technical Goal:** Add the deployment-based proxies and the hotfix-based ones to the delivery aggregation, each emitted only when its inputs exist in the cache and otherwise listed as unavailable with the reason the spec gives.

**Subtasks:**

- [x] In `delivery.py`, build the deployments per repository: with `settings.deploy_workflow`, completed `success` runs whose `workflow_path` file name or `name` equals it, at `updated_at`; without it, non-prerelease releases at `published_at`
- [x] `deployments`, `lead_time_p50`/`p90` (first commit, or `created_at`, to the first deployment of the same repo at or after `merged_at`, by the deployment's local date), `change_failure_rate` (hotfix pull request opened after the deployment and within `settings.failure_window`; labels compared with `casefold`) and `time_to_restore_p50`/`p90` (hotfix `created_at` to `merged_at`, by merge date), as the spec defines them
- [x] Return an unavailable row for each proxy that is not emitted, with the spec's reasons: no deployments (worded for releases or for the deploy workflow), and no hotfix pull request (naming `stats.hotfix_labels`); proxy series that are not emitted are left out, never empty
- [x] Tests in `src/tests/stats/test_delivery.py`: the Task 5 DORA expectations with releases as deployments and with `deploy_workflow='deploy.yml'` and with `deploy_workflow='Deploy'` (the same result); a prerelease is not a deployment; a pull request merged after the last deployment has no lead time; a deployment whose window reaches past `until` counts as not failed; with no hotfix pull request only `deployments` and the lead time are emitted and the rows name the change failure rate and time to restore; with no releases and no `deploy_workflow` no proxy is emitted and the reason says so; series order matches the spec with any subset of proxies

**Acceptance Criteria:**

- [x] Unconfigured proxies are listed as `unavailable` with a reason (the implementation order's "Done when")
- [x] No proxy is emitted as a series of zeros for lack of input

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/stats/test_delivery.py` passes

**Notes:**

- Depends on Task 6
- Key files: `src/wambatic/stats/delivery.py`, `src/tests/stats/test_delivery.py`
- DORA's own definitions, for the README in Task 12: [DORA's four keys](https://dora.dev/guides/dora-metrics-four-keys/).

---

## Task 8: `delivery` in `compute`

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** stats spec 1.3 (API: `resources_for`, `Series.unit`; Error handling; Range; Reading the cache; Groups not built yet; Aggregation: user subject, series order); system spec 1.5 Data flow step 2; review-3.md choices 1, 2, 16 and 18

**Technical Goal:** Read releases, runs and, when a proxy needs them, pull requests from the cache, feed them to the delivery aggregation, and fold its series and unavailable rows into the result.

**Subtasks:**

- [x] In `src/wambatic/stats/compute.py`, set `RESOURCES_BY_GROUP['delivery']` to `{'pull_requests', 'releases', 'workflow_runs'}`, `BUILT_GROUPS` to all three groups and `UNBUILT_GROUP_STEPS` to empty (keep the mechanism for step 10); change the `UNBUILT_ACTIVITY_METRICS` reasons to name step 10
- [x] Add `read_delivery`: every release; runs from a day before `since` (all when `since` is `None` or `stats.deploy_workflow` is set); every pull request only when a proxy needs them (always, since time to restore needs no deployments: read them once per repo); no author filter for a user subject
- [x] Resolve a `None` `since` from the earliest record of every requested built group, counting releases and runs and not the pull requests read only for delivery; raise `EmptySubjectError` only when no requested group has an event in range, using `delivery.has_event_in_range`
- [x] Place the delivery series after the flow series and before the breakdowns; append its unavailable rows after the group and activity rows
- [x] Update `src/wambatic/stats/base.py` only if a unit list or a comment there names the units (add `minutes`)
- [x] Tests in `src/tests/stats/test_compute.py`: `resources_for` for each group; `compute` with `groups={'delivery'}` on the Task 5 fixtures gives the expected series and `since`; `groups={'activity', 'flow', 'delivery'}` orders the series as the spec says; a user subject's delivery counts runs and releases of the user's repos whatever their author; a delivery-only request with records outside the range only raises `EmptySubjectError`; a request including `activity` lists `stars`, `forks`, `watchers` and `languages` as unavailable naming step 10 and lists `delivery` no longer; provenance has `fetched_at:releases`, `fetched_at:workflow_runs` and `fetched_at:pull_requests` for a delivery request

**Acceptance Criteria:**

- [x] `compute` never syncs and makes no request (the fetcher in the tests has no client entered)
- [x] The default request (`activity,flow`) gives the same series as before this list

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/stats/test_compute.py src/tests/stats/test_delivery.py src/tests/test_cli.py` passes

**Notes:**

- Depends on Tasks 4 and 7
- Key files: `src/wambatic/stats/compute.py`, `src/tests/stats/test_compute.py`
- `src/tests/test_cli.py` is in the Definition of Done because it checks the default report's unavailable rows.

---

## Task 9: Terminal delivery sections and JSON

**Status:** done
**Priority:** medium
**Complexity:** medium
**Spec Reference:** reports spec 1.5 (Terminal items 3 and 8 to 11; JSON output); review-3.md choice 19

**User Story:** As a maintainer, I want the terminal report to show my Actions runs, releases and DORA proxies by period, so that I can see how often and how reliably the project ships without opening the HTML page.

**Subtasks:**

- [x] In `src/wambatic/reports/rows.py`, add `has_delivery`, `has_dora`, the delivery metric tuples (imported from `wambatic.stats.delivery`, not copied), `delivery_table` and `dora_table` (only the columns of the emitted proxies), each with the `Total` row the spec gives; extend `TREND_METRICS` with `workflow_runs`, `release_count` and `deployments`
- [x] In `src/wambatic/reports/terminal.py`, render the two tables after flow with their captions; extend `format_cell` for minutes and days (minutes one decimal place) and for ratios as percentages with one decimal place (`87.5%`); renumbered Unavailable and provenance stay last
- [x] Check `result_to_dict` writes `minutes` and `ratio` values as floats and `release_interval_p50` (`days`) as an integer; add a test if none covers a new unit
- [x] Tests in `src/tests/reports/test_rows.py` and `src/tests/reports/test_terminal.py`: the delivery and DORA rows from a hand-built result, the `Total` rows, `-` for no value, percentages, a result with only some proxies, `--groups delivery` printing no activity or flow table, and trend lines for the three delivery counts and none for ratios; in `src/tests/reports/test_base.py`: the JSON types per unit

**Acceptance Criteria:**

- [x] `--groups delivery` renders in the terminal and JSON formats (half of the implementation order's last "Done when" item; Task 11 has HTML)

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/reports/test_rows.py src/tests/reports/test_terminal.py src/tests/reports/test_base.py` passes

**Notes:**

- Depends on Task 8
- Key files: `src/wambatic/reports/rows.py`, `src/wambatic/reports/terminal.py`, `src/tests/fixtures/reports.py`

---

## Task 10: CLI: `cache info` and a delivery report end to end

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** reports spec 1.5 (`cache info`; Running `report` step 5); fetch spec 1.6 (`CacheInfo`); review-3.md choice 9

**Technical Goal:** Show the new counts in `cache info`, and prove `report --groups delivery` syncs the three resources and renders from a replayed GitHub.

**Subtasks:**

- [x] In `src/wambatic/cli.py`, add `releases` and `workflow runs` lines to `cache info` after `issues`
- [x] Check the sync log line names `releases` and `workflow_runs` (it is built from `rows_written`; change nothing if it does)
- [x] Tests in `src/tests/test_cli.py`: `cache info` prints the release and run counts and 0 for a schema 2 file; `report repo:OWNER/NAME --groups delivery` against the replay server syncs `pull_requests`, `releases` and `workflow_runs`, logs their rows, and prints the Delivery by period table; the same with `--no-fetch` on the warm cache makes no request; `--format json --groups delivery` gives the delivery series

**Acceptance Criteria:**

- [x] A second `report --groups delivery` against an unchanged replayed repo makes one workflow-run request answered 304 and no release request (the implementation order's "Done when")

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 9
- Key files: `src/wambatic/cli.py`, `src/tests/test_cli.py`

---

## Task 11: HTML delivery section

**Status:** done
**Priority:** medium
**Complexity:** medium
**Spec Reference:** reports spec 1.5 (API `Figure.group`; Static HTML: layout items 2, 5 to 7, charts, testing); review-3.md choice 20

**User Story:** As a maintainer, I want the HTML report to chart my runs, releases and DORA proxies beside activity and flow, so that I can share one page that shows how the project ships.

**Subtasks:**

- [x] In `src/wambatic/reports/figures.py`, widen `Figure.group` (and the internal `Chart.group`) to include `'delivery'`, and add the delivery charts in the spec's order to `CHARTS`: bars for runs, releases and deployments; lines for the success and change failure rates as 0 to 100 per cent on a fixed axis; p50 and p90 lines for durations (minutes), lead time and time to restore (hours); a p50 line for the release interval (days); a proxy's chart only when its series is present
- [x] In `src/wambatic/reports/html.py`, add the delivery tiles, the Delivery section with its proxies line, and the two period tables per granularity from `rows.py`
- [x] Tests in `src/tests/reports/test_figures.py`: every delivery figure validates with `plotly.graph_objects.Figure`, ratios are multiplied by 100, a result without proxies has no proxy chart; in `src/tests/reports/test_html.py`: the tiles and section appear only with delivery series, the tables match `rows.py`; extend `src/tests/reports/test_html_browser.py` with a delivery report that renders every chart with no request, console error or page error

**Acceptance Criteria:**

- [x] `--groups delivery` renders in the HTML format (the rest of the implementation order's last "Done when" item)
- [x] The page still makes no network request

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/reports/test_figures.py src/tests/reports/test_html.py src/tests/reports/test_html_browser.py` passes

**Notes:**

- Depends on Task 9
- Key files: `src/wambatic/reports/figures.py`, `src/wambatic/reports/html.py`, `src/wambatic/reports/templates/`
- As the step 7 list found, build the report fixtures before launching the browser in the browser test: Playwright's sync API breaks `asyncio.run` in the same test.
- No chart has more than three series, so the palette's three categorical slots still suffice.

---

## Task 12: README

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** shared user-guides rule (keep guides in sync with code); reports spec 1.5 Terminal and Static HTML; stats spec 1.3 delivery and Settings; fetch spec 1.6 Cache (schema 3); review-3.md choices 6, 7, 10 to 16

**User Story:** As a wambatic user, I want the README to say what each delivery number measures, which are proxies and what they need, so that I know how far to trust a lead time or a change failure rate.

**Subtasks:**

- [x] In `README.md`: a Delivery section after Flow saying what each Actions and release metric counts and by which date, that durations are minutes and approximate; a DORA proxies subsection saying what a deployment is with and without `stats.deploy_workflow`, how lead time, change failure rate and time to restore are measured, that each appears only when its inputs exist and otherwise is listed under Unavailable, with a link to [DORA's four keys](https://dora.dev/guides/dora-metrics-four-keys/)
- [x] `--groups` no longer says `delivery` is not built; the `stats.deploy_workflow`, `stats.failure_window` and `stats.hotfix_labels` rows match the stats spec's Settings table; the Unavailable text names step 10's metrics only
- [x] The cache section says a cache from an earlier wambatic is refused once after this upgrade, and `cache info` lists release and run counts; the first sync with `--groups delivery` reads every workflow run, about one request per 100 runs per repository, and later syncs cost a free conditional request per repository
- [x] Check the token paragraph covers Actions on a private repository (`repo` scope; change nothing if it already says so)
- [x] Add a Common workflows example: `wambatic report repo:OWNER/NAME --groups delivery`
- [x] Run every README example that needs no network against a cache built from the stats fixtures, or with `--help`, and check its output matches the README
- [x] Keep counts out of the prose (shared counts-in-prose rule) and use British spelling

**Acceptance Criteria:**

- [x] Every delivery metric name the JSON output carries appears in the README
- [x] No sentence says the delivery group is not built

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Tasks 10 and 11
- Key files: `README.md`

---

## Task 13: Exports, layering and closing checks

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** fetch spec 1.6 API; stats spec 1.3 Module location; system spec Architecture (layering); implementation order step 8 "Done when"

**Technical Goal:** Expose the step 8 names, keep the layering enforced, remove what the new code duplicated, run every test the list can reach, and mark the step done.

**Subtasks:**

- [x] Check `wambatic.fetch.__all__` has `Release` and `WorkflowRun` (Task 1); `wambatic.stats` needs no new export (`delivery` is internal, as `flow` is)
- [x] Extend `src/tests/test_package.py`: `wambatic.fetch.Release` and `wambatic.fetch.WorkflowRun` resolve, and `BUILT_RESOURCES` contains `releases` and `workflow_runs`
- [x] Check `src/tests/test_layering.py` covers `wambatic.stats.delivery` (it scans every module; confirm with a run, and add a case only if it does not)
- [x] Hoist anything the new modules duplicate to a single owner: grep the tree for each literal collection, constant and one-line helper that `delivery.py`, the release and run cache methods, the parse functions, the new period tables, the new charts and the test fixtures define (the percentile and hours helpers, bucket location, record-to-row conversion, the upsert SQL pattern, the full-read decision shared by `sync_updated`, `sync_releases` and `sync_workflow_runs`, the period-table construction, metric name tuples), and import rather than copy, choosing the owner from the existing import graph and preferring a module the consumer already imports
- [x] Check the implementation order's "Done when" for step 8 and record in this task's Notes the test that shows each item: unconfigured proxies unavailable with a reason (Task 7), in-progress runs refreshed (Task 4), an unchanged repo costing one 304 and no release request (Tasks 3, 4 and 10), and `--groups delivery` in the terminal, JSON and HTML formats (Tasks 9 to 11)
- [x] Run every test that imports a changed module directly or transitively: `pytest src/tests/fetch src/tests/stats src/tests/reports src/tests/test_cli.py src/tests/test_package.py src/tests/test_layering.py`
- [x] In `agents/specs/implementation-order.md`, set step 8's Status to `done: [tasks-3](../tasks/stats/tasks-3.md)`

**Acceptance Criteria:**

- [x] Every step 8 "Done when" item is met, or its gap is recorded in the task that owns it
- [x] No new duplication between `delivery.py` and `flow.py`, or between the release and run code and the pull request code in `cache.py` and `base.py`

**Definition of Done:**

- [x] `source bin/activate.sh` succeeds
- [x] `ruff check` passes
- [x] `ruff format --check` passes
- [x] `mypy src` passes
- [x] `pre-commit run --all-files` passes
- [x] `pytest src/tests/fetch src/tests/stats src/tests/reports src/tests/test_cli.py src/tests/test_package.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Tasks 1 to 12
- The project has no affected-tests tool; the command above names every test file that reaches a module this list changed (`wambatic.fetch` is reached by the fetch, stats, reports and CLI tests, `wambatic.stats` by the stats, reports and CLI tests, `wambatic.reports` and `wambatic.cli` by the reports and CLI tests, and the package and layering tests check the whole tree).
- `src/tests/fetch/test_live.py` needs a working `GITHUB_TOKEN` and gets a 401 in cloud sessions, as on `main`; CI's `live` job runs it. Record that here if it is the only failure.
- No spec's `**Status:**` changes (see the header).
- Key files: `src/tests/test_package.py`, `src/tests/test_layering.py`, `agents/specs/implementation-order.md`
- The tests that show each of step 8's "Done when" items:
  - unconfigured proxies are listed as unavailable with a reason: `test_with_no_releases_and_no_deploy_workflow_no_proxy_is_emitted_and_the_reasons_say_why` in `src/tests/stats/test_delivery.py`, and the delivery gap rows in `src/tests/stats/test_compute.py`;
  - in-progress runs are refreshed on the next sync: `test_an_unfinished_run_not_on_the_pages_read_is_read_again_by_id_and_completes` in `src/tests/fetch/test_fetcher.py`;
  - an unchanged repository's workflow runs cost one 304 and its releases no request: `test_an_unchanged_second_run_sync_is_one_conditional_request_answered_304` in `src/tests/fetch/test_fetcher.py` and `test_a_second_delivery_report_costs_one_run_request_answered_304_and_no_release_request` in `src/tests/test_cli.py`;
  - `--groups delivery` renders in the terminal, JSON and HTML formats: `test_a_delivery_only_result_prints_the_delivery_tables_and_trends_but_no_other_group` in `src/tests/reports/test_terminal.py`, `test_a_json_delivery_report_has_the_delivery_series` and `test_html_of_the_delivery_group_alone_has_the_delivery_section_and_no_other` in `src/tests/test_cli.py`, and `test_a_delivery_report_draws_every_chart_with_no_request_or_error` in `src/tests/reports/test_html_browser.py`.
- Hoisted on 2026-10-30: the one-day constant to `wambatic.stats.buckets` and the minutes helper to `wambatic.stats.percentile`, beside the hours helper. The full-read decision is shared by `sync_updated`, `sync_releases` and `sync_workflow_runs` through `full_read_reason` and `plan_full_read` in `src/wambatic/fetch/base.py`.
- `src/tests/fetch/test_live.py` was not run in the cloud session (no working token), as on `main`; CI's `live` job runs it.
