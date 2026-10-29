import datetime
import hashlib
import json
import pathlib
import sqlite3
import threading

import gitstat.fetch.base
import gitstat.fetch.errors
import gitstat.fetch.queries
import gitstat.version

SCHEMA_VERSION = 1

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


def expected_identity() -> dict[str, str]:
    """What a cache written by the running code records in `meta`."""
    identity = {
        'schema_version': str(SCHEMA_VERSION),
        'gitstat_version': gitstat.version.VERSION,
    }
    for name, value in vars(gitstat.fetch.queries).items():
        if name.isupper() and isinstance(value, str):
            identity[f'query:{name}'] = hashlib.sha256(value.encode()).hexdigest()
    return identity


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


def repo_from_row(row: tuple[object, ...]) -> gitstat.fetch.base.Repo:
    name, branch, head, archived, fork, pushed_at, updated_at, missing = row
    return gitstat.fetch.base.Repo(
        name_with_owner=str(name),
        default_branch=None if branch is None else str(branch),
        head_oid=None if head is None else str(head),
        is_archived=bool(archived),
        is_fork=bool(fork),
        pushed_at=optional_from_text(None if pushed_at is None else str(pushed_at)),
        updated_at=from_text(str(updated_at)),
        missing=bool(missing),
    )


def commit_from_row(repo: str, row: tuple[object, ...]) -> gitstat.fetch.base.Commit:
    oid, authored_at, login, additions, deletions, is_merge = row
    return gitstat.fetch.base.Commit(
        repo=repo,
        oid=str(oid),
        authored_at=from_text(str(authored_at)),
        author_login=None if login is None else str(login),
        additions=int(str(additions)),
        deletions=int(str(deletions)),
        is_merge=bool(is_merge),
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
            differences = {
                key: (recorded.get(key), expected.get(key))
                for key in sorted(recorded.keys() | expected.keys())
                if recorded.get(key) != expected.get(key)
            }
            if not differences:
                return
            if not ignore_version:
                raise gitstat.fetch.errors.CacheVersionError(differences)
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
        self, owner: str, repos: list[gitstat.fetch.base.Repo], *, complete: bool
    ) -> None:
        """Insert or replace each repo; with `complete`, mark the owner's other repos missing."""
        with self.lock, self.connection:
            if complete:
                self.connection.execute(
                    'UPDATE repos SET missing = 1 WHERE owner = ? COLLATE NOCASE', (owner,)
                )
            self.connection.executemany(
                'INSERT OR REPLACE INTO repos (name_with_owner, owner, default_branch, head_oid, '
                'is_archived, is_fork, pushed_at, updated_at, missing) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)',
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
                    )
                    for repo in repos
                ],
            )

    def read_repos(self, subject: gitstat.fetch.base.Subject) -> list[gitstat.fetch.base.Repo]:
        columns = (
            'name_with_owner, default_branch, head_oid, is_archived, is_fork, pushed_at, '
            'updated_at, missing'
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

    def sync_state(self, repo: str, resource: str) -> gitstat.fetch.base.SyncState | None:
        with self.lock:
            row = self.connection.execute(
                'SELECT watermark, head_oid, pushed_at, updated_at, synced_at, full_synced_at '
                'FROM sync_state WHERE repo = ? AND resource = ?',
                (repo, resource),
            ).fetchone()
        if row is None:
            return None
        watermark, head_oid, pushed_at, updated_at, synced_at, full_synced_at = row
        return gitstat.fetch.base.SyncState(
            repo=repo,
            resource=resource,
            watermark=optional_from_text(watermark),
            head_oid=head_oid,
            pushed_at=optional_from_text(pushed_at),
            updated_at=from_text(updated_at),
            synced_at=from_text(synced_at),
            full_synced_at=from_text(full_synced_at),
        )

    def put_state(self, state: gitstat.fetch.base.SyncState) -> None:
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

    def write_commits(
        self,
        repo: str,
        commits: list[gitstat.fetch.base.Commit],
        state: gitstat.fetch.base.SyncState,
        *,
        replace: bool,
    ) -> int:
        """In one transaction: with `replace`, delete the repo's commits first; upsert by oid;
        write `state`. Returns the number of rows written."""
        if any(commit.repo != repo for commit in commits) or state.repo != repo:
            raise ValueError(f'every commit and the state must belong to {repo}')
        with self.lock, self.connection:
            if replace:
                self.connection.execute('DELETE FROM commits WHERE repo = ?', (repo,))
            self.connection.executemany(
                'INSERT INTO commits (repo, oid, authored_at, author_login, additions, deletions, '
                'is_merge) VALUES (?, ?, ?, ?, ?, ?, ?) '
                'ON CONFLICT (repo, oid) DO UPDATE SET authored_at = excluded.authored_at, '
                'author_login = excluded.author_login, additions = excluded.additions, '
                'deletions = excluded.deletions, is_merge = excluded.is_merge',
                [
                    (
                        commit.repo,
                        commit.oid,
                        to_text(commit.authored_at),
                        commit.author_login,
                        commit.additions,
                        commit.deletions,
                        commit.is_merge,
                    )
                    for commit in commits
                ],
            )
            self.put_state(state)
        return len(commits)

    def read_commits(
        self, repo: str, since: datetime.datetime | None, until: datetime.datetime | None
    ) -> list[gitstat.fetch.base.Commit]:
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
