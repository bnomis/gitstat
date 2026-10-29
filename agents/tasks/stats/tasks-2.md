# Tasks: Stats

**Spec:** `agents/specs/stats/spec.md`
**Created:** 2026-10-29
**Version:** 2

This list builds step 6 of the [implementation order](../../specs/implementation-order.md), "Flow data and stats (PRs, issues)": the `PullRequest` and `Issue` records and their cache tables, `Fetcher.pull_requests` and `Fetcher.issues` with updated-at paging and incremental sync, the `flow` group in `compute`, and the terminal's flow tables, so the default report (`activity,flow`) no longer lists `flow` as unavailable. It is written against version 1.2 of the stats spec, 1.5 of the [fetch spec](../../specs/fetch-and-cache/spec.md) and 1.3 of the [reports spec](../../specs/reports/spec.md); the gaps, the choices made and the one decision are in [review-2.md](../../specs/stats/review-2.md). The list follows the decision's recommended option (the repo listing probes each repo's newest pull request and issue); if the other option is chosen, Tasks 1, 3 and 5 change as review-2.md says before the list runs. The step 4 list, [tasks-1.md](tasks-1.md), built the `activity` group this list sits beside, and step 3's [fetch-and-cache/tasks-2.md](../fetch-and-cache/tasks-2.md) built the commit sync the new resources are modelled on.

## Spec coverage

| Spec section | Covered by |
|--------------|------------|
| Stats: Module location (`flow.py`) | Task 7 |
| Stats: Module location (`delivery.py`) | step 8 |
| Stats: API (`resources_for`, `compute`, `StatsRequest`, `StatsResult`) | Task 8 (unchanged signatures; `flow` now built) |
| Stats: Error handling (`EmptySubjectError` across groups) | Task 8 |
| Stats: Implementation (Range, Reading the cache, Partial buckets) | Task 8 |
| Stats: Groups not built yet (`flow` leaves `tables['unavailable']`) | Task 8 |
| Stats: Metric groups, `flow` | Task 7 |
| Stats: Metric groups, `activity` and `delivery` | stats/tasks-1.md (activity); step 8 (delivery, stars, forks, watchers, languages) |
| Stats: Aggregation (user subject, no flow breakdowns, series order) | Tasks 7 and 8 |
| Stats: Provenance (`fetched_at:issues`, `fetched_at:pull_requests`) | Task 8 |
| Stats: Settings | no change (`bot_logins` is not read by flow, review-2.md choice 12) |
| Fetch 1.5: Module location, API records (`Repo` probe fields, `PullRequest`, `Issue`) | Task 1 |
| Fetch 1.5: API `Cache` (`SCHEMA_VERSION` 2, `write_`/`read_pull_requests`, `write_`/`read_issues`), `CacheInfo` counts | Task 1 |
| Fetch 1.5: API `GitHubClient.graphql_dated` | Task 2 |
| Fetch 1.5: API `Fetcher.pull_requests`, `Fetcher.issues`, `BUILT_RESOURCES`, `SyncReport` | Tasks 4 and 5 |
| Fetch 1.5: Implementation, Cache (new tables, schema 2, no migration) | Task 1 |
| Fetch 1.5: Incremental sync 1 (listing probe, per-resource unchanged rule) | Tasks 3 and 5 |
| Fetch 1.5: Incremental sync 2 (`PULL_REQUESTS`, `ISSUES`, bot logins, first review, state rules) | Tasks 3 and 4 |
| Fetch 1.5: Incremental sync 3 (`Date` watermark), 4 (atomic advance), 5 (full re-read replaces rows) | Tasks 2 and 4 |
| Fetch 1.5: Implementation, Testing (hand-written step 6 fixtures) | Tasks 3 and 4 |
| Fetch: `releases`, `workflow_runs`, `star_events` | step 8 |
| Reports 1.3: Running `report` (sync log per resource), `cache info` counts | Task 10 |
| Reports 1.3: Terminal (conditional sections, Trends, Flow by period, Flow times by period) | Task 9 |
| Shared user-guides rule (README) | Task 11 |
| Implementation order step 6 "Done when" | Tasks 4, 5 and 8; checked in Task 12 |

No spec's `**Status:**` changes with this list: the stats and fetch specs still have the `delivery` group and its resources to build (step 8), and the reports spec the HTML report and web app (steps 7 and 9).

## Conventions for every task

- Async tests are plain `def test_...() -> None` functions whose body calls `asyncio.run(...)` on an inner coroutine; no pytest async plugin is added (as in the fetch, stats and CLI tests).
- Every cache in a test lives under pytest's `tmp_path`; the autouse `isolated_environment` fixture in `src/tests/conftest.py` already removes `GITHUB_TOKEN` and `WAMBATIC_CONFIG`. No test reaches the network: GitHub is the replay server (`tests.fixtures.fetch.server.ReplayServer`) through the existing `make_client`/`make_fetcher` fixtures.
- Hand-written GitHub responses carry a comment naming the documentation page their shape comes from, and are added to the re-record list in the module docstring of `src/tests/fixtures/fetch/responses.py` (fetch spec, Testing).
- Times are aware UTC `datetime`s everywhere below `compute`; the cache stores them with `wambatic.fetch.cache.to_text`, so text order is time order.
- The `flow` aggregation is pure, like `activity`: no I/O, records in, series out.
- Messages never echo a token or a config value (system spec, Settings).
- The project has no affected-tests tool, so each task names its test files literally; Task 12 runs every test the list can reach.
- The local environment may lack the exact Python patch release `pyproject.toml` requires (`>=3.14.7`); if `uv sync` cannot find it, say so in the task's Notes and do what the step 5 list did (resolve with the patch release lowered for that one command, then put `pyproject.toml` and `uv.lock` back), never by committing a changed `requires-python`. This list adds no dependency.
- A choice in review-2.md that is flagged before a task runs changes that task first; a task never extends a choice to a case it does not name, and stops for the user instead.

---

## Task 1: Records and cache schema 2

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** fetch spec 1.5 (Module location; API: `Repo`, `PullRequest`, `Issue`, `Cache`, `SCHEMA_VERSION`, `CacheInfo`; Implementation, Cache); review-2.md choices 2, 7, 8 and 9

**Technical Goal:** Give the cache somewhere to keep pull requests and issues, and the repo listing's newest-update probe, so the sync tasks can write them and stats can read them.

**Subtasks:**

- [ ] In `src/wambatic/fetch/base.py`, add the frozen, slotted `PullRequest` and `Issue` dataclasses with the spec's fields and comments, and `pull_requests_updated_at` and `issues_updated_at` (both `datetime.datetime | None = None`) on `Repo`, before `missing`
- [ ] In `src/wambatic/fetch/cache.py`, set `SCHEMA_VERSION = 2`; add to `SCHEMA` the `pull_requests` table (`repo`, `number`, `author_login`, `created_at`, `updated_at`, `merged_at`, `closed_at`, `first_review_at`, `additions`, `deletions`, primary key `(repo, number)`) and the `issues` table (`repo`, `number`, `author_login`, `created_at`, `updated_at`, `closed_at`, primary key `(repo, number)`), each with an index on `(repo, updated_at)`; add the `pull_requests_updated_at` and `issues_updated_at` columns to `repos`
- [ ] Extend `upsert_repos`, `read_repos` and `repo_from_row` for the two `Repo` fields
- [ ] Add `write_pull_requests`, `read_pull_requests`, `write_issues` and `read_issues` as the spec: one transaction each; with `replace`, delete the repo's rows first; upsert by `(repo, number)` with `ON CONFLICT ... DO UPDATE` as `write_commits` does; write the state; return the rows written; raise `ValueError` when a record or the state belongs to another repo; reads filter `updated_at >= since` when `since` is given and order by `number`
- [ ] Add `pull_requests` and `issues` to `CacheInfo` and count them in `inspect_cache` (0 for an absent table, as for `commits`)
- [ ] Export `PullRequest` and `Issue` from `wambatic.fetch` (`__init__.py` and `__all__`, keeping the existing order)
- [ ] Tests in `src/tests/fetch/test_cache.py`: round trip of each record, including `None` times and a non-ASCII login; `replace=True` removes a row that is not in the new list and `replace=False` keeps it; an upsert of a changed pull request replaces its fields and keeps the row count; `read_*` with `since` keeps exactly the rows at or after it; a record for another repo raises `ValueError` and writes nothing (not even the state); the repo probe fields round-trip through `upsert_repos`/`read_repos`; a cache file stamped with `schema_version` 1 raises `CacheVersionError` naming `schema_version` with `('1', '2')`; `inspect_cache` counts pull requests and issues, and gives 0 on a schema 1 file that lacks the tables
- [ ] Test in `src/tests/fetch/test_base.py`: `PullRequest`, `Issue` and `Repo` are frozen and slotted, and a `Repo` built without the probe fields has them `None`
- [ ] Update every existing test that pins `SCHEMA_VERSION` to 1 or `schema_version` to `'1'` (grep `src/tests` for both) to read `wambatic.fetch.cache.SCHEMA_VERSION` instead of a literal

**Acceptance Criteria:**

- [ ] A cache written before this task is refused with `CacheVersionError`, never read or migrated silently
- [ ] Each write method is one transaction: a failing write leaves the rows and the state as they were (shown by the other-repo test)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_cache.py src/tests/fetch/test_base.py src/tests/test_package.py src/tests/test_cli.py` passes

**Notes:**

- Depends on stats/tasks-1.md and reports/tasks-1.md (steps 4 and 5), done
- Key files: `src/wambatic/fetch/base.py`, `src/wambatic/fetch/cache.py`, `src/wambatic/fetch/__init__.py`, `src/tests/fetch/test_cache.py`, `src/tests/fetch/test_base.py`
- `src/tests/test_cli.py` is in the Definition of Done because it asserts the recorded `schema_version` (`rows['schema_version'] == ['1']`) and builds `CacheVersionError({'schema_version': ('0', '1')})`.
- Shared helpers for the three write methods are welcome now; Task 12 checks for duplication again.

---

## Task 2: `GitHubClient.graphql_dated`

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** fetch spec 1.5 (API: `GitHubClient.graphql_dated`; Incremental sync step 3); review-2.md choice 5

**Technical Goal:** Give the sync a server-side time for the watermark, from the response that carried the first page, through the client's one request path.

**Subtasks:**

- [ ] In `src/wambatic/fetch/client.py`, add `graphql_dated(query, variables) -> tuple[dict[str, object], datetime.datetime]`: the body of today's `graphql`, plus the response's `Date` header parsed with [`email.utils.parsedate_to_datetime`](https://docs.python.org/3.14/library/email.utils.html#email.utils.parsedate_to_datetime) and converted to UTC; a missing or unparseable header (including a naive result) raises `GraphQLError([('MALFORMED', ...)])`
- [ ] Make `graphql` return `(await self.graphql_dated(query, variables))[0]`, so there is one request path
- [ ] Tests in `src/tests/fetch/test_client.py`: a canned response with `Date: Thu, 29 Oct 2026 12:00:00 GMT` gives `datetime(2026, 10, 29, 12, 0, tzinfo=UTC)` and the same data `graphql` returns; a response whose `Date` is `not a date` raises `GraphQLError` with type `MALFORMED`; every existing `graphql` test still passes unchanged

**Acceptance Criteria:**

- [ ] `graphql`'s behaviour and errors are unchanged for every existing caller
- [ ] The watermark never comes from the local clock

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_client.py src/tests/fetch/test_fetcher.py` passes

**Notes:**

- Depends on nothing in this list; can run before or after Task 1
- Key files: `src/wambatic/fetch/client.py`, `src/tests/fetch/test_client.py`
- aiohttp's server adds a `Date` header to every response, so the replay server's responses carry one unless a `Canned` sets its own; check how `Canned.headers` interacts with it (a test that sets `Date` must see that value) before writing the tests. A test that needs a missing header may have to strip it in the replay server; if so, add that as an option on `Canned` rather than a second server.

---

## Task 3: Queries and parsing for pull requests, issues and the listing probe

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** fetch spec 1.5 (Incremental sync step 1, the listing probe; step 2, `PULL_REQUESTS` and `ISSUES`, bot logins, first review, state rules; Testing); review-2.md decision 1 and choices 2, 3 and 4

**Technical Goal:** Turn GitHub's GraphQL pages into `PullRequest`, `Issue` and probed `Repo` records, with every rule about state, bots and reviews in one parsing function each.

**Subtasks:**

- [ ] In `src/wambatic/fetch/queries.py`, add to the node selection of `OWNER_REPOSITORIES` and `REPOSITORY`: `pullRequests(first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) { nodes { updatedAt } }` and the same for `issues`
- [ ] Add `PULL_REQUESTS` and `ISSUES`, each `repository(owner: $owner, name: $name)` with `first: 100, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}`, `pageInfo { hasNextPage endCursor }`, the node fields the fetch spec lists, and `rateLimit { cost remaining resetAt }`
- [ ] In `src/wambatic/fetch/base.py`, extend `parse_repo` to read the two probes (`None` when the connection's `nodes` is empty)
- [ ] Add `actor_login(value, what) -> str | None`: `None` for `null`; `<login>[bot]` when `__typename` is `Bot`; otherwise `login`
- [ ] Add `parse_pull_request(repo, node) -> PullRequest` and `parse_issue(repo, node) -> Issue` with the spec's rules: `merged_at` only when `state` is `MERGED`; `closed_at` only when `state` is not `OPEN`; `first_review_at` the minimum `submittedAt` over review nodes whose author is not a `Bot` and whose login differs from the pull request author's (compare case-insensitively; a `null` review author counts; a node with `submittedAt` `null` is skipped); malformed shapes raise through the existing `mapping`/`text`/`integer`/`timestamp` helpers
- [ ] Add fixtures to `src/tests/fixtures/fetch/responses.py`, hand-written from [PullRequest](https://docs.github.com/en/graphql/reference/objects#pullrequest), [Issue](https://docs.github.com/en/graphql/reference/objects#issue) and [Bot](https://docs.github.com/en/graphql/reference/objects#bot) with those links in comments: builder functions `pull_request_node(...)`, `issue_node(...)`, `pull_requests_page(nodes, has_next, cursor)` and `issues_page(...)` in the style of `repo_node` and `history_page`, probe arguments on `repo_node`, and name each new constant in the module docstring's re-record list
- [ ] Tests in `src/tests/fetch/test_queries.py`: the new queries select `rateLimit` (the existing check covers every constant; confirm it picks them up) and the listing queries contain both probes
- [ ] Tests in `src/tests/fetch/test_base.py` (or `test_fetcher.py`, beside the existing `parse_*` tests; follow where they live): a merged pull request has `merged_at` and `closed_at`; a closed-unmerged one has `closed_at` only; an open one with a stale `closedAt` (reopened) has neither; a reopened issue has no `closed_at`; a `Bot` author becomes `name[bot]` and a `null` author `None`; `first_review_at` ignores the author's own review (different case), a `Bot` review and a pending review, counts a `null`-author review, and is the earliest when the reviews are out of order; no qualifying review gives `None`; a probe with empty `nodes` gives `None`; a node missing `number` raises `GraphQLError`

**Acceptance Criteria:**

- [ ] Every rule in the fetch spec's step 2 bullet for pull requests and issues has a test
- [ ] The cache identity gains `query:PULL_REQUESTS` and `query:ISSUES` and the listing hashes change (shown by `expected_identity()` in a test)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_queries.py src/tests/fetch/test_base.py src/tests/fetch/test_fetcher.py src/tests/fetch/test_cache.py` passes

**Notes:**

- Depends on Task 1 (the records and `Repo` fields)
- Key files: `src/wambatic/fetch/queries.py`, `src/wambatic/fetch/base.py`, `src/tests/fixtures/fetch/responses.py`, `src/tests/fetch/test_queries.py`, `src/tests/fetch/test_base.py`
- The listing fixtures (`OWNER_REPOSITORIES_OK`, `REPOSITORY_OK`) gain the probe fields; existing sync tests that compare a listed `Repo` with a cached one must still pass.
- Bot login suffix and the bot type of automatic reviewers are assumptions from the reference, to be confirmed when the fixtures are re-recorded (review-2.md, Open for a later step).

---

## Task 4: Syncing one repo's pull requests and issues

**Status:** todo
**Priority:** high
**Complexity:** large
**Spec Reference:** fetch spec 1.5 (Incremental sync steps 2 to 5 for `pull_requests` and `issues`); implementation order step 6 "Done when" (a changed PR is updated, unchanged ones untouched; the interval removes a deleted issue); review-2.md choices 5 and 6

**Technical Goal:** Bring one repo's pull requests or issues up to date: everything on the first sync or a full re-read, otherwise only what changed since the watermark, written with the new state in one transaction.

**Subtasks:**

- [ ] In `src/wambatic/fetch/base.py`, add `Fetcher.read_updated(repo, resource, state, full) -> tuple[list[PullRequest] | list[Issue], datetime.datetime]` (or one method per resource sharing a helper; name it as fits the module): page `PULL_REQUESTS` or `ISSUES` with `graphql_dated`, keep the first page's `Date` as the new watermark, parse every node, and stop at the first node whose `updatedAt` is earlier than `state.watermark - settings.overlap`, unless `full` or there is no state or no watermark, when every page is read
- [ ] Add `Fetcher.full_read_due(state, now) -> bool`: no state, or `now - state.full_synced_at > settings.full_refresh_after`
- [ ] Add `Fetcher.sync_updated(repo, resource, full_refresh) -> int`: decide `full` (`full_refresh` or `full_read_due`), read, build the new `SyncState` (`watermark` the first page's `Date`; `head_oid` `None`; `pushed_at`/`updated_at` from the listed repo; `synced_at` the client clock; `full_synced_at` the client clock on a full read, else the stored one), then `write_pull_requests` or `write_issues` with `replace=full`; log one `info` line when reading in full, with the reason, as `sync_commits` does
- [ ] Add `Fetcher.pull_requests(repo, since)` and `Fetcher.issues(repo, since)` reading the cache through `db`, as `commits` does
- [ ] Tests in `src/tests/fetch/test_fetcher.py`, driving `sync_updated` against the replay server: a first sync reads every page (two pages) and stores the first page's `Date` as the watermark; a second sync with a watermark reads one page, stops at the first item older than `watermark - overlap`, updates the one pull request that changed and leaves the older rows untouched (same values, and the server received exactly one request); an item inside the overlap is re-read and rewritten harmlessly; a failing second page leaves the old rows and state (atomic advance); with `full_synced_at` older than `full_refresh_after`, every page is read and an issue absent from GitHub's answer is removed from the cache; `full_refresh=True` does the same at once; an incremental sync keeps `full_synced_at`; `pull_requests(repo, since)` and `issues(repo, since)` return the cached rows from `since`

**Acceptance Criteria:**

- [ ] Implementation order step 6 "Done when": a changed pull request is updated and unchanged ones untouched, and the full-refresh interval removes a deleted issue, each shown by a named test
- [ ] The watermark stored is the first page's `Date`, never a record's `updatedAt` or the local clock

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_fetcher.py src/tests/fetch/test_cache.py` passes

**Notes:**

- Depends on Tasks 1, 2 and 3
- Key files: `src/wambatic/fetch/base.py`, `src/tests/fetch/test_fetcher.py`, `src/tests/fixtures/fetch/responses.py`
- `sync` itself is wired in Task 5; this task's tests call the per-repo method directly.
- Settings: `fetch.overlap` (default 1 hour) and `fetch.full_refresh_after` (default 30 days) already load from step 1.

---

## Task 5: `sync` for pull requests and issues

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** fetch spec 1.5 (API: `BUILT_RESOURCES`, `Fetcher.sync`, `SyncReport`; Incremental sync step 1, the per-resource unchanged rule); implementation order step 6 "Done when" (an unchanged repo costs no per-repo request); review-2.md decision 1 and choice 9

**Technical Goal:** Let `Fetcher.sync` bring `issues` and `pull_requests` up to date for a whole subject, skipping per resource what the listing shows unchanged, so the CLI can sync the `flow` group.

**Subtasks:**

- [ ] Set `BUILT_RESOURCES = frozenset({'commits', 'issues', 'pull_requests'})` and drop `issues` and `pull_requests` from `UNBUILT_RESOURCE_STEPS`
- [ ] Replace `unchanged(repo, resources)` with a per-resource rule: `commits` as today (listed `pushedAt` and `updatedAt` equal the state's); `pull_requests` and `issues` unchanged when a state exists, no full read is due (`full_read_due`), and the listed probe (`repo.pull_requests_updated_at` or `repo.issues_updated_at`) is `None` or earlier than `state.watermark - settings.overlap`; a state without a watermark is not unchanged
- [ ] In `sync`, give each listed repo the list of requested resources it needs (all with `full_refresh`), run each repo's resources in order inside one semaphore slot (`fetch.workers` stays a repo count), and count a repo as skipped only when it needs none
- [ ] Build `SyncReport.rows_written` with an entry for every requested resource (0 when nothing was written); keep `full_refetches` for commits only
- [ ] Update the tests in `src/tests/fetch/test_fetcher.py` that expect `NotImplementedError` for `issues` and `pull_requests` (the parametrised case near `('issues', 6)`) so only step 8 resources raise it
- [ ] Tests in `src/tests/fetch/test_fetcher.py`: syncing `{'commits', 'issues', 'pull_requests'}` for an org of two repos backfills all three and reports rows for each; a second sync with the listing unchanged and both probes older than the watermark less the overlap sends only the listing query (assert the replay server's requests); a newer probe on one repo sends that repo's query for that resource only; a repo with no pull requests (probe `None`) and a state is skipped for them; `full_refresh=True` reads every resource of every repo; the `fetch.workers` bound still holds (reuse the existing in-flight test pattern); `unchanged` for each resource and each branch

**Acceptance Criteria:**

- [ ] A repo whose newest pull request and issue are older than the watermark less the overlap, and whose commits are unchanged, costs no per-repo request (step 6 "Done when")
- [ ] Only `releases`, `star_events` and `workflow_runs` still raise `NotImplementedError`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_fetcher.py src/tests/fetch/test_base.py src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 4
- Key files: `src/wambatic/fetch/base.py`, `src/tests/fetch/test_fetcher.py`
- `src/tests/test_cli.py` is in the Definition of Done because its sync tests run the CLI against the replay server and assert that only built resources are synced; Task 10 updates what they expect, so here only check that the failures are the expected ones (default groups now sync `issues` and `pull_requests`) and record them in Notes for Task 10.
- If the decision in review-2.md is answered with option B (always query), the probe branch of the unchanged rule goes and `pull_requests` and `issues` are never unchanged.

---

## Task 6: Flow fixture data for stats

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** stats spec Metric groups (`flow`), Aggregation (user subject); shared testing rule (a known-good input/output pair)

**Technical Goal:** Give the stats, reports and CLI tests a small set of pull requests and issues in the existing `stats_cache`, with totals checked by hand, so every later flow test checks numbers already known to be right.

**Subtasks:**

- [ ] In `src/tests/fixtures/stats.py`, add `PULL_REQUESTS` and `ISSUES` for the existing repos (`ALPHA`, `BETA`, `GAMMA`) inside `SINCE` to `UNTIL`, covering: merged, closed-unmerged and open pull requests; one with no qualifying review; a bot author (`dependabot[bot]`); an unattributed author; one created before `SINCE` and merged inside it; a merge just before midnight UTC that falls on the next day in `Europe/Berlin`; a reopened issue (no `closed_at`); a closed issue; at least two merged pull requests in one month so the p50 and p90 differ; one month with no merged pull request so its duration buckets are absent; on `GAMMA`, items by `octocat` and by someone else for the user-subject rule
- [ ] Add hand-checked expectations: `ORG_FLOW_BY_MONTH_UTC` (each flow series' monthly values, absent buckets left out), `ORG_FLOW_BY_MONTH_BERLIN` for the series the midnight case moves, and `USER_FLOW_TOTAL_UTC` for `USER`; write the arithmetic for each p50, p90 and size in a comment, with the date it was checked
- [ ] Extend the `stats_cache` fixture in `src/tests/conftest.py` with a helper (beside `store_commits`) that writes the records and an `issues` and `pull_requests` sync state per repo, with `synced_at` equal to that repo's existing `*_SYNCED_AT`, so `fetched_at:` provenance and the CLI's `--max-age` tests see one time per repo for every resource
- [ ] Tests in `src/tests/stats/test_fixtures.py`: every record is inside the range or deliberately outside it as named; the expectations' counts equal a direct count over the records (a cross-check, not a replacement for the hand check)

**Acceptance Criteria:**

- [ ] Every value in the flow expectations was checked by hand and the arithmetic is in the fixture
- [ ] The activity fixtures and their expectations are unchanged

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/stats/test_fixtures.py src/tests/stats/test_compute.py src/tests/reports src/tests/test_cli.py` passes, apart from the tests that assert `flow` is unavailable, which Tasks 8, 9 and 10 update (list them in Notes)

**Notes:**

- Depends on Task 1 (records and cache methods)
- Key files: `src/tests/fixtures/stats.py`, `src/tests/conftest.py`, `src/tests/stats/test_fixtures.py`
- Keep it small: a few items per repo, as the shared testing rule asks.

---

## Task 7: The pure `flow` aggregation

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** stats spec Module location (`flow.py`); Metric groups (`flow`); Aggregation (empty buckets absent for medians, no flow breakdowns, series order); review-2.md choices 10, 11, 12 and 14

**User Story:** As a maintainer of a repo or an org, I want pull requests opened and merged, issues opened and closed, review, merge and close times and pull request size per period, so that I can see whether work is flowing faster or slower over time.

**Subtasks:**

- [ ] Add `src/wambatic/stats/flow.py` with `FLOW_METRICS` (the spec's series order with each unit) and `aggregate(pull_requests, issues, buckets, tz) -> list[Series]`: the four counts zero-filled over every bucket; the six duration series and `pr_size_p50` with a point only in buckets that have values; each event placed by the local date of its own end time in `tz`; events outside the buckets' range ignored; p50 by `statistics.median`, p90 by `statistics.quantiles(values, n=10, method='inclusive')[8]`, size by `statistics.median_low`, hours as `total_seconds() / 3600`
- [ ] Reuse the bucket location helper `activity.py` already uses (`locate`, or whatever it is called) rather than writing a second one; move it to `buckets.py` if `flow.py` importing `activity.py` would be the only reason for that edge
- [ ] Write `src/tests/stats/test_flow.py`: the `ORG_FLOW_BY_MONTH_UTC` and `ORG_FLOW_BY_MONTH_BERLIN` expectations from Task 6; `TOTAL` gives one bucket whose counts equal the number of events in range; a closed-unmerged pull request is in no count; a reopened issue is not in `issues_closed` or `time_to_close`; a pull request with no review is in `prs_merged` but not `time_to_first_review`; one value gives p50 equal to p90; series come in `FLOW_METRICS` order with units `count`, `hours` and `lines`
- [ ] Hypothesis tests (`@hypothesis.settings(max_examples=20, deadline=10000)`): for any list of pull requests with ordered times and any granularity, each count summed over buckets equals the number of its events in range; every duration point satisfies `min <= p50 <= p90 <= max` of that bucket's values; `pr_size_p50` is always one of the sizes

**Acceptance Criteria:**

- [ ] `flow.py` performs no I/O and imports nothing outside `wambatic.fetch.base`, `wambatic.settings` and `wambatic.stats`
- [ ] Empty buckets are zero for counts and absent for durations and size

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/stats/test_flow.py src/tests/stats/test_activity.py src/tests/stats/test_buckets.py` passes

**Notes:**

- Depends on Task 6
- Key files: `src/wambatic/stats/flow.py`, `src/tests/stats/test_flow.py`; `src/wambatic/stats/buckets.py` if the helper moves
- Modelled on `activity.py`; Task 12 checks for anything duplicated between them.
- [`statistics.quantiles`](https://docs.python.org/3.14/library/statistics.html#statistics.quantiles), [`statistics.median_low`](https://docs.python.org/3.14/library/statistics.html#statistics.median_low)

---

## Task 8: `flow` in `compute`

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** stats spec Error handling (`EmptySubjectError`); Implementation (Range, Reading the cache, Groups not built yet); Aggregation (user subject, series order); Provenance; review-2.md choices 13 and 15

**User Story:** As a wambatic user, I want the default report to include flow alongside activity, read from the cache only, so that one command shows both who committed and how pull requests and issues moved.

**Subtasks:**

- [ ] In `src/wambatic/stats/compute.py`, add `flow` to `BUILT_GROUPS` and remove it from `UNBUILT_GROUP_STEPS`
- [ ] Read pull requests and issues for each repo when `flow` is requested, with the widened lower instant (`since - 1 day` in UTC, or `None`), and for a `user` subject keep only items whose `author_login` matches the login case-insensitively, as `read_commits` does
- [ ] Resolve a `None` `since` from the earliest record over every requested built group (commit `authored_at`, pull request and issue `created_at`)
- [ ] Raise `EmptySubjectError` only when no requested built group has a record in range (name the groups in the message); run `activity.aggregate` with an empty commit list when only flow has records, and check that it zero-fills (fix it if it does not)
- [ ] Order the series: activity totals, flow totals, then breakdowns; provenance from `resources_for(built)`, so it carries `fetched_at:issues` and `fetched_at:pull_requests`
- [ ] Update the tests in `src/tests/stats/test_compute.py` that expect `flow` to be unavailable or unbuilt (`test_the_default_request_lists_flow_as_unavailable_and_still_returns_activity`, and the `EmptySubjectError` cases matching `flow (step 6)`): the default request now has flow series and no `flow` row in `tables['unavailable']`; `{'flow'}` alone computes; `{'delivery'}` alone still raises naming step 8
- [ ] New tests in `src/tests/stats/test_compute.py`: the org result's flow series equal `ORG_FLOW_BY_MONTH_UTC`, and in `Europe/Berlin` the Berlin expectation; the user result counts only `octocat`'s items (`USER_FLOW_TOTAL_UTC`); `groups={'flow'}` with `since=None` starts at the earliest pull request or issue's bucket; a range with pull requests but no commits gives zero activity and the flow values; a range with neither raises `EmptySubjectError`; provenance has both new `fetched_at:` keys; series order is activity, flow, breakdowns

**Acceptance Criteria:**

- [ ] `compute` never syncs and reads only through `Fetcher` (no new import of `wambatic.fetch.cache`)
- [ ] The step 4 activity expectations still hold unchanged

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/stats/test_compute.py src/tests/stats/test_flow.py src/tests/stats/test_activity.py` passes

**Notes:**

- Depends on Tasks 4 (the `Fetcher` read methods) and 7
- Key files: `src/wambatic/stats/compute.py`, `src/tests/stats/test_compute.py`

---

## Task 9: Terminal flow sections

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** reports spec 1.3 (Implementation, Terminal: conditional sections, item 3 Trends, item 6 Flow by period, item 7 Flow times by period); review-2.md choice 16

**User Story:** As a wambatic user, I want the terminal report to show pull request and issue counts and times per period beside the activity table, so that I can read flow at a glance without JSON.

**Subtasks:**

- [ ] In `src/wambatic/reports/terminal.py`, print items 2 to 5 only when the result has activity series and items 6 and 7 only when it has flow series; take the bucket list from whichever total series is present instead of `series['commits']`
- [ ] Trends: one line per total series whose unit is `count`, `days` or `lines`, activity metrics first then the four flow counts, with the existing cropping
- [ ] Flow by period: Period, PRs opened, PRs merged, Issues opened, Issues closed, partial marks and caption as the activity table, `Total` footer with more than one bucket
- [ ] Flow times by period: Period, Review p50, Review p90, Merge p50, Merge p90, Close p50, Close p90 with one decimal place, PR size p50 as an integer, `-` for an absent point, no `Total` row, caption `hours; - no data` (combined with `* partial period` when there is a partial bucket)
- [ ] Take metric names from `wambatic.stats.flow` as the activity names come from `wambatic.stats.activity`; no metric logic beyond summing the counts
- [ ] Regenerate `ORG_MONTH_TERMINAL` in `src/tests/fixtures/reports.py` from the renderer, check every new number by hand against `ORG_FLOW_BY_MONTH_UTC` and the layout against the spec, and record the date of the check in its comment; `flow` no longer appears under Unavailable
- [ ] Tests in `src/tests/reports/test_terminal.py`: the known-good rendering; a `groups={'flow'}` result prints no Activity, By repository or Top contributors tables and does print both flow tables and the flow trend lines; a `groups={'activity'}` result prints no flow tables; an absent duration point shows `-`; `repo_total_result` (one bucket) has no `Total` row in Flow by period; at width 40 the flow trend lines fit

**Acceptance Criteria:**

- [ ] Nothing in the output depends on colour
- [ ] Every number in the regenerated known-good rendering was checked by hand

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/reports/test_terminal.py src/tests/reports/test_base.py` passes

**Notes:**

- Depends on Task 8
- Key files: `src/wambatic/reports/terminal.py`, `src/tests/fixtures/reports.py`, `src/tests/reports/test_terminal.py`
- `src/tests/reports/test_base.py` is in the Definition of Done because the `org_result` fixture now carries flow series; JSON output needs no change (`hours` values are floats, the others integers), and `FORMAT_VERSION` stays 1 because no key changes meaning.
- `format_number` gives two decimals for floats; the times table needs one, so add a precision argument rather than a second formatter.

---

## Task 10: CLI: sync log, `cache info` and flow in the report

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** reports spec 1.3 (Running `report` step 5, the sync log line; `cache info`); review-2.md choice 9

**User Story:** As a wambatic user, I want the sync line to say what it wrote for each resource and `cache info` to count pull requests and issues, so that I can see that flow data arrived.

**Subtasks:**

- [ ] In `src/wambatic/cli.py`, make `log_sync` give the rows written per resource in `SyncReport.rows_written` order by name (`commits 12, issues 3, pull_requests 5`) instead of a commit total
- [ ] Add `pull requests` and `issues` rows to the `cache info` table after `commits`
- [ ] Update the tests in `src/tests/test_cli.py` that assume flow is unbuilt: `test_the_default_groups_sync_only_commits_and_list_flow_as_unavailable` becomes a test that the default groups sync `commits`, `issues` and `pull_requests` (the replay server receives the listing, history and both flow queries) and that Unavailable has no `flow` row; the `--groups flow` case now prints the flow tables from the `stats_cache` file with `--no-fetch` instead of raising; the replay routes for sync tests gain `PULL_REQUESTS` and `ISSUES` pages; the failures Task 5 recorded all pass
- [ ] New tests in `src/tests/test_cli.py`: the sync log line names each resource's count; `cache info` on the `stats_cache` file prints the pull request and issue counts; a `--max-age 30d` report with a clock one day after the fixture's sync times still makes no request (every resource's `fetched_at` is fresh, from Task 6)

**Acceptance Criteria:**

- [ ] `wambatic report repo:octo-org/alpha --no-fetch` from the `stats_cache` file prints the activity and flow tables with no token and no session
- [ ] Only resources in `BUILT_RESOURCES` are ever passed to `Fetcher.sync` (the existing test still holds)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Tasks 5, 6 and 9
- Key files: `src/wambatic/cli.py`, `src/tests/test_cli.py`

---

## Task 11: README

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** shared user-guides rule (keep guides in sync with code); reports spec 1.3 Terminal; fetch spec 1.5 Cache (schema 2); review-2.md choices 3, 8, 12 and 17

**User Story:** As a wambatic user upgrading from the activity-only release, I want the README to say what the flow tables mean, what the upgrade does to my cache and what the token needs, so that the new numbers are not a surprise.

**Subtasks:**

- [ ] In `README.md`: the opening paragraph and "A first report" list name the flow tables; a short Flow section says what each metric counts, by which date it is bucketed, that review time leaves out the author and bots, that durations are hours and p50/p90, and that bots count; `--groups` no longer says only `activity` is built (`delivery` is still listed as not built); the Unavailable bullet and Limits no longer name flow
- [ ] The cache section says a cache from an earlier wambatic is refused once after this upgrade and that `wambatic cache clear` then a report refetches it; `cache info` lists pull request and issue counts
- [ ] Correct the `stats.hotfix_labels` row to "For the delivery group, which is not built yet"
- [ ] Check the token paragraph: reading pull requests and issues of a public repository needs no scope beyond `public_repo`, a private one `repo` (from the fetch spec's External dependencies; change nothing if it already says so)
- [ ] Run every README example that needs no network against a cache built from the stats fixtures, or with `--help`, and check its output matches the README
- [ ] Keep counts out of the prose (shared counts-in-prose rule) and use British spelling

**Acceptance Criteria:**

- [ ] Every flow metric name the JSON output carries appears in the README
- [ ] No sentence says the flow group is not built

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/test_cli.py` passes

**Notes:**

- Depends on Task 10
- Key files: `README.md`

---

## Task 12: Exports, layering and closing checks

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** fetch spec 1.5 API; stats spec Module location; system spec Architecture (layering); implementation order step 6 "Done when"

**Technical Goal:** Expose the step 6 names, keep the layering enforced, remove what the new code duplicated, run every test the list can reach, and mark the step done.

**Subtasks:**

- [ ] Check `wambatic.fetch.__all__` has `Issue` and `PullRequest` (Task 1); `wambatic.stats` needs no new export (`flow` is internal, as `activity` is)
- [ ] Extend `src/tests/test_package.py`: `wambatic.fetch.Issue` and `wambatic.fetch.PullRequest` resolve, and `BUILT_RESOURCES` contains `issues` and `pull_requests`
- [ ] Check `src/tests/test_layering.py` covers `wambatic.stats.flow` (it scans every module; confirm with a run, and add a case only if it does not)
- [ ] Hoist anything the new modules duplicate to a single owner: grep the tree for each literal collection, constant and one-line helper that `flow.py`, the new cache methods, the parse functions, the new terminal tables and the test fixtures define (bucket location, record-to-row and row-to-record conversion, the upsert SQL pattern, the `[bot]` suffix, the period-table construction, metric name tuples), and import rather than copy, choosing the owner from the existing import graph and preferring a module the consumer already imports
- [ ] Check the implementation order's "Done when" for step 6 and record in this task's Notes the test that shows each item: a changed PR updated and unchanged ones untouched, and the interval removing a deleted issue (Task 4); an unchanged repo costing no per-repo request (Task 5); the default report with nothing unavailable for flow (Tasks 8 and 10)
- [ ] Run every test that imports a changed module directly or transitively: `pytest src/tests/fetch src/tests/stats src/tests/reports src/tests/test_cli.py src/tests/test_package.py src/tests/test_layering.py`
- [ ] In `agents/specs/implementation-order.md`, set step 6's Status to `done: [tasks-2](../tasks/stats/tasks-2.md)`

**Acceptance Criteria:**

- [ ] Every step 6 "Done when" item is met, or its gap is recorded in the task that owns it
- [ ] No new duplication between `flow.py` and `activity.py`, or between the commit and the pull request and issue code in `cache.py` and `base.py`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch src/tests/stats src/tests/reports src/tests/test_cli.py src/tests/test_package.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Tasks 1 to 11
- The project has no affected-tests tool; the command above names every test file that reaches a module this list changed (`wambatic.fetch` is reached by the fetch, stats, reports and CLI tests, `wambatic.stats` by the stats, reports and CLI tests, `wambatic.reports` and `wambatic.cli` by the reports and CLI tests, and the package and layering tests check the whole tree).
- `src/tests/fetch/test_live.py` needs a working `GITHUB_TOKEN` and gets a 401 in cloud sessions, as on `main`; CI's `live` job runs it. Record that here if it is the only failure.
- No spec's `**Status:**` changes (see the header).
- Key files: `src/tests/test_package.py`, `src/tests/test_layering.py`, `agents/specs/implementation-order.md`
