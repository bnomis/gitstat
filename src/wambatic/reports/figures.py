"""Charts as plain Plotly JSON (the `data` and `layout` plotly.js takes), built from a
`StatsResult` without importing plotly. Colours are left out: each trace carries a palette slot
and the page script fills in the colours of the active theme, so no figure is tied to one."""

import dataclasses
import typing

import wambatic.reports.base
import wambatic.reports.rows
import wambatic.stats.base

Hex = str
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
PARTIAL_CAPTION = 'hatched or open: partial period'
CATEGORICAL_SLOTS = 3
HEIGHT = 320


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
    group: typing.Literal['activity', 'flow']
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
    group: typing.Literal['activity', 'flow']
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
)
GROUP_METRIC = {'activity': 'commits', 'flow': 'prs_opened'}


def number(value: float | None, unit: str, negate: bool) -> float | None:
    """A series point as a JSON value: a whole number for a count, days or lines, and its
    negation for a bar drawn below zero."""
    if value is None:
        return None
    value = -value if negate else value
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
    return {
        'height': HEIGHT,
        'margin': {'l': 64, 'r': 56 if legend else 24, 't': 48 if legend else 16, 'b': 72},
        'font': {'family': FONT},
        'xaxis': {'type': 'category', 'automargin': True},
        'yaxis': {'title': {'text': unit}, 'automargin': True, 'zeroline': True},
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
    series = wambatic.reports.rows.total_series(result)
    labels = [bucket.label for bucket in wambatic.reports.rows.bucket_list(result)]
    flags = partial_flags(labels, wambatic.reports.rows.partial_labels(result))
    units = {s.metric: s.unit for s in result.series if s.by is None}
    figures: list[Figure] = []
    for chart in CHARTS:
        if GROUP_METRIC[chart.group] not in series:
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
