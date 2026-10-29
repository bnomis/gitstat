import dataclasses
import datetime
import pathlib
import typing


@dataclasses.dataclass(frozen=True, slots=True)
class FetchSettings:
    cache_path: pathlib.Path = pathlib.Path('~/.cache/gitstat/cache.sqlite3').expanduser()
    full_refresh_after: datetime.timedelta = datetime.timedelta(days=30)
    include_archived: bool = False
    include_forks: bool = False
    max_age: datetime.timedelta = datetime.timedelta(0)
    max_retries: int = 5
    on_rate_limit: typing.Literal['wait', 'fail'] = 'wait'
    overlap: datetime.timedelta = datetime.timedelta(hours=1)
    stats_retries: int = 6
    workers: int = 4


@dataclasses.dataclass(frozen=True, slots=True)
class StatsSettings:
    bot_logins: tuple[str, ...] = dataclasses.field(default=('dependabot[bot]', 'renovate[bot]'))
    deploy_workflow: str | None = None
    exclude_merge_commits: bool = True
    failure_window: datetime.timedelta = datetime.timedelta(days=7)
    hotfix_labels: tuple[str, ...] = dataclasses.field(default=('hotfix',))
    timezone: str = 'UTC'


@dataclasses.dataclass(frozen=True, slots=True)
class ReportSettings:
    allow_remote: bool = False
    format: typing.Literal['html', 'json', 'terminal'] = 'terminal'
    html_theme: typing.Literal['auto', 'dark', 'light'] = 'auto'
    out_dir: pathlib.Path = pathlib.Path('./gitstat-reports')
    web_host: str = '127.0.0.1'
    web_port: int = 8000


@dataclasses.dataclass(frozen=True, slots=True)
class Settings:
    fetch: FetchSettings = dataclasses.field(default_factory=FetchSettings)
    report: ReportSettings = dataclasses.field(default_factory=ReportSettings)
    stats: StatsSettings = dataclasses.field(default_factory=StatsSettings)
