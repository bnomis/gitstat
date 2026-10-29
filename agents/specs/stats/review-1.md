# Review: stats 1.1, the gaps step 4 needed settled

**Date:** 2026-10-29
**Spec:** `agents/specs/stats/spec.md` (1.0 to 1.1), with small amendments to `agents/specs/fetch-and-cache/spec.md` (1.2 to 1.3), `agents/specs/system/spec.md` (1.2 to 1.3) and `agents/specs/implementation-order.md` (1.2 to 1.3)
**Task list written against it:** `agents/tasks/stats/tasks-1.md`

## What is being reviewed and how

Writing the task list for step 4 of the implementation order (activity stats with bucketing) found places where stats 1.0 was silent, contradicted itself, or could not be built with what step 3 delivered. Version 1.1 settles them so the task list has no "decide with the user" tasks. None of them is a real decision that needs your answer before the work starts: each is a choice made on the spec's own logic and is reversible. They are listed so you can approve or flag each. One item is left open for step 8 and is not needed for step 4.

For each choice: approve it or flag it. A flagged choice changes the spec paragraph and the task named under it before the list runs.

## Automatic checks

- Whitespace and end-of-file checks (the only pre-commit hooks that apply to Markdown): checked with `git diff --check` and a final-newline check, because this session has no Python 3.14 to run `pre-commit`. No code changed.
- Every spec section is mapped to a task or a later step in the task list's coverage table: checked by hand.
- The ISO week facts the tests rely on (2026 has 53 weeks; 2026-12-31 and 2027-01-01 are in 2026-W53; 2025-12-29 is in 2026-W01) were checked with Python's `datetime.date.isocalendar()`.

## Choices made (approve or flag)

1. **`compute` never syncs.** 1.0 said `compute` "awaits the fetcher", and the system spec's data flow had `compute` trigger backfills. Since step 3 only `Fetcher.sync` reaches the network, and step 5's `--no-fetch` and `--max-age` need the caller to decide whether to sync. So the front end calls `Fetcher.sync(subject, resources_for(groups))` and then `compute`, which reads the cache alone. `resources_for` is new and public for that. The system spec's data flow is amended to match. (Task 7)
2. **Groups and metrics not built yet are listed as unavailable, not errors.** The default request includes `flow`, which step 6 builds, but step 5's CLI comes first and its done check runs the default report. Raising `NotImplementedError` (as `Fetcher.sync` does for unbuilt resources) would break that. Instead each unbuilt group, and the activity metrics nothing fetches yet (`stars`, `forks`, `watchers`, `languages`), gets a row in `tables['unavailable']` with the step that builds it, the same mechanism 1.0 already used for unconfigured DORA proxies. A request whose groups are all unbuilt raises `EmptySubjectError`. (Task 7)
3. **`until` is inclusive; a `None` bound resolves from the data or the clock.** 1.0 did not say. `--until 2026-10-31` now includes the 31st. `since=None` starts at the bucket holding the earliest commit, so the first bucket is not marked partial for lack of a bound; `until=None` is today in the report timezone, so the current period is marked partial. `compute` takes an optional `clock` for this, like `GitHubClient`. The resolved bounds are added to `StatsResult` as `since` and `until`. (Tasks 2 and 7)
4. **A range shorter than one bucket is valid.** 1.0 raised `InvalidRangeError` when "the range contains no complete bucket", which contradicts its own partial-bucket flagging: `--since 2026-10-01 --by year` would fail. 1.1 raises it only when `since` is after `until`, and gives one partial bucket otherwise. (Task 7)
5. **`InvalidRequestError` and a `StatsError` base.** 1.0 said `by_author` on a user subject is "rejected" without saying how. The reports spec already rejects it in the CLI with `UsageError`; stats raises the new `InvalidRequestError` for other callers. Every stats error now subclasses `StatsError`, like `FetchError` in fetch. The system spec's error list is amended. (Task 1)
6. **Settings travel in the request.** `compute(subject, fetcher, request)` had no way to receive `stats.bot_logins` or `stats.exclude_merge_commits`. `StatsRequest` gains `settings: StatsSettings`, so the result also records the settings it was computed with. `stats.timezone` stays the CLI's default for `StatsRequest.tz`; `compute` reads only `tz`. (Tasks 1 and 5)
7. **What each activity metric counts.** Read literally from 1.0's settings table: merge commits are left out of line counts only, so `commits` includes them; bots are left out of `contributors` (and the top-contributors table) only, so their commits and lines count. Unattributed commits count everywhere except `contributors`, where they cannot be told apart by person. Logins compare case-insensitively, as GitHub's do. Flag this if you want merges or bots out of commit counts too; it is a one-line change per metric. (Tasks 5 and 6)
8. **Breakdown series say what they break down by.** `Series` gains `by_kind` (`'author'` or `'repo'`), so an org result with both per-repo and per-author series cannot confuse the two. Breakdowns carry `commits` as well as the three line series (1.0 named only the lines), per-repo breakdowns are produced for user and org subjects, and per-author ones with `by_author`. A `top_contributors` table (which 1.0 named as an example and the reports spec renders) is produced for every subject. (Task 6)
9. **Provenance comes through `Fetcher`.** 1.0 required the cache identity and fetch times in provenance, but stats cannot reach the cache without going around `Fetcher`, which the system spec forbids. The fetch spec (1.3) adds `Fetcher.provenance(subject, resources)` and `Cache.version_override_at()`. Provenance records the cache identity, any version override (the shared versions rule requires the output to show it was used), `fetched_at:<resource>` as the oldest sync time over the subject's repos, `computed_at`, `timezone` and the partial bucket labels. (Tasks 3 and 7)
10. **`TOTAL` buckets and labels.** `bucket_for` cannot place a date in the `TOTAL` bucket without the range, so it raises `ValueError` for it; `bucket_range` returns the one bucket, labelled `total`. `bucket_range` and `partial_buckets` are new public helpers, needed for complete series and for the partition tests the implementation order asks for. (Task 2)
11. **Module layout.** `compute` goes in its own `compute.py` (it imports every group's aggregation, which import `base.py`), and the errors in `errors.py`, as in fetch. (Tasks 1 and 7)

## Open for a later step

- **Forks, watchers and languages have no fetch resource.** 1.0 lists `stars`, `forks`, `watchers` cumulative per bucket and a `languages` table under `activity`, but the fetch spec only has `star_events`. GitHub reports fork creation dates, but not when someone started watching, so `watchers` can be a current count but not a per-bucket series. The implementation order now puts all four in step 8, and the fetch spec needs resources for forks and languages (and a decision on watchers) before step 8's task list is written. Step 4 lists them as unavailable.

## Answers

(empty: your verdict on each choice, with the date)
