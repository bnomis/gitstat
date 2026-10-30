import dataclasses
import json
import re
import typing

import plotly.graph_objects
import pytest

import tests.fixtures.reports
import tests.fixtures.stats as fixture
import wambatic.reports.figures
import wambatic.stats.base

Granularity = wambatic.stats.base.Granularity
ORDER = [
    'activity-commits',
    'activity-contributors',
    'activity-active-days',
    'activity-lines',
    'flow-pull-requests',
    'flow-issues',
    'flow-review-time',
    'flow-merge-time',
    'flow-close-time',
    'flow-pr-size',
]
HEX = re.compile(r'#[0-9a-f]{6}')


def traces(
    figures: list[wambatic.reports.figures.Figure], key: str
) -> dict[str, dict[str, typing.Any]]:
    figure = next(f for f in figures if f.key == key)
    return {str(trace['name']): trace for trace in figure.data}


def annotations(figure: wambatic.reports.figures.Figure) -> list[dict[str, typing.Any]]:
    found: list[dict[str, typing.Any]] = figure.layout['annotations']  # type: ignore[assignment]
    return found


def keys_in(value: object) -> set[str]:
    """Every dictionary key anywhere inside `value`."""
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in keys_in(item)}
    if isinstance(value, list):
        return {key for item in value for key in keys_in(item)}
    return set()


def with_partial(
    result: wambatic.stats.base.StatsResult, labels: str
) -> wambatic.stats.base.StatsResult:
    return dataclasses.replace(result, provenance={**result.provenance, 'partial_buckets': labels})


def test_the_figures_come_in_the_specs_order(org_result: wambatic.stats.base.StatsResult) -> None:
    assert [f.key for f in wambatic.reports.figures.build_figures(org_result)] == ORDER


def test_each_figure_names_its_group_and_describes_itself(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    for figure in wambatic.reports.figures.build_figures(org_result):
        assert figure.group == figure.key.partition('-')[0]
        assert figure.title
        assert figure.description.endswith('.')


def test_the_count_traces_equal_the_hand_worked_months(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = wambatic.reports.figures.build_figures(org_result)
    months = list(fixture.LABELS)
    for key, name, metric in (
        ('activity-commits', 'Commits', 'commits'),
        ('activity-contributors', 'Contributors', 'contributors'),
        ('activity-active-days', 'Active days', 'active_days'),
        ('activity-lines', 'Added', 'lines_added'),
        ('activity-lines', 'Net', 'lines_net'),
    ):
        trace = traces(figures, key)[name]
        assert trace['x'] == months
        assert trace['y'] == [fixture.ORG_BY_MONTH_UTC[m][metric] for m in months]
    for key, name, metric in (
        ('flow-pull-requests', 'Opened', 'prs_opened'),
        ('flow-pull-requests', 'Merged', 'prs_merged'),
        ('flow-issues', 'Opened', 'issues_opened'),
        ('flow-issues', 'Closed', 'issues_closed'),
    ):
        trace = traces(figures, key)[name]
        assert trace['y'] == [fixture.ORG_FLOW_BY_MONTH_UTC[metric][m] for m in months]


def test_deleted_lines_are_plotted_below_zero_beside_added_lines(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = wambatic.reports.figures.build_figures(org_result)
    deleted = traces(figures, 'activity-lines')['Deleted']
    assert deleted['y'] == [-fixture.ORG_BY_MONTH_UTC[m]['lines_deleted'] for m in fixture.LABELS]
    assert deleted['type'] == 'bar'
    assert traces(figures, 'activity-lines')['Net']['type'] == 'scatter'
    layout = next(f for f in figures if f.key == 'activity-lines').layout
    assert layout['barmode'] == 'relative'


def test_a_duration_bucket_with_no_value_is_none_so_the_line_has_a_gap(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = wambatic.reports.figures.build_figures(org_result)
    for key, base in (
        ('flow-review-time', 'time_to_first_review'),
        ('flow-merge-time', 'time_to_merge'),
        ('flow-close-time', 'time_to_close'),
    ):
        for name in ('p50', 'p90'):
            trace = traces(figures, key)[name]
            expected = fixture.ORG_FLOW_BY_MONTH_UTC[f'{base}_{name}']
            assert trace['y'] == [expected.get(m) for m in fixture.LABELS]
            assert trace['connectgaps'] is False
    assert traces(figures, 'flow-merge-time')['p50']['y'] == [48.0, None, 37.5, 24.0]
    assert traces(figures, 'flow-pr-size')['p50']['y'] == [15, None, 5, 15]


def test_only_the_buckets_the_provenance_names_are_hatched_or_open(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = wambatic.reports.figures.build_figures(with_partial(org_result, '2026-10,2027-01'))
    shapes = traces(figures, 'activity-commits')['Commits']['marker']
    assert shapes == {'pattern': {'shape': ['/', '', '', '/']}}
    symbols = traces(figures, 'flow-merge-time')['p50']['marker']
    assert symbols == {'symbol': ['circle-open', 'circle', 'circle', 'circle-open']}
    whole = wambatic.reports.figures.build_figures(org_result)
    assert traces(whole, 'activity-commits')['Commits']['marker'] == {
        'pattern': {'shape': ['', '', '', '']}
    }


def test_a_figure_with_a_partial_bucket_says_so_in_its_caption(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    def captions(result: wambatic.stats.base.StatsResult) -> list[object]:
        return [
            a['text']
            for f in wambatic.reports.figures.build_figures(result)
            for a in annotations(f)
            if a.get('name') == 'caption'
        ]

    assert captions(org_result) == []
    partial = captions(with_partial(org_result, '2027-01'))
    assert partial == ['hatched or open: partial period'] * len(ORDER)


def test_a_chart_of_one_series_has_no_legend_and_one_of_several_has_one_and_end_labels(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = {f.key: f for f in wambatic.reports.figures.build_figures(org_result)}
    assert figures['activity-commits'].layout['showlegend'] is False
    assert figures['flow-pr-size'].layout['showlegend'] is False
    assert figures['flow-pull-requests'].layout['showlegend'] is True
    labels = [(a['text'], a['x'], a['y']) for a in annotations(figures['flow-merge-time'])]
    assert labels == [('p50', '2027-01', 24.0), ('p90', '2027-01', 24.0)]
    assert figures['activity-commits'].layout['annotations'] == []
    assert [a['text'] for a in annotations(figures['activity-lines'])] == ['Net']
    assert all(f.layout['hovermode'] == 'x unified' for f in figures.values())


def test_a_line_labelled_at_a_gap_is_labelled_at_its_last_value(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = {f.key: f for f in wambatic.reports.figures.build_figures(org_result)}
    close = annotations(figures['flow-close-time'])
    assert [(a['x'], a['y']) for a in close] == [('2026-11', 12.0), ('2026-11', 12.0)]


def test_the_flow_groups_alone_gives_flow_figures_only(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    flow_only = dataclasses.replace(
        org_result,
        series=[
            s
            for s in org_result.series
            if s.metric not in {'commits', 'contributors', 'active_days'}
            and not s.metric.startswith('lines_')
        ],
    )
    keys = [f.key for f in wambatic.reports.figures.build_figures(flow_only)]
    assert keys == [key for key in ORDER if key.startswith('flow-')]


def test_a_total_result_has_no_per_period_figures(
    repo_total_result: wambatic.stats.base.StatsResult,
) -> None:
    assert wambatic.reports.figures.build_figures(repo_total_result) == []


def test_a_chart_with_no_value_anywhere_is_left_out(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    quiet = dataclasses.replace(
        org_result,
        series=[
            dataclasses.replace(s, points={})
            if s.metric.startswith('time_to_close') and s.by is None
            else s
            for s in org_result.series
        ],
    )
    keys = [f.key for f in wambatic.reports.figures.build_figures(quiet)]
    assert 'flow-close-time' not in keys
    assert 'flow-merge-time' in keys


def test_no_chart_has_more_than_three_series_and_every_slot_is_one_to_three(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    for figure in wambatic.reports.figures.build_figures(org_result):
        slots = [typing.cast(dict[str, int], trace['meta'])['slot'] for trace in figure.data]
        assert 1 <= len(slots) <= 3
        assert all(slot in (1, 2, 3) for slot in slots)
        assert len(set(slots)) == len(slots)


def test_no_figure_carries_a_colour(org_result: wambatic.stats.base.StatsResult) -> None:
    for figure in wambatic.reports.figures.build_figures(org_result):
        found = keys_in(figure.data) | keys_in(figure.layout)
        assert not {key for key in found if 'color' in key.lower()}


def test_every_figure_is_valid_plotly_and_plain_json(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    for figure in wambatic.reports.figures.build_figures(with_partial(org_result, '2027-01')):
        plotly.graph_objects.Figure(data=figure.data, layout=figure.layout)
        assert json.loads(json.dumps(figure.data)) == figure.data
        assert json.loads(json.dumps(figure.layout)) == figure.layout


def test_plotly_rejects_an_unknown_property_so_the_validation_means_something() -> None:
    with pytest.raises(ValueError, match='nonsense'):
        plotly.graph_objects.Figure(data=[{'type': 'bar', 'nonsense': 1}])


def test_every_palette_value_is_a_hex_colour() -> None:
    for name, theme in wambatic.reports.figures.PALETTE.items():
        assert name in ('light', 'dark')
        for field, value in dataclasses.asdict(theme).items():
            values = value if isinstance(value, tuple) else [value]
            assert all(HEX.fullmatch(v) for v in values), field
        assert len(theme.categorical) == 3
        assert len(theme.sequential) == 5


def test_the_builder_reproduces_the_hand_checked_figures(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = {f.key: f for f in wambatic.reports.figures.build_figures(org_result)}
    for key, expected in tests.fixtures.reports.ORG_MONTH_FIGURES.items():
        assert dataclasses.asdict(figures[key]) == expected
