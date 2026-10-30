import dataclasses
import datetime
import io
import re

import hypothesis
import hypothesis.strategies as st
import pytest
import rich.console

import tests.conftest
import tests.fixtures.reports
import tests.fixtures.stats as fixture
import wambatic.fetch.base
import wambatic.reports.rows
import wambatic.reports.terminal
import wambatic.stats.base

METRICS = ('commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net')
Granularity = wambatic.stats.base.Granularity


def render(result: wambatic.stats.base.StatsResult, width: int = 120) -> str:
    stream = io.StringIO()
    console = rich.console.Console(
        file=stream, width=width, color_system=None, legacy_windows=False
    )
    wambatic.reports.terminal.render_terminal(result, console)
    return stream.getvalue()


def number(text: str) -> int:
    return int(text.replace(',', ''))


def period_rows(output: str) -> dict[str, dict[str, int]]:
    """The rows of the Activity by period table, by label (without a partial mark)."""
    rows: dict[str, dict[str, int]] = {}
    for line in output.splitlines():
        match = re.match(r'\s+(Total|total|\d{4}(?:-\w+)*)(?: \*)?\s+(-?[\d,+ ]+)$', line)
        if match is None:
            continue
        values = [number(word) for word in match.group(2).split()]
        if len(values) == len(METRICS):
            rows[match.group(1)] = dict(zip(METRICS, values, strict=True))
    return rows


def recompute(
    fetcher: wambatic.fetch.base.Fetcher, **changes: object
) -> wambatic.stats.base.StatsResult:
    fields: dict[str, object] = {'since': fixture.SINCE, 'until': fixture.UNTIL}
    fields.update(changes)
    request = wambatic.stats.base.StatsRequest(**fields)  # type: ignore[arg-type]
    return tests.conftest.compute_stats(fetcher, fixture.ORG, request)


def test_sparkline_known_cases() -> None:
    sparkline = wambatic.reports.terminal.sparkline
    assert sparkline([0, 7]) == '▁█'
    assert sparkline([3, 3, 3]) == '▁▁▁'
    assert sparkline([]) == ''
    assert sparkline([-4, 0, 4]) == '▁▅█'
    assert sparkline([5]) == '▁'


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(st.lists(st.floats(min_value=-1e6, max_value=1e6), max_size=40))
def test_sparkline_has_one_block_per_value(values: list[float]) -> None:
    line = wambatic.reports.terminal.sparkline(values)
    assert len(line) == len(values)
    assert all('▁' <= char <= '█' for char in line)
    if values and max(values) > min(values):
        assert line[values.index(max(values))] == '█'
        assert line[values.index(min(values))] == '▁'


@pytest.mark.parametrize(
    ('value', 'signed', 'expected'),
    [
        (1234, False, '1,234'),
        (1234, True, '+1,234'),
        (-56, True, '-56'),
        (-56, False, '-56'),
        (0, True, '0'),
        (7.0, False, '7'),
        (1234567.5, False, '1,234,567.50'),
    ],
)
def test_format_number(value: float, signed: bool, expected: str) -> None:
    assert wambatic.reports.terminal.format_number(value, signed=signed) == expected


def test_the_title_names_the_subject_range_granularity_and_zone(
    org_result: wambatic.stats.base.StatsResult,
    repo_total_result: wambatic.stats.base.StatsResult,
) -> None:
    assert render(org_result).splitlines()[0] == (
        'org octo-org, 2026-10-01 to 2027-01-31, by month, UTC'
    )
    assert render(repo_total_result).splitlines()[0] == (
        'repo octo-org/alpha, 2026-10-01 to 2027-01-31, total, UTC'
    )


def test_the_period_table_and_total_row_equal_the_hand_checked_monthly_totals(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    rows = period_rows(render(org_result))
    for label, expected in fixture.ORG_BY_MONTH_UTC.items():
        assert rows[label] == expected
    assert rows['Total'] == fixture.ORG_TOTAL_UTC


def test_partial_periods_are_marked_and_the_caption_says_so(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = recompute(
        stats_fetcher, since=datetime.date(2026, 10, 5), until=datetime.date(2027, 1, 20)
    )
    assert result.provenance['partial_buckets'] == '2026-10,2027-01'
    output = render(result)
    assert '2026-10 *' in output
    assert '2027-01 *' in output
    assert '2026-11 *' not in output
    assert '* partial period' in output


def test_a_whole_range_has_no_partial_mark_or_caption(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    output = render(org_result)
    assert ' *' not in output
    assert 'partial period' not in output


def test_one_bucket_prints_one_row_and_no_total_row_or_trends(
    repo_total_result: wambatic.stats.base.StatsResult,
) -> None:
    output = render(repo_total_result)
    rows = period_rows(output)
    assert list(rows) == ['total']
    assert 'Total' not in output
    assert 'Trends' not in output


def test_trends_show_one_line_per_metric_with_its_range(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    lines = render(org_result).splitlines()
    start = lines.index('Trends')
    assert [line.split()[0] for line in lines[start + 1 : start + 7]] == list(METRICS)
    assert lines[start + 1].split() == ['commits', '█▁▂▃', '0', 'to', '7']
    assert lines[start + 6].split() == ['lines_net', '█▁▂▂', '0', 'to', '+34']


def test_narrow_trends_keep_the_latest_periods_and_fit_the_width(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = recompute(stats_fetcher, granularity=Granularity.DAY)
    lines = render(result, width=40).splitlines()
    trends = lines[lines.index('Trends') + 1 : lines.index('Trends') + 7]
    assert len(trends) == len(METRICS)
    for line in trends:
        assert re.search(r'last \d+ periods?$', line), line
        assert len(line) <= 40
    wide = render(result, width=100).splitlines()
    wide_trends = wide[wide.index('Trends') + 1 : wide.index('Trends') + 7]
    assert all('last' in line and len(line) <= 100 for line in wide_trends)


def test_trends_that_fit_are_not_cropped(org_result: wambatic.stats.base.StatsResult) -> None:
    assert 'last' not in render(org_result)


def test_a_cache_version_override_prints_a_warning_naming_the_flag(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    provenance = {**org_result.provenance, 'version_override_at': '2027-02-02T09:00:00+00:00'}
    output = render(dataclasses.replace(org_result, provenance=provenance))
    (warning,) = [line for line in output.splitlines() if line.startswith('Warning')]
    assert '--ignore-cache-version' in warning
    assert '2027-02-02T09:00:00+00:00' in warning
    assert 'Warning' not in render(org_result)


def test_the_provenance_footer_lists_the_run_and_the_versions(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    lines = render(org_result).splitlines()
    footer = lines[lines.index('Provenance') + 1 :]
    assert footer == [
        'computed_at: 2027-01-20T12:00:00+00:00',
        'fetched_at:commits: 2027-02-01T10:00:00+00:00',
        'fetched_at:issues: 2027-02-01T10:00:00+00:00',
        'fetched_at:pull_requests: 2027-02-01T10:00:00+00:00',
        f'wambatic_version: {org_result.provenance["wambatic_version"]}',
        f'schema_version: {org_result.provenance["schema_version"]}',
    ]


def without_trailing_spaces(text: str) -> str:
    return '\n'.join(line.rstrip() for line in text.split('\n'))


def test_the_org_by_month_rendering_matches_the_known_good_text(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    expected = tests.fixtures.reports.ORG_MONTH_TERMINAL.format(
        wambatic_version=org_result.provenance['wambatic_version'],
        schema_version=org_result.provenance['schema_version'],
    )
    assert without_trailing_spaces(render(org_result)) == expected


def table_rows(output: str, title: str) -> dict[str, list[int]]:
    """The rows of the table headed `title`, by first column, as their numeric cells."""
    lines = output.splitlines()
    rows: dict[str, list[int]] = {}
    first = next(index for index, line in enumerate(lines) if line.strip() == title)
    for line in lines[first + 4 :]:
        if not line.strip():
            break
        name, *cells = line.split()
        rows[name] = [number(cell) for cell in cells]
    return rows


def test_the_repository_rows_add_up_to_the_total_row(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    output = render(org_result)
    rows = table_rows(output, 'By repository')
    assert set(rows) == {fixture.ALPHA, fixture.BETA}
    total = period_rows(output)['Total']
    sums = [sum(column) for column in zip(*rows.values(), strict=True)]
    assert sums == [
        total['commits'],
        total['lines_added'],
        total['lines_deleted'],
        total['lines_net'],
    ]


def test_the_author_rows_add_up_to_the_total_row_and_are_ordered_by_commits_then_name(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    output = render(org_result)
    rows = table_rows(output, 'By author')
    assert list(rows) == ['Octocat', 'hubot', 'dependabot[bot]', 'monalisa', 'unattributed']
    total = period_rows(output)['Total']
    sums = [sum(column) for column in zip(*rows.values(), strict=True)]
    assert sums == [
        total['commits'],
        total['lines_added'],
        total['lines_deleted'],
        total['lines_net'],
    ]


def test_by_author_appears_only_when_requested(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    output = render(recompute(stats_fetcher))
    assert 'By repository' in output
    assert 'By author' not in output


def test_a_repo_has_no_repository_breakdown(
    repo_total_result: wambatic.stats.base.StatsResult,
) -> None:
    assert 'By repository' not in render(repo_total_result)


def test_breakdown_rows_that_are_all_zero_are_left_out(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    zero = wambatic.stats.base.Series(
        'commits', 'count', dict.fromkeys(org_result.series[0].points, 0), 'ghost', 'author'
    )
    padded = dataclasses.replace(org_result, series=[*org_result.series, zero])
    assert 'ghost' not in render(padded)


def test_top_contributors_follow_the_table_order(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    rows = table_rows(render(org_result), 'Top contributors')
    assert list(rows) == [row['login'] for row in fixture.ORG_TOP_CONTRIBUTORS]
    assert rows['hubot'] == [3, 35, 12, 23, 3]


def test_at_most_twenty_top_contributors_are_shown_then_a_count_of_the_rest(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    many = [{**fixture.ORG_TOP_CONTRIBUTORS[0], 'login': f'person{n:02d}'} for n in range(25)]
    output = render(
        dataclasses.replace(org_result, tables={**org_result.tables, 'top_contributors': many})
    )
    shown = [line for line in output.splitlines() if line.strip().startswith('person')]
    assert len(shown) == wambatic.reports.terminal.TOP_CONTRIBUTORS_SHOWN == 20
    assert shown[-1].split()[0] == 'person19'
    assert 'and 5 more' in output


def test_exactly_twenty_top_contributors_have_no_more_line(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    twenty = [{**fixture.ORG_TOP_CONTRIBUTORS[0], 'login': f'person{n:02d}'} for n in range(20)]
    output = render(
        dataclasses.replace(org_result, tables={**org_result.tables, 'top_contributors': twenty})
    )
    assert ' more' not in output


def test_the_default_groups_list_nothing_as_unavailable(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    assert org_result.tables['unavailable'] == []
    assert 'Unavailable' not in render(org_result)


def test_unavailable_lists_each_row_with_its_reason(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    rows = [{'metric': 'deployments', 'reason': 'no releases in the cache'}]
    output = render(
        dataclasses.replace(org_result, tables={**org_result.tables, 'unavailable': rows})
    )
    assert 'Unavailable' in output
    assert re.search(r'^\s+deployments\s+no releases in the cache', output, re.MULTILINE)


# Flow tables


def flow_only_result(
    fetcher: wambatic.fetch.base.Fetcher, **changes: object
) -> wambatic.stats.base.StatsResult:
    return recompute(fetcher, groups=frozenset({'flow'}), **changes)


def table_lines(output: str, title: str) -> list[str]:
    """The lines of the table headed `title`, up to its blank line or the next heading."""
    lines = [line.rstrip() for line in output.splitlines()]
    first = lines.index(title)
    found: list[str] = []
    for line in lines[first + 1 :]:
        if not line.strip():
            if found:
                break
            continue
        found.append(line)
    return found


def test_a_flow_only_result_prints_the_flow_tables_and_trends_but_no_activity_tables(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    output = render(flow_only_result(stats_fetcher))
    for title in ('Flow by period', 'Flow times by period', 'Trends'):
        assert title in [line.rstrip() for line in output.splitlines()], title
    for title in ('Activity by period', 'By repository', 'By author', 'Top contributors'):
        assert title not in output
    trend = output.split('Trends')[1].split('\n\n')[0]
    assert {line.split()[0] for line in trend.strip().splitlines()} == {
        'prs_opened',
        'prs_merged',
        'issues_opened',
        'issues_closed',
    }


def test_an_activity_only_result_prints_no_flow_tables(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    output = render(recompute(stats_fetcher, groups=frozenset({'activity'})))
    assert 'Flow' not in output
    assert 'prs_opened' not in output
    assert 'Activity by period' in output


def test_an_absent_duration_point_shows_a_dash_and_a_value_one_decimal(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    rows = {
        line.split()[0]: line.split()[1:]
        for line in table_lines(render(org_result), 'Flow times by period')[2:]
        if line.split()[0].startswith('20')
    }
    assert rows['2026-11'] == ['-', '-', '-', '-', '12.0', '12.0', '-']
    assert rows['2026-12'] == ['2.0', '2.0', '37.5', '37.5', '-', '-', '5']
    assert rows['2026-10'][:2] == ['12.0', '21.6']


def test_the_flow_times_caption_says_hours_and_no_data_and_has_no_total_row(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    output = render(org_result)
    assert 'hours; - no data' in output
    assert not any(
        line.split()[:1] == ['Total'] for line in table_lines(output, 'Flow times by period')
    )
    assert any(line.split()[:1] == ['Total'] for line in table_lines(output, 'Flow by period'))


def test_a_single_bucket_has_no_total_row_in_flow_by_period(
    repo_total_result: wambatic.stats.base.StatsResult,
) -> None:
    output = render(repo_total_result)
    assert 'Flow by period' in output
    assert not any(line.split()[:1] == ['Total'] for line in table_lines(output, 'Flow by period'))
    assert 'Trends' not in output


def test_a_partial_bucket_is_marked_in_both_flow_tables_and_the_caption_says_so(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = flow_only_result(stats_fetcher, since=datetime.date(2026, 10, 15))
    output = render(result)
    for title in ('Flow by period', 'Flow times by period'):
        assert any(line.split()[:2] == ['2026-10', '*'] for line in table_lines(output, title))
    assert '* partial period; hours; - no data' in output


def test_the_flow_trend_lines_fit_at_width_40(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    output = render(flow_only_result(stats_fetcher), width=40)
    trend = output.split('Trends')[1].split('\n\n')[0].strip().splitlines()
    assert len(trend) == 4
    assert all(len(line) <= 40 for line in trend)


def test_a_delivery_only_result_prints_the_delivery_tables_and_trends_but_no_other_group(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    output = render(delivery_result)
    lines = [line.rstrip() for line in output.splitlines()]
    for title in ('Delivery by period', 'DORA proxies by period', 'Trends'):
        assert title in lines, title
    for title in ('Activity by period', 'Flow by period', 'Flow times by period', 'By repository'):
        assert title not in output
    trend = output.split('Trends')[1].split('\n\n')[0]
    assert {line.split()[0] for line in trend.strip().splitlines()} == {
        'workflow_runs',
        'release_count',
        'deployments',
    }


def test_the_delivery_table_shows_percentages_minutes_days_and_a_dash_for_no_value(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    output = render(delivery_result)
    lines = table_lines(output, 'Delivery by period')
    header, _, october, november, december, january, _, total, *_ = lines
    assert header.split() == [
        'Period',
        'Runs',
        'Success',
        'Duration',
        'p50',
        'Duration',
        'p90',
        'Releases',
        'Release',
        'interval',
        'p50',
    ]
    # 4 / 5 successes, minutes to one decimal place, whole days
    assert october.split() == ['2026-10', '7', '80.0%', '6.0', '10.8', '4', '14']
    assert november.split() == ['2026-11', '0', '-', '-', '-', '0', '-']
    assert december.split()[:3] == ['2026-12', '1', '-']
    assert january.split() == ['2027-01', '5', '50.0%', '20.0', '28.0', '1', '90']
    assert total.split() == ['Total', '13', '-', '-', '-', '6', '-']
    assert 'minutes and days; - no data' in output


def test_the_dora_table_shows_percentages_hours_and_a_total_for_deployments_only(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    output = render(delivery_result)
    lines = table_lines(output, 'DORA proxies by period')
    _, _, october, *_, total = lines[:-1] if lines[-1].startswith('proxies') else lines
    assert october.split() == ['2026-10', '3', '145.0', '303.6', '33.3%', '48.0', '48.0']
    assert total.split() == ['Total', '5', '-', '-', '-', '-', '-']
    assert 'proxies: see the README; hours; - no data' in output


def test_a_partial_period_is_marked_in_the_delivery_tables_and_their_captions(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    partial = dataclasses.replace(
        delivery_result, provenance={**delivery_result.provenance, 'partial_buckets': '2027-01'}
    )
    output = render(partial)
    assert output.count('2027-01 *') == 2
    assert '* partial period; minutes and days; - no data' in output
    assert '* partial period; proxies: see the README; hours; - no data' in output


def test_a_result_with_some_proxies_prints_only_their_columns(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    kept = [
        s for s in delivery_result.series if not s.metric.startswith(('time_to_restore', 'change'))
    ]
    output = render(dataclasses.replace(delivery_result, series=kept))
    header = table_lines(output, 'DORA proxies by period')[0]
    assert 'Lead time p90' in header
    assert 'Restore' not in header
    assert 'Change failure' not in header


def test_the_delivery_ratio_has_no_trend_line(
    delivery_result: wambatic.stats.base.StatsResult,
) -> None:
    trend = render(delivery_result).split('Trends')[1].split('\n\n')[0]
    assert 'rate' not in trend
    assert 'p50' not in trend


# Popularity tables


def popularity_output(fetcher: wambatic.fetch.base.Fetcher, **changes: object) -> str:
    return render(recompute(fetcher, groups=frozenset({'popularity'}), **changes))


def test_the_popularity_tables_print_with_their_captions(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    output = popularity_output(stats_fetcher)
    titles = [line.rstrip() for line in output.splitlines()]
    for title in ('Popularity by period', 'Popularity now', 'Languages', 'Trends'):
        assert title in titles, title
    period = table_lines(output, 'Popularity by period')
    assert period[0].split() == [
        'Period',
        'Stars',
        'added',
        'Stars',
        'total',
        'Forks',
        'added',
        'Forks',
        'total',
    ]
    rows = {line.split()[0]: line.split()[1:] for line in period[2:] if line.split()[0][:2] == '20'}
    assert rows['2026-10'] == ['3', '5', '1', '2']
    assert rows['2026-11'] == ['0', '5', '1', '3']
    assert rows['2026-12'] == ['1', '6', '0', '3']
    assert rows['2027-01'] == ['2', '8', '1', '4']
    total = [line.split() for line in period if line.split()[:1] == ['Total']]
    assert total == [['Total', '6', '8', '3', '4']]  # added: 3 + 0 + 1 + 2 and 1 + 1 + 0 + 1
    assert 'totals: stars and forks that exist now, by when they were made' in output


def test_popularity_now_lists_the_repositories_and_a_total_row(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    output = popularity_output(stats_fetcher)
    now = [line.split() for line in table_lines(output, 'Popularity now')]
    assert now[0] == ['Repository', 'Stars', 'Forks', 'Watchers']
    assert ['octo-org/alpha', '6', '3', '4'] in now
    assert ['octo-org/beta', '4', '2', '2'] in now
    assert ['Total', '10', '5', '6'] in now
    assert 'as of the last sync; forks: whole network' in output


def test_the_languages_table_gives_shares_as_percentages_with_one_decimal(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    output = popularity_output(stats_fetcher)
    rows = [line.split() for line in table_lines(output, 'Languages')[2:]]
    # 10000 / 14500, 3000 / 14500, 1000 / 14500 and 500 / 14500
    assert rows == [
        ['Python', '10,000', '69.0%'],
        ['Go', '3,000', '20.7%'],
        ['Shell', '1,000', '6.9%'],
        ['Other', '500', '3.4%'],
    ]


def test_languages_beyond_the_limit_are_counted_in_an_and_more_line(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = recompute(stats_fetcher, groups=frozenset({'popularity'}))
    many = [
        {'language': f'L{n:02d}', 'bytes': 100 - n, 'share': (100 - n) / 1000} for n in range(14)
    ]
    output = render(dataclasses.replace(result, tables={**result.tables, 'languages': many}))
    shown = table_lines(output, 'Languages')[2:]
    assert len(shown) == wambatic.reports.rows.TOP_LANGUAGES_SHOWN
    assert shown[-1].split()[0] == 'L09'
    assert 'and 4 more' in output


def test_an_empty_languages_table_prints_no_languages_section(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = recompute(stats_fetcher, groups=frozenset({'popularity'}))
    output = render(dataclasses.replace(result, tables={**result.tables, 'languages': []}))
    assert 'Languages' not in output
    assert 'Popularity now' in output


def test_popularity_only_prints_no_other_groups_tables_and_its_four_trend_lines(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    output = popularity_output(stats_fetcher)
    for title in (
        'Activity by period',
        'Flow by period',
        'Delivery by period',
        'DORA proxies by period',
    ):
        assert title not in output
    trend = output.split('Trends')[1].split('\n\n')[0]
    assert [line.split()[0] for line in trend.strip().splitlines()] == [
        'stars_added',
        'stars_total',
        'forks_added',
        'forks_total',
    ]


def test_a_popularity_report_with_a_partial_bucket_marks_it(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    output = popularity_output(stats_fetcher, since=datetime.date(2026, 10, 15))
    period = table_lines(output, 'Popularity by period')
    assert any(line.split()[:2] == ['2026-10', '*'] for line in period)
    assert '* partial period; totals: stars and forks' in output


def test_the_default_groups_print_no_popularity_tables(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    output = render(org_result)
    assert 'Popularity' not in output
    assert 'Languages' not in output
