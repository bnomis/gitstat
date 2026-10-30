import dataclasses
import html.parser
import importlib.resources
import json
import re
import typing

import pytest

import tests.fixtures.stats as fixture
import wambatic.fetch.base
import wambatic.reports.figures
import wambatic.reports.html
import wambatic.stats.base

Granularity = wambatic.stats.base.Granularity
HOSTILE = '<b>&"\'</script>'


class Page(html.parser.HTMLParser):
    """The parts of a report page the tests look at."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.tiles: dict[str, str] = {}
        self.data = ''
        self.style = ''
        self.text = ''
        self.open: list[tuple[str, dict[str, str | None]]] = []
        self.label = ''
        self.feed(text)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))
        if tag not in ('input', 'meta', 'br'):
            self.open.append((tag, dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        while self.open and self.open.pop()[0] != tag:
            pass

    def handle_data(self, data: str) -> None:
        if not self.open:
            return
        tag, attrs = self.open[-1]
        if tag == 'script':
            if attrs.get('id') == 'wambatic-data':
                self.data += data
        elif tag == 'style':
            self.style += data
        else:
            self.text += data
            if tag == 'dt':
                self.label = data
            elif tag == 'dd':
                self.tiles[self.label] = data

    def by_id(self, key: str) -> dict[str, str | None]:
        matches = [attrs for _, attrs in self.elements if attrs.get('id') == key]
        assert len(matches) == 1, key
        return matches[0]

    def tables(self) -> list[dict[str, str | None]]:
        return [attrs for tag, attrs in self.elements if tag == 'table']


def keys_of(report: wambatic.reports.html.HtmlReport) -> set[str]:
    keys: set[str] = set()
    for result in report.periods.values():
        keys |= {f.key for f in wambatic.reports.figures.build_figures(result)}
    keys |= {f.key for f in wambatic.reports.figures.build_range_figures(report.total)}
    calendar = wambatic.reports.figures.build_calendar(report.periods[Granularity.DAY])
    assert calendar is not None
    return keys | {calendar.key}


def test_every_figure_has_its_element_naming_the_chart(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    page = Page(wambatic.reports.html.html_document(org_report, 'auto'))
    keys = keys_of(org_report)
    assert 'activity-commits' in keys
    assert 'activity-calendar' in keys
    assert 'activity-by-author' in keys
    assert 'flow-merge-time' in keys
    for key in keys:
        element = page.by_id(key)
        assert element['role'] == 'img'
        assert element['aria-label']


def test_the_figures_of_every_granularity_are_in_the_embedded_data(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    page = Page(wambatic.reports.html.html_document(org_report, 'dark'))
    data = json.loads(page.data)
    assert data['initial'] == 'month'
    assert data['theme'] == 'dark'
    assert sorted(data['periods']) == ['day', 'month', 'week', 'year']
    months = data['periods']['month'][0]['data'][0]['x']
    assert months == list(fixture.LABELS)
    assert data['calendar']['key'] == 'activity-calendar'
    assert [f['key'] for f in data['range']] == [
        'activity-top-contributors',
        'activity-by-repository',
        'activity-by-author',
    ]
    assert data['palette']['light']['categorical'] == ['#2a78d6', '#eb6834', '#1baf7a']
    assert set(data['palette']) == {'light', 'dark'}


def test_period_tables_appear_once_per_granularity_with_only_the_initial_one_visible(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    page = Page(wambatic.reports.html.html_document(org_report, 'auto'))
    periods = [t for t in page.tables() if t.get('class') == 'period']
    seen: dict[str, list[str | None]] = {}
    for table in periods:
        granularity = table['data-granularity']
        assert granularity is not None
        seen.setdefault(granularity, []).append('hidden' if 'hidden' in table else None)
    assert sorted(seen) == ['day', 'month', 'week', 'year']
    assert all(len(hidden) == 3 for hidden in seen.values())  # activity, flow, flow times
    visible = {g for g, hidden in seen.items() if hidden[0] is None}
    assert visible == {'month'}
    assert all(h is None for h in seen['month'])
    assert all(h == 'hidden' for g, hidden in seen.items() if g != 'month' for h in hidden)
    other = Page(
        wambatic.reports.html.html_document(
            dataclasses.replace(org_report, initial=Granularity.DAY), 'auto'
        )
    )
    day_tables = [t for t in other.tables() if t.get('data-granularity') == 'day']
    assert all('hidden' not in t for t in day_tables)


def test_the_initial_granularitys_radio_is_checked(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    page = Page(wambatic.reports.html.html_document(org_report, 'auto'))
    radios = {
        attrs['value']: 'checked' in attrs
        for tag, attrs in page.elements
        if tag == 'input' and attrs.get('name') == 'granularity'
    }
    assert radios == {'year': False, 'month': True, 'week': False, 'day': False}


def test_the_tiles_show_the_totals(org_report: wambatic.reports.html.HtmlReport) -> None:
    page = Page(wambatic.reports.html.html_document(org_report, 'auto'))
    assert page.tiles['Commits'] == '10'
    assert page.tiles['Contributors'] == '3'
    assert page.tiles['Lines added'] == '90'
    assert page.tiles['Lines deleted'] == '48'
    assert page.tiles['Net lines'] == '+42'
    assert page.tiles['PRs opened'] == '10'
    assert page.tiles['PRs merged'] == '7'
    assert page.tiles['Issues opened'] == '5'
    assert page.tiles['Issues closed'] == '4'


def test_a_median_with_no_data_is_a_dash(org_report: wambatic.reports.html.HtmlReport) -> None:
    series = [
        dataclasses.replace(s, points={}) if s.metric == 'time_to_merge_p50' else s
        for s in org_report.total.series
    ]
    report = dataclasses.replace(
        org_report, total=dataclasses.replace(org_report.total, series=series)
    )
    page = Page(wambatic.reports.html.html_document(report, 'auto'))
    assert page.tiles['Median time to merge (hours)'] == '-'
    whole = Page(wambatic.reports.html.html_document(org_report, 'auto'))
    assert whole.tiles['Median time to merge (hours)'] != '-'


def test_the_period_tables_hold_the_terminals_rows(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    document = wambatic.reports.html.html_document(org_report, 'auto')
    assert '<td>2026-10</td><td class=num>7</td><td class=num>3</td>' in document
    assert '<td>Total</td><td class=num>10</td><td class=num>3</td>' in document
    assert '<td class=num>+34</td>' in document
    assert 'Flow times by period' in document
    assert '<td class=num>-</td>' in document


def test_the_document_holds_one_copy_of_plotly_js(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    import plotly.offline

    document = wambatic.reports.html.html_document(org_report, 'auto')
    marker = f'plotly.js v{plotly.offline.get_plotlyjs_version()}'
    assert document.count(marker) == 1
    assert document.count(str(plotly.offline.get_plotlyjs())) == 1
    assert f'plotly.js: {plotly.offline.get_plotlyjs_version()}' in document


def test_nothing_refers_outside_the_file(org_report: wambatic.reports.html.HtmlReport) -> None:
    page = Page(wambatic.reports.html.html_document(org_report, 'auto'))
    for _, attrs in page.elements:
        for name in ('src', 'href', 'action', 'data'):
            value = attrs.get(name)
            if value is not None and name != 'data':
                assert not value.startswith(('http:', 'https:', '//')), (name, value)
    assert all('src' not in attrs for tag, attrs in page.elements if tag == 'script')
    assert 'url(' not in page.style
    assert '@import' not in page.style


def test_a_hostile_login_is_escaped_in_the_html_and_round_trips_in_the_data(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    rows = [{**fixture.ORG_TOP_CONTRIBUTORS[0], 'login': HOSTILE}]
    total = dataclasses.replace(
        org_report.total, tables={**org_report.total.tables, 'top_contributors': rows}
    )
    document = wambatic.reports.html.html_document(
        dataclasses.replace(org_report, total=total), 'auto'
    )
    assert HOSTILE not in document
    assert '&lt;b&gt;&amp;&quot;&#x27;&lt;/script&gt;' in document
    page = Page(document)
    data = json.loads(page.data)
    assert data['range'][0]['data'][0]['y'] == [HOSTILE]
    assert '<' not in page.data
    assert '\\u003c/script\\u003e' in page.data


def test_hostile_labels_in_the_other_tables_are_escaped(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    unavailable = [{'metric': HOSTILE, 'reason': HOSTILE}]
    total = dataclasses.replace(
        org_report.total, tables={**org_report.total.tables, 'unavailable': unavailable}
    )
    document = wambatic.reports.html.html_document(
        dataclasses.replace(org_report, total=total), 'auto'
    )
    assert HOSTILE not in document
    assert document.count('&lt;b&gt;&amp;&quot;&#x27;&lt;/script&gt;') == 2


def test_the_embedded_data_is_valid_json_with_unicode_kept(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    rows = [{**fixture.ORG_TOP_CONTRIBUTORS[0], 'login': 'zoë'}]
    total = dataclasses.replace(
        org_report.total, tables={**org_report.total.tables, 'top_contributors': rows}
    )
    page = Page(
        wambatic.reports.html.html_document(dataclasses.replace(org_report, total=total), 'auto')
    )
    assert json.loads(page.data)['range'][0]['data'][0]['y'] == ['zoë']


@pytest.mark.parametrize(
    ('subject', 'name'),
    [
        (wambatic.fetch.base.Subject('repo', 'octo-org', 'alpha'), 'repo-octo-org-alpha.html'),
        (wambatic.fetch.base.Subject('user', 'octocat'), 'user-octocat.html'),
        (wambatic.fetch.base.Subject('org', 'octo-org'), 'org-octo-org.html'),
        (wambatic.fetch.base.Subject('repo', 'o', '.github'), 'repo-o-.github.html'),
        (wambatic.fetch.base.Subject('repo', 'o', 'a/../b'), 'repo-o-a-..-b.html'),
    ],
)
def test_report_filename_names_the_kind_and_the_subject(
    subject: wambatic.fetch.base.Subject, name: str
) -> None:
    assert wambatic.reports.html.report_filename(subject) == name


def test_a_total_that_is_not_total_is_refused(org_report: wambatic.reports.html.HtmlReport) -> None:
    month = org_report.periods[Granularity.MONTH]
    with pytest.raises(ValueError, match='total must be a TOTAL result'):
        wambatic.reports.html.html_document(dataclasses.replace(org_report, total=month), 'auto')


def test_a_missing_granularity_is_refused(org_report: wambatic.reports.html.HtmlReport) -> None:
    periods: dict[Granularity, wambatic.stats.base.StatsResult] = {
        g: r for g, r in org_report.periods.items() if g is not Granularity.WEEK
    }
    with pytest.raises(ValueError, match='periods must be exactly'):
        wambatic.reports.html.html_document(
            dataclasses.replace(org_report, periods=periods), 'auto'
        )


def test_an_initial_granularity_outside_the_periods_is_refused(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    with pytest.raises(ValueError, match='initial'):
        wambatic.reports.html.html_document(
            dataclasses.replace(org_report, initial=Granularity.TOTAL), 'auto'
        )


def test_a_result_made_for_another_range_is_refused_naming_the_difference(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    month = org_report.periods[Granularity.MONTH]
    other = dataclasses.replace(
        month, request=dataclasses.replace(month.request, since=fixture.SINCE.replace(day=2))
    )
    periods = {**org_report.periods, Granularity.MONTH: other}
    with pytest.raises(ValueError, match='month result differs from the total in request since'):
        wambatic.reports.html.html_document(
            dataclasses.replace(org_report, periods=periods), 'auto'
        )


def test_a_result_for_another_subject_or_groups_is_refused(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    day = org_report.periods[Granularity.DAY]
    user = dataclasses.replace(day, subject=wambatic.fetch.base.Subject('user', 'octocat'))
    with pytest.raises(ValueError, match='day result differs from the total in subject'):
        wambatic.reports.html.html_document(
            dataclasses.replace(org_report, periods={**org_report.periods, Granularity.DAY: user}),
            'auto',
        )
    groups = dataclasses.replace(
        day, request=dataclasses.replace(day.request, groups=frozenset({'activity'}))
    )
    with pytest.raises(ValueError, match='request groups'):
        wambatic.reports.html.html_document(
            dataclasses.replace(
                org_report, periods={**org_report.periods, Granularity.DAY: groups}
            ),
            'auto',
        )


def test_a_result_filed_under_the_wrong_granularity_is_refused(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    periods = {
        **org_report.periods,
        Granularity.WEEK: org_report.periods[Granularity.DAY],
    }
    with pytest.raises(ValueError, match='week result is by day'):
        wambatic.reports.html.html_document(
            dataclasses.replace(org_report, periods=periods), 'auto'
        )


@pytest.mark.parametrize(
    ('theme', 'attribute'), [('light', 'light'), ('dark', 'dark'), ('auto', None)]
)
def test_each_theme_sets_data_theme_on_the_html_element_as_it_should(
    org_report: wambatic.reports.html.HtmlReport,
    theme: typing.Literal['auto', 'dark', 'light'],
    attribute: str | None,
) -> None:
    page = Page(wambatic.reports.html.html_document(org_report, theme))
    html_attributes = next(attrs for tag, attrs in page.elements if tag == 'html')
    assert html_attributes.get('data-theme') == attribute


def test_the_stylesheet_defines_both_themes_as_custom_properties(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    page = Page(wambatic.reports.html.html_document(org_report, 'auto'))
    assert '--surface: #fcfcfb;' in page.style
    assert '--surface: #1a1a19;' in page.style
    assert ':root[data-theme="dark"]' in page.style
    assert 'prefers-color-scheme: dark' in page.style
    assert page.style.count('--series-1: #3987e5;') == 2
    assert re.search(r'--sequential-5: #b7d3f6;', page.style)


def test_a_repo_page_has_no_by_repository_table_and_the_sections_of_its_groups(
    repo_report: wambatic.reports.html.HtmlReport,
) -> None:
    document = wambatic.reports.html.html_document(repo_report, 'auto')
    assert 'By repository' not in document
    assert 'id="activity"' in document
    assert 'id="flow"' in document
    assert 'repo octo-org/alpha' in document


def test_a_group_the_result_lacks_has_no_section(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    def flow_free(result: wambatic.stats.base.StatsResult) -> wambatic.stats.base.StatsResult:
        return dataclasses.replace(
            result,
            series=[
                s
                for s in result.series
                if s.metric.startswith(('commits', 'contributors', 'active', 'lines'))
            ],
        )

    report = wambatic.reports.html.HtmlReport(
        total=flow_free(org_report.total),
        periods={g: flow_free(r) for g, r in org_report.periods.items()},
        initial=org_report.initial,
    )
    document = wambatic.reports.html.html_document(report, 'auto')
    assert 'id="activity"' in document
    assert 'id="flow"' not in document
    assert 'PRs opened' not in document


def test_the_templates_are_found_through_importlib_resources() -> None:
    templates = importlib.resources.files('wambatic.reports') / 'templates'
    for name in ('report.html', 'report.css', 'report.js'):
        assert (templates / name).is_file()


def test_the_report_names_the_range_the_timezone_and_the_provenance(
    org_report: wambatic.reports.html.HtmlReport,
) -> None:
    document = wambatic.reports.html.html_document(org_report, 'auto')
    assert '2026-10-01 to 2027-01-31, UTC' in document
    assert 'computed_at: 2027-01-20T12:00:00+00:00' in document
    assert 'schema_version: ' in document
    warned = dataclasses.replace(
        org_report.total,
        provenance={
            **org_report.total.provenance,
            'version_override_at': '2027-01-20T12:00:00+00:00',
        },
    )
    assert 'ignore-cache-version' in wambatic.reports.html.html_document(
        dataclasses.replace(org_report, total=warned), 'auto'
    )
