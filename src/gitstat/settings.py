import dataclasses
import datetime
import json
import os
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


class SettingsError(Exception):
    """A config file or override that cannot be turned into `Settings`."""


DEFAULT_CONFIG_PATH = pathlib.Path('~/.config/gitstat/config.json')
DURATION_UNITS = {
    's': datetime.timedelta(seconds=1),
    'm': datetime.timedelta(minutes=1),
    'h': datetime.timedelta(hours=1),
    'd': datetime.timedelta(days=1),
    'w': datetime.timedelta(weeks=1),
}
SECTIONS: dict[str, type] = {
    'fetch': FetchSettings,
    'report': ReportSettings,
    'stats': StatsSettings,
}


def parse_duration(text: str) -> datetime.timedelta:
    """Parse a non-negative integer and one unit of `s`, `m`, `h`, `d` or `w`."""
    digits, unit = text[:-1], text[-1:]
    if not (digits.isascii() and digits.isdigit() and unit in DURATION_UNITS):
        raise SettingsError('a duration is a non-negative integer and one unit of s, m, h, d or w')
    return int(digits) * DURATION_UNITS[unit]


def convert(key: str, annotation: object, value: object) -> object:
    """Check `value` against a setting's type and return it in that type."""
    if typing.get_origin(annotation) is typing.Literal:
        allowed = typing.get_args(annotation)
        if value not in allowed:
            raise SettingsError(f'{key} must be one of {", ".join(allowed)}')
        return value
    if annotation is bool:
        ok = isinstance(value, bool)
    elif annotation is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif annotation is str:
        ok = isinstance(value, str)
    elif annotation == str | None:
        ok = value is None or isinstance(value, str)
    elif annotation == tuple[str, ...]:
        if isinstance(value, list | tuple) and all(isinstance(item, str) for item in value):
            return tuple(value)
        ok = False
    elif annotation is pathlib.Path:
        if isinstance(value, str | pathlib.Path):
            return pathlib.Path(value).expanduser()
        ok = False
    elif annotation is datetime.timedelta:
        if isinstance(value, datetime.timedelta):
            return value
        if isinstance(value, str):
            try:
                return parse_duration(value)
            except SettingsError as e:
                raise SettingsError(f'{key}: {e}') from None
        ok = False
    else:
        raise TypeError(f'no conversion for {key}: {annotation}')
    if not ok:
        raise SettingsError(f'{key} has the wrong type')
    return value


def apply_section(name: str, current: object, values: object, source: str) -> object:
    if not isinstance(values, dict):
        raise SettingsError(f'{source}: {name} must be an object')
    hints = typing.get_type_hints(type(current))
    changes: dict[str, object] = {}
    for field, value in values.items():
        if field not in hints:
            raise SettingsError(f'{source}: unknown setting {name}.{field}')
        changes[field] = convert(f'{name}.{field}', hints[field], value)
    return dataclasses.replace(current, **changes)  # type: ignore[type-var]


def apply_layer(settings: Settings, layer: object, source: str) -> Settings:
    if not isinstance(layer, dict):
        raise SettingsError(f'{source} must be an object')
    for name in layer:
        if name not in SECTIONS:
            raise SettingsError(f'{source}: unknown section {name}')
    changes: dict[str, typing.Any] = {
        name: apply_section(name, getattr(settings, name), values, source)
        for name, values in layer.items()
    }
    return dataclasses.replace(settings, **changes)


def read_config(config_path: pathlib.Path | None) -> object:
    named = config_path
    if named is None and 'GITSTAT_CONFIG' in os.environ:
        named = pathlib.Path(os.environ['GITSTAT_CONFIG'])
    path = (named or DEFAULT_CONFIG_PATH).expanduser()
    try:
        text = path.read_text()
    except FileNotFoundError:
        if named is not None:
            raise SettingsError(f'config file {path} does not exist') from None
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SettingsError(f'config file {path} is not valid JSON ({e.msg})') from None


def load_settings(config_path: pathlib.Path | None, overrides: dict[str, object]) -> Settings:
    """Defaults, then the JSON file, then `overrides`; later wins."""
    settings = apply_layer(Settings(), read_config(config_path), 'config file')
    return apply_layer(settings, overrides, 'overrides')
