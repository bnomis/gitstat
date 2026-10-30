import re

import wambatic.fetch.cache
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


def test_the_listing_queries_probe_the_newest_pull_request_and_issue() -> None:
    for text in (
        wambatic.fetch.queries.OWNER_REPOSITORIES,
        wambatic.fetch.queries.REPOSITORY,
    ):
        for connection in ('pullRequests', 'issues'):
            assert (
                f'{connection}(first: 1, orderBy: {{field: UPDATED_AT, direction: DESC}})' in text
            )


def test_the_flow_queries_page_by_update_time_newest_first() -> None:
    for text, connection in (
        (wambatic.fetch.queries.PULL_REQUESTS, 'pullRequests'),
        (wambatic.fetch.queries.ISSUES, 'issues'),
    ):
        assert (
            f'{connection}(first: 100, after: $cursor, '
            'orderBy: {field: UPDATED_AT, direction: DESC})'
        ) in text
        assert 'pageInfo { hasNextPage endCursor }' in text
        assert 'author { __typename login }' in text


def test_the_cache_identity_has_a_hash_for_each_flow_query() -> None:
    identity = wambatic.fetch.cache.expected_identity()
    assert {'query:PULL_REQUESTS', 'query:ISSUES'} <= identity.keys()


def test_the_listing_queries_probe_the_newest_created_release() -> None:
    for text in (
        wambatic.fetch.queries.OWNER_REPOSITORIES,
        wambatic.fetch.queries.REPOSITORY,
    ):
        assert 'releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC})' in text
        assert 'totalCount' in text


def test_the_releases_query_pages_by_creation_time_newest_first() -> None:
    text = wambatic.fetch.queries.RELEASES
    assert (
        'releases(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC})'
    ) in text
    assert 'pageInfo { hasNextPage endCursor }' in text
    for field in ('tagName', 'createdAt', 'publishedAt', 'isDraft', 'isPrerelease'):
        assert field in text


def test_the_pull_requests_query_selects_labels_and_the_first_commit() -> None:
    text = wambatic.fetch.queries.PULL_REQUESTS
    assert 'labels(first: 20) { nodes { name } }' in text
    assert 'commits(first: 1) { nodes { commit { authoredDate } } }' in text


def test_the_cache_identity_has_a_hash_for_the_releases_query() -> None:
    assert 'query:RELEASES' in wambatic.fetch.cache.expected_identity()
