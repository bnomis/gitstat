#!/usr/bin/env python
"""Record the successful GitHub responses the fetch tests replay.

Sends wambatic's own GraphQL queries and REST requests to the live API and writes the
responses, trimmed to the fields the fetcher reads, to src/tests/fixtures/fetch/recorded.py,
then formats that file with ruff. The token comes from GITHUB_TOKEN or `gh auth token`, as
for wambatic itself, and is never written out. A fine-grained token is refused the
stargazers, and a classic one sees only its own repositories' stargazers (an empty list
elsewhere), so the stargazers and forks are recorded from a repository of the recording account:
run with GITHUB_TOKEN unset to use the GitHub CLI's classic token.

The GraphQL responses are recorded whole: the queries already select only what is read. The
REST lists are asked for a short page (REST_PAGE), because the tests read a page's shape, not
its length.
"""

import datetime
import hashlib
import json
import pathlib
import pprint
import subprocess
import sys
import urllib.parse
import urllib.request

import wambatic.fetch.auth
import wambatic.fetch.queries
import wambatic.version

API = 'https://api.github.com'
OUT = pathlib.Path(__file__).resolve().parent.parent / 'src/tests/fixtures/fetch/recorded.py'
REST_PAGE = 5

LISTING_OWNER = 'octocat'
ORGANIZATION = 'github'
# A repository with a short history, for the listing, history, compare and commit-node calls.
HISTORY_OWNER, HISTORY_NAME = 'octocat', 'Hello-World'
# A small public repository with pull requests (one by a bot), issues, releases (one a
# prerelease) and Actions runs, so each page is short and every field is present.
FLOW_OWNER, FLOW_NAME = 'miguelangellv', 'ha-gas-station-spain'
# A repository of the recording account with stars and forks (see the module docstring).
STAR_OWNER, STAR_NAME = 'bnomis', 'ab2cb'
# A pull request reviewed by GitHub Copilot, for the type and login of an automatic reviewer.
BOT_REVIEW_OWNER, BOT_REVIEW_NAME, BOT_REVIEW_NUMBER = 'microsoft', 'vscode', 345267

# The review selection of PULL_REQUESTS, on one pull request.
PULL_REQUEST_REVIEWS = """
query PullRequestReviews($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviews(first: 20, states: [APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED]) {
        nodes { submittedAt author { __typename login } }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""

RECORDED_QUERIES = (
    'COMMIT_COUNTS',
    'COMMIT_HISTORY',
    'ISSUES',
    'OWNER_REPOSITORIES',
    'PULL_REQUESTS',
    'RELEASES',
    'REPOSITORY',
    'STARGAZERS',
)
RUN_FIELDS = (
    'id',
    'name',
    'path',
    'event',
    'head_branch',
    'status',
    'conclusion',
    'created_at',
    'updated_at',
    'run_started_at',
    'run_attempt',
)


class RecordingError(Exception):
    """A request, the fixture file or its formatting failed; reported in one line by `main`."""


def query_sha256(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


class Recorder:
    def __init__(self, token: str) -> None:
        self.token = token

    def send(
        self, method: str, path: str, params: dict[str, str] | None = None, body: object = None
    ) -> tuple[object, dict[str, str]]:
        url = f'{API}{path}' + ('' if not params else f'?{urllib.parse.urlencode(params)}')
        request = urllib.request.Request(
            url,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                'Accept': 'application/vnd.github+json',
                'Authorization': f'Bearer {self.token}',
                'User-Agent': f'wambatic/{wambatic.version.VERSION}',
                'X-GitHub-Api-Version': '2022-11-28',
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response), dict(response.headers)
        except (OSError, ValueError) as error:
            # auditme: accept[except-interpolation] the HTTP or decoding reason is the payload
            raise RecordingError(f'{method} {url} failed: {error}') from error

    def graphql(self, query: str, **variables: object) -> dict[str, object]:
        body, _ = self.send('POST', '/graphql', body={'query': query, 'variables': variables})
        if not isinstance(body, dict) or 'errors' in body:
            raise RuntimeError(f'GraphQL error: {body!r}')
        return body

    def rest(self, path: str, params: dict[str, str] | None = None) -> object:
        return self.send('GET', path, params)[0]


def pick(node: object, fields: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(node, dict):
        raise RuntimeError(f'Expected an object, got {node!r}')
    return {field: node[field] for field in fields if field in node}


def compare_commit(node: dict[str, object]) -> dict[str, object]:
    """A compare commit trimmed to what `parse_compare_commit` reads."""
    commit = node['commit']
    account = node['author']
    parents = node['parents']
    if not isinstance(commit, dict) or not isinstance(parents, list):
        raise RuntimeError(f'Unexpected compare commit: {node!r}')
    return {
        'sha': node['sha'],
        'commit': {'author': pick(commit['author'], ('date',))},
        'author': None if account is None else pick(account, ('login',)),
        'parents': [pick(parent, ('sha',)) for parent in parents],
    }


def record(recorder: Recorder) -> dict[str, object]:
    queries = wambatic.fetch.queries
    hello = {'owner': HISTORY_OWNER, 'name': HISTORY_NAME}
    flow = {'owner': FLOW_OWNER, 'name': FLOW_NAME}
    flow_path = f'/repos/{FLOW_OWNER}/{FLOW_NAME}'
    hello_path = f'/repos/{HISTORY_OWNER}/{HISTORY_NAME}'
    stars = {'owner': STAR_OWNER, 'name': STAR_NAME}

    history = recorder.graphql(queries.COMMIT_HISTORY, cursor=None, **hello)
    commits = history['data']['repository']['defaultBranchRef']['target']['history']['nodes']  # type: ignore[index]
    compare = recorder.rest(
        f'{hello_path}/compare/{commits[-1]["oid"]}...{commits[0]["oid"]}',
        {'per_page': '100', 'page': '1'},
    )
    compared = pick(compare, ('status', 'ahead_by', 'behind_by', 'total_commits'))
    compared['commits'] = [compare_commit(node) for node in compare['commits']]  # type: ignore[index]
    oids = [node['sha'] for node in compared['commits']]  # type: ignore[attr-defined]
    counts_variables = {**hello, **{f'o{i}': oid for i, oid in enumerate(oids)}}

    repo, repo_headers = recorder.send('GET', hello_path)
    runs = recorder.rest(
        f'{flow_path}/actions/runs',
        {'per_page': str(REST_PAGE), 'exclude_pull_requests': 'true', 'page': '1'},
    )
    run_nodes = runs['workflow_runs']  # type: ignore[index]
    forks = recorder.rest(
        f'/repos/{STAR_OWNER}/{STAR_NAME}/forks',
        {'sort': 'newest', 'per_page': str(REST_PAGE), 'page': '1'},
    )
    return {
        'OWNER_REPOSITORIES_OK': recorder.graphql(
            queries.OWNER_REPOSITORIES, login=LISTING_OWNER, cursor=None
        ),
        'REPOSITORY_OK': recorder.graphql(queries.REPOSITORY, **hello),
        'COMMIT_HISTORY_OK': history,
        'COMPARE_AHEAD': compared,
        'COMMIT_COUNTS_OK': recorder.graphql(queries.commit_counts(len(oids)), **counts_variables),
        'REPO': pick(repo, ('id', 'full_name', 'default_branch')),
        'REPO_ETAG': repo_headers['ETag'],
        'USER_OK': pick(recorder.rest(f'/users/{LISTING_OWNER}'), ('login', 'type')),
        'ORGANIZATION_OK': pick(recorder.rest(f'/users/{ORGANIZATION}'), ('login', 'type')),
        'PULL_REQUESTS_OK': recorder.graphql(queries.PULL_REQUESTS, cursor=None, **flow),
        'ISSUES_OK': recorder.graphql(queries.ISSUES, cursor=None, **flow),
        'RELEASES_OK': recorder.graphql(queries.RELEASES, cursor=None, **flow),
        'WORKFLOW_RUNS_OK': {
            'total_count': runs['total_count'],  # type: ignore[index]
            'workflow_runs': [pick(node, RUN_FIELDS) for node in run_nodes],
        },
        'WORKFLOW_RUN_OK': pick(
            recorder.rest(f'{flow_path}/actions/runs/{run_nodes[0]["id"]}'), RUN_FIELDS
        ),
        'STARGAZERS_OK': recorder.graphql(queries.STARGAZERS, cursor=None, **stars),
        'FORKS_OK': [pick(node, ('id', 'created_at')) for node in forks],  # type: ignore[attr-defined]
        'BOT_REVIEWS_OK': recorder.graphql(
            PULL_REQUEST_REVIEWS,
            owner=BOT_REVIEW_OWNER,
            name=BOT_REVIEW_NAME,
            number=BOT_REVIEW_NUMBER,
        ),
    }


def module_text(recorded_at: str, responses: dict[str, object]) -> str:
    hashes = {
        name: query_sha256(getattr(wambatic.fetch.queries, name)) for name in RECORDED_QUERIES
    }
    lines = [
        f'"""Successful GitHub responses recorded from the live API on {recorded_at[:10]}.',
        '',
        'Written by bin/record-fixtures.sh; do not edit by hand, re-run it. The subjects are',
        f'{LISTING_OWNER} (the listing), {HISTORY_OWNER}/{HISTORY_NAME} (repository, history,',
        f'compare, commit counts, REST repo), {FLOW_OWNER}/{FLOW_NAME} (pull requests, issues,',
        f'releases, workflow runs), {STAR_OWNER}/{STAR_NAME} (stargazers, forks), the users',
        f'{LISTING_OWNER} and {ORGANIZATION}, and one review page of',
        f'{BOT_REVIEW_OWNER}/{BOT_REVIEW_NAME}#{BOT_REVIEW_NUMBER} (BOT_REVIEWS_OK). REST bodies',
        'are trimmed to the fields the fetcher reads.',
        '"""',
        '',
        '# ruff: noqa: E501',
        '',
        f'RECORDED_AT = {recorded_at!r}',
        f'WAMBATIC_VERSION = {wambatic.version.VERSION!r}',
        '# sha256 of each wambatic.fetch.queries text the recording was made with',
        f'QUERY_SHA256 = {pprint.pformat(hashes, width=99, sort_dicts=True)}',
    ]
    for name, value in responses.items():
        lines += ['', f'{name} = {pprint.pformat(value, width=99, sort_dicts=False)}']
    return '\n'.join(lines) + '\n'


def write_fixtures(text: str) -> None:
    """Write `text` to OUT and format it with ruff.

    Raises:
        RecordingError: when the file cannot be written or ruff cannot format it.
    """
    try:
        OUT.write_text(text, encoding='utf-8')
    except OSError as error:
        # auditme: accept[except-interpolation] the OS reason says what to fix
        raise RecordingError(f'cannot write {OUT}: {error.strerror or error}') from error
    try:
        subprocess.run(['ruff', 'format', '--quiet', str(OUT)], check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        # auditme: accept[except-interpolation] the reason ruff could not run is the payload
        raise RecordingError(f'cannot format {OUT} with ruff: {error}') from error


def main() -> int:
    recorder = Recorder(wambatic.fetch.auth.resolve_token())
    recorded_at = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    try:
        write_fixtures(module_text(recorded_at, record(recorder)))
    except RecordingError as error:
        # auditme: accept[except-interpolation] the one line is the failure's own message
        print(f'record-fixtures: {error}', file=sys.stderr)
        return 1
    print(OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
