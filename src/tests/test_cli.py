import dataclasses
import datetime
import zoneinfo

import cappa
import hypothesis
import hypothesis.strategies as st
import pytest

import gitstat.cli
import gitstat.fetch.base
import gitstat.reports.errors
import gitstat.settings
import gitstat.stats.base

Subject = gitstat.fetch.base.Subject
UsageError = gitstat.reports.errors.UsageError
SettingsError = gitstat.settings.SettingsError
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


@pytest.mark.parametrize(
    'flags',
    [
        report(),
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
