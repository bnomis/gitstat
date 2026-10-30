import asyncio
import collections.abc
import datetime

import tests.fixtures.stats as fixture
import wambatic.fetch.base
import wambatic.fetch.cache


def test_every_net_is_added_minus_deleted() -> None:
    for months in (fixture.ORG_BY_MONTH_UTC, fixture.ORG_BY_MONTH_BERLIN):
        for values in months.values():
            assert values['lines_net'] == values['lines_added'] - values['lines_deleted']
    for totals in (fixture.ORG_TOTAL_UTC, fixture.ORG_TOTAL_BERLIN):
        assert totals['lines_net'] == totals['lines_added'] - totals['lines_deleted']
    for breakdown in (fixture.ORG_BY_REPO_UTC, fixture.ORG_BY_AUTHOR_UTC):
        for rows in breakdown.values():
            for _, added, deleted, net in rows.values():
                assert net == added - deleted
    for top in fixture.ORG_TOP_CONTRIBUTORS:
        assert top['lines_net'] == top['lines_added'] - top['lines_deleted']


def test_the_months_sum_to_the_totals() -> None:
    for months, total in (
        (fixture.ORG_BY_MONTH_UTC, fixture.ORG_TOTAL_UTC),
        (fixture.ORG_BY_MONTH_BERLIN, fixture.ORG_TOTAL_BERLIN),
    ):
        assert tuple(months) == fixture.LABELS
        for metric in ('commits', 'active_days', 'lines_added', 'lines_deleted', 'lines_net'):
            assert sum(values[metric] for values in months.values()) == total[metric]


def test_the_breakdowns_sum_to_the_months() -> None:
    for breakdown in (fixture.ORG_BY_REPO_UTC, fixture.ORG_BY_AUTHOR_UTC):
        for label in fixture.LABELS:
            summed = [sum(months[label][i] for months in breakdown.values()) for i in range(4)]
            month = fixture.ORG_BY_MONTH_UTC[label]
            assert summed == [
                month['commits'],
                month['lines_added'],
                month['lines_deleted'],
                month['lines_net'],
            ]


def test_the_top_contributors_sum_to_the_totals_less_the_bot() -> None:
    rows = fixture.ORG_TOP_CONTRIBUTORS
    assert sum(row['commits'] for row in rows) == fixture.ORG_TOTAL_UTC['commits'] - 1
    assert sum(row['lines_added'] for row in rows) == fixture.ORG_TOTAL_UTC['lines_added'] - 30
    assert sum(row['lines_deleted'] for row in rows) == fixture.ORG_TOTAL_UTC['lines_deleted'] - 30


def test_the_fetcher_returns_every_fixture_commit(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    async def read() -> list[wambatic.fetch.base.Commit]:
        found: list[wambatic.fetch.base.Commit] = []
        for subject in (fixture.ORG, fixture.USER):
            for repo in await stats_fetcher.repos(subject):
                found.extend([c async for c in stats_fetcher.commits(repo, None, None)])
        return found

    found = asyncio.run(read())
    assert sorted(found, key=lambda c: (c.repo, c.oid)) == sorted(
        fixture.COMMITS, key=lambda c: (c.repo, c.oid)
    )


IN_RANGE_START = datetime.datetime(2026, 10, 1, tzinfo=datetime.UTC)
IN_RANGE_END = datetime.datetime(2027, 2, 1, tzinfo=datetime.UTC)
# Named records with an event outside the range, and one record that is wholly outside it
ALPHA_P9 = ('octo-org/alpha', 9)
PULLS_BEFORE_RANGE = {('octo-org/alpha', 5)}  # created in September
ISSUES_BEFORE_RANGE = {('octo-org/beta', 2)}  # created in September
AFTER_RANGE = {('octo-org/beta', 3)}  # merged on 2027-02-01


def in_range(moment: datetime.datetime | None) -> bool:
    return moment is not None and IN_RANGE_START <= moment < IN_RANGE_END


def test_every_flow_record_is_inside_the_range_or_deliberately_outside_it() -> None:
    for pull in fixture.PULL_REQUESTS:
        key = (pull.repo, pull.number)
        events = [pull.created_at, pull.first_review_at, pull.merged_at, pull.closed_at]
        inside = [in_range(moment) for moment in events if moment is not None]
        if key == ALPHA_P9:
            assert not any(inside)
        elif key in PULLS_BEFORE_RANGE:
            assert not in_range(pull.created_at)
            assert any(inside)
        elif key in AFTER_RANGE:
            assert in_range(pull.created_at)
            assert not in_range(pull.merged_at)
        else:
            assert all(inside), key
    for item in fixture.ISSUES:
        key = (item.repo, item.number)
        if key in ISSUES_BEFORE_RANGE:
            assert not in_range(item.created_at)
            assert in_range(item.closed_at)
        else:
            assert in_range(item.created_at), key
            assert item.closed_at is None or in_range(item.closed_at), key


def test_every_record_was_updated_at_or_after_each_of_its_events() -> None:
    for pull in fixture.PULL_REQUESTS:
        events = [pull.created_at, pull.first_review_at, pull.merged_at, pull.closed_at]
        assert all(moment <= pull.updated_at for moment in events if moment is not None)
    for item in fixture.ISSUES:
        assert max(item.created_at, item.closed_at or item.created_at) <= item.updated_at


def count_in_month(moments: collections.abc.Sequence[datetime.datetime | None], label: str) -> int:
    return sum(1 for m in moments if m is not None and m.strftime('%Y-%m') == label)


def test_the_expected_counts_equal_a_direct_count_over_the_org_records() -> None:
    pulls = [p for p in fixture.PULL_REQUESTS if p.repo != fixture.GAMMA]
    issues = [i for i in fixture.ISSUES if i.repo != fixture.GAMMA]
    expected = fixture.ORG_FLOW_BY_MONTH_UTC
    for label in fixture.LABELS:
        assert count_in_month([p.created_at for p in pulls], label) == expected['prs_opened'][label]
        assert count_in_month([p.merged_at for p in pulls], label) == expected['prs_merged'][label]
        assert (
            count_in_month([i.created_at for i in issues], label)
            == expected['issues_opened'][label]
        )
        assert (
            count_in_month([i.closed_at for i in issues], label) == expected['issues_closed'][label]
        )


def test_the_duration_expectations_are_absent_exactly_where_there_is_no_event() -> None:
    pulls = [p for p in fixture.PULL_REQUESTS if p.repo != fixture.GAMMA]
    issues = [i for i in fixture.ISSUES if i.repo != fixture.GAMMA]
    expected = fixture.ORG_FLOW_BY_MONTH_UTC
    for label in fixture.LABELS:
        reviewed = count_in_month([p.first_review_at for p in pulls], label) > 0
        merged = count_in_month([p.merged_at for p in pulls], label) > 0
        closed = count_in_month([i.closed_at for i in issues], label) > 0
        assert (label in expected['time_to_first_review_p50']) is reviewed
        assert (label in expected['time_to_first_review_p90']) is reviewed
        assert (label in expected['time_to_merge_p50']) is merged
        assert (label in expected['pr_size_p50']) is merged
        assert (label in expected['time_to_close_p90']) is closed


def test_the_p90_is_never_below_the_p50_and_the_berlin_moves_follow_the_merge() -> None:
    utc = fixture.ORG_FLOW_BY_MONTH_UTC
    for name in ('time_to_first_review', 'time_to_merge', 'time_to_close'):
        for label, p50 in utc[f'{name}_p50'].items():
            assert utc[f'{name}_p90'][label] >= p50
    assert sum(fixture.ORG_FLOW_BY_MONTH_BERLIN['prs_merged'].values()) == sum(
        utc['prs_merged'].values()
    )
    assert set(fixture.ORG_FLOW_BY_MONTH_BERLIN) <= set(utc)


def test_the_user_expectations_count_only_the_users_own_items_in_the_users_repos() -> None:
    mine = [p for p in fixture.PULL_REQUESTS if p.repo == fixture.GAMMA]
    own = [p for p in mine if (p.author_login or '').casefold() == fixture.USER.login]
    assert len(own) == fixture.USER_FLOW_TOTAL_UTC['prs_opened']
    assert len(own) < len(mine)
    items = [i for i in fixture.ISSUES if i.repo == fixture.GAMMA]
    own_issues = [i for i in items if (i.author_login or '').casefold() == fixture.USER.login]
    assert len(own_issues) == fixture.USER_FLOW_TOTAL_UTC['issues_opened']
    assert len(own_issues) < len(items)


def test_the_fetcher_returns_every_fixture_pull_request_and_issue(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    async def read() -> tuple[list[object], list[object]]:
        pulls: list[object] = []
        issues: list[object] = []
        for subject in (fixture.ORG, fixture.USER):
            for repo in await stats_fetcher.repos(subject):
                pulls.extend([p async for p in stats_fetcher.pull_requests(repo, None)])
                issues.extend([i async for i in stats_fetcher.issues(repo, None)])
        return pulls, issues

    pulls, issues = asyncio.run(read())

    def key(record: object) -> tuple[str, int]:
        return (record.repo, record.number)  # type: ignore[attr-defined]

    assert sorted(pulls, key=key) == sorted(fixture.PULL_REQUESTS, key=key)
    assert sorted(issues, key=key) == sorted(fixture.ISSUES, key=key)


def test_each_repo_has_a_sync_state_for_every_flow_resource_at_its_sync_time(
    stats_cache: wambatic.fetch.cache.Cache,
) -> None:
    times = {
        fixture.ALPHA: fixture.ALPHA_SYNCED_AT,
        fixture.BETA: fixture.BETA_SYNCED_AT,
        fixture.GAMMA: fixture.GAMMA_SYNCED_AT,
    }
    for name, synced_at in times.items():
        for resource in ('commits', 'issues', 'pull_requests'):
            state = stats_cache.sync_state(name, resource)
            assert state is not None
            assert state.synced_at == synced_at


# Delivery


def test_every_delivery_record_belongs_to_a_fixture_repo() -> None:
    names = {repo.name_with_owner for repo in fixture.REPOS}
    assert {release.repo for release in fixture.RELEASES} <= names
    assert {run.repo for run in fixture.WORKFLOW_RUNS} <= names


def test_a_release_is_published_at_or_after_it_was_created() -> None:
    for release in fixture.RELEASES:
        assert release.published_at >= release.created_at


def test_every_completed_run_has_a_conclusion_and_no_other_run_has() -> None:
    for run in fixture.WORKFLOW_RUNS:
        assert (run.status == 'completed') == (run.conclusion is not None), run.id
        assert run.updated_at >= run.created_at
        assert run.run_started_at is None or run.run_started_at >= run.created_at


def test_run_ids_and_release_tags_are_unique_within_a_repo() -> None:
    assert len({(run.repo, run.id) for run in fixture.WORKFLOW_RUNS}) == len(fixture.WORKFLOW_RUNS)
    assert len({(r.repo, r.tag_name) for r in fixture.RELEASES}) == len(fixture.RELEASES)


def test_the_fixtures_cover_what_each_delivery_rule_tells_apart() -> None:
    conclusions = {run.conclusion for run in fixture.WORKFLOW_RUNS}
    assert {'success', 'failure', 'timed_out', 'startup_failure', 'cancelled', 'skipped'} <= (
        conclusions
    )
    assert {'in_progress', 'queued'} <= {run.status for run in fixture.WORKFLOW_RUNS}
    assert any(run.run_started_at is None for run in fixture.WORKFLOW_RUNS)
    assert any(release.is_prerelease for release in fixture.RELEASES)
    assert any(
        release.published_at < fixture.moment('2026-10-01T00:00') for release in fixture.RELEASES
    )
    assert any(
        run.workflow_path.endswith('/deploy.yml') and run.name == 'Deploy'
        for run in fixture.WORKFLOW_RUNS
    )
    hotfix = [
        p for p in fixture.PULL_REQUESTS if 'hotfix' in {name.casefold() for name in p.labels}
    ]
    assert {'Hotfix', 'hotfix'} <= {name for p in hotfix for name in p.labels}


def test_the_utc_and_berlin_months_differ_only_where_a_record_crosses_midnight() -> None:
    assert (
        fixture.ORG_DELIVERY_BY_MONTH_UTC['workflow_runs']
        != (fixture.ORG_DELIVERY_BY_MONTH_BERLIN['workflow_runs'])
    )
    for name, by_label in fixture.ORG_DELIVERY_BY_MONTH_BERLIN.items():
        assert by_label['2026-10'] == fixture.ORG_DELIVERY_BY_MONTH_UTC[name]['2026-10']


def test_every_delivery_series_has_a_value_somewhere_and_a_percentile_or_ratio_has_a_gap() -> None:
    expected = {
        **fixture.ORG_DELIVERY_BY_MONTH_UTC,
        **fixture.ORG_DORA_RELEASES_BY_MONTH_UTC,
    }
    assert set(expected) == {
        'workflow_runs',
        'workflow_success_rate',
        'workflow_duration_p50',
        'workflow_duration_p90',
        'release_count',
        'release_interval_p50',
        'deployments',
        'lead_time_p50',
        'lead_time_p90',
        'change_failure_rate',
        'time_to_restore_p50',
        'time_to_restore_p90',
    }
    for name, by_label in expected.items():
        assert by_label, name
        if name not in ('workflow_runs', 'release_count', 'deployments'):
            assert len(by_label) < len(fixture.LABELS), name


def test_the_month_counts_equal_a_direct_count_over_the_org_records() -> None:
    org = {fixture.ALPHA, fixture.BETA}
    runs = [run.created_at for run in fixture.WORKFLOW_RUNS if run.repo in org]
    published = [release.published_at for release in fixture.RELEASES if release.repo in org]
    deployed = [r.published_at for r in fixture.RELEASES if r.repo in org and not r.is_prerelease]
    for label in fixture.LABELS:
        expected = fixture.ORG_DELIVERY_BY_MONTH_UTC
        assert count_in_month(runs, label) == expected['workflow_runs'][label]
        assert count_in_month(published, label) == expected['release_count'][label]
        dora = fixture.ORG_DORA_RELEASES_BY_MONTH_UTC
        assert count_in_month(deployed, label) == dora['deployments'][label]


def test_a_gamma_release_and_runs_are_the_users_whole_delivery() -> None:
    assert [r.tag_name for r in fixture.RELEASES if r.repo == fixture.GAMMA] == ['g1.0']
    assert [run.id for run in fixture.WORKFLOW_RUNS if run.repo == fixture.GAMMA] == [301, 302]
    assert not any(p.labels for p in fixture.PULL_REQUESTS if p.repo == fixture.GAMMA)
