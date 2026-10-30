# Tasks: Stats

**Spec:** `agents/specs/stats/spec.md`
**Created:** 2026-10-30
**Version:** 4

This list builds step 10 of the [implementation order](../../specs/implementation-order.md), "Popularity data and stats (stars, forks, watchers, languages)", the last step of that order: the `StarEvent` and `Fork` records and their cache tables (schema 4), the listing's star, fork and watcher counts and language sizes, the star and fork syncs with their probes, the `popularity` group in `compute` with its four series and two tables, the popularity sections of the terminal and the HTML page (the languages chart among them), and the README's popularity section. It is written against version 1.4 of the stats spec, 1.8 of the [fetch spec](../../specs/fetch-and-cache/spec.md) and 1.7 of the [reports spec](../../specs/reports/spec.md); the gaps and the choices made are in [review-4.md](../../specs/stats/review-4.md), whose review page is linked in its header.

That review has one decision, where the four metrics live (review-4.md decision 1). This list follows its recommended option A, a new `popularity` group asked for with `--groups`. If the answer recorded in review-4.md's Answers section is another option, Tasks 7 to 11 change before they run: with option B the four stay `activity` metrics and no group is added; with option C the default groups become `activity,flow,popularity`. A task that finds no answer recorded there runs as written. A choice flagged there changes the task it names before the list runs.

The step 8 list, [tasks-3.md](tasks-3.md), built the release and workflow-run syncs and the `delivery` group this list is modelled on: the star and fork syncs parallel the release probe and the pull request incremental read, and `popularity.py` parallels `delivery.py`. Task 12 has the deduplication subtask for that.

## Spec coverage

| Spec section | Covered by |
|--------------|------------|
| Fetch: Module location, API records (`Repo` popularity fields, `StarEvent`, `Fork`, `SyncState.probe` comment) | Task 1 |
| Fetch: API `Cache` (`SCHEMA_VERSION` 4, star and fork methods), `CacheInfo`; Implementation, Cache | Task 1 |
| Fetch: Incremental sync step 1 (listing counts, languages, star and fork probes) | Tasks 2, 3 and 4 |
| Fetch: Incremental sync step 2 (`star_events`), step 3 (watermark) and step 5 (full reads, falling count) | Task 3 |
| Fetch: Incremental sync step 2 (`forks`), step 3 and step 5 | Task 4 |
| Fetch: Incremental sync step 2 (watchers and languages have no resource) | Task 2 |
| Fetch: API `RESOURCES`, `BUILT_RESOURCES`, `Fetcher.star_events`, `Fetcher.forks` | Tasks 3 and 4 |
| Fetch: Testing (hand-written step 10 responses; live test) | Tasks 2 to 4 |
| Stats: API (`GROUPS`, `resources_for`, `StatsResult.tables`) | Task 7 |
| Stats: Module location (`popularity.py`) | Task 6 |
| Stats: Metric groups, popularity (series, `popularity` and `languages` tables, series order) | Task 6 |
| Stats: Metric groups, activity (the four leave it) and Groups not built yet | Task 7 |
| Stats: Range, Reading the cache (popularity) | Task 7 |
| Stats: Error handling (`EmptySubjectError` with popularity) | Task 7 |
| Stats: Aggregation (user subject, no popularity breakdowns, series order) | Tasks 6 and 7 |
| Reports: Command line (`--groups` help, web `groups` description, form hint) | Task 8 |
| Reports: Terminal items 3 and 10 to 14; JSON output | Task 8 |
| Reports: `cache info` counts | Task 9 |
| Reports: `Figure.group` `'popularity'`; Static HTML (tiles, layout item 6, charts, Languages chart); Visualisation choices | Task 10 |
| System: Architecture records, Data flow step 2 | Task 7 |
| User guide (shared user-guides rule) | Task 11 |
| Implementation order step 10 "Done when" | Tasks 3, 4, 7 and 8 to 10; checked in Task 12 |
| Every spec's `**Status:**` (step 10 is the last step) | Task 12 |

## Conventions for every task

- Async tests are plain `def test_...() -> None` functions whose body calls `asyncio.run(...)` on an inner coroutine; no pytest async plugin is added (as in the earlier lists).
- Every cache and file a test writes lives under pytest's `tmp_path`; the autouse `isolated_environment` fixture in `src/tests/conftest.py` already removes `GITHUB_TOKEN` and `WAMBATIC_CONFIG`. No test reaches the network: GitHub is the replay server (`tests.fixtures.fetch.server.ReplayServer`) through the existing `make_client`/`make_fetcher` fixtures.
- Hand-written GitHub responses carry a comment naming the documentation page their shape comes from (review-4.md, Automatic checks, lists the schema facts already checked), and are added to the re-record list in the module docstring of `src/tests/fixtures/fetch/responses.py`.
- Times are aware UTC `datetime`s everywhere below `compute`; the cache stores them with `wambatic.fetch.cache.to_text`, so text order is time order.
- The `popularity` aggregation is pure, like `activity`, `flow` and `delivery`: no I/O, records and repos in, series and tables out.
- No stargazer login is stored or logged: a star is keyed by the user's node id (review-4.md choice 4). Messages never echo a token or a config value (system spec, Settings).
- The project has no affected-tests tool, so each task names its test files literally (the touched test files and the changed modules' own tests); Task 12 runs every test the list can reach.
- `source bin/activate.sh` puts the project's `.venv/bin` on `PATH`, `pre-commit` among it. The local environment may lack the exact Python patch release `pyproject.toml` requires; if `uv sync` cannot find it, say so in the task's Notes and do what the step 5 list did (resolve with the patch release lowered for that one command, then put `pyproject.toml` and `uv.lock` back), never by committing a changed `requires-python`. This list adds no dependency.
- A task never extends a choice in review-4.md to a case it does not name, and stops for the user instead.

---

## Task 1: Records and cache schema 4

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** fetch spec 1.8 (Module location; API: `RESOURCES`, `Repo`, `StarEvent`, `Fork`, `SyncState`, `Cache`, `SCHEMA_VERSION`, `CacheInfo`; Implementation, Cache); review-4.md choices 1 to 4 and 9

**Technical Goal:** Give the cache somewhere to keep stargazers, forks, and each repository's counts and languages, so the sync tasks can write them and stats can read them.

**Subtasks:**

- [ ] In `src/wambatic/fetch/base.py`, add the frozen, slotted `StarEvent` (`repo`, `user_id: str`, `starred_at`) and `Fork` (`repo`, `id: int`, `created_at`) dataclasses with the spec's comments; add `stargazer_count: int = 0`, `fork_count: int = 0`, `watcher_count: int = 0`, `languages: tuple[tuple[str, int], ...] = ()` and `languages_size: int = 0` to `Repo` before `missing`; add `'forks'` to `RESOURCES` (leave `BUILT_RESOURCES` for Task 4) and `'forks': 10` to `UNBUILT_RESOURCE_STEPS`; update the `SyncState.probe` comment
- [ ] In `src/wambatic/fetch/cache.py`, set `SCHEMA_VERSION = 4`; add to `SCHEMA` the `star_events` table (`repo`, `user_id`, `starred_at`, primary key `(repo, user_id)`, indexed on `(repo, starred_at)`) and the `forks` table (`repo`, `id`, `created_at`, primary key `(repo, id)`, indexed on `(repo, created_at)`); add the `repos` columns `stargazer_count`, `fork_count`, `watcher_count`, `languages` (JSON array of `[name, bytes]` pairs, `'[]'` for none) and `languages_size`
- [ ] Extend the repo row conversions, `upsert_repos` and `read_repos` for the new fields; languages round-trip through `json.dumps`/`json.loads` as a tuple of `(str, int)` tuples in the stored order
- [ ] Add `write_star_events` and `write_forks` (as `write_commits`: one transaction, with `replace` deleting the repo's rows first, upserting by `user_id` or `id`, writing the state), and `read_star_events` (oldest `starred_at` first, then `user_id`) and `read_forks` (oldest `created_at` first, then `id`); each write raises `ValueError` when a record or the state belongs to another repo, before writing anything
- [ ] Add `star_events` and `forks` to `CacheInfo` and count them in `inspect_cache` (0 for an absent table)
- [ ] Export `StarEvent` and `Fork` from `wambatic.fetch` (`__init__.py` and `__all__`, keeping the existing order)
- [ ] Tests in `src/tests/fetch/test_cache.py`: round trip of each new record and of a repo with counts and languages (including a non-ASCII language name and an empty tuple); `write_star_events` with `replace=False` keeps an unlisted row and with `replace=True` removes it, and leaves another repo's rows alone; the same for `write_forks`; the read order; a record for another repo raises `ValueError` and writes nothing (not even the state); a cache stamped with `schema_version` 3 raises `CacheVersionError` naming `schema_version` with `('3', '4')`; `inspect_cache` counts star events and forks, and gives 0 on a schema 3 file that lacks the tables
- [ ] Test in `src/tests/fetch/test_base.py`: `StarEvent` and `Fork` are frozen and slotted; a `Repo` built without the new fields has their defaults
- [ ] Check every test that pins `SCHEMA_VERSION` or `schema_version` reads `wambatic.fetch.cache.SCHEMA_VERSION` (grep `src/tests` for `'3'` beside `schema_version` to be sure)

**Acceptance Criteria:**

- [ ] A cache written before this task is refused with `CacheVersionError`, never read or migrated silently
- [ ] Each write method is one transaction: a failing write leaves the rows and the state as they were (shown by the other-repo test)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/fetch/test_cache.py src/tests/fetch/test_base.py src/tests/test_package.py src/tests/test_cli.py` passes

**Notes:**

- Depends on tasks-3.md (step 8) and reports/tasks-3.md (step 9), done
- Key files: `src/wambatic/fetch/base.py`, `src/wambatic/fetch/cache.py`, `src/wambatic/fetch/__init__.py`, `src/tests/fetch/test_cache.py`, `src/tests/fetch/test_base.py`
- `src/tests/test_cli.py` is in the Definition of Done because it reads the recorded `schema_version` and prints `cache info`; `src/tests/test_package.py` because it may pin `RESOURCES`.
- Reuse the step 8 write helpers (the upsert pattern, the other-repo check); Task 12 checks for duplication again.

---

## Task 2: Queries and parsing

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** fetch spec 1.8 (Implementation: Incremental sync steps 1 and 2; Testing); review-4.md choices 1 to 6

**Technical Goal:** Ask GitHub for the counts, languages and stargazer pages, and parse those and the REST fork list into records and probes, so the sync tasks only page and write.

**Subtasks:**

- [ ] In `src/wambatic/fetch/queries.py`, add to the repository fields of `OWNER_REPOSITORIES` and `REPOSITORY` `stargazerCount forkCount watchers { totalCount }` and `languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name } } }`; add `STARGAZERS` paging `repository(owner:, name:) { stargazers(first: 100, after: $cursor, orderBy: {field: STARRED_AT, direction: DESC}) { pageInfo { hasNextPage endCursor } edges { starredAt node { id } } } }` with `rateLimit { cost remaining resetAt }`
- [ ] In `src/wambatic/fetch/base.py`, extend `parse_repo` with the counts, `languages` (name and size per edge, in GitHub's order) and `languages_size` (`totalSize`; a `null` `languages` connection gives `()` and 0); add `star_probe(repo) -> str` and `fork_probe(repo) -> str` (`str(stargazer_count)`, `str(fork_count)`); add `parse_star_edge(repo, edge) -> StarEvent` and `parse_fork(repo, node) -> Fork` (from a REST fork object's `id` and `created_at`), with the existing `mapping`/`text`/`integer`/`timestamp` helpers so a malformed shape raises `GraphQLError` (`MALFORMED`)
- [ ] Hand-write the responses in `src/tests/fixtures/fetch/responses.py`: listing pages and a `REPOSITORY` response with counts and languages (one repo with more than 20 languages' worth of `totalSize`, one with `languages` `null`), `STARGAZERS` pages (newest first, two pages), and REST fork list pages (`sort=newest`, two pages); add each to the re-record list; update the existing listing responses so every test that reads them still parses
- [ ] Tests in `src/tests/fetch/test_queries.py`: every query text still selects `rateLimit`, `STARGAZERS` orders by `STARRED_AT` descending, and the listing queries select the counts and languages; in `src/tests/fetch/test_base.py`: each parser on the fixtures, languages in order with `languages_size`, the probes' text, the `null`-languages case, and a malformed star edge and fork raising `GraphQLError`

**Acceptance Criteria:**

- [ ] Every new or changed query text changes its `query:<NAME>` hash, so a schema 3 cache is refused for that reason as well
- [ ] No parser keeps a stargazer's login

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/fetch/test_queries.py src/tests/fetch/test_base.py src/tests/fetch/test_fetcher.py src/tests/fetch/test_server.py` passes

**Notes:**

- Depends on Task 1
- Key files: `src/wambatic/fetch/queries.py`, `src/wambatic/fetch/base.py`, `src/tests/fixtures/fetch/responses.py`
- `src/tests/fetch/test_fetcher.py` is in the Definition of Done because every sync test replays the listing responses this task changes.
- GraphQL's `watchers { totalCount }` is the count of users subscribed; never read REST's `watchers_count`, which is the star count (review-4.md choice 2).

---

## Task 3: Syncing star events

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** fetch spec 1.8 (API: `Fetcher.star_events`; Implementation: Incremental sync steps 1 to 5); review-4.md choices 4, 6, 7 and 8

**Technical Goal:** Keep each repo's stargazers current with a newest-first read that stops at the watermark, a full read when the star count falls or the full-refresh interval passed, and no request when the listed count is unchanged; read them back from the cache.

**Subtasks:**

- [ ] In `Fetcher.unchanged`, add the `star_events` rule: a `sync_state` row exists, `full_read_due` is false and `state.probe == star_probe(repo)`
- [ ] Add `sync_star_events(repo, full_refresh) -> int`: the read is full when there is no state, on `--full-refresh`, when `full_read_due`, or when `repo.stargazer_count` is below the integer in `state.probe` (log that reason at `info`, as `full_read_reason` does for the others; extend it rather than adding a second helper); page `STARGAZERS` with `graphql_dated`, taking the watermark from the first page's `Date`; stop at the first edge whose `starredAt` is earlier than `watermark - fetch.overlap` unless the read is full; write with `Cache.write_star_events(..., replace=full)` and a state from `new_state` with the watermark, `probe=star_probe(repo)`, `head_oid=None`, and `full_synced_at` now on a full read and kept otherwise
- [ ] Dispatch `star_events` to it in `sync`'s `sync_one`; do not add `star_events` to `BUILT_RESOURCES` yet (Task 4 adds both, so `sync` never runs half of step 10)
- [ ] Add `Fetcher.star_events(repo)` reading `Cache.read_star_events`
- [ ] Tests in `src/tests/fetch/test_fetcher.py`, calling `sync_star_events`/`unchanged` directly or `sync` with `BUILT_RESOURCES` monkeypatched to include `star_events`: a first sync reads every page and stores every star; a second sync with the same listed count makes no `STARGAZERS` request; a higher count reads page 1, stops at the cutoff and does not request page 2; a lower count reads every page and a star GitHub no longer lists leaves the cache; a passed `fetch.full_refresh_after` reads every page with an equal count; an interrupted read (an error on the second page) leaves the old rows and state; `Fetcher.star_events` returns them oldest first
- [ ] Extend `src/tests/fetch/test_live.py` (marker `live`): sync `star_events` for `octocat/Hello-World` and check the cached rows are no more than the listed `stargazer_count`; if this shows GitHub refusing deep pages, stop and report it to the user (review-4.md, Open)

**Acceptance Criteria:**

- [ ] A repo whose star count is unchanged costs no per-repo request for stars (the implementation order's "Done when")
- [ ] A removed star leaves the cache on the next sync (shown by the lower-count test; the implementation order's "Done when")

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/fetch/test_fetcher.py src/tests/fetch/test_cache.py` passes

**Notes:**

- Depends on Tasks 1 and 2
- Key files: `src/wambatic/fetch/base.py`, `src/tests/fetch/test_fetcher.py`
- The replay server counts requests per query; use that, as the step 6 and step 8 skip tests do, to show "no request".
- `src/tests/fetch/test_live.py` needs a working `GITHUB_TOKEN` and gets a 401 in cloud sessions; CI's `live` job runs it. Record in these Notes if it was not run.

---

## Task 4: Syncing forks, and `BUILT_RESOURCES`

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** fetch spec 1.8 (API: `BUILT_RESOURCES`, `Fetcher.forks`; Implementation: Incremental sync steps 1 to 5); review-4.md choices 5 to 8

**Technical Goal:** Keep each repo's direct forks current through the REST fork list, with the same probe, cutoff and falling-count rules as stars, then mark both step 10 resources built.

**Subtasks:**

- [ ] Add `sync_forks(repo, full_refresh) -> int`: decide a full read as `sync_star_events` does, with `repo.fork_count` and `fork_probe`; request `/repos/{owner}/{name}/forks` with `sort=newest`, `per_page=100` and `page` through `client.rest_get` (no ETag); take the watermark from the first response's `date`, raising `GraphQLError` (`MALFORMED`) when it is `None`; parse each fork with `parse_fork`; stop at the first fork whose `created_at` is earlier than `watermark - fetch.overlap` unless the read is full; stop at an empty or short page; write with `Cache.write_forks(..., replace=full)` and the state
- [ ] A `NotFoundError` on the first page is read as no forks, as `sync_workflow_runs` does: write no forks and a state that keeps the previous watermark (none on a first sync), never one from the local clock; log it at `debug`
- [ ] In `Fetcher.unchanged`, add the `forks` rule (as `star_events`, with `fork_probe`); dispatch `forks` to `sync_forks` in `sync_one`
- [ ] Add `Fetcher.forks(repo)` reading `Cache.read_forks`
- [ ] Set `BUILT_RESOURCES` to `RESOURCES` and `UNBUILT_RESOURCE_STEPS` to empty (keep the `NotImplementedError` path, which no resource reaches now, only if removing it would change `sync`'s documented `ValueError` for unknown names; otherwise remove the mechanism and its test)
- [ ] Tests in `src/tests/fetch/test_fetcher.py`: a first sync reads every page and stores every fork; an unchanged `fork_count` makes no fork request; a higher count stops at the cutoff; a lower count reads every page and drops a deleted fork; `--full-refresh` reads every page; a 404 on the list writes no forks and does not raise; a list response without `Date` raises `GraphQLError`; an interrupted read keeps the old rows and watermark; `sync` with `{'star_events', 'forks'}` on an unchanged repo reports it in `repos_skipped` and makes no per-repo request
- [ ] Update the test in `src/tests/fetch/test_fetcher.py` or `src/tests/test_package.py` that pins `BUILT_RESOURCES` or `UNBUILT_RESOURCE_STEPS`
- [ ] Extend `src/tests/fetch/test_live.py`: sync `forks` for `octocat/Hello-World` and check the cached rows are no more than the listed `fork_count`

**Acceptance Criteria:**

- [ ] An unchanged repo's stars and forks cost no request (the implementation order's "Done when")
- [ ] No fork request goes through the ETag store, and none uses GraphQL's `forks` connection

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/fetch/test_fetcher.py src/tests/fetch/test_cache.py src/tests/test_package.py src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 3
- Key files: `src/wambatic/fetch/base.py`, `src/tests/fetch/test_fetcher.py`
- `src/tests/test_cli.py` is in the Definition of Done because `BUILT_RESOURCES` decides what `report` syncs.
- The 404-on-list subtask must not fall back to the local clock for a watermark (fetch spec, Incremental sync step 3).

---

## Task 5: Popularity fixture data for stats

**Status:** done
**Priority:** high
**Complexity:** small
**Spec Reference:** stats spec 1.4 (Metric groups, popularity; Aggregation); review-4.md choices 10 to 13

**Technical Goal:** Give the popularity tests a small, hand-checked set of stars, forks and repo counts and languages, with the expected value of every popularity series and table written out, so the aggregation is tested against arithmetic done by hand rather than against itself.

**Subtasks:**

- [ ] In `src/tests/fixtures/stats.py`, add star events and forks for `ALPHA`, `BETA` and `GAMMA` over the existing `SINCE` to `UNTIL` months, and give their `Repo` records counts and languages; include stars and forks before `SINCE` (so the cumulative series start above zero), a month with none, a star whose local date differs between UTC and `Europe/Berlin`, a repo whose `languages_size` exceeds its listed languages (an `Other` remainder), a language shared by two repos, and a repo with no languages; make one listed `stargazer_count` differ from its cached stars, as after a sync that missed new stars
- [ ] Write the expected series per month in UTC (`ORG_POPULARITY_BY_MONTH_UTC`) and the expected `popularity` and `languages` tables as module constants, each value with a comment showing the arithmetic
- [ ] Tests in `src/tests/stats/test_fixtures.py`: the fixture records are internally consistent (each star's and fork's repo is in `REPOS`, no two stars of one repo share a `user_id`, each repo's listed languages sum to no more than its `languages_size`)

**Acceptance Criteria:**

- [ ] Every popularity series name in the stats spec has an expected value in at least one month, and `stars_added` and `forks_added` are zero in at least one month

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/stats/test_fixtures.py src/tests/stats/test_compute.py src/tests/stats/test_activity.py` passes

**Notes:**

- Depends on Task 1 (the records)
- Key files: `src/tests/fixtures/stats.py`, `src/tests/stats/test_fixtures.py`
- The compute and activity tests are in the Definition of Done because they read the same `Repo` records; adding counts must not change an activity value.

---

## Task 6: The pure `popularity` aggregation

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** stats spec 1.4 (Module location; Metric groups, popularity; Aggregation); review-4.md choices 2, 3, 10, 11 and 14

**Technical Goal:** Turn star events, forks and the repos' counts and languages into the four popularity series and the `popularity` and `languages` tables, each event placed by its own local date, as `delivery.py` does for releases.

**Subtasks:**

- [ ] Create `src/wambatic/stats/popularity.py` with `POPULARITY_METRICS` (name and unit in the spec's series order) and `aggregate(stars, forks, repos, buckets, tz, since, until) -> tuple[list[Series], dict[str, list[dict[str, typing.Any]]]]`
- [ ] `stars_added` and `forks_added` per bucket, zero in an empty bucket; `stars_total` and `forks_total` as the count with a local date on or before each bucket's last day, or `until` for the last bucket, counting events before `since`; events after `until` count in nothing
- [ ] `tables['popularity']` and `tables['languages']` exactly as the spec defines them (ordering, the `Other` row last and only when above zero, `share` from 0 to 1, an empty languages table when no repo has languages)
- [ ] Add `has_event_in_range(stars, forks, tz, since, until)` for `compute`'s range resolution, as `delivery.has_event_in_range` does, if Task 7 needs it
- [ ] Use `buckets.locate` and the existing bucket-end helper rather than copies
- [ ] Tests in `src/tests/stats/test_popularity.py`: the Task 5 expectations for every series by month in UTC and in `Europe/Berlin`, and for both tables; a `TOTAL` bucket gives the counts over the range and the totals at `until`; hypothesis: for any list of stars, `stars_added` summed over the buckets equals the stars whose local date is in range, `stars_total` never falls from one bucket to the next, and its last value equals the stars on or before `until`

**Acceptance Criteria:**

- [ ] Every value of the four series is a whole number, as the JSON output requires of unit `count`
- [ ] `popularity.py` imports nothing from `wambatic.reports` or `wambatic.cli` (the layering test)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/stats/test_popularity.py src/tests/stats/test_buckets.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Task 5
- Key files: `src/wambatic/stats/popularity.py`, `src/tests/stats/test_popularity.py`
- Hypothesis is already a development dependency (shared tools-and-libraries rule).

---

## Task 7: `popularity` in `compute`

**Status:** done
**Priority:** high
**Complexity:** medium
**Spec Reference:** stats spec 1.4 (API: `GROUPS`, `resources_for`, `StatsResult.tables`; Error handling; Range; Reading the cache; Groups not built yet; Metric groups, activity; Aggregation: user subject, series order); system spec 1.7 Architecture and Data flow step 2; review-4.md decision 1 and choices 12 and 13

**Technical Goal:** Read star events and forks from the cache, feed them and the subject's repos to the popularity aggregation, fold its series and tables into the result, and take the four metrics off `activity`'s unavailable list.

**Subtasks:**

- [ ] In `src/wambatic/stats/base.py`, add `'popularity'` to `GROUPS`; in `src/wambatic/stats/compute.py`, add `RESOURCES_BY_GROUP['popularity'] = frozenset({'forks', 'star_events'})`, add `popularity` to `BUILT_GROUPS`, and remove `UNBUILT_ACTIVITY_METRICS` and its use in `unavailable` (keep `UNBUILT_GROUP_STEPS`, now empty, only if its removal would change a documented message; otherwise remove the mechanism and its tests)
- [ ] Add `read_popularity`: every star event and fork of each repo, with no author filter for a user subject
- [ ] Resolve a `None` `since` from the earliest record of every requested built group, counting stars' `starred_at` and forks' `created_at`; when no requested group has a dated record, use the start of the bucket holding `until` (`until` itself for `TOTAL`); do not raise `EmptySubjectError` for lack of records when `popularity` is requested and the subject has repos
- [ ] Place the popularity series after the delivery series and before the breakdowns; merge its tables into `tables`
- [ ] Tests in `src/tests/stats/test_compute.py`: `resources_for({'popularity'})`; `compute` with `groups={'popularity'}` on the Task 5 fixtures gives the expected series, tables and `since`; `groups={'activity', 'flow', 'delivery', 'popularity'}` orders the series as the spec says; a user subject's popularity counts every star of the user's repos; a popularity-only request on a subject with repos and no stars or forks returns one bucket of zeros and the tables, and does not raise; a request including `activity` has no unavailable row for `stars`, `forks`, `watchers` or `languages`; provenance has `fetched_at:star_events` and `fetched_at:forks` for a popularity request
- [ ] Update `src/tests/test_cli.py` and `src/tests/reports/` tests that expect the four unavailable rows

**Acceptance Criteria:**

- [ ] `compute` never syncs and makes no request (the fetcher in the tests has no client entered)
- [ ] The default request (`activity,flow`) gives the same series as before this list and lists nothing as unavailable (the implementation order's "Done when")

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/stats/test_compute.py src/tests/stats/test_popularity.py src/tests/stats/test_base.py src/tests/test_cli.py src/tests/reports/test_terminal.py src/tests/reports/test_html.py` passes

**Notes:**

- Depends on Tasks 4 and 6
- Key files: `src/wambatic/stats/base.py`, `src/wambatic/stats/compute.py`, `src/tests/stats/test_compute.py`
- If review-4.md's Answers records decision 1 as option B or C, this task changes first (see the header).

---

## Task 8: Terminal popularity sections, JSON and the groups help

**Status:** done
**Priority:** medium
**Complexity:** medium
**Spec Reference:** reports spec 1.7 (Command line: `--groups`; Terminal items 3 and 10 to 14; JSON output); review-4.md choices 11, 15 and 17

**User Story:** As a maintainer, I want the terminal report to show my stars and forks by period, each repository's counts and the languages, so that I can see how a project is received without opening the HTML page.

**Subtasks:**

- [ ] In `src/wambatic/reports/rows.py`, add `has_popularity`, `TOP_LANGUAGES_SHOWN = 10`, the popularity metric tuples (imported from `wambatic.stats.popularity`, not copied), `popularity_table` (with the `Total` row the spec gives: sums of the added columns, the last bucket's totals), `popularity_now_table` (with a `Total` row when there is more than one repository) and `languages_rows`; extend `TREND_METRICS` with the four popularity series
- [ ] In `src/wambatic/reports/terminal.py`, render the three tables after the DORA proxies with their captions (Languages: the first `TOP_LANGUAGES_SHOWN` rows, then `and N more`; share as a percentage with one decimal place); Unavailable and provenance stay last
- [ ] Name `popularity` in the `--groups` help in `src/wambatic/cli.py`, the `groups` description in `src/wambatic/reports/web.py` and the hint in `src/wambatic/reports/templates/form.html`
- [ ] Check `result_to_dict` writes the four series' values as integers and the tables as given; add a test if none covers the new tables
- [ ] Tests in `src/tests/reports/test_rows.py` and `src/tests/reports/test_terminal.py`: the three tables from a hand-built result, the `Total` rows, the languages cut-off and `and N more`, `--groups popularity` printing no other group's tables, and trend lines for the four series; in `src/tests/reports/test_base.py`: the JSON types of the popularity series and tables; in `src/tests/reports/test_web.py`: the form shows the new hint

**Acceptance Criteria:**

- [ ] `--groups popularity` renders in the terminal and JSON formats (part of the implementation order's last "Done when" item; Task 10 has HTML)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/reports/test_rows.py src/tests/reports/test_terminal.py src/tests/reports/test_base.py src/tests/reports/test_web.py src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 7
- Key files: `src/wambatic/reports/rows.py`, `src/wambatic/reports/terminal.py`, `src/wambatic/cli.py`, `src/wambatic/reports/web.py`, `src/tests/fixtures/reports.py`

---

## Task 9: CLI: `cache info` and a popularity report end to end

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** reports spec 1.7 (`cache info`; Running `report` step 5); fetch spec 1.8 (`CacheInfo`); review-4.md choices 9 and 17

**Technical Goal:** Show the new counts in `cache info`, and prove `report --groups popularity` syncs the two resources and renders from a replayed GitHub.

**Subtasks:**

- [ ] In `src/wambatic/cli.py`, add `star events` and `forks` lines to `cache info` after `workflow runs`
- [ ] Check the sync log line names `star_events` and `forks` (it is built from `rows_written`; change nothing if it does)
- [ ] Tests in `src/tests/test_cli.py`: `cache info` prints the star and fork counts and 0 for a schema 3 file; `report repo:OWNER/NAME --groups popularity` against the replay server syncs `star_events` and `forks`, logs their rows, and prints the Popularity by period table; the same with `--no-fetch` on the warm cache makes no request; `--format json --groups popularity` gives the popularity series and tables

**Acceptance Criteria:**

- [ ] A second `report --groups popularity` against an unchanged replayed repo makes the listing request and no star or fork request (the implementation order's "Done when")

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 8
- Key files: `src/wambatic/cli.py`, `src/tests/test_cli.py`

---

## Task 10: HTML popularity section

**Status:** done
**Priority:** medium
**Complexity:** medium
**Spec Reference:** reports spec 1.7 (API `Figure.group`, `build_range_figures`; Static HTML: layout items 2 and 6 to 8, charts, testing; Visualisation choices); review-4.md choice 16

**User Story:** As a maintainer, I want the HTML report to chart my stars, forks and languages beside the other groups, so that I can share one page that shows how a project is received.

**Subtasks:**

- [ ] In `src/wambatic/reports/figures.py`, widen `Figure.group` (and the internal `Chart.group`) to include `'popularity'`, add Stars per period and Forks per period (bars) and Stars over time and Forks over time (lines) to `CHARTS` in the spec's order, and add the Languages chart to `build_range_figures` (horizontal bars of share in per cent, the first `TOP_LANGUAGES_SHOWN` rows in the table's order, first row at the top; absent when the table is empty)
- [ ] In `src/wambatic/reports/html.py`, add the popularity tiles (Stars, Forks, Watchers, Top language), the Popularity section with its line about the counts, and Popularity by period per granularity, Popularity now and Languages (every row) from `rows.py`
- [ ] Tests in `src/tests/reports/test_figures.py`: every popularity figure validates with `plotly.graph_objects.Figure`, shares are multiplied by 100, the Languages chart is absent with an empty table; in `src/tests/reports/test_html.py`: the tiles and section appear only with popularity series, the tables match `rows.py`, Top language is `-` with no languages; extend `src/tests/reports/test_html_browser.py` with a popularity report that renders every chart with no request, console error or page error

**Acceptance Criteria:**

- [ ] `--groups popularity` renders in the HTML format (the rest of the implementation order's last "Done when" item)
- [ ] The page still makes no network request

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/reports/test_figures.py src/tests/reports/test_html.py src/tests/reports/test_html_browser.py` passes

**Notes:**

- Depends on Task 8
- Key files: `src/wambatic/reports/figures.py`, `src/wambatic/reports/html.py`, `src/wambatic/reports/templates/`
- As the step 7 list found, build the report fixtures before launching the browser in the browser test: Playwright's sync API breaks `asyncio.run` in the same test.
- Every popularity chart has one series, so it needs one palette slot and no legend.

---

## Task 11: README

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** shared user-guides rule (keep guides in sync with code); reports spec 1.7 Terminal and Static HTML; stats spec 1.4 popularity; fetch spec 1.8 Cache (schema 4); review-4.md decision 1 and choices 2, 3, 6, 8 and 10

**User Story:** As a wambatic user, I want the README to say what each popularity number counts and what it costs to fetch, so that I know why a cumulative star count can read below GitHub's and why the first popularity report is slow.

**Subtasks:**

- [ ] In `README.md`: a Popularity section after Delivery saying how to ask for it (`--groups popularity`), what each series counts and by which date, that the totals count the stars and forks that exist now (a removed star is in no period), that the table's counts are GitHub's own at the last sync (forks for the whole network), that watchers are a current count only and languages a snapshot of the 20 largest per repository with the rest as `Other`
- [ ] The first-report text lists the popularity tables among the sections; `--groups` names `popularity`; the Unavailable text no longer names the four metrics
- [ ] The cache section says a cache from an earlier wambatic is refused once after this upgrade, and `cache info` lists star and fork counts; the first sync with `--groups popularity` reads every star and fork, about one GraphQL point per 100 stars and one request per 100 forks per repository, and later syncs cost nothing for a repository whose counts did not change
- [ ] Add a Common workflows example: `wambatic report org:NAME --groups popularity`
- [ ] Run every README example that needs no network against a cache built from the stats fixtures, or with `--help`, and check its output matches the README
- [ ] Keep counts out of the prose (shared counts-in-prose rule) and use British spelling

**Acceptance Criteria:**

- [ ] Every popularity series and table name the JSON output carries appears in the README
- [ ] No sentence says stars, forks, watchers or languages are not built

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] The task's commit passes its pre-commit hooks (never `--no-verify`)
- [ ] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Tasks 9 and 10
- Key files: `README.md`

---

## Task 12: Exports, layering, closing checks and spec status

**Status:** done
**Priority:** medium
**Complexity:** small
**Spec Reference:** fetch spec 1.8 API; stats spec 1.4 Module location; system spec Architecture (layering); implementation order step 10 "Done when"; review-4.md choice 18

**Technical Goal:** Expose the step 10 names, keep the layering enforced, remove what the new code duplicated, run every test the list can reach, mark the step done and, since it is the last step, every spec implemented.

**Subtasks:**

- [ ] Check `wambatic.fetch.__all__` has `StarEvent` and `Fork` (Task 1); `wambatic.stats` needs no new export (`popularity` is internal, as `delivery` is)
- [ ] Extend `src/tests/test_package.py`: `wambatic.fetch.StarEvent` and `wambatic.fetch.Fork` resolve, `BUILT_RESOURCES` equals `RESOURCES`, and `wambatic.stats.GROUPS` (or `wambatic.stats.base.GROUPS`) contains `popularity`
- [ ] Check `src/tests/test_layering.py` covers `wambatic.stats.popularity` (it scans every module; confirm with a run, and add a case only if it does not)
- [ ] Hoist anything this component duplicates from its siblings to a single owner: grep the tree for each literal collection, constant and one-line helper that `popularity.py`, the star and fork cache methods, the probe and parse functions, `sync_star_events` and `sync_forks`, the new period tables, the new charts and the test fixtures define (the count probes beside `release_probe`, the full-read decision shared with `sync_updated`, `sync_releases` and `sync_workflow_runs`, the REST paging loop shared with `read_workflow_runs`, the 404-as-empty handling, the upsert SQL pattern, record-to-row conversion, bucket location and bucket ends, the period-table construction and its `Total` row, the `and N more` cut-off shared with Top contributors, metric name tuples), and import rather than copy, choosing the owner from the existing import graph and preferring a module the consumer already imports
- [ ] Check the implementation order's "Done when" for step 10 and record in this task's Notes the test that shows each item: an unchanged repo's stars and forks cost no request (Tasks 3, 4 and 9), a removed star leaves the cache on the next sync (Task 3), the default report lists nothing as unavailable (Task 7), and `--groups popularity` in the terminal, JSON and HTML formats (Tasks 8 to 10)
- [ ] Run every test that imports a changed module directly or transitively: `pytest src/tests/fetch src/tests/stats src/tests/reports src/tests/test_cli.py src/tests/test_package.py src/tests/test_layering.py`
- [ ] In `agents/specs/implementation-order.md`, set step 10's Status to `done: [tasks-4](../tasks/stats/tasks-4.md)`
- [ ] Set the spec's `**Status:**` to `implemented` in `agents/specs/stats/spec.md`, and, since step 10 completes every step of the implementation order, in `agents/specs/fetch-and-cache/spec.md`, `agents/specs/reports/spec.md`, `agents/specs/system/spec.md` and `agents/specs/implementation-order.md` (review-4.md choice 18)

**Acceptance Criteria:**

- [ ] Every step 10 "Done when" item is met, or its gap is recorded in the task that owns it
- [ ] No new duplication between `popularity.py` and `delivery.py`, or between the star and fork code and the release, run and pull request code in `cache.py` and `base.py`
- [ ] No spec says `proposed`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch src/tests/stats src/tests/reports src/tests/test_cli.py src/tests/test_package.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Tasks 1 to 11
- The project has no affected-tests tool; the command above names every test file that reaches a module this list changed (`wambatic.fetch` is reached by the fetch, stats, reports and CLI tests, `wambatic.stats` by the stats, reports and CLI tests, `wambatic.reports` and `wambatic.cli` by the reports and CLI tests, and the package and layering tests check the whole tree).
- `pre-commit run --all-files` runs `mypy` over the whole tree with the other hooks; it is the list's one whole-tree lint run.
- `src/tests/fetch/test_live.py` needs a working `GITHUB_TOKEN` and gets a 401 in cloud sessions, as on `main`; CI's `live` job runs it. Record that here if it is the only failure.
- Key files: `src/tests/test_package.py`, `src/tests/test_layering.py`, `agents/specs/implementation-order.md`, the four spec files
- Done-when evidence: an unchanged repo's stars and forks cost no request (`test_fetcher.py` star and fork sections, `test_cli.py` second-run test); a removed star leaves the cache on the next sync (`test_fetcher.py`, the falling-count full read); the default report lists nothing as unavailable (`reports/test_terminal.py` known-good text, `test_cli.py`); `--groups popularity` in terminal, JSON and HTML (`test_cli.py` end-to-end, `reports/test_html.py`, `reports/test_html_browser.py`).
- Closing run: all of the listed test files pass except the four `test_live.py` tests, which get a 401 in this cloud session and run in CI's `live` job. `pre-commit run --all-files` passes.
