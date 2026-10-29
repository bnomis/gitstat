# Stats

**Version:** 1.1
**Status:** proposed
**Date:** 2026-10-29

Turns the raw records from [Fetch and cache](../fetch-and-cache/spec.md) into statistics for a user, repository or organisation, optionally bucketed by year, month, week or day. It does no network or rendering of its own: `compute` reads the cache through the fetcher, and the aggregation functions it calls are pure. [Reports](../reports/spec.md) consumes its output.

**Prerequisite:** the `wambatic.fetch` package exists and `Fetcher` reads the records of each group's resources from the cache (check: `python -c 'import wambatic.fetch'`). The `activity` group needs `repos()` and `commits()` (implementation step 3); `flow` needs `pull_requests()` and `issues()` (step 6); `delivery` needs `releases()`, `workflow_runs()` and `star_events()` (step 8).

Version 1.1 settles what step 4 of the [implementation order](../implementation-order.md) needed; the gaps and the choices made are in [review-1.md](review-1.md).

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

`compute` lives in its own module because it imports every group's aggregation, and each aggregation imports the records in `base.py`.

## API

```python
import collections.abc
import dataclasses
import datetime
import enum
import typing

import wambatic.settings

GROUPS = frozenset({'activity', 'delivery', 'flow'})

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
    unit: str                        # 'count', 'days', 'lines', 'hours', 'ratio'
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
    'delivery' -> {'releases', 'star_events', 'workflow_runs'}. Raises UnknownGroupError."""

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
    tables: dict[str, list[dict[str, typing.Any]]]   # 'top_contributors', 'unavailable', later 'languages'
    provenance: dict[str, str]                       # see Provenance
```

`StatsRequest.tz` is the zone the caller resolved; `compute` does not read `settings.timezone`, which is how the CLI chooses `tz` when `--tz` is absent.

## Error handling

All stats errors subclass `StatsError(Exception)`, so a front end can catch them together.

- `InvalidRangeError`: `since` is after `until` (after resolving `None` bounds). A range shorter than one bucket is valid and gives one partial bucket.
- `InvalidRequestError`: `by_author` with a `user` subject. The CLI rejects this first with its own `UsageError`; this error is for other callers.
- `UnknownGroupError`: `request.groups` names a group outside `GROUPS`; the message names each unknown group.
- `EmptySubjectError`: the cache holds no repositories for the subject, no records of the requested groups in range, or no requested group is built yet (the message names the steps that build them); callers print a message rather than an empty report.
- Fetch errors (`AuthError`, `RateLimitError`, `CacheVersionError`) propagate unchanged.
- Records with `author_login is None` are counted under the `unattributed` key, never dropped.

Validation happens before any cache read, in this order: unknown groups, `by_author` on a user subject, then the range when both bounds are given.

## Implementation

All timestamps are stored UTC and converted once to `request.tz` before bucketing; a record belongs to the local date of `authored_at.astimezone(tz)`. Weeks follow [ISO 8601](https://en.wikipedia.org/wiki/ISO_week_date), so a week can straddle a year boundary and carries the ISO year in its label (`2026-12-31` is in `2026-W53`, and so is `2027-01-01`). Labels are `YYYY`, `YYYY-MM`, `YYYY-Www` with a two-digit week, `YYYY-MM-DD`, and `total`. Bucket boundaries are half-open on local dates: a bucket runs from its `start` up to the next bucket's `start`.

**Range.** `since` and `until` are local dates in `tz`, both inclusive (`--until 2026-10-31` includes the 31st). A `None` `since` resolves to the start of the bucket holding the earliest record, so the first bucket is never partial for lack of a bound; for `TOTAL` it resolves to the earliest record's local date. A `None` `until` resolves to today in `tz` from `clock`, so the current bucket is partial. The resolved bounds are in `StatsResult.since` and `until`.

**Reading the cache.** `compute` converts the range to UTC instants for `Fetcher.commits` widened by one day at each end, then keeps only records whose local date is in the range. The widening makes the result independent of how `tz` handles midnight (a zone whose clocks skip midnight has no `00:00` on that date).

**Partial buckets.** `partial_buckets` names the first and last bucket when the range covers only part of them; their labels are recorded comma-separated in `provenance['partial_buckets']` (empty when none), and reports chart them with a hatch pattern.

**Groups not built yet.** A requested group whose implementation step has not been built, and an `activity` metric whose resource is not fetched yet, is not an error: it gets no series and a row in `tables['unavailable']`, `{'metric': <group or metric name>, 'reason': <text naming the step that builds it>}`. The same table carries the delivery proxies that are not configured (below). This lets the default request, which includes `flow`, run before step 6 is built. A group whose resources are built but empty for the subject is not unavailable; it contributes zeros.

### Metric groups

**activity** (all subjects; per repository and aggregated)

- `commits` (unit `count`): commits in the bucket, merge commits included.
- `contributors` (unit `count`): distinct author logins with a commit in the bucket, compared case-insensitively, excluding `stats.bot_logins` and excluding unattributed commits (they cannot be told apart by person).
- `active_days` (unit `days`): distinct local dates with at least one commit in the bucket.
- **Code contributions:** `lines_added`, `lines_deleted`, `lines_net` (added minus deleted, unit `lines`) from per-commit `additions` and `deletions`, summed per bucket. Merge commits are excluded when `stats.exclude_merge_commits` is true (the default) so lines are not double counted; the setting does not affect `commits`. Bot commits are counted in `commits` and lines; `stats.bot_logins` only affects contributor counts. Generated and vendored files are not filtered because GitHub does not expose per-file stats cheaply (documented limitation).
- `stars`, `forks`, `watchers` cumulative and per bucket, `languages` (bytes per language, latest snapshot table). Not built in step 4: they are listed in `tables['unavailable']` until the step that fetches them (stars from `star_events` in step 8; forks, watchers and languages have no fetch resource yet, see review-1.md).
- `tables['top_contributors']`: one row per author over the whole range, `{'login', 'commits', 'lines_added', 'lines_deleted', 'lines_net', 'active_days'}`, with the same merge rule as the series, ordered by `commits` descending then `login`. Bots are left out; unattributed commits are one row with `login` `'unattributed'`. Produced for every subject, with or without `by_author`.

**flow** (pull requests and issues)

- `prs_opened`, `prs_merged`, `issues_opened`, `issues_closed`.
- `time_to_first_review`, `time_to_merge`, `time_to_close` as median and 90th percentile in hours per bucket, using `statistics.quantiles`, bucketed by the end event's date.
- `pr_size` median additions plus deletions.

**delivery** (CI and delivery; approximations, labelled as proxies in reports)

- `workflow_runs`, `workflow_success_rate`, `workflow_duration_p50` from Actions runs.
- `release_count` and `release_interval_days`.
- Four-keys proxies following [DORA](https://dora.dev/guides/dora-metrics-four-keys/): deployment frequency (releases, or successful runs of the workflow named by `stats.deploy_workflow`), lead time for changes (first commit on a merged PR to its release), change failure rate (releases followed by a hotfix-labelled PR within `stats.failure_window`) and time to restore (hotfix PR open to merge). These need conventions that GitHub does not enforce, so each is only emitted when its inputs are configured and is otherwise listed in `tables['unavailable']` with the reason.

### Aggregation

- `user` subject: repositories owned by the user, counting only commits whose `author_login` matches the subject's login case-insensitively; `by_author` is not meaningful and is rejected. Per-repo breakdown series as for `org`.
- `repo` subject: one repository, optionally per author.
- `org` subject: sum across org repositories, with per-repo breakdown series always and per-author breakdown series with `by_author`.
- **Breakdown series** are `commits`, `lines_added`, `lines_deleted` and `lines_net` with `by` set to the author login (or `'unattributed'`, `by_kind='author'`) or the repo's `owner/name` (`by_kind='repo'`). Per-author series include bots: they are not contributors, but their lines are counted.
- A series' `points` holds every bucket of the range in chronological order: empty buckets are zero for counts and lines, and absent for medians and ratios. Breakdown series are filled over the whole range too, so they align with the totals.
- `series` is ordered: the group's total series in the order listed above, then breakdown series ordered by `by_kind` (`author` before `repo`), then `by`, then metric in the order listed above.
- Summing an `activity` breakdown's points over every `by` of one `by_kind` gives the total series' points, for each of its four metrics.

### Provenance

Every result records what produced it, so a saved report can be traced and a mismatch with a later run is detectable. `provenance` holds:

- from `Fetcher.provenance(subject, resources)` (fetch spec): the cache identity (`schema_version`, `wambatic_version` as recorded, `query:<NAME>` hashes), `version_override_at` when the cache was opened with the version override, and `fetched_at:<resource>` for each resource read, the earliest `synced_at` over the subject's repos (the oldest data in the result), or `never` when a repo has no sync state for it;
- from stats: `computed_at` (ISO UTC, from `clock`), `timezone` (`str(tz)`), and `partial_buckets`.

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `stats.bot_logins` | `list[str]` | `['dependabot[bot]', 'renovate[bot]']` | Authors excluded from contributor counts and the top-contributors table |
| `stats.deploy_workflow` | `str \| None` | `None` | Workflow name counted as a deployment |
| `stats.exclude_merge_commits` | `bool` | `True` | Skip merge commits in line counts |
| `stats.failure_window` | `timedelta` | `7 days` | Window for change-failure detection |
| `stats.hotfix_labels` | `list[str]` | `['hotfix']` | PR labels marking a failure fix |
| `stats.timezone` | `str` | `'UTC'` | IANA zone the CLI uses for `StatsRequest.tz` when `--tz` is absent |

`compute` takes the settings from `StatsRequest.settings`, so a result records the settings it was computed with.

## External dependencies

- `wambatic.fetch` (see [Fetch and cache](../fetch-and-cache/spec.md)) and `wambatic.settings`.
- Stdlib only: `bisect`, `datetime`, `zoneinfo`, `statistics`, `dataclasses`. No dependency is added.
