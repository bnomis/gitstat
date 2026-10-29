import dataclasses
import datetime
import io
import json
import typing

import hypothesis
import hypothesis.strategies as st

import gitstat.fetch.base
import gitstat.reports.base
import gitstat.settings
import gitstat.stats.base
import tests.conftest
import tests.fixtures.stats as fixture

TOP_LEVEL_KEYS = [
    'format_version',
    'subject',
    'request',
    'since',
    'until',
    'series',
    'tables',
    'provenance',
]
REQUEST_KEYS = ['granularity', 'groups', 'since', 'until', 'by_author', 'tz', 'settings']
SERIES_KEYS = ['metric', 'unit', 'by', 'by_kind', 'points']
POINT_KEYS = ['label', 'start', 'value']


def as_dict(result: gitstat.stats.base.StatsResult) -> dict[str, typing.Any]:
    return gitstat.reports.base.result_to_dict(result)


def render(result: gitstat.stats.base.StatsResult) -> str:
    stream = io.StringIO()
    gitstat.reports.base.render_json(result, stream)
    return stream.getvalue()


def test_top_level_keys_are_in_the_specified_order(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    data = as_dict(org_result)
    assert list(data) == TOP_LEVEL_KEYS
    assert data['format_version'] == 1
    assert list(data['request']) == REQUEST_KEYS
    assert list(data['series'][0]) == SERIES_KEYS
    assert list(data['series'][0]['points'][0]) == POINT_KEYS


def test_the_header_fields_are_as_requested_and_as_resolved(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    data = as_dict(org_result)
    assert data['subject'] == {'kind': 'org', 'login': 'octo-org', 'name': None}
    assert data['since'] == '2026-10-01'
    assert data['until'] == '2027-01-31'
    request = data['request']
    assert request['granularity'] == 'month'
    assert request['groups'] == ['activity', 'flow']
    assert (request['since'], request['until']) == ('2026-10-01', '2027-01-31')
    assert request['by_author'] is True
    assert request['tz'] == 'UTC'


def test_unrequested_dates_are_null_and_a_repo_subject_has_its_name(
    stats_fetcher: gitstat.fetch.base.Fetcher,
) -> None:
    result = tests.conftest.compute_stats(
        stats_fetcher,
        gitstat.fetch.base.Subject('repo', 'octo-org', 'alpha'),
        gitstat.stats.base.StatsRequest(granularity=gitstat.stats.base.Granularity.TOTAL),
    )
    data = as_dict(result)
    request = data['request']
    assert (request['since'], request['until']) == (None, None)
    assert data['subject'] == {'kind': 'repo', 'login': 'octo-org', 'name': 'alpha'}
    assert isinstance(data['since'], str)


def test_render_json_round_trips_through_result_to_dict(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    assert json.loads(render(org_result)) == as_dict(org_result)


def test_output_ends_with_exactly_one_newline(org_result: gitstat.stats.base.StatsResult) -> None:
    text = render(org_result)
    assert text.endswith('}\n')
    assert not text.endswith('\n\n')


def test_a_series_points_are_in_bucket_order_with_matching_label_and_start(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    data = as_dict(org_result)
    commits = [s for s in data['series'] if (s['metric'], s['by']) == ('commits', None)]
    (total,) = commits
    assert [p['label'] for p in total['points']] == list(fixture.LABELS)
    assert [p['start'] for p in total['points']] == [
        '2026-10-01',
        '2026-11-01',
        '2026-12-01',
        '2027-01-01',
    ]
    assert [p['value'] for p in total['points']] == [7, 0, 1, 2]


def test_count_day_and_line_values_are_integers(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    data = as_dict(org_result)
    for series in data['series']:
        for point in series['points']:
            assert type(point['value']) is int, (series['metric'], point)


def test_other_units_are_floats() -> None:
    bucket = gitstat.stats.base.Bucket(datetime.date(2026, 10, 1), '2026-10')
    series = gitstat.stats.base.Series('lead_time', 'hours', {bucket: 3.0})
    (point,) = typing.cast(
        list[dict[str, typing.Any]], gitstat.reports.base.series_to_dict(series)['points']
    )
    assert type(point['value']) is float


def test_the_failure_window_is_written_as_seconds_and_parses_back(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    data = as_dict(org_result)
    settings = data['request']['settings']
    assert settings['failure_window'] == '604800s'
    assert gitstat.settings.parse_duration(settings['failure_window']) == datetime.timedelta(days=7)
    assert settings['bot_logins'] == ['dependabot[bot]', 'renovate[bot]']
    assert settings['deploy_workflow'] is None


def test_non_ascii_logins_are_written_as_they_are(
    org_result: gitstat.stats.base.StatsResult,
) -> None:
    rows = [{**row, 'login': 'zoë'} for row in org_result.tables['top_contributors'][:1]]
    changed = dataclasses.replace(
        org_result, tables={**org_result.tables, 'top_contributors': rows}
    )
    text = render(changed)
    assert 'zoë' in text
    assert '\\u' not in text


durations = st.integers(min_value=0, max_value=10**8).map(lambda n: datetime.timedelta(seconds=n))
words = st.lists(st.text(max_size=12), max_size=4).map(tuple)


@hypothesis.settings(
    max_examples=20,
    deadline=10000,
    suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture],
)
@hypothesis.given(
    settings=st.builds(
        gitstat.settings.StatsSettings,
        bot_logins=words,
        deploy_workflow=st.none() | st.text(max_size=12),
        exclude_merge_commits=st.booleans(),
        failure_window=durations,
        hotfix_labels=words,
        timezone=st.text(max_size=12),
    )
)
def test_any_stats_settings_survive_json_and_durations_parse_back(
    org_result: gitstat.stats.base.StatsResult, settings: gitstat.settings.StatsSettings
) -> None:
    result = dataclasses.replace(
        org_result, request=dataclasses.replace(org_result.request, settings=settings)
    )
    written = as_dict(result)['request']['settings']
    assert json.loads(json.dumps(written)) == written
    assert gitstat.settings.parse_duration(written['failure_window']) == settings.failure_window
