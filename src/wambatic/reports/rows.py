"""The table rows the terminal and the HTML page both show, as plain data: labels and numbers,
with no Rich objects and no formatting, so the two renderers cannot disagree."""

import dataclasses
import typing

import wambatic.stats.activity
import wambatic.stats.base
import wambatic.stats.flow

TOTAL_METRICS = tuple(metric for metric, _ in wambatic.stats.activity.TOTAL_METRICS)
UNATTRIBUTED = wambatic.stats.activity.UNATTRIBUTED
PARTIAL_MARK = ' *'
TOP_CONTRIBUTORS_SHOWN = 20
BREAKDOWN_TITLES = (('repo', 'By repository'), ('author', 'By author'))
SIGNED_METRICS = frozenset({'lines_net'})
FLOW_COUNTS = wambatic.stats.flow.COUNT_METRICS
FLOW_TIMES = wambatic.stats.flow.TIME_METRICS
SIZE_METRIC = wambatic.stats.flow.SIZE_METRIC
TREND_METRICS = (*TOTAL_METRICS, *FLOW_COUNTS)
NO_DATA = '-'
ACTIVITY_HEADERS = ('Commits', 'Contributors', 'Active days', 'Added', 'Deleted', 'Net')
FLOW_HEADERS = ('PRs opened', 'PRs merged', 'Issues opened', 'Issues closed')
FLOW_TIMES_METRICS = (*FLOW_TIMES, SIZE_METRIC)
FLOW_TIMES_HEADERS = (
    'Review p50',
    'Review p90',
    'Merge p50',
    'Merge p90',
    'Close p50',
    'Close p90',
    'PR size p50',
)
BREAKDOWN_HEADERS = ('Name', 'Commits', 'Added', 'Deleted', 'Net')
CONTRIBUTOR_HEADERS = ('Login', 'Commits', 'Added', 'Deleted', 'Net', 'Active days')
UNAVAILABLE_HEADERS = ('Metric', 'Reason')


@dataclasses.dataclass(frozen=True, slots=True)
class PeriodRow:
    label: str
    partial: bool
    values: tuple[float | None, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class PeriodTable:
    """One row per bucket under `metrics`, in the order of `headers`; `total` is the footer row
    when there is more than one bucket and the column can be added up, else None (a column that
    cannot be added up is None in it)."""

    title: str
    headers: tuple[str, ...]
    metrics: tuple[str, ...]
    rows: tuple[PeriodRow, ...]
    total: tuple[float | None, ...] | None

    @property
    def has_partial(self) -> bool:
        return any(row.partial for row in self.rows)


@dataclasses.dataclass(frozen=True, slots=True)
class BreakdownRow:
    name: str
    commits: float
    lines_added: float
    lines_deleted: float
    lines_net: float


@dataclasses.dataclass(frozen=True, slots=True)
class Contributor:
    login: str
    commits: int
    lines_added: int
    lines_deleted: int
    lines_net: int
    active_days: int


def total_series(
    result: wambatic.stats.base.StatsResult,
) -> dict[str, list[tuple[wambatic.stats.base.Bucket, float]]]:
    """Each total series' points (the ones with no breakdown) in bucket order, by metric."""
    return {
        series.metric: sorted(series.points.items())
        for series in result.series
        if series.by is None
    }


def bucket_list(result: wambatic.stats.base.StatsResult) -> list[wambatic.stats.base.Bucket]:
    """The result's buckets, from whichever total series is present."""
    series = total_series(result)
    for metric in (*TOTAL_METRICS, *FLOW_COUNTS):
        if metric in series:
            return [bucket for bucket, _ in series[metric]]
    return []


def partial_labels(result: wambatic.stats.base.StatsResult) -> frozenset[str]:
    return frozenset(
        label for label in result.provenance.get('partial_buckets', '').split(',') if label
    )


def contributor_count(result: wambatic.stats.base.StatsResult) -> int:
    return sum(
        1 for row in result.tables.get('top_contributors', []) if row['login'] != UNATTRIBUTED
    )


def subject_text(result: wambatic.stats.base.StatsResult) -> str:
    subject = result.subject
    name = subject.full_name if subject.kind == 'repo' else subject.login
    return f'{subject.kind} {name}'


def period_row(
    label: str, partial: frozenset[str], values: typing.Iterable[float | None]
) -> PeriodRow:
    return PeriodRow(label, label in partial, tuple(values))


def activity_table(result: wambatic.stats.base.StatsResult) -> PeriodTable | None:
    """Activity by period; None without activity series."""
    series = total_series(result)
    if 'commits' not in series:
        return None
    partial = partial_labels(result)
    rows = tuple(
        period_row(bucket.label, partial, (series[metric][index][1] for metric in TOTAL_METRICS))
        for index, (bucket, _) in enumerate(series['commits'])
    )
    total: tuple[float | None, ...] | None = None
    if len(rows) > 1:
        sums = {metric: sum(value for _, value in series[metric]) for metric in TOTAL_METRICS}
        sums['contributors'] = contributor_count(result)
        total = tuple(sums[metric] for metric in TOTAL_METRICS)
    return PeriodTable('Activity by period', ACTIVITY_HEADERS, TOTAL_METRICS, rows, total)


def flow_table(result: wambatic.stats.base.StatsResult) -> PeriodTable | None:
    """Flow by period; None without flow series."""
    series = total_series(result)
    if 'prs_opened' not in series:
        return None
    partial = partial_labels(result)
    rows = tuple(
        period_row(bucket.label, partial, (series[metric][index][1] for metric in FLOW_COUNTS))
        for index, bucket in enumerate(bucket_list(result))
    )
    total: tuple[float | None, ...] | None = None
    if len(rows) > 1:
        total = tuple(sum(value for _, value in series[metric]) for metric in FLOW_COUNTS)
    return PeriodTable('Flow by period', FLOW_HEADERS, FLOW_COUNTS, rows, total)


def flow_times_table(result: wambatic.stats.base.StatsResult) -> PeriodTable | None:
    """Flow times by period, a bucket with no value `None`; there is no total, because medians
    do not add up over buckets. None without flow series."""
    series = total_series(result)
    if 'prs_opened' not in series:
        return None
    partial = partial_labels(result)
    points = {metric: dict(series[metric]) for metric in FLOW_TIMES_METRICS}
    rows = tuple(
        period_row(
            bucket.label, partial, (points[metric].get(bucket) for metric in FLOW_TIMES_METRICS)
        )
        for bucket in bucket_list(result)
    )
    return PeriodTable('Flow times by period', FLOW_TIMES_HEADERS, FLOW_TIMES_METRICS, rows, None)


def breakdown_rows(result: wambatic.stats.base.StatsResult, kind: str) -> list[BreakdownRow] | None:
    """Each breakdown name of `kind` with its metrics summed over the range, most commits first
    and then by name, leaving out names whose metrics are all zero; None when the result has no
    breakdown of `kind`."""
    if not any(series.by_kind == kind for series in result.series):
        return None
    totals: dict[str, dict[str, float]] = {}
    for series in result.series:
        if series.by_kind == kind and series.by is not None:
            totals.setdefault(series.by, {})[series.metric] = sum(series.points.values())
    rows = [
        BreakdownRow(
            name,
            metrics['commits'],
            metrics['lines_added'],
            metrics['lines_deleted'],
            metrics['lines_net'],
        )
        for name, metrics in totals.items()
        if any(metrics.values())
    ]
    return sorted(rows, key=lambda row: (-row.commits, row.name))


def top_contributors(
    result: wambatic.stats.base.StatsResult, limit: int | None = None
) -> list[Contributor]:
    """The top-contributors table in its own order, the first `limit` rows when given."""
    rows = result.tables.get('top_contributors', [])
    return [
        Contributor(
            row['login'],
            row['commits'],
            row['lines_added'],
            row['lines_deleted'],
            row['lines_net'],
            row['active_days'],
        )
        for row in rows[:limit]
    ]


def unavailable_rows(result: wambatic.stats.base.StatsResult) -> list[tuple[str, str]]:
    return [(row['metric'], row['reason']) for row in result.tables.get('unavailable', [])]


def provenance_lines(result: wambatic.stats.base.StatsResult) -> list[str]:
    provenance = result.provenance
    keys = ['computed_at', *sorted(k for k in provenance if k.startswith('fetched_at:'))]
    keys += ['wambatic_version', 'schema_version']
    lines = [f'{key}: {provenance[key]}' for key in keys if key in provenance]
    if 'version_override_at' in provenance:
        lines.append(
            f'Warning: the cache was read with --ignore-cache-version at '
            f'{provenance["version_override_at"]}; its recorded version differs from this wambatic'
        )
    return lines
