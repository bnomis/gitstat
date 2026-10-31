"""The sync-then-compute pipeline the command line and the web app share."""

import collections.abc
import contextlib
import datetime
import os
import re
import typing
import zoneinfo

import loguru

import wambatic.fetch.auth
import wambatic.fetch.base
import wambatic.fetch.cache
import wambatic.fetch.ratelimit
import wambatic.reports.errors
import wambatic.settings
import wambatic.stats
import wambatic.stats.base

LOGIN = re.compile(r'[A-Za-z0-9-]{1,39}')
REPO_NAME = re.compile(r'[A-Za-z0-9._-]{1,100}')
DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')
PREFIXES: dict[str, typing.Literal['org', 'repo', 'user']] = {
    'org': 'org',
    'repo': 'repo',
    'user': 'user',
}
TARGET_FORMS = 'user:NAME, org:NAME, repo:OWNER/NAME, OWNER/NAME or NAME'


def parse_target(text: str) -> wambatic.fetch.base.Subject | str:
    """A `Subject` for `user:NAME`, `org:NAME`, `repo:OWNER/NAME` or `OWNER/NAME`; a bare `NAME`
    comes back as the login string, for the caller to resolve."""
    invalid = wambatic.reports.errors.UsageError(
        f'the target must be one of {TARGET_FORMS} (a NAME is 1 to 39 letters, digits and "-"; '
        'a repo NAME is 1 to 100 letters, digits, ".", "_" and "-")'
    )
    kind: typing.Literal['org', 'repo', 'user'] | None = None
    rest = text
    prefix, colon, after = text.partition(':')
    if colon:
        kind = PREFIXES.get(prefix)
        if kind is None:
            raise invalid
        rest = after
    owner, slash, name = rest.partition('/')
    if not LOGIN.fullmatch(owner):
        raise invalid
    if kind == 'org' or kind == 'user':
        if slash:
            raise invalid
        return wambatic.fetch.base.Subject(kind, owner)
    if not slash:
        if kind == 'repo':
            raise invalid
        return owner
    if not REPO_NAME.fullmatch(name):
        raise invalid
    return wambatic.fetch.base.Subject('repo', owner, name)


def parse_date(text: str, flag: str = 'a date') -> datetime.date:
    """Exactly `YYYY-MM-DD`; `date.fromisoformat` alone also takes `20261029` and week dates."""
    try:
        if DATE.fullmatch(text):
            return datetime.date.fromisoformat(text)
    except ValueError:
        pass
    raise wambatic.reports.errors.UsageError(f'{flag} must be a date written YYYY-MM-DD')


def check_by_author(subject: wambatic.fetch.base.Subject) -> None:
    if subject.kind == 'user':
        raise wambatic.reports.errors.UsageError(
            '--by-author is for an organisation or a repository; a user is already one author'
        )


def resolve_tz(settings: wambatic.settings.Settings) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(settings.stats.timezone)
    except zoneinfo.ZoneInfoNotFoundError, ValueError:
        raise wambatic.settings.SettingsError('stats.timezone is not a known time zone') from None


def make_request(
    by: str,
    since: str | None,
    until: str | None,
    groups: str | None,
    by_author: bool,
    tz: zoneinfo.ZoneInfo,
    settings: wambatic.settings.Settings,
) -> wambatic.stats.base.StatsRequest:
    """The `StatsRequest` of the computing flags or query parameters."""
    fields: dict[str, object] = {}
    if groups is not None:
        names = frozenset(name.strip() for name in groups.split(',') if name.strip())
        if not names:
            raise wambatic.reports.errors.UsageError('--groups needs at least one group name')
        fields['groups'] = names
    try:
        granularity = wambatic.stats.base.Granularity(by)
    except ValueError:
        choices = ', '.join(sorted(item.value for item in wambatic.stats.base.Granularity))
        raise wambatic.reports.errors.UsageError(f'--by must be one of {choices}') from None
    return wambatic.stats.base.StatsRequest(
        granularity=granularity,
        since=None if since is None else parse_date(since, '--since'),
        until=None if until is None else parse_date(until, '--until'),
        by_author=by_author,
        tz=tz,
        settings=settings.stats,
        **fields,  # type: ignore[arg-type]
    )


def make_fetcher(
    token: str, cache: wambatic.fetch.cache.Cache, settings: wambatic.settings.FetchSettings
) -> wambatic.fetch.base.Fetcher:
    """The one place a `Fetcher` is built, so tests can swap in one that talks to a replay
    server. An empty token is for a fetcher that is only read from and never entered."""
    return wambatic.fetch.base.Fetcher(token, cache, settings)


def needs_sync(
    provenance: dict[str, str],
    resources: frozenset[str],
    settings: wambatic.settings.FetchSettings,
    full_refresh: bool,
    no_fetch: bool,
    now: datetime.datetime,
) -> bool:
    """Whether the cache must be brought up to date before the report is computed."""
    if no_fetch or not resources:
        return False
    if full_refresh:
        return True
    if settings.max_age <= datetime.timedelta(0):
        return True
    for resource in resources:
        try:
            fetched_at = datetime.datetime.fromisoformat(provenance[f'fetched_at:{resource}'])
        except ValueError, KeyError:
            return True
        if now - fetched_at >= settings.max_age:
            return True
    return False


def log_sync(report: wambatic.fetch.base.SyncReport) -> None:
    written = ', '.join(f'{name} {rows}' for name, rows in sorted(report.rows_written.items()))
    message = (
        f'Synced {report.repos_listed} repositories ({report.repos_skipped} unchanged), '
        f'rows written: {written}'
    )
    if report.full_refetches:
        message += f'; read in full again: {", ".join(report.full_refetches)}'
    loguru.logger.info(message)


async def sync_target(
    settings: wambatic.settings.Settings,
    cache: wambatic.fetch.cache.Cache,
    target: wambatic.fetch.base.Subject | str,
    groups: frozenset[str],
    *,
    by_author: bool,
    full_refresh: bool,
    no_fetch: bool,
    sync: bool | None = None,
    progress: wambatic.fetch.base.SyncProgress | None = None,
    clock: collections.abc.Callable[[], datetime.datetime] = wambatic.fetch.ratelimit.utc_now,
) -> wambatic.fetch.base.Subject:
    """Resolve a bare NAME and sync once when `sync` is True, or, when it is None, when
    `needs_sync` says so; the network is used (and a token resolved) only for those."""
    reader = make_fetcher('', cache, settings.fetch)
    async with contextlib.AsyncExitStack() as stack:
        online: wambatic.fetch.base.Fetcher | None = None
        if isinstance(target, str):
            token = wambatic.fetch.auth.resolve_token()
            online = await stack.enter_async_context(make_fetcher(token, cache, settings.fetch))
            subject = wambatic.fetch.base.Subject(await online.owner_kind(target), target)
            if by_author:
                check_by_author(subject)
        else:
            subject = target
        resources = wambatic.stats.resources_for(groups) & wambatic.fetch.base.BUILT_RESOURCES
        if sync is None:
            provenance = await reader.provenance(subject, resources)
            sync = needs_sync(
                provenance, resources, settings.fetch, full_refresh, no_fetch, clock()
            )
        if sync:
            if online is None:
                token = wambatic.fetch.auth.resolve_token()
                online = await stack.enter_async_context(make_fetcher(token, cache, settings.fetch))
            if progress is None:
                report = await online.sync(subject, resources, full_refresh=full_refresh)
            else:
                report = await online.sync(
                    subject, resources, full_refresh=full_refresh, progress=progress
                )
            log_sync(report)
    return subject


async def build_results(
    settings: wambatic.settings.Settings,
    cache: wambatic.fetch.cache.Cache,
    target: wambatic.fetch.base.Subject | str,
    requests: list[wambatic.stats.base.StatsRequest],
    *,
    by_author: bool,
    full_refresh: bool,
    no_fetch: bool,
    sync: bool | None = None,
    progress: wambatic.fetch.base.SyncProgress | None = None,
    clock: collections.abc.Callable[[], datetime.datetime] = wambatic.fetch.ratelimit.utc_now,
) -> tuple[wambatic.fetch.base.Subject, list[wambatic.stats.base.StatsResult]]:
    """Resolve the subject, sync once when needed and compute each of `requests` (which share
    their groups); the network is used (and a token resolved) only for a bare NAME or a sync."""
    subject = await sync_target(
        settings,
        cache,
        target,
        requests[0].groups,
        by_author=by_author,
        full_refresh=full_refresh,
        no_fetch=no_fetch,
        sync=sync,
        progress=progress,
        clock=clock,
    )
    reader = make_fetcher('', cache, settings.fetch)
    try:
        return subject, [
            await wambatic.stats.compute(subject, reader, request, clock=clock)
            for request in requests
        ]
    except wambatic.stats.EmptySubjectError as e:
        if no_fetch:
            raise wambatic.stats.EmptySubjectError(
                f'{e}; the cache may only need a sync, so try again without --no-fetch'
            ) from None
        raise


def redact_environment_token(text: str) -> str:
    return wambatic.fetch.auth.redact(text, os.environ.get('GITHUB_TOKEN', '').strip())


def redact_error(error: BaseException) -> str:
    """The message of `error` without the environment's token, which is also removed from the
    args of `error` and of what it was raised from, so a logged traceback cannot carry it."""
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        current.args = tuple(
            redact_environment_token(arg) if isinstance(arg, str) else arg for arg in current.args
        )
        current = current.__cause__ or current.__context__
    return redact_environment_token(str(error))
