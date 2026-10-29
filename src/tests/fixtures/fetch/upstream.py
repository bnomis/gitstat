"""A fake GitHub holding repositories with linear default-branch histories.

It answers the queries and the compare call the fetcher sends, so sync tests change the
upstream between runs (push a commit, rewrite history) instead of hand-ordering canned replies.
Response bodies are built by the helpers in `responses`, which cite the documentation each shape
comes from.
"""

import dataclasses
import datetime
import re

import tests.fixtures.fetch.responses
import tests.fixtures.fetch.server

COMPARE_PATH = re.compile(r'/repos/(?P<name>[^/]+/[^/]+)/compare/(?P<base>\w+)\.\.\.(?P<head>\w+)')


@dataclasses.dataclass(slots=True)
class FakeCommit:
    oid: str
    authored_at: datetime.datetime
    login: str | None = 'octocat'
    additions: int = 1
    deletions: int = 0
    parents: int = 1


@dataclasses.dataclass(slots=True)
class FakeRepo:
    name: str
    history: list[FakeCommit]
    pushed_at: datetime.datetime = tests.fixtures.fetch.responses.HELLO_PUSHED_AT
    updated_at: datetime.datetime = tests.fixtures.fetch.responses.HELLO_UPDATED_AT
    is_fork: bool = False
    is_archived: bool = False
    branch: str = 'main'

    @property
    def head(self) -> str | None:
        return self.history[-1].oid if self.history else None

    def node(self) -> dict[str, object]:
        return tests.fixtures.fetch.responses.repo_node(
            self.name,
            head=self.head if self.history else None,
            pushed_at=self.pushed_at,
            updated_at=self.updated_at,
            branch=self.branch,
            is_fork=self.is_fork,
            is_archived=self.is_archived,
        )

    def push(self, *commits: FakeCommit) -> None:
        """Add commits to the branch and move `pushedAt` and `updatedAt` forward."""
        self.history.extend(commits)
        self.pushed_at += datetime.timedelta(hours=1)
        self.updated_at += datetime.timedelta(hours=1)


class Upstream:
    def __init__(self, repos: list[FakeRepo]) -> None:
        self.repos = {repo.name: repo for repo in repos}
        self.owner_page_size = 100
        self.history_page_size = 100
        self.failing_history: set[str] = set()
        self.history_delay = 0.0
        self.unknown_base = 'not found'
        self.dropped_nodes: set[str] = set()

    def respond(
        self, received: tests.fixtures.fetch.server.Received
    ) -> tests.fixtures.fetch.server.Canned:
        if received.path == '/graphql':
            return self.graphql(received)
        match = COMPARE_PATH.fullmatch(received.path)
        if match:
            return self.compare(match, received.query)
        return tests.fixtures.fetch.server.Canned(404, tests.fixtures.fetch.responses.NOT_FOUND)

    def graphql(
        self, received: tests.fixtures.fetch.server.Received
    ) -> tests.fixtures.fetch.server.Canned:
        body = received.json
        assert isinstance(body, dict)
        query, variables = str(body['query']), body['variables']
        assert isinstance(variables, dict)
        headers = tests.fixtures.fetch.responses.RATE_HEADERS
        if 'query OwnerRepositories' in query:
            return tests.fixtures.fetch.server.Canned(200, self.owner_page(variables), headers)
        if 'query Repository(' in query:
            repo = self.repos.get(f'{variables["owner"]}/{variables["name"]}')
            if repo is None:
                return tests.fixtures.fetch.server.Canned(
                    200, tests.fixtures.fetch.responses.GRAPHQL_REPOSITORY_NOT_FOUND, headers
                )
            return tests.fixtures.fetch.server.Canned(
                200, tests.fixtures.fetch.responses.repository_response(repo.node()), headers
            )
        if 'query CommitHistory' in query:
            name = f'{variables["owner"]}/{variables["name"]}'
            if name in self.failing_history:
                return tests.fixtures.fetch.server.Canned(
                    500, tests.fixtures.fetch.responses.SERVER_ERROR, delay=self.history_delay
                )
            return tests.fixtures.fetch.server.Canned(
                200, self.history_page(name, variables['cursor']), headers, self.history_delay
            )
        if 'query CommitNodes' in query:
            return tests.fixtures.fetch.server.Canned(200, self.nodes(variables['ids']), headers)
        raise AssertionError(f'unexpected query: {query}')

    def owner_page(self, variables: dict[str, object]) -> dict[str, object]:
        owner = str(variables['login'])
        repos = [r for r in self.repos.values() if r.name.split('/')[0].lower() == owner.lower()]
        start = int(str(variables['cursor'] or 0))
        end = start + self.owner_page_size
        return tests.fixtures.fetch.responses.owner_page(
            [repo.node() for repo in repos[start:end]], end < len(repos), str(end)
        )

    def history_page(self, name: str, cursor: object) -> dict[str, object]:
        newest_first = list(reversed(self.repos[name].history))
        start = int(str(cursor or 0))
        end = start + self.history_page_size
        return tests.fixtures.fetch.responses.history_page(
            [
                tests.fixtures.fetch.responses.history_node(
                    c.oid, c.authored_at, c.login, c.additions, c.deletions, c.parents
                )
                for c in newest_first[start:end]
            ],
            end < len(newest_first),
            str(end),
        )

    def nodes(self, ids: object) -> dict[str, object]:
        assert isinstance(ids, list)
        by_node_id = {f'C_{c.oid}': c for repo in self.repos.values() for c in repo.history}
        return tests.fixtures.fetch.responses.nodes_response(
            [
                {
                    'oid': by_node_id[i].oid,
                    'additions': by_node_id[i].additions,
                    'deletions': by_node_id[i].deletions,
                }
                if i in by_node_id and i not in self.dropped_nodes
                else None
                for i in ids
            ]
        )

    def compare(
        self, match: re.Match[str], query: dict[str, str]
    ) -> tests.fixtures.fetch.server.Canned:
        repo = self.repos.get(match['name'])
        oids = [c.oid for c in repo.history] if repo else []
        if match['head'] not in oids:
            return tests.fixtures.fetch.server.Canned(404, tests.fixtures.fetch.responses.NOT_FOUND)
        head = oids.index(match['head'])
        if match['base'] not in oids:
            if self.unknown_base == 'not found':
                return tests.fixtures.fetch.server.Canned(
                    404, tests.fixtures.fetch.responses.NOT_FOUND
                )
            return tests.fixtures.fetch.server.Canned(
                200, tests.fixtures.fetch.responses.compare_response('diverged', [])
            )
        base = oids.index(match['base'])
        if base > head:
            return tests.fixtures.fetch.server.Canned(
                200, tests.fixtures.fetch.responses.compare_response('behind', [])
            )
        assert repo is not None
        commits = [
            tests.fixtures.fetch.responses.compare_commit(c.oid, c.authored_at, c.login, c.parents)
            for c in repo.history[base + 1 : head + 1]
        ]
        per_page, page = int(query['per_page']), int(query['page'])
        status = 'ahead' if commits else 'identical'
        shown = commits[(page - 1) * per_page : page * per_page]
        return tests.fixtures.fetch.server.Canned(
            200, tests.fixtures.fetch.responses.compare_response(status, shown, total=len(commits))
        )

    def requests(self, server: tests.fixtures.fetch.server.ReplayServer) -> list[str]:
        """The kind of each request the server received, in order."""
        kinds = {
            'query OwnerRepositories': 'listing',
            'query Repository(': 'repository',
            'query CommitHistory': 'history',
            'query CommitNodes': 'nodes',
        }
        found: list[str] = []
        for received in server.received:
            if received.path != '/graphql':
                found.append('compare')
                continue
            assert isinstance(received.json, dict)
            query = str(received.json['query'])
            found.append(next(kind for key, kind in kinds.items() if key in query))
        return found
