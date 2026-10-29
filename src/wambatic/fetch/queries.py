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

COMMIT_NODES = """
query CommitNodes($ids: [ID!]!) {
  nodes(ids: $ids) { ... on Commit { oid additions deletions } }
  rateLimit { cost remaining resetAt }
}
"""
