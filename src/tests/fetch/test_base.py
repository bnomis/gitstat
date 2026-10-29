import dataclasses
import datetime

import pytest

import wambatic.fetch.base

NOW = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)


@pytest.mark.parametrize(
    'subject',
    [
        wambatic.fetch.base.Subject('user', 'octocat'),
        wambatic.fetch.base.Subject('org', 'github'),
        wambatic.fetch.base.Subject('repo', 'octocat', 'Hello-World'),
    ],
)
def test_valid_subjects_construct(subject: wambatic.fetch.base.Subject) -> None:
    assert subject.login


@pytest.mark.parametrize(
    ('kind', 'name'),
    [('repo', None), ('user', 'Hello-World'), ('org', 'Hello-World')],
)
def test_invalid_subjects_raise(kind: str, name: str | None) -> None:
    with pytest.raises(ValueError, match='subject'):
        wambatic.fetch.base.Subject(kind, 'octocat', name)  # type: ignore[arg-type]


def test_full_name_of_a_repo_subject() -> None:
    assert wambatic.fetch.base.Subject('repo', 'octocat', 'Hello-World').full_name == (
        'octocat/Hello-World'
    )


@pytest.mark.parametrize('kind', ['user', 'org'])
def test_full_name_of_an_owner_subject_raises(kind: str) -> None:
    with pytest.raises(ValueError, match='no repo name'):
        wambatic.fetch.base.Subject(kind, 'octocat').full_name  # type: ignore[arg-type]  # noqa: B018


def test_records_are_immutable() -> None:
    commit = wambatic.fetch.base.Commit('octocat/Hello-World', 'a' * 40, NOW, None, 1, 2, False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        commit.additions = 5  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        wambatic.fetch.base.Subject('user', 'octocat').login = 'x'  # type: ignore[misc]


def test_commit_records_merges() -> None:
    commit = wambatic.fetch.base.Commit('octocat/Hello-World', 'a' * 40, NOW, None, 0, 0, True)
    assert commit.is_merge


def test_resources_are_the_spec_names() -> None:
    assert wambatic.fetch.base.RESOURCES == {
        'commits',
        'issues',
        'pull_requests',
        'releases',
        'star_events',
        'workflow_runs',
    }


def test_built_resources_are_the_commits_only_and_a_subset_of_all_resources() -> None:
    assert wambatic.fetch.base.BUILT_RESOURCES <= wambatic.fetch.base.RESOURCES
    assert wambatic.fetch.base.BUILT_RESOURCES == frozenset({'commits'})
