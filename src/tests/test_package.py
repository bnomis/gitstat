import importlib

import pytest

import gitstat
import gitstat.fetch


@pytest.mark.parametrize('name', ['gitstat', 'gitstat.fetch', 'gitstat.reports', 'gitstat.stats'])
def test_package_imports(name: str) -> None:
    assert importlib.import_module(name).__name__ == name


@pytest.mark.parametrize('name', ['Fetcher', 'Settings', 'Subject', 'load_settings'])
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
