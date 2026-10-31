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
        'forks',
        'issues',
        'pull_requests',
        'releases',
        'star_events',
        'workflow_runs',
    }


def test_every_resource_is_built() -> None:
    assert wambatic.fetch.base.BUILT_RESOURCES == wambatic.fetch.base.RESOURCES


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
    assert (repo.releases_count, repo.releases_updated_at) == (0, None)
    assert not hasattr(repo, '__dict__')


def test_release_and_workflow_run_are_frozen_and_slotted() -> None:
    release = wambatic.fetch.base.Release('octocat/Hello-World', 'v1', NOW, NOW, False)
    run = wambatic.fetch.base.WorkflowRun(
        'octocat/Hello-World', 1, 'ci.yml', 'CI', 'push', None, 'queued', None, NOW, NOW, None, 1
    )
    for record, field in ((release, 'tag_name'), (run, 'id')):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(record, field, 2)
        assert not hasattr(record, '__dict__')


def test_star_event_and_fork_are_frozen_and_slotted() -> None:
    star = wambatic.fetch.base.StarEvent('octocat/Hello-World', 'MDQ6VXNlcjE=', NOW)
    fork = wambatic.fetch.base.Fork('octocat/Hello-World', 1, NOW)
    for record, field in ((star, 'user_id'), (fork, 'id')):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(record, field, 2)
        assert not hasattr(record, '__dict__')


def test_a_repo_built_without_the_popularity_fields_has_their_defaults() -> None:
    repo = wambatic.fetch.base.Repo('octocat/Hello-World', 'main', None, False, False, None, NOW)
    assert (repo.stargazer_count, repo.fork_count, repo.watcher_count) == (0, 0, 0)
    assert (repo.languages, repo.languages_size) == ((), 0)


def test_a_pull_request_and_a_sync_state_built_without_the_new_fields_have_defaults() -> None:
    pull = pull_request()
    assert (pull.labels, pull.first_commit_at) == ((), None)
    state = wambatic.fetch.base.SyncState(
        'octocat/Hello-World', 'commits', None, None, None, NOW, NOW, NOW
    )
    assert state.probe is None


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


def test_the_recorded_pull_request_and_issue_pages_parse() -> None:
    pulls = responses.PULL_REQUESTS_OK['data']['repository']['pullRequests']['nodes']  # type: ignore[index]
    parsed = [wambatic.fetch.base.parse_pull_request(HELLO, node) for node in pulls]
    assert parsed
    assert any(pull.merged_at is not None for pull in parsed)
    assert any(pull.labels for pull in parsed)
    assert all(pull.first_commit_at is not None for pull in parsed)
    bots = [node['author']['login'] for node in pulls if node['author']['__typename'] == 'Bot']
    assert bots
    assert not any(login.endswith('[bot]') for login in bots)
    assert {f'{login}[bot]' for login in bots} <= {pull.author_login for pull in parsed}
    issues = responses.ISSUES_OK['data']['repository']['issues']['nodes']  # type: ignore[index]
    assert [wambatic.fetch.base.parse_issue(HELLO, node).number for node in issues] == [
        node['number'] for node in issues
    ]


def test_an_automatic_reviewer_is_a_bot_without_the_suffix_and_not_a_first_review() -> None:
    reviews = responses.BOT_REVIEWS_OK['data']['repository']['pullRequest']['reviews']  # type: ignore[index]
    # The recording is of a live pull request, so people may review it after the bot does.
    bots = [node for node in reviews['nodes'] if node['author']['__typename'] == 'Bot']
    assert [node['author'] for node in bots] == [
        {'__typename': 'Bot', 'login': 'copilot-pull-request-reviewer'}
    ]
    assert wambatic.fetch.base.first_review_at({'nodes': bots}, 'someone') is None


# Labels, first commits, releases, workflow runs and the release probe


def test_labels_keep_githubs_order_and_a_pull_request_without_any_has_none() -> None:
    assert parse_pull(labels=('Hotfix', 'bug', 'ünï')).labels == ('Hotfix', 'bug', 'ünï')
    assert parse_pull().labels == ()


def test_first_commit_at_is_the_first_commits_authored_date_or_none() -> None:
    assert parse_pull(first_commit_at=NOW - HOUR).first_commit_at == NOW - HOUR
    assert parse_pull(first_commit_at=None).first_commit_at is None


@pytest.mark.parametrize('field', ['labels', 'commits'])
def test_a_pull_request_without_labels_or_commits_is_malformed(field: str) -> None:
    node = responses.pull_request_node(1)
    del node[field]
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_pull_request(HELLO, node)


def test_a_release_parses_and_keeps_the_prerelease_flag() -> None:
    release = wambatic.fetch.base.parse_release(
        HELLO,
        responses.release_node('v1', created_at=NOW - HOUR, published_at=NOW, is_prerelease=True),
    )
    assert release == wambatic.fetch.base.Release(HELLO, 'v1', NOW - HOUR, NOW, True)


def test_a_draft_or_a_release_without_publication_time_is_not_stored() -> None:
    draft = responses.release_node('v2', is_draft=True)
    unpublished = responses.release_node('v3', published_at=None)
    assert wambatic.fetch.base.parse_release(HELLO, draft) is None
    assert wambatic.fetch.base.parse_release(HELLO, unpublished) is None


def test_a_release_without_a_tag_is_malformed() -> None:
    node = responses.release_node('v1')
    del node['tagName']
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_release(HELLO, node)


def test_the_recorded_release_page_parses_and_keeps_a_prerelease() -> None:
    nodes = responses.RELEASES_OK['data']['repository']['releases']['nodes']  # type: ignore[index]
    parsed = [wambatic.fetch.base.parse_release(HELLO, node) for node in nodes]
    assert [release.tag_name for release in parsed if release] == [
        node['tagName'] for node in nodes if not node['isDraft']
    ]
    assert [release.is_prerelease for release in parsed if release].count(True) == 1


def test_a_workflow_run_parses_every_field() -> None:
    run = wambatic.fetch.base.parse_workflow_run(
        HELLO,
        responses.workflow_run_object(
            7,
            path='.github/workflows/deploy.yml',
            name='Deploy',
            event='workflow_dispatch',
            head_branch='release',
            created_at=NOW,
            updated_at=NOW + HOUR,
            run_started_at=NOW + HOUR / 2,
            run_attempt=2,
        ),
    )
    assert run == wambatic.fetch.base.WorkflowRun(
        HELLO,
        7,
        '.github/workflows/deploy.yml',
        'Deploy',
        'workflow_dispatch',
        'release',
        'completed',
        'success',
        NOW,
        NOW + HOUR,
        NOW + HOUR / 2,
        2,
    )


def test_an_unfinished_run_has_no_conclusion_and_a_queued_one_no_start() -> None:
    running = wambatic.fetch.base.parse_workflow_run(
        HELLO, responses.workflow_run_object(1, status='in_progress', conclusion=None)
    )
    queued = wambatic.fetch.base.parse_workflow_run(
        HELLO,
        responses.workflow_run_object(2, status='queued', conclusion=None, run_started_at=None),
    )
    assert (running.status, running.conclusion) == ('in_progress', None)
    assert (queued.status, queued.run_started_at) == ('queued', None)


def test_a_run_with_null_name_status_and_branch_and_no_attempt_still_parses() -> None:
    node = responses.workflow_run_object(3, name=None, status=None, head_branch=None)
    del node['run_attempt']
    run = wambatic.fetch.base.parse_workflow_run(HELLO, node)
    assert (run.name, run.status, run.head_branch, run.run_attempt) == ('', '', None, 1)


@pytest.mark.parametrize('field', ['id', 'path', 'event', 'created_at', 'updated_at'])
def test_a_malformed_run_raises(field: str) -> None:
    node = responses.workflow_run_object(1)
    del node[field]
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_workflow_run(HELLO, node)


def test_the_recorded_run_pages_parse_with_the_short_workflow_path() -> None:
    runs = responses.WORKFLOW_RUNS_OK['workflow_runs']
    assert isinstance(runs, list)
    parsed = [wambatic.fetch.base.parse_workflow_run(HELLO, node) for node in runs]
    assert [run.id for run in parsed] == [node['id'] for node in runs]
    assert all(run.workflow_path.startswith('.github/workflows/') for run in parsed)
    assert all(run.name and run.status and run.run_started_at for run in parsed)
    single = wambatic.fetch.base.parse_workflow_run(HELLO, responses.WORKFLOW_RUN_OK)
    assert single == parsed[0]


def test_the_release_probe_reads_the_count_and_the_newest_update() -> None:
    with_releases = wambatic.fetch.base.parse_repo(
        responses.repo_node(
            'octocat/x',
            head=None,
            pushed_at=None,
            updated_at=NOW,
            releases_count=3,
            releases_updated_at=NOW - HOUR,
        )
    )
    assert (with_releases.releases_count, with_releases.releases_updated_at) == (3, NOW - HOUR)
    assert wambatic.fetch.base.release_probe(with_releases) == '3 2026-10-29T11:00:00+00:00'
    without = wambatic.fetch.base.parse_repo(
        responses.repo_node('octocat/x', head=None, pushed_at=None, updated_at=NOW)
    )
    assert wambatic.fetch.base.release_probe(without) == '0 none'


def test_a_listing_node_without_the_release_probe_is_malformed() -> None:
    node = responses.repo_node('octocat/x', head=None, pushed_at=None, updated_at=NOW)
    del node['releases']
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_repo(node)
    node = responses.repo_node('octocat/x', head=None, pushed_at=None, updated_at=NOW)
    del node['releases']['totalCount']  # type: ignore[attr-defined]
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_repo(node)


# Counts, languages, stars and forks


def parse_popular(**changes: object) -> wambatic.fetch.base.Repo:
    return wambatic.fetch.base.parse_repo(
        responses.repo_node('octocat/x', head=None, pushed_at=None, updated_at=NOW, **changes)  # type: ignore[arg-type]
    )


def test_the_listing_counts_and_languages_are_read_in_githubs_order() -> None:
    repo = parse_popular(
        stargazer_count=12,
        fork_count=3,
        watcher_count=5,
        languages=[('Python', 900), ('Ünïcode', 80)],
        languages_size=1500,
    )
    assert (repo.stargazer_count, repo.fork_count, repo.watcher_count) == (12, 3, 5)
    assert repo.languages == (('Python', 900), ('Ünïcode', 80))
    assert repo.languages_size == 1500


def test_a_null_languages_connection_is_no_languages() -> None:
    repo = parse_popular(stargazer_count=1)
    assert (repo.languages, repo.languages_size) == ((), 0)


def test_the_probes_are_the_listed_counts_as_text() -> None:
    repo = parse_popular(stargazer_count=12, fork_count=3)
    assert wambatic.fetch.base.star_probe(repo) == '12'
    assert wambatic.fetch.base.fork_probe(repo) == '3'


@pytest.mark.parametrize('field', ['stargazerCount', 'forkCount', 'watchers'])
def test_a_listing_node_without_a_count_is_malformed(field: str) -> None:
    node = responses.repo_node('octocat/x', head=None, pushed_at=None, updated_at=NOW)
    del node[field]
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_repo(node)


def test_a_language_edge_without_a_size_or_a_name_is_malformed() -> None:
    for broken in ({'node': {'name': 'C'}}, {'size': 1, 'node': {}}):
        node = responses.repo_node('octocat/x', head=None, pushed_at=None, updated_at=NOW)
        node['languages'] = {'totalSize': 1, 'edges': [broken]}
        with pytest.raises(wambatic.fetch.errors.GraphQLError):
            wambatic.fetch.base.parse_repo(node)


def test_a_star_edge_keeps_the_node_id_and_no_login() -> None:
    star = wambatic.fetch.base.parse_star_edge(HELLO, responses.star_edge('MDQ6VXNlcjE=', NOW))
    assert star == wambatic.fetch.base.StarEvent(HELLO, 'MDQ6VXNlcjE=', NOW)
    assert set(dataclasses.asdict(star)) == {'repo', 'user_id', 'starred_at'}


@pytest.mark.parametrize(
    'edge',
    [
        {'node': {'id': 'U_1'}},
        {'starredAt': '2026-10-29T12:00:00Z'},
        {'starredAt': '2026-10-29T12:00:00Z', 'node': {}},
        {'starredAt': 'yesterday', 'node': {'id': 'U_1'}},
        None,
    ],
)
def test_a_malformed_star_edge_raises(edge: object) -> None:
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_star_edge(HELLO, edge)


def test_a_fork_reads_its_id_and_creation_time() -> None:
    fork = wambatic.fetch.base.parse_fork(HELLO, responses.fork_object(7, NOW))
    assert fork == wambatic.fetch.base.Fork(HELLO, 7, NOW)


@pytest.mark.parametrize(
    'node',
    [{'created_at': '2026-10-29T12:00:00Z'}, {'id': 1}, {'id': '7', 'created_at': 'x'}, []],
)
def test_a_malformed_fork_raises(node: object) -> None:
    with pytest.raises(wambatic.fetch.errors.GraphQLError):
        wambatic.fetch.base.parse_fork(HELLO, node)


def test_the_recorded_popularity_responses_parse() -> None:
    listing = responses.OWNER_REPOSITORIES_OK['data']['repositoryOwner']['repositories']['nodes']  # type: ignore[index]
    repos = {node['nameWithOwner']: wambatic.fetch.base.parse_repo(node) for node in listing}
    hello, spoon = repos['octocat/Hello-World'], repos['octocat/Spoon-Knife']
    assert (hello.languages, hello.languages_size) == ((), 0)
    assert spoon.languages[0][0] == 'HTML'
    assert spoon.languages_size == sum(size for _, size in spoon.languages)
    assert spoon.stargazer_count > 0
    assert spoon.fork_count > 0
    assert spoon.watcher_count > 0
    stars = responses.STARGAZERS_OK['data']['repository']['stargazers']['edges']  # type: ignore[index]
    parsed = [wambatic.fetch.base.parse_star_edge(HELLO, edge) for edge in stars]
    assert [star.user_id for star in parsed] == [edge['node']['id'] for edge in stars]
    assert [star.starred_at for star in parsed] == sorted(
        (star.starred_at for star in parsed), reverse=True
    )
    forks = [wambatic.fetch.base.parse_fork(HELLO, fork) for fork in responses.FORKS_OK]
    assert [fork.created_at for fork in forks] == sorted(
        (fork.created_at for fork in forks), reverse=True
    )
