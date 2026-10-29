import dataclasses
import datetime
import io
import re

import hypothesis
import hypothesis.strategies as st
import pytest
import rich.console

import gitstat.fetch.base
import gitstat.reports.terminal
import gitstat.stats.base
import tests.conftest
import tests.fixtures.stats as fixture

METRICS = ('commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net')
Granularity = gitstat.stats.base.Granularity


def render(result: gitstat.stats.base.StatsResult, width: int = 120) -> str:
    stream = io.StringIO()
    console = rich.console.Console(
        file=stream, width=width, color_system=None, legacy_windows=False
    )
    gitstat.reports.terminal.render_terminal(result, console)
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
    fetcher: gitstat.fetch.base.Fetcher, **changes: object
) -> gitstat.stats.base.StatsResult:
    fields: dict[str, object] = {'since': fixture.SINCE, 'until': fixture.UNTIL}
    fields.update(changes)
    request = gitstat.stats.base.StatsRequest(**fields)  # type: ignore[arg-type]
    return tests.conftest.compute_stats(fetcher, fixture.ORG, request)


def test_sparkline_known_cases() -> None:
    sparkline = gitstat.reports.terminal.sparkline
    assert sparkline([0, 7]) == '▁█'
    assert sparkline([3, 3, 3]) == '▁▁▁'
    assert sparkline([]) == ''
    assert sparkline([-4, 0, 4]) == '▁▅█'
    assert sparkline([5]) == '▁'


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(st.lists(st.floats(min_value=-1e6, max_value=1e6), max_size=40))
def test_sparkline_has_one_block_per_value(values: list[float]) -> None:
    line = gitstat.reports.terminal.sparkline(values)
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
    assert gitstat.reports.terminal.format_number(value, signed=signed) == expected


def test_the_title_names_the_subject_range_granularity_and_zone(
    org_result: gitstat.stats.base.StatsResult,
    repo_total_result: gitstat.stats.base.StatsResult,
) -> None:
    assert render(org_result).splitlines()[0] == (
        'org octo-org, 2026-10-01 to 2027-01-31, by month, UTC'
    )
    assert render(repo_total_result).splitlines()[0] == (
        'repo octo-org/alpha, 2026-10-01 to 2027-01-31, total, UTC'
    )


def test_the_period_table_and_total_row_equal_the_hand_checked_monthly_totals(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    rows = period_rows(render(org_result))
    for label, expected in fixture.ORG_BY_MONTH_UTC.items():
        assert rows[label] == expected
    assert rows['Total'] == fixture.ORG_TOTAL_UTC


def test_partial_periods_are_marked_and_the_caption_says_so(
    stats_fetcher: gitstat.fetch.base.Fetcher,
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
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    output = render(org_result)
    assert ' *' not in output
    assert 'partial period' not in output


def test_one_bucket_prints_one_row_and_no_total_row_or_trends(
    repo_total_result: gitstat.stats.base.StatsResult,
) -> None:
    output = render(repo_total_result)
    rows = period_rows(output)
    assert list(rows) == ['total']
    assert 'Total' not in output
    assert 'Trends' not in output


def test_trends_show_one_line_per_metric_with_its_range(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    lines = render(org_result).splitlines()
    start = lines.index('Trends')
    assert [line.split()[0] for line in lines[start + 1 : start + 7]] == list(METRICS)
    assert lines[start + 1].split() == ['commits', '█▁▂▃', '0', 'to', '7']
    assert lines[start + 6].split() == ['lines_net', '█▁▂▂', '0', 'to', '+34']


def test_narrow_trends_keep_the_latest_periods_and_fit_the_width(
    stats_fetcher: gitstat.fetch.base.Fetcher,
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


def test_trends_that_fit_are_not_cropped(org_result: gitstat.stats.base.StatsResult) -> None:
    assert 'last' not in render(org_result)


def test_a_cache_version_override_prints_a_warning_naming_the_flag(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    provenance = {**org_result.provenance, 'version_override_at': '2027-02-02T09:00:00+00:00'}
    output = render(dataclasses.replace(org_result, provenance=provenance))
    (warning,) = [line for line in output.splitlines() if line.startswith('Warning')]
    assert '--ignore-cache-version' in warning
    assert '2027-02-02T09:00:00+00:00' in warning
    assert 'Warning' not in render(org_result)


def test_the_provenance_footer_lists_the_run_and_the_versions(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    lines = render(org_result).splitlines()
    footer = lines[lines.index('Provenance') + 1 :]
    assert footer == [
        'computed_at: 2027-01-20T12:00:00+00:00',
        'fetched_at:commits: 2027-02-01T10:00:00+00:00',
        f'gitstat_version: {org_result.provenance["gitstat_version"]}',
        'schema_version: 1',
    ]
