import subprocess

import hypothesis
import hypothesis.strategies
import pytest

import wambatic.fetch.auth
import wambatic.fetch.errors


def fake_run(
    monkeypatch: pytest.MonkeyPatch, *, stdout: str = '', stderr: str = '', code: int = 0
) -> None:
    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(['gh'], code, stdout, stderr)

    monkeypatch.setattr(subprocess, 'run', run)


def test_environment_token_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        pytest.fail('gh must not be called')

    monkeypatch.setattr(subprocess, 'run', fail)
    monkeypatch.setenv('GITHUB_TOKEN', '  env-token \n')
    assert wambatic.fetch.auth.resolve_token() == 'env-token'


def test_blank_environment_falls_through_to_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', '   ')
    fake_run(monkeypatch, stdout='gh-token\n')
    assert wambatic.fetch.auth.resolve_token() == 'gh-token'


@pytest.mark.parametrize(
    ('stdout', 'code'),
    [('secret-out\n', 1), ('  \n', 0)],
)
def test_gh_failure_or_empty_raises(
    monkeypatch: pytest.MonkeyPatch, stdout: str, code: int
) -> None:
    fake_run(monkeypatch, stdout=stdout, stderr='secret-err', code=code)
    with pytest.raises(wambatic.fetch.errors.AuthError) as info:
        wambatic.fetch.auth.resolve_token()
    assert 'secret-out' not in str(info.value)
    assert 'secret-err' not in str(info.value)
    assert str(info.value) == wambatic.fetch.errors.NO_TOKEN_MESSAGE


@pytest.mark.parametrize(
    'exc',
    [FileNotFoundError(), subprocess.TimeoutExpired(['gh'], 10)],
)
def test_gh_missing_or_timeout_raises(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    def run(*args: object, **kwargs: object) -> None:
        raise exc

    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(wambatic.fetch.errors.AuthError):
        wambatic.fetch.auth.resolve_token()


def test_redact_known_pair() -> None:
    assert wambatic.fetch.auth.redact('Bearer abc and abc', 'abc') == 'Bearer *** and ***'
    assert wambatic.fetch.auth.redact('text', '') == 'text'


TOKENS = hypothesis.strategies.text(alphabet='abc', min_size=1)
CONTEXT = hypothesis.strategies.text(alphabet='xyz *')


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(token=TOKENS, before=CONTEXT, after=CONTEXT)
def test_redact_removes_token(token: str, before: str, after: str) -> None:
    redacted = wambatic.fetch.auth.redact(f'{before}{token}{after}', token)
    assert token not in redacted
    assert redacted == f'{before}***{after}'


@hypothesis.settings(max_examples=20, deadline=10000)
@hypothesis.given(token=TOKENS, text=hypothesis.strategies.text(alphabet='xyz *'))
def test_redact_unchanged_without_token(token: str, text: str) -> None:
    assert wambatic.fetch.auth.redact(text, token) == text
