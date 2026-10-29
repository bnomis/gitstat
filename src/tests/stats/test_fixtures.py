import asyncio

import tests.fixtures.stats as fixture
import wambatic.fetch.base


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
