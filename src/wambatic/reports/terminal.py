import collections.abc

import rich.box
import rich.console
import rich.table
import rich.text

import wambatic.stats.activity
import wambatic.stats.base
import wambatic.stats.flow

BLOCKS = '▁▂▃▄▅▆▇█'
TOTAL_METRICS = tuple(metric for metric, _ in wambatic.stats.activity.TOTAL_METRICS)
UNATTRIBUTED = wambatic.stats.activity.UNATTRIBUTED
PARTIAL_MARK = ' *'
TOP_CONTRIBUTORS_SHOWN = 20
BREAKDOWN_TITLES = (('repo', 'By repository'), ('author', 'By author'))
SIGNED_METRICS = frozenset({'lines_net'})
FLOW_COUNTS = wambatic.stats.flow.COUNT_METRICS
TREND_METRICS = (*TOTAL_METRICS, *FLOW_COUNTS)
FLOW_TIMES = wambatic.stats.flow.TIME_METRICS
NO_DATA = '-'


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


def text_cell(value: str) -> rich.text.Text:
    """A string cell that Rich does not read as markup (a login can be `dependabot[bot]`)."""
    return rich.text.Text(value)


def make_table(title: str, columns: collections.abc.Sequence[tuple[str, bool]]) -> rich.table.Table:
    """A borderless table whose numeric columns (the `True` ones) are right-aligned."""
    table = rich.table.Table(title=title, title_justify='left', box=rich.box.SIMPLE)
    for name, numeric in columns:
        table.add_column(name, justify='right' if numeric else 'left', no_wrap=True)
    return table


def subject_text(result: wambatic.stats.base.StatsResult) -> str:
    subject = result.subject
    name = subject.full_name if subject.kind == 'repo' else subject.login
    return f'{subject.kind} {name}'


def title_line(result: wambatic.stats.base.StatsResult) -> rich.text.Text:
    granularity = result.request.granularity
    by = 'total' if granularity is wambatic.stats.base.Granularity.TOTAL else f'by {granularity}'
    return rich.text.Text(
        f'{subject_text(result)}, {result.since} to {result.until}, {by}, {result.request.tz}',
        style='bold',
    )


def total_series(
    result: wambatic.stats.base.StatsResult,
) -> dict[str, list[tuple[wambatic.stats.base.Bucket, float]]]:
    """Each total series' points (the ones with no breakdown) in bucket order, by metric."""
    return {
        series.metric: sorted(series.points.items())
        for series in result.series
        if series.by is None
    }


def partial_labels(result: wambatic.stats.base.StatsResult) -> frozenset[str]:
    return frozenset(
        label for label in result.provenance.get('partial_buckets', '').split(',') if label
    )


def contributor_count(result: wambatic.stats.base.StatsResult) -> int:
    return sum(
        1 for row in result.tables.get('top_contributors', []) if row['login'] != UNATTRIBUTED
    )


def period_label(bucket: wambatic.stats.base.Bucket, partial: frozenset[str]) -> str:
    return bucket.label + (PARTIAL_MARK if bucket.label in partial else '')


def period_table(result: wambatic.stats.base.StatsResult) -> rich.table.Table:
    series = total_series(result)
    partial = partial_labels(result)
    buckets = [bucket for bucket, _ in series['commits']]
    table = make_table(
        'Activity by period',
        [
            ('Period', False),
            ('Commits', True),
            ('Contributors', True),
            ('Active days', True),
            ('Added', True),
            ('Deleted', True),
            ('Net', True),
        ],
    )
    for index, bucket in enumerate(buckets):
        label = period_label(bucket, partial)
        table.add_row(
            text_cell(label),
            *(
                format_number(series[metric][index][1], signed=metric in SIGNED_METRICS)
                for metric in TOTAL_METRICS
            ),
        )
    if partial & {bucket.label for bucket in buckets}:
        table.caption = '* partial period'
        table.caption_justify = 'left'
    if len(buckets) > 1:
        table.show_footer = True
        sums = {
            metric: sum(value for _, value in series[metric])
            for metric in TOTAL_METRICS
            if metric != 'contributors'
        }
        footer = [
            'Total',
            format_number(sums['commits']),
            format_number(contributor_count(result)),
            format_number(sums['active_days']),
            format_number(sums['lines_added']),
            format_number(sums['lines_deleted']),
            format_number(sums['lines_net'], signed=True),
        ]
        for column, text in zip(table.columns, footer, strict=True):
            column.footer = text
    return table


def bucket_list(result: wambatic.stats.base.StatsResult) -> list[wambatic.stats.base.Bucket]:
    """The result's buckets, from whichever total series is present."""
    series = total_series(result)
    for metric in (*TOTAL_METRICS, *FLOW_COUNTS):
        if metric in series:
            return [bucket for bucket, _ in series[metric]]
    return []


def partial_note(partial: frozenset[str], buckets: list[wambatic.stats.base.Bucket]) -> str:
    return '* partial period' if partial & {bucket.label for bucket in buckets} else ''


def flow_table(result: wambatic.stats.base.StatsResult) -> rich.table.Table:
    series = total_series(result)
    partial = partial_labels(result)
    buckets = bucket_list(result)
    table = make_table(
        'Flow by period',
        [
            ('Period', False),
            ('PRs opened', True),
            ('PRs merged', True),
            ('Issues opened', True),
            ('Issues closed', True),
        ],
    )
    for index, bucket in enumerate(buckets):
        label = period_label(bucket, partial)
        table.add_row(
            text_cell(label), *(format_number(series[metric][index][1]) for metric in FLOW_COUNTS)
        )
    if note := partial_note(partial, buckets):
        table.caption = note
        table.caption_justify = 'left'
    if len(buckets) > 1:
        table.show_footer = True
        footer = ['Total']
        footer += [format_number(sum(value for _, value in series[m])) for m in FLOW_COUNTS]
        for column, text in zip(table.columns, footer, strict=True):
            column.footer = text
    return table


def flow_times_table(result: wambatic.stats.base.StatsResult) -> rich.table.Table:
    series = total_series(result)
    partial = partial_labels(result)
    buckets = bucket_list(result)
    table = make_table(
        'Flow times by period',
        [
            ('Period', False),
            ('Review p50', True),
            ('Review p90', True),
            ('Merge p50', True),
            ('Merge p90', True),
            ('Close p50', True),
            ('Close p90', True),
            ('PR size p50', True),
        ],
    )
    points = {
        metric: dict(series[metric]) for metric in (*FLOW_TIMES, wambatic.stats.flow.SIZE_METRIC)
    }
    for bucket in buckets:
        label = period_label(bucket, partial)
        cells = [
            NO_DATA
            if bucket not in points[metric]
            else format_number(points[metric][bucket], decimals=1)
            for metric in FLOW_TIMES
        ]
        size = points[wambatic.stats.flow.SIZE_METRIC].get(bucket)
        cells.append(NO_DATA if size is None else format_number(size))
        table.add_row(text_cell(label), *cells)
    note = partial_note(partial, buckets)
    table.caption = f'{note}; hours; {NO_DATA} no data' if note else f'hours; {NO_DATA} no data'
    table.caption_justify = 'left'
    return table


def plural(count: int) -> str:
    return 'period' if count == 1 else 'periods'


def value_range(values: list[float], *, signed: bool) -> str:
    low, high = format_number(min(values), signed=signed), format_number(max(values), signed=signed)
    return f'{low} to {high}'


def trend_lines(result: wambatic.stats.base.StatsResult, width: int) -> list[str]:
    """One `<metric>  <sparkline>  <min> to <max>` line per total series, cropped to the latest
    buckets that fit `width` with `last N periods` added."""
    series = total_series(result)
    buckets = len(bucket_list(result))
    metrics = [m for m in TREND_METRICS if m in series and len(series[m]) == buckets]
    label_width = max(len(metric) for metric in metrics)
    lines: list[str] = []
    for metric in metrics:
        values = [value for _, value in series[metric]]
        shown = len(values)
        while True:
            kept = values[len(values) - shown :]
            span = value_range(kept, signed=metric in SIGNED_METRICS)
            note = '' if shown == len(values) else f'  last {shown} {plural(shown)}'
            line = f'{metric:<{label_width}}  {sparkline(kept)}  {span}{note}'
            if len(line) <= width or shown == 1:
                break
            shown -= 1
        lines.append(line)
    return lines


def provenance_lines(result: wambatic.stats.base.StatsResult) -> list[str]:
    provenance = result.provenance
    keys = ['computed_at', *sorted(k for k in provenance if k.startswith('fetched_at:'))]
    keys += ['wambatic_version', 'schema_version']
    lines = [f'{key}: {provenance[key]}' for key in keys if key in provenance]
    if 'version_override_at' in provenance:
        lines.append(
            f'Warning: the cache was read with --ignore-cache-version at '
            f'{provenance["version_override_at"]}; its recorded version differs from this wambatic'
        )
    return lines


def heading(console: rich.console.Console, text: str) -> None:
    console.print()
    console.print(rich.text.Text(text, style='bold'))


def breakdown_rows(
    result: wambatic.stats.base.StatsResult, kind: str
) -> list[tuple[str, dict[str, float]]]:
    """Each breakdown name of `kind` with its metrics summed over the range, most commits first
    and then by name, leaving out names whose metrics are all zero."""
    totals: dict[str, dict[str, float]] = {}
    for series in result.series:
        if series.by_kind == kind and series.by is not None:
            totals.setdefault(series.by, {})[series.metric] = sum(series.points.values())
    rows = [(name, metrics) for name, metrics in totals.items() if any(metrics.values())]
    return sorted(rows, key=lambda row: (-row[1].get('commits', 0), row[0]))


def render_breakdowns(
    result: wambatic.stats.base.StatsResult, console: rich.console.Console
) -> None:
    """By repository and By author (item 4 of the terminal layout)."""
    for kind, title in BREAKDOWN_TITLES:
        rows = breakdown_rows(result, kind)
        if not any(series.by_kind == kind for series in result.series):
            continue
        table = make_table(
            title,
            [('Name', False), ('Commits', True), ('Added', True), ('Deleted', True), ('Net', True)],
        )
        for name, metrics in rows:
            table.add_row(
                text_cell(name),
                format_number(metrics['commits']),
                format_number(metrics['lines_added']),
                format_number(metrics['lines_deleted']),
                format_number(metrics['lines_net'], signed=True),
            )
        console.print()
        console.print(table)


def render_top_contributors(
    result: wambatic.stats.base.StatsResult, console: rich.console.Console
) -> None:
    """Top contributors (item 5): the first TOP_CONTRIBUTORS_SHOWN rows of the table."""
    rows = result.tables.get('top_contributors', [])
    if not rows:
        return
    table = make_table(
        'Top contributors',
        [
            ('Login', False),
            ('Commits', True),
            ('Added', True),
            ('Deleted', True),
            ('Net', True),
            ('Active days', True),
        ],
    )
    for row in rows[:TOP_CONTRIBUTORS_SHOWN]:
        table.add_row(
            text_cell(row['login']),
            format_number(row['commits']),
            format_number(row['lines_added']),
            format_number(row['lines_deleted']),
            format_number(row['lines_net'], signed=True),
            format_number(row['active_days']),
        )
    console.print()
    console.print(table)
    if len(rows) > TOP_CONTRIBUTORS_SHOWN:
        console.print(rich.text.Text(f'and {len(rows) - TOP_CONTRIBUTORS_SHOWN} more'))


def render_unavailable(
    result: wambatic.stats.base.StatsResult, console: rich.console.Console
) -> None:
    """Unavailable (item 6): the metrics the report leaves out, and why."""
    rows = result.tables.get('unavailable', [])
    if not rows:
        return
    table = make_table('Unavailable', [('Metric', False), ('Reason', False)])
    for row in rows:
        table.add_row(text_cell(row['metric']), text_cell(row['reason']))
    console.print()
    console.print(table)


def render_flow(result: wambatic.stats.base.StatsResult, console: rich.console.Console) -> None:
    """Flow by period and Flow times by period (items 6 and 7 of the terminal layout)."""
    console.print()
    console.print(flow_table(result))
    console.print()
    console.print(flow_times_table(result))


def render_terminal(result: wambatic.stats.base.StatsResult, console: rich.console.Console) -> None:
    series = total_series(result)
    console.print(title_line(result))
    if 'commits' in series:
        console.print(period_table(result))
    if len(bucket_list(result)) > 1 and any(metric in series for metric in TREND_METRICS):
        heading(console, 'Trends')
        for line in trend_lines(result, console.width):
            console.print(rich.text.Text(line))
    if 'commits' in series:
        render_breakdowns(result, console)
        render_top_contributors(result, console)
    if 'prs_opened' in series:
        render_flow(result, console)
    render_unavailable(result, console)
    heading(console, 'Provenance')
    for line in provenance_lines(result):
        console.print(rich.text.Text(line))
