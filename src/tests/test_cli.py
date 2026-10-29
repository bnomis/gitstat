import asyncio
import dataclasses
import datetime
import io
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import tomllib
import typing
import zoneinfo

import cappa
import hypothesis
import hypothesis.strategies as st
import loguru
import pytest
import rich.console

import gitstat.cli
import gitstat.fetch.base
import gitstat.fetch.cache
import gitstat.fetch.client
import gitstat.fetch.errors
import gitstat.reports.errors
import gitstat.settings
import gitstat.stats
import gitstat.stats.base
import tests.conftest
import tests.fixtures.fetch.responses
import tests.fixtures.fetch.server
import tests.fixtures.fetch.upstream
import tests.fixtures.stats

Subject = gitstat.fetch.base.Subject
UsageError = gitstat.reports.errors.UsageError
SettingsError = gitstat.settings.SettingsError
COMMITS = frozenset({'commits'})
LOGINS = st.from_regex(r'[A-Za-z0-9-]{1,39}', fullmatch=True)
REPO_NAMES = st.from_regex(r'[A-Za-z0-9._-]{1,100}', fullmatch=True)


def report(**changes: object) -> gitstat.cli.Report:
    return gitstat.cli.Report(target='repo:octo-org/alpha', **changes)  # type: ignore[arg-type]


def settings_for(flags: gitstat.cli.Report) -> gitstat.settings.Settings:
    return gitstat.settings.load_settings(None, gitstat.cli.overrides(flags))


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('user:octocat', Subject('user', 'octocat')),
        ('org:octo-org', Subject('org', 'octo-org')),
        ('repo:octocat/Hello-World', Subject('repo', 'octocat', 'Hello-World')),
        ('octocat/Hello-World', Subject('repo', 'octocat', 'Hello-World')),
        ('octocat/hello.world_2', Subject('repo', 'octocat', 'hello.world_2')),
        ('octocat', 'octocat'),
        ('a' * 39, 'a' * 39),
        ('a' * 39 + '/' + 'b' * 100, Subject('repo', 'a' * 39, 'b' * 100)),
    ],
)
def test_valid_targets(text: str, expected: Subject | str) -> None:
    assert gitstat.cli.parse_target(text) == expected


@pytest.mark.parametrize(
    'text',
    [
        '',
        'REPO:octocat/Hello-World',
        'User:octocat',
        'team:octocat',
        'user:',
        'org:',
        'repo:',
        'repo:octocat',
        'user:octocat/Hello-World',
        'a/b/c',
        '/Hello-World',
        'octocat/',
        'a' * 40,
        'a' * 40 + '/b',
        'a/' + 'b' * 101,
        'octo cat',
        'octocat/Hello World',
        'zoë',
        'octocat/zoë',
        'user:octo_cat',
        ':octocat',
        'user:octocat:x',
        'octocat\n',
    ],
)
def test_invalid_targets_name_the_accepted_forms(text: str) -> None:
    with pytest.raises(UsageError, match=r'user:NAME, org:NAME, repo:OWNER/NAME'):
        gitstat.cli.parse_target(text)


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(login=LOGINS, name=REPO_NAMES)
def test_every_valid_login_and_repo_name_round_trips(login: str, name: str) -> None:
    assert gitstat.cli.parse_target(f'user:{login}') == Subject('user', login)
    assert gitstat.cli.parse_target(f'org:{login}') == Subject('org', login)
    assert gitstat.cli.parse_target(f'repo:{login}/{name}') == Subject('repo', login, name)
    assert gitstat.cli.parse_target(f'{login}/{name}') == Subject('repo', login, name)
    assert gitstat.cli.parse_target(login) == login


def allowed(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == '-')


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(
    login=LOGINS,
    bad=st.characters().filter(lambda char: not allowed(char)),
    where=st.integers(min_value=0, max_value=39),
    prefix=st.sampled_from(['user:', 'org:', 'repo:', '']),
)
def test_a_character_outside_the_login_rule_is_rejected(
    login: str, bad: str, where: int, prefix: str
) -> None:
    where = min(where, len(login))
    owner = login[:where] + bad + login[where:]
    with pytest.raises(UsageError):
        gitstat.cli.parse_target(
            f'{prefix}{owner}/name' if prefix in ('repo:', '') else prefix + owner
        )


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(login=st.text(alphabet='ab-', min_size=40, max_size=60))
def test_a_login_over_the_length_limit_is_rejected(login: str) -> None:
    with pytest.raises(UsageError):
        gitstat.cli.parse_target(f'user:{login}')


def test_dates_are_exactly_year_month_day() -> None:
    assert gitstat.cli.parse_date('2026-10-29') == datetime.date(2026, 10, 29)


@pytest.mark.parametrize(
    'text', ['20261029', '2026-W44-1', '2026-02-30', '2026-1-1', '26-10-29', '', '2026-10-29 ']
)
def test_other_date_forms_are_rejected_naming_the_flag(text: str) -> None:
    with pytest.raises(UsageError, match='--since must be a date written YYYY-MM-DD'):
        gitstat.cli.parse_date(text, '--since')


def test_overrides_are_only_the_flags_given() -> None:
    assert gitstat.cli.overrides(report()) == {}
    assert gitstat.cli.overrides(report(format='json')) == {'report': {'format': 'json'}}
    assert gitstat.cli.overrides(report(max_age='1d', tz='Europe/Berlin')) == {
        'fetch': {'max_age': '1d'},
        'stats': {'timezone': 'Europe/Berlin'},
    }


def test_the_overrides_reach_the_settings() -> None:
    settings = settings_for(report(format='json', max_age='1d', tz='Europe/Berlin'))
    assert settings.report.format == 'json'
    assert settings.fetch.max_age == datetime.timedelta(days=1)
    assert settings.stats.timezone == 'Europe/Berlin'


def test_a_malformed_max_age_is_a_settings_error_naming_the_setting() -> None:
    with pytest.raises(SettingsError, match='fetch.max_age'):
        settings_for(report(max_age='1x'))


def test_an_unknown_time_zone_is_a_settings_error_naming_the_setting_not_the_value() -> None:
    settings = settings_for(report(tz='Mars/Base'))
    with pytest.raises(SettingsError, match='stats.timezone') as caught:
        gitstat.cli.resolve_tz(settings)
    assert 'Mars' not in str(caught.value)


@pytest.mark.parametrize('zone', ['', '../etc/passwd', 'UTC/..'])
def test_a_malformed_time_zone_key_is_also_a_settings_error(zone: str) -> None:
    settings = settings_for(report(tz=zone))
    with pytest.raises(SettingsError, match='stats.timezone'):
        gitstat.cli.resolve_tz(settings)


def test_a_known_time_zone_resolves() -> None:
    settings = settings_for(report(tz='Europe/Berlin'))
    assert gitstat.cli.resolve_tz(settings) == zoneinfo.ZoneInfo('Europe/Berlin')


def test_the_request_defaults_follow_the_stats_request() -> None:
    flags = report()
    settings = settings_for(flags)
    request = gitstat.cli.build_request(flags, settings, gitstat.cli.resolve_tz(settings))
    assert request.granularity is gitstat.stats.base.Granularity.MONTH
    assert request.groups == gitstat.stats.base.StatsRequest().groups
    assert (request.since, request.until, request.by_author) == (None, None, False)
    assert request.settings == settings.stats


def test_the_request_carries_the_flags() -> None:
    flags = report(by='week', since='2026-10-01', until='2026-10-29', by_author=True, tz='UTC')
    settings = settings_for(flags)
    request = gitstat.cli.build_request(flags, settings, gitstat.cli.resolve_tz(settings))
    assert request.granularity is gitstat.stats.base.Granularity.WEEK
    assert request.since == datetime.date(2026, 10, 1)
    assert request.until == datetime.date(2026, 10, 29)
    assert request.by_author is True


def test_groups_are_split_on_commas_and_stripped() -> None:
    flags = report(groups='activity, flow')
    settings = settings_for(flags)
    request = gitstat.cli.build_request(flags, settings, gitstat.cli.resolve_tz(settings))
    assert request.groups == frozenset({'activity', 'flow'})


def test_an_unknown_group_is_passed_through_for_compute_to_reject() -> None:
    flags = report(groups='activity,bogus')
    settings = settings_for(flags)
    request = gitstat.cli.build_request(flags, settings, gitstat.cli.resolve_tz(settings))
    assert request.groups == frozenset({'activity', 'bogus'})


def test_no_group_at_all_is_a_usage_error() -> None:
    flags = report(groups=' , ')
    settings = settings_for(flags)
    with pytest.raises(UsageError, match='--groups'):
        gitstat.cli.build_request(flags, settings, gitstat.cli.resolve_tz(settings))


@pytest.mark.parametrize(('since', 'until'), [('20261029', None), (None, '2026-02-30')])
def test_a_bad_date_flag_is_a_usage_error(since: str | None, until: str | None) -> None:
    flags = report(since=since, until=until)
    settings = settings_for(flags)
    with pytest.raises(UsageError, match='YYYY-MM-DD'):
        gitstat.cli.build_request(flags, settings, gitstat.cli.resolve_tz(settings))


def test_full_refresh_with_no_fetch_is_a_usage_error() -> None:
    flags = report(full_refresh=True, no_fetch=True)
    with pytest.raises(UsageError, match='--full-refresh and --no-fetch'):
        gitstat.cli.check_report(flags, settings_for(flags))


def test_the_html_format_is_a_usage_error_naming_step_7_from_a_flag_or_the_config() -> None:
    flags = report(format='html')
    with pytest.raises(UsageError, match='step 7'):
        gitstat.cli.check_report(flags, settings_for(flags))
    configured = dataclasses.replace(
        gitstat.settings.Settings(),
        report=dataclasses.replace(gitstat.settings.ReportSettings(), format='html'),
    )
    with pytest.raises(UsageError, match='step 7'):
        gitstat.cli.check_report(report(), configured)


def test_a_bare_name_with_no_fetch_asks_for_a_prefix() -> None:
    flags = gitstat.cli.Report(target='octocat', no_fetch=True)
    with pytest.raises(UsageError, match='user:NAME or org:NAME'):
        gitstat.cli.check_report(flags, settings_for(flags))


def test_by_author_with_an_explicit_user_is_a_usage_error() -> None:
    flags = gitstat.cli.Report(target='user:octocat', by_author=True)
    with pytest.raises(UsageError, match='--by-author'):
        gitstat.cli.check_report(flags, settings_for(flags))


@pytest.mark.parametrize(
    'flags',
    [
        report(),
        report(by_author=True),
        report(no_fetch=True),
        report(full_refresh=True),
        report(format='json'),
        gitstat.cli.Report(target='octocat'),
        gitstat.cli.Report(target='user:octocat', no_fetch=True),
    ],
)
def test_other_combinations_pass_the_checks(flags: gitstat.cli.Report) -> None:
    gitstat.cli.check_report(flags, settings_for(flags))


def test_verbose_and_quiet_together_are_a_usage_error() -> None:
    command = gitstat.cli.CacheCommand(action='info')
    gitstat.cli.check_verbosity(gitstat.cli.Gitstat(command, verbose=True))
    gitstat.cli.check_verbosity(gitstat.cli.Gitstat(command, quiet=True))
    with pytest.raises(UsageError, match='-v and -q'):
        gitstat.cli.check_verbosity(gitstat.cli.Gitstat(command, verbose=True, quiet=True))


def test_cappa_reads_every_report_flag() -> None:
    parsed = cappa.parse(
        gitstat.cli.Gitstat,
        argv=[
            '-v',
            'report',
            'org:octo-org',
            '--format',
            'json',
            '--by',
            'week',
            '--since',
            '2026-10-01',
            '--until',
            '2026-10-29',
            '--groups',
            'activity',
            '--by-author',
            '--tz',
            'UTC',
            '--max-age',
            '1d',
            '--ignore-cache-version',
        ],
    )
    assert parsed.verbose is True
    assert parsed.command == gitstat.cli.Report(
        target='org:octo-org',
        format='json',
        by='week',
        since='2026-10-01',
        until='2026-10-29',
        groups='activity',
        by_author=True,
        tz='UTC',
        max_age='1d',
        ignore_cache_version=True,
    )


def test_cappa_reads_the_cache_command_and_the_two_cache_flags() -> None:
    assert cappa.parse(gitstat.cli.Gitstat, argv=['-q', 'cache', 'clear']).command == (
        gitstat.cli.CacheCommand(action='clear')
    )
    parsed = cappa.parse(
        gitstat.cli.Gitstat, argv=['report', 'a/b', '--full-refresh', '--no-fetch']
    ).command
    assert isinstance(parsed, gitstat.cli.Report)
    assert (parsed.full_refresh, parsed.no_fetch) == (True, True)


@pytest.mark.parametrize(
    'argv', [['report', 'a/b', '--by', 'fortnight'], ['cache', 'wipe'], ['report'], []]
)
def test_cappa_rejects_what_it_cannot_parse_with_exit_status_2(argv: list[str]) -> None:
    with pytest.raises(cappa.Exit) as caught:
        cappa.parse(gitstat.cli.Gitstat, argv=argv)
    assert caught.value.code == 2


UTC = datetime.UTC
SYNCED = tests.fixtures.stats.ALPHA_SYNCED_AT
ALPHA_FLAGS = ['--since', '2026-10-01', '--until', '2027-01-31']


class SessionOpened(AssertionError):
    pass


class NoSessionClient(gitstat.fetch.client.GitHubClient):
    """A client that fails the test if anything opens its aiohttp session."""

    async def __aenter__(self) -> typing.Self:
        raise SessionOpened('the report opened a network session')


@dataclasses.dataclass
class Ran:
    console: str
    stdout: str
    paths: list[str]
    syncs: list[tuple[gitstat.fetch.base.Subject, frozenset[str], bool]]


def alpha_upstream() -> tests.fixtures.fetch.upstream.Upstream:
    """A fake GitHub whose repositories match the stats fixture's, so a sync finds them
    unchanged."""
    alpha, _, gamma = tests.fixtures.stats.REPOS
    repos = [
        tests.fixtures.fetch.upstream.FakeRepo(
            repo.name_with_owner,
            [
                tests.fixtures.fetch.upstream.FakeCommit(
                    str(repo.head_oid), datetime.datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
                )
            ],
            pushed_at=repo.pushed_at or tests.fixtures.stats.NOW,
            updated_at=repo.updated_at,
        )
        for repo in (alpha, gamma)
    ]
    return tests.fixtures.fetch.upstream.Upstream(repos)


def cli_settings(flags: gitstat.cli.Report, cache_path: pathlib.Path) -> gitstat.settings.Settings:
    base = settings_for(flags)
    return dataclasses.replace(base, fetch=dataclasses.replace(base.fetch, cache_path=cache_path))


def parse_report(*argv: str) -> gitstat.cli.Report:
    parsed = cappa.parse(gitstat.cli.Gitstat, argv=['report', *argv])
    assert isinstance(parsed.command, gitstat.cli.Report)
    return parsed.command


def run_report(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    cache_path: pathlib.Path,
    argv: list[str],
    *,
    clock: datetime.datetime = SYNCED + datetime.timedelta(days=1),
    routes: dict[tuple[str, str], list[tests.fixtures.fetch.server.Canned]] | None = None,
    upstream: tests.fixtures.fetch.upstream.Upstream | None = None,
    online: bool = True,
) -> Ran:
    """Run `gitstat report` with `argv`. With `online` False the fetcher's client fails on any
    use of a session; otherwise requests go to a replay server over `upstream`."""
    flags = parse_report(*argv)
    settings = cli_settings(flags, cache_path)
    syncs: list[tuple[gitstat.fetch.base.Subject, frozenset[str], bool]] = []
    original = gitstat.fetch.base.Fetcher.sync

    async def spy(
        self: gitstat.fetch.base.Fetcher,
        subject: gitstat.fetch.base.Subject,
        resources: frozenset[str],
        full_refresh: bool = False,
    ) -> gitstat.fetch.base.SyncReport:
        syncs.append((subject, resources, full_refresh))
        return await original(self, subject, resources, full_refresh)

    monkeypatch.setattr(gitstat.fetch.base.Fetcher, 'sync', spy)
    console = io.StringIO()
    stdout = io.StringIO()

    async def scenario() -> list[str]:
        server = tests.fixtures.fetch.server.ReplayServer(
            routes or {}, (upstream or alpha_upstream()).respond
        )
        async with server:

            def factory(
                token: str,
                cache: gitstat.fetch.cache.Cache,
                fetch_settings: gitstat.settings.FetchSettings,
            ) -> gitstat.fetch.base.Fetcher:
                client = (
                    make_client(server, fetch_settings)
                    if online
                    else NoSessionClient('', fetch_settings)
                )
                return gitstat.fetch.base.Fetcher(token, cache, fetch_settings, client=client)

            monkeypatch.setattr(gitstat.cli, 'make_fetcher', factory)
            await gitstat.cli.run_report(
                flags,
                settings,
                rich.console.Console(
                    file=console, width=120, color_system=None, legacy_windows=False
                ),
                stdout,
                clock=lambda: clock,
            )
            return [received.path for received in server.received]

    paths = asyncio.run(scenario())
    return Ran(console.getvalue(), stdout.getvalue(), paths, syncs)


def test_a_warm_cache_with_no_fetch_reports_without_a_token_or_a_session(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    assert 'GITHUB_TOKEN' not in os.environ
    ran = run_report(
        monkeypatch,
        make_client,
        stats_cache_path,
        ['repo:octo-org/alpha', '--by', 'month', '--no-fetch', *ALPHA_FLAGS],
        online=False,
    )
    assert 'Activity by period' in ran.console
    assert 'repo octo-org/alpha, 2026-10-01 to 2027-01-31, by month, UTC' in ran.console
    assert ran.syncs == []
    assert ran.paths == []
    assert ran.stdout == ''


def test_a_cache_younger_than_max_age_is_reported_without_a_token_or_a_session(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    ran = run_report(
        monkeypatch,
        make_client,
        stats_cache_path,
        ['repo:octo-org/alpha', '--max-age', '30d', *ALPHA_FLAGS],
        online=False,
    )
    assert 'Activity by period' in ran.console
    assert ran.syncs == []


def test_a_cache_older_than_max_age_syncs_through_the_server(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    upstream = alpha_upstream()
    ran = run_report(
        monkeypatch,
        make_client,
        stats_cache_path,
        ['repo:octo-org/alpha', '--max-age', '30d', *ALPHA_FLAGS],
        clock=SYNCED + datetime.timedelta(days=31),
        upstream=upstream,
    )
    assert ran.syncs == [(Subject('repo', 'octo-org', 'alpha'), COMMITS, False)]
    assert ran.paths == ['/graphql']
    assert 'Activity by period' in ran.console


def test_a_sync_with_no_token_fails_with_an_auth_error(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    def no_gh(*args: object, **kwargs: object) -> typing.NoReturn:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, 'run', no_gh)
    with pytest.raises(gitstat.fetch.errors.AuthError, match='GITHUB_TOKEN'):
        run_report(
            monkeypatch,
            make_client,
            stats_cache_path,
            ['repo:octo-org/alpha', *ALPHA_FLAGS],
            online=False,
        )


def test_full_refresh_syncs_a_fresh_cache_and_reads_the_history_again(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    upstream = alpha_upstream()
    ran = run_report(
        monkeypatch,
        make_client,
        stats_cache_path,
        ['repo:octo-org/alpha', '--max-age', '30d', '--full-refresh', *ALPHA_FLAGS],
        upstream=upstream,
    )
    assert ran.syncs == [(Subject('repo', 'octo-org', 'alpha'), COMMITS, True)]
    assert 'Activity by period' in ran.console


def test_the_default_groups_sync_only_commits_and_list_flow_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    ran = run_report(
        monkeypatch, make_client, stats_cache_path, ['repo:octo-org/alpha', *ALPHA_FLAGS]
    )
    assert ran.syncs == [(Subject('repo', 'octo-org', 'alpha'), COMMITS, False)]
    assert gitstat.stats.base.StatsRequest().groups == frozenset({'activity', 'flow'})
    assert 'Unavailable' in ran.console
    assert re.search(r'^\s+flow\s+the flow group', ran.console, re.MULTILINE)


def test_only_built_resources_are_ever_synced(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    ran = run_report(
        monkeypatch,
        make_client,
        stats_cache_path,
        ['repo:octo-org/alpha', '--groups', 'activity,flow,delivery', *ALPHA_FLAGS],
    )
    for _, resources, _ in ran.syncs:
        assert resources <= gitstat.fetch.base.BUILT_RESOURCES


def test_a_bare_name_is_resolved_through_the_users_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    routes = {
        ('GET', '/users/octocat'): [
            tests.fixtures.fetch.server.Canned(200, tests.fixtures.fetch.responses.USER_OK)
        ]
    }
    ran = run_report(
        monkeypatch,
        make_client,
        stats_cache_path,
        ['octocat', '--by', 'total', *ALPHA_FLAGS],
        routes=routes,
    )
    assert ran.paths[0] == '/users/octocat'
    assert ran.syncs == [(Subject('user', 'octocat'), COMMITS, False)]
    assert ran.console.startswith('user octocat, 2026-10-01 to 2027-01-31, total, UTC')


def test_a_bare_name_that_is_an_organisation_reports_the_organisation(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    routes = {
        ('GET', '/users/octo-org'): [
            tests.fixtures.fetch.server.Canned(200, {'login': 'octo-org', 'type': 'Organization'})
        ]
    }
    ran = run_report(
        monkeypatch,
        make_client,
        stats_cache_path,
        ['octo-org', '--max-age', '30d', *ALPHA_FLAGS],
        routes=routes,
    )
    assert ran.console.startswith('org octo-org, ')


def test_by_author_with_a_name_that_resolves_to_a_user_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    routes = {
        ('GET', '/users/octocat'): [
            tests.fixtures.fetch.server.Canned(200, tests.fixtures.fetch.responses.USER_OK)
        ]
    }
    with pytest.raises(UsageError, match='--by-author'):
        run_report(
            monkeypatch,
            make_client,
            stats_cache_path,
            ['octocat', '--by-author', *ALPHA_FLAGS],
            routes=routes,
        )


def test_by_author_with_an_explicit_user_is_rejected_before_the_cache_is_opened(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / 'never' / 'cache.sqlite3'
    with pytest.raises(UsageError, match='--by-author'):
        run_report(
            monkeypatch,
            make_client,
            path,
            ['user:octocat', '--by-author'],
            online=False,
        )
    assert not path.parent.exists()


def test_json_goes_to_stdout_and_nothing_else_does(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    ran = run_report(
        monkeypatch,
        make_client,
        stats_cache_path,
        ['repo:octo-org/alpha', '--no-fetch', '--format', 'json', *ALPHA_FLAGS],
        online=False,
    )
    data = json.loads(ran.stdout)
    assert data['format_version'] == 1
    assert data['subject'] == {'kind': 'repo', 'login': 'octo-org', 'name': 'alpha'}
    assert ran.console == ''


def set_schema_version(path: pathlib.Path, value: str) -> None:
    connection = sqlite3.connect(path)
    with connection:
        connection.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (value,))
    connection.close()


def test_ignore_cache_version_reports_a_refused_cache_with_a_warning(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    set_schema_version(stats_cache_path, '0')
    argv = ['repo:octo-org/alpha', '--no-fetch', *ALPHA_FLAGS]
    with pytest.raises(gitstat.fetch.errors.CacheVersionError, match='--ignore-cache-version'):
        run_report(monkeypatch, make_client, stats_cache_path, argv, online=False)
    ran = run_report(
        monkeypatch, make_client, stats_cache_path, [*argv, '--ignore-cache-version'], online=False
    )
    (warning,) = [line for line in ran.console.splitlines() if line.startswith('Warning')]
    assert '--ignore-cache-version' in warning


def test_a_group_that_needs_no_resource_syncs_nothing_and_finds_nothing_to_report(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    stats_cache_path: pathlib.Path,
) -> None:
    with pytest.raises(gitstat.stats.EmptySubjectError, match='no requested group is built'):
        run_report(
            monkeypatch,
            make_client,
            stats_cache_path,
            ['repo:octo-org/alpha', '--groups', 'flow'],
            online=False,
        )


def test_an_unknown_group_is_rejected_before_the_cache_is_opened(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / 'never' / 'cache.sqlite3'
    with pytest.raises(gitstat.stats.UnknownGroupError, match='bogus'):
        run_report(monkeypatch, make_client, path, ['repo:a/b', '--groups', 'bogus'], online=False)
    assert not path.parent.exists()


def test_an_empty_cache_with_no_fetch_says_it_may_only_need_a_sync(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    tmp_path: pathlib.Path,
) -> None:
    with pytest.raises(gitstat.stats.EmptySubjectError, match='try again without --no-fetch'):
        run_report(
            monkeypatch,
            make_client,
            tmp_path / 'empty' / 'cache.sqlite3',
            ['user:octocat', '--no-fetch'],
            online=False,
        )


def test_an_empty_cache_without_no_fetch_gives_no_such_hint(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    tmp_path: pathlib.Path,
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    with pytest.raises(gitstat.stats.EmptySubjectError) as caught:
        run_report(
            monkeypatch,
            make_client,
            tmp_path / 'empty' / 'cache.sqlite3',
            ['user:nobody', '--groups', 'activity'],
            upstream=tests.fixtures.fetch.upstream.Upstream([]),
        )
    assert '--no-fetch' not in str(caught.value)


def fetch_settings(max_age: str) -> gitstat.settings.FetchSettings:
    return settings_for(report(max_age=max_age)).fetch


NOW = datetime.datetime(2027, 3, 1, 12, 0, tzinfo=UTC)
FRESH = (NOW - datetime.timedelta(hours=1)).isoformat()
STALE = (NOW - datetime.timedelta(days=2)).isoformat()


@pytest.mark.parametrize(
    ('provenance', 'resources', 'max_age', 'full_refresh', 'no_fetch', 'expected'),
    [
        ({'fetched_at:commits': FRESH}, {'commits'}, '1d', False, True, False),
        ({'fetched_at:commits': STALE}, {'commits'}, '1d', True, True, False),
        ({}, set(), '0s', False, False, False),
        ({}, set(), '0s', True, False, False),
        ({'fetched_at:commits': FRESH}, {'commits'}, '1d', True, False, True),
        ({'fetched_at:commits': FRESH}, {'commits'}, '0s', False, False, True),
        ({'fetched_at:commits': FRESH}, {'commits'}, '1d', False, False, False),
        ({'fetched_at:commits': STALE}, {'commits'}, '1d', False, False, True),
        ({'fetched_at:commits': 'never'}, {'commits'}, '1d', False, False, True),
        ({}, {'commits'}, '1d', False, False, True),
        (
            {'fetched_at:commits': FRESH, 'fetched_at:issues': STALE},
            {'commits', 'issues'},
            '1d',
            False,
            False,
            True,
        ),
        (
            {'fetched_at:commits': FRESH, 'fetched_at:issues': FRESH},
            {'commits', 'issues'},
            '1d',
            False,
            False,
            False,
        ),
    ],
)
def test_needs_sync(
    provenance: dict[str, str],
    resources: set[str],
    max_age: str,
    full_refresh: bool,
    no_fetch: bool,
    expected: bool,
) -> None:
    assert (
        gitstat.cli.needs_sync(
            provenance, frozenset(resources), fetch_settings(max_age), full_refresh, no_fetch, NOW
        )
        is expected
    )


def test_a_cache_exactly_max_age_old_is_stale() -> None:
    provenance = {'fetched_at:commits': (NOW - datetime.timedelta(days=1)).isoformat()}
    assert gitstat.cli.needs_sync(provenance, COMMITS, fetch_settings('1d'), False, False, NOW)


def run_cache(
    action: typing.Literal['clear', 'info'], cache_path: pathlib.Path
) -> tuple[str, list[str]]:
    """The console output and the info-level log lines of `gitstat cache <action>`."""
    messages: list[str] = []
    sink = loguru.logger.add(
        lambda message: messages.append(message.record['message']), level='INFO'
    )
    out = io.StringIO()
    try:
        gitstat.cli.run_cache(
            gitstat.cli.CacheCommand(action),
            cli_settings(report(), cache_path),
            rich.console.Console(file=out, width=120, color_system=None, legacy_windows=False),
        )
    finally:
        loguru.logger.remove(sink)
    return out.getvalue(), messages


def test_cache_info_lists_the_counts_and_no_differences(stats_cache_path: pathlib.Path) -> None:
    output, messages = run_cache('info', stats_cache_path)
    assert messages == []
    rows = {line.split()[0]: line.split()[1:] for line in output.splitlines() if line.strip()}
    assert rows['repositories'] == ['3']
    assert rows['commits'] == [str(len(tests.fixtures.stats.COMMITS))]
    assert rows['differences'] == ['none']
    assert rows['last'] == ['synced', tests.fixtures.stats.BETA_SYNCED_AT.isoformat()]
    assert rows['schema_version'] == ['1']
    assert str(stats_cache_path) in output
    assert 'differs' not in output


def test_cache_info_shows_why_a_cache_is_refused_and_leaves_it_alone(
    stats_cache_path: pathlib.Path,
) -> None:
    set_schema_version(stats_cache_path, '0')

    def meta() -> list[tuple[str, str]]:
        connection = sqlite3.connect(stats_cache_path)
        try:
            return connection.execute('SELECT key, value FROM meta ORDER BY key').fetchall()
        finally:
            connection.close()

    before = meta()
    output, _ = run_cache('info', stats_cache_path)
    assert 'differs: schema_version' in output
    assert '0 -> 1' in output
    assert meta() == before


def test_cache_info_of_a_missing_path_says_so_and_creates_nothing(tmp_path: pathlib.Path) -> None:
    path = tmp_path / 'missing' / 'cache.sqlite3'
    output, _ = run_cache('info', path)
    assert output.strip() == f'no cache at {path}'
    assert not path.parent.exists()


def test_cache_clear_removes_the_files_then_reports_nothing_to_remove(
    stats_cache: gitstat.fetch.cache.Cache, stats_cache_path: pathlib.Path
) -> None:
    wal = stats_cache_path.with_name(stats_cache_path.name + '-wal')
    shm = stats_cache_path.with_name(stats_cache_path.name + '-shm')
    assert wal.exists()
    _, removed = run_cache('clear', stats_cache_path)
    assert removed == [f'Removed {stats_cache_path}', f'Removed {wal}', f'Removed {shm}']
    assert not stats_cache_path.exists()
    _, again = run_cache('clear', stats_cache_path)
    assert again == [f'no cache at {stats_cache_path}']


@pytest.fixture(autouse=True)
def restore_logger() -> typing.Iterator[None]:
    yield
    loguru.logger.remove()


def config_for(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, cache: pathlib.Path
) -> None:
    config = tmp_path / 'main-config.json'
    config.write_text(json.dumps({'fetch': {'cache_path': str(cache)}}))
    monkeypatch.setenv('GITSTAT_CONFIG', str(config))


def raising(error: BaseException) -> typing.Callable[..., typing.Awaitable[None]]:
    async def run(*args: object, **kwargs: object) -> None:
        raise error

    return run


RESET = datetime.datetime(2027, 3, 1, 13, 0, tzinfo=UTC)
ERROR_STATUSES = [
    (gitstat.fetch.errors.AuthError('No GitHub token found: set GITHUB_TOKEN'), 1),
    (
        gitstat.fetch.errors.CacheVersionError({'schema_version': ('0', '1')}),
        1,
    ),
    (gitstat.fetch.errors.GraphQLError([('NOT_FOUND', 'no such thing')]), 1),
    (gitstat.fetch.errors.NotFoundError('octocat not found'), 1),
    (gitstat.fetch.errors.RateLimitError(RESET), 1),
    (gitstat.fetch.errors.StatsPendingError('still computing'), 1),
    (gitstat.stats.EmptySubjectError('no commits in the cache for this range'), 1),
    (gitstat.stats.InvalidRangeError('since is after until'), 1),
    (gitstat.stats.InvalidRequestError('by_author is not meaningful for a user'), 1),
    (gitstat.stats.UnknownGroupError('unknown groups: bogus'), 1),
    (UsageError('flags clash'), 2),
    (SettingsError('fetch.max_age is wrong'), 2),
]


@pytest.mark.parametrize(
    ('error', 'status'), ERROR_STATUSES, ids=[type(error).__name__ for error, _ in ERROR_STATUSES]
)
def test_each_typed_error_is_one_logged_line_and_its_exit_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    status: int,
) -> None:
    monkeypatch.setattr(gitstat.cli, 'run_report', raising(error))
    assert gitstat.cli.main(['report', 'repo:octo-org/alpha']) == status
    captured = capsys.readouterr()
    errors = [line for line in captured.err.splitlines() if line.startswith('ERROR:')]
    assert errors == [f'ERROR: {error}']
    assert 'Traceback' not in captured.err
    assert captured.out == ''


def test_any_other_exception_logs_its_traceback_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gitstat.cli, 'run_report', raising(RuntimeError('boom')))
    assert gitstat.cli.main(['report', 'repo:octo-org/alpha']) == 1
    err = capsys.readouterr().err
    assert 'Traceback' in err
    assert 'RuntimeError: boom' in err


def test_a_keyboard_interrupt_exits_130_with_no_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gitstat.cli, 'run_report', raising(KeyboardInterrupt()))
    assert gitstat.cli.main(['report', 'repo:octo-org/alpha']) == 130
    assert capsys.readouterr().err == ''


def test_help_returns_0_and_a_bad_command_line_returns_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert gitstat.cli.main(['--help']) == 0
    assert 'report' in capsys.readouterr().out
    assert gitstat.cli.main(['report', 'repo:a/b', '--by', 'fortnight']) == 2
    assert gitstat.cli.main([]) == 2


def test_a_missing_config_file_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    monkeypatch.setenv('GITSTAT_CONFIG', str(tmp_path / 'absent.json'))
    assert gitstat.cli.main(['cache', 'info']) == 2
    assert 'does not exist' in capsys.readouterr().err


def test_verbose_and_quiet_together_return_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert gitstat.cli.main(['-v', '-q', 'cache', 'info']) == 2
    assert 'ERROR: -v and -q cannot be used together' in capsys.readouterr().err


def test_a_bad_flag_value_returns_2_before_any_cache_is_opened(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
) -> None:
    cache = tmp_path / 'never' / 'cache.sqlite3'
    config_for(tmp_path, monkeypatch, cache)
    assert gitstat.cli.main(['report', 'repo:a/b', '--max-age', '1x']) == 2
    assert 'fetch.max_age' in capsys.readouterr().err
    assert gitstat.cli.main(['report', 'a/b/c']) == 2
    assert gitstat.cli.main(['report', 'repo:a/b', '--format', 'html']) == 2
    assert not cache.parent.exists()


def test_a_warm_cache_report_through_main_returns_0_and_prints_the_period_table(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
    stats_cache_path: pathlib.Path,
) -> None:
    config_for(tmp_path, monkeypatch, stats_cache_path)
    argv = ['report', 'repo:octo-org/alpha', '--no-fetch', *ALPHA_FLAGS]
    assert gitstat.cli.main(argv) == 0
    captured = capsys.readouterr()
    assert 'Activity by period' in captured.out
    assert '2026-10' in captured.out
    assert captured.err == ''


def test_json_through_main_is_pure_json_on_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
    stats_cache_path: pathlib.Path,
) -> None:
    config_for(tmp_path, monkeypatch, stats_cache_path)
    argv = ['report', 'org:octo-org', '--no-fetch', '--format', 'json', *ALPHA_FLAGS]
    assert gitstat.cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)['subject']['login'] == 'octo-org'


def test_a_cache_command_through_main_returns_0(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
) -> None:
    config_for(tmp_path, monkeypatch, tmp_path / 'absent' / 'cache.sqlite3')
    assert gitstat.cli.main(['cache', 'info']) == 0
    assert 'no cache at' in capsys.readouterr().out
    assert gitstat.cli.main(['-q', 'cache', 'clear']) == 0


TOKEN = 'ghp_sentinelsentinelsentinelsentinel1234'


def test_a_token_in_an_error_never_reaches_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', TOKEN)
    for error in (
        gitstat.fetch.errors.AuthError(f'bad credentials {TOKEN}'),
        RuntimeError(f'request failed with {TOKEN}'),
    ):
        monkeypatch.setattr(gitstat.cli, 'run_report', raising(error))
        assert gitstat.cli.main(['report', 'repo:octo-org/alpha']) == 1
        err = capsys.readouterr().err
        assert err
        assert TOKEN not in err
        assert '***' in err


def test_a_token_in_the_cause_of_an_error_never_reaches_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', TOKEN)

    async def run(*args: object, **kwargs: object) -> None:
        try:
            raise ValueError(f'inner {TOKEN}')
        except ValueError as e:
            raise RuntimeError('outer') from e

    monkeypatch.setattr(gitstat.cli, 'run_report', run)
    assert gitstat.cli.main(['report', 'repo:octo-org/alpha']) == 1
    assert TOKEN not in capsys.readouterr().err


SRC = pathlib.Path(__file__).parents[1]


def subprocess_environment() -> dict[str, str]:
    return {
        **os.environ,
        'PYTHONPATH': os.pathsep.join([str(SRC), os.environ.get('PYTHONPATH', '')]),
    }


def test_python_dash_m_gitstat_help_exits_0() -> None:
    done = subprocess.run(
        [sys.executable, '-m', 'gitstat', '--help'],
        capture_output=True,
        text=True,
        env=subprocess_environment(),
        check=False,
    )
    assert done.returncode == 0
    assert 'report' in done.stdout
    assert 'cache' in done.stdout


def test_the_gitstat_console_script_exits_0_and_lists_both_commands() -> None:
    script = pathlib.Path(sys.executable).parent / 'gitstat'
    assert script.exists(), 'the console script is installed by `uv sync`'
    done = subprocess.run([str(script), '--help'], capture_output=True, text=True, check=False)
    assert done.returncode == 0
    assert 'report' in done.stdout
    assert 'cache' in done.stdout


def test_the_console_script_is_declared_in_pyproject() -> None:
    pyproject = tomllib.loads((SRC.parent / 'pyproject.toml').read_text())
    assert pyproject['project']['scripts'] == {'gitstat': 'gitstat.cli:run'}


def test_a_closed_pipe_ends_the_terminal_report_quietly(
    tmp_path: pathlib.Path, stats_cache_path: pathlib.Path
) -> None:
    config = tmp_path / 'pipe-config.json'
    config.write_text(json.dumps({'fetch': {'cache_path': str(stats_cache_path)}}))
    environment = {**subprocess_environment(), 'GITSTAT_CONFIG': str(config)}
    process = subprocess.Popen(
        [
            sys.executable,
            '-m',
            'gitstat',
            'report',
            'org:octo-org',
            '--no-fetch',
            *ALPHA_FLAGS,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    assert process.stdout.readline()
    process.stdout.close()
    assert process.wait(timeout=30) == 1
    assert process.stderr.read() == ''
    process.stderr.close()


class PipeStdout:
    """A stand-in for sys.stdout that has a file descriptor."""

    def fileno(self) -> int:
        return 1

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        pass


def test_a_broken_pipe_while_writing_json_ends_quietly_with_status_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    redirected: list[tuple[int, int]] = []
    monkeypatch.setattr(os, 'dup2', lambda source, target: redirected.append((source, target)))
    monkeypatch.setattr(sys, 'stdout', PipeStdout())
    monkeypatch.setattr(gitstat.cli, 'run_report', raising(BrokenPipeError()))
    assert gitstat.cli.main(['report', 'repo:octo-org/alpha', '--format', 'json']) == 1
    assert capsys.readouterr().err == ''
    assert [target for _, target in redirected] == [1]


def report_choices(field: str) -> set[object]:
    """The values of every Literal in the annotation of a `Report` field."""
    annotation = typing.get_type_hints(gitstat.cli.Report, include_extras=True)[field]
    (bare, *_) = typing.get_args(annotation)
    members = typing.get_args(bare) if typing.get_origin(bare) is not typing.Literal else (bare,)
    return {value for member in members for value in typing.get_args(member)}


def test_the_by_choices_are_the_granularities() -> None:
    assert report_choices('by') == {g.value for g in gitstat.stats.base.Granularity}


def test_the_format_choices_are_the_report_formats() -> None:
    settings_hints = typing.get_type_hints(gitstat.settings.ReportSettings)
    assert report_choices('format') == set(typing.get_args(settings_hints['format']))
