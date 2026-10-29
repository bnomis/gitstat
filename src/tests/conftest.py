import dataclasses
import pathlib
import random
import typing

import pytest

import gitstat.fetch.client
import gitstat.settings
import tests.fixtures.fetch.responses
import tests.fixtures.fetch.server
import tests.fixtures.settings

MakeClient = typing.Callable[..., gitstat.fetch.client.GitHubClient]


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


class Sleeps(list[float]):
    async def __call__(self, seconds: float) -> None:
        self.append(seconds)


@pytest.fixture
def sleeps() -> Sleeps:
    return Sleeps()


@pytest.fixture
def fetch_settings() -> gitstat.settings.FetchSettings:
    return dataclasses.replace(gitstat.settings.FetchSettings(), max_retries=2, stats_retries=2)


@pytest.fixture
def make_client(sleeps: Sleeps, fetch_settings: gitstat.settings.FetchSettings) -> MakeClient:
    def make(
        server: tests.fixtures.fetch.server.ReplayServer,
        settings: gitstat.settings.FetchSettings = fetch_settings,
    ) -> gitstat.fetch.client.GitHubClient:
        return gitstat.fetch.client.GitHubClient(
            'test-token',
            settings,
            api_url=server.url,
            sleep=sleeps,
            clock=lambda: tests.fixtures.fetch.responses.NOW,
            rng=random.Random(0),
        )

    return make
