# Tasks: Stats

**Spec:** `agents/specs/stats/spec.md`
**Created:** 2026-10-29
**Version:** 1

This list builds step 4 of the [implementation order](../../specs/implementation-order.md), "Activity stats with bucketing": the stats records and errors, bucketing by year, month, ISO week, day and total in any timezone, the pure `activity` aggregation (commits, contributors, active days, lines added, deleted and net, merges excluded, per repo and per author), `compute` reading the cache through `Fetcher`, and provenance. It is written against version 1.1 of the spec, which settled what 1.0 left open for this step; the gaps and the choices made are in [review-1.md](../../specs/stats/review-1.md). It also adds `Fetcher.provenance` and `Cache.version_override_at` from version 1.3 of the [fetch spec](../../specs/fetch-and-cache/spec.md). The step 3 list, [fetch-and-cache/tasks-2.md](../fetch-and-cache/tasks-2.md), built the `Fetcher.repos()` and `Fetcher.commits()` this list reads.

## Spec coverage

| Spec section | Covered by |
|--------------|------------|
| Module location (`errors.py`, `base.py`, `buckets.py`, `activity.py`, `compute.py`) | Tasks 1, 2, 5 and 7 |
| Module location (`flow.py`, `delivery.py`) | steps 6 and 8 |
| API: `GROUPS`, `Granularity`, `Bucket`, `Series`, `StatsRequest`, `StatsResult` | Task 1 |
| API: `bucket_for`, `bucket_range`, `partial_buckets` | Task 2 |
| API: `resources_for`, `compute` | Task 7 |
| Error handling (every stats error, validation order) | Tasks 1 and 7 |
| Implementation: local dates, ISO weeks, labels, half-open buckets | Task 2 |
| Implementation: Range | Tasks 2 and 7 |
| Implementation: Reading the cache (widened window) | Task 7 |
| Implementation: Partial buckets | Tasks 2 and 7 |
| Implementation: Groups not built yet (`tables['unavailable']`) | Task 7 |
| Metric groups: activity (`commits`, `contributors`, `active_days`, lines) | Task 5 |
| Metric groups: activity (`top_contributors`) | Task 6 |
| Metric groups: activity (`stars`, `forks`, `watchers`, `languages`) | listed unavailable in Task 7; built in step 8 |
| Metric groups: flow, delivery | steps 6 and 8 (unavailable in Task 7) |
| Aggregation (user, repo, org subjects; breakdowns; zero fill; ordering; sums) | Tasks 5, 6 and 7 |
| Provenance | Tasks 3 and 7 |
| Settings (`bot_logins`, `exclude_merge_commits`; `timezone` is step 5's CLI) | Tasks 5 and 6 |
| Settings (`deploy_workflow`, `failure_window`, `hotfix_labels`) | step 8 |
| System spec API (`StatsRequest`, `StatsResult`, `compute` re-exported from `gitstat`) | Task 8 |
| Implementation order step 4 "Done when" | Tasks 2 and 4 to 7; checked in Task 8 |

The spec's `**Status:**` is not changed by this list: the `flow` and `delivery` groups are built by the step 6 and step 8 lists, and the last of them sets it to `implemented`.

## Conventions for every task

- Async tests are plain `def test_...() -> None` functions whose body calls `asyncio.run(...)` on an inner coroutine; no pytest async plugin is added (as in the fetch tests).
- Hypothesis tests use `@hypothesis.settings(max_examples=20, deadline=10000)` (shared testing rule).
- Every cache in a test lives under pytest's `tmp_path`; no test touches `~/.cache`, and no stats test reaches the network.
- Times passed between modules are timezone-aware; `datetime.UTC` and `zoneinfo.ZoneInfo` zones only, never naive datetimes.
- Logins are compared with `str.casefold()` wherever the spec says case-insensitively (the subject login of a `user` subject and `stats.bot_logins`); the login stored in a result is the one GitHub reported.
- `gitstat.stats` modules import nothing from gitstat outside `gitstat.stats`, `gitstat.fetch`, `gitstat.settings` and `gitstat.version`; Task 8 makes `src/tests/test_layering.py` enforce it.
- No dependency is added: `bisect`, `datetime` and `zoneinfo` are stdlib.

---

## Task 1: Records and errors

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** API (`GROUPS`, `Granularity`, `Bucket`, `Series`, `StatsRequest`, `StatsResult`); Error handling; Module location (`errors.py`, `base.py`)

**Technical Goal:** Define the frozen types and typed errors every later task passes around, so the bucketing, aggregation and `compute` tasks only add behaviour.

**Subtasks:**

- [ ] Add `src/gitstat/stats/errors.py` with `StatsError(Exception)` and its subclasses `EmptySubjectError`, `InvalidRangeError`, `InvalidRequestError` and `UnknownGroupError`, each taking a message
- [ ] Add `src/gitstat/stats/base.py` with `GROUPS`, `Granularity`, `Bucket` (`order=True`), `Series` (with `by_kind`), `StatsRequest` (with `settings`) and `StatsResult` (with `since` and `until`) exactly as the spec's API: frozen, slotted dataclasses; field names, types and defaults as written
- [ ] `Series.__post_init__` raises `ValueError` when exactly one of `by` and `by_kind` is `None`
- [ ] Import `Subject` for `StatsResult` from `gitstat.fetch` at run time (it is a dataclass field type, so mypy and `dataclasses` need it); import `Fetcher` nowhere in this module
- [ ] Write `src/tests/stats/__init__.py` and `src/tests/stats/test_base.py`: `GROUPS` is exactly `{'activity', 'delivery', 'flow'}`; `Granularity` has the five values in the spec; `StatsRequest()` has the spec's defaults, including `StatsSettings()`; buckets sort by `start`; records are immutable (`dataclasses.FrozenInstanceError`); `Series` with `by` and no `by_kind`, or the reverse, raises `ValueError`
- [ ] Write `src/tests/stats/test_errors.py`: every error is a `StatsError`, and `StatsError` is not a `FetchError` (front ends catch them separately)

**Acceptance Criteria:**

- [ ] `base.py` and `errors.py` perform no I/O
- [ ] `StatsRequest` is hashable (frozen, and `StatsSettings` holds tuples), so a request can key a cache in the web app later

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/stats/test_base.py src/tests/stats/test_errors.py` passes

**Notes:**

- Depends on fetch-and-cache/tasks-2.md Task 12 (step 3), done
- `src/gitstat/stats/__init__.py` exists and is empty; exports are added in Task 8.
- Key files: `src/gitstat/stats/base.py`, `src/gitstat/stats/errors.py`, `src/tests/stats/test_base.py`, `src/tests/stats/test_errors.py`

---

## Task 2: Bucketing

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`bucket_for`, `bucket_range`, `partial_buckets`); Implementation (local dates, ISO weeks, labels, half-open buckets; Range; Partial buckets); implementation order step 4 "Done when" (buckets partition any date range with no gaps or overlaps)

**User Story:** As a gitstat user, I want every commit counted in exactly one period of my chosen size in my own timezone, with ISO weeks labelled by their ISO year, so that totals per period add up to the whole and line up with my calendar.

**Subtasks:**

- [ ] Add `src/gitstat/stats/buckets.py` with an internal `bucket_start(day, granularity) -> datetime.date`: the year's 1 January, the month's 1st, the ISO week's Monday (`date.fromisocalendar(y, w, 1)`), or the day itself; `ValueError` for `TOTAL`
- [ ] An internal `next_start(start, granularity) -> datetime.date`: the start of the following bucket (next 1 January, next month's 1st, `start + 7 days`, `start + 1 day`)
- [ ] An internal `label(start, granularity) -> str`: `'2026'`, `'2026-10'`, `f'{iso_year}-W{iso_week:02d}'` from `start.isocalendar()`, `'2026-10-29'`
- [ ] `bucket_for(when, granularity, tz)`: `ValueError` for a naive `when` and for `TOTAL`; otherwise the bucket of `when.astimezone(tz).date()`
- [ ] `bucket_range(since, until, granularity)`: `ValueError` when `since > until`; `[Bucket(since, 'total')]` for `TOTAL`; otherwise from `bucket_start(since)` by `next_start` while the start is `<= until`
- [ ] `partial_buckets(since, until, buckets)`: the first bucket when `since > first.start`, the last when `until < next_start(last.start) - 1 day`, each once; `[]` for a `TOTAL` bucket
- [ ] Write `src/tests/stats/test_buckets.py` with known cases: labels for each granularity; `2026-12-31` and `2027-01-01` both in `2026-W53` and `2027-01-04` in `2027-W01`; `2025-12-29` in `2026-W01`; a commit at `2026-12-31T23:30Z` is in month `2026-12` in UTC and `2027-01` in `Europe/Berlin`; a commit at `2026-03-29T23:30Z` is on `2026-03-30` in `Europe/London` (summer time began that morning) while one at `2026-03-28T23:30Z` stays on `2026-03-28`; `TOTAL` raises in `bucket_for`; a range of one day at `YEAR` gives one bucket that `partial_buckets` names as partial; a range of whole months at `MONTH` has no partial bucket
- [ ] Write hypothesis tests in the same file, for any `since <= until` within years 1971 to 2100 and every granularity except `TOTAL`: consecutive buckets have `next_start(a.start) == b.start` (no gaps, no overlaps); the first bucket contains `since` and the last contains `until`; every date in a sample of the range (`since`, `until` and dates drawn between them) maps through `bucket_for` (at noon UTC, `tz=UTC`) to exactly one bucket of the range; labels are unique and in the same order as starts
- [ ] Write a hypothesis test that for any aware datetime and any zone from `hypothesis.strategies.timezones()`, `bucket_for(...).start <= when.astimezone(tz).date() < next_start(start)`

**Acceptance Criteria:**

- [ ] Buckets partition any range: shown by the hypothesis tests
- [ ] A week's label carries its ISO year, not the calendar year of its start

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/stats/test_buckets.py` passes

**Notes:**

- Depends on Task 1
- 2026 has 53 ISO weeks because 1 January 2026 is a Thursday ([ISO week date](https://en.wikipedia.org/wiki/ISO_week_date)); check each hand-written date with `datetime.date.isocalendar()` before relying on it.
- Python's `datetime.date.fromisocalendar` and `isocalendar` implement ISO 8601 weeks ([datetime docs](https://docs.python.org/3.14/library/datetime.html#datetime.date.isocalendar)).
- `hypothesis.strategies.timezones()` needs the system tz database (present on the Linux CI runner and on macOS); if it is absent, the test must fail rather than skip, so the gap is seen.
- Key files: `src/gitstat/stats/buckets.py`, `src/tests/stats/test_buckets.py`

---

## Task 3: Fetch provenance

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** Provenance; fetch spec 1.3 API (`Fetcher.provenance`, `Cache.identity`, `Cache.version_override_at`)

**Technical Goal:** Let stats record the cache identity, any version override and the fetch times without reaching around `Fetcher` into the cache, as the system spec's layering requires.

**Subtasks:**

- [ ] Add `Cache.version_override_at() -> str | None` to `src/gitstat/fetch/cache.py`, reading the `meta` row under the cache lock
- [ ] Add `Fetcher.provenance(subject, resources) -> dict[str, str]` to `src/gitstat/fetch/base.py`: `identity()`, then `version_override_at` when recorded, then for each resource in sorted order `fetched_at:<resource>` = the earliest `synced_at` (ISO UTC) over `repos(subject)`, or `'never'` when one of those repos has no `sync_state` row for it; cache calls go through `self.db`
- [ ] A resource name outside `RESOURCES` raises `ValueError` naming it, as `sync` does; an unbuilt resource is allowed (it reads `'never'`)
- [ ] Write tests in `src/tests/fetch/test_cache.py`: `version_override_at()` is `None` for a matching cache and the recorded time after opening with `ignore_version=True` over a difference
- [ ] Write tests in `src/tests/fetch/test_fetcher.py`: after syncing two repos at different clock times, `fetched_at:commits` is the earlier time; a repo listed but never synced gives `'never'`; the identity keys are present; the call sends no request (the replay server records none)

**Acceptance Criteria:**

- [ ] `provenance()` reaches no network
- [ ] An overridden cache is visible in the result's provenance (shared versions rule: the output records that the override was used)

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/fetch/test_cache.py src/tests/fetch/test_fetcher.py` passes

**Notes:**

- Depends on fetch-and-cache/tasks-2.md Task 12, done. Independent of Tasks 1 and 2.
- A repo listed but never synced has a `repos` row and no `sync_state` row; `Cache.upsert_repos` then no `write_commits` produces it.
- Key files: `src/gitstat/fetch/cache.py`, `src/gitstat/fetch/base.py`, `src/tests/fetch/test_cache.py`, `src/tests/fetch/test_fetcher.py`

---

## Task 4: Known-good activity fixture

**Status:** todo
**Priority:** high
**Complexity:** small
**Spec Reference:** Metric groups (activity); Aggregation; implementation order step 4 "Done when" (known-good fixture totals match by hand)

**Technical Goal:** Write one small set of commits whose totals are worked out by hand, so the aggregation and `compute` tests compare against numbers nobody computed with the code under test.

**Subtasks:**

- [ ] Add `src/tests/fixtures/stats.py` with `REPOS` (`octo-org/alpha` and `octo-org/beta` for an org subject, and `octocat/gamma` for a user subject) and `COMMITS`, about a dozen `Commit` records chosen to hit: a merge commit with non-zero line counts; an unattributed commit (`author_login=None`); a `dependabot[bot]` commit; one author with two commits on the same day; one author whose login appears in two cases across the org repos (`Octocat` and `octocat`), counted as one contributor; in `octocat/gamma`, commits by `Octocat` and by one other author; a commit at `2026-12-31T23:30Z` (December in UTC, January 2027 in `Europe/Berlin`); commits in ISO week `2026-W53` on both sides of the new year; and a month with no commits between two that have some
- [ ] In the same module, write the expected values for the org subject (`octo-org/alpha` and `octo-org/beta`) by hand as literal dicts, with a comment per figure showing the sum it came from: `commits`, `contributors`, `active_days`, `lines_added`, `lines_deleted` and `lines_net` per month in UTC for the range `2026-10-01` to `2027-01-31`; the same by month in `Europe/Berlin`; the `TOTAL` values; and the `top_contributors` rows
- [ ] Add a `stats_cache` fixture to `src/tests/conftest.py` that opens a `Cache` under `tmp_path`, stores `REPOS` with `upsert_repos(owner, ..., complete=True)` per owner and each repo's commits with `write_commits(..., replace=True)` and a `SyncState` with a fixed `synced_at`, and returns the cache; and a `stats_fetcher` fixture returning `Fetcher('test-token', stats_cache, FetchSettings())`, never entered, so any network use fails
- [ ] Write `src/tests/stats/test_fixtures.py`: the fixture's own consistency (every `lines_net` equals added minus deleted, and the month values sum to the `TOTAL` values) and that `stats_fetcher.commits()` returns every fixture commit

**Acceptance Criteria:**

- [ ] Every expected figure is a literal, with its derivation in a comment, not computed from `COMMITS` in code
- [ ] The fixture loads through the real `Cache`, so `compute` tests exercise the cache's ordering and bounds

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/stats/test_fixtures.py` passes

**Notes:**

- Depends on Task 1
- Shared testing rule: fixtures live in `src/tests/fixtures/` named after the source module, and are loaded in `src/tests/conftest.py`.
- Key files: `src/tests/fixtures/stats.py`, `src/tests/conftest.py`, `src/tests/stats/test_fixtures.py`

---

## Task 5: Activity totals

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** Metric groups (activity: `commits`, `contributors`, `active_days`, `lines_added`, `lines_deleted`, `lines_net`); Aggregation (zero fill; ordering); Settings (`bot_logins`, `exclude_merge_commits`)

**User Story:** As a gitstat user, I want commits, contributors, active days and lines added, deleted and net per period, with merge commits left out of line counts, so that I can see how much work landed and how much code changed without double counting merges.

**Subtasks:**

- [ ] Add `src/gitstat/stats/activity.py` with a pure `aggregate(commits, buckets, tz, settings, *, by_author, by_repo) -> tuple[list[Series], dict[str, list[dict[str, typing.Any]]]]`; this task builds the total series, Task 6 the breakdowns and table
- [ ] Place each commit in its bucket by `bisect.bisect_right` over the bucket starts with the commit's local date; a commit outside the buckets raises `ValueError` (the caller filters by range first)
- [ ] `commits` counts every commit; `lines_added` and `lines_deleted` sum non-merge commits when `settings.exclude_merge_commits`, all commits otherwise; `lines_net` is their difference
- [ ] `contributors` counts distinct `author_login.casefold()` per bucket, leaving out `None` and every login in `settings.bot_logins` (casefolded)
- [ ] `active_days` counts distinct local dates per bucket
- [ ] Every series has a point for every bucket, in bucket order, zero where nothing happened; units as the spec (`count`, `days`, `lines`); series in the spec's order
- [ ] Write `src/tests/stats/test_activity.py`: the Task 4 fixture by month in UTC and in `Europe/Berlin`, and by `TOTAL`, equals the hand-written values; with `exclude_merge_commits=False` the merge commit's lines are added; a bot commit counts in `commits` and lines but not `contributors`; `Octocat` and `octocat` are one contributor; an empty month is present with zeros
- [ ] Write hypothesis tests: for any list of commits within a range, the sum of `lines_added` points equals the sum of non-merge additions, `commits` points sum to the list's length, `lines_net == lines_added - lines_deleted` in every bucket, and `contributors` and `active_days` in a bucket never exceed its `commits`

**Acceptance Criteria:**

- [ ] `aggregate` performs no I/O and does not await (system spec: pure core)
- [ ] The hand-written fixture totals match exactly

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/stats/test_activity.py` passes

**Notes:**

- Depends on Task 2, Task 4
- Filtering by a `user` subject's login is `compute`'s job (Task 7), before `aggregate`; `aggregate` counts what it is given.
- Key files: `src/gitstat/stats/activity.py`, `src/tests/stats/test_activity.py`

---

## Task 6: Breakdowns and top contributors

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** Aggregation (breakdown series by author and by repo; ordering; sums); Metric groups (activity: `top_contributors`); Error handling (`unattributed`)

**User Story:** As a gitstat user reporting on a repository or organisation, I want the same line and commit series per author and per repository, and a table of top contributors, so that I can see who and which repos the change came from.

**Subtasks:**

- [ ] In `aggregate`, with `by_author`, add `commits`, `lines_added`, `lines_deleted` and `lines_net` series per author with `by_kind='author'`: `by` is the login as GitHub reported it (the first spelling seen for a casefolded login, in commit order) or `'unattributed'`; bots get series too
- [ ] With `by_repo`, add the same four series per `commit.repo` with `by_kind='repo'`
- [ ] Order breakdown series by `by_kind` (`author` first), then `by`, then metric, after the totals; fill every bucket with zeros
- [ ] Build `tables['top_contributors']` over all buckets for every call: one row per casefolded login, plus one `'unattributed'` row when there are unattributed commits, bots left out; keys `login`, `commits`, `lines_added`, `lines_deleted`, `lines_net`, `active_days`; merge rule as the series; ordered by `commits` descending then `login`
- [ ] Write tests in `src/tests/stats/test_activity.py`: the fixture's per-author and per-repo series and `top_contributors` rows equal the hand-written values; `Octocat` and `octocat` share one series and one row; the unattributed commit has a series and a row; a bot has a series but no row; without `by_author` there are no author series, without `by_repo` no repo series
- [ ] Write a hypothesis test: for any commits, per-author series summed over authors equal the totals for each of the four metrics in every bucket, and the same for per-repo series

**Acceptance Criteria:**

- [ ] No commit is dropped from the breakdowns: the sums equal the totals
- [ ] Series order is deterministic for the same input

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/stats/test_activity.py` passes

**Notes:**

- Depends on Task 5
- The spec's sum property holds for `commits` and the three line metrics; `contributors` and `active_days` have no breakdown.
- Key files: `src/gitstat/stats/activity.py`, `src/tests/stats/test_activity.py`, `src/tests/fixtures/stats.py`

---

## Task 7: `compute`

**Status:** todo
**Priority:** high
**Complexity:** medium
**Spec Reference:** API (`compute`, `resources_for`); Error handling (all, and the validation order); Implementation (Range; Reading the cache; Partial buckets; Groups not built yet); Aggregation (user, repo and org subjects); Provenance

**User Story:** As a gitstat front end, I want one call that turns a subject and a request into a complete, traceable result from the cache, so that the terminal report, HTML report and web app all show the same numbers and none of them reaches the network through stats.

**Subtasks:**

- [ ] Add `src/gitstat/stats/compute.py` with `resources_for(groups)` per the spec's mapping; an unknown group raises `UnknownGroupError` naming each, sorted
- [ ] `compute` validates in the spec's order before any cache read: unknown groups (`UnknownGroupError`), `by_author` with a `user` subject (`InvalidRequestError`), then `since > until` when both are given (`InvalidRangeError`)
- [ ] Split the requested groups into built (`activity`) and unbuilt (`flow` step 6, `delivery` step 8); with no built group, raise `EmptySubjectError` naming the steps
- [ ] Read `fetcher.repos(subject)`; none raises `EmptySubjectError`
- [ ] Read each repo's commits with `fetcher.commits(repo, lo, hi)`, where `lo` and `hi` are the given bounds as UTC instants widened by one day (or `None` when a bound is `None`); keep a commit when its local date is in `[since, until]`; for a `user` subject, also keep only commits whose `author_login.casefold()` equals `subject.login.casefold()`
- [ ] Resolve the range: `since` `None` gives the bucket start of the earliest kept commit's local date (that date itself for `TOTAL`); `until` `None` gives `clock()`'s date in `tz`; after resolving, `since > until` raises `InvalidRangeError`; no kept commit raises `EmptySubjectError`
- [ ] Build buckets with `bucket_range`, call `activity.aggregate` with `by_repo` true for `user` and `org` subjects and `by_author` from the request
- [ ] Add `tables['unavailable']` rows for each unbuilt requested group, and, when `activity` is requested, for `stars` (step 8), `forks`, `watchers` and `languages` (step 8, fetch resource not yet specified), each reason naming the step
- [ ] Build `provenance`: `await fetcher.provenance(subject, resources_for(built groups))`, then `computed_at` (ISO UTC from `clock`), `timezone` (`str(tz)`) and `partial_buckets` (labels from `partial_buckets`, comma-separated)
- [ ] Write `src/tests/stats/test_compute.py` using the `stats_fetcher` fixture: an `org` subject by month in UTC equals the Task 4 values, with per-repo series and no author series; with `by_author` the author series appear; a `repo` subject has no per-repo series; a `user` subject (`Subject('user', 'octocat')`) reads only `octocat/gamma` and counts only the commits authored as `Octocat` (matched case-insensitively), not the other author's; `since`/`until` cut the range inclusively at local dates in `Europe/Berlin` (the `2026-12-31T23:30Z` commit is in for `since=2027-01-01` and out for `until=2026-12-31`); `until=None` uses the fixed `clock` and flags the last bucket as partial; the default request lists `flow` in `unavailable` and still returns activity; each error in the validation order is raised before the cache is read (the fetcher is a stub that fails on any call); no requests are sent (the fetcher's client is never entered)
- [ ] Write a hypothesis test: for any range inside the fixture's span and any granularity, `compute`'s total `lines_added` points sum to the non-merge additions, summed directly in the test, of the org's fixture commits whose UTC date is in range (with `tz=UTC`)

**Acceptance Criteria:**

- [ ] `compute` never calls `Fetcher.sync` and sends no request
- [ ] Every requested group is either in `series` or in `tables['unavailable']`
- [ ] Provenance holds the cache identity, `fetched_at:commits`, `computed_at`, `timezone` and `partial_buckets`

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/stats/test_compute.py` passes

**Notes:**

- Depends on Task 3, Task 6
- A naive `datetime.combine(day, datetime.time(), tzinfo=tz)` can name a local time that does not exist in zones that skip midnight; the one-day widening plus the local-date filter makes that harmless, so do not try to compute exact UTC bounds.
- `compute` is the only async function in `gitstat.stats`; every function it calls after reading the records is pure.
- Key files: `src/gitstat/stats/compute.py`, `src/tests/stats/test_compute.py`

---

## Task 8: Exports and closing checks

**Status:** todo
**Priority:** medium
**Complexity:** small
**Spec Reference:** Module location; API; system spec API (`StatsRequest`, `StatsResult`, `compute` re-exported from `gitstat`); system spec Architecture (layering); implementation order step 4 "Done when"

**Technical Goal:** Expose the step 4 names, enforce the stats layer's imports, run every test this list can affect, and mark the step done.

**Subtasks:**

- [ ] In `src/gitstat/stats/__init__.py`, import and list in `__all__`, alphabetically: `Bucket`, `EmptySubjectError`, `GROUPS`, `Granularity`, `InvalidRangeError`, `InvalidRequestError`, `Series`, `StatsError`, `StatsRequest`, `StatsResult`, `UnknownGroupError`, `bucket_for`, `bucket_range`, `compute`, `partial_buckets`, `resources_for`
- [ ] In `src/gitstat/__init__.py`, re-export `StatsRequest`, `StatsResult` and `compute` and add them to `__all__` (system spec, API)
- [ ] Extend `src/tests/test_package.py`: every name in `gitstat.stats.__all__` resolves, and `gitstat.compute is gitstat.stats.compute`
- [ ] Extend `violations` in `src/tests/test_layering.py` so a `gitstat.stats` module importing anything outside `gitstat.stats`, `gitstat.fetch`, `gitstat.settings` and `gitstat.version` is a violation (today only `gitstat.reports` is), with a test like `test_detects_fetch_importing_reports` for it
- [ ] Check the implementation order's "Done when" for step 4: hypothesis partition tests (Task 2) and hand-checked fixture totals (Tasks 5 to 7)
- [ ] Run every test that imports a changed module directly or transitively: `pytest src/tests/stats src/tests/fetch src/tests/test_package.py src/tests/test_layering.py`
- [ ] In `agents/specs/implementation-order.md`, set step 4's Status to `done: [tasks-1](../tasks/stats/tasks-1.md)`

**Acceptance Criteria:**

- [ ] `import gitstat; gitstat.compute; gitstat.StatsRequest; gitstat.StatsResult` works
- [ ] Every step 4 "Done when" item is met, or its gap is recorded in the task that owns it

**Definition of Done:**

- [ ] `source bin/activate.sh` succeeds
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy src` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `pytest src/tests/stats src/tests/fetch src/tests/test_package.py src/tests/test_layering.py` passes

**Notes:**

- Depends on Tasks 1 to 7
- The project has no affected-tests tool; the command above names every test file that reaches a module this list changed (Task 3 changed `gitstat.fetch`, whose tests are under `src/tests/fetch/`; `gitstat` and `gitstat.stats` are imported outside `src/tests/stats/` only by `src/tests/test_package.py` and checked by `src/tests/test_layering.py`).
- The stats spec's `**Status:**` stays `proposed` (see the header).
- Key files: `src/gitstat/stats/__init__.py`, `src/gitstat/__init__.py`, `src/tests/test_package.py`, `src/tests/test_layering.py`, `agents/specs/implementation-order.md`

---
