import collections
import collections.abc
import datetime
import typing

import wambatic.fetch.base
import wambatic.stats.base
import wambatic.stats.buckets

POPULARITY_METRICS = (
    ('stars_added', 'count'),
    ('stars_total', 'count'),
    ('forks_added', 'count'),
    ('forks_total', 'count'),
)
OTHER = 'Other'
Tables = dict[str, list[dict[str, typing.Any]]]


def counted(
    moments: list[datetime.datetime],
    buckets: list[wambatic.stats.base.Bucket],
    tz: datetime.tzinfo,
    since: datetime.date,
    until: datetime.date,
) -> tuple[list[int], list[int]]:
    """The events in each bucket and the events at or before the end of each: those before
    `since` count in the totals, those after `until` in nothing."""
    place = wambatic.stats.buckets.placer(buckets, tz, since, until)
    added = [0] * len(buckets)
    earlier = 0
    for moment in moments:
        if (index := place(moment)) is not None:
            added[index] += 1
        elif moment.astimezone(tz).date() < since:
            earlier += 1
    running = earlier
    totals: list[int] = []
    for count in added:
        running += count
        totals.append(running)
    return added, totals


def popularity_table(
    repos: collections.abc.Iterable[wambatic.fetch.base.Repo],
) -> list[dict[str, typing.Any]]:
    """GitHub's own counts for each repository at the last listing, most starred first."""
    return [
        {
            'repo': repo.name_with_owner,
            'stars': repo.stargazer_count,
            'forks': repo.fork_count,
            'watchers': repo.watcher_count,
        }
        for repo in sorted(repos, key=lambda r: (-r.stargazer_count, r.name_with_owner))
    ]


def languages_table(
    repos: collections.abc.Iterable[wambatic.fetch.base.Repo],
) -> list[dict[str, typing.Any]]:
    """The bytes and share of each language over the repositories, largest first. What a
    repository's listed languages leave of its total is one `Other` row, last."""
    sizes: collections.Counter[str] = collections.Counter()
    other = 0
    for repo in repos:
        sizes.update(dict(repo.languages))
        other += max(repo.languages_size - sum(size for _, size in repo.languages), 0)
    rows = sorted(sizes.items(), key=lambda item: (-item[1], item[0]))
    if other:
        rows.append((OTHER, other))
    total = sum(size for _, size in rows)
    return [
        {'language': name, 'bytes': size, 'share': size / total if total else 0.0}
        for name, size in rows
    ]


def aggregate(
    stars: collections.abc.Iterable[wambatic.fetch.base.StarEvent],
    forks: collections.abc.Iterable[wambatic.fetch.base.Fork],
    repos: collections.abc.Iterable[wambatic.fetch.base.Repo],
    buckets: list[wambatic.stats.base.Bucket],
    tz: datetime.tzinfo,
    since: datetime.date,
    until: datetime.date,
) -> tuple[list[wambatic.stats.base.Series], Tables]:
    """The popularity series for the stars and forks, each event placed by its own local date in
    `tz`, and the `popularity` and `languages` tables for the repositories.

    The totals start from the events before `since`. Every value is a whole number, zero in an
    empty bucket."""
    repos = list(repos)
    added_stars, total_stars = counted([s.starred_at for s in stars], buckets, tz, since, until)
    added_forks, total_forks = counted([f.created_at for f in forks], buckets, tz, since, until)
    found = {
        'stars_added': added_stars,
        'stars_total': total_stars,
        'forks_added': added_forks,
        'forks_total': total_forks,
    }
    series = [
        wambatic.stats.base.Series(name, unit, dict(zip(buckets, found[name], strict=True)))
        for name, unit in POPULARITY_METRICS
    ]
    tables: Tables = {'popularity': popularity_table(repos), 'languages': languages_table(repos)}
    return series, tables
