OWNER_REPOSITORIES = """
query OwnerRepositories($login: String!, $cursor: String) {
  repositoryOwner(login: $login) {
    repositories(
      first: 100, after: $cursor, ownerAffiliations: OWNER,
      orderBy: {field: PUSHED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner isArchived isFork pushedAt updatedAt
        defaultBranchRef { name target { oid } }
        pullRequests(first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes { updatedAt }
        }
        issues(first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) { nodes { updatedAt } }
        releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
          totalCount
          nodes { updatedAt }
        }
        stargazerCount forkCount watchers { totalCount }
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          totalSize
          edges { size node { name } }
        }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""

REPOSITORY = """
query Repository($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner isArchived isFork pushedAt updatedAt
    defaultBranchRef { name target { oid } }
    pullRequests(first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes { updatedAt }
    }
    issues(first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) { nodes { updatedAt } }
    releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
      totalCount
      nodes { updatedAt }
    }
    stargazerCount forkCount watchers { totalCount }
    languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
      totalSize
      edges { size node { name } }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""

COMMIT_HISTORY = """
query CommitHistory($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              oid authoredDate author { user { login } } additions deletions
              parents { totalCount }
            }
          }
        }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""

COMMIT_COUNT_PAGE = 100


def commit_counts(count: int) -> str:
    """The query for the line counts of `count` commits, looked up by object id.

    Each commit is one aliased `object(oid:)` field with its own `$oN` variable, so no GraphQL
    global node id is sent: `nodes(ids:)` with a REST `node_id` draws a deprecation warning for
    every commit of a repository old enough to have legacy ids.
    """
    variables = ', '.join(f'$o{i}: GitObjectID!' for i in range(count))
    fields = '\n'.join(
        f'    c{i}: object(oid: $o{i}) {{ ... on Commit {{ oid additions deletions }} }}'
        for i in range(count)
    )
    return (
        f'\nquery CommitCounts($owner: String!, $name: String!, {variables}) {{\n'
        f'  repository(owner: $owner, name: $name) {{\n{fields}\n  }}\n'
        '  rateLimit { cost remaining resetAt }\n}\n'
    )


# The full-page form; its hash stands for the builder in the cache identity.
COMMIT_COUNTS = commit_counts(COMMIT_COUNT_PAGE)

PULL_REQUESTS = """
query PullRequests($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: 100, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number state createdAt updatedAt mergedAt closedAt additions deletions
        author { __typename login }
        reviews(first: 20, states: [APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED]) {
          nodes { submittedAt author { __typename login } }
        }
        labels(first: 20) { nodes { name } }
        commits(first: 1) { nodes { commit { authoredDate } } }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""

ISSUES = """
query Issues($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number state createdAt updatedAt closedAt
        author { __typename login }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""

RELEASES = """
query Releases($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    releases(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { tagName createdAt publishedAt isDraft isPrerelease }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""

STARGAZERS = """
query Stargazers($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    stargazers(first: 100, after: $cursor, orderBy: {field: STARRED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      edges { starredAt node { id } }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""
