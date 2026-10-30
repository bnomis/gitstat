# Stats

**Version:** 1.4
**Status:** proposed
**Date:** 2026-10-30

Turns the raw records from [Fetch and cache](../fetch-and-cache/spec.md) into statistics for a user, repository or organisation, optionally bucketed by year, month, week or day. It does no network or rendering of its own: `compute` reads the cache through the fetcher, and the aggregation functions it calls are pure. [Reports](../reports/spec.md) consumes its output.

**Prerequisite:** the `wambatic.fetch` package exists and `Fetcher` reads the records of each group's resources from the cache (check: `python -c 'import wambatic.fetch'`). The `activity` group needs `repos()` and `commits()` (implementation step 3); `flow` needs `pull_requests()` and `issues()` (step 6); `delivery` needs `releases()`, `workflow_runs()` (step 8) and `pull_requests()`; `popularity` needs `star_events()`, `forks()` and the `Repo` popularity fields (step 10).

Version 1.1 settles what step 4 of the [implementation order](../implementation-order.md) needed; the gaps and the choices made are in [review-1.md](review-1.md). Version 1.2 settles what step 6 needed for the `flow` group: what each flow metric counts and its series names, how the range and an empty result are found when several groups are read, and the user-subject rule for pull requests and issues; the choices are in [review-2.md](review-2.md). Version 1.3 settles what step 8 needed for the `delivery` group: what each delivery metric and DORA proxy counts, its series names and units, when a proxy counts as configured, and which resources the group reads; stars, forks, watchers and languages move to step 10. The choices are in [review-3.md](review-3.md). Version 1.4 settles what step 10 needed: stars, forks, watchers and languages leave `activity` for a `popularity` group of their own, asked for with `--groups`, with what each metric and table counts and which resources the group reads; the choices are in [review-4.md](review-4.md).

## Module location

`src/wambatic/stats/`, with tests in `src/tests/stats/` and fixtures in `src/tests/fixtures/stats.py`:

| Module | Holds | Built in implementation step |
|--------|-------|------------------------------|
| `errors.py` | `StatsError` and every typed error below | 4 |
| `base.py` | `Granularity`, `Bucket`, `Series`, `StatsRequest`, `StatsResult`, `GROUPS` | 4 |
| `buckets.py` | `bucket_for`, `bucket_range`, `partial_buckets` | 4 |
| `activity.py` | the pure `activity` aggregation | 4 |
| `compute.py` | `compute`, `resources_for` | 4 |
| `flow.py` | the pure `flow` aggregation | 6 |
| `delivery.py` | the pure `delivery` aggregation | 8 |
| `popularity.py` | the pure `popularity` aggregation | 10 |

`compute` lives in its own module because it imports every group's aggregation, and each aggregation imports the records in `base.py`.

## API

```python
import collections.abc
import dataclasses
import datetime
import enum
import typing

import wambatic.settings

GROUPS = frozenset({'activity', 'delivery', 'flow', 'popularity'})

class Granularity(enum.StrEnum):
    DAY = 'day'
    MONTH = 'month'
    TOTAL = 'total'      # a single bucket over the whole range
    WEEK = 'week'
    YEAR = 'year'

@dataclasses.dataclass(frozen=True, slots=True, order=True)
class Bucket:
    start: datetime.date   # first day of the bucket in the report timezone
    label: str             # '2026', '2026-10', '2026-W44', '2026-10-29', or 'total'

@dataclasses.dataclass(frozen=True, slots=True)
class Series:
    metric: str                      # e.g. 'lines_added'
    unit: str                        # 'count', 'days', 'lines', 'hours', 'minutes', 'ratio'
    points: dict[Bucket, float]      # every bucket of the range, in order; see Aggregation
    by: str | None = None            # grouping key: an author login, 'unattributed', or 'owner/name'
    by_kind: typing.Literal['author', 'repo'] | None = None   # what `by` is; None when `by` is None

def bucket_for(when: datetime.datetime, granularity: Granularity, tz: datetime.tzinfo) -> Bucket:
    """Bucket containing `when` (an aware datetime) in `tz`; weeks are ISO 8601 weeks starting
    Monday. Raises ValueError for Granularity.TOTAL, whose one bucket depends on the range."""

def bucket_range(since: datetime.date, until: datetime.date, granularity: Granularity) -> list[Bucket]:
    """The buckets covering the local dates `since` to `until`, both inclusive, in order.
    For TOTAL, the one bucket Bucket(since, 'total')."""

def partial_buckets(since: datetime.date, until: datetime.date, buckets: list[Bucket]) -> list[Bucket]:
    """The first and last of `buckets` when the range starts after the first's start or ends
    before the last's end; never a TOTAL bucket."""

def resources_for(groups: frozenset[str]) -> frozenset[str]:
    """The fetch resources the groups read, for the caller's Fetcher.sync before compute:
    'activity' -> {'commits'}, 'flow' -> {'issues', 'pull_requests'},
    'delivery' -> {'pull_requests', 'releases', 'workflow_runs'},
    'popularity' -> {'forks', 'star_events'}. Raises UnknownGroupError."""

async def compute(
    subject: Subject,
    fetcher: Fetcher,
    request: StatsRequest,
    *,
    clock: collections.abc.Callable[[], datetime.datetime] | None = None,
) -> StatsResult:
    """All requested metric groups for the subject, from the cache, bucketed by
    request.granularity. Never syncs: the caller runs Fetcher.sync first, or not at all for
    --no-fetch. `clock` (default: now in UTC) gives today's date when `until` is None."""

@dataclasses.dataclass(frozen=True, slots=True)
class StatsRequest:
    granularity: Granularity = Granularity.MONTH
    groups: frozenset[str] = frozenset({'activity', 'flow'})   # a subset of GROUPS
    since: datetime.date | None = None     # first local date counted; None: the earliest record's bucket start
    until: datetime.date | None = None     # last local date counted, inclusive; None: today in tz
    by_author: bool = False
    tz: datetime.tzinfo = datetime.UTC
    settings: wambatic.settings.StatsSettings = dataclasses.field(default_factory=wambatic.settings.StatsSettings)

@dataclasses.dataclass(frozen=True, slots=True)
class StatsResult:
    subject: Subject
    request: StatsRequest
    since: datetime.date                             # the resolved range, both inclusive
    until: datetime.date
    series: list[Series]
    tables: dict[str, list[dict[str, typing.Any]]]   # 'top_contributors', 'unavailable'; 'popularity' and 'languages' with that group
    provenance: dict[str, str]                       # see Provenance
```

`StatsRequest.tz` is the zone the caller resolved; `compute` does not read `settings.timezone`, which is how the CLI chooses `tz` when `--tz` is absent.

## Error handling

All stats errors subclass `StatsError(Exception)`, so a front end can catch them together.

- `InvalidRangeError`: `since` is after `until` (after resolving `None` bounds). A range shorter than one bucket is valid and gives one partial bucket.
- `InvalidRequestError`: `by_author` with a `user` subject. The CLI rejects this first with its own `UsageError`; this error is for other callers.
- `UnknownGroupError`: `request.groups` names a group outside `GROUPS`; the message names each unknown group.
- `EmptySubjectError`: the cache holds no repositories for the subject, no records of any requested built group in range (a group with records still reports the others as zeros; `popularity` always has records, since its tables come from the repositories themselves), or no requested group is built yet (the message names the steps that build them); callers print a message rather than an empty report.
- Fetch errors (`AuthError`, `RateLimitError`, `CacheVersionError`) propagate unchanged.
- Records with `author_login is None` are counted under the `unattributed` key, never dropped.

Validation happens before any cache read, in this order: unknown groups, `by_author` on a user subject, then the range when both bounds are given.

## Implementation

All timestamps are stored UTC and converted once to `request.tz` before bucketing; a record belongs to the local date of `authored_at.astimezone(tz)`. Weeks follow [ISO 8601](https://en.wikipedia.org/wiki/ISO_week_date), so a week can straddle a year boundary and carries the ISO year in its label (`2026-12-31` is in `2026-W53`, and so is `2027-01-01`). Labels are `YYYY`, `YYYY-MM`, `YYYY-Www` with a two-digit week, `YYYY-MM-DD`, and `total`. Bucket boundaries are half-open on local dates: a bucket runs from its `start` up to the next bucket's `start`.

**Range.** `since` and `until` are local dates in `tz`, both inclusive (`--until 2026-10-31` includes the 31st). A `None` `since` resolves to the start of the bucket holding the earliest record of any requested built group (a commit's `authored_at`, a pull request's or issue's `created_at`, a release's `published_at`, a workflow run's `created_at`, a star's `starred_at`, a fork's `created_at`; for `delivery` the pull requests it reads for the proxies do not count, since they are inputs to release events, not events of their own), so the first bucket is never partial for lack of a bound; for `TOTAL` it resolves to the earliest record's local date. When no requested group has a dated record (possible only with `popularity`, whose tables need none), `since` resolves to the start of the bucket holding `until`, or to `until` itself for `TOTAL`. A `None` `until` resolves to today in `tz` from `clock`, so the current bucket is partial. The resolved bounds are in `StatsResult.since` and `until`.

**Reading the cache.** `compute` converts the range to UTC instants for `Fetcher.commits` widened by one day at each end, then keeps only records whose local date is in the range. For `flow` it passes the widened lower instant to `Fetcher.pull_requests` and `Fetcher.issues`, which filter on `updated_at` (every event of an item is at or before it), and each flow metric then keeps the events whose local date is in the range. For `delivery` it reads every release (`Fetcher.releases`), because a release interval and a lead time reach back before the range, the workflow runs from the widened lower instant (`Fetcher.workflow_runs`, which filters on `created_at`), or all of them when `stats.deploy_workflow` is set, because deployments are then runs and a lead time reaches back like a release interval, and, only when a proxy needs them, every pull request (`Fetcher.pull_requests(repo, None)`), because a release in range can ship a pull request merged long before it; each delivery metric then keeps the events whose local date is in the range. For `popularity` it reads every star event and fork (`Fetcher.star_events`, `Fetcher.forks`), because a cumulative count reaches back before any range, and takes the counts and languages from the `Repo` rows `Fetcher.repos` already returned. The widening makes the result independent of how `tz` handles midnight (a zone whose clocks skip midnight has no `00:00` on that date).

**Partial buckets.** `partial_buckets` names the first and last bucket when the range covers only part of them; their labels are recorded comma-separated in `provenance['partial_buckets']` (empty when none), and reports chart them with a hatch pattern.

**Groups not built yet.** A requested group whose implementation step has not been built, and an `activity` metric whose resource is not fetched yet, is not an error: it gets no series and a row in `tables['unavailable']`, `{'metric': <group or metric name>, 'reason': <text naming the step that builds it>}`. The same table carries the delivery proxies that are not configured (below). Since step 10 every group and metric is built, so the table holds only those proxies. This lets the default request, which includes `flow`, run before step 6 is built. A group whose resources are built but empty for the subject is not unavailable; it contributes zeros.

### Metric groups

**activity** (all subjects; per repository and aggregated)

- `commits` (unit `count`): commits in the bucket, merge commits included.
- `contributors` (unit `count`): distinct author logins with a commit in the bucket, compared case-insensitively, excluding `stats.bot_logins` and excluding unattributed commits (they cannot be told apart by person).
- `active_days` (unit `days`): distinct local dates with at least one commit in the bucket.
- **Code contributions:** `lines_added`, `lines_deleted`, `lines_net` (added minus deleted, unit `lines`) from per-commit `additions` and `deletions`, summed per bucket. Merge commits are excluded when `stats.exclude_merge_commits` is true (the default) so lines are not double counted; the setting does not affect `commits`. Bot commits are counted in `commits` and lines; `stats.bot_logins` only affects contributor counts. Generated and vendored files are not filtered because GitHub does not expose per-file stats cheaply (documented limitation).
- Stars, forks, watchers and languages were listed here until step 10, which moves them to `popularity` (review-4.md decision 1).
- `tables['top_contributors']`: one row per author over the whole range, `{'login', 'commits', 'lines_added', 'lines_deleted', 'lines_net', 'active_days'}`, with the same merge rule as the series, ordered by `commits` descending then `login`. Bots are left out; unattributed commits are one row with `login` `'unattributed'`. Produced for every subject, with or without `by_author`.

**flow** (pull requests and issues; total series only, built in step 6)

- Counts (unit `count`), each bucketed by the local date of its event: `prs_opened` (`created_at`), `prs_merged` (`merged_at`), `issues_opened` (`created_at`), `issues_closed` (`closed_at`, issues closed now; a reopened issue is open). A pull request closed without merging counts in `prs_opened` only.
- Durations (unit `hours`), each bucketed by the local date of its end event, as `<name>_p50` (`statistics.median`) and `<name>_p90` (`statistics.quantiles(values, n=10, method='inclusive')[8]`, which stays inside the values, unlike the default `exclusive` method, and accepts one value on Python 3.13 and later): `time_to_first_review` (pull request `created_at` to `first_review_at`), `time_to_merge` (`created_at` to `merged_at`) and `time_to_close` (issue `created_at` to `closed_at`; pull requests have `time_to_merge`). Hours are `(end - start).total_seconds() / 3600`.
- `pr_size_p50` (unit `lines`): `statistics.median_low` of `additions + deletions` over the pull requests merged in the bucket, so the value is one pull request's real size and an integer, as the JSON output requires of `lines`.
- Bots are counted: `stats.bot_logins` affects contributor counts only, as in `activity`. Who reviewed is settled by the fetch layer (`first_review_at` leaves out the author and bots).
- Series order: `prs_opened`, `prs_merged`, `issues_opened`, `issues_closed`, `time_to_first_review_p50`, `time_to_first_review_p90`, `time_to_merge_p50`, `time_to_merge_p90`, `time_to_close_p50`, `time_to_close_p90`, `pr_size_p50`.

**delivery** (CI and delivery; approximations, labelled as proxies in reports)

Built in step 8; total series only. Percentiles are computed as in `flow` (`statistics.median` for p50, `statistics.quantiles(values, n=10, method='inclusive')[8]` for p90), and an empty bucket has no value for a percentile or a ratio and zero for a count.

- **Actions.** Every workflow run counts, whatever its workflow, event or branch, bucketed by the local date of its `created_at`:
  - `workflow_runs` (unit `count`): runs created in the bucket, finished or not.
  - `workflow_success_rate` (unit `ratio`, 0 to 1): of the bucket's completed runs whose `conclusion` is `success`, `failure`, `timed_out` or `startup_failure`, the share that is `success`. `cancelled`, `skipped`, `neutral`, `action_required` and `stale` are not outcomes of the code and are left out of both counts; a bucket with none of the four has no value.
  - `workflow_duration_p50` and `workflow_duration_p90` (unit `minutes`): `(updated_at - run_started_at).total_seconds() / 60` over the bucket's completed runs with a `run_started_at`, the wall-clock time of the latest attempt. This is a proxy: GitHub's per-run timing endpoint would cost a request per run, and a run's `updated_at` can move after it finishes (a re-run request resets it), which reads as a longer run.
- **Releases.** Published releases only (drafts are not stored), prereleases included, bucketed by the local date of `published_at`:
  - `release_count` (unit `count`).
  - `release_interval_p50` (unit `days`): `statistics.median_low` of the whole days (`(later - earlier).days`) between each release and the previous release of the same repository by `published_at`, bucketed by the later one, so the value is one real interval and an integer, as the JSON output requires of `days`. A repository's first release has no interval.
- **DORA proxies**, following the [four keys](https://dora.dev/guides/dora-metrics-four-keys/). They lean on conventions GitHub does not enforce, so each is emitted only when its inputs exist and is otherwise a row in `tables['unavailable']` naming what is missing:
  - *Deployments.* With `stats.deploy_workflow` set, a deployment is a completed run with `conclusion` `success` whose workflow file name (`workflow_path` after its last `/`, such as `deploy.yml`) or `name` equals the setting, at its `updated_at` (when it finished). Without the setting, a deployment is a release that is not a prerelease, at its `published_at`. Deployments are per repository.
  - `deployments` (unit `count`): deployments in the bucket. Emitted when the subject has at least one deployment in the cache (at any time); otherwise unavailable with `no releases in the cache and stats.deploy_workflow is not set`, or `no successful run of the workflow named by stats.deploy_workflow`.
  - `lead_time_p50` and `lead_time_p90` (unit `hours`): for each merged pull request, from its `first_commit_at` (its `created_at` when that is `None`) to the first deployment of the same repository at or after its `merged_at`, bucketed by that deployment's local date. A pull request with no deployment after its merge yet is not counted. Emitted with `deployments`, under the same condition.
  - `change_failure_rate` (unit `ratio`): of the bucket's deployments, the share followed by a hotfix pull request of the same repository whose `created_at` is after the deployment and no later than `stats.failure_window` after it. A hotfix pull request is one with a label in `stats.hotfix_labels`, compared case-insensitively. Emitted when `deployments` is and the subject has at least one hotfix pull request in the cache; otherwise unavailable, naming whichever is missing. A deployment within `stats.failure_window` of now is counted as not failed, since its window is still open.
  - `time_to_restore_p50` and `time_to_restore_p90` (unit `hours`): hotfix pull requests from `created_at` to `merged_at`, bucketed by the local date of `merged_at`. Emitted when the subject has at least one hotfix pull request; it needs no deployments.
- Bots are counted, as in `flow`; `stats.bot_logins` affects contributor counts only.
- Series order: `workflow_runs`, `workflow_success_rate`, `workflow_duration_p50`, `workflow_duration_p90`, `release_count`, `release_interval_p50`, `deployments`, `lead_time_p50`, `lead_time_p90`, `change_failure_rate`, `time_to_restore_p50`, `time_to_restore_p90`; a proxy that is not emitted is left out, never sent as an empty series.

**popularity** (stars, forks, watchers, languages; built in step 10)

A star, a fork or a watch belongs to a repository, not to an author, so for every subject kind the group counts every star and fork of the subject's repositories, as `delivery` does. Total series only.

- Per bucket (unit `count`), by the local date of the event: `stars_added` (stargazers whose `starred_at` is in the bucket) and `forks_added` (direct forks whose `created_at` is in the bucket).
- Cumulative (unit `count`): `stars_total` and `forks_total`, the stargazers (or direct forks) in the cache whose local date is on or before the bucket's last day, or `until` for the last bucket. They count the stars and forks that exist now, by when they were made: a star since removed, or a fork since deleted, is not in any bucket, so a cumulative series never falls and can be below the count GitHub showed at the time. Its last value can also differ from the table below, which is GitHub's own count at the last listing (stars made since the sync, and for forks the whole network).
- Watchers have no series: GitHub records no time of watching (fetch spec, Incremental sync step 2).
- `tables['popularity']`: one row per repository of the subject, `{'repo', 'stars', 'forks', 'watchers'}` from `Repo.stargazer_count`, `fork_count` and `watcher_count` as of the last listing, ordered by `stars` descending, then `repo`.
- `tables['languages']`: one row per language over the subject's repositories, `{'language', 'bytes', 'share'}`: `bytes` summed by language name from `Repo.languages`; each repository's `languages_size` less its listed languages' bytes, summed, is one row `'Other'` when above zero; `share` (0 to 1) is a row's bytes over the sum of every row's bytes. Ordered by `bytes` descending then `language`, with `'Other'` last. Empty when no repository has a language.
- Series order: `stars_added`, `stars_total`, `forks_added`, `forks_total`.

### Aggregation

- `user` subject: repositories owned by the user, counting only commits, pull requests and issues whose `author_login` matches the subject's login case-insensitively; `by_author` is not meaningful and is rejected. Per-repo breakdown series as for `org`. `delivery` and `popularity` are the exceptions: `popularity` counts every star and fork of the user's repositories, and `delivery` counts every release, workflow run and pull request of them, because a release or a run ships the repository's work, not one author's, and a lead time measured on the user's own pull requests only would leave out what the release shipped.
- `repo` subject: one repository, optionally per author.
- `org` subject: sum across org repositories, with per-repo breakdown series always and per-author breakdown series with `by_author`.
- **Breakdown series** are `commits`, `lines_added`, `lines_deleted` and `lines_net` with `by` set to the author login (or `'unattributed'`, `by_kind='author'`) or the repo's `owner/name` (`by_kind='repo'`). Per-author series include bots: they are not contributors, but their lines are counted.
- A series' `points` holds every bucket of the range in chronological order: empty buckets are zero for counts and lines, and absent for medians and ratios. Breakdown series are filled over the whole range too, so they align with the totals.
- `flow`, `delivery` and `popularity` have no breakdown series; `by_author` and the per-repo breakdowns apply to `activity` only (a repository's own stars and forks are in `tables['popularity']`).
- `series` is ordered: the `activity` total series, then the `flow` total series, then the `delivery` total series, then the `popularity` total series, each in the order listed above, then breakdown series ordered by `by_kind` (`author` before `repo`), then `by`, then metric in the order listed above.
- Summing an `activity` breakdown's points over every `by` of one `by_kind` gives the total series' points, for each of its four metrics.

### Provenance

Every result records what produced it, so a saved report can be traced and a mismatch with a later run is detectable. `provenance` holds:

- from `Fetcher.provenance(subject, resources)` (fetch spec): the cache identity (`schema_version`, `wambatic_version` as recorded, `query:<NAME>` hashes), `version_override_at` when the cache was opened with the version override, and `fetched_at:<resource>` for each resource read, the earliest `synced_at` over the subject's repos (the oldest data in the result), or `never` when a repo has no sync state for it;
- from stats: `computed_at` (ISO UTC, from `clock`), `timezone` (`str(tz)`), and `partial_buckets`.

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `stats.bot_logins` | `list[str]` | `['dependabot[bot]', 'renovate[bot]']` | Authors excluded from contributor counts and the top-contributors table |
| `stats.deploy_workflow` | `str \| None` | `None` | Workflow counted as a deployment, matched against a run's workflow file name (`deploy.yml`) or its name; unset, non-prerelease releases are the deployments |
| `stats.exclude_merge_commits` | `bool` | `True` | Skip merge commits in line counts |
| `stats.failure_window` | `timedelta` | `7 days` | How long after a deployment a hotfix pull request marks it as failed |
| `stats.hotfix_labels` | `list[str]` | `['hotfix']` | Pull request labels marking a failure fix, compared case-insensitively |
| `stats.timezone` | `str` | `'UTC'` | IANA zone the CLI uses for `StatsRequest.tz` when `--tz` is absent |

`compute` takes the settings from `StatsRequest.settings`, so a result records the settings it was computed with.

## External dependencies

- `wambatic.fetch` (see [Fetch and cache](../fetch-and-cache/spec.md)) and `wambatic.settings`.
- Stdlib only: `bisect`, `datetime`, `zoneinfo`, `statistics`, `dataclasses`. No dependency is added.
