import dataclasses
import json
import re
import typing

import plotly.graph_objects
import pytest

import tests.fixtures.reports
import tests.fixtures.stats as fixture
import wambatic.reports.figures
import wambatic.reports.rows
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
DELIVERY_ORDER = [
    'delivery-runs',
    'delivery-success-rate',
    'delivery-duration',
    'delivery-releases',
    'delivery-release-interval',
    'delivery-deployments',
    'delivery-lead-time',
    'delivery-change-failure-rate',
    'delivery-time-to-restore',
]
PROXY_METRICS = ('deployments', 'lead_time', 'change_failure_rate', 'time_to_restore')
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


def test_the_range_figures_are_the_top_contributors_and_the_breakdowns(
    org_total_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = wambatic.reports.figures.build_range_figures(org_total_result)
    assert [f.key for f in figures] == [
        'activity-top-contributors',
        'activity-by-repository',
        'activity-by-author',
    ]
    top, repos, authors = (f.data[0] for f in figures)
    assert top['y'] == [row['login'] for row in fixture.ORG_TOP_CONTRIBUTORS]
    assert top['x'] == [row['commits'] for row in fixture.ORG_TOP_CONTRIBUTORS]
    assert dict(zip(repos['y'], repos['x'], strict=True)) == {fixture.ALPHA: 6, fixture.BETA: 4}  # type: ignore[call-overload]
    assert list(zip(authors['y'], authors['x'], strict=True)) == [  # type: ignore[call-overload]
        ('Octocat', 4),
        ('hubot', 3),
        ('dependabot[bot]', 1),
        ('monalisa', 1),
        ('unattributed', 1),
    ]
    for figure in figures:
        assert figure.data[0]['orientation'] == 'h'
        assert figure.layout['yaxis']['autorange'] == 'reversed'  # type: ignore[index]


def test_the_breakdown_bars_equal_the_tables_rows(
    org_total_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = {f.key: f for f in wambatic.reports.figures.build_range_figures(org_total_result)}
    rows = wambatic.reports.rows.breakdown_rows(org_total_result, 'author')
    assert rows is not None
    data = figures['activity-by-author'].data[0]
    assert data['y'] == [row.name for row in rows]
    assert data['x'] == [row.commits for row in rows]


def test_a_repo_has_no_by_repository_figure(
    repo_total_result: wambatic.stats.base.StatsResult,
) -> None:
    keys = [f.key for f in wambatic.reports.figures.build_range_figures(repo_total_result)]
    assert 'activity-by-repository' not in keys
    assert 'activity-by-author' not in keys


def test_twenty_five_top_contributors_give_twenty_bars(
    org_total_result: wambatic.stats.base.StatsResult,
) -> None:
    many = [{**fixture.ORG_TOP_CONTRIBUTORS[0], 'login': f'person{n:02d}'} for n in range(25)]
    result = dataclasses.replace(
        org_total_result, tables={**org_total_result.tables, 'top_contributors': many}
    )
    top = wambatic.reports.figures.build_range_figures(result)[0]
    assert top.key == 'activity-top-contributors'
    assert top.data[0]['y'] == [f'person{n:02d}' for n in range(20)]


def test_range_figures_without_activity_series_are_empty(
    org_total_result: wambatic.stats.base.StatsResult,
) -> None:
    flow_only = dataclasses.replace(
        org_total_result,
        series=[s for s in org_total_result.series if s.metric.startswith(('prs', 'issues'))],
    )
    assert wambatic.reports.figures.build_range_figures(flow_only) == []


def test_range_figures_need_a_total_result(org_result: wambatic.stats.base.StatsResult) -> None:
    with pytest.raises(ValueError, match='TOTAL'):
        wambatic.reports.figures.build_range_figures(org_result)


def calendar_cells(
    figure: wambatic.reports.figures.Figure,
) -> dict[str, int | None]:
    """Each cell's day (from the hover text) with its value."""
    trace = figure.data[0]
    return {
        day: value
        for z_row, text_row in zip(trace['z'], trace['text'], strict=True)  # type: ignore[call-overload]
        for value, day in zip(z_row, text_row, strict=True)
    }


def test_the_calendar_puts_each_days_commits_in_its_week_and_weekday_cell(
    org_day_result: wambatic.stats.base.StatsResult,
) -> None:
    figure = wambatic.reports.figures.build_calendar(org_day_result)
    assert figure is not None
    assert figure.key == 'activity-calendar'
    trace: dict[str, typing.Any] = figure.data[0]
    assert trace['y'] == ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    assert trace['x'][0] == '2026-09-28'
    assert trace['x'][-1] == '2027-01-25'
    cells = calendar_cells(figure)
    expected = {
        '2026-10-05': 2,
        '2026-10-20': 2,
        '2026-10-21': 1,
        '2026-10-25': 1,
        '2026-10-26': 1,
        '2026-12-31': 1,
        '2027-01-01': 1,
        '2027-01-15': 1,
    }
    for day, commits in expected.items():
        assert cells[day] == commits
    assert cells['2026-10-06'] == 0
    week = trace['x'].index('2026-10-19')
    assert [trace['z'][weekday][week] for weekday in range(7)] == [0, 2, 1, 0, 0, 0, 1]


def test_the_calendars_cells_sum_to_the_commits_total(
    org_day_result: wambatic.stats.base.StatsResult,
) -> None:
    figure = wambatic.reports.figures.build_calendar(org_day_result)
    assert figure is not None
    total = sum(value for value in calendar_cells(figure).values() if value is not None)
    assert total == fixture.ORG_TOTAL_UTC['commits']


def test_days_outside_the_range_are_blank(org_day_result: wambatic.stats.base.StatsResult) -> None:
    figure = wambatic.reports.figures.build_calendar(org_day_result)
    assert figure is not None
    cells = calendar_cells(figure)
    for day in ('2026-09-28', '2026-09-30'):  # the Monday to Wednesday before `since`
        assert cells[day] is None
    assert cells['2026-10-01'] == 0
    assert cells['2027-01-31'] == 0
    assert all(day not in cells for day in ('2027-02-01',))
    assert figure.data[0]['meta'] == {'scale': 'sequential'}


def test_days_after_until_are_blank(org_day_result: wambatic.stats.base.StatsResult) -> None:
    short = dataclasses.replace(org_day_result, until=fixture.UNTIL.replace(day=29))
    figure = wambatic.reports.figures.build_calendar(short)
    assert figure is not None
    cells = calendar_cells(figure)
    assert cells['2027-01-29'] == 0
    assert cells['2027-01-30'] is None
    assert cells['2027-01-31'] is None


def test_the_calendar_needs_a_day_result_and_activity_series(
    org_result: wambatic.stats.base.StatsResult,
    org_day_result: wambatic.stats.base.StatsResult,
) -> None:
    with pytest.raises(ValueError, match='DAY'):
        wambatic.reports.figures.build_calendar(org_result)
    flow_only = dataclasses.replace(
        org_day_result,
        series=[s for s in org_day_result.series if s.metric.startswith(('prs', 'issues'))],
    )
    assert wambatic.reports.figures.build_calendar(flow_only) is None


def test_the_range_and_calendar_figures_are_valid_plotly_and_colourless(
    org_total_result: wambatic.stats.base.StatsResult,
    org_day_result: wambatic.stats.base.StatsResult,
) -> None:
    calendar = wambatic.reports.figures.build_calendar(org_day_result)
    assert calendar is not None
    for figure in [*wambatic.reports.figures.build_range_figures(org_total_result), calendar]:
        plotly.graph_objects.Figure(data=figure.data, layout=figure.layout)
        assert json.loads(json.dumps(figure.data)) == figure.data
        found = keys_in(figure.data) | keys_in(figure.layout)
        assert not {key for key in found if 'color' in key.lower() and key != 'colorbar'}


def delivery_figures(
    result: wambatic.stats.base.StatsResult,
) -> list[wambatic.reports.figures.Figure]:
    return wambatic.reports.figures.build_figures(result)


def test_the_delivery_figures_come_in_the_specs_order_and_belong_to_delivery(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = delivery_figures(delivery_result)
    assert [f.key for f in figures] == DELIVERY_ORDER
    assert {f.group for f in figures} == {'delivery'}
    assert all(f.description.endswith('.') for f in figures)


def test_every_delivery_figure_is_valid_plotly_plain_json_and_colourless(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    for figure in delivery_figures(with_partial(delivery_result, '2027-01')):
        plotly.graph_objects.Figure(data=figure.data, layout=figure.layout)
        assert json.loads(json.dumps(figure.data)) == figure.data
        assert json.loads(json.dumps(figure.layout)) == figure.layout
        assert not HEX.search(json.dumps([figure.data, figure.layout]))


def test_the_ratios_are_plotted_as_per_cent_on_a_fixed_axis(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = {f.key: f for f in delivery_figures(delivery_result)}
    success = figures['delivery-success-rate']
    (trace,) = success.data
    # 4 / 5 in October and 2 / 4 in January; November and December have no completed run
    assert trace['y'] == [80.0, None, None, 50.0]
    failure = figures['delivery-change-failure-rate']
    y = failure.data[0]['y']
    assert y[0] == pytest.approx(100 / 3)  # type: ignore[index]
    assert y[1:] == [None, 0.0, 0.0]  # type: ignore[index]
    for figure in (success, failure):
        assert figure.layout['yaxis']['range'] == [0, 100]  # type: ignore[index]


def test_the_counts_and_days_of_the_delivery_figures_are_whole_numbers(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = {f.key: f for f in delivery_figures(delivery_result)}
    assert figures['delivery-runs'].data[0]['y'] == [7, 0, 1, 5]
    assert figures['delivery-releases'].data[0]['y'] == [4, 0, 1, 1]
    assert figures['delivery-deployments'].data[0]['y'] == [3, 0, 1, 1]
    assert figures['delivery-release-interval'].data[0]['y'] == [14, None, 67, 90]


def test_a_chart_of_a_proxy_that_is_not_emitted_is_left_out(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    kept = [s for s in delivery_result.series if not s.metric.startswith(PROXY_METRICS)]
    figures = delivery_figures(dataclasses.replace(delivery_result, series=kept))
    assert [f.key for f in figures] == [
        'delivery-runs',
        'delivery-success-rate',
        'delivery-duration',
        'delivery-releases',
        'delivery-release-interval',
    ]


def test_a_result_without_delivery_series_has_no_delivery_figure(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    assert not any(f.group == 'delivery' for f in delivery_figures(org_result))


POPULARITY_ORDER = [
    'popularity-stars-added',
    'popularity-stars-total',
    'popularity-forks-added',
    'popularity-forks-total',
]


def test_the_popularity_figures_come_in_the_specs_order_and_belong_to_popularity(
    popularity_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = wambatic.reports.figures.build_figures(popularity_result)
    assert [f.key for f in figures] == POPULARITY_ORDER
    assert {f.group for f in figures} == {'popularity'}
    assert all(f.description.endswith('.') for f in figures)


def test_the_popularity_traces_equal_the_hand_worked_months(
    popularity_result: wambatic.stats.base.StatsResult,
) -> None:
    figures = {f.key: f for f in wambatic.reports.figures.build_figures(popularity_result)}
    months = sorted(fixture.ORG_POPULARITY_BY_MONTH_UTC)
    for key, metric, kind in (
        ('popularity-stars-added', 'stars_added', 'bar'),
        ('popularity-stars-total', 'stars_total', 'scatter'),
        ('popularity-forks-added', 'forks_added', 'bar'),
        ('popularity-forks-total', 'forks_total', 'scatter'),
    ):
        (trace,) = figures[key].data
        assert trace['type'] == kind
        assert trace['x'] == months
        assert trace['y'] == [int(fixture.ORG_POPULARITY_BY_MONTH_UTC[m][metric]) for m in months]


def test_every_popularity_figure_is_valid_plotly_plain_json_and_colourless(
    popularity_result: wambatic.stats.base.StatsResult,
) -> None:
    for figure in wambatic.reports.figures.build_figures(popularity_result):
        plotly.graph_objects.Figure(data=figure.data, layout=figure.layout)
        assert json.loads(json.dumps(figure.data)) == figure.data
        assert not HEX.search(json.dumps([figure.data, figure.layout]))


def test_the_languages_figure_plots_each_share_in_per_cent_first_row_at_the_top(
    popularity_total: wambatic.stats.base.StatsResult,
) -> None:
    (figure,) = wambatic.reports.figures.build_range_figures(popularity_total)
    assert (figure.key, figure.group) == ('popularity-languages', 'popularity')
    (trace,) = figure.data
    assert trace['orientation'] == 'h'
    assert trace['y'] == [row['language'] for row in fixture.ORG_LANGUAGES_TABLE]
    assert trace['x'] == [row['share'] * 100 for row in fixture.ORG_LANGUAGES_TABLE]
    assert trace['y'][-1] == 'Other'
    assert figure.layout['yaxis']['autorange'] == 'reversed'  # type: ignore[index]
    plotly.graph_objects.Figure(data=figure.data, layout=figure.layout)


def test_the_languages_figure_shows_only_the_top_rows_and_is_absent_when_the_table_is_empty(
    popularity_total: wambatic.stats.base.StatsResult,
) -> None:
    many = [{'language': f'L{n}', 'bytes': 1, 'share': 0.05} for n in range(15)]
    figure = wambatic.reports.figures.build_range_figures(
        dataclasses.replace(popularity_total, tables={**popularity_total.tables, 'languages': many})
    )[0]
    assert len(figure.data[0]['y']) == wambatic.reports.rows.TOP_LANGUAGES_SHOWN  # type: ignore[arg-type]
    empty = dataclasses.replace(
        popularity_total, tables={**popularity_total.tables, 'languages': []}
    )
    assert wambatic.reports.figures.build_range_figures(empty) == []
