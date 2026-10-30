import datetime
import pathlib
import sqlite3
import typing

import hypothesis
import hypothesis.strategies
import pytest

import tests.fixtures.stats
import wambatic.fetch.base
import wambatic.fetch.cache
import wambatic.fetch.errors
import wambatic.fetch.queries
import wambatic.version

UTC = datetime.UTC
T0 = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
HELLO = 'octocat/Hello-World'
SPOON = 'octocat/Spoon-Knife'
CURRENT_SCHEMA_VERSION = wambatic.fetch.cache.SCHEMA_VERSION
NEXT_SCHEMA_VERSION = CURRENT_SCHEMA_VERSION + 1


@pytest.fixture
def cache_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / 'nested' / 'cache.sqlite3'


@pytest.fixture
def cache(cache_path: pathlib.Path) -> typing.Iterator[wambatic.fetch.cache.Cache]:
    opened = wambatic.fetch.cache.Cache.open(cache_path)
    yield opened
    opened.close()


def repo(name: str = HELLO, **changes: object) -> wambatic.fetch.base.Repo:
    fields: dict[str, object] = {
        'name_with_owner': name,
        'default_branch': 'main',
        'head_oid': 'a' * 40,
        'is_archived': False,
        'is_fork': False,
        'pushed_at': T0,
        'updated_at': T0 + datetime.timedelta(hours=1),
    }
    fields.update(changes)
    return wambatic.fetch.base.Repo(**fields)  # type: ignore[arg-type]


def commit(
    oid: str, hours: int = 0, repo_name: str = HELLO, **changes: object
) -> wambatic.fetch.base.Commit:
    fields: dict[str, object] = {
        'repo': repo_name,
        'oid': oid,
        'authored_at': T0 + datetime.timedelta(hours=hours),
        'author_login': 'octocat',
        'additions': 3,
        'deletions': 1,
        'is_merge': False,
    }
    fields.update(changes)
    return wambatic.fetch.base.Commit(**fields)  # type: ignore[arg-type]


def pull_request(
    number: int, hours: int = 0, repo_name: str = HELLO, **changes: object
) -> wambatic.fetch.base.PullRequest:
    fields: dict[str, object] = {
        'repo': repo_name,
        'number': number,
        'author_login': 'octocat',
        'created_at': T0,
        'updated_at': T0 + datetime.timedelta(hours=hours),
        'merged_at': T0 + datetime.timedelta(hours=hours),
        'closed_at': T0 + datetime.timedelta(hours=hours),
        'first_review_at': T0 + datetime.timedelta(minutes=30),
        'additions': 10,
        'deletions': 2,
    }
    fields.update(changes)
    return wambatic.fetch.base.PullRequest(**fields)  # type: ignore[arg-type]


def issue(
    number: int, hours: int = 0, repo_name: str = HELLO, **changes: object
) -> wambatic.fetch.base.Issue:
    fields: dict[str, object] = {
        'repo': repo_name,
        'number': number,
        'author_login': 'octocat',
        'created_at': T0,
        'updated_at': T0 + datetime.timedelta(hours=hours),
        'closed_at': None,
    }
    fields.update(changes)
    return wambatic.fetch.base.Issue(**fields)  # type: ignore[arg-type]


def release(
    tag_name: str, hours: int = 0, repo_name: str = HELLO, **changes: object
) -> wambatic.fetch.base.Release:
    created = T0 + datetime.timedelta(hours=hours)
    fields: dict[str, object] = {
        'repo': repo_name,
        'tag_name': tag_name,
        'created_at': created,
        'published_at': created + datetime.timedelta(minutes=5),
        'is_prerelease': False,
    }
    fields.update(changes)
    return wambatic.fetch.base.Release(**fields)  # type: ignore[arg-type]


def workflow_run(
    run_id: int, hours: int = 0, repo_name: str = HELLO, **changes: object
) -> wambatic.fetch.base.WorkflowRun:
    created = T0 + datetime.timedelta(hours=hours)
    fields: dict[str, object] = {
        'repo': repo_name,
        'id': run_id,
        'workflow_path': '.github/workflows/ci.yml',
        'name': 'CI',
        'event': 'push',
        'head_branch': 'main',
        'status': 'completed',
        'conclusion': 'success',
        'created_at': created,
        'updated_at': created + datetime.timedelta(minutes=4),
        'run_started_at': created + datetime.timedelta(seconds=10),
        'run_attempt': 1,
    }
    fields.update(changes)
    return wambatic.fetch.base.WorkflowRun(**fields)  # type: ignore[arg-type]


def star_event(
    user_id: str, hours: int = 0, repo_name: str = HELLO
) -> wambatic.fetch.base.StarEvent:
    return wambatic.fetch.base.StarEvent(
        repo=repo_name, user_id=user_id, starred_at=T0 + datetime.timedelta(hours=hours)
    )


def fork(fork_id: int, hours: int = 0, repo_name: str = HELLO) -> wambatic.fetch.base.Fork:
    return wambatic.fetch.base.Fork(
        repo=repo_name, id=fork_id, created_at=T0 + datetime.timedelta(hours=hours)
    )


def state(
    repo_name: str = HELLO,
    head: str | None = 'a' * 40,
    hours: int = 0,
    resource: str = 'commits',
    probe: str | None = None,
) -> wambatic.fetch.base.SyncState:
    return wambatic.fetch.base.SyncState(
        repo=repo_name,
        resource=resource,
        watermark=None,
        head_oid=head,
        pushed_at=T0,
        updated_at=T0 + datetime.timedelta(hours=1),
        synced_at=T0 + datetime.timedelta(hours=hours),
        full_synced_at=T0,
        probe=probe,
    )


def table_rows(path: pathlib.Path, table: str) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(f'SELECT * FROM {table}').fetchall()
    finally:
        connection.close()


# Open, schema and identity


def test_new_file_is_wal_with_the_expected_identity(cache_path: pathlib.Path) -> None:
    opened = wambatic.fetch.cache.Cache.open(cache_path)
    try:
        assert opened.identity() == wambatic.fetch.cache.expected_identity()
        mode = opened.connection.execute('PRAGMA journal_mode').fetchone()[0]
        assert mode == 'wal'
        tables = {
            row[0]
            for row in opened.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {'meta', 'repos', 'commits', 'etags', 'sync_state'} <= tables
    finally:
        opened.close()


def test_identity_has_versions_and_a_hash_per_query(cache: wambatic.fetch.cache.Cache) -> None:
    identity = cache.identity()
    assert identity['schema_version'] == str(wambatic.fetch.cache.SCHEMA_VERSION)
    assert identity['wambatic_version'] == wambatic.version.VERSION
    assert {'query:OWNER_REPOSITORIES', 'query:COMMIT_HISTORY'} <= identity.keys()
    assert len(identity['query:COMMIT_NODES']) == 64


def test_reopening_succeeds(cache_path: pathlib.Path) -> None:
    wambatic.fetch.cache.Cache.open(cache_path).close()
    wambatic.fetch.cache.Cache.open(cache_path).close()


def test_changed_schema_version_raises(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wambatic.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.setattr(wambatic.fetch.cache, 'SCHEMA_VERSION', NEXT_SCHEMA_VERSION)
    with pytest.raises(wambatic.fetch.errors.CacheVersionError) as caught:
        wambatic.fetch.cache.Cache.open(cache_path)
    assert caught.value.differences == {
        'schema_version': (str(CURRENT_SCHEMA_VERSION), str(NEXT_SCHEMA_VERSION))
    }
    assert (
        f'schema_version: cache has {CURRENT_SCHEMA_VERSION}, '
        f'this wambatic has {NEXT_SCHEMA_VERSION}'
    ) in str(caught.value)
    assert 'wambatic cache clear' in str(caught.value)
    assert '--ignore-cache-version' in str(caught.value)


def test_changed_wambatic_version_raises(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wambatic.fetch.cache.Cache.open(cache_path).close()
    recorded = wambatic.version.VERSION
    monkeypatch.setattr(wambatic.version, 'VERSION', '9.9.9')
    with pytest.raises(wambatic.fetch.errors.CacheVersionError) as caught:
        wambatic.fetch.cache.Cache.open(cache_path)
    assert caught.value.differences == {'wambatic_version': (recorded, '9.9.9')}


def test_changed_query_text_raises_naming_the_query(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wambatic.fetch.cache.Cache.open(cache_path).close()
    recorded = wambatic.fetch.cache.expected_identity()['query:COMMIT_NODES']
    monkeypatch.setattr(wambatic.fetch.queries, 'COMMIT_NODES', 'query { changed }')
    with pytest.raises(wambatic.fetch.errors.CacheVersionError) as caught:
        wambatic.fetch.cache.Cache.open(cache_path)
    (key, (old, new)), *rest = caught.value.differences.items()
    assert (key, old, rest) == ('query:COMMIT_NODES', recorded, [])
    assert new != recorded


def test_adding_a_query_changes_the_identity_without_editing_the_cache_module(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wambatic.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.setattr(wambatic.fetch.queries, 'EXTRA_QUERY', 'query { extra }', raising=False)
    with pytest.raises(wambatic.fetch.errors.CacheVersionError) as caught:
        wambatic.fetch.cache.Cache.open(cache_path)
    assert list(caught.value.differences) == ['query:EXTRA_QUERY']
    assert caught.value.differences['query:EXTRA_QUERY'][0] is None


def test_a_query_removed_from_the_code_raises(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wambatic.fetch.queries, 'EXTRA_QUERY', 'query { extra }', raising=False)
    wambatic.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.delattr(wambatic.fetch.queries, 'EXTRA_QUERY')
    with pytest.raises(wambatic.fetch.errors.CacheVersionError) as caught:
        wambatic.fetch.cache.Cache.open(cache_path)
    assert caught.value.differences['query:EXTRA_QUERY'][1] is None
    assert 'this wambatic has nothing' in str(caught.value)


def test_a_mismatch_closes_the_connection(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wambatic.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.setattr(wambatic.fetch.cache, 'SCHEMA_VERSION', NEXT_SCHEMA_VERSION)
    connections: list[sqlite3.Connection] = []
    connect = sqlite3.connect

    def spy(*args: object, **kwargs: object) -> sqlite3.Connection:
        connections.append(connect(*args, **kwargs))  # type: ignore[call-overload]
        return connections[-1]

    monkeypatch.setattr(sqlite3, 'connect', spy)
    with pytest.raises(wambatic.fetch.errors.CacheVersionError):
        wambatic.fetch.cache.Cache.open(cache_path)
    (connection,) = connections
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connection.execute('SELECT 1')


def test_ignore_version_opens_and_records_the_override(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wambatic.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.setattr(wambatic.fetch.cache, 'SCHEMA_VERSION', NEXT_SCHEMA_VERSION)
    opened = wambatic.fetch.cache.Cache.open(cache_path, ignore_version=True)
    try:
        assert 'version_override_at' not in opened.identity()
        assert opened.identity()['schema_version'] == str(CURRENT_SCHEMA_VERSION)
    finally:
        opened.close()
    keys = {row[0] for row in table_rows(cache_path, 'meta')}
    assert 'version_override_at' in keys
    with pytest.raises(wambatic.fetch.errors.CacheVersionError):
        wambatic.fetch.cache.Cache.open(cache_path)


def test_ignore_version_on_a_matching_cache_records_nothing(cache_path: pathlib.Path) -> None:
    wambatic.fetch.cache.Cache.open(cache_path).close()
    wambatic.fetch.cache.Cache.open(cache_path, ignore_version=True).close()
    assert 'version_override_at' not in {row[0] for row in table_rows(cache_path, 'meta')}


def test_version_override_at_is_none_for_a_matching_cache(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    assert cache.version_override_at() is None


def test_version_override_at_is_the_recorded_time_after_an_override(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wambatic.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.setattr(wambatic.fetch.cache, 'SCHEMA_VERSION', NEXT_SCHEMA_VERSION)
    before = datetime.datetime.now(UTC)
    opened = wambatic.fetch.cache.Cache.open(cache_path, ignore_version=True)
    try:
        recorded = opened.version_override_at()
    finally:
        opened.close()
    assert recorded is not None
    assert before <= wambatic.fetch.cache.from_text(recorded) <= datetime.datetime.now(UTC)


# Repos


def test_repos_round_trip(cache: wambatic.fetch.cache.Cache) -> None:
    empty = repo('octocat/Empty', default_branch=None, head_oid=None, pushed_at=None)
    stored = [repo(), empty, repo(SPOON, is_fork=True, is_archived=True)]
    cache.upsert_repos('octocat', stored, complete=True)
    read = cache.read_repos(wambatic.fetch.base.Subject('user', 'octocat'))
    assert read == sorted(stored, key=lambda item: item.name_with_owner)


def test_read_repos_of_a_repo_subject_is_its_one_row(cache: wambatic.fetch.cache.Cache) -> None:
    cache.upsert_repos('octocat', [repo(), repo(SPOON)], complete=True)
    subject = wambatic.fetch.base.Subject('repo', 'octocat', 'Hello-World')
    assert cache.read_repos(subject) == [repo()]
    assert cache.read_repos(wambatic.fetch.base.Subject('repo', 'octocat', 'nope')) == []


def test_owner_lookup_ignores_case(cache: wambatic.fetch.cache.Cache) -> None:
    cache.upsert_repos('OctoCat', [repo()], complete=True)
    assert cache.read_repos(wambatic.fetch.base.Subject('org', 'OCTOCAT')) == [repo()]
    assert cache.read_repos(wambatic.fetch.base.Subject('repo', 'OctoCat', 'hello-world')) == [
        repo()
    ]


def test_complete_listing_marks_absent_repos_missing_and_keeps_their_commits(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    cache.upsert_repos('octocat', [repo(), repo(SPOON)], complete=True)
    cache.write_commits(SPOON, [commit('s1', repo_name=SPOON)], state(SPOON), replace=True)
    cache.upsert_repos('octocat', [repo()], complete=True)
    by_name = {
        item.name_with_owner: item
        for item in cache.read_repos(wambatic.fetch.base.Subject('user', 'octocat'))
    }
    assert not by_name[HELLO].missing
    assert by_name[SPOON].missing
    assert [c.oid for c in cache.read_commits(SPOON, None, None)] == ['s1']
    cache.upsert_repos('octocat', [repo(), repo(SPOON)], complete=True)
    assert not cache.read_repos(wambatic.fetch.base.Subject('repo', 'octocat', 'Spoon-Knife'))[
        0
    ].missing


def test_incomplete_listing_leaves_other_repos_alone(cache: wambatic.fetch.cache.Cache) -> None:
    cache.upsert_repos('octocat', [repo(), repo(SPOON)], complete=True)
    cache.upsert_repos('octocat', [repo()], complete=False)
    rows = cache.read_repos(wambatic.fetch.base.Subject('user', 'octocat'))
    assert [item.missing for item in rows] == [False, False]


def test_complete_listing_leaves_other_owners_alone(cache: wambatic.fetch.cache.Cache) -> None:
    cache.upsert_repos('octocat', [repo()], complete=True)
    cache.upsert_repos('github', [repo('github/docs')], complete=True)
    assert not cache.read_repos(wambatic.fetch.base.Subject('user', 'octocat'))[0].missing


def test_naive_times_are_refused(cache: wambatic.fetch.cache.Cache) -> None:
    with pytest.raises(ValueError, match='timezone-aware'):
        cache.upsert_repos(
            'octocat', [repo(updated_at=datetime.datetime(2026, 1, 1))], complete=False
        )


# Commits and sync state


def test_state_round_trip(cache: wambatic.fetch.cache.Cache) -> None:
    assert cache.sync_state(HELLO, 'commits') is None
    written = state()
    cache.write_commits(HELLO, [], written, replace=False)
    assert cache.sync_state(HELLO, 'commits') == written
    assert cache.sync_state(HELLO, 'issues') is None


def test_state_with_no_head_or_pushed_at_round_trips(cache: wambatic.fetch.cache.Cache) -> None:
    written = wambatic.fetch.base.SyncState(HELLO, 'commits', None, None, None, T0, T0, T0)
    cache.write_commits(HELLO, [], written, replace=False)
    assert cache.sync_state(HELLO, 'commits') == written


def test_commit_upsert_by_oid_is_idempotent(cache: wambatic.fetch.cache.Cache) -> None:
    commits = [commit('c1', 1), commit('c2', 2)]
    cache.write_commits(HELLO, commits, state(), replace=False)
    cache.write_commits(HELLO, commits, state(), replace=False)
    assert cache.read_commits(HELLO, None, None) == commits


def test_upsert_replaces_a_commit_with_the_same_oid(cache: wambatic.fetch.cache.Cache) -> None:
    cache.write_commits(HELLO, [commit('c1', additions=1)], state(), replace=False)
    cache.write_commits(HELLO, [commit('c1', additions=9)], state(), replace=False)
    assert [c.additions for c in cache.read_commits(HELLO, None, None)] == [9]


def test_write_commits_returns_the_rows_written(cache: wambatic.fetch.cache.Cache) -> None:
    assert cache.write_commits(HELLO, [commit('c1'), commit('c2')], state(), replace=False) == 2


def test_replace_removes_commits_not_in_the_new_list(cache: wambatic.fetch.cache.Cache) -> None:
    cache.write_commits(HELLO, [commit('c1', 1), commit('c2', 2)], state(), replace=False)
    cache.write_commits(SPOON, [commit('s1', 1, SPOON)], state(SPOON), replace=False)
    cache.write_commits(HELLO, [commit('c2', 2), commit('c3', 3)], state(), replace=True)
    assert [c.oid for c in cache.read_commits(HELLO, None, None)] == ['c2', 'c3']
    assert [c.oid for c in cache.read_commits(SPOON, None, None)] == ['s1']


def test_commits_of_another_repo_are_refused(cache: wambatic.fetch.cache.Cache) -> None:
    with pytest.raises(ValueError, match='must belong to'):
        cache.write_commits(HELLO, [commit('s1', repo_name=SPOON)], state(), replace=False)
    with pytest.raises(ValueError, match='must belong to'):
        cache.write_commits(HELLO, [], state(SPOON), replace=False)


def test_a_failure_mid_write_leaves_rows_and_state_unchanged(
    cache: wambatic.fetch.cache.Cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = state(head='a' * 40)
    cache.write_commits(HELLO, [commit('c1', 1)], old, replace=False)

    def fail(new_state: wambatic.fetch.base.SyncState) -> None:
        raise sqlite3.OperationalError('disk full')

    monkeypatch.setattr(cache, 'put_state', fail)
    for replace in (False, True):
        with pytest.raises(sqlite3.OperationalError):
            cache.write_commits(HELLO, [commit('c2', 2)], state(head='b' * 40), replace=replace)
        assert [c.oid for c in cache.read_commits(HELLO, None, None)] == ['c1']
        assert cache.sync_state(HELLO, 'commits') == old


def test_read_commits_bounds_are_half_open_and_ordered(cache: wambatic.fetch.cache.Cache) -> None:
    commits = [commit('c3', 3), commit('c1', 1), commit('c2b', 2), commit('c2a', 2)]
    cache.write_commits(HELLO, commits, state(), replace=False)

    def oids(since: int | None, until: int | None) -> list[str]:
        lower = None if since is None else T0 + datetime.timedelta(hours=since)
        upper = None if until is None else T0 + datetime.timedelta(hours=until)
        return [c.oid for c in cache.read_commits(HELLO, lower, upper)]

    assert oids(None, None) == ['c1', 'c2a', 'c2b', 'c3']
    assert oids(2, 3) == ['c2a', 'c2b']
    assert oids(None, 2) == ['c1']
    assert oids(3, None) == ['c3']
    assert oids(4, None) == []


def test_commit_without_an_account_and_merge_flag_round_trip(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    stored = commit('m1', author_login=None, is_merge=True, additions=0, deletions=0)
    cache.write_commits(HELLO, [stored], state(), replace=False)
    assert cache.read_commits(HELLO, None, None) == [stored]


instants = hypothesis.strategies.datetimes(
    min_value=datetime.datetime(2000, 1, 1),
    max_value=datetime.datetime(2100, 1, 1),
    timezones=hypothesis.strategies.just(UTC),
)
commit_lists = hypothesis.strategies.lists(
    hypothesis.strategies.builds(
        wambatic.fetch.base.Commit,
        repo=hypothesis.strategies.just(HELLO),
        oid=hypothesis.strategies.sampled_from(['a', 'b', 'c', 'd']),
        authored_at=instants,
        author_login=hypothesis.strategies.none() | hypothesis.strategies.just('octocat'),
        additions=hypothesis.strategies.integers(0, 10_000),
        deletions=hypothesis.strategies.integers(0, 10_000),
        is_merge=hypothesis.strategies.booleans(),
    ),
    max_size=12,
)


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(commits=commit_lists)
def test_write_then_read_keeps_the_last_commit_per_oid(
    commits: list[wambatic.fetch.base.Commit], tmp_path_factory: pytest.TempPathFactory
) -> None:
    opened = wambatic.fetch.cache.Cache.open(tmp_path_factory.mktemp('cache') / 'cache.sqlite3')
    try:
        opened.write_commits(HELLO, commits, state(), replace=False)
        last = {c.oid: c for c in commits}
        read = opened.read_commits(HELLO, None, None)
        assert sorted(read, key=lambda c: c.oid) == sorted(last.values(), key=lambda c: c.oid)
        assert read == sorted(read, key=lambda c: (c.authored_at, c.oid))
    finally:
        opened.close()


# Pull requests and issues


def test_pull_requests_round_trip_with_none_times_and_a_non_ascii_login(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    pulls = [
        pull_request(1, 2),
        pull_request(
            2,
            3,
            author_login='zoë-ü',
            merged_at=None,
            closed_at=None,
            first_review_at=None,
        ),
        pull_request(3, 4, author_login=None),
    ]
    assert (
        cache.write_pull_requests(HELLO, pulls, state(resource='pull_requests'), replace=False) == 3
    )
    assert cache.read_pull_requests(HELLO, None) == pulls


def test_issues_round_trip_with_none_times_and_a_non_ascii_login(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    issues = [
        issue(1, 2, closed_at=T0 + datetime.timedelta(hours=2)),
        issue(2, 3, author_login='zoë-ü'),
        issue(3, 4, author_login=None),
    ]
    assert cache.write_issues(HELLO, issues, state(resource='issues'), replace=False) == 3
    assert cache.read_issues(HELLO, None) == issues


def test_replace_removes_pull_requests_and_issues_not_in_the_new_list(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    pulls_state = state(resource='pull_requests')
    issues_state = state(resource='issues')
    cache.write_pull_requests(HELLO, [pull_request(1), pull_request(2)], pulls_state, replace=False)
    cache.write_issues(HELLO, [issue(1), issue(2)], issues_state, replace=False)
    cache.write_pull_requests(HELLO, [pull_request(2)], pulls_state, replace=False)
    cache.write_issues(HELLO, [issue(2)], issues_state, replace=False)
    assert [pull.number for pull in cache.read_pull_requests(HELLO, None)] == [1, 2]
    assert [item.number for item in cache.read_issues(HELLO, None)] == [1, 2]
    cache.write_pull_requests(HELLO, [pull_request(2)], pulls_state, replace=True)
    cache.write_issues(HELLO, [issue(2)], issues_state, replace=True)
    assert [pull.number for pull in cache.read_pull_requests(HELLO, None)] == [2]
    assert [item.number for item in cache.read_issues(HELLO, None)] == [2]


def test_replace_leaves_another_repos_pull_requests_alone(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    cache.write_pull_requests(
        SPOON,
        [pull_request(1, repo_name=SPOON)],
        state(SPOON, resource='pull_requests'),
        replace=False,
    )
    cache.write_pull_requests(HELLO, [], state(resource='pull_requests'), replace=True)
    assert len(cache.read_pull_requests(SPOON, None)) == 1


def test_upserting_a_changed_pull_request_replaces_its_fields_and_keeps_the_row_count(
    cache: wambatic.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    pulls_state = state(resource='pull_requests')
    cache.write_pull_requests(
        HELLO, [pull_request(1, 1, merged_at=None)], pulls_state, replace=False
    )
    changed = pull_request(1, 5, additions=99)
    cache.write_pull_requests(HELLO, [changed], pulls_state, replace=False)
    assert cache.read_pull_requests(HELLO, None) == [changed]
    assert len(table_rows(cache_path, 'pull_requests')) == 1


def test_upserting_a_changed_issue_replaces_its_fields_and_keeps_the_row_count(
    cache: wambatic.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    issues_state = state(resource='issues')
    cache.write_issues(HELLO, [issue(1, 1)], issues_state, replace=False)
    changed = issue(1, 5, closed_at=T0 + datetime.timedelta(hours=5))
    cache.write_issues(HELLO, [changed], issues_state, replace=False)
    assert cache.read_issues(HELLO, None) == [changed]
    assert len(table_rows(cache_path, 'issues')) == 1


def test_reads_with_since_keep_exactly_the_rows_updated_at_or_after_it(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    cache.write_pull_requests(
        HELLO,
        [pull_request(3, 5), pull_request(1, 1), pull_request(2, 3)],
        state(resource='pull_requests'),
        replace=False,
    )
    cache.write_issues(
        HELLO, [issue(3, 5), issue(1, 1), issue(2, 3)], state(resource='issues'), replace=False
    )
    since = T0 + datetime.timedelta(hours=3)
    assert [pull.number for pull in cache.read_pull_requests(HELLO, since)] == [2, 3]
    assert [item.number for item in cache.read_issues(HELLO, since)] == [2, 3]
    assert [pull.number for pull in cache.read_pull_requests(HELLO, None)] == [1, 2, 3]
    assert [item.number for item in cache.read_issues(HELLO, None)] == [1, 2, 3]


def test_a_pull_request_or_state_for_another_repo_raises_and_writes_nothing(
    cache: wambatic.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    pulls_state = state(resource='pull_requests')
    with pytest.raises(ValueError, match='must belong to'):
        cache.write_pull_requests(
            HELLO, [pull_request(1), pull_request(2, repo_name=SPOON)], pulls_state, replace=False
        )
    with pytest.raises(ValueError, match='must belong to'):
        cache.write_pull_requests(
            HELLO, [pull_request(1)], state(SPOON, resource='pull_requests'), replace=False
        )
    assert table_rows(cache_path, 'pull_requests') == []
    assert cache.sync_state(HELLO, 'pull_requests') is None
    assert cache.sync_state(SPOON, 'pull_requests') is None


def test_an_issue_or_state_for_another_repo_raises_and_writes_nothing(
    cache: wambatic.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    issues_state = state(resource='issues')
    with pytest.raises(ValueError, match='must belong to'):
        cache.write_issues(
            HELLO, [issue(1), issue(2, repo_name=SPOON)], issues_state, replace=False
        )
    with pytest.raises(ValueError, match='must belong to'):
        cache.write_issues(HELLO, [issue(1)], state(SPOON, resource='issues'), replace=False)
    assert table_rows(cache_path, 'issues') == []
    assert cache.sync_state(HELLO, 'issues') is None
    assert cache.sync_state(SPOON, 'issues') is None


def test_the_repo_probe_fields_round_trip_through_upsert_and_read(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    probed = repo(
        pull_requests_updated_at=T0 + datetime.timedelta(hours=2),
        issues_updated_at=T0 + datetime.timedelta(hours=3),
    )
    cache.upsert_repos('octocat', [probed, repo(SPOON)], complete=True)
    rows = cache.read_repos(wambatic.fetch.base.Subject('user', 'octocat'))
    assert rows == [probed, repo(SPOON)]
    assert rows[1].pull_requests_updated_at is None
    assert rows[1].issues_updated_at is None


@pytest.mark.parametrize('old', ['1', '2', '3'])
def test_a_cache_stamped_with_an_earlier_schema_version_is_refused(
    cache_path: pathlib.Path, old: str
) -> None:
    wambatic.fetch.cache.Cache.open(cache_path).close()
    connection = sqlite3.connect(cache_path)
    with connection:
        connection.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (old,))
    connection.close()
    with pytest.raises(wambatic.fetch.errors.CacheVersionError) as caught:
        wambatic.fetch.cache.Cache.open(cache_path)
    assert caught.value.differences['schema_version'] == (old, str(CURRENT_SCHEMA_VERSION))


# Labels, releases and workflow runs


def test_pull_requests_round_trip_with_labels_and_a_first_commit(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    pulls = [
        pull_request(
            1, 2, labels=('Hotfix', 'bug'), first_commit_at=T0 - datetime.timedelta(days=1)
        ),
        pull_request(2, 3, labels=('ünïcode ✓',)),
        pull_request(3, 4, labels=(), first_commit_at=None),
    ]
    cache.write_pull_requests(HELLO, pulls, state(resource='pull_requests'), replace=False)
    read = cache.read_pull_requests(HELLO, None)
    assert read == pulls
    assert read[0].labels == ('Hotfix', 'bug')
    assert read[1].labels == ('ünïcode ✓',)
    assert read[2].labels == ()
    assert read[2].first_commit_at is None


def test_releases_round_trip_oldest_published_first_then_tag(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    releases = [
        release('v2', 5),
        release('v1.1', 1, is_prerelease=True),
        release('b', 3, published_at=T0 + datetime.timedelta(hours=9)),
        release('a', 4, published_at=T0 + datetime.timedelta(hours=9)),
    ]
    assert cache.write_releases(HELLO, releases, state(resource='releases')) == 4
    assert [r.tag_name for r in cache.read_releases(HELLO)] == ['v1.1', 'v2', 'a', 'b']
    assert sorted(cache.read_releases(HELLO), key=lambda r: r.tag_name) == sorted(
        releases, key=lambda r: r.tag_name
    )


def test_write_releases_replaces_the_repos_rows_and_leaves_another_repo_alone(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    cache.write_releases(HELLO, [release('v1'), release('v2', 1)], state(resource='releases'))
    cache.write_releases(SPOON, [release('s1', repo_name=SPOON)], state(SPOON, resource='releases'))
    cache.write_releases(HELLO, [release('v3', 2)], state(resource='releases'))
    assert [r.tag_name for r in cache.read_releases(HELLO)] == ['v3']
    assert [r.tag_name for r in cache.read_releases(SPOON)] == ['s1']


def test_workflow_runs_round_trip_with_none_fields(cache: wambatic.fetch.cache.Cache) -> None:
    runs = [
        workflow_run(1, 1),
        workflow_run(
            2,
            2,
            status='in_progress',
            conclusion=None,
            head_branch=None,
            run_attempt=3,
        ),
        workflow_run(3, 3, status='queued', conclusion=None, run_started_at=None),
    ]
    assert (
        cache.write_workflow_runs(HELLO, runs, state(resource='workflow_runs'), replace=False) == 3
    )
    assert cache.read_workflow_runs(HELLO, None) == runs


def test_write_workflow_runs_upserts_and_replace_controls_unlisted_runs(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    runs_state = state(resource='workflow_runs')
    cache.write_workflow_runs(
        HELLO, [workflow_run(1, 1), workflow_run(2, 2)], runs_state, replace=False
    )
    cache.write_workflow_runs(
        HELLO, [workflow_run(2, 2, conclusion='failure')], runs_state, replace=False
    )
    read = cache.read_workflow_runs(HELLO, None)
    assert [(run.id, run.conclusion) for run in read] == [(1, 'success'), (2, 'failure')]
    cache.write_workflow_runs(HELLO, [workflow_run(2, 2)], runs_state, replace=True)
    assert [run.id for run in cache.read_workflow_runs(HELLO, None)] == [2]


def test_write_workflow_runs_removes_the_gone_ids_either_way(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    runs_state = state(resource='workflow_runs')
    cache.write_workflow_runs(
        HELLO,
        [workflow_run(1, 1), workflow_run(2, 2), workflow_run(3, 3)],
        runs_state,
        replace=False,
    )
    cache.write_workflow_runs(
        SPOON,
        [workflow_run(1, 1, repo_name=SPOON)],
        state(SPOON, resource='workflow_runs'),
        replace=False,
    )
    cache.write_workflow_runs(HELLO, [], runs_state, replace=False, gone={1})
    assert [run.id for run in cache.read_workflow_runs(HELLO, None)] == [2, 3]
    cache.write_workflow_runs(HELLO, [workflow_run(4, 4)], runs_state, replace=True, gone={2, 4})
    assert [run.id for run in cache.read_workflow_runs(HELLO, None)] == []
    assert [run.id for run in cache.read_workflow_runs(SPOON, None)] == [1]


def test_read_workflow_runs_with_since_keeps_exactly_the_rows_at_or_after_it(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    runs = [workflow_run(10, 3), workflow_run(11, 1), workflow_run(12, 2)]
    cache.write_workflow_runs(HELLO, runs, state(resource='workflow_runs'), replace=False)
    since = T0 + datetime.timedelta(hours=2)
    assert [run.id for run in cache.read_workflow_runs(HELLO, since)] == [12, 10]
    assert [run.id for run in cache.read_workflow_runs(HELLO, None)] == [11, 12, 10]


def test_unfinished_runs_lists_queued_and_in_progress_ids_ascending(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    runs = [
        workflow_run(9, 1, status='in_progress', conclusion=None),
        workflow_run(3, 2),
        workflow_run(5, 3, status='queued', conclusion=None),
        workflow_run(7, 4, repo_name=SPOON, status='queued', conclusion=None),
    ]
    cache.write_workflow_runs(HELLO, runs[:3], state(resource='workflow_runs'), replace=False)
    cache.write_workflow_runs(
        SPOON, runs[3:], state(SPOON, resource='workflow_runs'), replace=False
    )
    assert cache.unfinished_runs(HELLO) == [5, 9]
    assert cache.unfinished_runs('octocat/none') == []


def test_the_sync_state_probe_and_the_repo_release_probe_round_trip(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    cache.write_releases(HELLO, [], state(resource='releases', probe='2 2026-10-01T10:00:00+00:00'))
    stored = cache.sync_state(HELLO, 'releases')
    assert stored is not None
    assert stored.probe == '2 2026-10-01T10:00:00+00:00'
    cache.write_commits(HELLO, [], state(), replace=False)
    commits_state = cache.sync_state(HELLO, 'commits')
    assert commits_state is not None
    assert commits_state.probe is None
    probed = repo(releases_count=3, releases_updated_at=T0 + datetime.timedelta(hours=4))
    cache.upsert_repos('octocat', [probed, repo(SPOON)], complete=True)
    rows = cache.read_repos(wambatic.fetch.base.Subject('user', 'octocat'))
    assert rows == [probed, repo(SPOON)]
    assert (rows[1].releases_count, rows[1].releases_updated_at) == (0, None)


def test_a_release_or_run_or_state_for_another_repo_raises_and_writes_nothing(
    cache: wambatic.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    with pytest.raises(ValueError, match='must belong to'):
        cache.write_releases(
            HELLO, [release('v1'), release('v2', repo_name=SPOON)], state(resource='releases')
        )
    with pytest.raises(ValueError, match='must belong to'):
        cache.write_releases(HELLO, [release('v1')], state(SPOON, resource='releases'))
    for replace in (False, True):
        with pytest.raises(ValueError, match='must belong to'):
            cache.write_workflow_runs(
                HELLO,
                [workflow_run(1), workflow_run(2, repo_name=SPOON)],
                state(resource='workflow_runs'),
                replace=replace,
            )
        with pytest.raises(ValueError, match='must belong to'):
            cache.write_workflow_runs(
                HELLO, [workflow_run(1)], state(SPOON, resource='workflow_runs'), replace=replace
            )
    assert table_rows(cache_path, 'releases') == []
    assert table_rows(cache_path, 'workflow_runs') == []
    for resource in ('releases', 'workflow_runs'):
        assert cache.sync_state(HELLO, resource) is None
        assert cache.sync_state(SPOON, resource) is None


def test_a_failure_mid_write_of_runs_leaves_rows_and_state_unchanged(
    cache: wambatic.fetch.cache.Cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = state(resource='workflow_runs', hours=1)
    cache.write_workflow_runs(HELLO, [workflow_run(1, 1)], old, replace=False)

    def fail(new_state: wambatic.fetch.base.SyncState) -> None:
        raise sqlite3.OperationalError('disk full')

    monkeypatch.setattr(cache, 'put_state', fail)
    with pytest.raises(sqlite3.OperationalError):
        cache.write_workflow_runs(
            HELLO,
            [workflow_run(2, 2)],
            state(resource='workflow_runs', hours=2),
            replace=True,
            gone={1},
        )
    assert [run.id for run in cache.read_workflow_runs(HELLO, None)] == [1]
    assert cache.sync_state(HELLO, 'workflow_runs') == old


# Stars and forks


def test_a_repo_with_counts_and_languages_round_trips(cache: wambatic.fetch.cache.Cache) -> None:
    popular = repo(
        stargazer_count=12,
        fork_count=3,
        watcher_count=5,
        languages=(('Python', 900), ('Ünïcode', 80), ('C++', 20)),
        languages_size=1500,
    )
    bare = repo(SPOON)
    cache.upsert_repos('octocat', [popular, bare], complete=True)
    rows = cache.read_repos(wambatic.fetch.base.Subject('user', 'octocat'))
    assert rows == [popular, bare]
    assert rows[1].languages == ()
    assert (rows[1].stargazer_count, rows[1].languages_size) == (0, 0)


def test_star_events_round_trip_oldest_first_then_user_id(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    stars = [star_event('U_b', 2), star_event('U_z', 1), star_event('U_a', 1)]
    cache.write_star_events(HELLO, stars, state(resource='star_events'), replace=False)
    assert [star.user_id for star in cache.read_star_events(HELLO)] == ['U_a', 'U_z', 'U_b']
    assert cache.read_star_events(HELLO)[0] == star_event('U_a', 1)


def test_forks_round_trip_oldest_first_then_id(cache: wambatic.fetch.cache.Cache) -> None:
    cache.write_forks(
        HELLO, [fork(9, 2), fork(8, 1), fork(7, 1)], state(resource='forks'), replace=False
    )
    assert cache.read_forks(HELLO) == [fork(7, 1), fork(8, 1), fork(9, 2)]


def test_write_star_events_replace_controls_unlisted_rows_and_leaves_other_repos(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    cache.write_star_events(
        SPOON,
        [star_event('U_s', repo_name=SPOON)],
        state(SPOON, resource='star_events'),
        replace=False,
    )
    old = [star_event('U_1'), star_event('U_2', 1)]
    cache.write_star_events(HELLO, old, state(resource='star_events'), replace=False)
    written = cache.write_star_events(
        HELLO,
        [star_event('U_3', 2), star_event('U_2', 5)],
        state(resource='star_events'),
        replace=False,
    )
    assert written == 2
    assert [(star.user_id, star.starred_at) for star in cache.read_star_events(HELLO)] == [
        ('U_1', T0),
        ('U_3', T0 + datetime.timedelta(hours=2)),
        ('U_2', T0 + datetime.timedelta(hours=5)),
    ]
    cache.write_star_events(
        HELLO, [star_event('U_3', 2)], state(resource='star_events'), replace=True
    )
    assert [star.user_id for star in cache.read_star_events(HELLO)] == ['U_3']
    assert [star.user_id for star in cache.read_star_events(SPOON)] == ['U_s']


def test_write_forks_replace_controls_unlisted_rows_and_leaves_other_repos(
    cache: wambatic.fetch.cache.Cache,
) -> None:
    cache.write_forks(
        SPOON, [fork(1, repo_name=SPOON)], state(SPOON, resource='forks'), replace=False
    )
    cache.write_forks(HELLO, [fork(10), fork(11, 1)], state(resource='forks'), replace=False)
    cache.write_forks(HELLO, [fork(12, 2)], state(resource='forks'), replace=False)
    assert [item.id for item in cache.read_forks(HELLO)] == [10, 11, 12]
    cache.write_forks(HELLO, [fork(11, 1)], state(resource='forks'), replace=True)
    assert [item.id for item in cache.read_forks(HELLO)] == [11]
    assert [item.id for item in cache.read_forks(SPOON)] == [1]


def test_a_star_or_fork_or_state_for_another_repo_raises_and_writes_nothing(
    cache: wambatic.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    for replace in (False, True):
        with pytest.raises(ValueError, match='must belong to'):
            cache.write_star_events(
                HELLO,
                [star_event('U_1'), star_event('U_2', repo_name=SPOON)],
                state(resource='star_events'),
                replace=replace,
            )
        with pytest.raises(ValueError, match='must belong to'):
            cache.write_star_events(
                HELLO, [star_event('U_1')], state(SPOON, resource='star_events'), replace=replace
            )
        with pytest.raises(ValueError, match='must belong to'):
            cache.write_forks(
                HELLO,
                [fork(1), fork(2, repo_name=SPOON)],
                state(resource='forks'),
                replace=replace,
            )
        with pytest.raises(ValueError, match='must belong to'):
            cache.write_forks(HELLO, [fork(1)], state(SPOON, resource='forks'), replace=replace)
    assert table_rows(cache_path, 'star_events') == []
    assert table_rows(cache_path, 'forks') == []
    for resource in ('star_events', 'forks'):
        assert cache.sync_state(HELLO, resource) is None
        assert cache.sync_state(SPOON, resource) is None


def test_a_failure_mid_write_of_stars_leaves_rows_and_state_unchanged(
    cache: wambatic.fetch.cache.Cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = state(resource='star_events', hours=1, probe='1')
    cache.write_star_events(HELLO, [star_event('U_1')], old, replace=False)

    def fail(new_state: wambatic.fetch.base.SyncState) -> None:
        raise sqlite3.OperationalError('disk full')

    monkeypatch.setattr(cache, 'put_state', fail)
    with pytest.raises(sqlite3.OperationalError):
        cache.write_star_events(
            HELLO, [star_event('U_2')], state(resource='star_events', hours=2), replace=True
        )
    assert [star.user_id for star in cache.read_star_events(HELLO)] == ['U_1']
    assert cache.sync_state(HELLO, 'star_events') == old


def test_inspect_cache_counts_star_events_and_forks(
    cache: wambatic.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    cache.write_star_events(
        HELLO, [star_event('U_1'), star_event('U_2')], state(resource='star_events'), replace=False
    )
    cache.write_forks(HELLO, [fork(1)], state(resource='forks'), replace=False)
    info = wambatic.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert (info.star_events, info.forks) == (2, 1)


# ETags


def test_etag_round_trip(cache: wambatic.fetch.cache.Cache) -> None:
    assert cache.etag('/repos/x?page=1') is None
    cache.store_etag('/repos/x?page=1', '"abc"', {'a': [1, 2], 'b': None})
    assert cache.etag('/repos/x?page=1') == ('"abc"', {'a': [1, 2], 'b': None})
    cache.store_etag('/repos/x?page=1', '"def"', [])
    assert cache.etag('/repos/x?page=1') == ('"def"', [])


def test_inspect_cache_of_a_missing_path_is_none_and_creates_nothing(
    cache_path: pathlib.Path,
) -> None:
    assert wambatic.fetch.cache.inspect_cache(cache_path) is None
    assert not cache_path.exists()
    assert not cache_path.parent.exists()


def test_inspect_cache_reports_counts_identity_and_latest_sync(
    stats_cache_path: pathlib.Path,
) -> None:
    path = stats_cache_path
    info = wambatic.fetch.cache.inspect_cache(path)
    assert info is not None
    assert info.path == path
    assert info.repos == len(tests.fixtures.stats.REPOS)
    assert info.commits == len(tests.fixtures.stats.COMMITS)
    assert info.identity == wambatic.fetch.cache.expected_identity()
    assert info.differences == {}
    assert info.version_override_at is None
    assert info.last_synced_at == tests.fixtures.stats.BETA_SYNCED_AT
    assert info.size_bytes >= path.stat().st_size


def test_inspect_cache_counts_only_repos_not_marked_missing(
    cache: wambatic.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    cache.upsert_repos('octocat', [repo(HELLO), repo(SPOON)], complete=True)
    cache.upsert_repos('octocat', [repo(HELLO)], complete=True)
    info = wambatic.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert info.repos == 1


def write_other_schema_version(path: pathlib.Path) -> None:
    wambatic.fetch.cache.Cache.open(path).close()
    connection = sqlite3.connect(path)
    with connection:
        connection.execute("UPDATE meta SET value = '0' WHERE key = 'schema_version'")
    connection.close()


def test_inspect_cache_reads_a_cache_that_open_refuses_and_changes_nothing(
    cache_path: pathlib.Path,
) -> None:
    write_other_schema_version(cache_path)

    def meta() -> list[tuple[str, str]]:
        connection = sqlite3.connect(cache_path)
        try:
            return connection.execute('SELECT key, value FROM meta ORDER BY key').fetchall()
        finally:
            connection.close()

    before = meta()
    info = wambatic.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert info.differences == {'schema_version': ('0', str(wambatic.fetch.cache.SCHEMA_VERSION))}
    assert info.version_override_at is None
    with pytest.raises(wambatic.fetch.errors.CacheVersionError):
        wambatic.fetch.cache.Cache.open(cache_path).close()
    assert meta() == before


def test_inspect_cache_reports_the_version_override_time(cache_path: pathlib.Path) -> None:
    write_other_schema_version(cache_path)
    wambatic.fetch.cache.Cache.open(cache_path, ignore_version=True).close()
    info = wambatic.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert info.version_override_at is not None
    assert wambatic.fetch.cache.OVERRIDE_KEY not in info.identity


def test_inspect_cache_counts_pull_requests_and_issues(
    cache: wambatic.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    cache.write_pull_requests(
        HELLO, [pull_request(1), pull_request(2)], state(resource='pull_requests'), replace=False
    )
    cache.write_issues(HELLO, [issue(1)], state(resource='issues'), replace=False)
    info = wambatic.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert (info.pull_requests, info.issues) == (2, 1)


def test_inspect_cache_counts_releases_and_runs(
    cache: wambatic.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    cache.write_releases(HELLO, [release('v1'), release('v2', 1)], state(resource='releases'))
    cache.write_workflow_runs(
        HELLO,
        [workflow_run(1), workflow_run(2, 1), workflow_run(3, 2)],
        state(resource='workflow_runs'),
        replace=False,
    )
    info = wambatic.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert (info.releases, info.workflow_runs) == (2, 3)


def test_inspect_cache_gives_zero_pull_requests_and_issues_on_a_file_that_lacks_the_tables(
    cache_path: pathlib.Path,
) -> None:
    cache_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(cache_path)
    with connection:
        connection.executescript(
            'CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);'
            "INSERT INTO meta VALUES ('schema_version', '1');"
        )
    connection.close()
    info = wambatic.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert (info.pull_requests, info.issues) == (0, 0)
    assert (info.releases, info.workflow_runs) == (0, 0)
    assert (info.star_events, info.forks) == (0, 0)


def test_inspect_cache_of_an_empty_sqlite_file_has_zero_counts_and_adds_no_tables(
    cache_path: pathlib.Path,
) -> None:
    cache_path.parent.mkdir(parents=True)
    sqlite3.connect(cache_path).close()
    info = wambatic.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert (info.repos, info.commits, info.last_synced_at) == (0, 0, None)
    assert info.identity == {}
    assert set(info.differences) == set(wambatic.fetch.cache.expected_identity())
    connection = sqlite3.connect(cache_path)
    try:
        assert connection.execute('SELECT COUNT(*) FROM sqlite_master').fetchone() == (0,)
    finally:
        connection.close()


def test_clear_cache_removes_the_file_and_its_wal_and_shm_files(cache_path: pathlib.Path) -> None:
    cache = wambatic.fetch.cache.Cache.open(cache_path)
    cache.upsert_repos('octocat', [repo(HELLO)], complete=True)
    wal = cache_path.with_name(cache_path.name + '-wal')
    shm = cache_path.with_name(cache_path.name + '-shm')
    assert wal.exists()
    assert shm.exists()
    removed = wambatic.fetch.cache.clear_cache(cache_path)
    assert removed == [cache_path, wal, shm]
    assert not any(path.exists() for path in removed)
    assert wambatic.fetch.cache.clear_cache(cache_path) == []
    cache.close()
