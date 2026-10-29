import collections.abc
import datetime
import typing

import gitstat.fetch.base
import gitstat.stats.activity
import gitstat.stats.base
import gitstat.stats.buckets
import gitstat.stats.errors

RESOURCES_BY_GROUP = {
    'activity': frozenset({'commits'}),
    'flow': frozenset({'issues', 'pull_requests'}),
    'delivery': frozenset({'releases', 'star_events', 'workflow_runs'}),
}
BUILT_GROUPS = frozenset({'activity'})
UNBUILT_GROUP_STEPS = {'flow': 6, 'delivery': 8}
UNBUILT_ACTIVITY_METRICS = (
    ('stars', 'stars come from star_events, which step 8 fetches'),
    ('forks', 'forks has no fetch resource yet; it is specified before step 8'),
    ('watchers', 'watchers has no fetch resource yet; it is specified before step 8'),
    ('languages', 'languages has no fetch resource yet; it is specified before step 8'),
)
ONE_DAY = datetime.timedelta(days=1)


def resources_for(groups: frozenset[str]) -> frozenset[str]:
    """The fetch resources the groups read, for the caller's Fetcher.sync before compute."""
    unknown = sorted(groups - gitstat.stats.base.GROUPS)
    if unknown:
        raise gitstat.stats.errors.UnknownGroupError(f'unknown groups: {", ".join(unknown)}')
    return frozenset().union(*(RESOURCES_BY_GROUP[group] for group in groups))


def utc_midnight(day: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(), tzinfo=datetime.UTC)


def unavailable(groups: frozenset[str]) -> list[dict[str, typing.Any]]:
    rows: list[dict[str, typing.Any]] = [
        {
            'metric': group,
            'reason': f'the {group} group is built in implementation step {step}',
        }
        for group, step in sorted(UNBUILT_GROUP_STEPS.items())
        if group in groups
    ]
    if 'activity' in groups:
        rows.extend(
            {'metric': metric, 'reason': reason} for metric, reason in UNBUILT_ACTIVITY_METRICS
        )
    return rows


async def read_commits(
    subject: gitstat.fetch.base.Subject,
    fetcher: gitstat.fetch.base.Fetcher,
    repos: list[gitstat.fetch.base.Repo],
    request: gitstat.stats.base.StatsRequest,
) -> list[gitstat.fetch.base.Commit]:
    """The cached commits whose local date is inside the requested bounds, from the subject's
    own authors only for a user subject."""
    lo = None if request.since is None else utc_midnight(request.since) - ONE_DAY
    hi = None if request.until is None else utc_midnight(request.until + ONE_DAY) + ONE_DAY
    login = subject.login.casefold()
    kept: list[gitstat.fetch.base.Commit] = []
    for repo in repos:
        async for commit in fetcher.commits(repo, lo, hi):
            day = commit.authored_at.astimezone(request.tz).date()
            if request.since is not None and day < request.since:
                continue
            if request.until is not None and day > request.until:
                continue
            if subject.kind == 'user' and (commit.author_login or '').casefold() != login:
                continue
            kept.append(commit)
    return kept


async def compute(
    subject: gitstat.fetch.base.Subject,
    fetcher: gitstat.fetch.base.Fetcher,
    request: gitstat.stats.base.StatsRequest,
    *,
    clock: collections.abc.Callable[[], datetime.datetime] | None = None,
) -> gitstat.stats.base.StatsResult:
    """All requested metric groups for the subject, from the cache, bucketed by
    request.granularity. Never syncs: the caller runs Fetcher.sync first, or not at all for
    --no-fetch. `clock` (default: now in UTC) gives today's date when `until` is None."""
    resources_for(request.groups)
    if request.by_author and subject.kind == 'user':
        raise gitstat.stats.errors.InvalidRequestError('by_author is not meaningful for a user')
    if request.since is not None and request.until is not None and request.since > request.until:
        raise gitstat.stats.errors.InvalidRangeError(
            f'since {request.since} is after until {request.until}'
        )
    built = request.groups & BUILT_GROUPS
    if not built:
        steps = ', '.join(
            f'{group} (step {UNBUILT_GROUP_STEPS[group]})' for group in sorted(request.groups)
        )
        raise gitstat.stats.errors.EmptySubjectError(f'no requested group is built yet: {steps}')
    repos = await fetcher.repos(subject)
    if not repos:
        raise gitstat.stats.errors.EmptySubjectError(
            f'the cache holds no repositories for {subject.login}'
        )
    commits = await read_commits(subject, fetcher, repos, request)
    if not commits:
        raise gitstat.stats.errors.EmptySubjectError('no commits in the cache for this range')
    now = (clock or (lambda: datetime.datetime.now(datetime.UTC)))()
    tz = request.tz
    granularity = request.granularity
    since = request.since
    if since is None:
        earliest = min(commit.authored_at for commit in commits).astimezone(tz).date()
        since = (
            earliest
            if granularity is gitstat.stats.base.Granularity.TOTAL
            else gitstat.stats.buckets.bucket_start(earliest, granularity)
        )
    until = request.until if request.until is not None else now.astimezone(tz).date()
    if since > until:
        raise gitstat.stats.errors.InvalidRangeError(f'since {since} is after until {until}')
    commits = [c for c in commits if since <= c.authored_at.astimezone(tz).date() <= until]
    if not commits:
        raise gitstat.stats.errors.EmptySubjectError('no commits in the cache for this range')
    buckets = gitstat.stats.buckets.bucket_range(since, until, granularity)
    series, tables = gitstat.stats.activity.aggregate(
        commits,
        buckets,
        tz,
        request.settings,
        by_author=request.by_author,
        by_repo=subject.kind != 'repo',
    )
    tables['unavailable'] = unavailable(request.groups)
    provenance = await fetcher.provenance(subject, resources_for(built))
    provenance['computed_at'] = now.astimezone(datetime.UTC).isoformat()
    provenance['timezone'] = str(tz)
    provenance['partial_buckets'] = ','.join(
        bucket.label for bucket in gitstat.stats.buckets.partial_buckets(since, until, buckets)
    )
    return gitstat.stats.base.StatsResult(
        subject=subject,
        request=request,
        since=since,
        until=until,
        series=series,
        tables=tables,
        provenance=provenance,
    )
