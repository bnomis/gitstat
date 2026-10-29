import dataclasses
import datetime
import re
import typing
import zoneinfo

import cappa

import gitstat.fetch.base
import gitstat.reports.errors
import gitstat.settings
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
    if report.no_fetch and isinstance(parse_target(report.target), str):
        raise gitstat.reports.errors.UsageError(
            '--no-fetch needs user:NAME or org:NAME: a bare NAME is resolved with the network'
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
