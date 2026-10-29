import dataclasses
import datetime
import pathlib

import pytest

import gitstat.settings


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
