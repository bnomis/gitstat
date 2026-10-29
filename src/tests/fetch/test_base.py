import dataclasses
import datetime

import pytest

import gitstat.fetch.base

NOW = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)


@pytest.mark.parametrize(
    'subject',
    [
        gitstat.fetch.base.Subject('user', 'octocat'),
        gitstat.fetch.base.Subject('org', 'github'),
        gitstat.fetch.base.Subject('repo', 'octocat', 'Hello-World'),
    ],
)
def test_valid_subjects_construct(subject: gitstat.fetch.base.Subject) -> None:
    assert subject.login


@pytest.mark.parametrize(
    ('kind', 'name'),
    [('repo', None), ('user', 'Hello-World'), ('org', 'Hello-World')],
)
def test_invalid_subjects_raise(kind: str, name: str | None) -> None:
    with pytest.raises(ValueError, match='subject'):
        gitstat.fetch.base.Subject(kind, 'octocat', name)  # type: ignore[arg-type]


def test_full_name_of_a_repo_subject() -> None:
    assert gitstat.fetch.base.Subject('repo', 'octocat', 'Hello-World').full_name == (
        'octocat/Hello-World'
    )


@pytest.mark.parametrize('kind', ['user', 'org'])
def test_full_name_of_an_owner_subject_raises(kind: str) -> None:
    with pytest.raises(ValueError, match='no repo name'):
        gitstat.fetch.base.Subject(kind, 'octocat').full_name  # type: ignore[arg-type]  # noqa: B018


def test_records_are_immutable() -> None:
    commit = gitstat.fetch.base.Commit('octocat/Hello-World', 'a' * 40, NOW, None, 1, 2, False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        commit.additions = 5  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        gitstat.fetch.base.Subject('user', 'octocat').login = 'x'  # type: ignore[misc]


def test_commit_records_merges() -> None:
    commit = gitstat.fetch.base.Commit('octocat/Hello-World', 'a' * 40, NOW, None, 0, 0, True)
    assert commit.is_merge


def test_resources_are_the_spec_names() -> None:
    assert gitstat.fetch.base.RESOURCES == {
        'commits',
        'issues',
        'pull_requests',
        'releases',
        'star_events',
        'workflow_runs',
    }


def test_built_resources_are_the_commits_only_and_a_subset_of_all_resources() -> None:
    assert gitstat.fetch.base.BUILT_RESOURCES <= gitstat.fetch.base.RESOURCES
    assert gitstat.fetch.base.BUILT_RESOURCES == frozenset({'commits'})
