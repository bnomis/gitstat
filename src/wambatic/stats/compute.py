import collections.abc
import datetime
import typing

import wambatic.fetch.base
import wambatic.stats.activity
import wambatic.stats.base
import wambatic.stats.buckets
import wambatic.stats.delivery
import wambatic.stats.errors
import wambatic.stats.flow
import wambatic.stats.popularity

RESOURCES_BY_GROUP = {
    'activity': frozenset({'commits'}),
    'flow': frozenset({'issues', 'pull_requests'}),
    'delivery': frozenset({'pull_requests', 'releases', 'workflow_runs'}),
    'popularity': frozenset({'forks', 'star_events'}),
}


def resources_for(groups: frozenset[str]) -> frozenset[str]:
    """The fetch resources the groups read, for the caller's Fetcher.sync before compute."""
    unknown = sorted(groups - wambatic.stats.base.GROUPS)
    if unknown:
        raise wambatic.stats.errors.UnknownGroupError(f'unknown groups: {", ".join(unknown)}')
    return frozenset().union(*(RESOURCES_BY_GROUP[group] for group in groups))


def utc_midnight(day: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(), tzinfo=datetime.UTC)


async def read_commits(
    subject: wambatic.fetch.base.Subject,
    fetcher: wambatic.fetch.base.Fetcher,
    repos: list[wambatic.fetch.base.Repo],
    request: wambatic.stats.base.StatsRequest,
) -> list[wambatic.fetch.base.Commit]:
    """The cached commits whose local date is inside the requested bounds, from the subject's
    own authors only for a user subject."""
    lo = (
        None
        if request.since is None
        else utc_midnight(request.since) - wambatic.stats.buckets.ONE_DAY
    )
    hi = (
        None
        if request.until is None
        else utc_midnight(request.until + wambatic.stats.buckets.ONE_DAY)
        + wambatic.stats.buckets.ONE_DAY
    )
    login = subject.login.casefold()
    kept: list[wambatic.fetch.base.Commit] = []
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


async def read_flow(
    subject: wambatic.fetch.base.Subject,
    fetcher: wambatic.fetch.base.Fetcher,
    repos: list[wambatic.fetch.base.Repo],
    request: wambatic.stats.base.StatsRequest,
) -> tuple[list[wambatic.fetch.base.PullRequest], list[wambatic.fetch.base.Issue]]:
    """The cached pull requests and issues updated since a day before the requested start (every
    event of an item is at or before its `updated_at`), from the subject's own items only for a
    user subject. The flow aggregation keeps the events whose local date is in the range."""
    lo = (
        None
        if request.since is None
        else utc_midnight(request.since) - wambatic.stats.buckets.ONE_DAY
    )
    login = subject.login.casefold()

    def wanted(author: str | None) -> bool:
        return subject.kind != 'user' or (author or '').casefold() == login

    pulls: list[wambatic.fetch.base.PullRequest] = []
    issues: list[wambatic.fetch.base.Issue] = []
    for repo in repos:
        pulls.extend([p async for p in fetcher.pull_requests(repo, lo) if wanted(p.author_login)])
        issues.extend([i async for i in fetcher.issues(repo, lo) if wanted(i.author_login)])
    return pulls, issues


async def read_delivery(
    fetcher: wambatic.fetch.base.Fetcher,
    repos: list[wambatic.fetch.base.Repo],
    request: wambatic.stats.base.StatsRequest,
) -> tuple[
    list[wambatic.fetch.base.WorkflowRun],
    list[wambatic.fetch.base.Release],
    list[wambatic.fetch.base.PullRequest],
]:
    """Every cached release and pull request of the subject's repositories, and the runs created
    since a day before the requested start (all of them when `since` is None or a deploy workflow
    is set, since deployments are then runs and a lead time reaches back). No author filter: a
    release ships the repository's work, not one author's."""
    lo = (
        None
        if request.since is None or request.settings.deploy_workflow is not None
        else utc_midnight(request.since) - wambatic.stats.buckets.ONE_DAY
    )
    runs: list[wambatic.fetch.base.WorkflowRun] = []
    releases: list[wambatic.fetch.base.Release] = []
    pulls: list[wambatic.fetch.base.PullRequest] = []
    for repo in repos:
        runs.extend([run async for run in fetcher.workflow_runs(repo, lo)])
        releases.extend([release async for release in fetcher.releases(repo)])
        pulls.extend([pull async for pull in fetcher.pull_requests(repo, None)])
    return runs, releases, pulls


async def read_popularity(
    fetcher: wambatic.fetch.base.Fetcher, repos: list[wambatic.fetch.base.Repo]
) -> tuple[
    list[wambatic.fetch.base.StarEvent],
    list[wambatic.fetch.base.Fork],
    list[wambatic.fetch.base.Repo],
]:
    """Every cached star and fork of the subject's repositories, since a cumulative count reaches
    back before any range, and the repositories whose stargazers the token could not see (their
    stars are left out). No author filter: a star is given to a repository, not to an author."""
    stars: list[wambatic.fetch.base.StarEvent] = []
    forks: list[wambatic.fetch.base.Fork] = []
    hidden: list[wambatic.fetch.base.Repo] = []
    for repo in repos:
        if await fetcher.stars_hidden(repo):
            hidden.append(repo)
        else:
            stars.extend([star async for star in fetcher.star_events(repo)])
        forks.extend([fork async for fork in fetcher.forks(repo)])
    return stars, forks, hidden


async def compute(
    subject: wambatic.fetch.base.Subject,
    fetcher: wambatic.fetch.base.Fetcher,
    request: wambatic.stats.base.StatsRequest,
    *,
    clock: collections.abc.Callable[[], datetime.datetime] | None = None,
) -> wambatic.stats.base.StatsResult:
    """All requested metric groups for the subject, from the cache, bucketed by
    request.granularity. Never syncs: the caller runs Fetcher.sync first, or not at all for
    --no-fetch. `clock` (default: now in UTC) gives today's date when `until` is None."""
    resources_for(request.groups)
    if request.by_author and subject.kind == 'user':
        raise wambatic.stats.errors.InvalidRequestError('by_author is not meaningful for a user')
    if request.since is not None and request.until is not None and request.since > request.until:
        raise wambatic.stats.errors.InvalidRangeError(
            f'since {request.since} is after until {request.until}'
        )
    built = request.groups
    if not built:
        raise wambatic.stats.errors.EmptySubjectError(
            'no requested group: name at least one metric group'
        )
    repos = await fetcher.repos(subject)
    if not repos:
        raise wambatic.stats.errors.EmptySubjectError(
            f'the cache holds no repositories for {subject.login}'
        )
    commits: list[wambatic.fetch.base.Commit] = []
    pulls: list[wambatic.fetch.base.PullRequest] = []
    issues: list[wambatic.fetch.base.Issue] = []
    runs: list[wambatic.fetch.base.WorkflowRun] = []
    releases: list[wambatic.fetch.base.Release] = []
    delivery_pulls: list[wambatic.fetch.base.PullRequest] = []
    stars: list[wambatic.fetch.base.StarEvent] = []
    forks: list[wambatic.fetch.base.Fork] = []
    hidden: list[wambatic.fetch.base.Repo] = []
    if 'activity' in built:
        commits = await read_commits(subject, fetcher, repos, request)
    if 'flow' in built:
        pulls, issues = await read_flow(subject, fetcher, repos, request)
    if 'delivery' in built:
        runs, releases, delivery_pulls = await read_delivery(fetcher, repos, request)
    if 'popularity' in built:
        stars, forks, hidden = await read_popularity(fetcher, repos)
    empty = wambatic.stats.errors.EmptySubjectError(
        f'no {" or ".join(sorted(built))} records in the cache for this range'
    )
    popularity = 'popularity' in built
    if not (commits or pulls or issues or runs or releases or popularity):
        raise empty
    now = (clock or (lambda: datetime.datetime.now(datetime.UTC)))()
    tz = request.tz
    granularity = request.granularity
    until = request.until if request.until is not None else now.astimezone(tz).date()
    since = request.since
    if since is None:
        firsts = [commit.authored_at for commit in commits]
        firsts += [pull.created_at for pull in pulls] + [issue.created_at for issue in issues]
        firsts += [run.created_at for run in runs] + [release.published_at for release in releases]
        firsts += [star.starred_at for star in stars] + [fork.created_at for fork in forks]
        earliest = min(firsts).astimezone(tz).date() if firsts else until
        since = (
            earliest
            if granularity is wambatic.stats.base.Granularity.TOTAL
            else wambatic.stats.buckets.bucket_start(earliest, granularity)
        )
    if since > until:
        raise wambatic.stats.errors.InvalidRangeError(f'since {since} is after until {until}')
    commits = [c for c in commits if since <= c.authored_at.astimezone(tz).date() <= until]
    flow_found = wambatic.stats.flow.has_event_in_range(pulls, issues, tz, since, until)
    delivery_found = wambatic.stats.delivery.has_event_in_range(runs, releases, tz, since, until)
    if not (commits or flow_found or delivery_found or popularity):
        raise empty
    buckets = wambatic.stats.buckets.bucket_range(since, until, granularity)
    series: list[wambatic.stats.base.Series] = []
    tables: dict[str, list[dict[str, typing.Any]]] = {}
    if 'activity' in built:
        series, tables = wambatic.stats.activity.aggregate(
            commits,
            buckets,
            tz,
            request.settings,
            by_author=request.by_author,
            by_repo=subject.kind != 'repo',
        )
    totals = len(wambatic.stats.activity.TOTAL_METRICS) if 'activity' in built else 0
    gaps: list[dict[str, typing.Any]] = []
    if 'flow' in built:
        flow = wambatic.stats.flow.aggregate(pulls, issues, buckets, tz, since, until)
        series = [*series[:totals], *flow, *series[totals:]]
        totals += len(flow)
    if 'delivery' in built:
        delivery, missing = wambatic.stats.delivery.aggregate(
            runs, releases, delivery_pulls, buckets, tz, since, until, request.settings
        )
        series = [*series[:totals], *delivery, *series[totals:]]
        totals += len(delivery)
        gaps = list(missing)
    if popularity:
        liked, popular_tables = wambatic.stats.popularity.aggregate(
            stars, forks, repos, buckets, tz, since, until
        )
        series = [*series[:totals], *liked, *series[totals:]]
        tables.update(popular_tables)
        gaps.extend(wambatic.stats.popularity.hidden_star_gaps(hidden))
    tables['unavailable'] = gaps
    provenance = await fetcher.provenance(subject, resources_for(built))
    provenance['computed_at'] = now.astimezone(datetime.UTC).isoformat()
    provenance['timezone'] = str(tz)
    provenance['partial_buckets'] = ','.join(
        bucket.label for bucket in wambatic.stats.buckets.partial_buckets(since, until, buckets)
    )
    return wambatic.stats.base.StatsResult(
        subject=subject,
        request=request,
        since=since,
        until=until,
        series=series,
        tables=tables,
        provenance=provenance,
    )
