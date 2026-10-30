import asyncio
import datetime
import typing
import zoneinfo

import hypothesis
import hypothesis.strategies as st
import pytest

import tests.fixtures.stats as fixture
import wambatic.fetch.base
import wambatic.stats
import wambatic.stats.base
import wambatic.stats.errors
import wambatic.stats.flow

Granularity = wambatic.stats.base.Granularity
Request = wambatic.stats.base.StatsRequest
UTC = datetime.UTC
BERLIN = zoneinfo.ZoneInfo('Europe/Berlin')
ALPHA_SUBJECT = wambatic.fetch.base.Subject('repo', 'octo-org', 'alpha')
ACTIVITY = frozenset({'activity'})
FLOW = frozenset({'flow'})
TOTALS = ('commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net')
BREAKDOWN = ('commits', 'lines_added', 'lines_deleted', 'lines_net')


def clock() -> datetime.datetime:
    return fixture.NOW


def request(**changes: object) -> Request:
    fields: dict[str, object] = {
        'since': fixture.SINCE,
        'until': fixture.UNTIL,
        'groups': ACTIVITY,
    }
    fields.update(changes)
    return Request(**fields)  # type: ignore[arg-type]


def compute(
    fetcher: wambatic.fetch.base.Fetcher,
    subject: wambatic.fetch.base.Subject = fixture.ORG,
    **changes: object,
) -> wambatic.stats.base.StatsResult:
    return asyncio.run(wambatic.stats.compute(subject, fetcher, request(**changes), clock=clock))


def pick(
    result: wambatic.stats.base.StatsResult,
    metric: str,
    by: str | None = None,
    by_kind: str | None = None,
) -> dict[str, float]:
    (found,) = [s for s in result.series if (s.metric, s.by, s.by_kind) == (metric, by, by_kind)]
    return {bucket.label: value for bucket, value in found.points.items()}


class Untouchable:
    """A fetcher that fails on any use, for errors that come before the cache is read."""

    def __getattr__(self, name: str) -> typing.NoReturn:
        raise AssertionError(f'the fetcher was used: {name}')


def untouched(subject: wambatic.fetch.base.Subject = fixture.ORG, **changes: object) -> None:
    fetcher = typing.cast(wambatic.fetch.base.Fetcher, Untouchable())
    asyncio.run(wambatic.stats.compute(subject, fetcher, request(**changes), clock=clock))


# resources_for


def test_resources_for_maps_each_group() -> None:
    resources_for = wambatic.stats.resources_for
    assert resources_for(frozenset({'activity'})) == {'commits'}
    assert resources_for(frozenset({'flow'})) == {'issues', 'pull_requests'}
    assert resources_for(frozenset({'delivery'})) == {'releases', 'star_events', 'workflow_runs'}
    assert resources_for(frozenset({'activity', 'flow'})) == {
        'commits',
        'issues',
        'pull_requests',
    }
    assert resources_for(frozenset()) == frozenset()


def test_resources_for_names_each_unknown_group_sorted() -> None:
    with pytest.raises(wambatic.stats.errors.UnknownGroupError, match='alpha, zeta') as raised:
        wambatic.stats.resources_for(frozenset({'zeta', 'activity', 'alpha'}))
    assert 'activity' not in str(raised.value)


# Results


def test_an_org_by_month_matches_the_hand_written_values_with_repo_series_only(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = compute(stats_fetcher)
    for metric in TOTALS:
        assert pick(result, metric) == {
            label: values[metric] for label, values in fixture.ORG_BY_MONTH_UTC.items()
        }
    for name, months in fixture.ORG_BY_REPO_UTC.items():
        for position, metric in enumerate(BREAKDOWN):
            assert pick(result, metric, name, 'repo') == {
                label: values[position] for label, values in months.items()
            }
    assert not [s for s in result.series if s.by_kind == 'author']
    assert result.tables['top_contributors'] == fixture.ORG_TOP_CONTRIBUTORS
    assert (result.since, result.until) == (fixture.SINCE, fixture.UNTIL)
    assert result.subject == fixture.ORG


def test_by_author_adds_the_author_series(stats_fetcher: wambatic.fetch.base.Fetcher) -> None:
    result = compute(stats_fetcher, by_author=True)
    for login, months in fixture.ORG_BY_AUTHOR_UTC.items():
        for position, metric in enumerate(BREAKDOWN):
            assert pick(result, metric, login, 'author') == {
                label: values[position] for label, values in months.items()
            }


def test_the_org_in_berlin_matches_the_hand_written_values(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = compute(stats_fetcher, tz=BERLIN)
    for metric in TOTALS:
        assert pick(result, metric) == {
            label: values[metric] for label, values in fixture.ORG_BY_MONTH_BERLIN.items()
        }
    total = compute(stats_fetcher, tz=BERLIN, granularity=Granularity.TOTAL)
    for metric in TOTALS:
        assert pick(total, metric) == {'total': fixture.ORG_TOTAL_BERLIN[metric]}


def test_a_repo_subject_has_no_per_repo_series(stats_fetcher: wambatic.fetch.base.Fetcher) -> None:
    result = compute(stats_fetcher, ALPHA_SUBJECT)
    assert not [s for s in result.series if s.by_kind == 'repo']
    assert pick(result, 'commits') == {'2026-10': 4, '2026-11': 0, '2026-12': 1, '2027-01': 1}
    by_author = compute(stats_fetcher, ALPHA_SUBJECT, by_author=True)
    assert {s.by for s in by_author.series if s.by_kind == 'author'} == {
        'Octocat',
        'hubot',
        'monalisa',
    }


def test_a_user_subject_counts_only_the_users_own_commits_in_the_users_repos(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = compute(stats_fetcher, fixture.USER)
    assert pick(result, 'commits')['2026-10'] == 1  # g1, not monalisa's g2
    assert pick(result, 'lines_added')['2026-10'] == 5
    assert pick(result, 'lines_deleted')['2026-10'] == 1
    repo_series = {s.by for s in result.series if s.by_kind == 'repo'}
    assert repo_series == {fixture.GAMMA}
    assert [row['login'] for row in result.tables['top_contributors']] == ['Octocat']


def test_a_user_is_matched_case_insensitively(stats_fetcher: wambatic.fetch.base.Fetcher) -> None:
    result = compute(stats_fetcher, wambatic.fetch.base.Subject('user', 'OCTOCAT'))
    assert pick(result, 'commits')['2026-10'] == 1


def test_since_and_until_cut_at_local_dates_inclusively(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    after = compute(stats_fetcher, tz=BERLIN, since=datetime.date(2027, 1, 1))
    assert pick(after, 'commits') == {'2027-01': 3}  # a5 at 00:30 on the 1st in Berlin
    before = compute(stats_fetcher, tz=BERLIN, until=datetime.date(2026, 12, 31))
    assert sum(pick(before, 'commits').values()) == 7  # a5 is out
    in_utc = compute(stats_fetcher, until=datetime.date(2026, 12, 31))
    assert sum(pick(in_utc, 'commits').values()) == 8  # a5 is in
    one_day = compute(
        stats_fetcher, since=datetime.date(2026, 10, 5), until=datetime.date(2026, 10, 5)
    )
    assert sum(pick(one_day, 'commits').values()) == 2  # a1 and a2 on the last day counted


def test_an_open_end_uses_the_clock_and_flags_the_last_bucket_partial(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = compute(stats_fetcher, since=None, until=None)
    assert (result.since, result.until) == (datetime.date(2026, 10, 1), datetime.date(2027, 1, 20))
    assert list(pick(result, 'commits')) == list(fixture.LABELS)
    assert result.provenance['partial_buckets'] == '2027-01'


def test_an_open_start_begins_at_the_earliest_commits_bucket(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    month = compute(stats_fetcher, since=None)
    assert month.since == datetime.date(2026, 10, 1)
    week = compute(stats_fetcher, since=None, granularity=Granularity.WEEK)
    assert week.since == datetime.date(2026, 10, 5)  # a1 is in the week of Monday 5 October
    total = compute(stats_fetcher, since=None, granularity=Granularity.TOTAL)
    assert total.since == datetime.date(2026, 10, 5)
    assert list(pick(total, 'commits')) == ['total']


def test_a_commit_after_today_is_left_out_when_the_end_is_open(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    early_clock = datetime.datetime(2027, 1, 10, 12, 0, tzinfo=UTC)
    result = asyncio.run(
        wambatic.stats.compute(
            fixture.ORG, stats_fetcher, request(until=None), clock=lambda: early_clock
        )
    )
    assert result.until == datetime.date(2027, 1, 10)
    assert pick(result, 'commits')['2027-01'] == 1  # a6; b4 on the 15th is in the future


def test_the_default_request_returns_flow_beside_activity_with_no_flow_row_unavailable(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = asyncio.run(wambatic.stats.compute(fixture.ORG, stats_fetcher, Request(), clock=clock))
    assert pick(result, 'commits')
    assert pick(result, 'prs_opened')
    rows = {row['metric']: row['reason'] for row in result.tables['unavailable']}
    assert 'flow' not in rows
    assert {'stars', 'forks', 'watchers', 'languages'} <= rows.keys()
    assert 'step 8' in rows['stars']
    assert 'delivery' not in rows


def test_every_requested_group_is_in_the_series_or_unavailable(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = compute(stats_fetcher, groups=frozenset({'activity', 'flow', 'delivery'}))
    rows = {row['metric'] for row in result.tables['unavailable']}
    assert 'delivery' in rows
    assert 'flow' not in rows
    assert pick(result, 'commits')
    assert pick(result, 'prs_opened')


def flow_only(
    fetcher: wambatic.fetch.base.Fetcher,
    subject: wambatic.fetch.base.Subject = fixture.ORG,
    **changes: object,
) -> wambatic.stats.base.StatsResult:
    return compute(fetcher, subject, groups=FLOW, **changes)


def test_the_org_flow_series_equal_the_hand_written_values_in_utc(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = compute(stats_fetcher, groups=frozenset({'activity', 'flow'}))
    for metric, expected in fixture.ORG_FLOW_BY_MONTH_UTC.items():
        assert pick(result, metric) == pytest.approx(expected), metric


def test_the_org_flow_series_equal_the_hand_written_values_in_berlin(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = flow_only(stats_fetcher, tz=BERLIN)
    for metric, expected in fixture.ORG_FLOW_BY_MONTH_UTC.items():
        expected = fixture.ORG_FLOW_BY_MONTH_BERLIN.get(metric, expected)
        assert pick(result, metric) == pytest.approx(expected), metric


def test_a_user_subject_counts_only_the_users_own_pull_requests_and_issues(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = flow_only(stats_fetcher, fixture.USER, granularity=Granularity.TOTAL)
    for metric, expected in fixture.USER_FLOW_TOTAL_UTC.items():
        assert pick(result, metric) == pytest.approx({'total': expected}), metric


def test_flow_alone_with_no_start_begins_at_the_earliest_pull_request_or_issue(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = flow_only(stats_fetcher, since=None, until=fixture.UNTIL)
    assert result.since == datetime.date(2026, 8, 1)  # alpha's pull request created on 08-01
    assert list(pick(result, 'prs_opened'))[:3] == ['2026-08', '2026-09', '2026-10']
    assert pick(result, 'prs_opened')['2026-08'] == 1
    assert pick(result, 'prs_merged')['2026-08'] == 1


def test_a_range_with_pull_requests_but_no_commits_gives_zero_activity_and_the_flow_values(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = compute(
        stats_fetcher,
        groups=frozenset({'activity', 'flow'}),
        since=datetime.date(2026, 11, 1),
        until=datetime.date(2026, 11, 30),
    )
    assert pick(result, 'commits') == {'2026-11': 0}
    assert pick(result, 'lines_net') == {'2026-11': 0}
    assert pick(result, 'prs_opened') == {'2026-11': 1}
    assert pick(result, 'issues_closed') == {'2026-11': 1}
    assert result.tables['top_contributors'] == []


def test_a_range_with_neither_commits_nor_flow_events_is_empty(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    with pytest.raises(wambatic.stats.errors.EmptySubjectError, match='activity or flow.*range'):
        compute(
            stats_fetcher,
            groups=frozenset({'activity', 'flow'}),
            since=datetime.date(2025, 1, 1),
            until=datetime.date(2025, 2, 1),
        )
    with pytest.raises(wambatic.stats.errors.EmptySubjectError, match='flow.*range'):
        flow_only(stats_fetcher, since=datetime.date(2025, 1, 1), until=datetime.date(2025, 2, 1))


def test_a_pull_request_updated_in_range_but_with_every_event_outside_it_is_not_a_record(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    with pytest.raises(wambatic.stats.errors.EmptySubjectError):
        flow_only(
            stats_fetcher, since=datetime.date(2026, 12, 1), until=datetime.date(2026, 12, 29)
        )


def test_the_provenance_carries_a_fetched_at_for_each_flow_resource(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = compute(stats_fetcher, groups=frozenset({'activity', 'flow'}))
    for resource in ('commits', 'issues', 'pull_requests'):
        assert result.provenance[f'fetched_at:{resource}'] == fixture.ALPHA_SYNCED_AT.isoformat()
    assert 'fetched_at:issues' not in compute(stats_fetcher).provenance


def test_the_series_come_in_the_order_activity_flow_breakdowns(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = compute(stats_fetcher, groups=frozenset({'activity', 'flow'}), by_author=True)
    names = [(s.metric, s.by_kind) for s in result.series]
    totals = [name for name, kind in names if kind is None]
    assert totals == list(TOTALS) + [name for name, _ in wambatic.stats.flow.FLOW_METRICS]
    first_breakdown = next(i for i, (_, kind) in enumerate(names) if kind is not None)
    assert first_breakdown == len(totals)
    assert names[first_breakdown][1] == 'author'


def test_a_flow_only_result_has_no_activity_series_or_tables_beyond_unavailable(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = flow_only(stats_fetcher, by_author=True)
    assert [s.metric for s in result.series] == [n for n, _ in wambatic.stats.flow.FLOW_METRICS]
    assert set(result.tables) == {'unavailable'}


def test_delivery_alone_still_raises_naming_step_8(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    with pytest.raises(wambatic.stats.errors.EmptySubjectError, match=r'delivery \(step 8\)'):
        compute(stats_fetcher, groups=frozenset({'delivery'}))


def test_the_provenance_records_the_cache_the_clock_the_zone_and_the_partial_buckets(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    result = compute(stats_fetcher, tz=BERLIN, since=datetime.date(2026, 10, 15), until=None)
    provenance = result.provenance
    assert {'schema_version', 'wambatic_version'} <= provenance.keys()
    assert provenance['fetched_at:commits'] == fixture.ALPHA_SYNCED_AT.isoformat()
    assert provenance['computed_at'] == fixture.NOW.isoformat()
    assert provenance['timezone'] == 'Europe/Berlin'
    assert provenance['partial_buckets'] == '2026-10,2027-01'
    assert 'fetched_at:issues' not in provenance
    whole = compute(stats_fetcher)
    assert whole.provenance['partial_buckets'] == ''
    assert whole.provenance['timezone'] == 'UTC'


# Errors


def test_every_error_in_the_validation_order_comes_before_the_cache_is_read() -> None:
    with pytest.raises(wambatic.stats.errors.UnknownGroupError):
        untouched(fixture.USER, groups=frozenset({'nope'}), by_author=True)
    with pytest.raises(wambatic.stats.errors.InvalidRequestError):
        untouched(fixture.USER, by_author=True, since=fixture.UNTIL, until=fixture.SINCE)
    with pytest.raises(wambatic.stats.errors.InvalidRangeError):
        untouched(since=fixture.UNTIL, until=fixture.SINCE)
    with pytest.raises(wambatic.stats.errors.EmptySubjectError, match=r'delivery \(step 8\)'):
        untouched(groups=frozenset({'delivery'}))


def test_a_subject_with_no_repositories_is_empty(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    with pytest.raises(wambatic.stats.errors.EmptySubjectError, match='repositories'):
        compute(stats_fetcher, wambatic.fetch.base.Subject('org', 'nobody'))


def test_a_range_with_no_commits_is_empty(stats_fetcher: wambatic.fetch.base.Fetcher) -> None:
    with pytest.raises(wambatic.stats.errors.EmptySubjectError, match='range'):
        compute(stats_fetcher, since=datetime.date(2025, 1, 1), until=datetime.date(2025, 2, 1))
    with pytest.raises(wambatic.stats.errors.EmptySubjectError):
        compute(
            stats_fetcher,
            tz=BERLIN,
            since=datetime.date(2026, 12, 1),
            until=datetime.date(2026, 12, 31),
        )


def test_an_open_start_after_an_open_end_is_an_invalid_range(
    stats_fetcher: wambatic.fetch.base.Fetcher,
) -> None:
    long_ago = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    with pytest.raises(wambatic.stats.errors.InvalidRangeError):
        asyncio.run(
            wambatic.stats.compute(
                fixture.ORG, stats_fetcher, request(since=None, until=None), clock=lambda: long_ago
            )
        )


# No network, no sync


def test_compute_never_syncs_and_sends_no_request(
    stats_fetcher: wambatic.fetch.base.Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def forbidden(*args: object, **kwargs: object) -> typing.NoReturn:
        raise AssertionError('sync was called')

    monkeypatch.setattr(stats_fetcher, 'sync', forbidden)
    compute(stats_fetcher, by_author=True)
    compute(stats_fetcher, fixture.USER)
    assert stats_fetcher.client.session is None


# Properties

DAYS = (fixture.SINCE, fixture.UNTIL)


@st.composite
def spans(draw: st.DrawFn) -> tuple[datetime.date, datetime.date]:
    low = draw(st.dates(min_value=fixture.SINCE, max_value=fixture.UNTIL))
    high = draw(st.dates(min_value=low, max_value=fixture.UNTIL))
    return low, high


@hypothesis.settings(
    max_examples=20,
    deadline=10000,
    suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture],
)
@hypothesis.given(spans(), st.sampled_from(list(Granularity)))
def test_the_total_lines_added_are_the_non_merge_additions_in_range(
    stats_fetcher: wambatic.fetch.base.Fetcher,
    span: tuple[datetime.date, datetime.date],
    granularity: Granularity,
) -> None:
    since, until = span
    expected = [c for c in fixture.ORG_COMMITS if since <= c.authored_at.date() <= until]
    if not expected:
        with pytest.raises(wambatic.stats.errors.EmptySubjectError):
            compute(stats_fetcher, since=since, until=until, granularity=granularity)
        return
    result = compute(stats_fetcher, since=since, until=until, granularity=granularity)
    assert sum(pick(result, 'lines_added').values()) == sum(
        c.additions for c in expected if not c.is_merge
    )
    assert sum(pick(result, 'commits').values()) == len(expected)
