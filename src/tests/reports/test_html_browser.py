import collections.abc
import dataclasses
import pathlib
import typing

import playwright.sync_api
import pytest

import wambatic.reports.figures
import wambatic.reports.html
import wambatic.stats.base

pytestmark = pytest.mark.browser

Granularity = wambatic.stats.base.Granularity
# The Chromium that Claude Code's cloud environment preinstalls; Playwright's own is tried first.
PREINSTALLED_CHROMIUM = pathlib.Path('/opt/pw-browsers/chromium')
FIRST_CHART = 'activity-commits'
DARK_SURFACE = wambatic.reports.figures.PALETTE['dark'].surface
LIGHT_SURFACE = wambatic.reports.figures.PALETTE['light'].surface


@dataclasses.dataclass
class Opened:
    page: playwright.sync_api.Page
    requests: list[str]
    problems: list[str]


@pytest.fixture
def chromium() -> collections.abc.Iterator[playwright.sync_api.Browser]:
    """A launched Chromium. It is per test, not per session: Playwright's sync API runs an event
    loop while it is open, and computing the report (`asyncio.run`) cannot happen then, so tests
    ask for their report fixtures before this one."""
    with playwright.sync_api.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch()
        except playwright.sync_api.Error as first:
            if not PREINSTALLED_CHROMIUM.exists():
                pytest.skip(f'no Chromium can be launched: {str(first).splitlines()[0]}')
            try:
                browser = driver.chromium.launch(executable_path=str(PREINSTALLED_CHROMIUM))
            except playwright.sync_api.Error as second:
                pytest.skip(f'no Chromium can be launched: {str(second).splitlines()[0]}')
        yield browser
        browser.close()


@pytest.fixture
def open_report(
    org_report: wambatic.reports.html.HtmlReport,
    tmp_path: pathlib.Path,
    chromium: playwright.sync_api.Browser,
) -> collections.abc.Iterator[typing.Callable[..., Opened]]:
    contexts: list[playwright.sync_api.BrowserContext] = []

    def open_page(
        theme: typing.Literal['auto', 'dark', 'light'] = 'auto',
        scheme: typing.Literal['dark', 'light'] = 'light',
    ) -> Opened:
        out = wambatic.reports.html.render_html(org_report, tmp_path / 'out' / 'report.html', theme)
        context = chromium.new_context(color_scheme=scheme)
        contexts.append(context)
        page = context.new_page()
        requests: list[str] = []
        problems: list[str] = []

        def route(route: playwright.sync_api.Route) -> None:
            if route.request.url == out.as_uri():
                route.continue_()
            else:
                requests.append(route.request.url)
                route.abort()

        page.route('**/*', route)
        page.on('console', lambda m: problems.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: problems.append(str(e)))
        page.goto(out.as_uri())
        page.wait_for_selector(f'#{FIRST_CHART} .main-svg')
        return Opened(page, requests, problems)

    yield open_page
    for context in contexts:
        context.close()


def keys(report: wambatic.reports.html.HtmlReport) -> list[str]:
    figures = [
        figure
        for result in report.periods.values()
        for figure in wambatic.reports.figures.build_figures(result)
    ]
    calendar = wambatic.reports.figures.build_calendar(report.periods[Granularity.DAY])
    assert calendar is not None
    figures += wambatic.reports.figures.build_range_figures(report.total) + [calendar]
    return sorted({figure.key for figure in figures})


def test_the_file_opens_offline_without_errors_and_every_chart_is_drawn(
    open_report: typing.Callable[..., Opened], org_report: wambatic.reports.html.HtmlReport
) -> None:
    opened = open_report()
    expected = keys(org_report)
    assert 'activity-calendar' in expected
    for key in expected:
        opened.page.wait_for_selector(f'#{key} .main-svg')
    assert opened.requests == []
    assert opened.problems == []


def visible_tables(page: playwright.sync_api.Page) -> set[str]:
    found = page.eval_on_selector_all(
        'table.period',
        'tables => tables.filter(t => !t.hidden).map(t => t.dataset.granularity)',
    )
    return set(found)


def test_each_granularity_shows_its_own_buckets_and_tables(
    open_report: typing.Callable[..., Opened], org_report: wambatic.reports.html.HtmlReport
) -> None:
    opened = open_report()
    page = opened.page
    assert visible_tables(page) == {'month'}
    for granularity in wambatic.reports.html.PERIODS:
        figures = wambatic.reports.figures.build_figures(org_report.periods[granularity])
        expected = len(figures[0].data[0]['x'])  # type: ignore[arg-type]
        page.check(f'input[name=granularity][value={granularity}]')
        page.wait_for_function(
            f'document.getElementById("{FIRST_CHART}").data[0].x.length === {expected}'
        )
        assert visible_tables(page) == {str(granularity)}
    assert opened.requests == []
    assert opened.problems == []


def surface(page: playwright.sync_api.Page) -> str:
    colour: str = page.evaluate(
        f'document.getElementById("{FIRST_CHART}")._fullLayout.paper_bgcolor'
    )
    return colour


def test_auto_follows_the_system_scheme_and_a_change_of_it(
    open_report: typing.Callable[..., Opened],
) -> None:
    dark = open_report('auto', 'dark')
    assert surface(dark.page) == DARK_SURFACE
    dark.page.emulate_media(color_scheme='light')
    dark.page.wait_for_function(
        f'document.getElementById("{FIRST_CHART}")._fullLayout.paper_bgcolor === "{LIGHT_SURFACE}"'
    )
    light = open_report('auto', 'light')
    assert surface(light.page) == LIGHT_SURFACE
    assert dark.problems == [] and light.problems == []


def test_a_fixed_theme_ignores_the_system_scheme(
    open_report: typing.Callable[..., Opened],
) -> None:
    opened = open_report('light', 'dark')
    assert surface(opened.page) == LIGHT_SURFACE
    opened.page.emulate_media(color_scheme='dark')
    opened.page.wait_for_timeout(300)
    assert surface(opened.page) == LIGHT_SURFACE
    fixed_dark = open_report('dark', 'light')
    assert surface(fixed_dark.page) == DARK_SURFACE


def test_the_series_take_the_themes_colours(
    open_report: typing.Callable[..., Opened],
) -> None:
    opened = open_report('auto', 'dark')
    colour: str = opened.page.evaluate(
        f'document.getElementById("{FIRST_CHART}").data[0].marker.color'
    )
    assert colour == wambatic.reports.figures.PALETTE['dark'].categorical[0]
