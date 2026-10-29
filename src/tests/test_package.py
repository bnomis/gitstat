import importlib

import pytest

import gitstat
import gitstat.fetch


@pytest.mark.parametrize('name', ['gitstat', 'gitstat.fetch', 'gitstat.reports', 'gitstat.stats'])
def test_package_imports(name: str) -> None:
    assert importlib.import_module(name).__name__ == name


@pytest.mark.parametrize('name', ['Settings', 'load_settings'])
def test_public_names_resolve(name: str) -> None:
    assert name in gitstat.__all__
    assert getattr(gitstat, name)


@pytest.mark.parametrize('name', gitstat.fetch.__all__)
def test_fetch_names_resolve(name: str) -> None:
    assert getattr(gitstat.fetch, name)
