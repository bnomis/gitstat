import asyncio
import collections.abc
import contextlib
import dataclasses
import datetime
import os
import pathlib
import sys
import typing
import zoneinfo

import cappa
import loguru
import rich.box
import rich.console
import rich.table

import wambatic.fetch.base
import wambatic.fetch.cache
import wambatic.fetch.errors
import wambatic.fetch.ratelimit
import wambatic.logs
import wambatic.reports.base
import wambatic.reports.errors
import wambatic.reports.html
import wambatic.reports.service
import wambatic.reports.terminal
import wambatic.reports.web
import wambatic.settings
import wambatic.stats
import wambatic.stats.base

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
        cappa.Arg(
            long=True,
            help=(
                'Comma-separated metric groups: activity, flow, delivery, popularity '
                '(default: activity,flow)'
            ),
        ),
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


@cappa.command(name='serve', help='Run the web app, on this machine only unless told otherwise.')
@dataclasses.dataclass
class Serve:
    target: typing.Annotated[
        str | None,
        cappa.Arg(help='Fills the form and names the first report URL, like the report target'),
    ] = None
    host: typing.Annotated[
        str | None,
        cappa.Arg(long=True, help='Address to listen on (default: report.web_host, 127.0.0.1)'),
    ] = None
    port: typing.Annotated[
        int | None, cappa.Arg(long=True, help='Port to listen on (default: report.web_port, 8000)')
    ] = None
    allow_remote: typing.Annotated[
        bool,
        cappa.Arg(
            long=True,
            help='Listen on an address other than loopback; anyone who can reach it'
            ' acts with your GitHub token',
        ),
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
    command: cappa.Subcommands[Report | Serve | CacheCommand]
    verbose: typing.Annotated[
        bool, cappa.Arg(short='-v', long=True, help='Log debugging detail')
    ] = False
    quiet: typing.Annotated[
        bool, cappa.Arg(short='-q', long=True, help='Log warnings and errors only')
    ] = False


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


def serve_overrides(serve: Serve) -> dict[str, object]:
    """The `load_settings` overrides for the flags of `serve`, only where given."""
    result: dict[str, dict[str, object]] = {}
    if serve.host is not None:
        result.setdefault('report', {})['web_host'] = serve.host
    if serve.port is not None:
        result.setdefault('report', {})['web_port'] = serve.port
    if serve.allow_remote:
        result.setdefault('report', {})['allow_remote'] = True
    if serve.max_age is not None:
        result.setdefault('fetch', {})['max_age'] = serve.max_age
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
    target = wambatic.reports.service.parse_target(report.target)
    if report.no_fetch and isinstance(target, str):
        raise wambatic.reports.errors.UsageError(
            '--no-fetch needs user:NAME or org:NAME: a bare NAME is resolved with the network'
        )
    if report.by_author and not isinstance(target, str):
        wambatic.reports.service.check_by_author(target)


def build_request(
    report: Report, settings: wambatic.settings.Settings, tz: zoneinfo.ZoneInfo
) -> wambatic.stats.base.StatsRequest:
    return wambatic.reports.service.make_request(
        report.by, report.since, report.until, report.groups, report.by_author, tz, settings
    )


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
    page = wambatic.reports.html.html_report(results, wambatic.stats.base.Granularity(report.by))
    path = output_path(report.out, settings, subject)
    wambatic.reports.html.render_html(page, path, settings.report.html_theme)
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
    target = wambatic.reports.service.parse_target(report.target)
    check_report(report, settings)
    request = build_request(report, settings, wambatic.reports.service.resolve_tz(settings))
    wambatic.stats.resources_for(request.groups)
    cache = wambatic.fetch.cache.Cache.open(
        settings.fetch.cache_path, ignore_version=report.ignore_cache_version
    )
    as_html = settings.report.format == 'html'
    requests = wambatic.reports.html.period_requests(request) if as_html else [request]
    try:
        subject, results = await wambatic.reports.service.build_results(
            settings,
            cache,
            target,
            requests,
            by_author=report.by_author,
            full_refresh=report.full_refresh,
            no_fetch=report.no_fetch,
            clock=clock,
        )
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
        ('releases', wambatic.reports.terminal.format_number(info.releases)),
        ('workflow runs', wambatic.reports.terminal.format_number(info.workflow_runs)),
        ('star events', wambatic.reports.terminal.format_number(info.star_events)),
        ('forks', wambatic.reports.terminal.format_number(info.forks)),
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


def execute(root: Wambatic) -> None:
    check_verbosity(root)
    command = root.command
    console = rich.console.Console()
    if isinstance(command, Report):
        settings = wambatic.settings.load_settings(None, overrides(command))
        asyncio.run(run_report(command, settings, console, sys.stdout))
    elif isinstance(command, Serve):
        wambatic.reports.web.serve(
            wambatic.settings.load_settings(None, serve_overrides(command)),
            default_target=command.target,
            ignore_cache_version=command.ignore_cache_version,
        )
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
        loguru.logger.error(wambatic.reports.service.redact_environment_token(str(e)))
        return 2
    except (
        wambatic.fetch.errors.FetchError,
        wambatic.reports.errors.OutputError,
        wambatic.reports.errors.ServeError,
        wambatic.stats.StatsError,
    ) as e:
        loguru.logger.error(wambatic.reports.service.redact_environment_token(str(e)))
        return 1
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # The reader of stdout went away (`wambatic report ... | head`). Rich ends the same way
        # for the terminal format; point stdout at the null device so exit does not flush again.
        with contextlib.suppress(OSError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 1
    except Exception as e:
        loguru.logger.exception(f'Unexpected error: {wambatic.reports.service.redact_error(e)}')
        return 1
    return 0


def run() -> None:
    """The `wambatic` console script and `python -m wambatic`."""
    sys.exit(main())
