import asyncio
import collections.abc
import dataclasses
import datetime
import typing
import urllib.parse

import loguru

import wambatic.fetch.client
import wambatic.fetch.errors
import wambatic.fetch.queries
import wambatic.settings

if typing.TYPE_CHECKING:
    import wambatic.fetch.cache

RESOURCES = frozenset(
    {'commits', 'issues', 'pull_requests', 'releases', 'star_events', 'workflow_runs'}
)
BUILT_RESOURCES = frozenset({'commits'})
UNBUILT_RESOURCE_STEPS = {
    'issues': 6,
    'pull_requests': 6,
    'releases': 8,
    'star_events': 8,
    'workflow_runs': 8,
}
PAGE_SIZE = 100


@dataclasses.dataclass(frozen=True, slots=True)
class Subject:
    kind: typing.Literal['user', 'repo', 'org']
    login: str
    name: str | None = None

    def __post_init__(self) -> None:
        if self.kind == 'repo' and self.name is None:
            raise ValueError('a repo subject needs a name')
        if self.kind != 'repo' and self.name is not None:
            raise ValueError(f'a {self.kind} subject has no name')

    @property
    def full_name(self) -> str:
        if self.name is None:
            raise ValueError(f'a {self.kind} subject has no repo name')
        return f'{self.login}/{self.name}'


@dataclasses.dataclass(frozen=True, slots=True)
class Repo:
    name_with_owner: str
    default_branch: str | None
    head_oid: str | None
    is_archived: bool
    is_fork: bool
    pushed_at: datetime.datetime | None
    updated_at: datetime.datetime
    pull_requests_updated_at: datetime.datetime | None = None
    issues_updated_at: datetime.datetime | None = None
    missing: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class Commit:
    repo: str
    oid: str
    authored_at: datetime.datetime
    author_login: str | None
    additions: int
    deletions: int
    is_merge: bool


@dataclasses.dataclass(frozen=True, slots=True)
class PullRequest:
    repo: str
    number: int
    author_login: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    merged_at: datetime.datetime | None
    closed_at: datetime.datetime | None
    first_review_at: datetime.datetime | None
    additions: int
    deletions: int


@dataclasses.dataclass(frozen=True, slots=True)
class Issue:
    repo: str
    number: int
    author_login: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    closed_at: datetime.datetime | None


@dataclasses.dataclass(frozen=True, slots=True)
class SyncState:
    repo: str
    resource: str
    watermark: datetime.datetime | None
    head_oid: str | None
    pushed_at: datetime.datetime | None
    updated_at: datetime.datetime
    synced_at: datetime.datetime
    full_synced_at: datetime.datetime


@dataclasses.dataclass(frozen=True, slots=True)
class SyncReport:
    repos_listed: int
    repos_skipped: int
    rows_written: dict[str, int]
    full_refetches: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class NewCommit:
    """A commit found by a compare, before its line counts are known."""

    oid: str
    node_id: str
    authored_at: datetime.datetime
    author_login: str | None
    is_merge: bool


def malformed(what: str) -> wambatic.fetch.errors.GraphQLError:
    return wambatic.fetch.errors.GraphQLError([('MALFORMED', f'unexpected shape: {what}')])


def mapping(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise malformed(what)
    return value


def sequence(value: object, what: str) -> list[object]:
    if not isinstance(value, list):
        raise malformed(what)
    return value


def text(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise malformed(what)
    return value


def integer(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise malformed(what)
    return value


def timestamp(value: object, what: str) -> datetime.datetime:
    try:
        parsed = datetime.datetime.fromisoformat(text(value, what))
    except ValueError:
        raise malformed(what) from None
    if parsed.tzinfo is None:
        raise malformed(what)
    return parsed.astimezone(datetime.UTC)


def parse_repo(node: object) -> Repo:
    fields = mapping(node, 'repository')
    branch = fields.get('defaultBranchRef')
    default_branch: str | None = None
    head_oid: str | None = None
    if branch is not None:
        branch_fields = mapping(branch, 'defaultBranchRef')
        default_branch = text(branch_fields.get('name'), 'defaultBranchRef.name')
        target = mapping(branch_fields.get('target'), 'defaultBranchRef.target')
        head_oid = text(target.get('oid'), 'defaultBranchRef.target.oid')
    pushed_at = fields.get('pushedAt')
    return Repo(
        name_with_owner=text(fields.get('nameWithOwner'), 'nameWithOwner'),
        default_branch=default_branch,
        head_oid=head_oid,
        is_archived=fields.get('isArchived') is True,
        is_fork=fields.get('isFork') is True,
        pushed_at=None if pushed_at is None else timestamp(pushed_at, 'pushedAt'),
        updated_at=timestamp(fields.get('updatedAt'), 'updatedAt'),
    )


def parse_history_node(repo: str, node: object) -> Commit:
    fields = mapping(node, 'history node')
    author = fields.get('author')
    user = mapping(author, 'author').get('user') if author is not None else None
    login = mapping(user, 'author.user').get('login') if user is not None else None
    parents = mapping(fields.get('parents'), 'parents')
    return Commit(
        repo=repo,
        oid=text(fields.get('oid'), 'oid'),
        authored_at=timestamp(fields.get('authoredDate'), 'authoredDate'),
        author_login=None if login is None else text(login, 'author.user.login'),
        additions=integer(fields.get('additions'), 'additions'),
        deletions=integer(fields.get('deletions'), 'deletions'),
        is_merge=integer(parents.get('totalCount'), 'parents.totalCount') > 1,
    )


def parse_compare_commit(node: object) -> NewCommit:
    fields = mapping(node, 'compare commit')
    commit = mapping(fields.get('commit'), 'commit')
    author = mapping(commit.get('author'), 'commit.author')
    account = fields.get('author')
    login = mapping(account, 'author').get('login') if account is not None else None
    return NewCommit(
        oid=text(fields.get('sha'), 'sha'),
        node_id=text(fields.get('node_id'), 'node_id'),
        authored_at=timestamp(author.get('date'), 'commit.author.date'),
        author_login=None if login is None else text(login, 'author.login'),
        is_merge=len(sequence(fields.get('parents'), 'parents')) > 1,
    )


def split_name(name_with_owner: str) -> tuple[str, str]:
    owner, _, name = name_with_owner.partition('/')
    return owner, name


class Fetcher:
    """Brings the cache up to date from GitHub and reads records back from it.

    Only `sync` reaches the network; `repos` and `commits` read the cache.
    """

    def __init__(
        self,
        token: str,
        cache: wambatic.fetch.cache.Cache,
        settings: wambatic.settings.FetchSettings,
        *,
        client: wambatic.fetch.client.GitHubClient | None = None,
    ) -> None:
        self.cache = cache
        self.settings = settings
        self.client = client or wambatic.fetch.client.GitHubClient(token, settings)
        self.semaphore = asyncio.Semaphore(settings.workers)

    async def __aenter__(self) -> Fetcher:
        await self.client.__aenter__()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.client.__aexit__(*exc_info)

    async def db[**P, R](
        self, function: collections.abc.Callable[P, R], *args: P.args, **kwargs: P.kwargs
    ) -> R:
        """Run a `Cache` method on a worker thread so the event loop is never blocked."""
        return await asyncio.to_thread(function, *args, **kwargs)

    async def rest_cached(self, path: str, params: collections.abc.Mapping[str, str]) -> object:
        """GET revalidated with the stored ETag; a 304 returns the stored body."""
        url = f'{path}?{urllib.parse.urlencode(sorted(params.items()))}'
        stored = await self.db(self.cache.etag, url)
        response = await self.client.rest_get(
            path, params, etag=None if stored is None else stored[0]
        )
        if response.status == 304 and stored is not None:
            return stored[1]
        if response.etag is not None:
            await self.db(self.cache.store_etag, url, response.etag, response.data)
        return response.data

    async def owner_kind(self, login: str) -> typing.Literal['user', 'org']:
        """Whether `login` is a user or an organisation, from GitHub's own `type` field; one
        request, nothing cached."""
        response = await self.client.rest_get(f'/users/{login}')
        body = response.data
        kind = body.get('type') if isinstance(body, dict) else None
        if kind == 'User':
            return 'user'
        if kind == 'Organization':
            return 'org'
        raise wambatic.fetch.errors.NotFoundError(
            f'{login} is not a user or an organisation (type: {kind!r})'
        )

    async def list_repos(self, subject: Subject) -> list[Repo]:
        """The subject's repositories from GitHub, after the fork and archived filters."""
        if subject.kind == 'repo':
            data = await self.client.graphql(
                wambatic.fetch.queries.REPOSITORY, {'owner': subject.login, 'name': subject.name}
            )
            if data.get('repository') is None:
                raise wambatic.fetch.errors.NotFoundError(f'{subject.full_name} not found')
            return [parse_repo(data['repository'])]
        repos: list[Repo] = []
        cursor: str | None = None
        while True:
            data = await self.client.graphql(
                wambatic.fetch.queries.OWNER_REPOSITORIES,
                {'login': subject.login, 'cursor': cursor},
            )
            if data.get('repositoryOwner') is None:
                raise wambatic.fetch.errors.NotFoundError(f'{subject.login} not found')
            connection = mapping(
                mapping(data['repositoryOwner'], 'repositoryOwner').get('repositories'),
                'repositories',
            )
            repos.extend(parse_repo(node) for node in sequence(connection.get('nodes'), 'nodes'))
            page = mapping(connection.get('pageInfo'), 'pageInfo')
            if page.get('hasNextPage') is not True:
                return self.filter_repos(repos)
            cursor = text(page.get('endCursor'), 'endCursor')

    def filter_repos(self, repos: list[Repo]) -> list[Repo]:
        return [
            repo
            for repo in repos
            if (self.settings.include_forks or not repo.is_fork)
            and (self.settings.include_archived or not repo.is_archived)
        ]

    async def unchanged(self, repo: Repo, resources: collections.abc.Iterable[str]) -> bool:
        """True when every resource was last synced against this listed `pushedAt`/`updatedAt`."""
        for resource in resources:
            state = await self.db(self.cache.sync_state, repo.name_with_owner, resource)
            if (
                state is None
                or state.pushed_at != repo.pushed_at
                or state.updated_at != repo.updated_at
            ):
                return False
        return True

    async def repos(self, subject: Subject) -> list[Repo]:
        """From the cache: repositories owned by a user or org, excluding missing ones and
        applying the current fork and archived settings; a repo subject yields itself."""
        rows = await self.db(self.cache.read_repos, subject)
        rows = [repo for repo in rows if not repo.missing]
        return rows if subject.kind == 'repo' else self.filter_repos(rows)

    async def commits(
        self, repo: Repo, since: datetime.datetime | None, until: datetime.datetime | None
    ) -> collections.abc.AsyncIterator[Commit]:
        """From the cache: default-branch commits with `since <= authored_at < until`, oldest
        first."""
        for commit in await self.db(self.cache.read_commits, repo.name_with_owner, since, until):
            yield commit

    async def provenance(self, subject: Subject, resources: frozenset[str]) -> dict[str, str]:
        """From the cache: the cache identity, `version_override_at` when recorded, and for each
        resource `fetched_at:<resource>`, the earliest `synced_at` over the subject's repos, or
        `never` when one of them has no sync state for it."""
        unknown = sorted(resources - RESOURCES)
        if unknown:
            raise ValueError(f'unknown resources: {", ".join(unknown)}')
        result = await self.db(self.cache.identity)
        override = await self.db(self.cache.version_override_at)
        if override is not None:
            result['version_override_at'] = override
        repos = await self.repos(subject)
        for resource in sorted(resources):
            synced: list[datetime.datetime] = []
            for repo in repos:
                state = await self.db(self.cache.sync_state, repo.name_with_owner, resource)
                if state is not None:
                    synced.append(state.synced_at)
            if len(synced) < len(repos) or not synced:
                result[f'fetched_at:{resource}'] = 'never'
            else:
                result[f'fetched_at:{resource}'] = min(synced).astimezone(datetime.UTC).isoformat()
        return result

    def new_state(
        self, repo: Repo, resource: str, full_synced_at: datetime.datetime | None
    ) -> SyncState:
        now = self.client.clock()
        return SyncState(
            repo=repo.name_with_owner,
            resource=resource,
            watermark=None,
            head_oid=repo.head_oid,
            pushed_at=repo.pushed_at,
            updated_at=repo.updated_at,
            synced_at=now,
            full_synced_at=full_synced_at or now,
        )

    async def backfill_commits(self, repo: Repo) -> int:
        """Read the default branch's whole history from its head and replace the cached rows."""
        commits: list[Commit] = []
        if repo.default_branch is not None:
            owner, name = split_name(repo.name_with_owner)
            cursor: str | None = None
            while True:
                data = await self.client.graphql(
                    wambatic.fetch.queries.COMMIT_HISTORY,
                    {'owner': owner, 'name': name, 'cursor': cursor},
                )
                repository = mapping(data.get('repository'), 'repository')
                branch = mapping(repository.get('defaultBranchRef'), 'defaultBranchRef')
                target = mapping(branch.get('target'), 'target')
                history = mapping(target.get('history'), 'history')
                commits.extend(
                    parse_history_node(repo.name_with_owner, node)
                    for node in sequence(history.get('nodes'), 'nodes')
                )
                page = mapping(history.get('pageInfo'), 'pageInfo')
                if page.get('hasNextPage') is not True:
                    break
                cursor = text(page.get('endCursor'), 'endCursor')
        state = self.new_state(repo, 'commits', None)
        return await self.db(
            self.cache.write_commits, repo.name_with_owner, commits, state, replace=True
        )

    async def compare(self, repo: Repo, base: str, head: str) -> list[NewCommit] | None:
        """Commits reachable from `head` and not `base`; None when `base` is not an ancestor."""
        path = f'/repos/{repo.name_with_owner}/compare/{base}...{head}'
        found: list[NewCommit] = []
        status = ''
        page = 1
        while True:
            try:
                body = await self.rest_cached(path, {'per_page': str(PAGE_SIZE), 'page': str(page)})
            except wambatic.fetch.errors.NotFoundError:
                return None
            fields = mapping(body, 'compare')
            if page == 1:
                status = text(fields.get('status'), 'status')
                if status in ('diverged', 'behind'):
                    return None
            nodes = sequence(fields.get('commits'), 'commits')
            found.extend(parse_compare_commit(node) for node in nodes)
            total = integer(fields.get('total_commits'), 'total_commits')
            if len(nodes) < PAGE_SIZE or len(found) >= total:
                return found
            page += 1

    async def line_counts(self, repo: Repo, new: list[NewCommit]) -> list[Commit]:
        """Add `additions` and `deletions` to compare commits, 100 per GraphQL query."""
        counts: dict[str, tuple[int, int]] = {}
        for start in range(0, len(new), PAGE_SIZE):
            ids = [commit.node_id for commit in new[start : start + PAGE_SIZE]]
            data = await self.client.graphql(wambatic.fetch.queries.COMMIT_NODES, {'ids': ids})
            for node in sequence(data.get('nodes'), 'nodes'):
                if node is None:
                    continue
                fields = mapping(node, 'commit node')
                counts[text(fields.get('oid'), 'oid')] = (
                    integer(fields.get('additions'), 'additions'),
                    integer(fields.get('deletions'), 'deletions'),
                )
        commits: list[Commit] = []
        for commit in new:
            if commit.oid not in counts:
                raise wambatic.fetch.errors.GraphQLError(
                    [('MISSING', f'no line counts returned for commit {commit.oid}')]
                )
            additions, deletions = counts[commit.oid]
            commits.append(
                Commit(
                    repo=repo.name_with_owner,
                    oid=commit.oid,
                    authored_at=commit.authored_at,
                    author_login=commit.author_login,
                    additions=additions,
                    deletions=deletions,
                    is_merge=commit.is_merge,
                )
            )
        return commits

    async def update_commits(self, repo: Repo, state: SyncState) -> int | None:
        """Add the commits that reached the head since the stored one.

        Returns the rows written, or None when the stored head is not an ancestor of the
        listed one (or is gone) and the history must be read again.
        """
        commits: list[Commit] = []
        if repo.head_oid != state.head_oid:
            if repo.head_oid is None or state.head_oid is None:
                return None
            new = await self.compare(repo, state.head_oid, repo.head_oid)
            if new is None:
                return None
            commits = await self.line_counts(repo, new)
        new_state = self.new_state(repo, 'commits', state.full_synced_at)
        return await self.db(
            self.cache.write_commits, repo.name_with_owner, commits, new_state, replace=False
        )

    async def sync_commits(self, repo: Repo, full_refresh: bool) -> tuple[int, bool]:
        """Rows written and whether the history was read from scratch."""
        state = await self.db(self.cache.sync_state, repo.name_with_owner, 'commits')
        if state is None:
            reason = 'no previous sync'
        elif full_refresh:
            reason = 'full refresh requested'
        else:
            written = await self.update_commits(repo, state)
            if written is not None:
                return written, False
            reason = 'history rewritten'
        loguru.logger.info(f'Reading all commits of {repo.name_with_owner}: {reason}')
        return await self.backfill_commits(repo), True

    async def sync(
        self, subject: Subject, resources: frozenset[str], full_refresh: bool = False
    ) -> SyncReport:
        """Bring the cache up to date for the subject: backfill on first use, otherwise only
        the delta."""
        unknown = sorted(resources - RESOURCES)
        if unknown:
            raise ValueError(f'unknown resources: {", ".join(unknown)}')
        unbuilt = sorted(resources - BUILT_RESOURCES)
        if unbuilt:
            steps = ', '.join(f'{name} (step {UNBUILT_RESOURCE_STEPS[name]})' for name in unbuilt)
            raise NotImplementedError(f'not built yet: {steps}')
        listed = await self.list_repos(subject)
        await self.db(
            self.cache.upsert_repos, subject.login, listed, complete=subject.kind != 'repo'
        )
        pending: list[Repo] = []
        for repo in listed:
            if full_refresh or not await self.unchanged(repo, resources):
                pending.append(repo)
        rows = 0
        refetched: list[str] = []

        async def sync_one(repo: Repo) -> None:
            nonlocal rows
            async with self.semaphore:
                written, full = await self.sync_commits(repo, full_refresh)
            rows += written
            if full:
                refetched.append(repo.name_with_owner)

        try:
            async with asyncio.TaskGroup() as group:
                for repo in pending:
                    group.create_task(sync_one(repo))
        except ExceptionGroup as errors:
            raise errors.exceptions[0] from errors
        return SyncReport(
            repos_listed=len(listed),
            repos_skipped=len(listed) - len(pending),
            rows_written={'commits': rows} if 'commits' in resources else {},
            full_refetches=tuple(sorted(refetched)),
        )
