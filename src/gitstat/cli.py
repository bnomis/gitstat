import asyncio
import collections.abc
import contextlib
import dataclasses
import datetime
import os
import re
import sys
import typing
import zoneinfo

import cappa
import loguru
import rich.box
import rich.console
import rich.table

import gitstat.fetch.auth
import gitstat.fetch.base
import gitstat.fetch.cache
import gitstat.fetch.errors
import gitstat.logs
import gitstat.reports.base
import gitstat.reports.errors
import gitstat.reports.terminal
import gitstat.settings
import gitstat.stats
import gitstat.stats.base

LOGIN = re.compile(r'[A-Za-z0-9-]{1,39}')
REPO_NAME = re.compile(r'[A-Za-z0-9._-]{1,100}')
DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')
PREFIXES: dict[str, typing.Literal['org', 'repo', 'user']] = {
    'org': 'org',
    'repo': 'repo',
    'user': 'user',
}
TARGET_FORMS = 'user:NAME, org:NAME, repo:OWNER/NAME, OWNER/NAME or NAME'
GRANULARITIES = typing.Literal['day', 'month', 'total', 'week', 'year']
FORMATS = typing.Literal['html', 'json', 'terminal']


@cappa.command(name='report', help='Print a report of a user, an organisation or a repository.')
@dataclasses.dataclass
class Report:
    target: typing.Annotated[
        str, cappa.Arg(help='user:NAME, org:NAME, repo:OWNER/NAME, OWNER/NAME or a bare NAME')
    ]
    format: typing.Annotated[
        FORMATS | None, cappa.Arg(long=True, help='Output format (default: report.format)')
    ] = None
    by: typing.Annotated[
        GRANULARITIES, cappa.Arg(long=True, help='Period to bucket by (default: month)')
    ] = 'month'
    since: typing.Annotated[
        str | None, cappa.Arg(long=True, help='First day, YYYY-MM-DD (default: first commit)')
    ] = None
    until: typing.Annotated[
        str | None, cappa.Arg(long=True, help='Last day, YYYY-MM-DD (default: today)')
    ] = None
    groups: typing.Annotated[
        str | None,
        cappa.Arg(long=True, help='Comma-separated metric groups (default: activity,flow)'),
    ] = None
    by_author: typing.Annotated[
        bool, cappa.Arg(long=True, help='Break activity down by author (not for a user)')
    ] = False
    tz: typing.Annotated[
        str | None, cappa.Arg(long=True, help='Time zone (default: stats.timezone)')
    ] = None
    full_refresh: typing.Annotated[
        bool, cappa.Arg(long=True, help='Read all history again; ignores --max-age')
    ] = False
    no_fetch: typing.Annotated[
        bool, cappa.Arg(long=True, help='Report from the cache without using the network')
    ] = False
    max_age: typing.Annotated[
        str | None,
        cappa.Arg(long=True, help='Skip the network if synced more recently, e.g. 30m or 1d'),
    ] = None
    ignore_cache_version: typing.Annotated[
        bool, cappa.Arg(long=True, help='Read a cache written by a different version')
    ] = False


@cappa.command(name='cache', help='Show or remove the local cache.')
@dataclasses.dataclass
class CacheCommand:
    action: typing.Annotated[
        typing.Literal['clear', 'info'],
        cappa.Arg(help='info describes the cache, clear removes it'),
    ]


@cappa.command(name='gitstat', help='Statistics from github.com for a user, an org or a repo.')
@dataclasses.dataclass
class Gitstat:
    command: cappa.Subcommands[Report | CacheCommand]
    verbose: typing.Annotated[
        bool, cappa.Arg(short='-v', long=True, help='Log debugging detail')
    ] = False
    quiet: typing.Annotated[
        bool, cappa.Arg(short='-q', long=True, help='Log warnings and errors only')
    ] = False


def parse_target(text: str) -> gitstat.fetch.base.Subject | str:
    """A `Subject` for `user:NAME`, `org:NAME`, `repo:OWNER/NAME` or `OWNER/NAME`; a bare `NAME`
    comes back as the login string, for the caller to resolve."""
    invalid = gitstat.reports.errors.UsageError(
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
        return gitstat.fetch.base.Subject(kind, owner)
    if not slash:
        if kind == 'repo':
            raise invalid
        return owner
    if not REPO_NAME.fullmatch(name):
        raise invalid
    return gitstat.fetch.base.Subject('repo', owner, name)


def parse_date(text: str, flag: str = 'a date') -> datetime.date:
    """Exactly `YYYY-MM-DD`; `date.fromisoformat` alone also takes `20261029` and week dates."""
    try:
        if DATE.fullmatch(text):
            return datetime.date.fromisoformat(text)
    except ValueError:
        pass
    raise gitstat.reports.errors.UsageError(f'{flag} must be a date written YYYY-MM-DD')


def overrides(report: Report) -> dict[str, object]:
    """The `load_settings` overrides for the flags that set a setting, only where given."""
    result: dict[str, dict[str, object]] = {}
    if report.format is not None:
        result.setdefault('report', {})['format'] = report.format
    if report.max_age is not None:
        result.setdefault('fetch', {})['max_age'] = report.max_age
    if report.tz is not None:
        result.setdefault('stats', {})['timezone'] = report.tz
    return typing.cast(dict[str, object], result)


def check_verbosity(root: Gitstat) -> None:
    if root.verbose and root.quiet:
        raise gitstat.reports.errors.UsageError('-v and -q cannot be used together')


def check_report(report: Report, settings: gitstat.settings.Settings) -> None:
    """The flag combinations that can be rejected before the cache or the network is touched."""
    if report.full_refresh and report.no_fetch:
        raise gitstat.reports.errors.UsageError('--full-refresh and --no-fetch cannot be combined')
    if settings.report.format == 'html':
        raise gitstat.reports.errors.UsageError(
            'the html format is built in implementation step 7; use --format terminal or json'
        )
    target = parse_target(report.target)
    if report.no_fetch and isinstance(target, str):
        raise gitstat.reports.errors.UsageError(
            '--no-fetch needs user:NAME or org:NAME: a bare NAME is resolved with the network'
        )
    if report.by_author and not isinstance(target, str):
        check_by_author(target)


def check_by_author(subject: gitstat.fetch.base.Subject) -> None:
    if subject.kind == 'user':
        raise gitstat.reports.errors.UsageError(
            '--by-author is for an organisation or a repository; a user is already one author'
        )


def resolve_tz(settings: gitstat.settings.Settings) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(settings.stats.timezone)
    except zoneinfo.ZoneInfoNotFoundError, ValueError:
        raise gitstat.settings.SettingsError('stats.timezone is not a known time zone') from None


def build_request(
    report: Report, settings: gitstat.settings.Settings, tz: zoneinfo.ZoneInfo
) -> gitstat.stats.base.StatsRequest:
    fields: dict[str, object] = {}
    if report.groups is not None:
        groups = frozenset(name.strip() for name in report.groups.split(',') if name.strip())
        if not groups:
            raise gitstat.reports.errors.UsageError('--groups needs at least one group name')
        fields['groups'] = groups
    return gitstat.stats.base.StatsRequest(
        granularity=gitstat.stats.base.Granularity(report.by),
        since=None if report.since is None else parse_date(report.since, '--since'),
        until=None if report.until is None else parse_date(report.until, '--until'),
        by_author=report.by_author,
        tz=tz,
        settings=settings.stats,
        **fields,  # type: ignore[arg-type]
    )


def make_fetcher(
    token: str, cache: gitstat.fetch.cache.Cache, settings: gitstat.settings.FetchSettings
) -> gitstat.fetch.base.Fetcher:
    """The one place a `Fetcher` is built, so tests can swap in one that talks to a replay
    server. An empty token is for a fetcher that is only read from and never entered."""
    return gitstat.fetch.base.Fetcher(token, cache, settings)


def needs_sync(
    provenance: dict[str, str],
    resources: frozenset[str],
    settings: gitstat.settings.FetchSettings,
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


def log_sync(report: gitstat.fetch.base.SyncReport) -> None:
    written = sum(report.rows_written.values())
    message = (
        f'Synced {report.repos_listed} repositories ({report.repos_skipped} unchanged), '
        f'{written} commits written'
    )
    if report.full_refetches:
        message += f'; read in full again: {", ".join(report.full_refetches)}'
    loguru.logger.info(message)


async def build_result(
    report: Report,
    settings: gitstat.settings.Settings,
    cache: gitstat.fetch.cache.Cache,
    target: gitstat.fetch.base.Subject | str,
    request: gitstat.stats.base.StatsRequest,
    clock: collections.abc.Callable[[], datetime.datetime],
) -> gitstat.stats.base.StatsResult:
    """Resolve the subject, sync when needed and compute; the network is used (and a token
    resolved) only for a bare NAME or a sync."""
    reader = make_fetcher('', cache, settings.fetch)
    async with contextlib.AsyncExitStack() as stack:
        online: gitstat.fetch.base.Fetcher | None = None
        if isinstance(target, str):
            token = gitstat.fetch.auth.resolve_token()
            online = await stack.enter_async_context(make_fetcher(token, cache, settings.fetch))
            subject = gitstat.fetch.base.Subject(await online.owner_kind(target), target)
            if report.by_author:
                check_by_author(subject)
        else:
            subject = target
        resources = gitstat.stats.resources_for(request.groups) & gitstat.fetch.base.BUILT_RESOURCES
        provenance = await reader.provenance(subject, resources)
        synced = needs_sync(
            provenance, resources, settings.fetch, report.full_refresh, report.no_fetch, clock()
        )
        if synced:
            if online is None:
                token = gitstat.fetch.auth.resolve_token()
                online = await stack.enter_async_context(make_fetcher(token, cache, settings.fetch))
            log_sync(await online.sync(subject, resources, full_refresh=report.full_refresh))
    try:
        return await gitstat.stats.compute(subject, reader, request, clock=clock)
    except gitstat.stats.EmptySubjectError as e:
        if report.no_fetch:
            raise gitstat.stats.EmptySubjectError(
                f'{e}; the cache may only need a sync, so try again without --no-fetch'
            ) from None
        raise


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


async def run_report(
    report: Report,
    settings: gitstat.settings.Settings,
    console: rich.console.Console,
    stdout: typing.TextIO,
    *,
    clock: collections.abc.Callable[[], datetime.datetime] = utc_now,
) -> None:
    """Check the flags, bring the cache up to date if needed, compute and print the report."""
    target = parse_target(report.target)
    check_report(report, settings)
    request = build_request(report, settings, resolve_tz(settings))
    gitstat.stats.resources_for(request.groups)
    cache = gitstat.fetch.cache.Cache.open(
        settings.fetch.cache_path, ignore_version=report.ignore_cache_version
    )
    try:
        result = await build_result(report, settings, cache, target, request, clock)
    finally:
        cache.close()
    if settings.report.format == 'json':
        gitstat.reports.base.render_json(result, stdout)
    else:
        gitstat.reports.terminal.render_terminal(result, console)


def cache_info_table(info: gitstat.fetch.cache.CacheInfo) -> rich.table.Table:
    table = rich.table.Table(show_header=False, box=rich.box.SIMPLE, title='Cache')
    table.add_column(justify='left', no_wrap=True)
    table.add_column(justify='left')
    rows: list[tuple[str, str]] = [
        ('path', str(info.path)),
        ('size', f'{gitstat.reports.terminal.format_number(info.size_bytes)} bytes'),
        *sorted(info.identity.items()),
    ]
    for key, (recorded, running) in info.differences.items():
        rows.append((f'differs: {key}', f'{recorded or "nothing"} -> {running or "nothing"}'))
    if not info.differences:
        rows.append(('differences', 'none'))
    if info.version_override_at is not None:
        rows.append(('version_override_at', info.version_override_at))
    rows += [
        ('repositories', gitstat.reports.terminal.format_number(info.repos)),
        ('commits', gitstat.reports.terminal.format_number(info.commits)),
        (
            'last synced',
            'never' if info.last_synced_at is None else info.last_synced_at.isoformat(),
        ),
    ]
    for name, value in rows:
        table.add_row(
            gitstat.reports.terminal.text_cell(name), gitstat.reports.terminal.text_cell(value)
        )
    return table


def run_cache(
    command: CacheCommand, settings: gitstat.settings.Settings, console: rich.console.Console
) -> None:
    """`cache info` describes the cache, `cache clear` removes it; neither uses the network."""
    path = settings.fetch.cache_path
    if command.action == 'info':
        info = gitstat.fetch.cache.inspect_cache(path)
        if info is None:
            console.print(gitstat.reports.terminal.text_cell(f'no cache at {path}'))
        else:
            console.print(cache_info_table(info))
        return
    removed = gitstat.fetch.cache.clear_cache(path)
    for deleted in removed:
        loguru.logger.info(f'Removed {deleted}')
    if not removed:
        loguru.logger.info(f'no cache at {path}')


def log_level(root: Gitstat) -> str:
    if root.quiet and not root.verbose:
        return 'WARNING'
    if root.verbose and not root.quiet:
        return 'DEBUG'
    return 'INFO'


def redact_environment_token(text: str) -> str:
    return gitstat.fetch.auth.redact(text, os.environ.get('GITHUB_TOKEN', '').strip())


def redact_exception(error: BaseException | None) -> None:
    """Remove the environment's token from the messages of `error` and what it was raised from,
    so the traceback that is logged cannot carry it."""
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        error.args = tuple(
            redact_environment_token(arg) if isinstance(arg, str) else arg for arg in error.args
        )
        error = error.__cause__ or error.__context__


def execute(root: Gitstat) -> None:
    check_verbosity(root)
    command = root.command
    console = rich.console.Console()
    if isinstance(command, Report):
        settings = gitstat.settings.load_settings(None, overrides(command))
        asyncio.run(run_report(command, settings, console, sys.stdout))
    else:
        run_cache(command, gitstat.settings.load_settings(None, {}), console)


def exit_status(code: str | int | None) -> int:
    return code if isinstance(code, int) else 0 if code is None else 1


def main(argv: list[str] | None = None) -> int:
    """Parse `argv` (default `sys.argv[1:]`), run the command and return the exit status; every
    error is turned into a logged line and a status here and nowhere else."""
    try:
        root = cappa.parse(Gitstat, argv=sys.argv[1:] if argv is None else argv)
    except cappa.Exit as e:
        return exit_status(e.code)
    gitstat.logs.configure_logging(log_level(root))
    try:
        execute(root)
    except (gitstat.reports.errors.UsageError, gitstat.settings.SettingsError) as e:
        loguru.logger.error(redact_environment_token(str(e)))
        return 2
    except (gitstat.fetch.errors.FetchError, gitstat.stats.StatsError) as e:
        loguru.logger.error(redact_environment_token(str(e)))
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        redact_exception(e)
        loguru.logger.exception(f'Unexpected error: {redact_environment_token(str(e))}')
        return 1
    return 0


def run() -> None:
    """The `gitstat` console script and `python -m gitstat`."""
    sys.exit(main())
