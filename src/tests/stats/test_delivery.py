import dataclasses
import datetime
import zoneinfo

import hypothesis
import hypothesis.strategies as st
import pytest

import tests.fixtures.stats as fixture
import wambatic.fetch.base
import wambatic.settings
import wambatic.stats.base
import wambatic.stats.buckets
import wambatic.stats.delivery

Granularity = wambatic.stats.base.Granularity
Series = wambatic.stats.base.Series
UTC = datetime.UTC
BERLIN = zoneinfo.ZoneInfo('Europe/Berlin')
ORG = {fixture.ALPHA, fixture.BETA}
ORG_RUNS = [r for r in fixture.WORKFLOW_RUNS if r.repo in ORG]
ORG_RELEASES = [r for r in fixture.RELEASES if r.repo in ORG]
ORG_PULLS = [p for p in fixture.PULL_REQUESTS if p.repo in ORG]
SETTINGS = wambatic.settings.StatsSettings()
DEPLOY_YML = dataclasses.replace(SETTINGS, deploy_workflow='deploy.yml')
DEPLOY_NAME = dataclasses.replace(SETTINGS, deploy_workflow='Deploy')
ACTIONS_AND_RELEASES = [
    'workflow_runs',
    'workflow_success_rate',
    'workflow_duration_p50',
    'workflow_duration_p90',
    'release_count',
    'release_interval_p50',
]
PROXIES = [
    'deployments',
    'lead_time_p50',
    'lead_time_p90',
    'change_failure_rate',
    'time_to_restore_p50',
    'time_to_restore_p90',
]


def run(
    runs: list[wambatic.fetch.base.WorkflowRun] | None = None,
    releases: list[wambatic.fetch.base.Release] | None = None,
    pulls: list[wambatic.fetch.base.PullRequest] | None = None,
    granularity: Granularity = Granularity.MONTH,
    tz: datetime.tzinfo = UTC,
    since: datetime.date = fixture.SINCE,
    until: datetime.date = fixture.UNTIL,
    settings: wambatic.settings.StatsSettings = SETTINGS,
) -> tuple[list[Series], list[dict[str, str]]]:
    buckets = wambatic.stats.buckets.bucket_range(since, until, granularity)
    return wambatic.stats.delivery.aggregate(
        ORG_RUNS if runs is None else runs,
        ORG_RELEASES if releases is None else releases,
        ORG_PULLS if pulls is None else pulls,
        buckets,
        tz,
        since,
        until,
        settings,
    )


def pick(series: list[Series], metric: str) -> dict[str, float]:
    (found,) = [s for s in series if s.metric == metric]
    return {bucket.label: value for bucket, value in found.points.items()}


def check(series: list[Series], expected: dict[str, dict[str, float]], metrics: list[str]) -> None:
    for metric in metrics:
        assert pick(series, metric) == pytest.approx(expected.get(metric, {})), metric


def a_run(
    created: str, conclusion: str | None, minutes: int = 5, **changes: object
) -> wambatic.fetch.base.WorkflowRun:
    return fixture.run(fixture.ALPHA, 1, created, conclusion, minutes, **changes)  # type: ignore[arg-type]


# Actions and releases


def test_the_fixture_by_month_in_utc_matches_the_hand_written_values() -> None:
    series, _ = run()
    check(series, fixture.ORG_DELIVERY_BY_MONTH_UTC, ACTIONS_AND_RELEASES)


def test_the_fixture_by_month_in_berlin_moves_what_the_midnight_crossing_records_move() -> None:
    series, _ = run(tz=BERLIN)
    check(series, fixture.ORG_DELIVERY_BY_MONTH_BERLIN, ACTIONS_AND_RELEASES)


def test_series_come_in_the_listed_order_with_the_listed_units() -> None:
    series, _ = run(settings=DEPLOY_YML)
    assert [(s.metric, s.unit) for s in series] == list(wambatic.stats.delivery.DELIVERY_METRICS)
    assert all(s.by is None and s.by_kind is None for s in series)
    assert {s.unit for s in series} == {'count', 'ratio', 'minutes', 'days', 'hours'}


def test_counts_are_zero_in_an_empty_bucket_and_percentiles_and_ratios_have_no_point() -> None:
    series, _ = run()
    november = {
        s.metric: s.points.get(wambatic.stats.base.Bucket(datetime.date(2026, 11, 1), '2026-11'))
        for s in series
    }
    assert november['workflow_runs'] == 0
    assert november['release_count'] == 0
    assert november['deployments'] == 0
    for metric in (
        'workflow_success_rate',
        'workflow_duration_p50',
        'release_interval_p50',
        'lead_time_p50',
        'change_failure_rate',
        'time_to_restore_p50',
    ):
        assert november[metric] is None, metric


def test_a_bucket_with_only_cancelled_runs_has_no_success_rate() -> None:
    cancelled = a_run('2026-10-05T10:00', 'cancelled')
    series, _ = run([cancelled], [], [])
    assert pick(series, 'workflow_runs')['2026-10'] == 1
    assert pick(series, 'workflow_success_rate') == {}


def test_every_conclusion_is_sorted_into_an_outcome_or_left_out() -> None:
    conclusions = {
        'success': True,
        'failure': True,
        'timed_out': True,
        'startup_failure': True,
        'cancelled': None,
        'skipped': None,
        'neutral': None,
        'action_required': None,
        'stale': None,
    }
    for conclusion, counts in conclusions.items():
        series, _ = run([a_run('2026-10-05T10:00', conclusion)], [], [])
        rate = pick(series, 'workflow_success_rate')
        if counts is None:
            assert rate == {}, conclusion
        else:
            assert rate == {'2026-10': 1.0 if conclusion == 'success' else 0.0}, conclusion


def test_a_run_without_a_start_is_left_out_of_durations_and_an_unfinished_one_too() -> None:
    unstarted = a_run('2026-10-05T10:00', 'failure', 7, started=False)
    running = a_run('2026-10-05T11:00', None, 9, status='in_progress')
    timed = a_run('2026-10-05T12:00', 'success', 4)
    series, _ = run([unstarted, running, timed], [], [])
    assert pick(series, 'workflow_duration_p50') == {'2026-10': 4.0}
    assert pick(series, 'workflow_runs') == {
        '2026-10': 3,
        '2026-11': 0,
        '2026-12': 0,
        '2027-01': 0,
    }
    assert pick(series, 'workflow_success_rate') == {'2026-10': 0.5}


def test_a_release_before_since_gives_an_interval_but_no_count() -> None:
    releases = [
        fixture.release(fixture.ALPHA, 'v1', '2026-09-20T10:00'),
        fixture.release(fixture.ALPHA, 'v2', '2026-10-06T12:00'),
    ]
    series, _ = run([], releases, [])
    assert pick(series, 'release_count')['2026-10'] == 1
    assert pick(series, 'release_interval_p50') == {'2026-10': 16}


def test_a_repos_first_release_has_no_interval_and_repos_do_not_mix() -> None:
    releases = [
        fixture.release(fixture.ALPHA, 'v1', '2026-10-01T10:00'),
        fixture.release(fixture.BETA, 'b1', '2026-10-05T10:00'),
    ]
    series, _ = run([], releases, [])
    assert pick(series, 'release_interval_p50') == {}


def test_a_prerelease_counts_as_a_release_and_in_the_interval() -> None:
    releases = [
        fixture.release(fixture.ALPHA, 'v1', '2026-10-01T10:00'),
        fixture.release(fixture.ALPHA, 'v2-rc', '2026-10-04T10:00', prerelease=True),
    ]
    series, _ = run([], releases, [])
    assert pick(series, 'release_count')['2026-10'] == 2
    assert pick(series, 'release_interval_p50') == {'2026-10': 3}


def test_release_interval_is_always_a_whole_number_of_days() -> None:
    series, _ = run()
    for value in pick(series, 'release_interval_p50').values():
        assert isinstance(value, int)


def test_total_gives_one_bucket() -> None:
    series, _ = run(granularity=Granularity.TOTAL)
    assert pick(series, 'workflow_runs') == {'total': 13}  # 7 + 0 + 1 + 5
    assert pick(series, 'release_count') == {'total': 6}  # 4 + 0 + 1 + 1
    assert pick(series, 'workflow_success_rate') == {
        'total': pytest.approx(6 / 9)
    }  # 4 + 2 of 5 + 4


def test_has_event_in_range_looks_at_run_creation_and_release_publication_dates() -> None:
    has = wambatic.stats.delivery.has_event_in_range
    run_2026 = a_run('2026-10-05T10:00', 'success')
    release_2026 = fixture.release(fixture.ALPHA, 'v1', '2026-10-06T12:00')
    nov = (datetime.date(2026, 11, 1), datetime.date(2026, 11, 30))
    assert has([run_2026], [], UTC, fixture.SINCE, fixture.UNTIL)
    assert has([], [release_2026], UTC, fixture.SINCE, fixture.UNTIL)
    assert not has([run_2026], [release_2026], UTC, *nov)
    assert not has([], [], UTC, fixture.SINCE, fixture.UNTIL)
    late = a_run('2026-12-31T23:30', 'success')
    jan = (datetime.date(2027, 1, 1), datetime.date(2027, 1, 31))
    assert not has([late], [], UTC, *jan)
    assert has([late], [], BERLIN, *jan)


# Properties

TIMES = st.datetimes(
    min_value=datetime.datetime(2026, 1, 1), max_value=datetime.datetime(2026, 12, 31, 12, 0)
)
YEAR = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
CONCLUSIONS = st.sampled_from(
    [None, 'success', 'failure', 'cancelled', 'skipped', 'timed_out', 'startup_failure', 'neutral']
)


@st.composite
def run_lists(draw: st.DrawFn) -> list[wambatic.fetch.base.WorkflowRun]:
    runs = []
    for number in range(draw(st.integers(0, 25))):
        created = draw(TIMES).replace(tzinfo=UTC)
        conclusion = draw(CONCLUSIONS)
        runs.append(
            dataclasses.replace(
                fixture.run(
                    fixture.ALPHA,
                    number,
                    created.isoformat(),
                    conclusion,
                    draw(st.integers(0, 90)),
                    status='completed'
                    if conclusion
                    else draw(st.sampled_from(['queued', 'in_progress'])),
                    started=draw(st.booleans()),
                ),
                created_at=created,
            )
        )
    return runs


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(run_lists(), st.sampled_from(list(Granularity)))
def test_workflow_runs_summed_over_the_buckets_equal_the_runs_in_range(
    runs: list[wambatic.fetch.base.WorkflowRun], granularity: Granularity
) -> None:
    series, _ = run(runs, [], [], granularity, since=YEAR[0], until=YEAR[1])
    total = sum(pick(series, 'workflow_runs').values())
    assert total == sum(1 for r in runs if YEAR[0] <= r.created_at.date() <= YEAR[1])


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(run_lists(), st.sampled_from(list(Granularity)))
def test_every_success_rate_is_between_zero_and_one_and_durations_stay_ordered(
    runs: list[wambatic.fetch.base.WorkflowRun], granularity: Granularity
) -> None:
    series, _ = run(runs, [], [], granularity, since=YEAR[0], until=YEAR[1])
    assert all(0 <= rate <= 1 for rate in pick(series, 'workflow_success_rate').values())
    p50, p90 = pick(series, 'workflow_duration_p50'), pick(series, 'workflow_duration_p90')
    assert p50.keys() == p90.keys()
    assert all(p50[label] <= p90[label] for label in p50)


# DORA proxies


def test_the_release_deployments_match_the_hand_written_values_in_utc_and_berlin() -> None:
    series, _ = run()
    check(series, fixture.ORG_DORA_RELEASES_BY_MONTH_UTC, PROXIES)
    berlin, _ = run(tz=BERLIN)
    check(berlin, fixture.ORG_DORA_RELEASES_BY_MONTH_BERLIN, PROXIES)


@pytest.mark.parametrize('settings', [DEPLOY_YML, DEPLOY_NAME], ids=['file name', 'name'])
def test_the_workflow_deployments_match_the_hand_written_values_by_file_name_or_name(
    settings: wambatic.settings.StatsSettings,
) -> None:
    series, _ = run(settings=settings)
    check(series, fixture.ORG_DORA_WORKFLOW_BY_MONTH_UTC, PROXIES)


def test_a_workflow_path_with_a_ref_or_a_directory_prefix_still_matches_its_file_name() -> None:
    deployed = [
        dataclasses.replace(r, workflow_path='octo-org/alpha/.github/workflows/deploy.yml@main')
        if r.id == 105
        else r
        for r in ORG_RUNS
    ]
    series, _ = run(deployed, settings=DEPLOY_YML)
    assert pick(series, 'deployments')['2026-10'] == 1


def test_only_a_successful_completed_run_of_the_workflow_is_a_deployment() -> None:
    failed = a_run('2026-10-05T10:00', 'failure', workflow='deploy')
    running = a_run('2026-10-06T10:00', None, status='in_progress', workflow='deploy')
    other = a_run('2026-10-07T10:00', 'success')
    series, rows = run([failed, running, other], [], [], settings=DEPLOY_YML)
    assert 'deployments' not in {s.metric for s in series}
    assert rows[0]['reason'] == 'no successful run of the workflow named by stats.deploy_workflow'


def test_a_prerelease_is_not_a_deployment() -> None:
    releases = [fixture.release(fixture.ALPHA, 'rc', '2026-10-06T12:00', prerelease=True)]
    series, rows = run([], releases, [])
    assert 'deployments' not in {s.metric for s in series}
    assert rows[0] == {
        'metric': 'deployments',
        'reason': 'no releases in the cache and stats.deploy_workflow is not set',
    }


def test_a_pull_request_merged_after_the_last_deployment_has_no_lead_time() -> None:
    releases = [fixture.release(fixture.ALPHA, 'v1', '2026-10-06T12:00')]
    late = fixture.pull(fixture.ALPHA, 1, 'octocat', '2026-10-07T09:00', merged='2026-10-08T09:00')
    series, _ = run([], releases, [late])
    assert pick(series, 'lead_time_p50') == {}
    assert pick(series, 'deployments')['2026-10'] == 1


def test_lead_time_uses_the_first_commit_and_falls_back_to_creation() -> None:
    releases = [fixture.release(fixture.ALPHA, 'v1', '2026-10-06T12:00')]
    with_commit = fixture.pull(
        fixture.ALPHA,
        1,
        'octocat',
        '2026-10-05T10:00',
        merged='2026-10-06T10:00',
        first_commit='2026-10-04T10:00',
    )
    without = fixture.pull(
        fixture.ALPHA, 2, 'octocat', '2026-10-05T12:00', merged='2026-10-06T10:00'
    )
    assert pick(run([], releases, [with_commit])[0], 'lead_time_p50') == {'2026-10': 50.0}
    assert pick(run([], releases, [without])[0], 'lead_time_p50') == {'2026-10': 24.0}


def test_a_deployment_is_matched_with_pull_requests_of_its_own_repo_only() -> None:
    releases = [fixture.release(fixture.BETA, 'b1', '2026-10-06T12:00')]
    other = fixture.pull(fixture.ALPHA, 1, 'octocat', '2026-10-05T10:00', merged='2026-10-06T10:00')
    series, _ = run([], releases, [other])
    assert pick(series, 'lead_time_p50') == {}


def hotfix_pulls(
    opened: str, merged: str | None = None, repo: str = fixture.ALPHA, label: str = 'HOTFIX'
) -> wambatic.fetch.base.PullRequest:
    return fixture.pull(repo, 99, 'octocat', opened, merged=merged, labels=(label,))


def test_a_hotfix_inside_the_window_fails_the_deployment_and_one_outside_does_not() -> None:
    releases = [fixture.release(fixture.ALPHA, 'v1', '2026-10-06T12:00')]
    inside = hotfix_pulls('2026-10-13T12:00')  # exactly 7 days later: still inside
    outside = hotfix_pulls('2026-10-13T12:01')
    before = hotfix_pulls('2026-10-06T11:00')
    assert pick(run([], releases, [inside])[0], 'change_failure_rate') == {'2026-10': 1.0}
    assert pick(run([], releases, [outside])[0], 'change_failure_rate') == {'2026-10': 0.0}
    assert pick(run([], releases, [before])[0], 'change_failure_rate') == {'2026-10': 0.0}


def test_a_hotfix_of_another_repo_does_not_fail_a_deployment() -> None:
    releases = [fixture.release(fixture.ALPHA, 'v1', '2026-10-06T12:00')]
    series, _ = run([], releases, [hotfix_pulls('2026-10-07T12:00', repo=fixture.BETA)])
    assert pick(series, 'change_failure_rate') == {'2026-10': 0.0}


def test_hotfix_labels_are_compared_whatever_their_case_in_the_pull_request_or_the_setting() -> (
    None
):
    releases = [fixture.release(fixture.ALPHA, 'v1', '2026-10-06T12:00')]
    shouting = dataclasses.replace(SETTINGS, hotfix_labels=('HotFix', 'urgent'))
    pull = hotfix_pulls('2026-10-07T12:00', label='URGENT')
    series, _ = run([], releases, [pull], settings=shouting)
    assert pick(series, 'change_failure_rate') == {'2026-10': 1.0}


def test_a_deployment_whose_window_reaches_past_until_counts_as_not_failed() -> None:
    releases = [fixture.release(fixture.ALPHA, 'v1', '2026-10-06T12:00')]
    pull = hotfix_pulls('2026-10-07T12:00')
    until_open = datetime.date(
        2026, 10, 12
    )  # the day ends 10-13T00:00: the window ends 10-13T12:00
    until_closed = datetime.date(2026, 10, 13)
    open_window, _ = run([], releases, [pull], until=until_open)
    closed_window, _ = run([], releases, [pull], until=until_closed)
    assert pick(open_window, 'change_failure_rate') == {'2026-10': 0.0}
    assert pick(closed_window, 'change_failure_rate') == {'2026-10': 1.0}


def test_the_failure_window_setting_moves_the_window() -> None:
    releases = [fixture.release(fixture.ALPHA, 'v1', '2026-10-06T12:00')]
    pull = hotfix_pulls('2026-10-20T12:00')
    short, _ = run([], releases, [pull])
    wide_settings = dataclasses.replace(SETTINGS, failure_window=datetime.timedelta(days=30))
    wide, _ = run([], releases, [pull], settings=wide_settings)
    assert pick(short, 'change_failure_rate') == {'2026-10': 0.0}
    assert pick(wide, 'change_failure_rate') == {'2026-10': 1.0}


def test_time_to_restore_is_open_to_merge_by_merge_date_and_skips_an_unmerged_hotfix() -> None:
    merged = hotfix_pulls('2026-10-07T12:00', '2026-10-09T12:00')
    unmerged = hotfix_pulls('2026-10-08T12:00')
    series, rows = run([], [], [merged, unmerged])
    assert pick(series, 'time_to_restore_p50') == {'2026-10': 48.0}
    assert pick(series, 'time_to_restore_p90') == {'2026-10': 48.0}
    assert [row['metric'] for row in rows] == [
        'deployments',
        'lead_time_p50',
        'lead_time_p90',
        'change_failure_rate',
    ]


def test_with_no_hotfix_only_deployments_and_the_lead_time_are_emitted() -> None:
    series, rows = run(pulls=[p for p in ORG_PULLS if not p.labels])
    names = [s.metric for s in series]
    assert names == [*ACTIONS_AND_RELEASES, 'deployments', 'lead_time_p50', 'lead_time_p90']
    assert rows == [
        {
            'metric': 'change_failure_rate',
            'reason': 'no pull request in the cache has a label in stats.hotfix_labels',
        },
        {
            'metric': 'time_to_restore_p50',
            'reason': 'no pull request in the cache has a label in stats.hotfix_labels',
        },
        {
            'metric': 'time_to_restore_p90',
            'reason': 'no pull request in the cache has a label in stats.hotfix_labels',
        },
    ]


def test_the_user_fixture_has_no_hotfix_rows_matching_the_hand_written_ones() -> None:
    gamma_runs = [r for r in fixture.WORKFLOW_RUNS if r.repo == fixture.GAMMA]
    gamma_releases = [r for r in fixture.RELEASES if r.repo == fixture.GAMMA]
    gamma_pulls = [p for p in fixture.PULL_REQUESTS if p.repo == fixture.GAMMA]
    series, rows = run(gamma_runs, gamma_releases, gamma_pulls, Granularity.TOTAL)
    for metric, expected in fixture.USER_DELIVERY_TOTAL_UTC.items():
        assert pick(series, metric) == pytest.approx({'total': expected}), metric
    assert pick(series, 'release_interval_p50') == {}
    assert rows == fixture.UNAVAILABLE_NO_HOTFIX


def test_with_no_releases_and_no_deploy_workflow_no_proxy_is_emitted_and_the_reasons_say_why() -> (
    None
):
    series, rows = run(ORG_RUNS, [], [])
    assert [s.metric for s in series] == ACTIONS_AND_RELEASES
    no_deployments = 'no releases in the cache and stats.deploy_workflow is not set'
    no_hotfix = 'no pull request in the cache has a label in stats.hotfix_labels'
    assert rows == [
        {'metric': 'deployments', 'reason': no_deployments},
        {'metric': 'lead_time_p50', 'reason': no_deployments},
        {'metric': 'lead_time_p90', 'reason': no_deployments},
        {'metric': 'change_failure_rate', 'reason': f'{no_deployments}; {no_hotfix}'},
        {'metric': 'time_to_restore_p50', 'reason': no_hotfix},
        {'metric': 'time_to_restore_p90', 'reason': no_hotfix},
    ]


def test_series_order_matches_the_spec_with_any_subset_of_proxies() -> None:
    order = [name for name, _ in wambatic.stats.delivery.DELIVERY_METRICS]
    for deploy in (None, 'deploy.yml'):
        for pulls in (ORG_PULLS, [p for p in ORG_PULLS if not p.labels], []):
            for releases in (ORG_RELEASES, []):
                settings = dataclasses.replace(SETTINGS, deploy_workflow=deploy)
                series, rows = run(ORG_RUNS, releases, pulls, settings=settings)
                names = [s.metric for s in series]
                assert names == [name for name in order if name in names]
                assert set(names).isdisjoint(row['metric'] for row in rows)
                assert set(names) | {row['metric'] for row in rows} == set(order)


def test_no_proxy_is_ever_sent_as_an_empty_series_of_zeros_for_lack_of_input() -> None:
    series, _ = run(ORG_RUNS, [], [])
    assert not {s.metric for s in series} & set(PROXIES)
