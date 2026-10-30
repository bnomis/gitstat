"""The static HTML report: one self-contained file holding the summary, every chart and every
table, built from the results of one request that differ only in granularity."""

import dataclasses
import html
import importlib.resources
import json
import os
import pathlib
import re
import string
import tempfile
import typing

import plotly.offline

import wambatic.reports.figures
import wambatic.reports.rows
import wambatic.reports.terminal
import wambatic.stats.base

Granularity = wambatic.stats.base.Granularity
Theme = typing.Literal['auto', 'dark', 'light']
PERIODS = (Granularity.YEAR, Granularity.MONTH, Granularity.WEEK, Granularity.DAY)
SAFE_FILENAME = re.compile(r'[^A-Za-z0-9._-]')
FILE_MODE = 0o644
JSON_ESCAPES = {'<': '\\u003c', '>': '\\u003e', '&': '\\u0026'}


@dataclasses.dataclass(frozen=True, slots=True)
class HtmlReport:
    """The five results one page is built from: `total` for the tiles, the whole-range charts
    and tables, and one result for each of year, month, week and day for the switch; `initial`
    is the granularity shown on load."""

    total: wambatic.stats.base.StatsResult
    periods: dict[Granularity, wambatic.stats.base.StatsResult]
    initial: Granularity


class SubjectLike(typing.Protocol):
    """What `report_filename` reads of a `wambatic.fetch.Subject`, which `wambatic.reports` may
    not import."""

    @property
    def kind(self) -> str: ...

    @property
    def login(self) -> str: ...

    @property
    def full_name(self) -> str: ...


def report_filename(subject: SubjectLike) -> str:
    """`repo-OWNER-NAME.html`, `user-NAME.html` or `org-NAME.html`."""
    name = subject.full_name.replace('/', '-') if subject.kind == 'repo' else subject.login
    return f'{subject.kind}-{SAFE_FILENAME.sub("-", name)}.html'


def first_difference(
    total: wambatic.stats.base.StatsResult, other: wambatic.stats.base.StatsResult
) -> str | None:
    """The first thing, other than granularity, in which `other` was not made like `total`."""
    if total.subject != other.subject:
        return 'subject'
    for field in dataclasses.fields(wambatic.stats.base.StatsRequest):
        if field.name != 'granularity' and getattr(total.request, field.name) != getattr(
            other.request, field.name
        ):
            return f'request {field.name}'
    for name in ('since', 'until'):
        if getattr(total, name) != getattr(other, name):
            return f'the resolved {name}'
    return None


def check_report(report: HtmlReport) -> None:
    if report.total.request.granularity is not Granularity.TOTAL:
        raise ValueError(f'total must be a TOTAL result, not {report.total.request.granularity}')
    if set(report.periods) != set(PERIODS):
        raise ValueError(
            f'periods must be exactly {", ".join(PERIODS)}, not '
            f'{", ".join(sorted(report.periods)) or "none"}'
        )
    if report.initial not in report.periods:
        raise ValueError(f'initial must be one of {", ".join(PERIODS)}, not {report.initial}')
    for granularity, result in report.periods.items():
        if result.request.granularity is not granularity:
            raise ValueError(f'the {granularity} result is by {result.request.granularity}')
        if (difference := first_difference(report.total, result)) is not None:
            raise ValueError(f'the {granularity} result differs from the total in {difference}')


def read_template(name: str) -> str:
    resource = importlib.resources.files('wambatic.reports') / 'templates' / name
    return resource.read_text(encoding='utf-8')


def escape(text: object) -> str:
    return html.escape(str(text))


def json_for_script(data: object) -> str:
    """JSON that cannot close or open a script element, whatever the data holds."""
    text = json.dumps(data, ensure_ascii=False)
    return ''.join(JSON_ESCAPES.get(char, char) for char in text)


def tokens(theme: wambatic.reports.figures.Theme) -> str:
    """A theme's colours as the CSS custom properties the stylesheet reads."""
    declarations = {
        'page': theme.page,
        'surface': theme.surface,
        'ink': theme.ink,
        'ink-secondary': theme.ink_secondary,
        'grid': theme.grid,
        **{f'series-{n}': colour for n, colour in enumerate(theme.categorical, 1)},
        **{f'sequential-{n}': colour for n, colour in enumerate(theme.sequential, 1)},
    }
    return '\n  '.join(f'--{name}: {colour};' for name, colour in declarations.items())


def stylesheet() -> str:
    palette = wambatic.reports.figures.PALETTE
    return string.Template(read_template('report.css')).substitute(
        light=tokens(palette['light']), dark=tokens(palette['dark'])
    )


def cell(text: str, numeric: bool, tag: str = 'td') -> str:
    return f'<{tag}{" class=num" if numeric else ""}>{escape(text)}</{tag}>'


def table_html(
    title: str,
    headers: typing.Sequence[str],
    rows: typing.Sequence[typing.Sequence[str]],
    *,
    footer: typing.Sequence[str] | None = None,
    note: str = '',
    attributes: str = '',
) -> str:
    """A data table whose first column is text and the others numbers."""
    head = ''.join(cell(h, i > 0, 'th') for i, h in enumerate(headers))
    body = ''.join(
        '<tr>' + ''.join(cell(text, i > 0) for i, text in enumerate(row)) + '</tr>' for row in rows
    )
    foot = ''
    if footer is not None:
        foot = (
            '<tfoot><tr>' + ''.join(cell(t, i > 0) for i, t in enumerate(footer)) + '</tr></tfoot>'
        )
    caption = escape(title) + (f'<span class="note">{escape(note)}</span>' if note else '')
    return (
        f'<div class="table-scroll"><table{attributes}><caption>{caption}</caption>'
        f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody>{foot}</table></div>'
    )


def period_table_html(
    table: wambatic.reports.rows.PeriodTable, granularity: Granularity, hidden: bool, note: str
) -> str:
    rows = [
        [
            row.label + (wambatic.reports.rows.PARTIAL_MARK if row.partial else ''),
            *(
                wambatic.reports.terminal.format_cell(metric, value)
                for metric, value in zip(table.metrics, row.values, strict=True)
            ),
        ]
        for row in table.rows
    ]
    footer = None
    if table.total is not None:
        footer = [
            'Total',
            *(
                wambatic.reports.terminal.format_cell(metric, value)
                for metric, value in zip(table.metrics, table.total, strict=True)
            ),
        ]
    attributes = f' class="period" data-granularity="{granularity}"' + (' hidden' if hidden else '')
    return table_html(
        table.title,
        ['Period', *table.headers],
        rows,
        footer=footer,
        note=note,
        attributes=attributes,
    )


def period_tables_html(
    report: HtmlReport,
    build: typing.Callable[
        [wambatic.stats.base.StatsResult], wambatic.reports.rows.PeriodTable | None
    ],
    note: typing.Callable[[wambatic.reports.rows.PeriodTable], str],
) -> str:
    """One table for each granularity, all but the initial one hidden."""
    pieces = []
    for granularity in PERIODS:
        table = build(report.periods[granularity])
        if table is not None:
            pieces.append(
                period_table_html(table, granularity, granularity != report.initial, note(table))
            )
    return ''.join(pieces)


def partial_note(table: wambatic.reports.rows.PeriodTable) -> str:
    return '* partial period' if table.has_partial else ''


def breakdown_html(result: wambatic.stats.base.StatsResult) -> str:
    pieces = []
    for kind, title in wambatic.reports.rows.BREAKDOWN_TITLES:
        rows = wambatic.reports.rows.breakdown_rows(result, kind)
        if rows is not None:
            pieces.append(
                table_html(
                    title,
                    wambatic.reports.rows.BREAKDOWN_HEADERS,
                    [
                        [
                            row.name,
                            wambatic.reports.terminal.format_number(row.commits),
                            wambatic.reports.terminal.format_number(row.lines_added),
                            wambatic.reports.terminal.format_number(row.lines_deleted),
                            wambatic.reports.terminal.format_number(row.lines_net, signed=True),
                        ]
                        for row in rows
                    ],
                )
            )
    return ''.join(pieces)


def contributors_html(result: wambatic.stats.base.StatsResult) -> str:
    rows = wambatic.reports.rows.top_contributors(result)
    if not rows:
        return ''
    format_number = wambatic.reports.terminal.format_number
    return table_html(
        'Top contributors',
        wambatic.reports.rows.CONTRIBUTOR_HEADERS,
        [
            [
                row.login,
                format_number(row.commits),
                format_number(row.lines_added),
                format_number(row.lines_deleted),
                format_number(row.lines_net, signed=True),
                format_number(row.active_days),
            ]
            for row in rows
        ],
    )


def unavailable_html(result: wambatic.stats.base.StatsResult) -> str:
    rows = wambatic.reports.rows.unavailable_rows(result)
    if not rows:
        return ''
    return (
        '<section id="unavailable"><h2>Unavailable</h2>'
        + table_html('Unavailable', wambatic.reports.rows.UNAVAILABLE_HEADERS, rows)
        + '</section>'
    )


def figure_html(figure: wambatic.reports.figures.Figure, wide: bool = False) -> str:
    """A chart's element: plotly.js draws into the `div`, which names the chart for assistive
    technology; the caption stays outside it so drawing does not remove it."""
    return (
        f'<figure class="chart{" wide" if wide else ""}" data-group="{figure.group}">'
        f'<div id="{escape(figure.key)}" class="plot" role="img" '
        f'aria-label="{escape(figure.description)}"></div>'
        f'<figcaption>{escape(figure.title)}</figcaption></figure>'
    )


def period_figures(report: HtmlReport) -> list[wambatic.reports.figures.Figure]:
    """One figure for each chart any granularity has, in page order, as the elements the page
    script draws into."""
    seen: dict[str, wambatic.reports.figures.Figure] = {}
    for granularity in (report.initial, *PERIODS):
        for figure in wambatic.reports.figures.build_figures(report.periods[granularity]):
            seen.setdefault(figure.key, figure)
    order = {chart.key: index for index, chart in enumerate(wambatic.reports.figures.CHARTS)}
    return sorted(seen.values(), key=lambda figure: order[figure.key])


def tile(label: str, value: str) -> str:
    return f'<div class="tile"><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>'


def tiles_html(total: wambatic.stats.base.StatsResult) -> str:
    series = wambatic.reports.rows.total_series(total)
    format_number = wambatic.reports.terminal.format_number

    def value(metric: str) -> float | None:
        points = series.get(metric)
        return points[0][1] if points else None

    pieces = []
    if wambatic.reports.rows.has_activity(total):
        pieces += [
            tile('Commits', format_number(value('commits') or 0)),
            tile('Contributors', format_number(wambatic.reports.rows.contributor_count(total))),
            tile('Lines added', format_number(value('lines_added') or 0)),
            tile('Lines deleted', format_number(value('lines_deleted') or 0)),
            tile('Net lines', format_number(value('lines_net') or 0, signed=True)),
        ]
    if wambatic.reports.rows.has_flow(total):
        pieces += [
            tile('PRs opened', format_number(value('prs_opened') or 0)),
            tile('PRs merged', format_number(value('prs_merged') or 0)),
            tile('Issues opened', format_number(value('issues_opened') or 0)),
            tile('Issues closed', format_number(value('issues_closed') or 0)),
            tile(
                'Median time to merge (hours)',
                wambatic.reports.terminal.format_cell(
                    'time_to_merge_p50', value('time_to_merge_p50')
                ),
            ),
        ]
    return f'<dl class="tiles">{"".join(pieces)}</dl>' if pieces else ''


def header_html(report: HtmlReport) -> str:
    total = report.total
    subject = wambatic.reports.rows.subject_text(total)
    switch = ''.join(
        f'<label><input type="radio" name="granularity" value="{granularity}"'
        f'{" checked" if granularity == report.initial else ""}> {granularity.title()}</label>'
        for granularity in PERIODS
    )
    return (
        '<header>'
        f'<h1>wambatic <span class="subject">{escape(subject)}</span></h1>'
        f'<p class="range">{escape(total.since)} to {escape(total.until)}, '
        f'{escape(total.request.tz)}</p>'
        f'<fieldset class="switch"><legend>Period</legend>{switch}</fieldset>'
        '</header>'
    )


def footer_html(total: wambatic.stats.base.StatsResult) -> str:
    lines = [
        *wambatic.reports.rows.provenance_lines(total),
        f'plotly.js: {plotly.offline.get_plotlyjs_version()}',
    ]
    return (
        '<footer>'
        + ''.join(
            f'<p{" class=warning" if line.startswith("Warning:") else ""}>{escape(line)}</p>'
            for line in lines
        )
        + '</footer>'
    )


def sections_html(report: HtmlReport) -> str:
    total = report.total
    figures = period_figures(report)
    range_figures = wambatic.reports.figures.build_range_figures(total)
    calendar = wambatic.reports.figures.build_calendar(report.periods[Granularity.DAY])
    sections = []
    if wambatic.reports.rows.activity_table(total) is not None:
        charts = [f for f in figures if f.group == 'activity']
        wide = [calendar] if calendar is not None else []
        pieces = [
            '<section id="activity"><h2>Activity</h2>',
            '<div class="charts">',
            *(figure_html(f) for f in charts),
            *(figure_html(f, True) for f in wide),
            *(figure_html(f) for f in range_figures),
            '</div>',
            period_tables_html(report, wambatic.reports.rows.activity_table, partial_note),
            breakdown_html(total),
            contributors_html(total),
            '</section>',
        ]
        sections.append(''.join(pieces))
    if wambatic.reports.rows.flow_table(total) is not None:
        pieces = [
            '<section id="flow"><h2>Flow</h2>',
            '<div class="charts">',
            *(figure_html(f) for f in figures if f.group == 'flow'),
            '</div>',
            period_tables_html(report, wambatic.reports.rows.flow_table, partial_note),
            period_tables_html(
                report,
                wambatic.reports.rows.flow_times_table,
                wambatic.reports.terminal.flow_times_caption,
            ),
            '</section>',
        ]
        sections.append(''.join(pieces))
    sections.append(unavailable_html(total))
    return ''.join(sections)


def page_data(report: HtmlReport, theme: Theme) -> dict[str, object]:
    calendar = wambatic.reports.figures.build_calendar(report.periods[Granularity.DAY])
    return {
        'initial': str(report.initial),
        'theme': theme,
        'palette': {
            name: dataclasses.asdict(colours)
            for name, colours in wambatic.reports.figures.PALETTE.items()
        },
        'periods': {
            str(granularity): [
                dataclasses.asdict(f) for f in wambatic.reports.figures.build_figures(result)
            ]
            for granularity, result in report.periods.items()
        },
        'range': [
            dataclasses.asdict(f)
            for f in wambatic.reports.figures.build_range_figures(report.total)
        ],
        'calendar': None if calendar is None else dataclasses.asdict(calendar),
    }


def html_document(report: HtmlReport, theme: Theme) -> str:
    """The whole self-contained page. Pure: the only reads are of this package's templates.
    Raises ValueError when the five results differ in anything but granularity."""
    check_report(report)
    title = f'wambatic: {wambatic.reports.rows.subject_text(report.total)}'
    return string.Template(read_template('report.html')).substitute(
        theme_attribute='' if theme == 'auto' else f' data-theme="{theme}"',
        title=escape(title),
        style=stylesheet(),
        header=header_html(report),
        tiles=tiles_html(report.total),
        sections=sections_html(report),
        footer=footer_html(report.total),
        data=json_for_script(page_data(report, theme)),
        plotlyjs=str(plotly.offline.get_plotlyjs()),
        script=read_template('report.js'),
    )


def render_html(report: HtmlReport, out: pathlib.Path, theme: Theme) -> pathlib.Path:
    """Write `html_document(report, theme)` to `out` and return it. The file is written to a
    temporary file beside `out` and moved into place, so a failed write leaves `out` as it was
    and no temporary file behind. Missing parent directories are created."""
    document = html_document(report, theme)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        'w', encoding='utf-8', dir=out.parent, suffix='.tmp', delete=False
    ) as handle:
        temporary = pathlib.Path(handle.name)
        try:
            handle.write(document)
            handle.flush()
            temporary.chmod(FILE_MODE)
            os.replace(temporary, out)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    return out
