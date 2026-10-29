import importlib

import pytest

import gitstat
import gitstat.cli
import gitstat.fetch
import gitstat.reports
import gitstat.stats


@pytest.mark.parametrize(
    'name', ['gitstat', 'gitstat.cli', 'gitstat.fetch', 'gitstat.reports', 'gitstat.stats']
)
def test_package_imports(name: str) -> None:
    assert importlib.import_module(name).__name__ == name


@pytest.mark.parametrize(
    'name',
    ['Fetcher', 'Settings', 'StatsRequest', 'StatsResult', 'Subject', 'compute', 'load_settings'],
)
def test_public_names_are_exported(name: str) -> None:
    assert name in gitstat.__all__


@pytest.mark.parametrize('name', gitstat.__all__)
def test_public_names_resolve(name: str) -> None:
    assert getattr(gitstat, name)


def test_fetcher_and_subject_are_the_fetch_layers() -> None:
    assert gitstat.Fetcher is gitstat.fetch.Fetcher
    assert gitstat.Subject is gitstat.fetch.Subject


@pytest.mark.parametrize('name', gitstat.fetch.__all__)
def test_fetch_names_resolve(name: str) -> None:
    assert getattr(gitstat.fetch, name)


@pytest.mark.parametrize('name', gitstat.stats.__all__)
def test_stats_names_resolve(name: str) -> None:
    assert getattr(gitstat.stats, name)


def test_the_stats_names_are_the_stats_layers() -> None:
    assert gitstat.compute is gitstat.stats.compute
    assert gitstat.StatsRequest is gitstat.stats.StatsRequest
    assert gitstat.StatsResult is gitstat.stats.StatsResult


@pytest.mark.parametrize('name', ['BUILT_RESOURCES', 'CacheInfo', 'clear_cache', 'inspect_cache'])
def test_the_step_5_fetch_names_are_exported(name: str) -> None:
    assert name in gitstat.fetch.__all__
    assert getattr(gitstat.fetch, name)


@pytest.mark.parametrize('name', gitstat.reports.__all__)
def test_reports_names_resolve(name: str) -> None:
    assert getattr(gitstat.reports, name)


@pytest.mark.parametrize(
    'name', ['UsageError', 'render_json', 'render_terminal', 'result_to_dict', 'sparkline']
)
def test_reports_names_are_exported(name: str) -> None:
    assert name in gitstat.reports.__all__


def test_the_command_line_entry_points_are_callable() -> None:
    assert callable(gitstat.cli.main)
    assert callable(gitstat.cli.run)
