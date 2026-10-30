import collections.abc

import rich.box
import rich.console
import rich.table
import rich.text

import wambatic.reports.rows
import wambatic.stats.base

BLOCKS = '▁▂▃▄▅▆▇█'


def __getattr__(name: str) -> int:
    """`TOP_CONTRIBUTORS_SHOWN` stays reachable here, but it lives in `rows`; `wambatic.reports`
    is still being imported when this module loads, so it cannot be copied at import time."""
    if name == 'TOP_CONTRIBUTORS_SHOWN':
        return wambatic.reports.rows.TOP_CONTRIBUTORS_SHOWN
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def sparkline(values: list[float]) -> str:
    """One block character per value from U+2581 to U+2588, scaled linearly from the minimum to
    the maximum; all-equal values give U+2581 throughout and an empty list gives ''."""
    if not values:
        return ''
    low, high = min(values), max(values)
    if high == low:
        return BLOCKS[0] * len(values)
    top = len(BLOCKS) - 1
    return ''.join(BLOCKS[round((value - low) / (high - low) * top)] for value in values)


def format_number(value: float, *, signed: bool = False, decimals: int | None = None) -> str:
    """Thousands separators; with `signed`, an explicit sign on every non-zero value. A whole
    number has no decimals and another has two, unless `decimals` fixes the count."""
    number: float = int(value) if float(value).is_integer() else value
    if decimals is not None:
        text = f'{value:,.{decimals}f}'
    else:
        text = f'{number:,}' if isinstance(number, int) else f'{number:,.2f}'
    if signed and number > 0:
        return f'+{text}'
    return text


def format_cell(metric: str, value: float | None) -> str:
    """A period table's cell: hours and minutes with one decimal place, ratios as percentages,
    `lines_net` signed, `-` for no data."""
    if value is None:
        return wambatic.reports.rows.NO_DATA
    if metric in wambatic.reports.rows.FLOW_TIMES:
        return format_number(value, decimals=1)
    unit = wambatic.reports.rows.DELIVERY_UNITS.get(metric)
    if unit == 'ratio':
        return f'{value * 100:,.1f}%'
    if unit in ('minutes', 'hours'):
        return format_number(value, decimals=1)
    return format_number(value, signed=metric in wambatic.reports.rows.SIGNED_METRICS)


def text_cell(value: str) -> rich.text.Text:
    """A string cell that Rich does not read as markup (a login can be `dependabot[bot]`)."""
    return rich.text.Text(value)


def make_table(title: str, columns: collections.abc.Sequence[tuple[str, bool]]) -> rich.table.Table:
    """A borderless table whose numeric columns (the `True` ones) are right-aligned."""
    table = rich.table.Table(title=title, title_justify='left', box=rich.box.SIMPLE)
    for name, numeric in columns:
        table.add_column(name, justify='right' if numeric else 'left', no_wrap=True)
    return table


def title_line(result: wambatic.stats.base.StatsResult) -> rich.text.Text:
    granularity = result.request.granularity
    by = 'total' if granularity is wambatic.stats.base.Granularity.TOTAL else f'by {granularity}'
    return rich.text.Text(
        f'{wambatic.reports.rows.subject_text(result)}, {result.since} to {result.until}, {by}, '
        f'{result.request.tz}',
        style='bold',
    )


def period_table(
    table: wambatic.reports.rows.PeriodTable, *, caption: str | None = None
) -> rich.table.Table:
    """A period table from its rows; `caption` replaces the partial-period note."""
    rich_table = make_table(
        table.title, [('Period', False), *((header, True) for header in table.headers)]
    )
    for row in table.rows:
        label = row.label + (wambatic.reports.rows.PARTIAL_MARK if row.partial else '')
        rich_table.add_row(
            text_cell(label),
            *(
                format_cell(metric, value)
                for metric, value in zip(table.metrics, row.values, strict=True)
            ),
        )
    if caption is None and table.has_partial:
        caption = '* partial period'
    if caption is not None:
        rich_table.caption = caption
        rich_table.caption_justify = 'left'
    if table.total is not None:
        rich_table.show_footer = True
        footers = [
            'Total',
            *(
                format_cell(metric, value)
                for metric, value in zip(table.metrics, table.total, strict=True)
            ),
        ]
        for column, text in zip(rich_table.columns, footers, strict=True):
            column.footer = text
    return rich_table


def flow_times_caption(table: wambatic.reports.rows.PeriodTable) -> str:
    unit = f'hours; {wambatic.reports.rows.NO_DATA} no data'
    return f'* partial period; {unit}' if table.has_partial else unit


def plural(count: int) -> str:
    return 'period' if count == 1 else 'periods'


def value_range(values: list[float], *, signed: bool) -> str:
    low, high = format_number(min(values), signed=signed), format_number(max(values), signed=signed)
    return f'{low} to {high}'


def trend_lines(result: wambatic.stats.base.StatsResult, width: int) -> list[str]:
    """One `<metric>  <sparkline>  <min> to <max>` line per total series, cropped to the latest
    buckets that fit `width` with `last N periods` added."""
    series = wambatic.reports.rows.total_series(result)
    buckets = len(wambatic.reports.rows.bucket_list(result))
    metrics = [
        m for m in wambatic.reports.rows.TREND_METRICS if m in series and len(series[m]) == buckets
    ]
    label_width = max(len(metric) for metric in metrics)
    lines: list[str] = []
    for metric in metrics:
        values = [value for _, value in series[metric]]
        shown = len(values)
        while True:
            kept = values[len(values) - shown :]
            span = value_range(kept, signed=metric in wambatic.reports.rows.SIGNED_METRICS)
            note = '' if shown == len(values) else f'  last {shown} {plural(shown)}'
            line = f'{metric:<{label_width}}  {sparkline(kept)}  {span}{note}'
            if len(line) <= width or shown == 1:
                break
            shown -= 1
        lines.append(line)
    return lines


def heading(console: rich.console.Console, text: str) -> None:
    console.print()
    console.print(rich.text.Text(text, style='bold'))


def render_breakdowns(
    result: wambatic.stats.base.StatsResult, console: rich.console.Console
) -> None:
    """By repository and By author (item 4 of the terminal layout)."""
    for kind, title in wambatic.reports.rows.BREAKDOWN_TITLES:
        rows = wambatic.reports.rows.breakdown_rows(result, kind)
        if rows is None:
            continue
        table = make_table(
            title,
            [
                (header, header != wambatic.reports.rows.BREAKDOWN_HEADERS[0])
                for header in wambatic.reports.rows.BREAKDOWN_HEADERS
            ],
        )
        for row in rows:
            table.add_row(
                text_cell(row.name),
                format_number(row.commits),
                format_number(row.lines_added),
                format_number(row.lines_deleted),
                format_number(row.lines_net, signed=True),
            )
        console.print()
        console.print(table)


def render_top_contributors(
    result: wambatic.stats.base.StatsResult, console: rich.console.Console
) -> None:
    """Top contributors (item 5): the first TOP_CONTRIBUTORS_SHOWN rows of the table."""
    everyone = wambatic.reports.rows.top_contributors(result)
    if not everyone:
        return
    table = make_table(
        'Top contributors',
        [
            (header, header != wambatic.reports.rows.CONTRIBUTOR_HEADERS[0])
            for header in wambatic.reports.rows.CONTRIBUTOR_HEADERS
        ],
    )
    for row in everyone[: wambatic.reports.rows.TOP_CONTRIBUTORS_SHOWN]:
        table.add_row(
            text_cell(row.login),
            format_number(row.commits),
            format_number(row.lines_added),
            format_number(row.lines_deleted),
            format_number(row.lines_net, signed=True),
            format_number(row.active_days),
        )
    console.print()
    console.print(table)
    if len(everyone) > wambatic.reports.rows.TOP_CONTRIBUTORS_SHOWN:
        console.print(
            rich.text.Text(
                f'and {len(everyone) - wambatic.reports.rows.TOP_CONTRIBUTORS_SHOWN} more'
            )
        )


def render_unavailable(
    result: wambatic.stats.base.StatsResult, console: rich.console.Console
) -> None:
    """Unavailable (item 6): the metrics the report leaves out, and why."""
    rows = wambatic.reports.rows.unavailable_rows(result)
    if not rows:
        return
    table = make_table(
        'Unavailable', [(header, False) for header in wambatic.reports.rows.UNAVAILABLE_HEADERS]
    )
    for metric, reason in rows:
        table.add_row(text_cell(metric), text_cell(reason))
    console.print()
    console.print(table)


def render_flow(result: wambatic.stats.base.StatsResult, console: rich.console.Console) -> None:
    """Flow by period and Flow times by period (items 6 and 7 of the terminal layout)."""
    flow = wambatic.reports.rows.flow_table(result)
    times = wambatic.reports.rows.flow_times_table(result)
    if flow is None or times is None:
        return
    console.print()
    console.print(period_table(flow))
    console.print()
    console.print(period_table(times, caption=flow_times_caption(times)))


def render_delivery(result: wambatic.stats.base.StatsResult, console: rich.console.Console) -> None:
    """Delivery by period and DORA proxies by period (items 8 and 9 of the terminal layout)."""
    for table, unit in (
        (wambatic.reports.rows.delivery_table(result), 'minutes and days'),
        (wambatic.reports.rows.dora_table(result), 'proxies: see the README; hours'),
    ):
        if table is not None:
            console.print()
            console.print(period_table(table, caption=delivery_caption(table, unit)))


def delivery_caption(table: wambatic.reports.rows.PeriodTable, unit: str) -> str:
    note = f'{unit}; {wambatic.reports.rows.NO_DATA} no data'
    return f'* partial period; {note}' if table.has_partial else note


def popularity_caption(table: wambatic.reports.rows.PeriodTable) -> str:
    note = 'totals: stars and forks that exist now, by when they were made'
    return f'* partial period; {note}' if table.has_partial else note


def render_popularity(
    result: wambatic.stats.base.StatsResult, console: rich.console.Console
) -> None:
    """Popularity by period, Popularity now and Languages (items 10 to 12 of the layout)."""
    by_period = wambatic.reports.rows.popularity_table(result)
    if by_period is None:
        return
    console.print()
    console.print(period_table(by_period, caption=popularity_caption(by_period)))
    now = wambatic.reports.rows.popularity_now(result)
    if now is not None:
        table = make_table(
            'Popularity now',
            [
                (header, header != wambatic.reports.rows.POPULARITY_NOW_HEADERS[0])
                for header in wambatic.reports.rows.POPULARITY_NOW_HEADERS
            ],
        )
        for row in now.rows:
            table.add_row(
                text_cell(row.repo),
                format_number(row.stars),
                format_number(row.forks),
                format_number(row.watchers),
            )
        if now.total is not None:
            table.show_footer = True
            footers = [
                now.total.repo,
                format_number(now.total.stars),
                format_number(now.total.forks),
                format_number(now.total.watchers),
            ]
            for column, text in zip(table.columns, footers, strict=True):
                column.footer = text
        table.caption = 'as of the last sync; forks: whole network'
        table.caption_justify = 'left'
        console.print()
        console.print(table)
    languages = wambatic.reports.rows.languages_rows(
        result, wambatic.reports.rows.TOP_LANGUAGES_SHOWN
    )
    if languages is None:
        return
    table = make_table(
        'Languages',
        [
            (header, header != wambatic.reports.rows.LANGUAGE_HEADERS[0])
            for header in wambatic.reports.rows.LANGUAGE_HEADERS
        ],
    )
    for language in languages.rows:
        table.add_row(
            text_cell(language.language),
            format_number(language.bytes),
            f'{language.share * 100:,.1f}%',
        )
    console.print()
    console.print(table)
    if languages.more:
        console.print(rich.text.Text(f'and {languages.more} more'))


def render_terminal(result: wambatic.stats.base.StatsResult, console: rich.console.Console) -> None:
    series = wambatic.reports.rows.total_series(result)
    activity = wambatic.reports.rows.activity_table(result)
    console.print(title_line(result))
    if activity is not None:
        console.print(period_table(activity))
    if len(wambatic.reports.rows.bucket_list(result)) > 1 and any(
        metric in series for metric in wambatic.reports.rows.TREND_METRICS
    ):
        heading(console, 'Trends')
        for line in trend_lines(result, console.width):
            console.print(rich.text.Text(line))
    if activity is not None:
        render_breakdowns(result, console)
        render_top_contributors(result, console)
    render_flow(result, console)
    render_delivery(result, console)
    render_popularity(result, console)
    render_unavailable(result, console)
    heading(console, 'Provenance')
    for line in wambatic.reports.rows.provenance_lines(result):
        console.print(rich.text.Text(line))
