import dataclasses
import datetime
import enum
import typing

import wambatic.fetch
import wambatic.settings

GROUPS = frozenset({'activity', 'delivery', 'flow', 'popularity'})


class Granularity(enum.StrEnum):
    DAY = 'day'
    MONTH = 'month'
    TOTAL = 'total'
    WEEK = 'week'
    YEAR = 'year'


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class Bucket:
    start: datetime.date
    label: str


@dataclasses.dataclass(frozen=True, slots=True)
class Series:
    metric: str
    unit: str
    points: dict[Bucket, float]
    by: str | None = None
    by_kind: typing.Literal['author', 'repo'] | None = None

    def __post_init__(self) -> None:
        if (self.by is None) != (self.by_kind is None):
            raise ValueError('by and by_kind are both set or both None')


@dataclasses.dataclass(frozen=True, slots=True)
class StatsRequest:
    granularity: Granularity = Granularity.MONTH
    groups: frozenset[str] = frozenset({'activity', 'flow'})
    since: datetime.date | None = None
    until: datetime.date | None = None
    by_author: bool = False
    tz: datetime.tzinfo = datetime.UTC
    settings: wambatic.settings.StatsSettings = dataclasses.field(
        default_factory=wambatic.settings.StatsSettings
    )


@dataclasses.dataclass(frozen=True, slots=True)
class StatsResult:
    subject: wambatic.fetch.Subject
    request: StatsRequest
    since: datetime.date
    until: datetime.date
    series: list[Series]
    tables: dict[str, list[dict[str, typing.Any]]]
    provenance: dict[str, str]
