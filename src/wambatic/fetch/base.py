import asyncio
import collections.abc
import contextlib
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
    {'commits', 'forks', 'issues', 'pull_requests', 'releases', 'star_events', 'workflow_runs'}
)
BUILT_RESOURCES = frozenset({'commits', 'issues', 'pull_requests', 'releases', 'workflow_runs'})
UNBUILT_RESOURCE_STEPS = {'forks': 10, 'star_events': 10}
PAGE_SIZE = 100
BOT_SUFFIX = '[bot]'


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
    releases_count: int = 0
    releases_updated_at: datetime.datetime | None = None
    stargazer_count: int = 0
    fork_count: int = 0
    watcher_count: int = 0
    languages: tuple[tuple[str, int], ...] = ()
    languages_size: int = 0
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
    labels: tuple[str, ...] = ()
    first_commit_at: datetime.datetime | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Issue:
    repo: str
    number: int
    author_login: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    closed_at: datetime.datetime | None


@dataclasses.dataclass(frozen=True, slots=True)
class Release:
    """A published release; drafts are not stored."""

    repo: str
    tag_name: str
    created_at: datetime.datetime
    published_at: datetime.datetime
    is_prerelease: bool


@dataclasses.dataclass(frozen=True, slots=True)
class WorkflowRun:
    """A GitHub Actions run, its latest attempt."""

    repo: str
    id: int
    workflow_path: str
    name: str
    event: str
    head_branch: str | None
    status: str
    conclusion: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    run_started_at: datetime.datetime | None
    run_attempt: int


@dataclasses.dataclass(frozen=True, slots=True)
class StarEvent:
    """A star a user gave a repo; the user is its GraphQL node id, no login is stored."""

    repo: str
    user_id: str
    starred_at: datetime.datetime


@dataclasses.dataclass(frozen=True, slots=True)
class Fork:
    """A direct fork of a repo, from the REST fork list."""

    repo: str
    id: int
    created_at: datetime.datetime


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
    probe: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class SyncReport:
    repos_listed: int
    repos_skipped: int
    rows_written: dict[str, int]
    full_refetches: tuple[str, ...]


@dataclasses.dataclass(slots=True)
class SyncProgress:
    """Filled in by `Fetcher.sync` as it runs, on the event loop that runs it."""

    repos_listed: int | None = None
    repos_pending: int | None = None
    repos_done: int = 0
    rows_written: dict[str, int] = dataclasses.field(default_factory=dict)


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


def probe(fields: dict[str, object], name: str) -> datetime.datetime | None:
    """The `updatedAt` of the one node a listing selects from the connection `name`."""
    nodes = sequence(mapping(fields.get(name), name).get('nodes'), f'{name}.nodes')
    if not nodes:
        return None
    return timestamp(mapping(nodes[0], f'{name} node').get('updatedAt'), f'{name}.updatedAt')


def release_probe(repo: Repo) -> str:
    """The text a repo's releases are compared by: their count and the newest-created one's
    `updatedAt`, so adding, deleting, publishing or editing the newest release changes it."""
    newest = (
        'none'
        if repo.releases_updated_at is None
        else repo.releases_updated_at.astimezone(datetime.UTC).isoformat()
    )
    return f'{repo.releases_count} {newest}'


def star_probe(repo: Repo) -> str:
    """The text a repo's stars are compared by: its listed star count."""
    return str(repo.stargazer_count)


def fork_probe(repo: Repo) -> str:
    """The text a repo's forks are compared by: its listed fork count, forks of forks included."""
    return str(repo.fork_count)


def parse_languages(languages: object) -> tuple[tuple[tuple[str, int], ...], int]:
    """The listed languages in GitHub's order (largest first) and `totalSize`; `null` is none."""
    if languages is None:
        return (), 0
    fields = mapping(languages, 'languages')
    found: list[tuple[str, int]] = []
    for edge in sequence(fields.get('edges'), 'languages.edges'):
        edge_fields = mapping(edge, 'language edge')
        name = text(mapping(edge_fields.get('node'), 'language').get('name'), 'language.name')
        found.append((name, integer(edge_fields.get('size'), 'language.size')))
    return tuple(found), integer(fields.get('totalSize'), 'languages.totalSize')


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
    pulls_at = probe(fields, 'pullRequests')
    issues_at = probe(fields, 'issues')
    releases_at = probe(fields, 'releases')
    releases_count = integer(
        mapping(fields.get('releases'), 'releases').get('totalCount'), 'releases.totalCount'
    )
    languages, languages_size = parse_languages(fields.get('languages'))
    return Repo(
        name_with_owner=text(fields.get('nameWithOwner'), 'nameWithOwner'),
        default_branch=default_branch,
        head_oid=head_oid,
        is_archived=fields.get('isArchived') is True,
        is_fork=fields.get('isFork') is True,
        pushed_at=None if pushed_at is None else timestamp(pushed_at, 'pushedAt'),
        updated_at=timestamp(fields.get('updatedAt'), 'updatedAt'),
        pull_requests_updated_at=pulls_at,
        issues_updated_at=issues_at,
        releases_count=releases_count,
        releases_updated_at=releases_at,
        stargazer_count=integer(fields.get('stargazerCount'), 'stargazerCount'),
        fork_count=integer(fields.get('forkCount'), 'forkCount'),
        watcher_count=integer(
            mapping(fields.get('watchers'), 'watchers').get('totalCount'), 'watchers.totalCount'
        ),
        languages=languages,
        languages_size=languages_size,
    )


def actor_login(value: object, what: str) -> str | None:
    """The REST form of an author: `login`, `login[bot]` for a bot, None for a deleted account."""
    if value is None:
        return None
    fields = mapping(value, what)
    login = text(fields.get('login'), f'{what}.login')
    return f'{login}{BOT_SUFFIX}' if fields.get('__typename') == 'Bot' else login


def optional_timestamp(value: object, what: str) -> datetime.datetime | None:
    return None if value is None else timestamp(value, what)


def first_review_at(reviews: object, author: str | None) -> datetime.datetime | None:
    """The earliest submitted review by anyone but the pull request's author and bots."""
    found: list[datetime.datetime] = []
    for node in sequence(mapping(reviews, 'reviews').get('nodes'), 'reviews.nodes'):
        fields = mapping(node, 'review')
        submitted = optional_timestamp(fields.get('submittedAt'), 'review.submittedAt')
        if submitted is None:
            continue
        reviewer = actor_login(fields.get('author'), 'review.author')
        if reviewer is not None and (
            reviewer.endswith(BOT_SUFFIX)
            or (author is not None and reviewer.casefold() == author.casefold())
        ):
            continue
        found.append(submitted)
    return min(found, default=None)


def label_names(labels: object) -> tuple[str, ...]:
    nodes = sequence(mapping(labels, 'labels').get('nodes'), 'labels.nodes')
    return tuple(text(mapping(node, 'label').get('name'), 'label.name') for node in nodes)


def first_commit_at(commits: object) -> datetime.datetime | None:
    """The `authoredDate` of the first (oldest) commit of a pull request, None when it has none."""
    nodes = sequence(mapping(commits, 'commits').get('nodes'), 'commits.nodes')
    if not nodes:
        return None
    commit = mapping(mapping(nodes[0], 'pull request commit').get('commit'), 'commit')
    return timestamp(commit.get('authoredDate'), 'commit.authoredDate')


def parse_pull_request(repo: str, node: object) -> PullRequest:
    fields = mapping(node, 'pull request')
    state = text(fields.get('state'), 'state')
    author = actor_login(fields.get('author'), 'author')
    return PullRequest(
        repo=repo,
        number=integer(fields.get('number'), 'number'),
        author_login=author,
        created_at=timestamp(fields.get('createdAt'), 'createdAt'),
        updated_at=timestamp(fields.get('updatedAt'), 'updatedAt'),
        merged_at=optional_timestamp(fields.get('mergedAt'), 'mergedAt')
        if state == 'MERGED'
        else None,
        closed_at=optional_timestamp(fields.get('closedAt'), 'closedAt')
        if state != 'OPEN'
        else None,
        first_review_at=first_review_at(fields.get('reviews'), author),
        additions=integer(fields.get('additions'), 'additions'),
        deletions=integer(fields.get('deletions'), 'deletions'),
        labels=label_names(fields.get('labels')),
        first_commit_at=first_commit_at(fields.get('commits')),
    )


def parse_issue(repo: str, node: object) -> Issue:
    fields = mapping(node, 'issue')
    state = text(fields.get('state'), 'state')
    return Issue(
        repo=repo,
        number=integer(fields.get('number'), 'number'),
        author_login=actor_login(fields.get('author'), 'author'),
        created_at=timestamp(fields.get('createdAt'), 'createdAt'),
        updated_at=timestamp(fields.get('updatedAt'), 'updatedAt'),
        closed_at=optional_timestamp(fields.get('closedAt'), 'closedAt')
        if state == 'CLOSED'
        else None,
    )


def parse_release(repo: str, node: object) -> Release | None:
    """None for a draft or a release with no `publishedAt`: drafts are not stored."""
    fields = mapping(node, 'release')
    published = optional_timestamp(fields.get('publishedAt'), 'publishedAt')
    if fields.get('isDraft') is True or published is None:
        return None
    return Release(
        repo=repo,
        tag_name=text(fields.get('tagName'), 'tagName'),
        created_at=timestamp(fields.get('createdAt'), 'createdAt'),
        published_at=published,
        is_prerelease=fields.get('isPrerelease') is True,
    )


def parse_workflow_run(repo: str, node: object) -> WorkflowRun:
    """A run object of the REST list. `name`, `status` and `run_started_at` may be null and
    `run_attempt` absent in GitHub's schema; a missing attempt is the first."""
    fields = mapping(node, 'workflow run')
    name = fields.get('name')
    status = fields.get('status')
    branch = fields.get('head_branch')
    conclusion = fields.get('conclusion')
    attempt = fields.get('run_attempt')
    return WorkflowRun(
        repo=repo,
        id=integer(fields.get('id'), 'id'),
        workflow_path=text(fields.get('path'), 'path'),
        name='' if name is None else text(name, 'name'),
        event=text(fields.get('event'), 'event'),
        head_branch=None if branch is None else text(branch, 'head_branch'),
        status='' if status is None else text(status, 'status'),
        conclusion=None if conclusion is None else text(conclusion, 'conclusion'),
        created_at=timestamp(fields.get('created_at'), 'created_at'),
        updated_at=timestamp(fields.get('updated_at'), 'updated_at'),
        run_started_at=optional_timestamp(fields.get('run_started_at'), 'run_started_at'),
        run_attempt=1 if attempt is None else integer(attempt, 'run_attempt'),
    )


def parse_star_edge(repo: str, edge: object) -> StarEvent:
    """An edge of `Repository.stargazers`; the user's node id is kept, never the login."""
    fields = mapping(edge, 'stargazer edge')
    user = mapping(fields.get('node'), 'stargazer')
    return StarEvent(
        repo=repo,
        user_id=text(user.get('id'), 'stargazer.id'),
        starred_at=timestamp(fields.get('starredAt'), 'starredAt'),
    )


def parse_fork(repo: str, node: object) -> Fork:
    """A fork object of the REST list, trimmed to the fields the fetcher reads."""
    fields = mapping(node, 'fork')
    return Fork(
        repo=repo,
        id=integer(fields.get('id'), 'id'),
        created_at=timestamp(fields.get('created_at'), 'created_at'),
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


@dataclasses.dataclass(frozen=True, slots=True)
class UpdatedRead[R: PullRequest | Issue]:
    """How to page a mutable resource: its query, the connection the query selects, its parser."""

    query: str
    connection: str
    parse: collections.abc.Callable[[str, object], R]


def repository_connection(
    name: str,
) -> collections.abc.Callable[[dict[str, object]], dict[str, object]]:
    """Finds the connection `name` of `repository` in a response's `data`."""

    def connection(data: dict[str, object]) -> dict[str, object]:
        repository = mapping(data.get('repository'), 'repository')
        return mapping(repository.get(name), name)

    return connection


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

    async def rest_cached(
        self, path: str, params: collections.abc.Mapping[str, str]
    ) -> tuple[object, datetime.datetime | None]:
        """GET revalidated with the stored ETag; a 304 returns the stored body. Also returns the
        `Date` of the response, a 304's own included."""
        url = f'{path}?{urllib.parse.urlencode(sorted(params.items()))}'
        stored = await self.db(self.cache.etag, url)
        response = await self.client.rest_get(
            path, params, etag=None if stored is None else stored[0]
        )
        if response.status == 304 and stored is not None:
            return stored[1], response.date
        if response.etag is not None:
            await self.db(self.cache.store_etag, url, response.etag, response.data)
        return response.data, response.date

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

    async def pages(
        self,
        query: str,
        variables: collections.abc.Mapping[str, object],
        connection_of: collections.abc.Callable[[dict[str, object]], dict[str, object]],
        items: str = 'nodes',
    ) -> collections.abc.AsyncGenerator[tuple[list[object], datetime.datetime]]:
        """The nodes (or the `items` of a connection that selects edges) of each page of a paged
        GraphQL connection, with the `Date` of the response that carried it. `connection_of` finds
        the connection in a response's `data`."""
        cursor: str | None = None
        while True:
            data, date = await self.client.graphql_dated(query, {**variables, 'cursor': cursor})
            connection = connection_of(data)
            yield sequence(connection.get(items), items), date
            page = mapping(connection.get('pageInfo'), 'pageInfo')
            if page.get('hasNextPage') is not True:
                return
            cursor = text(page.get('endCursor'), 'endCursor')

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

        def repositories(data: dict[str, object]) -> dict[str, object]:
            if data.get('repositoryOwner') is None:
                raise wambatic.fetch.errors.NotFoundError(f'{subject.login} not found')
            owner = mapping(data['repositoryOwner'], 'repositoryOwner')
            return mapping(owner.get('repositories'), 'repositories')

        async with contextlib.aclosing(
            self.pages(
                wambatic.fetch.queries.OWNER_REPOSITORIES, {'login': subject.login}, repositories
            )
        ) as pages:
            async for nodes, _ in pages:
                repos.extend(parse_repo(node) for node in nodes)
        return self.filter_repos(repos)

    def filter_repos(self, repos: list[Repo]) -> list[Repo]:
        return [
            repo
            for repo in repos
            if (self.settings.include_forks or not repo.is_fork)
            and (self.settings.include_archived or not repo.is_archived)
        ]

    async def unchanged(self, repo: Repo, resource: str) -> bool:
        """True when `resource` needs no request for this listed repo.

        `commits` were last synced against this `pushedAt` and `updatedAt`. `issues` and
        `pull_requests` have a watermark, no full read is due and the listed newest `updatedAt`
        is absent or before the point at which paging would stop on its first item. `releases`
        have no full read due and the listed release probe equals the stored one. `workflow_runs`
        have no probe in GraphQL: their conditional request is the check, so they are never
        unchanged.
        """
        if resource == 'workflow_runs':
            return False
        state = await self.db(self.cache.sync_state, repo.name_with_owner, resource)
        if state is None:
            return False
        if resource == 'commits':
            return state.pushed_at == repo.pushed_at and state.updated_at == repo.updated_at
        if self.full_read_due(state, self.client.clock()):
            return False
        if resource == 'releases':
            return state.probe == release_probe(repo)
        if state.watermark is None:
            return False
        newest = (
            repo.pull_requests_updated_at if resource == 'pull_requests' else repo.issues_updated_at
        )
        return newest is None or newest < state.watermark - self.settings.overlap

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

            def history(data: dict[str, object]) -> dict[str, object]:
                repository = mapping(data.get('repository'), 'repository')
                branch = mapping(repository.get('defaultBranchRef'), 'defaultBranchRef')
                target = mapping(branch.get('target'), 'target')
                return mapping(target.get('history'), 'history')

            async with contextlib.aclosing(
                self.pages(
                    wambatic.fetch.queries.COMMIT_HISTORY, {'owner': owner, 'name': name}, history
                )
            ) as pages:
                async for nodes, _ in pages:
                    commits.extend(parse_history_node(repo.name_with_owner, node) for node in nodes)
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
                body, _ = await self.rest_cached(
                    path, {'per_page': str(PAGE_SIZE), 'page': str(page)}
                )
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

    def full_read_due(self, state: SyncState | None, now: datetime.datetime) -> bool:
        """Whether a time-windowed resource must be read from scratch: it never was, or not for
        longer than `fetch.full_refresh_after`, the only way a deleted item leaves the cache."""
        return state is None or now - state.full_synced_at > self.settings.full_refresh_after

    def full_read_reason(self, state: SyncState | None, full_refresh: bool) -> str:
        """Why a time-windowed resource is read from scratch, '' when an incremental read will
        do; the reason is logged by the caller."""
        if state is None:
            return 'no previous sync'
        if full_refresh:
            return 'full refresh requested'
        if self.full_read_due(state, self.client.clock()):
            return 'full refresh interval passed'
        return ''

    async def read_updated[R: PullRequest | Issue](
        self, repo: Repo, read: UpdatedRead[R], state: SyncState | None, full: bool
    ) -> tuple[list[R], datetime.datetime]:
        """The repo's pull requests or issues, newest update first, and the watermark for them:
        the `Date` of the first page's response. Paging stops at the first item last updated
        before `state.watermark - fetch.overlap`, unless `full` or there is no watermark."""
        owner, name = split_name(repo.name_with_owner)
        cutoff = (
            None
            if full or state is None or state.watermark is None
            else state.watermark - self.settings.overlap
        )
        found: list[R] = []
        watermark: datetime.datetime | None = None

        async with contextlib.aclosing(
            self.pages(
                read.query, {'owner': owner, 'name': name}, repository_connection(read.connection)
            )
        ) as pages:
            async for nodes, date in pages:
                watermark = watermark or date
                for node in nodes:
                    record = read.parse(repo.name_with_owner, node)
                    if cutoff is not None and record.updated_at < cutoff:
                        return found, watermark
                    found.append(record)
        if watermark is None:
            raise malformed('no page was read')
        return found, watermark

    async def sync_updated(self, repo: Repo, resource: str, full_refresh: bool) -> int:
        """Bring the repo's pull requests or issues up to date and return the rows written:
        everything on the first sync, on a full refresh or when a full read is due, else the
        items changed since the watermark. The rows and the new state go in one transaction."""
        state = await self.db(self.cache.sync_state, repo.name_with_owner, resource)
        full, full_synced_at = self.plan_full_read(repo, resource, state, full_refresh)
        if resource == 'pull_requests':
            pulls, watermark = await self.read_updated(
                repo,
                UpdatedRead(
                    wambatic.fetch.queries.PULL_REQUESTS, 'pullRequests', parse_pull_request
                ),
                state,
                full,
            )
            return await self.db(
                self.cache.write_pull_requests,
                repo.name_with_owner,
                pulls,
                self.flow_state(repo, resource, watermark, full_synced_at),
                replace=full,
            )
        issues, watermark = await self.read_updated(
            repo,
            UpdatedRead(wambatic.fetch.queries.ISSUES, 'issues', parse_issue),
            state,
            full,
        )
        return await self.db(
            self.cache.write_issues,
            repo.name_with_owner,
            issues,
            self.flow_state(repo, resource, watermark, full_synced_at),
            replace=full,
        )

    def plan_full_read(
        self, repo: Repo, resource: str, state: SyncState | None, full_refresh: bool
    ) -> tuple[bool, datetime.datetime | None]:
        """Whether this read is a full one, logging why, and the `full_synced_at` the new state
        keeps (None: now)."""
        reason = self.full_read_reason(state, full_refresh)
        if reason:
            loguru.logger.info(f'Reading all {resource} of {repo.name_with_owner}: {reason}')
        return bool(reason), None if reason or state is None else state.full_synced_at

    def flow_state(
        self,
        repo: Repo,
        resource: str,
        watermark: datetime.datetime | None,
        full_synced_at: datetime.datetime | None,
    ) -> SyncState:
        return dataclasses.replace(
            self.new_state(repo, resource, full_synced_at), watermark=watermark, head_oid=None
        )

    async def sync_releases(self, repo: Repo, full_refresh: bool) -> int:
        """Read every published release of the repo and replace its cached ones, in one
        transaction with the listing's release probe. Every read is a full read."""
        state = await self.db(self.cache.sync_state, repo.name_with_owner, 'releases')
        self.plan_full_read(repo, 'releases', state, full_refresh)
        owner, name = split_name(repo.name_with_owner)
        releases: list[Release] = []
        async with contextlib.aclosing(
            self.pages(
                wambatic.fetch.queries.RELEASES,
                {'owner': owner, 'name': name},
                repository_connection('releases'),
            )
        ) as pages:
            async for nodes, _ in pages:
                for node in nodes:
                    release = parse_release(repo.name_with_owner, node)
                    if release is not None:
                        releases.append(release)
        new_state = dataclasses.replace(
            self.new_state(repo, 'releases', None), head_oid=None, probe=release_probe(repo)
        )
        return await self.db(self.cache.write_releases, repo.name_with_owner, releases, new_state)

    async def read_workflow_runs(
        self, repo: Repo, cutoff: datetime.datetime | None
    ) -> tuple[list[WorkflowRun], datetime.datetime | None]:
        """The repo's runs, newest first, and the `Date` of the first page's response, which
        is the watermark. The first page goes through the ETag store, so an unchanged repo costs
        a 304. Paging stops at the first run created before `cutoff` (never when None) and at
        a short page. A 404 on the first page is an empty list with no date."""
        path = f'/repos/{repo.name_with_owner}/actions/runs'
        found: list[WorkflowRun] = []
        watermark: datetime.datetime | None = None
        page = 1
        while True:
            params = {
                'per_page': str(PAGE_SIZE),
                'exclude_pull_requests': 'true',
                'page': str(page),
            }
            if page == 1:
                try:
                    body, date = await self.rest_cached(path, params)
                except wambatic.fetch.errors.NotFoundError:
                    loguru.logger.debug(f'No workflow runs for {repo.name_with_owner}: not found')
                    return found, None
                watermark = wambatic.fetch.client.require_date(date)
            else:
                body = (await self.client.rest_get(path, params)).data
            nodes = sequence(mapping(body, 'workflow runs').get('workflow_runs'), 'workflow_runs')
            for node in nodes:
                run = parse_workflow_run(repo.name_with_owner, node)
                if cutoff is not None and run.created_at < cutoff:
                    return found, watermark
                found.append(run)
            if len(nodes) < PAGE_SIZE:
                return found, watermark
            page += 1

    async def reread_unfinished_runs(
        self, repo: Repo, read: list[WorkflowRun]
    ) -> tuple[list[WorkflowRun], list[int]]:
        """Each cached run that is not `completed` and is not in `read`, read again by id, and
        the ids GitHub no longer has."""
        seen = {run.id for run in read}
        again: list[WorkflowRun] = []
        gone: list[int] = []
        for run_id in await self.db(self.cache.unfinished_runs, repo.name_with_owner):
            if run_id in seen:
                continue
            try:
                response = await self.client.rest_get(
                    f'/repos/{repo.name_with_owner}/actions/runs/{run_id}'
                )
            except wambatic.fetch.errors.NotFoundError:
                gone.append(run_id)
                continue
            again.append(parse_workflow_run(repo.name_with_owner, response.data))
        return again, gone

    async def sync_workflow_runs(self, repo: Repo, full_refresh: bool) -> int:
        """Bring the repo's Actions runs up to date and return the rows written: every run on
        a full read, else the runs created since the watermark less `fetch.overlap`, plus every
        cached unfinished run read again. Rows and state go in one transaction."""
        state = await self.db(self.cache.sync_state, repo.name_with_owner, 'workflow_runs')
        full, full_synced_at = self.plan_full_read(repo, 'workflow_runs', state, full_refresh)
        cutoff = (
            None
            if full or state is None or state.watermark is None
            else state.watermark - self.settings.overlap
        )
        runs, watermark = await self.read_workflow_runs(repo, cutoff)
        if watermark is None and state is not None:
            watermark = state.watermark
        again, gone = await self.reread_unfinished_runs(repo, runs)
        return await self.db(
            self.cache.write_workflow_runs,
            repo.name_with_owner,
            [*runs, *again],
            self.flow_state(repo, 'workflow_runs', watermark, full_synced_at),
            replace=full,
            gone=gone,
        )

    async def releases(self, repo: Repo) -> collections.abc.AsyncIterator[Release]:
        """From the cache: the repo's published releases, oldest first. All of them: an interval
        and a lead time reach back before any range."""
        for release in await self.db(self.cache.read_releases, repo.name_with_owner):
            yield release

    async def workflow_runs(
        self, repo: Repo, since: datetime.datetime | None
    ) -> collections.abc.AsyncIterator[WorkflowRun]:
        """From the cache: the repo's runs with `created_at >= since` (all when None), oldest
        first."""
        for run in await self.db(self.cache.read_workflow_runs, repo.name_with_owner, since):
            yield run

    async def pull_requests(
        self, repo: Repo, since: datetime.datetime | None
    ) -> collections.abc.AsyncIterator[PullRequest]:
        """From the cache: the repo's pull requests with `updated_at >= since` (all when None),
        by number. Every event of a pull request is at or before its `updated_at`, so this
        holds every one with an event since `since`."""
        for pull in await self.db(self.cache.read_pull_requests, repo.name_with_owner, since):
            yield pull

    async def issues(
        self, repo: Repo, since: datetime.datetime | None
    ) -> collections.abc.AsyncIterator[Issue]:
        """From the cache, as `pull_requests`."""
        for issue in await self.db(self.cache.read_issues, repo.name_with_owner, since):
            yield issue

    async def sync(
        self,
        subject: Subject,
        resources: frozenset[str],
        full_refresh: bool = False,
        *,
        progress: SyncProgress | None = None,
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
        ordered = sorted(resources)
        pending: list[tuple[Repo, list[str]]] = []
        for repo in listed:
            needed = [
                resource
                for resource in ordered
                if full_refresh or not await self.unchanged(repo, resource)
            ]
            if needed:
                pending.append((repo, needed))
        rows = dict.fromkeys(ordered, 0)
        refetched: list[str] = []
        if progress is not None:
            progress.repos_listed = len(listed)
            progress.repos_pending = len(pending)

        async def sync_one(repo: Repo, needed: list[str]) -> None:
            async with self.semaphore:
                for resource in needed:
                    if resource == 'commits':
                        written, full = await self.sync_commits(repo, full_refresh)
                        if full:
                            refetched.append(repo.name_with_owner)
                    elif resource == 'releases':
                        written = await self.sync_releases(repo, full_refresh)
                    elif resource == 'workflow_runs':
                        written = await self.sync_workflow_runs(repo, full_refresh)
                    else:
                        written = await self.sync_updated(repo, resource, full_refresh)
                    rows[resource] += written
                    if progress is not None:
                        progress.rows_written[resource] = (
                            progress.rows_written.get(resource, 0) + written
                        )
                if progress is not None:
                    progress.repos_done += 1

        try:
            async with asyncio.TaskGroup() as group:
                for repo, needed in pending:
                    group.create_task(sync_one(repo, needed))
        except ExceptionGroup as errors:
            raise errors.exceptions[0] from errors
        return SyncReport(
            repos_listed=len(listed),
            repos_skipped=len(listed) - len(pending),
            rows_written=rows,
            full_refetches=tuple(sorted(refetched)),
        )
