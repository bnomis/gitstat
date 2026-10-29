import pathlib
import tomllib

import gitstat.version


def test_version_matches_pyproject() -> None:
    pyproject = pathlib.Path(__file__).parents[2] / 'pyproject.toml'
    expected = tomllib.loads(pyproject.read_text())['project']['version']
    assert gitstat.version.VERSION == expected


def test_version_is_non_empty_string() -> None:
    assert isinstance(gitstat.version.VERSION, str)
    assert gitstat.version.VERSION
