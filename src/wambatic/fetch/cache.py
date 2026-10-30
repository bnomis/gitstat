import collections.abc
import dataclasses
import datetime
import hashlib
import json
import pathlib
import sqlite3
import threading
import typing

import wambatic.fetch.base
import wambatic.fetch.errors
import wambatic.fetch.queries
import wambatic.version

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS repos (
    name_with_owner TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    default_branch TEXT,
    head_oid TEXT,
    is_archived INTEGER NOT NULL,
    is_fork INTEGER NOT NULL,
    pushed_at TEXT,
    updated_at TEXT NOT NULL,
    pull_requests_updated_at TEXT,
    issues_updated_at TEXT,
    missing INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS repos_owner ON repos (owner);
CREATE TABLE IF NOT EXISTS commits (
    repo TEXT NOT NULL,
    oid TEXT NOT NULL,
    authored_at TEXT NOT NULL,
    author_login TEXT,
    additions INTEGER NOT NULL,
    deletions INTEGER NOT NULL,
    is_merge INTEGER NOT NULL,
    PRIMARY KEY (repo, oid)
);
CREATE INDEX IF NOT EXISTS commits_repo_authored_at ON commits (repo, authored_at);
CREATE TABLE IF NOT EXISTS pull_requests (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    author_login TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    merged_at TEXT,
    closed_at TEXT,
    first_review_at TEXT,
    additions INTEGER NOT NULL,
    deletions INTEGER NOT NULL,
    PRIMARY KEY (repo, number)
);
CREATE INDEX IF NOT EXISTS pull_requests_repo_updated_at ON pull_requests (repo, updated_at);
CREATE TABLE IF NOT EXISTS issues (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    author_login TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    PRIMARY KEY (repo, number)
);
CREATE INDEX IF NOT EXISTS issues_repo_updated_at ON issues (repo, updated_at);
CREATE TABLE IF NOT EXISTS etags (url TEXT PRIMARY KEY, etag TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_state (
    repo TEXT NOT NULL,
    resource TEXT NOT NULL,
    watermark TEXT,
    head_oid TEXT,
    pushed_at TEXT,
    updated_at TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    full_synced_at TEXT NOT NULL,
    PRIMARY KEY (repo, resource)
);
"""
OVERRIDE_KEY = 'version_override_at'
COMMIT_COLUMNS = (
    'repo',
    'oid',
    'authored_at',
    'author_login',
    'additions',
    'deletions',
    'is_merge',
)
PULL_REQUEST_COLUMNS = (
    'repo',
    'number',
    'author_login',
    'created_at',
    'updated_at',
    'merged_at',
    'closed_at',
    'first_review_at',
    'additions',
    'deletions',
)
ISSUE_COLUMNS = ('repo', 'number', 'author_login', 'created_at', 'updated_at', 'closed_at')


def expected_identity() -> dict[str, str]:
    """What a cache written by the running code records in `meta`."""
    identity = {
        'schema_version': str(SCHEMA_VERSION),
        'wambatic_version': wambatic.version.VERSION,
    }
    for name, value in vars(wambatic.fetch.queries).items():
        if name.isupper() and isinstance(value, str):
            identity[f'query:{name}'] = hashlib.sha256(value.encode()).hexdigest()
    return identity


def identity_differences(
    recorded: dict[str, str], expected: dict[str, str]
) -> dict[str, tuple[str | None, str | None]]:
    """Each key whose recorded and expected values differ, as (recorded, expected)."""
    return {
        key: (recorded.get(key), expected.get(key))
        for key in sorted(recorded.keys() | expected.keys())
        if recorded.get(key) != expected.get(key)
    }


def to_text(value: datetime.datetime) -> str:
    """ISO 8601 UTC at one fixed width, so text order is time order."""
    if value.tzinfo is None:
        raise ValueError('cache times must be timezone-aware')
    return value.astimezone(datetime.UTC).isoformat(timespec='microseconds')


def optional_to_text(value: datetime.datetime | None) -> str | None:
    return None if value is None else to_text(value)


def from_text(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


def optional_from_text(value: str | None) -> datetime.datetime | None:
    return None if value is None else from_text(value)


class Record(typing.Protocol):
    @property
    def repo(self) -> str: ...


def repo_from_row(row: tuple[object, ...]) -> wambatic.fetch.base.Repo:
    name, branch, head, archived, fork, pushed_at, updated_at, pulls_at, issues_at, missing = row
    return wambatic.fetch.base.Repo(
        name_with_owner=str(name),
        default_branch=None if branch is None else str(branch),
        head_oid=None if head is None else str(head),
        is_archived=bool(archived),
        is_fork=bool(fork),
        pushed_at=optional_from_text(None if pushed_at is None else str(pushed_at)),
        updated_at=from_text(str(updated_at)),
        pull_requests_updated_at=optional_from_text(None if pulls_at is None else str(pulls_at)),
        issues_updated_at=optional_from_text(None if issues_at is None else str(issues_at)),
        missing=bool(missing),
    )


def commit_from_row(repo: str, row: tuple[object, ...]) -> wambatic.fetch.base.Commit:
    oid, authored_at, login, additions, deletions, is_merge = row
    return wambatic.fetch.base.Commit(
        repo=repo,
        oid=str(oid),
        authored_at=from_text(str(authored_at)),
        author_login=None if login is None else str(login),
        additions=int(str(additions)),
        deletions=int(str(deletions)),
        is_merge=bool(is_merge),
    )


def pull_request_from_row(repo: str, row: tuple[object, ...]) -> wambatic.fetch.base.PullRequest:
    number, login, created, updated, merged, closed, review, additions, deletions = row
    return wambatic.fetch.base.PullRequest(
        repo=repo,
        number=int(str(number)),
        author_login=None if login is None else str(login),
        created_at=from_text(str(created)),
        updated_at=from_text(str(updated)),
        merged_at=optional_from_text(None if merged is None else str(merged)),
        closed_at=optional_from_text(None if closed is None else str(closed)),
        first_review_at=optional_from_text(None if review is None else str(review)),
        additions=int(str(additions)),
        deletions=int(str(deletions)),
    )


def issue_from_row(repo: str, row: tuple[object, ...]) -> wambatic.fetch.base.Issue:
    number, login, created, updated, closed = row
    return wambatic.fetch.base.Issue(
        repo=repo,
        number=int(str(number)),
        author_login=None if login is None else str(login),
        created_at=from_text(str(created)),
        updated_at=from_text(str(updated)),
        closed_at=optional_from_text(None if closed is None else str(closed)),
    )


class Cache:
    """The SQLite cache. One connection, serialised by one lock taken by every public method.

    Each write method is one transaction. Helpers that run inside a method's transaction do not
    take the lock again.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.lock = threading.Lock()

    @classmethod
    def open(cls, path: pathlib.Path, *, ignore_version: bool = False) -> Cache:
        """Create the parent directory and file if absent, set WAL mode, create the schema,
        then check or write the identity; raises CacheVersionError on a mismatch unless
        `ignore_version`, which is recorded in `meta` as `version_override_at`."""
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, check_same_thread=False)
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA foreign_keys=ON')
            connection.executescript(SCHEMA)
            cache = cls(connection)
            cache.check_identity(ignore_version)
        except BaseException:
            connection.close()
            raise
        return cache

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    def check_identity(self, ignore_version: bool) -> None:
        expected = expected_identity()
        with self.lock, self.connection:
            recorded = self.recorded_identity()
            if not recorded:
                self.connection.executemany(
                    'INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', expected.items()
                )
                return
            differences = identity_differences(recorded, expected)
            if not differences:
                return
            if not ignore_version:
                raise wambatic.fetch.errors.CacheVersionError(differences)
            self.connection.execute(
                'INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)',
                (OVERRIDE_KEY, to_text(datetime.datetime.now(datetime.UTC))),
            )

    def recorded_identity(self) -> dict[str, str]:
        rows = self.connection.execute('SELECT key, value FROM meta').fetchall()
        return {key: value for key, value in rows if key != OVERRIDE_KEY}

    def identity(self) -> dict[str, str]:
        with self.lock:
            return self.recorded_identity()

    def version_override_at(self) -> str | None:
        """When the cache was opened with `ignore_version` over a difference, if it was."""
        with self.lock:
            row = self.connection.execute(
                'SELECT value FROM meta WHERE key = ?', (OVERRIDE_KEY,)
            ).fetchone()
        return None if row is None else str(row[0])

    def upsert_repos(
        self, owner: str, repos: list[wambatic.fetch.base.Repo], *, complete: bool
    ) -> None:
        """Insert or replace each repo; with `complete`, mark the owner's other repos missing."""
        with self.lock, self.connection:
            if complete:
                self.connection.execute(
                    'UPDATE repos SET missing = 1 WHERE owner = ? COLLATE NOCASE', (owner,)
                )
            self.connection.executemany(
                'INSERT OR REPLACE INTO repos (name_with_owner, owner, default_branch, head_oid, '
                'is_archived, is_fork, pushed_at, updated_at, pull_requests_updated_at, '
                'issues_updated_at, missing) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)',
                [
                    (
                        repo.name_with_owner,
                        repo.name_with_owner.partition('/')[0],
                        repo.default_branch,
                        repo.head_oid,
                        repo.is_archived,
                        repo.is_fork,
                        optional_to_text(repo.pushed_at),
                        to_text(repo.updated_at),
                        optional_to_text(repo.pull_requests_updated_at),
                        optional_to_text(repo.issues_updated_at),
                    )
                    for repo in repos
                ],
            )

    def read_repos(self, subject: wambatic.fetch.base.Subject) -> list[wambatic.fetch.base.Repo]:
        columns = (
            'name_with_owner, default_branch, head_oid, is_archived, is_fork, pushed_at, '
            'updated_at, pull_requests_updated_at, issues_updated_at, missing'
        )
        with self.lock:
            if subject.kind == 'repo':
                rows = self.connection.execute(
                    f'SELECT {columns} FROM repos WHERE name_with_owner = ? COLLATE NOCASE',
                    (subject.full_name,),
                ).fetchall()
            else:
                rows = self.connection.execute(
                    f'SELECT {columns} FROM repos WHERE owner = ? COLLATE NOCASE '
                    'ORDER BY name_with_owner',
                    (subject.login,),
                ).fetchall()
        return [repo_from_row(row) for row in rows]

    def sync_state(self, repo: str, resource: str) -> wambatic.fetch.base.SyncState | None:
        with self.lock:
            row = self.connection.execute(
                'SELECT watermark, head_oid, pushed_at, updated_at, synced_at, full_synced_at '
                'FROM sync_state WHERE repo = ? AND resource = ?',
                (repo, resource),
            ).fetchone()
        if row is None:
            return None
        watermark, head_oid, pushed_at, updated_at, synced_at, full_synced_at = row
        return wambatic.fetch.base.SyncState(
            repo=repo,
            resource=resource,
            watermark=optional_from_text(watermark),
            head_oid=head_oid,
            pushed_at=optional_from_text(pushed_at),
            updated_at=from_text(updated_at),
            synced_at=from_text(synced_at),
            full_synced_at=from_text(full_synced_at),
        )

    def put_state(self, state: wambatic.fetch.base.SyncState) -> None:
        """Write a `sync_state` row inside the caller's transaction."""
        self.connection.execute(
            'INSERT OR REPLACE INTO sync_state (repo, resource, watermark, head_oid, pushed_at, '
            'updated_at, synced_at, full_synced_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (
                state.repo,
                state.resource,
                optional_to_text(state.watermark),
                state.head_oid,
                optional_to_text(state.pushed_at),
                to_text(state.updated_at),
                to_text(state.synced_at),
                to_text(state.full_synced_at),
            ),
        )

    def write_rows[T: Record](
        self,
        table: str,
        columns: tuple[str, ...],
        key: tuple[str, ...],
        repo: str,
        records: list[T],
        values: collections.abc.Callable[[T], tuple[object, ...]],
        state: wambatic.fetch.base.SyncState,
        *,
        replace: bool,
    ) -> int:
        """In one transaction: with `replace`, delete the repo's rows from `table` first; upsert
        each record by `key`; write `state`. Returns the number of rows written."""
        if any(record.repo != repo for record in records) or state.repo != repo:
            raise ValueError(f'every record and the state must belong to {repo}')
        updates = ', '.join(f'{name} = excluded.{name}' for name in columns if name not in key)
        sql = (
            f'INSERT INTO {table} ({", ".join(columns)}) '
            f'VALUES ({", ".join("?" * len(columns))}) '
            f'ON CONFLICT ({", ".join(key)}) DO UPDATE SET {updates}'
        )
        with self.lock, self.connection:
            if replace:
                self.connection.execute(f'DELETE FROM {table} WHERE repo = ?', (repo,))
            self.connection.executemany(sql, [values(record) for record in records])
            self.put_state(state)
        return len(records)

    def read_rows(
        self,
        table: str,
        columns: str,
        repo: str,
        since: datetime.datetime | None,
        *,
        time_column: str,
        order: str,
    ) -> list[tuple[object, ...]]:
        query = f'SELECT {columns} FROM {table} WHERE repo = ?'
        params: list[str] = [repo]
        if since is not None:
            query += f' AND {time_column} >= ?'
            params.append(to_text(since))
        with self.lock:
            return self.connection.execute(f'{query} ORDER BY {order}', params).fetchall()

    def write_commits(
        self,
        repo: str,
        commits: list[wambatic.fetch.base.Commit],
        state: wambatic.fetch.base.SyncState,
        *,
        replace: bool,
    ) -> int:
        """In one transaction: with `replace`, delete the repo's commits first; upsert by oid;
        write `state`. Returns the number of rows written."""
        return self.write_rows(
            'commits',
            COMMIT_COLUMNS,
            ('repo', 'oid'),
            repo,
            commits,
            lambda commit: (
                commit.repo,
                commit.oid,
                to_text(commit.authored_at),
                commit.author_login,
                commit.additions,
                commit.deletions,
                commit.is_merge,
            ),
            state,
            replace=replace,
        )

    def write_pull_requests(
        self,
        repo: str,
        pulls: list[wambatic.fetch.base.PullRequest],
        state: wambatic.fetch.base.SyncState,
        *,
        replace: bool,
    ) -> int:
        """As `write_commits`, upserting by number."""
        return self.write_rows(
            'pull_requests',
            PULL_REQUEST_COLUMNS,
            ('repo', 'number'),
            repo,
            pulls,
            lambda pull: (
                pull.repo,
                pull.number,
                pull.author_login,
                to_text(pull.created_at),
                to_text(pull.updated_at),
                optional_to_text(pull.merged_at),
                optional_to_text(pull.closed_at),
                optional_to_text(pull.first_review_at),
                pull.additions,
                pull.deletions,
            ),
            state,
            replace=replace,
        )

    def write_issues(
        self,
        repo: str,
        issues: list[wambatic.fetch.base.Issue],
        state: wambatic.fetch.base.SyncState,
        *,
        replace: bool,
    ) -> int:
        """As `write_commits`, upserting by number."""
        return self.write_rows(
            'issues',
            ISSUE_COLUMNS,
            ('repo', 'number'),
            repo,
            issues,
            lambda issue: (
                issue.repo,
                issue.number,
                issue.author_login,
                to_text(issue.created_at),
                to_text(issue.updated_at),
                optional_to_text(issue.closed_at),
            ),
            state,
            replace=replace,
        )

    def read_commits(
        self, repo: str, since: datetime.datetime | None, until: datetime.datetime | None
    ) -> list[wambatic.fetch.base.Commit]:
        query = (
            'SELECT oid, authored_at, author_login, additions, deletions, is_merge '
            'FROM commits WHERE repo = ?'
        )
        params: list[str] = [repo]
        if since is not None:
            query += ' AND authored_at >= ?'
            params.append(to_text(since))
        if until is not None:
            query += ' AND authored_at < ?'
            params.append(to_text(until))
        with self.lock:
            rows = self.connection.execute(query + ' ORDER BY authored_at, oid', params).fetchall()
        return [commit_from_row(repo, row) for row in rows]

    def read_pull_requests(
        self, repo: str, since: datetime.datetime | None
    ) -> list[wambatic.fetch.base.PullRequest]:
        """Rows with `updated_at >= since` (all when None), by number."""
        rows = self.read_rows(
            'pull_requests',
            ', '.join(PULL_REQUEST_COLUMNS[1:]),
            repo,
            since,
            time_column='updated_at',
            order='number',
        )
        return [pull_request_from_row(repo, row) for row in rows]

    def read_issues(
        self, repo: str, since: datetime.datetime | None
    ) -> list[wambatic.fetch.base.Issue]:
        """Rows with `updated_at >= since` (all when None), by number."""
        rows = self.read_rows(
            'issues',
            ', '.join(ISSUE_COLUMNS[1:]),
            repo,
            since,
            time_column='updated_at',
            order='number',
        )
        return [issue_from_row(repo, row) for row in rows]

    def etag(self, url: str) -> tuple[str, object] | None:
        """The stored ETag and parsed body for a REST URL."""
        with self.lock:
            row = self.connection.execute(
                'SELECT etag, body FROM etags WHERE url = ?', (url,)
            ).fetchone()
        return None if row is None else (row[0], json.loads(row[1]))

    def store_etag(self, url: str, etag: str, body: object) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                'INSERT OR REPLACE INTO etags (url, etag, body) VALUES (?, ?, ?)',
                (url, etag, json.dumps(body)),
            )


@dataclasses.dataclass(frozen=True, slots=True)
class CacheInfo:
    path: pathlib.Path
    size_bytes: int
    identity: dict[str, str]
    differences: dict[str, tuple[str | None, str | None]]
    version_override_at: str | None
    repos: int
    commits: int
    pull_requests: int
    issues: int
    last_synced_at: datetime.datetime | None


def inspect_cache(path: pathlib.Path) -> CacheInfo | None:
    """What `path` holds, read with plain SELECTs on its own connection, or None when it does
    not exist. It creates, migrates and stamps nothing, so a cache `Cache.open` refuses can still
    be inspected; a table absent from the file counts as 0 rows."""
    if not path.exists():
        return None
    connection = sqlite3.connect(path)
    try:
        tables = {
            name
            for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

        def scalar(table: str, query: str) -> object:
            return connection.execute(query).fetchone()[0] if table in tables else None

        meta: dict[str, str] = (
            dict(connection.execute('SELECT key, value FROM meta').fetchall())
            if 'meta' in tables
            else {}
        )
        last_synced = scalar('sync_state', 'SELECT MAX(synced_at) FROM sync_state')
        repos = scalar('repos', 'SELECT COUNT(*) FROM repos WHERE missing = 0')
        commits = scalar('commits', 'SELECT COUNT(*) FROM commits')
        pull_requests = scalar('pull_requests', 'SELECT COUNT(*) FROM pull_requests')
        issues = scalar('issues', 'SELECT COUNT(*) FROM issues')
    finally:
        connection.close()
    identity = {key: value for key, value in meta.items() if key != OVERRIDE_KEY}
    wal = path.with_name(path.name + '-wal')
    return CacheInfo(
        path=path,
        size_bytes=path.stat().st_size + (wal.stat().st_size if wal.exists() else 0),
        identity=identity,
        differences=identity_differences(identity, expected_identity()),
        version_override_at=meta.get(OVERRIDE_KEY),
        repos=int(str(repos or 0)),
        commits=int(str(commits or 0)),
        pull_requests=int(str(pull_requests or 0)),
        issues=int(str(issues or 0)),
        last_synced_at=None if last_synced is None else from_text(str(last_synced)),
    )


def clear_cache(path: pathlib.Path) -> list[pathlib.Path]:
    """Delete `path` and its `-wal` and `-shm` files where present; return those deleted."""
    deleted: list[pathlib.Path] = []
    for candidate in (path, path.with_name(path.name + '-wal'), path.with_name(path.name + '-shm')):
        try:
            candidate.unlink()
        except FileNotFoundError:
            continue
        deleted.append(candidate)
    return deleted
