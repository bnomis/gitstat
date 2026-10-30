import bisect
import collections
import collections.abc
import datetime
import statistics

import wambatic.fetch.base
import wambatic.settings
import wambatic.stats.base
import wambatic.stats.buckets
import wambatic.stats.percentile

DELIVERY_METRICS = (
    ('workflow_runs', 'count'),
    ('workflow_success_rate', 'ratio'),
    ('workflow_duration_p50', 'minutes'),
    ('workflow_duration_p90', 'minutes'),
    ('release_count', 'count'),
    ('release_interval_p50', 'days'),
    ('deployments', 'count'),
    ('lead_time_p50', 'hours'),
    ('lead_time_p90', 'hours'),
    ('change_failure_rate', 'ratio'),
    ('time_to_restore_p50', 'hours'),
    ('time_to_restore_p90', 'hours'),
)
DEPLOYMENT_METRICS = frozenset({'deployments', 'lead_time_p50', 'lead_time_p90'})
FAILURE_METRICS = frozenset({'change_failure_rate'})
RESTORE_METRICS = frozenset({'time_to_restore_p50', 'time_to_restore_p90'})
DORA_METRICS = tuple(
    name
    for name, _ in DELIVERY_METRICS
    if name in DEPLOYMENT_METRICS | FAILURE_METRICS | RESTORE_METRICS
)
ACTIONS_RELEASE_METRICS = tuple(name for name, _ in DELIVERY_METRICS if name not in DORA_METRICS)
UNITS = dict(DELIVERY_METRICS)
OUTCOMES = frozenset({'failure', 'startup_failure', 'success', 'timed_out'})
SECONDS_PER_MINUTE = 60
NO_RELEASES = 'no releases in the cache and stats.deploy_workflow is not set'
NO_DEPLOY_RUNS = 'no successful run of the workflow named by stats.deploy_workflow'
NO_HOTFIX = 'no pull request in the cache has a label in stats.hotfix_labels'
ONE_DAY = datetime.timedelta(days=1)


def minutes(start: datetime.datetime, end: datetime.datetime) -> float:
    return (end - start).total_seconds() / SECONDS_PER_MINUTE


def has_event_in_range(
    runs: collections.abc.Iterable[wambatic.fetch.base.WorkflowRun],
    releases: collections.abc.Iterable[wambatic.fetch.base.Release],
    tz: datetime.tzinfo,
    since: datetime.date,
    until: datetime.date,
) -> bool:
    """Whether any run was created, or release published, on a local date in the range."""
    moments = [run.created_at for run in runs] + [release.published_at for release in releases]
    return any(since <= moment.astimezone(tz).date() <= until for moment in moments)


def workflow_file(path: str) -> str:
    """The file name of a run's workflow path, without any `@ref` GitHub may append."""
    return path.partition('@')[0].rpartition('/')[2]


def deployments_by_repo(
    runs: collections.abc.Iterable[wambatic.fetch.base.WorkflowRun],
    releases: collections.abc.Iterable[wambatic.fetch.base.Release],
    settings: wambatic.settings.StatsSettings,
) -> dict[str, list[datetime.datetime]]:
    """Each repository's deployments, oldest first: the successful completed runs of
    `settings.deploy_workflow` at `updated_at`, or without it the releases that are not
    prereleases at `published_at`."""
    found: dict[str, list[datetime.datetime]] = collections.defaultdict(list)
    workflow = settings.deploy_workflow
    if workflow is None:
        for release in releases:
            if not release.is_prerelease:
                found[release.repo].append(release.published_at)
    else:
        for run in runs:
            if (
                run.status == 'completed'
                and run.conclusion == 'success'
                and workflow in (run.name, workflow_file(run.workflow_path))
            ):
                found[run.repo].append(run.updated_at)
    return {repo: sorted(moments) for repo, moments in found.items()}


def hotfixes(
    pull_requests: collections.abc.Iterable[wambatic.fetch.base.PullRequest],
    settings: wambatic.settings.StatsSettings,
) -> list[wambatic.fetch.base.PullRequest]:
    """The pull requests with a label in `settings.hotfix_labels`, whatever its case."""
    wanted = {label.casefold() for label in settings.hotfix_labels}
    return [pull for pull in pull_requests if wanted & {label.casefold() for label in pull.labels}]


def missing_inputs(
    has_deployments: bool, has_hotfix: bool, settings: wambatic.settings.StatsSettings
) -> dict[str, str]:
    """Each proxy that cannot be emitted, in series order, with what its inputs lack."""
    no_deployments = NO_RELEASES if settings.deploy_workflow is None else NO_DEPLOY_RUNS
    missing: dict[str, str] = {}
    for name, _ in DELIVERY_METRICS:
        reasons: list[str] = []
        if (name in DEPLOYMENT_METRICS or name in FAILURE_METRICS) and not has_deployments:
            reasons.append(no_deployments)
        if (name in FAILURE_METRICS or name in RESTORE_METRICS) and not has_hotfix:
            reasons.append(NO_HOTFIX)
        if reasons:
            missing[name] = '; '.join(reasons)
    return missing


def aggregate(
    runs: collections.abc.Iterable[wambatic.fetch.base.WorkflowRun],
    releases: collections.abc.Iterable[wambatic.fetch.base.Release],
    pull_requests: collections.abc.Iterable[wambatic.fetch.base.PullRequest],
    buckets: list[wambatic.stats.base.Bucket],
    tz: datetime.tzinfo,
    since: datetime.date,
    until: datetime.date,
    settings: wambatic.settings.StatsSettings,
) -> tuple[list[wambatic.stats.base.Series], list[dict[str, str]]]:
    """The delivery series for the records, each event placed by its own local date in `tz` and
    ignored when that date is outside `since` to `until`, and a row for each proxy that is not
    emitted because its inputs are not in the cache.

    `releases` and `pull_requests` are read whole: an interval and a lead time reach back before
    the range. A deployment whose `settings.failure_window` ends after `until` counts as not
    failed, since its window is still open. Counts are zero in an empty bucket; the percentiles
    and ratios have no point there."""
    runs, releases, pull_requests = list(runs), list(releases), list(pull_requests)
    place = wambatic.stats.buckets.placer(buckets, tz, since, until)
    size = len(buckets)
    counts = {name: [0] * size for name in ('workflow_runs', 'release_count', 'deployments')}
    outcomes, successes, failures = ([0] * size for _ in range(3))
    values: dict[str, list[list[float]]] = {
        name: [[] for _ in buckets]
        for name in ('duration', 'interval', 'lead_time', 'time_to_restore')
    }

    for run in runs:
        if (index := place(run.created_at)) is None:
            continue
        counts['workflow_runs'][index] += 1
        if run.status != 'completed':
            continue
        if run.conclusion in OUTCOMES:
            outcomes[index] += 1
            successes[index] += run.conclusion == 'success'
        if run.run_started_at is not None:
            values['duration'][index].append(minutes(run.run_started_at, run.updated_at))

    previous: dict[str, datetime.datetime] = {}
    for release in sorted(releases, key=lambda r: (r.published_at, r.tag_name)):
        if (index := place(release.published_at)) is not None:
            counts['release_count'][index] += 1
            if release.repo in previous:
                days = (release.published_at - previous[release.repo]).days
                values['interval'][index].append(days)
        previous[release.repo] = release.published_at

    by_repo = deployments_by_repo(runs, releases, settings)
    hotfix = hotfixes(pull_requests, settings)
    has_deployments = any(by_repo.values())
    has_hotfix = bool(hotfix)
    window = settings.failure_window
    horizon = datetime.datetime.combine(until + ONE_DAY, datetime.time(), tzinfo=tz)
    hotfix_opened: dict[str, list[datetime.datetime]] = collections.defaultdict(list)
    for pull in hotfix:
        hotfix_opened[pull.repo].append(pull.created_at)
        if (index := place(pull.merged_at)) is not None and pull.merged_at is not None:
            values['time_to_restore'][index].append(
                wambatic.stats.percentile.hours(pull.created_at, pull.merged_at)
            )
    for repo, moments in by_repo.items():
        for moment in moments:
            if (index := place(moment)) is None:
                continue
            counts['deployments'][index] += 1
            window_closed = moment + window <= horizon
            failures[index] += window_closed and any(
                moment < opened <= moment + window for opened in hotfix_opened[repo]
            )
    for pull in pull_requests:
        if pull.merged_at is None:
            continue
        moments = by_repo.get(pull.repo, [])
        after = bisect.bisect_left(moments, pull.merged_at)
        if after < len(moments) and (index := place(moments[after])) is not None:
            start = pull.first_commit_at or pull.created_at
            values['lead_time'][index].append(
                wambatic.stats.percentile.hours(start, moments[after])
            )

    missing = missing_inputs(has_deployments, has_hotfix, settings)
    series: list[wambatic.stats.base.Series] = []
    for name, unit in DELIVERY_METRICS:
        if name in missing:
            continue
        points: dict[wambatic.stats.base.Bucket, float]
        if name in counts:
            points = dict(zip(buckets, counts[name], strict=True))
        elif name == 'workflow_success_rate':
            points = {
                bucket: successes[i] / outcomes[i]
                for i, bucket in enumerate(buckets)
                if outcomes[i]
            }
        elif name == 'change_failure_rate':
            points = {
                bucket: failures[i] / counts['deployments'][i]
                for i, bucket in enumerate(buckets)
                if counts['deployments'][i]
            }
        else:
            points = percentile_points(name, buckets, values)
        series.append(wambatic.stats.base.Series(name, unit, points))
    return series, [{'metric': name, 'reason': reason} for name, reason in missing.items()]


def percentile_points(
    name: str,
    buckets: list[wambatic.stats.base.Bucket],
    values: dict[str, list[list[float]]],
) -> dict[wambatic.stats.base.Bucket, float]:
    """The buckets that have values for a duration, interval, lead time or restore series."""
    base, _, suffix = name.rpartition('_')
    found = values['interval' if name == 'release_interval_p50' else base.removeprefix('workflow_')]
    summary: wambatic.stats.percentile.Summary = (
        statistics.median_low
        if name == 'release_interval_p50'
        else wambatic.stats.percentile.summary(suffix)
    )
    return {bucket: summary(items) for bucket, items in zip(buckets, found, strict=True) if items}
