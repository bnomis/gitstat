import gitstat.fetch.queries


def test_every_query_selects_rate_limit() -> None:
    queries = {
        name: value
        for name, value in vars(gitstat.fetch.queries).items()
        if name.isupper() and isinstance(value, str)
    }
    assert queries
    for name, text in queries.items():
        assert 'rateLimit { cost remaining resetAt }' in text, name
