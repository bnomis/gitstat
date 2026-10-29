# Stats

**Version:** 1.0
**Status:** proposed
**Date:** 2026-10-29

Turns the raw records from [Fetch and cache](../fetch-and-cache/spec.md) into statistics for a user, repository or organisation, optionally bucketed by year, month, week or day. It is pure computation: no network, no rendering. [Reports](../reports/spec.md) consumes its output.

**Prerequisite:** the `gitstat.fetch` package exists and `Fetcher` yields `Commit`, `PullRequest`, `Issue`, `Release`, `WorkflowRun` and `StarEvent` records (check: `python -c 'import gitstat.fetch'`).

## Module location

`src/gitstat/stats/` (`base.py`, `buckets.py`, `activity.py`, `flow.py`, `delivery.py`), with tests in `src/tests/stats/`.

## API

```python
import dataclasses
import datetime
import enum
import typing

class Granularity(enum.StrEnum):
    DAY = 'day'
    MONTH = 'month'
    TOTAL = 'total'      # a single bucket over the whole range
    WEEK = 'week'
    YEAR = 'year'

@dataclasses.dataclass(frozen=True, slots=True)
class Bucket:
    start: datetime.date   # first day of the bucket in the report timezone
    label: str             # '2026', '2026-10', '2026-W44', '2026-10-29'

@dataclasses.dataclass(frozen=True, slots=True)
class Series:
    metric: str                      # e.g. 'lines_added'
    unit: str                        # 'count', 'lines', 'hours', 'ratio'
    points: dict[Bucket, float]      # missing buckets are filled with 0, or absent for ratios
    by: str | None = None            # grouping key such as an author login or repo

def bucket_for(when: datetime.datetime, granularity: Granularity, tz: datetime.tzinfo) -> Bucket:
    """Bucket containing `when`; weeks are ISO 8601 weeks starting Monday."""

def compute(subject: Subject, fetcher: Fetcher, request: StatsRequest) -> StatsResult:
    """All requested metric groups for the subject, bucketed by request.granularity."""

@dataclasses.dataclass(frozen=True, slots=True)
class StatsRequest:
    granularity: Granularity = Granularity.MONTH
    groups: frozenset[str] = frozenset({'activity', 'flow'})   # 'activity', 'delivery', 'flow'
    since: datetime.date | None = None
    until: datetime.date | None = None
    by_author: bool = False
    tz: datetime.tzinfo = datetime.UTC

@dataclasses.dataclass(frozen=True, slots=True)
class StatsResult:
    subject: Subject
    request: StatsRequest
    series: list[Series]
    tables: dict[str, list[dict[str, typing.Any]]]   # e.g. 'top_contributors', 'languages'
    provenance: dict[str, str]                       # gitstat version, schema version, fetched-at, query hashes
```

## Error handling

- `InvalidRangeError`: `since` is after `until`, or the range contains no complete bucket at the requested granularity.
- `UnknownGroupError`: `request.groups` names a group that does not exist.
- `EmptySubjectError`: the subject has no repositories or no data in range; callers print a message rather than an empty report.
- Fetch errors (`AuthError`, `RateLimitError`, `CacheVersionError`) propagate unchanged.
- Records with `author_login is None` are counted under the `unattributed` key, never dropped.

## Implementation

All timestamps are stored UTC and converted once to `request.tz` before bucketing. Weeks follow [ISO 8601](https://en.wikipedia.org/wiki/ISO_week_date), so a week can straddle a year boundary and carries the ISO year in its label. Bucket boundaries are half-open; the partial first and last buckets are flagged in `provenance` and charted with a hatch pattern.

### Metric groups

**activity** (all subjects; per repository and aggregated)

- `commits`, `contributors` (distinct authors), `active_days`.
- **Code contributions:** `lines_added`, `lines_deleted`, `lines_net` (added minus deleted) from per-commit `additions` and `deletions`, summed per bucket. With `by_author` the same three series are produced per author login. Merge commits are excluded by default so lines are not double counted; generated and vendored files are not filtered because GitHub does not expose per-file stats cheaply (documented limitation).
- `stars`, `forks`, `watchers` cumulative and per bucket, `languages` (bytes per language, latest snapshot table).

**flow** (pull requests and issues)

- `prs_opened`, `prs_merged`, `issues_opened`, `issues_closed`.
- `time_to_first_review`, `time_to_merge`, `time_to_close` as median and 90th percentile in hours per bucket, using `statistics.quantiles`, bucketed by the end event's date.
- `pr_size` median additions plus deletions.

**delivery** (CI and delivery; approximations, labelled as proxies in reports)

- `workflow_runs`, `workflow_success_rate`, `workflow_duration_p50` from Actions runs.
- `release_count` and `release_interval_days`.
- Four-keys proxies following [DORA](https://dora.dev/guides/dora-metrics-four-keys/): deployment frequency (releases, or successful runs of the workflow named by `stats.deploy_workflow`), lead time for changes (first commit on a merged PR to its release), change failure rate (releases followed by a hotfix-labelled PR within `stats.failure_window`) and time to restore (hotfix PR open to merge). These need conventions that GitHub does not enforce, so each is only emitted when its inputs are configured and is otherwise listed as `unavailable` with the reason.

### Aggregation

- `user` subject: repositories owned by the user, with contributions by that user's login across them; `by_author` is not meaningful and is rejected.
- `repo` subject: one repository, optionally per author.
- `org` subject: sum across org repositories, with per-repo and per-author breakdowns as extra `by` series.
- A series' `points` is complete over the range: empty buckets are zero for counts and absent for medians and ratios.

### Provenance

Every result records gitstat version, cache `schema_version`, query hashes and fetch times, so a saved report can be traced to what produced it and a mismatch with a later run is detectable.

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `stats.bot_logins` | `list[str]` | `['dependabot[bot]', 'renovate[bot]']` | Authors excluded from contributor counts |
| `stats.deploy_workflow` | `str \| None` | `None` | Workflow name counted as a deployment |
| `stats.exclude_merge_commits` | `bool` | `True` | Skip merge commits in line counts |
| `stats.failure_window` | `timedelta` | `7 days` | Window for change-failure detection |
| `stats.hotfix_labels` | `list[str]` | `['hotfix']` | PR labels marking a failure fix |
| `stats.timezone` | `str` | `'UTC'` | IANA zone for bucketing |

## External dependencies

- `gitstat.fetch` (see [Fetch and cache](../fetch-and-cache/spec.md)).
- Stdlib only: `datetime`, `zoneinfo`, `statistics`, `dataclasses`.
