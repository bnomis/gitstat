import pathlib
import tomllib

import wambatic.version


def test_version_matches_pyproject() -> None:
    pyproject = pathlib.Path(__file__).parents[2] / 'pyproject.toml'
    expected = tomllib.loads(pyproject.read_text())['project']['version']
    assert wambatic.version.VERSION == expected


def test_version_is_non_empty_string() -> None:
    assert isinstance(wambatic.version.VERSION, str)
    assert wambatic.version.VERSION
