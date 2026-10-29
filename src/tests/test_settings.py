import dataclasses
import datetime
import json
import pathlib
import tempfile

import hypothesis
import hypothesis.strategies
import pytest

import gitstat.settings
import tests.fixtures.settings


def test_fetch_defaults() -> None:
    fetch = gitstat.settings.Settings().fetch
    assert fetch == gitstat.settings.FetchSettings(
        cache_path=pathlib.Path.home() / '.cache/gitstat/cache.sqlite3',
        full_refresh_after=datetime.timedelta(days=30),
        include_archived=False,
        include_forks=False,
        max_age=datetime.timedelta(0),
        max_retries=5,
        on_rate_limit='wait',
        overlap=datetime.timedelta(hours=1),
        stats_retries=6,
        workers=4,
    )


def test_stats_defaults() -> None:
    stats = gitstat.settings.Settings().stats
    assert stats.bot_logins == ('dependabot[bot]', 'renovate[bot]')
    assert stats.deploy_workflow is None
    assert stats.exclude_merge_commits is True
    assert stats.failure_window == datetime.timedelta(days=7)
    assert stats.hotfix_labels == ('hotfix',)
    assert stats.timezone == 'UTC'


def test_report_defaults() -> None:
    report = gitstat.settings.Settings().report
    assert report.allow_remote is False
    assert report.format == 'terminal'
    assert report.html_theme == 'auto'
    assert report.out_dir == pathlib.Path('./gitstat-reports')
    assert report.web_host == '127.0.0.1'
    assert report.web_port == 8000


def test_settings_are_frozen() -> None:
    settings = gitstat.settings.Settings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.fetch = gitstat.settings.FetchSettings()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.fetch.workers = 9  # type: ignore[misc]


def test_settings_hashable() -> None:
    assert hash(gitstat.settings.Settings()) == hash(gitstat.settings.Settings())


def test_load_known_good_file(config_file: pathlib.Path) -> None:
    loaded = gitstat.settings.load_settings(config_file, {})
    assert loaded == tests.fixtures.settings.CONFIG_SETTINGS


def test_missing_default_file_gives_defaults() -> None:
    assert gitstat.settings.load_settings(None, {}) == gitstat.settings.Settings()


def test_missing_named_file_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises(gitstat.settings.SettingsError):
        gitstat.settings.load_settings(tmp_path / 'absent.json', {})


def test_missing_env_named_file_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setenv('GITSTAT_CONFIG', str(tmp_path / 'absent.json'))
    with pytest.raises(gitstat.settings.SettingsError):
        gitstat.settings.load_settings(None, {})


def test_env_selects_file(monkeypatch: pytest.MonkeyPatch, config_file: pathlib.Path) -> None:
    monkeypatch.setenv('GITSTAT_CONFIG', str(config_file))
    loaded = gitstat.settings.load_settings(None, {})
    assert loaded == tests.fixtures.settings.CONFIG_SETTINGS


def test_config_path_beats_env(
    monkeypatch: pytest.MonkeyPatch, config_file: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setenv('GITSTAT_CONFIG', str(tmp_path / 'absent.json'))
    loaded = gitstat.settings.load_settings(config_file, {})
    assert loaded == tests.fixtures.settings.CONFIG_SETTINGS


def test_overrides_beat_file(config_file: pathlib.Path) -> None:
    loaded = gitstat.settings.load_settings(
        config_file, {'fetch': {'workers': 2}, 'report': {'format': 'html'}}
    )
    assert loaded.fetch.workers == 2
    assert loaded.fetch.include_forks is True
    assert loaded.report.format == 'html'
    assert loaded.report.web_port == 9000


def test_malformed_json_raises(tmp_path: pathlib.Path) -> None:
    path = tmp_path / 'bad.json'
    path.write_text('{')
    with pytest.raises(gitstat.settings.SettingsError, match='not valid JSON'):
        gitstat.settings.load_settings(path, {})


@pytest.mark.parametrize('text', ['[]', '{"fetch": []}'])
def test_wrong_shape_raises(tmp_path: pathlib.Path, text: str) -> None:
    path = tmp_path / 'bad.json'
    path.write_text(text)
    with pytest.raises(gitstat.settings.SettingsError):
        gitstat.settings.load_settings(path, {})


def test_invalid_literal_names_key_and_allowed_values() -> None:
    with pytest.raises(gitstat.settings.SettingsError) as raised:
        gitstat.settings.load_settings(None, {'report': {'format': 'pdf'}})
    message = str(raised.value)
    assert 'report.format' in message
    assert 'html, json, terminal' in message
    assert 'pdf' not in message


@pytest.mark.parametrize(
    ('section', 'key', 'value'),
    [
        ('fetch', 'workers', 'four'),
        ('fetch', 'workers', True),
        ('fetch', 'include_forks', 1),
        ('fetch', 'cache_path', 3),
        ('stats', 'bot_logins', 'ci[bot]'),
        ('stats', 'bot_logins', [1]),
        ('stats', 'deploy_workflow', 3),
        ('report', 'web_host', None),
    ],
)
def test_wrong_type_raises_naming_key(section: str, key: str, value: object) -> None:
    with pytest.raises(gitstat.settings.SettingsError, match=f'{section}.{key}'):
        gitstat.settings.load_settings(None, {section: {key: value}})


@pytest.mark.parametrize('text', ['30', '1.5h', '-1d', '3y', '', 'd', '１d', ' 1d'])
def test_malformed_duration_raises(text: str) -> None:
    with pytest.raises(gitstat.settings.SettingsError, match='fetch.max_age'):
        gitstat.settings.load_settings(None, {'fetch': {'max_age': text}})


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('0s', datetime.timedelta(0)),
        ('90s', datetime.timedelta(seconds=90)),
        ('5m', datetime.timedelta(minutes=5)),
        ('1h', datetime.timedelta(hours=1)),
        ('30d', datetime.timedelta(days=30)),
        ('2w', datetime.timedelta(weeks=2)),
    ],
)
def test_parse_duration_known_good(text: str, expected: datetime.timedelta) -> None:
    assert gitstat.settings.parse_duration(text) == expected


def test_path_expands_tilde_only() -> None:
    loaded = gitstat.settings.load_settings(
        None, {'report': {'out_dir': '~/x'}, 'fetch': {'cache_path': '$HOME/x'}}
    )
    assert loaded.report.out_dir == pathlib.Path.home() / 'x'
    assert loaded.fetch.cache_path == pathlib.Path('$HOME/x')


def test_relative_path_stays_relative() -> None:
    loaded = gitstat.settings.load_settings(None, {'report': {'out_dir': 'out'}})
    assert loaded.report.out_dir == pathlib.Path('out')


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(
    file_workers=hypothesis.strategies.integers(),
    override_workers=hypothesis.strategies.one_of(
        hypothesis.strategies.none(), hypothesis.strategies.integers()
    ),
)
def test_override_wins_over_file(file_workers: int, override_workers: int | None) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / 'config.json'
        path.write_text(json.dumps({'fetch': {'workers': file_workers}}))
        overrides: dict[str, object] = (
            {} if override_workers is None else {'fetch': {'workers': override_workers}}
        )
        loaded = gitstat.settings.load_settings(path, overrides)
    expected = file_workers if override_workers is None else override_workers
    assert loaded.fetch.workers == expected


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(
    n=hypothesis.strategies.integers(min_value=0, max_value=10**6),
    unit=hypothesis.strategies.sampled_from('smhdw'),
)
def test_parse_duration_any_integer_and_unit(n: int, unit: str) -> None:
    expected = {
        's': datetime.timedelta(seconds=n),
        'm': datetime.timedelta(minutes=n),
        'h': datetime.timedelta(hours=n),
        'd': datetime.timedelta(days=n),
        'w': datetime.timedelta(weeks=n),
    }[unit]
    assert gitstat.settings.parse_duration(f'{n}{unit}') == expected


SECRET = 'ghp_supersecretvalue'


@pytest.mark.parametrize('key', ['token', 'github_token'])
def test_token_in_file_is_refused(tmp_path: pathlib.Path, key: str) -> None:
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'fetch': {key: SECRET}}))
    with pytest.raises(gitstat.settings.SettingsError) as raised:
        gitstat.settings.load_settings(path, {})
    assert key in str(raised.value)
    assert SECRET not in str(raised.value)


@pytest.mark.parametrize('section', ['fetch', 'report', 'stats'])
def test_token_in_overrides_is_refused(section: str) -> None:
    with pytest.raises(gitstat.settings.SettingsError) as raised:
        gitstat.settings.load_settings(None, {section: {'token': SECRET}})
    assert SECRET not in str(raised.value)


def test_token_section_is_refused() -> None:
    with pytest.raises(gitstat.settings.SettingsError) as raised:
        gitstat.settings.load_settings(None, {'token': SECRET})
    assert SECRET not in str(raised.value)


def test_wrong_type_error_does_not_echo_value() -> None:
    with pytest.raises(gitstat.settings.SettingsError) as raised:
        gitstat.settings.load_settings(None, {'fetch': {'workers': SECRET}})
    assert SECRET not in str(raised.value)


def test_github_token_env_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', SECRET)
    assert gitstat.settings.load_settings(None, {}) == gitstat.settings.Settings()


def test_no_field_names_a_token() -> None:
    def names(cls: type) -> list[str]:
        out: list[str] = []
        for field in dataclasses.fields(cls):
            out.append(field.name)
            if dataclasses.is_dataclass(field.type):
                out.extend(names(field.type))  # type: ignore[arg-type]
        return out

    assert not [name for name in names(gitstat.settings.Settings) if 'token' in name]
