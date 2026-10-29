import re

import wambatic.fetch.queries

CONNECTION = re.compile(r'\b(?:history|repositories)\(([^)]*)\)')


def all_queries() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(wambatic.fetch.queries).items()
        if name.isupper() and isinstance(value, str)
    }


def test_every_query_selects_rate_limit() -> None:
    queries = all_queries()
    assert queries
    for name, text in queries.items():
        assert 'rateLimit { cost remaining resetAt }' in text, name


def test_every_connection_asks_for_a_hundred_nodes() -> None:
    found = 0
    for name, text in all_queries().items():
        for arguments in CONNECTION.findall(text):
            found += 1
            assert 'first: 100' in arguments, name
    assert found


def test_owner_repositories_are_ordered_by_latest_push() -> None:
    assert 'orderBy: {field: PUSHED_AT, direction: DESC}' in (
        wambatic.fetch.queries.OWNER_REPOSITORIES
    )


def test_commit_nodes_takes_ids() -> None:
    assert 'nodes(ids: $ids)' in wambatic.fetch.queries.COMMIT_NODES
