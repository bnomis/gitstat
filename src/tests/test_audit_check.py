import collections.abc
import io
import pathlib
import subprocess
import types

import loguru
import pytest

STATS_ALIAS = 'src/wambatic/stats/base.py:3 typing-deprecated-alias List'
TEST_ALIAS = 'src/tests/reports/test_base.py:8 aliased-imports import X as Y'
EXTRA_ALIAS = 'src/wambatic_extra/base.py:12 typing-deprecated-alias Dict'
LOCKFILE = '-:- lockfile-stale uv lock --check'
EVERY_HIT = [STATS_ALIAS, TEST_ALIAS, EXTRA_ALIAS, LOCKFILE]

ALIAS_RULE = ['typing-deprecated-alias']
ACCEPTED_RULE = ['silent-broad-except']
PACKAGE = ['src/wambatic']


def lines(
    audit_check: types.ModuleType,
    jsonl: str,
    rules: list[str],
    paths: list[str],
) -> list[str]:
    return [audit_check.format_hit(hit) for hit in audit_check.unaccepted(jsonl, rules, paths)]


def test_every_unaccepted_hit_is_listed_in_order(
    audit_check: types.ModuleType,
    audit_jsonl: str,
) -> None:
    assert lines(audit_check, audit_jsonl, [], []) == EVERY_HIT


def test_rule_restricts_to_the_named_rules(
    audit_check: types.ModuleType,
    audit_jsonl: str,
) -> None:
    assert lines(audit_check, audit_jsonl, ALIAS_RULE, []) == [STATS_ALIAS, EXTRA_ALIAS]
    assert lines(audit_check, audit_jsonl, ['aliased-imports', 'lockfile-stale'], []) == [
        TEST_ALIAS,
        LOCKFILE,
    ]
    assert not lines(audit_check, audit_jsonl, ACCEPTED_RULE, [])


@pytest.mark.parametrize('prefix', ['src/wambatic', 'src/wambatic/'])
def test_path_matches_whole_directories(
    audit_check: types.ModuleType,
    audit_jsonl: str,
    prefix: str,
) -> None:
    assert lines(audit_check, audit_jsonl, [], [prefix]) == [STATS_ALIAS]


def test_paths_and_rules_combine(audit_check: types.ModuleType, audit_jsonl: str) -> None:
    assert lines(audit_check, audit_jsonl, [], ['src/tests', 'src/wambatic_extra']) == [
        TEST_ALIAS,
        EXTRA_ALIAS,
    ]
    assert not lines(audit_check, audit_jsonl, ['aliased-imports'], PACKAGE)
    one_file = ['src/wambatic/stats/base.py']
    assert lines(audit_check, audit_jsonl, ALIAS_RULE, one_file) == [STATS_ALIAS]


@pytest.mark.parametrize(
    ('rules', 'paths', 'status', 'written'),
    [
        ([], [], 1, EVERY_HIT),
        (ACCEPTED_RULE, [], 0, []),
        ([], ['bin'], 0, []),
        (ALIAS_RULE, PACKAGE, 1, [STATS_ALIAS]),
    ],
)
def test_report_exits_1_only_when_a_hit_remains(
    audit_check: types.ModuleType,
    audit_jsonl: str,
    rules: list[str],
    paths: list[str],
    status: int,
    written: list[str],
) -> None:
    out = io.StringIO()
    assert audit_check.report(audit_jsonl, rules, paths, out) == status
    assert out.getvalue().splitlines() == written


def test_main_filters_the_checker_output(
    audit_check: types.ModuleType,
    audit_jsonl: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / audit_check.CHECKER).parent.mkdir(parents=True)
    (tmp_path / audit_check.CHECKER).touch()

    def run_checker(root: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout=audit_jsonl)

    monkeypatch.setattr(audit_check, 'run_checker', run_checker)
    argv = ['--rule', 'typing-deprecated-alias', '--path', 'src/wambatic']
    assert audit_check.main(argv, root=tmp_path) == 1
    assert capsys.readouterr().out.splitlines() == [STATS_ALIAS]
    assert audit_check.main(['--path', 'bin'], root=tmp_path) == 0
    assert capsys.readouterr().out == ''


@pytest.fixture
def errors() -> collections.abc.Iterator[list[str]]:
    messages: list[str] = []
    handler = loguru.logger.add(
        lambda message: messages.append(message.rstrip('\n')), format='{message}', level='ERROR'
    )
    yield messages
    loguru.logger.remove(handler)


def test_an_empty_submodule_exits_2_and_names_the_command(
    audit_check: types.ModuleType,
    errors: list[str],
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / '.agents').mkdir()
    assert audit_check.main([], root=tmp_path) == 2
    assert len(errors) == 1
    assert 'git submodule update --init' in errors[0]


def test_a_failing_checker_exits_2(
    audit_check: types.ModuleType,
    errors: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / audit_check.CHECKER).parent.mkdir(parents=True)
    (tmp_path / audit_check.CHECKER).touch()

    def run_checker(root: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 3, stdout='')

    monkeypatch.setattr(audit_check, 'run_checker', run_checker)
    assert audit_check.main([], root=tmp_path) == 2
    assert errors == [f'{audit_check.CHECKER} exited with status 3']
