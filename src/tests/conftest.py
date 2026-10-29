import pathlib

import pytest

import gitstat.settings
import tests.fixtures.settings


@pytest.fixture
def config_file(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / 'config.json'
    path.write_text(tests.fixtures.settings.CONFIG_JSON)
    return path


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setattr(
        gitstat.settings, 'DEFAULT_CONFIG_PATH', tmp_path / 'default' / 'config.json'
    )
    monkeypatch.delenv('GITSTAT_CONFIG', raising=False)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
