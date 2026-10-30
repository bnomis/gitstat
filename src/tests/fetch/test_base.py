import dataclasses
import datetime

import pytest

import tests.fixtures.fetch.responses as responses
import wambatic.fetch.base
import wambatic.fetch.errors

NOW = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)


@pytest.mark.parametrize(
    'subject',
    [
        wambatic.fetch.base.Subject('user', 'octocat'),
        wambatic.fetch.base.Subject('org', 'github'),
        wambatic.fetch.base.Subject('repo', 'octocat', 'Hello-World'),
    ],
)
def test_valid_subjects_construct(subject: wambatic.fetch.base.Subject) -> None:
    assert subject.login


@pytest.mark.parametrize(
    ('kind', 'name'),
    [('repo', None), ('user', 'Hello-World'), ('org', 'Hello-World')],
)
def test_invalid_subjects_raise(kind: str, name: str | None) -> None:
    with pytest.raises(ValueError, match='subject'):
        wambatic.fetch.base.Subject(kind, 'octocat', name)  # type: ignore[arg-type]


def test_full_name_of_a_repo_subject() -> None:
    assert wambatic.fetch.base.Subject('repo', 'octocat', 'Hello-World').full_name == (
        'octocat/Hello-World'
    )


@pytest.mark.parametrize('kind', ['user', 'org'])
def test_full_name_of_an_owner_subject_raises(kind: str) -> None:
    with pytest.raises(ValueError, match='no repo name'):
        wambatic.fetch.base.Subject(kind, 'octocat').full_name  # type: ignore[arg-type]  # noqa: B018


def test_records_are_immutable() -> None:
    commit = wambatic.fetch.base.Commit('octocat/Hello-World', 'a' * 40, NOW, None, 1, 2, False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        commit.additions = 5  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        wambatic.fetch.base.Subject('user', 'octocat').login = 'x'  # type: ignore[misc]


def test_commit_records_merges() -> None:
    commit = wambatic.fetch.base.Commit('octocat/Hello-World', 'a' * 40, NOW, None, 0, 0, True)
    assert commit.is_merge


def test_resources_are_the_spec_names() -> None:
    assert wambatic.fetch.base.RESOURCES == {
        'commits',
        'issues',
        'pull_requests',
        'releases',
        'star_events',
        'workflow_runs',
    }


def test_built_resources_are_a_subset_of_all_resources() -> None:
    assert wambatic.fetch.base.BUILT_RESOURCES <= wambatic.fetch.base.RESOURCES


def pull_request() -> wambatic.fetch.base.PullRequest:
    return wambatic.fetch.base.PullRequest(
        'octocat/Hello-World', 1, 'octocat', NOW, NOW, None, None, None, 3, 4
    )


def issue() -> wambatic.fetch.base.Issue:
    return wambatic.fetch.base.Issue('octocat/Hello-World', 1, 'octocat', NOW, NOW, None)


def test_pull_request_and_issue_are_frozen_and_slotted() -> None:
    for record in (pull_request(), issue()):
        with pytest.raises(dataclasses.FrozenInstanceError):
            record.number = 2  # type: ignore[misc]
        assert not hasattr(record, '__dict__')


def test_a_repo_built_without_the_probe_fields_has_them_none() -> None:
    repo = wambatic.fetch.base.Repo('octocat/Hello-World', 'main', None, False, False, None, NOW)
    assert repo.pull_requests_updated_at is None
    assert repo.issues_updated_at is None
    assert not hasattr(repo, '__dict__')


# Parsing pull requests, issues and the listing probes

HELLO = 'octocat/Hello-World'
HOUR = datetime.timedelta(hours=1)
UTC = datetime.UTC


def parse_pull(**changes: object) -> wambatic.fetch.base.PullRequest:
    return wambatic.fetch.base.parse_pull_request(
        HELLO,
        responses.pull_request_node(1, **changes),  # type: ignore[arg-type]
    )


def parse_issue(**changes: object) -> wambatic.fetch.base.Issue:
    return wambatic.fetch.base.parse_issue(
        HELLO,
        responses.issue_node(1, **changes),  # type: ignore[arg-type]
    )


def test_a_merged_pull_request_has_merged_at_and_closed_at() -> None:
    pull = parse_pull(state='MERGED', merged_at=NOW, closed_at=NOW)
    assert (pull.merged_at, pull.closed_at) == (NOW, NOW)


def test_a_closed_unmerged_pull_request_has_closed_at_only() -> None:
    pull = parse_pull(state='CLOSED', closed_at=NOW, merged_at=None)
    assert (pull.merged_at, pull.closed_at) == (None, NOW)


def test_a_stale_closed_at_on_an_open_pull_request_is_dropped() -> None:
    pull = parse_pull(state='OPEN', closed_at=NOW, merged_at=NOW)
    assert (pull.merged_at, pull.closed_at) == (None, None)


def test_a_reopened_issue_has_no_closed_at_and_a_closed_one_has_it() -> None:
    assert parse_issue(state='OPEN', closed_at=NOW).closed_at is None
    assert parse_issue(state='CLOSED', closed_at=NOW).closed_at == NOW


def test_a_bot_author_gets_the_bot_suffix_and_a_deleted_account_is_none() -> None:
    assert parse_pull(login='dependabot', bot=True).author_login == 'dependabot[bot]'
    assert parse_issue(login='dependabot', bot=True).author_login == 'dependabot[bot]'
    assert parse_pull(login=None).author_login is None
    assert parse_issue(login=None).author_login is None
    assert parse_pull(login='octocat').author_login == 'octocat'


def test_the_pull_request_fields_are_read() -> None:
    pull = parse_pull(created_at=NOW - HOUR, updated_at=NOW, additions=7, deletions=3)
    assert (pull.repo, pull.number) == (HELLO, 1)
    assert (pull.created_at, pull.updated_at) == (NOW - HOUR, NOW)
    assert (pull.additions, pull.deletions) == (7, 3)
    assert pull.first_review_at is None


def test_first_review_at_skips_the_authors_own_review_whatever_its_case() -> None:
    reviews = [
        responses.review_node(NOW + 1 * HOUR, 'OctoCat'),
        responses.review_node(NOW + 5 * HOUR, 'hubot'),
    ]
    assert parse_pull(login='octocat', reviews=reviews).first_review_at == NOW + 5 * HOUR


def test_first_review_at_skips_bot_reviews_and_pending_reviews() -> None:
    reviews = [
        responses.review_node(NOW + 1 * HOUR, 'copilot', bot=True),
        responses.review_node(None, 'hubot'),
        responses.review_node(NOW + 6 * HOUR, 'hubot'),
    ]
    assert parse_pull(reviews=reviews).first_review_at == NOW + 6 * HOUR


def test_first_review_at_counts_a_review_whose_author_is_null() -> None:
    reviews = [responses.review_node(NOW + 2 * HOUR, None)]
    assert parse_pull(reviews=reviews).first_review_at == NOW + 2 * HOUR


def test_first_review_at_is_the_earliest_when_the_reviews_are_out_of_order() -> None:
    reviews = [
        responses.review_node(NOW + 9 * HOUR, 'hubot'),
        responses.review_node(NOW + 3 * HOUR, 'mona'),
        responses.review_node(NOW + 7 * HOUR, 'hubot'),
    ]
    assert parse_pull(reviews=reviews).first_review_at == NOW + 3 * HOUR


def test_no_qualifying_review_gives_none() -> None:
    reviews = [
        responses.review_node(NOW, 'octocat'),
        responses.review_node(NOW, 'copilot', bot=True),
    ]
    assert parse_pull(login='octocat', reviews=reviews).first_review_at is None
    assert parse_pull(reviews=[]).first_review_at is None


def test_a_review_by_a_pull_request_with_no_author_counts() -> None:
    reviews = [responses.review_node(NOW, 'hubot')]
    assert parse_pull(login=None, reviews=reviews).first_review_at == NOW


def test_a_probe_with_empty_nodes_gives_none_and_a_node_gives_its_update_time() -> None:
    bare = wambatic.fetch.base.parse_repo(
        responses.repo_node('octocat/x', head=None, pushed_at=None, updated_at=NOW)
    )
    assert (bare.pull_requests_updated_at, bare.issues_updated_at) == (None, None)
    probed = wambatic.fetch.base.parse_repo(
        responses.repo_node(
            'octocat/x',
            head=None,
            pushed_at=None,
            updated_at=NOW,
            pull_requests_updated_at=NOW - HOUR,
            issues_updated_at=NOW - 2 * HOUR,
        )
    )
    assert probed.pull_requests_updated_at == NOW - HOUR
    assert probed.issues_updated_at == NOW - 2 * HOUR


def test_a_listing_node_without_the_probe_connections_is_malformed() -> None:
    node = responses.repo_node('octocat/x', head=None, pushed_at=None, updated_at=NOW)
    del node['pullRequests']
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_repo(node)


@pytest.mark.parametrize('field', ['number', 'createdAt', 'updatedAt', 'state'])
def test_a_node_missing_a_required_field_raises(field: str) -> None:
    pull = responses.pull_request_node(1)
    del pull[field]
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_pull_request(HELLO, pull)
    issue = responses.issue_node(1)
    del issue[field]
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_issue(HELLO, issue)


def test_an_author_without_a_login_is_malformed() -> None:
    node = responses.pull_request_node(1)
    node['author'] = {'__typename': 'User'}
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_pull_request(HELLO, node)


def test_the_hand_written_pages_parse() -> None:
    pulls = responses.PULL_REQUESTS_OK['data']['repository']['pullRequests']['nodes']  # type: ignore[index]
    parsed = [wambatic.fetch.base.parse_pull_request(HELLO, node) for node in pulls]
    assert [pull.number for pull in parsed] == [2, 1]
    assert parsed[0].first_review_at is not None
    assert parsed[1].author_login == 'dependabot[bot]'
