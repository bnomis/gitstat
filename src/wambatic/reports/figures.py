"""Charts as plain Plotly JSON (the `data` and `layout` plotly.js takes), built from a
`StatsResult` without importing plotly. Colours are left out: each trace carries a palette slot
and the page script fills in the colours of the active theme, so no figure is tied to one."""

import dataclasses
import datetime
import typing

import wambatic.reports.base
import wambatic.reports.rows
import wambatic.stats.base

Hex = str
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
PARTIAL_CAPTION = 'hatched or open: partial period'
CATEGORICAL_SLOTS = 3
HEIGHT = 320
PERCENT = 'per cent'
PERCENT_RANGE = [0, 100]
PERCENT_FACTOR = 100


@dataclasses.dataclass(frozen=True, slots=True)
class Theme:
    """The colours of one theme: the series colours by slot, the heat-map's ramp from low to
    high, and the chrome."""

    categorical: tuple[Hex, ...]
    sequential: tuple[Hex, ...]
    surface: Hex
    page: Hex
    ink: Hex
    ink_secondary: Hex
    grid: Hex


# The validated reference palette of the dataviz skill available to Claude Code sessions, read
# 2026-10-30 (reports spec, Palette and themes): its first three categorical slots, which it
# validates for every pair in both themes, its blue sequential ramp, and its surfaces and inks.
PALETTE: dict[typing.Literal['dark', 'light'], Theme] = {
    'light': Theme(
        categorical=('#2a78d6', '#eb6834', '#1baf7a'),
        sequential=('#cde2fb', '#86b6ef', '#3987e5', '#256abf', '#0d366b'),
        surface='#fcfcfb',
        page='#f9f9f7',
        ink='#0b0b0b',
        ink_secondary='#52514e',
        grid='#e1e0d9',
    ),
    'dark': Theme(
        categorical=('#3987e5', '#d95926', '#199e70'),
        sequential=('#104281', '#1c5cab', '#3987e5', '#6da7ec', '#b7d3f6'),
        surface='#1a1a19',
        page='#0d0d0d',
        ink='#f0efec',
        ink_secondary='#c3c2b7',
        grid='#2c2c2a',
    ),
}


@dataclasses.dataclass(frozen=True, slots=True)
class Figure:
    key: str
    group: typing.Literal['activity', 'delivery', 'flow', 'popularity']
    title: str
    description: str
    data: list[dict[str, object]]
    layout: dict[str, object]


@dataclasses.dataclass(frozen=True, slots=True)
class Trace:
    """One series of a per-period chart: a bar or a line, in palette slot `slot`."""

    metric: str
    name: str
    kind: typing.Literal['bar', 'line']
    slot: int
    below_zero: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class Chart:
    key: str
    group: typing.Literal['activity', 'delivery', 'flow', 'popularity']
    title: str
    description: str
    unit: str
    traces: tuple[Trace, ...]
    barmode: typing.Literal['group', 'relative'] = 'group'


def durations(key: str, metric: str, title: str, noun: str) -> Chart:
    return Chart(
        key,
        'flow',
        f'Time to {title} per period',
        f'Lines of the median and 90th percentile hours to {title} for each period, with a gap '
        f'where no {noun} has a value.',
        'hours',
        (Trace(f'{metric}_p50', 'p50', 'line', 1), Trace(f'{metric}_p90', 'p90', 'line', 2)),
    )


CHARTS = (
    Chart(
        'activity-commits',
        'activity',
        'Commits per period',
        'Bars of the commits in each period.',
        'commits',
        (Trace('commits', 'Commits', 'bar', 1),),
    ),
    Chart(
        'activity-contributors',
        'activity',
        'Contributors per period',
        'Bars of the distinct contributors in each period.',
        'contributors',
        (Trace('contributors', 'Contributors', 'bar', 1),),
    ),
    Chart(
        'activity-active-days',
        'activity',
        'Active days per period',
        'Bars of the days with at least one commit in each period.',
        'days',
        (Trace('active_days', 'Active days', 'bar', 1),),
    ),
    Chart(
        'activity-lines',
        'activity',
        'Lines added and deleted per period',
        'Bars of lines added above zero and lines deleted below it for each period, with a line '
        'for the net.',
        'lines',
        (
            Trace('lines_added', 'Added', 'bar', 1),
            Trace('lines_deleted', 'Deleted', 'bar', 2, below_zero=True),
            Trace('lines_net', 'Net', 'line', 3),
        ),
        'relative',
    ),
    Chart(
        'flow-pull-requests',
        'flow',
        'Pull requests per period',
        'Grouped bars of the pull requests opened and merged in each period.',
        'pull requests',
        (Trace('prs_opened', 'Opened', 'bar', 1), Trace('prs_merged', 'Merged', 'bar', 2)),
    ),
    Chart(
        'flow-issues',
        'flow',
        'Issues per period',
        'Grouped bars of the issues opened and closed in each period.',
        'issues',
        (Trace('issues_opened', 'Opened', 'bar', 1), Trace('issues_closed', 'Closed', 'bar', 2)),
    ),
    durations('flow-review-time', 'time_to_first_review', 'first review', 'review'),
    durations('flow-merge-time', 'time_to_merge', 'merge', 'merge'),
    durations('flow-close-time', 'time_to_close', 'close', 'issue'),
    Chart(
        'flow-pr-size',
        'flow',
        'Pull request size per period',
        'A line of the median lines changed by the pull requests merged in each period, with a '
        'gap where none merged.',
        'lines',
        (Trace('pr_size_p50', 'p50', 'line', 1),),
    ),
    Chart(
        'delivery-runs',
        'delivery',
        'Workflow runs per period',
        'Bars of the Actions workflow runs created in each period.',
        'runs',
        (Trace('workflow_runs', 'Runs', 'bar', 1),),
    ),
    Chart(
        'delivery-success-rate',
        'delivery',
        'Workflow success rate',
        'A line of the per cent of completed runs that succeeded in each period, on a fixed axis '
        'from 0 to 100, with a gap where no run completed.',
        PERCENT,
        (Trace('workflow_success_rate', 'Success rate', 'line', 1),),
    ),
    Chart(
        'delivery-duration',
        'delivery',
        'Workflow duration',
        'Lines of the median and 90th percentile minutes the completed runs took in each period.',
        'minutes',
        (
            Trace('workflow_duration_p50', 'p50', 'line', 1),
            Trace('workflow_duration_p90', 'p90', 'line', 2),
        ),
    ),
    Chart(
        'delivery-releases',
        'delivery',
        'Releases per period',
        'Bars of the releases published in each period.',
        'releases',
        (Trace('release_count', 'Releases', 'bar', 1),),
    ),
    Chart(
        'delivery-release-interval',
        'delivery',
        'Release interval',
        'A line of the median whole days since the previous release of the repository, for the '
        'releases published in each period.',
        'days',
        (Trace('release_interval_p50', 'p50', 'line', 1),),
    ),
    Chart(
        'delivery-deployments',
        'delivery',
        'Deployments per period',
        'Bars of the deployments in each period.',
        'deployments',
        (Trace('deployments', 'Deployments', 'bar', 1),),
    ),
    Chart(
        'delivery-lead-time',
        'delivery',
        'Lead time',
        'Lines of the median and 90th percentile hours from the first commit of a merged pull '
        'request to the next deployment, for the deployments in each period.',
        'hours',
        (Trace('lead_time_p50', 'p50', 'line', 1), Trace('lead_time_p90', 'p90', 'line', 2)),
    ),
    Chart(
        'delivery-change-failure-rate',
        'delivery',
        'Change failure rate',
        'A line of the per cent of deployments followed by a hotfix pull request within the '
        'failure window, on a fixed axis from 0 to 100.',
        PERCENT,
        (Trace('change_failure_rate', 'Change failure rate', 'line', 1),),
    ),
    Chart(
        'delivery-time-to-restore',
        'delivery',
        'Time to restore',
        'Lines of the median and 90th percentile hours from opening to merging a hotfix pull '
        'request, for those merged in each period.',
        'hours',
        (
            Trace('time_to_restore_p50', 'p50', 'line', 1),
            Trace('time_to_restore_p90', 'p90', 'line', 2),
        ),
    ),
    Chart(
        'popularity-stars-added',
        'popularity',
        'Stars per period',
        'Bars of the stars given in each period.',
        'stars',
        (Trace('stars_added', 'Stars', 'bar', 1),),
    ),
    Chart(
        'popularity-stars-total',
        'popularity',
        'Stars over time',
        'A line of the stars that exist now, counted by when they were given, up to the end of '
        'each period.',
        'stars',
        (Trace('stars_total', 'Stars', 'line', 1),),
    ),
    Chart(
        'popularity-forks-added',
        'popularity',
        'Forks per period',
        'Bars of the forks made in each period.',
        'forks',
        (Trace('forks_added', 'Forks', 'bar', 1),),
    ),
    Chart(
        'popularity-forks-total',
        'popularity',
        'Forks over time',
        'A line of the forks that exist now, counted by when they were made, up to the end of '
        'each period.',
        'forks',
        (Trace('forks_total', 'Forks', 'line', 1),),
    ),
)


def number(value: float | None, unit: str, negate: bool) -> float | None:
    """A series point as a JSON value: a whole number for a count, days or lines, a ratio as a
    per cent, and its negation for a bar drawn below zero."""
    if value is None:
        return None
    value = -value if negate else value
    if unit == 'ratio':
        return value * PERCENT_FACTOR
    return int(value) if unit in wambatic.reports.base.INTEGER_UNITS else value


def partial_flags(labels: list[str], partial: frozenset[str]) -> list[bool]:
    return [label in partial for label in labels]


def trace_json(
    trace: Trace, labels: list[str], values: list[float | None], partial: list[bool]
) -> dict[str, object]:
    if trace.kind == 'bar':
        return {
            'type': 'bar',
            'name': trace.name,
            'x': labels,
            'y': values,
            'marker': {'pattern': {'shape': ['/' if flag else '' for flag in partial]}},
            'meta': {'slot': trace.slot},
        }
    return {
        'type': 'scatter',
        'mode': 'lines+markers',
        'name': trace.name,
        'x': labels,
        'y': values,
        'marker': {'symbol': ['circle-open' if flag else 'circle' for flag in partial]},
        'connectgaps': False,
        'meta': {'slot': trace.slot},
    }


def end_label(name: str, labels: list[str], values: list[float | None]) -> dict[str, object] | None:
    """An annotation naming a line at its last point that has a value."""
    for label, value in zip(reversed(labels), reversed(values), strict=True):
        if value is not None:
            return {
                'x': label,
                'y': value,
                'xref': 'x',
                'yref': 'y',
                'text': name,
                'showarrow': False,
                'xanchor': 'left',
                'xshift': 6,
            }
    return None


def caption_annotation(text: str) -> dict[str, object]:
    return {
        'name': 'caption',
        'xref': 'paper',
        'yref': 'paper',
        'x': 0,
        'y': -0.3,
        'xanchor': 'left',
        'yanchor': 'top',
        'text': text,
        'showarrow': False,
        'font': {'size': 12},
    }


def chart_layout(
    unit: str, legend: bool, barmode: str, annotations: list[dict[str, object]]
) -> dict[str, object]:
    yaxis: dict[str, object] = {'title': {'text': unit}, 'automargin': True, 'zeroline': True}
    if unit == PERCENT:
        yaxis['range'] = PERCENT_RANGE
    return {
        'height': HEIGHT,
        'margin': {'l': 64, 'r': 56 if legend else 24, 't': 48 if legend else 16, 'b': 72},
        'font': {'family': FONT},
        'xaxis': {'type': 'category', 'automargin': True},
        'yaxis': yaxis,
        'barmode': barmode,
        'hovermode': 'x unified',
        'showlegend': legend,
        'legend': {'orientation': 'h', 'x': 0, 'y': 1.15},
        'annotations': annotations,
    }


def build_figures(result: wambatic.stats.base.StatsResult) -> list[Figure]:
    """The per-period charts of the result's total series, in page order and only for the groups
    the result holds; `[]` for a TOTAL result, whose one bucket has no trend to chart."""
    if result.request.granularity is wambatic.stats.base.Granularity.TOTAL:
        return []
    present = {
        'activity': wambatic.reports.rows.has_activity(result),
        'delivery': wambatic.reports.rows.has_delivery(result),
        'flow': wambatic.reports.rows.has_flow(result),
        'popularity': wambatic.reports.rows.has_popularity(result),
    }
    series = wambatic.reports.rows.total_series(result)
    labels = [bucket.label for bucket in wambatic.reports.rows.bucket_list(result)]
    flags = partial_flags(labels, wambatic.reports.rows.partial_labels(result))
    units = {s.metric: s.unit for s in result.series if s.by is None}
    figures: list[Figure] = []
    for chart in CHARTS:
        if not present[chart.group] or any(t.metric not in series for t in chart.traces):
            continue
        points = {t.metric: dict(series[t.metric]) for t in chart.traces}
        buckets = wambatic.reports.rows.bucket_list(result)
        values = {
            t.metric: [
                number(points[t.metric].get(bucket), units[t.metric], t.below_zero)
                for bucket in buckets
            ]
            for t in chart.traces
        }
        if all(value is None for column in values.values() for value in column):
            continue
        legend = len(chart.traces) > 1
        annotations: list[dict[str, object]] = []
        if legend:
            for trace in chart.traces:
                if trace.kind == 'line' and (
                    label := end_label(trace.name, labels, values[trace.metric])
                ):
                    annotations.append(label)
        if any(flags):
            annotations.append(caption_annotation(PARTIAL_CAPTION))
        figures.append(
            Figure(
                chart.key,
                chart.group,
                chart.title,
                chart.description,
                [trace_json(t, labels, values[t.metric], flags) for t in chart.traces],
                chart_layout(chart.unit, legend, chart.barmode, annotations),
            )
        )
    return figures


WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
BAR_ROW_HEIGHT = 28
BAR_CHART_PADDING = 96


def bars_layout(unit: str, rows: int) -> dict[str, object]:
    """A horizontal bar chart's layout, tall enough for `rows` bars, the first at the top."""
    return {
        'height': max(HEIGHT // 2, BAR_ROW_HEIGHT * rows + BAR_CHART_PADDING),
        'margin': {'l': 16, 'r': 24, 't': 16, 'b': 56},
        'font': {'family': FONT},
        'xaxis': {'title': {'text': unit}, 'automargin': True, 'zeroline': True},
        'yaxis': {'type': 'category', 'autorange': 'reversed', 'automargin': True},
        'hovermode': 'closest',
        'showlegend': False,
        'annotations': [],
    }


def bars(
    key: str,
    group: typing.Literal['activity', 'popularity'],
    title: str,
    description: str,
    name: str,
    unit: str,
    labels: list[str],
    values: list[float],
) -> Figure:
    trace: dict[str, object] = {
        'type': 'bar',
        'orientation': 'h',
        'name': name,
        'x': values,
        'y': labels,
        'meta': {'slot': 1},
    }
    return Figure(key, group, title, description, [trace], bars_layout(unit, len(labels)))


def commit_bars(
    key: str, title: str, description: str, names: list[str], commits: list[float]
) -> Figure:
    return bars(
        key,
        'activity',
        title,
        description,
        'Commits',
        'commits',
        names,
        [int(value) for value in commits],
    )


def activity_range_figures(total: wambatic.stats.base.StatsResult) -> list[Figure]:
    figures: list[Figure] = []
    top = wambatic.reports.rows.top_contributors(
        total, wambatic.reports.rows.TOP_CONTRIBUTORS_SHOWN
    )
    if top:
        figures.append(
            commit_bars(
                'activity-top-contributors',
                'Top contributors',
                'Horizontal bars of the commits of the top contributors, the most at the top.',
                [row.login for row in top],
                [row.commits for row in top],
            )
        )
    for kind, key, title, noun in (
        ('repo', 'activity-by-repository', 'Commits by repository', 'repository'),
        ('author', 'activity-by-author', 'Commits by author', 'author'),
    ):
        rows = wambatic.reports.rows.breakdown_rows(total, kind)
        if rows:
            figures.append(
                commit_bars(
                    key,
                    title,
                    f'Horizontal bars of the commits of each {noun}, the most at the top.',
                    [row.name for row in rows],
                    [row.commits for row in rows],
                )
            )
    return figures


def languages_figure(total: wambatic.stats.base.StatsResult) -> Figure | None:
    languages = wambatic.reports.rows.languages_rows(
        total, wambatic.reports.rows.TOP_LANGUAGES_SHOWN
    )
    if languages is None:
        return None
    return bars(
        'popularity-languages',
        'popularity',
        'Languages',
        'Horizontal bars of the share of each language in the code, the largest at the top.',
        'Share',
        PERCENT,
        [row.language for row in languages.rows],
        [row.share * PERCENT_FACTOR for row in languages.rows],
    )


def build_range_figures(total: wambatic.stats.base.StatsResult) -> list[Figure]:
    """The whole-range charts of a TOTAL result: horizontal bars of commits (the top
    contributors, then each breakdown the result holds, with the tables' rows) when it has
    activity series, then the languages' shares when its languages table is not empty. Raises
    ValueError for any other granularity."""
    if total.request.granularity is not wambatic.stats.base.Granularity.TOTAL:
        raise ValueError(
            f'build_range_figures needs a TOTAL result, not {total.request.granularity}'
        )
    figures = activity_range_figures(total) if wambatic.reports.rows.has_activity(total) else []
    if (languages := languages_figure(total)) is not None:
        figures.append(languages)
    return figures


def build_calendar(day: wambatic.stats.base.StatsResult) -> Figure | None:
    """The commits-by-day heat-map of a DAY result: a column for each ISO week in the range
    (x is its Monday) and a row for each weekday, Monday at the top, a day outside the range
    `None` so it is blank. None without activity series. Raises ValueError for any other
    granularity."""
    if day.request.granularity is not wambatic.stats.base.Granularity.DAY:
        raise ValueError(f'build_calendar needs a DAY result, not {day.request.granularity}')
    if not wambatic.reports.rows.has_activity(day):
        return None
    series = wambatic.reports.rows.total_series(day)
    commits = {bucket.start: value for bucket, value in series['commits']}
    first = day.since - datetime.timedelta(days=day.since.weekday())
    weeks = (day.until - first).days // 7 + 1
    mondays = [first + datetime.timedelta(weeks=week) for week in range(weeks)]
    z: list[list[int | None]] = []
    text: list[list[str]] = []
    for weekday in range(len(WEEKDAYS)):
        cells = [monday + datetime.timedelta(days=weekday) for monday in mondays]
        z.append(
            [
                int(commits.get(cell, 0)) if day.since <= cell <= day.until else None
                for cell in cells
            ]
        )
        text.append([cell.isoformat() for cell in cells])
    trace: dict[str, object] = {
        'type': 'heatmap',
        'x': [monday.isoformat() for monday in mondays],
        'y': list(WEEKDAYS),
        'z': z,
        'text': text,
        'hovertemplate': '%{text}: %{z} commits<extra></extra>',
        'hoverongaps': False,
        'xgap': 2,
        'ygap': 2,
        'zmin': 0,
        'colorbar': {'title': {'text': 'commits'}},
        'meta': {'scale': 'sequential'},
    }
    layout: dict[str, object] = {
        'height': HEIGHT // 2 + 40,
        'margin': {'l': 48, 'r': 16, 't': 16, 'b': 72},
        'font': {'family': FONT},
        'xaxis': {'type': 'category', 'title': {'text': 'week starting'}, 'automargin': True},
        'yaxis': {'type': 'category', 'autorange': 'reversed', 'automargin': True},
        'hovermode': 'closest',
        'annotations': [],
    }
    return Figure(
        'activity-calendar',
        'activity',
        'Commits by day',
        'A calendar heat-map of the commits on each day, a column for each week.',
        [trace],
        layout,
    )
