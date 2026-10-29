import datetime
import pathlib
import sqlite3
import typing

import hypothesis
import hypothesis.strategies
import pytest

import gitstat.fetch.base
import gitstat.fetch.cache
import gitstat.fetch.errors
import gitstat.fetch.queries
import gitstat.version
import tests.fixtures.stats

UTC = datetime.UTC
T0 = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
HELLO = 'octocat/Hello-World'
SPOON = 'octocat/Spoon-Knife'


@pytest.fixture
def cache_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / 'nested' / 'cache.sqlite3'


@pytest.fixture
def cache(cache_path: pathlib.Path) -> typing.Iterator[gitstat.fetch.cache.Cache]:
    opened = gitstat.fetch.cache.Cache.open(cache_path)
    yield opened
    opened.close()


def repo(name: str = HELLO, **changes: object) -> gitstat.fetch.base.Repo:
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
    return gitstat.fetch.base.Repo(**fields)  # type: ignore[arg-type]


def commit(
    oid: str, hours: int = 0, repo_name: str = HELLO, **changes: object
) -> gitstat.fetch.base.Commit:
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
    return gitstat.fetch.base.Commit(**fields)  # type: ignore[arg-type]


def state(
    repo_name: str = HELLO, head: str | None = 'a' * 40, hours: int = 0
) -> gitstat.fetch.base.SyncState:
    return gitstat.fetch.base.SyncState(
        repo=repo_name,
        resource='commits',
        watermark=None,
        head_oid=head,
        pushed_at=T0,
        updated_at=T0 + datetime.timedelta(hours=1),
        synced_at=T0 + datetime.timedelta(hours=hours),
        full_synced_at=T0,
    )


def table_rows(path: pathlib.Path, table: str) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(f'SELECT * FROM {table}').fetchall()
    finally:
        connection.close()


# Open, schema and identity


def test_new_file_is_wal_with_the_expected_identity(cache_path: pathlib.Path) -> None:
    opened = gitstat.fetch.cache.Cache.open(cache_path)
    try:
        assert opened.identity() == gitstat.fetch.cache.expected_identity()
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


def test_identity_has_versions_and_a_hash_per_query(cache: gitstat.fetch.cache.Cache) -> None:
    identity = cache.identity()
    assert identity['schema_version'] == str(gitstat.fetch.cache.SCHEMA_VERSION)
    assert identity['gitstat_version'] == gitstat.version.VERSION
    assert {'query:OWNER_REPOSITORIES', 'query:COMMIT_HISTORY'} <= identity.keys()
    assert len(identity['query:COMMIT_NODES']) == 64


def test_reopening_succeeds(cache_path: pathlib.Path) -> None:
    gitstat.fetch.cache.Cache.open(cache_path).close()
    gitstat.fetch.cache.Cache.open(cache_path).close()


def test_changed_schema_version_raises(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gitstat.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.setattr(gitstat.fetch.cache, 'SCHEMA_VERSION', 2)
    with pytest.raises(gitstat.fetch.errors.CacheVersionError) as caught:
        gitstat.fetch.cache.Cache.open(cache_path)
    assert caught.value.differences == {'schema_version': ('1', '2')}
    assert 'schema_version: cache has 1, this gitstat has 2' in str(caught.value)
    assert 'gitstat cache clear' in str(caught.value)
    assert '--ignore-cache-version' in str(caught.value)


def test_changed_gitstat_version_raises(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gitstat.fetch.cache.Cache.open(cache_path).close()
    recorded = gitstat.version.VERSION
    monkeypatch.setattr(gitstat.version, 'VERSION', '9.9.9')
    with pytest.raises(gitstat.fetch.errors.CacheVersionError) as caught:
        gitstat.fetch.cache.Cache.open(cache_path)
    assert caught.value.differences == {'gitstat_version': (recorded, '9.9.9')}


def test_changed_query_text_raises_naming_the_query(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gitstat.fetch.cache.Cache.open(cache_path).close()
    recorded = gitstat.fetch.cache.expected_identity()['query:COMMIT_NODES']
    monkeypatch.setattr(gitstat.fetch.queries, 'COMMIT_NODES', 'query { changed }')
    with pytest.raises(gitstat.fetch.errors.CacheVersionError) as caught:
        gitstat.fetch.cache.Cache.open(cache_path)
    (key, (old, new)), *rest = caught.value.differences.items()
    assert (key, old, rest) == ('query:COMMIT_NODES', recorded, [])
    assert new != recorded


def test_adding_a_query_changes_the_identity_without_editing_the_cache_module(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gitstat.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.setattr(gitstat.fetch.queries, 'EXTRA_QUERY', 'query { extra }', raising=False)
    with pytest.raises(gitstat.fetch.errors.CacheVersionError) as caught:
        gitstat.fetch.cache.Cache.open(cache_path)
    assert list(caught.value.differences) == ['query:EXTRA_QUERY']
    assert caught.value.differences['query:EXTRA_QUERY'][0] is None


def test_a_query_removed_from_the_code_raises(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gitstat.fetch.queries, 'EXTRA_QUERY', 'query { extra }', raising=False)
    gitstat.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.delattr(gitstat.fetch.queries, 'EXTRA_QUERY')
    with pytest.raises(gitstat.fetch.errors.CacheVersionError) as caught:
        gitstat.fetch.cache.Cache.open(cache_path)
    assert caught.value.differences['query:EXTRA_QUERY'][1] is None
    assert 'this gitstat has nothing' in str(caught.value)


def test_a_mismatch_closes_the_connection(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gitstat.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.setattr(gitstat.fetch.cache, 'SCHEMA_VERSION', 2)
    connections: list[sqlite3.Connection] = []
    connect = sqlite3.connect

    def spy(*args: object, **kwargs: object) -> sqlite3.Connection:
        connections.append(connect(*args, **kwargs))  # type: ignore[call-overload]
        return connections[-1]

    monkeypatch.setattr(sqlite3, 'connect', spy)
    with pytest.raises(gitstat.fetch.errors.CacheVersionError):
        gitstat.fetch.cache.Cache.open(cache_path)
    (connection,) = connections
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connection.execute('SELECT 1')


def test_ignore_version_opens_and_records_the_override(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gitstat.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.setattr(gitstat.fetch.cache, 'SCHEMA_VERSION', 2)
    opened = gitstat.fetch.cache.Cache.open(cache_path, ignore_version=True)
    try:
        assert 'version_override_at' not in opened.identity()
        assert opened.identity()['schema_version'] == '1'
    finally:
        opened.close()
    keys = {row[0] for row in table_rows(cache_path, 'meta')}
    assert 'version_override_at' in keys
    with pytest.raises(gitstat.fetch.errors.CacheVersionError):
        gitstat.fetch.cache.Cache.open(cache_path)


def test_ignore_version_on_a_matching_cache_records_nothing(cache_path: pathlib.Path) -> None:
    gitstat.fetch.cache.Cache.open(cache_path).close()
    gitstat.fetch.cache.Cache.open(cache_path, ignore_version=True).close()
    assert 'version_override_at' not in {row[0] for row in table_rows(cache_path, 'meta')}


def test_version_override_at_is_none_for_a_matching_cache(
    cache: gitstat.fetch.cache.Cache,
) -> None:
    assert cache.version_override_at() is None


def test_version_override_at_is_the_recorded_time_after_an_override(
    cache_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gitstat.fetch.cache.Cache.open(cache_path).close()
    monkeypatch.setattr(gitstat.fetch.cache, 'SCHEMA_VERSION', 2)
    before = datetime.datetime.now(UTC)
    opened = gitstat.fetch.cache.Cache.open(cache_path, ignore_version=True)
    try:
        recorded = opened.version_override_at()
    finally:
        opened.close()
    assert recorded is not None
    assert before <= gitstat.fetch.cache.from_text(recorded) <= datetime.datetime.now(UTC)


# Repos


def test_repos_round_trip(cache: gitstat.fetch.cache.Cache) -> None:
    empty = repo('octocat/Empty', default_branch=None, head_oid=None, pushed_at=None)
    stored = [repo(), empty, repo(SPOON, is_fork=True, is_archived=True)]
    cache.upsert_repos('octocat', stored, complete=True)
    read = cache.read_repos(gitstat.fetch.base.Subject('user', 'octocat'))
    assert read == sorted(stored, key=lambda item: item.name_with_owner)


def test_read_repos_of_a_repo_subject_is_its_one_row(cache: gitstat.fetch.cache.Cache) -> None:
    cache.upsert_repos('octocat', [repo(), repo(SPOON)], complete=True)
    subject = gitstat.fetch.base.Subject('repo', 'octocat', 'Hello-World')
    assert cache.read_repos(subject) == [repo()]
    assert cache.read_repos(gitstat.fetch.base.Subject('repo', 'octocat', 'nope')) == []


def test_owner_lookup_ignores_case(cache: gitstat.fetch.cache.Cache) -> None:
    cache.upsert_repos('OctoCat', [repo()], complete=True)
    assert cache.read_repos(gitstat.fetch.base.Subject('org', 'OCTOCAT')) == [repo()]
    assert cache.read_repos(gitstat.fetch.base.Subject('repo', 'OctoCat', 'hello-world')) == [
        repo()
    ]


def test_complete_listing_marks_absent_repos_missing_and_keeps_their_commits(
    cache: gitstat.fetch.cache.Cache,
) -> None:
    cache.upsert_repos('octocat', [repo(), repo(SPOON)], complete=True)
    cache.write_commits(SPOON, [commit('s1', repo_name=SPOON)], state(SPOON), replace=True)
    cache.upsert_repos('octocat', [repo()], complete=True)
    by_name = {
        item.name_with_owner: item
        for item in cache.read_repos(gitstat.fetch.base.Subject('user', 'octocat'))
    }
    assert not by_name[HELLO].missing
    assert by_name[SPOON].missing
    assert [c.oid for c in cache.read_commits(SPOON, None, None)] == ['s1']
    cache.upsert_repos('octocat', [repo(), repo(SPOON)], complete=True)
    assert not cache.read_repos(gitstat.fetch.base.Subject('repo', 'octocat', 'Spoon-Knife'))[
        0
    ].missing


def test_incomplete_listing_leaves_other_repos_alone(cache: gitstat.fetch.cache.Cache) -> None:
    cache.upsert_repos('octocat', [repo(), repo(SPOON)], complete=True)
    cache.upsert_repos('octocat', [repo()], complete=False)
    rows = cache.read_repos(gitstat.fetch.base.Subject('user', 'octocat'))
    assert [item.missing for item in rows] == [False, False]


def test_complete_listing_leaves_other_owners_alone(cache: gitstat.fetch.cache.Cache) -> None:
    cache.upsert_repos('octocat', [repo()], complete=True)
    cache.upsert_repos('github', [repo('github/docs')], complete=True)
    assert not cache.read_repos(gitstat.fetch.base.Subject('user', 'octocat'))[0].missing


def test_naive_times_are_refused(cache: gitstat.fetch.cache.Cache) -> None:
    with pytest.raises(ValueError, match='timezone-aware'):
        cache.upsert_repos(
            'octocat', [repo(updated_at=datetime.datetime(2026, 1, 1))], complete=False
        )


# Commits and sync state


def test_state_round_trip(cache: gitstat.fetch.cache.Cache) -> None:
    assert cache.sync_state(HELLO, 'commits') is None
    written = state()
    cache.write_commits(HELLO, [], written, replace=False)
    assert cache.sync_state(HELLO, 'commits') == written
    assert cache.sync_state(HELLO, 'issues') is None


def test_state_with_no_head_or_pushed_at_round_trips(cache: gitstat.fetch.cache.Cache) -> None:
    written = gitstat.fetch.base.SyncState(HELLO, 'commits', None, None, None, T0, T0, T0)
    cache.write_commits(HELLO, [], written, replace=False)
    assert cache.sync_state(HELLO, 'commits') == written


def test_commit_upsert_by_oid_is_idempotent(cache: gitstat.fetch.cache.Cache) -> None:
    commits = [commit('c1', 1), commit('c2', 2)]
    cache.write_commits(HELLO, commits, state(), replace=False)
    cache.write_commits(HELLO, commits, state(), replace=False)
    assert cache.read_commits(HELLO, None, None) == commits


def test_upsert_replaces_a_commit_with_the_same_oid(cache: gitstat.fetch.cache.Cache) -> None:
    cache.write_commits(HELLO, [commit('c1', additions=1)], state(), replace=False)
    cache.write_commits(HELLO, [commit('c1', additions=9)], state(), replace=False)
    assert [c.additions for c in cache.read_commits(HELLO, None, None)] == [9]


def test_write_commits_returns_the_rows_written(cache: gitstat.fetch.cache.Cache) -> None:
    assert cache.write_commits(HELLO, [commit('c1'), commit('c2')], state(), replace=False) == 2


def test_replace_removes_commits_not_in_the_new_list(cache: gitstat.fetch.cache.Cache) -> None:
    cache.write_commits(HELLO, [commit('c1', 1), commit('c2', 2)], state(), replace=False)
    cache.write_commits(SPOON, [commit('s1', 1, SPOON)], state(SPOON), replace=False)
    cache.write_commits(HELLO, [commit('c2', 2), commit('c3', 3)], state(), replace=True)
    assert [c.oid for c in cache.read_commits(HELLO, None, None)] == ['c2', 'c3']
    assert [c.oid for c in cache.read_commits(SPOON, None, None)] == ['s1']


def test_commits_of_another_repo_are_refused(cache: gitstat.fetch.cache.Cache) -> None:
    with pytest.raises(ValueError, match='must belong to'):
        cache.write_commits(HELLO, [commit('s1', repo_name=SPOON)], state(), replace=False)
    with pytest.raises(ValueError, match='must belong to'):
        cache.write_commits(HELLO, [], state(SPOON), replace=False)


def test_a_failure_mid_write_leaves_rows_and_state_unchanged(
    cache: gitstat.fetch.cache.Cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = state(head='a' * 40)
    cache.write_commits(HELLO, [commit('c1', 1)], old, replace=False)

    def fail(new_state: gitstat.fetch.base.SyncState) -> None:
        raise sqlite3.OperationalError('disk full')

    monkeypatch.setattr(cache, 'put_state', fail)
    for replace in (False, True):
        with pytest.raises(sqlite3.OperationalError):
            cache.write_commits(HELLO, [commit('c2', 2)], state(head='b' * 40), replace=replace)
        assert [c.oid for c in cache.read_commits(HELLO, None, None)] == ['c1']
        assert cache.sync_state(HELLO, 'commits') == old


def test_read_commits_bounds_are_half_open_and_ordered(cache: gitstat.fetch.cache.Cache) -> None:
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
    cache: gitstat.fetch.cache.Cache,
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
        gitstat.fetch.base.Commit,
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
    commits: list[gitstat.fetch.base.Commit], tmp_path_factory: pytest.TempPathFactory
) -> None:
    opened = gitstat.fetch.cache.Cache.open(tmp_path_factory.mktemp('cache') / 'cache.sqlite3')
    try:
        opened.write_commits(HELLO, commits, state(), replace=False)
        last = {c.oid: c for c in commits}
        read = opened.read_commits(HELLO, None, None)
        assert sorted(read, key=lambda c: c.oid) == sorted(last.values(), key=lambda c: c.oid)
        assert read == sorted(read, key=lambda c: (c.authored_at, c.oid))
    finally:
        opened.close()


# ETags


def test_etag_round_trip(cache: gitstat.fetch.cache.Cache) -> None:
    assert cache.etag('/repos/x?page=1') is None
    cache.store_etag('/repos/x?page=1', '"abc"', {'a': [1, 2], 'b': None})
    assert cache.etag('/repos/x?page=1') == ('"abc"', {'a': [1, 2], 'b': None})
    cache.store_etag('/repos/x?page=1', '"def"', [])
    assert cache.etag('/repos/x?page=1') == ('"def"', [])


def test_inspect_cache_of_a_missing_path_is_none_and_creates_nothing(
    cache_path: pathlib.Path,
) -> None:
    assert gitstat.fetch.cache.inspect_cache(cache_path) is None
    assert not cache_path.exists()
    assert not cache_path.parent.exists()


def test_inspect_cache_reports_counts_identity_and_latest_sync(
    stats_cache_path: pathlib.Path,
) -> None:
    path = stats_cache_path
    info = gitstat.fetch.cache.inspect_cache(path)
    assert info is not None
    assert info.path == path
    assert info.repos == len(tests.fixtures.stats.REPOS)
    assert info.commits == len(tests.fixtures.stats.COMMITS)
    assert info.identity == gitstat.fetch.cache.expected_identity()
    assert info.differences == {}
    assert info.version_override_at is None
    assert info.last_synced_at == tests.fixtures.stats.BETA_SYNCED_AT
    assert info.size_bytes >= path.stat().st_size


def test_inspect_cache_counts_only_repos_not_marked_missing(
    cache: gitstat.fetch.cache.Cache, cache_path: pathlib.Path
) -> None:
    cache.upsert_repos('octocat', [repo(HELLO), repo(SPOON)], complete=True)
    cache.upsert_repos('octocat', [repo(HELLO)], complete=True)
    info = gitstat.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert info.repos == 1


def write_other_schema_version(path: pathlib.Path) -> None:
    gitstat.fetch.cache.Cache.open(path).close()
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
    info = gitstat.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert info.differences == {'schema_version': ('0', str(gitstat.fetch.cache.SCHEMA_VERSION))}
    assert info.version_override_at is None
    with pytest.raises(gitstat.fetch.errors.CacheVersionError):
        gitstat.fetch.cache.Cache.open(cache_path).close()
    assert meta() == before


def test_inspect_cache_reports_the_version_override_time(cache_path: pathlib.Path) -> None:
    write_other_schema_version(cache_path)
    gitstat.fetch.cache.Cache.open(cache_path, ignore_version=True).close()
    info = gitstat.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert info.version_override_at is not None
    assert gitstat.fetch.cache.OVERRIDE_KEY not in info.identity


def test_inspect_cache_of_an_empty_sqlite_file_has_zero_counts_and_adds_no_tables(
    cache_path: pathlib.Path,
) -> None:
    cache_path.parent.mkdir(parents=True)
    sqlite3.connect(cache_path).close()
    info = gitstat.fetch.cache.inspect_cache(cache_path)
    assert info is not None
    assert (info.repos, info.commits, info.last_synced_at) == (0, 0, None)
    assert info.identity == {}
    assert set(info.differences) == set(gitstat.fetch.cache.expected_identity())
    connection = sqlite3.connect(cache_path)
    try:
        assert connection.execute('SELECT COUNT(*) FROM sqlite_master').fetchone() == (0,)
    finally:
        connection.close()


def test_clear_cache_removes_the_file_and_its_wal_and_shm_files(cache_path: pathlib.Path) -> None:
    cache = gitstat.fetch.cache.Cache.open(cache_path)
    cache.upsert_repos('octocat', [repo(HELLO)], complete=True)
    wal = cache_path.with_name(cache_path.name + '-wal')
    shm = cache_path.with_name(cache_path.name + '-shm')
    assert wal.exists()
    assert shm.exists()
    removed = gitstat.fetch.cache.clear_cache(cache_path)
    assert removed == [cache_path, wal, shm]
    assert not any(path.exists() for path in removed)
    assert gitstat.fetch.cache.clear_cache(cache_path) == []
    cache.close()
