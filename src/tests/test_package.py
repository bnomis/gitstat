import importlib

import pytest

import wambatic
import wambatic.cli
import wambatic.fetch
import wambatic.reports
import wambatic.stats


@pytest.mark.parametrize(
    'name', ['wambatic', 'wambatic.cli', 'wambatic.fetch', 'wambatic.reports', 'wambatic.stats']
)
def test_package_imports(name: str) -> None:
    assert importlib.import_module(name).__name__ == name


@pytest.mark.parametrize(
    'name',
    ['Fetcher', 'Settings', 'StatsRequest', 'StatsResult', 'Subject', 'compute', 'load_settings'],
)
def test_public_names_are_exported(name: str) -> None:
    assert name in wambatic.__all__


@pytest.mark.parametrize('name', wambatic.__all__)
def test_public_names_resolve(name: str) -> None:
    assert getattr(wambatic, name)


def test_fetcher_and_subject_are_the_fetch_layers() -> None:
    assert wambatic.Fetcher is wambatic.fetch.Fetcher
    assert wambatic.Subject is wambatic.fetch.Subject


@pytest.mark.parametrize('name', wambatic.fetch.__all__)
def test_fetch_names_resolve(name: str) -> None:
    assert getattr(wambatic.fetch, name)


@pytest.mark.parametrize('name', wambatic.stats.__all__)
def test_stats_names_resolve(name: str) -> None:
    assert getattr(wambatic.stats, name)


def test_the_stats_names_are_the_stats_layers() -> None:
    assert wambatic.compute is wambatic.stats.compute
    assert wambatic.StatsRequest is wambatic.stats.StatsRequest
    assert wambatic.StatsResult is wambatic.stats.StatsResult


@pytest.mark.parametrize('name', ['BUILT_RESOURCES', 'CacheInfo', 'clear_cache', 'inspect_cache'])
def test_the_step_5_fetch_names_are_exported(name: str) -> None:
    assert name in wambatic.fetch.__all__
    assert getattr(wambatic.fetch, name)


@pytest.mark.parametrize('name', wambatic.reports.__all__)
def test_reports_names_resolve(name: str) -> None:
    assert getattr(wambatic.reports, name)


@pytest.mark.parametrize(
    'name',
    [
        'Figure',
        'HtmlReport',
        'OutputError',
        'UsageError',
        'build_calendar',
        'build_figures',
        'build_range_figures',
        'html_document',
        'render_html',
        'render_json',
        'render_terminal',
        'report_filename',
        'result_to_dict',
        'sparkline',
    ],
)
def test_reports_names_are_exported(name: str) -> None:
    assert name in wambatic.reports.__all__


def test_the_command_line_entry_points_are_callable() -> None:
    assert callable(wambatic.cli.main)
    assert callable(wambatic.cli.run)


@pytest.mark.parametrize('name', ['Issue', 'PullRequest'])
def test_the_step_6_fetch_records_are_exported(name: str) -> None:
    assert name in wambatic.fetch.__all__
    assert getattr(wambatic.fetch, name)


def test_the_built_resources_include_issues_and_pull_requests() -> None:
    assert {'issues', 'pull_requests'} <= wambatic.fetch.BUILT_RESOURCES


@pytest.mark.parametrize('name', ['Release', 'WorkflowRun'])
def test_the_step_8_fetch_records_are_exported(name: str) -> None:
    assert name in wambatic.fetch.__all__
    assert getattr(wambatic.fetch, name)


def test_the_built_resources_include_releases_and_workflow_runs() -> None:
    assert {'releases', 'workflow_runs'} <= wambatic.fetch.BUILT_RESOURCES
