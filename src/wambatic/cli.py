import asyncio
import collections.abc
import contextlib
import dataclasses
import datetime
import os
import pathlib
import re
import sys
import typing
import zoneinfo

import cappa
import loguru
import rich.box
import rich.console
import rich.table

import wambatic.fetch.auth
import wambatic.fetch.base
import wambatic.fetch.cache
import wambatic.fetch.errors
import wambatic.fetch.ratelimit
import wambatic.logs
import wambatic.reports.base
import wambatic.reports.errors
import wambatic.reports.html
import wambatic.reports.terminal
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
GRANULARITIES = typing.Literal['day', 'month', 'total', 'week', 'year']
FORMATS = typing.Literal['html', 'json', 'terminal']


@cappa.command(name='report', help='Print a report of a user, an organisation or a repository.')
@dataclasses.dataclass
class Report:
    target: typing.Annotated[
        str, cappa.Arg(help='user:NAME, org:NAME, repo:OWNER/NAME, OWNER/NAME or a bare NAME')
    ]
    format: typing.Annotated[
        FORMATS | None,
        cappa.Arg(long=True, help='Output format: terminal, html or json (default: report.format)'),
    ] = None
    out: typing.Annotated[
        str | None,
        cappa.Arg(
            long=True,
            help='File, or existing directory, for --format html (default: report.out_dir)',
        ),
    ] = None
    by: typing.Annotated[
        GRANULARITIES,
        cappa.Arg(
            long=True,
            help='Period to bucket by; with html, the period shown first (default: month)',
        ),
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


@cappa.command(name='wambatic', help='Statistics from github.com for a user, an org or a repo.')
@dataclasses.dataclass
class Wambatic:
    command: cappa.Subcommands[Report | CacheCommand]
    verbose: typing.Annotated[
        bool, cappa.Arg(short='-v', long=True, help='Log debugging detail')
    ] = False
    quiet: typing.Annotated[
        bool, cappa.Arg(short='-q', long=True, help='Log warnings and errors only')
    ] = False


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


def check_verbosity(root: Wambatic) -> None:
    if root.verbose and root.quiet:
        raise wambatic.reports.errors.UsageError('-v and -q cannot be used together')


def check_report(report: Report, settings: wambatic.settings.Settings) -> None:
    """The flag combinations that can be rejected before the cache or the network is touched."""
    if report.full_refresh and report.no_fetch:
        raise wambatic.reports.errors.UsageError('--full-refresh and --no-fetch cannot be combined')
    if report.out is not None and settings.report.format != 'html':
        raise wambatic.reports.errors.UsageError('--out is for --format html')
    if settings.report.format == 'html' and report.by == 'total':
        raise wambatic.reports.errors.UsageError(
            '--by total is not for --format html: the page shows the totals as tiles and '
            'switches between year, month, week and day'
        )
    target = parse_target(report.target)
    if report.no_fetch and isinstance(target, str):
        raise wambatic.reports.errors.UsageError(
            '--no-fetch needs user:NAME or org:NAME: a bare NAME is resolved with the network'
        )
    if report.by_author and not isinstance(target, str):
        check_by_author(target)


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


def build_request(
    report: Report, settings: wambatic.settings.Settings, tz: zoneinfo.ZoneInfo
) -> wambatic.stats.base.StatsRequest:
    fields: dict[str, object] = {}
    if report.groups is not None:
        groups = frozenset(name.strip() for name in report.groups.split(',') if name.strip())
        if not groups:
            raise wambatic.reports.errors.UsageError('--groups needs at least one group name')
        fields['groups'] = groups
    return wambatic.stats.base.StatsRequest(
        granularity=wambatic.stats.base.Granularity(report.by),
        since=None if report.since is None else parse_date(report.since, '--since'),
        until=None if report.until is None else parse_date(report.until, '--until'),
        by_author=report.by_author,
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


async def build_result(
    report: Report,
    settings: wambatic.settings.Settings,
    cache: wambatic.fetch.cache.Cache,
    target: wambatic.fetch.base.Subject | str,
    requests: list[wambatic.stats.base.StatsRequest],
    clock: collections.abc.Callable[[], datetime.datetime],
) -> tuple[wambatic.fetch.base.Subject, list[wambatic.stats.base.StatsResult]]:
    """Resolve the subject, sync once when needed and compute each of `requests` (which share
    their groups); the network is used (and a token resolved) only for a bare NAME or a sync."""
    reader = make_fetcher('', cache, settings.fetch)
    async with contextlib.AsyncExitStack() as stack:
        online: wambatic.fetch.base.Fetcher | None = None
        if isinstance(target, str):
            token = wambatic.fetch.auth.resolve_token()
            online = await stack.enter_async_context(make_fetcher(token, cache, settings.fetch))
            subject = wambatic.fetch.base.Subject(await online.owner_kind(target), target)
            if report.by_author:
                check_by_author(subject)
        else:
            subject = target
        resources = (
            wambatic.stats.resources_for(requests[0].groups) & wambatic.fetch.base.BUILT_RESOURCES
        )
        provenance = await reader.provenance(subject, resources)
        synced = needs_sync(
            provenance, resources, settings.fetch, report.full_refresh, report.no_fetch, clock()
        )
        if synced:
            if online is None:
                token = wambatic.fetch.auth.resolve_token()
                online = await stack.enter_async_context(make_fetcher(token, cache, settings.fetch))
            log_sync(await online.sync(subject, resources, full_refresh=report.full_refresh))
    try:
        return subject, [
            await wambatic.stats.compute(subject, reader, request, clock=clock)
            for request in requests
        ]
    except wambatic.stats.EmptySubjectError as e:
        if report.no_fetch:
            raise wambatic.stats.EmptySubjectError(
                f'{e}; the cache may only need a sync, so try again without --no-fetch'
            ) from None
        raise


def output_path(
    out: str | None, settings: wambatic.settings.Settings, subject: wambatic.fetch.base.Subject
) -> pathlib.Path:
    """`--out` as given, or inside it when it is an existing directory; else the default
    directory. A file is named by `report_filename`."""
    name = wambatic.reports.html.report_filename(subject)
    if out is None:
        return settings.report.out_dir / name
    path = pathlib.Path(out).expanduser()
    return path / name if path.is_dir() else path


def render_html_report(
    report: Report,
    settings: wambatic.settings.Settings,
    subject: wambatic.fetch.base.Subject,
    results: list[wambatic.stats.base.StatsResult],
    stdout: typing.TextIO,
) -> None:
    """Build the page from the TOTAL result and the four period results, write it and print
    the path."""
    total, *periods = results
    page = wambatic.reports.html.HtmlReport(
        total=total,
        periods={result.request.granularity: result for result in periods},
        initial=wambatic.stats.base.Granularity(report.by),
    )
    path = output_path(report.out, settings, subject)
    try:
        wambatic.reports.html.render_html(page, path, settings.report.html_theme)
    except OSError as e:
        raise wambatic.reports.errors.OutputError(f'cannot write {path}: {e.strerror or e}') from e
    stdout.write(f'{path}\n')


async def run_report(
    report: Report,
    settings: wambatic.settings.Settings,
    console: rich.console.Console,
    stdout: typing.TextIO,
    *,
    clock: collections.abc.Callable[[], datetime.datetime] = wambatic.fetch.ratelimit.utc_now,
) -> None:
    """Check the flags, bring the cache up to date if needed, compute and print the report."""
    target = parse_target(report.target)
    check_report(report, settings)
    request = build_request(report, settings, resolve_tz(settings))
    wambatic.stats.resources_for(request.groups)
    cache = wambatic.fetch.cache.Cache.open(
        settings.fetch.cache_path, ignore_version=report.ignore_cache_version
    )
    as_html = settings.report.format == 'html'
    requests = [request]
    if as_html:
        requests = [
            dataclasses.replace(request, granularity=granularity)
            for granularity in (
                wambatic.stats.base.Granularity.TOTAL,
                *wambatic.reports.html.PERIODS,
            )
        ]
    try:
        subject, results = await build_result(report, settings, cache, target, requests, clock)
    finally:
        cache.close()
    if as_html:
        render_html_report(report, settings, subject, results, stdout)
    elif settings.report.format == 'json':
        wambatic.reports.base.render_json(results[0], stdout)
    else:
        wambatic.reports.terminal.render_terminal(results[0], console)


def cache_info_table(info: wambatic.fetch.cache.CacheInfo) -> rich.table.Table:
    table = rich.table.Table(show_header=False, box=rich.box.SIMPLE, title='Cache')
    table.add_column(justify='left', no_wrap=True)
    table.add_column(justify='left', overflow='fold')
    rows: list[tuple[str, str]] = [
        ('path', str(info.path)),
        ('size', f'{wambatic.reports.terminal.format_number(info.size_bytes)} bytes'),
        *sorted(info.identity.items()),
    ]
    for key, (recorded, running) in info.differences.items():
        rows.append((f'differs: {key}', f'{recorded or "nothing"} -> {running or "nothing"}'))
    if not info.differences:
        rows.append(('differences', 'none'))
    if info.version_override_at is not None:
        rows.append(('version_override_at', info.version_override_at))
    rows += [
        ('repositories', wambatic.reports.terminal.format_number(info.repos)),
        ('commits', wambatic.reports.terminal.format_number(info.commits)),
        ('pull requests', wambatic.reports.terminal.format_number(info.pull_requests)),
        ('issues', wambatic.reports.terminal.format_number(info.issues)),
        (
            'last synced',
            'never' if info.last_synced_at is None else info.last_synced_at.isoformat(),
        ),
    ]
    for name, value in rows:
        table.add_row(
            wambatic.reports.terminal.text_cell(name), wambatic.reports.terminal.text_cell(value)
        )
    return table


def run_cache(
    command: CacheCommand, settings: wambatic.settings.Settings, console: rich.console.Console
) -> None:
    """`cache info` describes the cache, `cache clear` removes it; neither uses the network."""
    path = settings.fetch.cache_path
    if command.action == 'info':
        info = wambatic.fetch.cache.inspect_cache(path)
        if info is None:
            console.print(wambatic.reports.terminal.text_cell(f'no cache at {path}'))
        else:
            console.print(cache_info_table(info))
        return
    removed = wambatic.fetch.cache.clear_cache(path)
    for deleted in removed:
        loguru.logger.info(f'Removed {deleted}')
    if not removed:
        loguru.logger.info(f'no cache at {path}')


def log_level(root: Wambatic) -> str:
    if root.quiet and not root.verbose:
        return 'WARNING'
    if root.verbose and not root.quiet:
        return 'DEBUG'
    return 'INFO'


def redact_environment_token(text: str) -> str:
    return wambatic.fetch.auth.redact(text, os.environ.get('GITHUB_TOKEN', '').strip())


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


def execute(root: Wambatic) -> None:
    check_verbosity(root)
    command = root.command
    console = rich.console.Console()
    if isinstance(command, Report):
        settings = wambatic.settings.load_settings(None, overrides(command))
        asyncio.run(run_report(command, settings, console, sys.stdout))
    else:
        run_cache(command, wambatic.settings.load_settings(None, {}), console)


def exit_status(code: str | int | None) -> int:
    return code if isinstance(code, int) else 0 if code is None else 1


def main(argv: list[str] | None = None) -> int:
    """Parse `argv` (default `sys.argv[1:]`), run the command and return the exit status; every
    error is turned into a logged line and a status here and nowhere else."""
    try:
        root = cappa.parse(Wambatic, argv=sys.argv[1:] if argv is None else argv)
    except cappa.Exit as e:
        return exit_status(e.code)
    wambatic.logs.configure_logging(log_level(root))
    try:
        execute(root)
    except (wambatic.reports.errors.UsageError, wambatic.settings.SettingsError) as e:
        loguru.logger.error(redact_environment_token(str(e)))
        return 2
    except (
        wambatic.fetch.errors.FetchError,
        wambatic.reports.errors.OutputError,
        wambatic.stats.StatsError,
    ) as e:
        loguru.logger.error(redact_environment_token(str(e)))
        return 1
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # The reader of stdout went away (`wambatic report ... | head`). Rich ends the same way
        # for the terminal format; point stdout at the null device so exit does not flush again.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 1
    except Exception as e:
        redact_exception(e)
        loguru.logger.exception(f'Unexpected error: {redact_environment_token(str(e))}')
        return 1
    return 0


def run() -> None:
    """The `wambatic` console script and `python -m wambatic`."""
    sys.exit(main())
