import dataclasses
import datetime
import json
import typing

import gitstat.settings
import gitstat.stats.base

FORMAT_VERSION = 1
INTEGER_UNITS = frozenset({'count', 'days', 'lines'})


def setting_to_json(value: object) -> object:
    """A `StatsSettings` value as JSON data: tuples as lists, durations as `<seconds>s`, which
    `gitstat.settings.parse_duration` reads back."""
    if isinstance(value, datetime.timedelta):
        return f'{int(value.total_seconds())}s'
    if isinstance(value, tuple):
        return list(value)
    return value


def series_to_dict(series: gitstat.stats.base.Series) -> dict[str, object]:
    integer = series.unit in INTEGER_UNITS
    return {
        'metric': series.metric,
        'unit': series.unit,
        'by': series.by,
        'by_kind': series.by_kind,
        'points': [
            {
                'label': bucket.label,
                'start': bucket.start.isoformat(),
                'value': int(value) if integer else float(value),
            }
            for bucket, value in series.points.items()
        ],
    }


def result_to_dict(result: gitstat.stats.base.StatsResult) -> dict[str, object]:
    """The result as JSON-ready data; shared by `--format json` and the web app's JSON API."""
    request = result.request
    return {
        'format_version': FORMAT_VERSION,
        'subject': {
            'kind': result.subject.kind,
            'login': result.subject.login,
            'name': result.subject.name,
        },
        'request': {
            'granularity': request.granularity.value,
            'groups': sorted(request.groups),
            'since': None if request.since is None else request.since.isoformat(),
            'until': None if request.until is None else request.until.isoformat(),
            'by_author': request.by_author,
            'tz': str(request.tz),
            'settings': {
                field.name: setting_to_json(getattr(request.settings, field.name))
                for field in dataclasses.fields(gitstat.settings.StatsSettings)
            },
        },
        'since': result.since.isoformat(),
        'until': result.until.isoformat(),
        'series': [series_to_dict(series) for series in result.series],
        'tables': result.tables,
        'provenance': result.provenance,
    }


def render_json(result: gitstat.stats.base.StatsResult, stream: typing.TextIO) -> None:
    stream.write(json.dumps(result_to_dict(result), indent=2, ensure_ascii=False) + '\n')
