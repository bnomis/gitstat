import bisect
import collections.abc
import dataclasses
import datetime
import typing

import gitstat.fetch.base
import gitstat.settings
import gitstat.stats.base
import gitstat.stats.buckets

Bucket = gitstat.stats.base.Bucket
Series = gitstat.stats.base.Series

UNATTRIBUTED = 'unattributed'
TOTAL_METRICS = (
    ('commits', 'count'),
    ('contributors', 'count'),
    ('active_days', 'days'),
    ('lines_added', 'lines'),
    ('lines_deleted', 'lines'),
    ('lines_net', 'lines'),
)
BREAKDOWN_METRICS = ('commits', 'lines_added', 'lines_deleted', 'lines_net')
Tables = dict[str, list[dict[str, typing.Any]]]


@dataclasses.dataclass(slots=True)
class Tally:
    """What the commits of one group add up to, in one bucket or over the whole range."""

    commits: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    logins: set[str] = dataclasses.field(default_factory=set)
    days: set[datetime.date] = dataclasses.field(default_factory=set)

    def add(self, commit: gitstat.fetch.base.Commit, day: datetime.date, lines: bool) -> None:
        self.commits += 1
        self.days.add(day)
        if lines:
            self.lines_added += commit.additions
            self.lines_deleted += commit.deletions

    def value(self, metric: str) -> float:
        match metric:
            case 'commits':
                return self.commits
            case 'contributors':
                return len(self.logins)
            case 'active_days':
                return len(self.days)
            case 'lines_added':
                return self.lines_added
            case 'lines_deleted':
                return self.lines_deleted
            case _:
                return self.lines_added - self.lines_deleted


def locate(day: datetime.date, starts: list[datetime.date], end: datetime.date | None) -> int:
    index = bisect.bisect_right(starts, day) - 1
    if index < 0 or (end is not None and day >= end):
        raise ValueError(f'{day} is outside the buckets')
    return index


def series_of(
    metric: str,
    unit: str,
    buckets: list[Bucket],
    tallies: collections.abc.Sequence[Tally],
    by: str | None = None,
    by_kind: typing.Literal['author', 'repo'] | None = None,
) -> Series:
    points = {bucket: tally.value(metric) for bucket, tally in zip(buckets, tallies, strict=True)}
    return Series(metric, unit, points, by, by_kind)


def aggregate(
    commits: collections.abc.Iterable[gitstat.fetch.base.Commit],
    buckets: list[Bucket],
    tz: datetime.tzinfo,
    settings: gitstat.settings.StatsSettings,
    *,
    by_author: bool,
    by_repo: bool,
) -> tuple[list[Series], Tables]:
    """The activity series and tables for `commits`, which the caller has already restricted to
    the range `buckets` covers; a commit outside it raises ValueError."""
    bots = {login.casefold() for login in settings.bot_logins}
    starts = [bucket.start for bucket in buckets]
    end = None
    if buckets and buckets[0].label != 'total':
        granularity = gitstat.stats.buckets.bucket_granularity(buckets[-1])
        end = gitstat.stats.buckets.next_start(buckets[-1].start, granularity)
    totals = [Tally() for _ in buckets]
    authors: dict[str | None, list[Tally]] = {}
    spellings: dict[str | None, str] = {}
    repos: dict[str, list[Tally]] = {}
    overall: dict[str | None, Tally] = {}
    for commit in commits:
        day = commit.authored_at.astimezone(tz).date()
        index = locate(day, starts, end)
        lines = not (settings.exclude_merge_commits and commit.is_merge)
        key = None if commit.author_login is None else commit.author_login.casefold()
        spellings.setdefault(key, UNATTRIBUTED if key is None else str(commit.author_login))
        totals[index].add(commit, day, lines)
        if key is not None and key not in bots:
            totals[index].logins.add(key)
        overall.setdefault(key, Tally()).add(commit, day, lines)
        if by_author:
            authors.setdefault(key, [Tally() for _ in buckets])[index].add(commit, day, lines)
        if by_repo:
            repos.setdefault(commit.repo, [Tally() for _ in buckets])[index].add(commit, day, lines)
    series = [series_of(metric, unit, buckets, totals) for metric, unit in TOTAL_METRICS]
    breakdowns: list[tuple[str, str, list[Tally]]] = [
        ('author', spellings[key], tallies) for key, tallies in authors.items()
    ] + [('repo', name, tallies) for name, tallies in repos.items()]
    for kind, by, tallies in sorted(breakdowns, key=lambda item: (item[0], item[1])):
        for metric in BREAKDOWN_METRICS:
            unit = 'count' if metric == 'commits' else 'lines'
            series.append(series_of(metric, unit, buckets, tallies, by, kind))  # type: ignore[arg-type]
    rows: list[dict[str, typing.Any]] = [
        {
            'login': spellings[key],
            'commits': tally.commits,
            'lines_added': tally.lines_added,
            'lines_deleted': tally.lines_deleted,
            'lines_net': tally.lines_added - tally.lines_deleted,
            'active_days': len(tally.days),
        }
        for key, tally in overall.items()
        if key is None or key not in bots
    ]
    rows.sort(key=lambda row: (-row['commits'], row['login']))
    return series, {'top_contributors': rows}
