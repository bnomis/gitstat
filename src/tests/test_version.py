import importlib.metadata
import pathlib
import tomllib

import pytest

import wambatic.version


def test_version_matches_pyproject() -> None:
    pyproject = pathlib.Path(__file__).parents[2] / 'pyproject.toml'
    expected = tomllib.loads(pyproject.read_text())['project']['version']
    assert wambatic.version.VERSION == expected


def test_version_is_non_empty_string() -> None:
    assert isinstance(wambatic.version.VERSION, str)
    assert wambatic.version.VERSION


def test_version_without_package_metadata_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, 'version', missing)
    assert wambatic.version.package_version() == wambatic.version.UNKNOWN_VERSION == '0+unknown'
