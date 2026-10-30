import dataclasses

import tests.fixtures.stats as fixture
import wambatic.reports.rows
import wambatic.stats.base

ACTIVITY_METRICS = wambatic.reports.rows.TOTAL_METRICS
FLOW_METRICS = wambatic.reports.rows.FLOW_COUNTS


def table_by_label(table: wambatic.reports.rows.PeriodTable) -> dict[str, dict[str, float | None]]:
    return {row.label: dict(zip(table.metrics, row.values, strict=True)) for row in table.rows}


def test_the_activity_rows_are_the_hand_worked_months(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    table = wambatic.reports.rows.activity_table(org_result)
    assert table is not None
    assert table_by_label(table) == fixture.ORG_BY_MONTH_UTC
    assert table.headers == wambatic.reports.rows.ACTIVITY_HEADERS


def test_the_activity_total_row_adds_up_and_counts_contributors_once(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    table = wambatic.reports.rows.activity_table(org_result)
    assert table is not None
    assert table.total is not None
    assert dict(zip(table.metrics, table.total, strict=True)) == fixture.ORG_TOTAL_UTC


def test_the_buckets_the_provenance_names_are_marked_partial_on_their_rows_only(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    whole = wambatic.reports.rows.activity_table(org_result)
    assert whole is not None
    assert not whole.has_partial
    partial = dataclasses.replace(
        org_result, provenance={**org_result.provenance, 'partial_buckets': '2026-10,2027-01'}
    )
    table = wambatic.reports.rows.activity_table(partial)
    assert table is not None
    assert {row.label for row in table.rows if row.partial} == {'2026-10', '2027-01'}
    assert table.has_partial


def test_the_flow_rows_are_the_hand_worked_months(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    table = wambatic.reports.rows.flow_table(org_result)
    assert table is not None
    expected = {
        label: {metric: fixture.ORG_FLOW_BY_MONTH_UTC[metric][label] for metric in FLOW_METRICS}
        for label in fixture.LABELS
    }
    assert table_by_label(table) == expected
    assert table.total is not None
    assert table.total == tuple(
        sum(fixture.ORG_FLOW_BY_MONTH_UTC[metric].values()) for metric in FLOW_METRICS
    )


def test_a_flow_times_bucket_with_no_value_is_none_and_there_is_no_total(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    table = wambatic.reports.rows.flow_times_table(org_result)
    assert table is not None
    assert table.total is None
    rows = table_by_label(table)
    assert rows['2026-11']['time_to_merge_p50'] is None
    assert rows['2026-11']['time_to_close_p50'] == 12.0
    for label in fixture.LABELS:
        for metric in wambatic.reports.rows.FLOW_TIMES_METRICS:
            assert rows[label][metric] == fixture.ORG_FLOW_BY_MONTH_UTC[metric].get(label)


def test_the_breakdown_rows_add_up_to_the_total_row(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    activity = wambatic.reports.rows.activity_table(org_result)
    assert activity is not None
    assert activity.total is not None
    totals = dict(zip(activity.metrics, activity.total, strict=True))
    for kind in ('repo', 'author'):
        rows = wambatic.reports.rows.breakdown_rows(org_result, kind)
        assert rows is not None
        assert sum(row.commits for row in rows) == totals['commits']
        assert sum(row.lines_added for row in rows) == totals['lines_added']
        assert sum(row.lines_deleted for row in rows) == totals['lines_deleted']
        assert sum(row.lines_net for row in rows) == totals['lines_net']


def test_the_breakdown_rows_are_ordered_by_commits_then_name(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    rows = wambatic.reports.rows.breakdown_rows(org_result, 'author')
    assert rows is not None
    assert [row.name for row in rows] == [
        'Octocat',
        'hubot',
        'dependabot[bot]',
        'monalisa',
        'unattributed',
    ]
    repos = wambatic.reports.rows.breakdown_rows(org_result, 'repo')
    assert repos is not None
    assert [(row.name, row.commits) for row in repos] == [
        (fixture.ALPHA, 6),
        (fixture.BETA, 4),
    ]


def test_all_zero_breakdown_rows_are_left_out(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    quiet = wambatic.stats.base.Series(
        'commits',
        'count',
        {bucket: 0 for bucket in org_result.series[0].points},
        by='nobody',
        by_kind='author',
    )
    result = dataclasses.replace(org_result, series=[*org_result.series, quiet])
    rows = wambatic.reports.rows.breakdown_rows(result, 'author')
    assert rows is not None
    assert 'nobody' not in {row.name for row in rows}


def test_a_kind_with_no_breakdown_is_none(
    repo_total_result: wambatic.stats.base.StatsResult,
) -> None:
    assert wambatic.reports.rows.breakdown_rows(repo_total_result, 'author') is None
    assert wambatic.reports.rows.breakdown_rows(repo_total_result, 'repo') is None


def test_a_one_bucket_result_has_one_row_and_no_total(
    repo_total_result: wambatic.stats.base.StatsResult,
) -> None:
    for build in (
        wambatic.reports.rows.activity_table,
        wambatic.reports.rows.flow_table,
        wambatic.reports.rows.flow_times_table,
    ):
        table = build(repo_total_result)
        assert table is not None
        assert len(table.rows) == 1
        assert table.total is None


def test_a_result_without_a_group_has_no_table_for_it(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    flow_only = dataclasses.replace(
        org_result,
        series=[s for s in org_result.series if s.metric not in ACTIVITY_METRICS],
    )
    assert wambatic.reports.rows.activity_table(flow_only) is None
    assert wambatic.reports.rows.flow_table(flow_only) is not None
    activity_only = dataclasses.replace(
        org_result, series=[s for s in org_result.series if s.metric in ACTIVITY_METRICS]
    )
    assert wambatic.reports.rows.flow_table(activity_only) is None
    assert wambatic.reports.rows.flow_times_table(activity_only) is None


def test_the_top_contributors_come_in_the_tables_order_and_can_be_limited(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    rows = wambatic.reports.rows.top_contributors(org_result)
    assert [dataclasses.asdict(row) for row in rows] == fixture.ORG_TOP_CONTRIBUTORS
    assert wambatic.reports.rows.top_contributors(org_result, 2) == rows[:2]
    assert wambatic.reports.rows.contributor_count(org_result) == 3


def test_the_subject_text_names_the_kind_and_the_login_or_repo(
    org_result: wambatic.stats.base.StatsResult,
    repo_total_result: wambatic.stats.base.StatsResult,
) -> None:
    assert wambatic.reports.rows.subject_text(org_result) == 'org octo-org'
    assert wambatic.reports.rows.subject_text(repo_total_result) == 'repo octo-org/alpha'


def test_the_provenance_lines_start_with_the_computed_time(
    org_result: wambatic.stats.base.StatsResult,
) -> None:
    lines = wambatic.reports.rows.provenance_lines(org_result)
    assert lines[0].startswith('computed_at: ')
    assert lines[-1].startswith('schema_version: ')
    warned = dataclasses.replace(
        org_result,
        provenance={**org_result.provenance, 'version_override_at': '2027-01-20T12:00:00+00:00'},
    )
    assert 'ignore-cache-version' in wambatic.reports.rows.provenance_lines(warned)[-1]
