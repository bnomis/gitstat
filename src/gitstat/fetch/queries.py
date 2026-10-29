OWNER_REPOSITORIES = """
query OwnerRepositories($login: String!, $cursor: String) {
  repositoryOwner(login: $login) {
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {
      pageInfo { hasNextPage endCursor }
      nodes { nameWithOwner }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""
