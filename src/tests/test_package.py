import importlib

import pytest


@pytest.mark.parametrize('name', ['gitstat', 'gitstat.fetch', 'gitstat.reports', 'gitstat.stats'])
def test_package_imports(name: str) -> None:
    assert importlib.import_module(name).__name__ == name
