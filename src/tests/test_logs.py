import collections.abc

import loguru
import pytest

import gitstat.logs


@pytest.fixture(autouse=True)
def restore_logger() -> collections.abc.Iterator[None]:
    yield
    loguru.logger.remove()


def test_level_filters_messages(capsys: pytest.CaptureFixture[str]) -> None:
    gitstat.logs.configure_logging('WARNING')
    loguru.logger.info('quiet-info')
    loguru.logger.warning('loud-warning')
    err = capsys.readouterr().err
    assert 'loud-warning' in err
    assert 'quiet-info' not in err


def test_configure_twice_leaves_one_sink(capsys: pytest.CaptureFixture[str]) -> None:
    gitstat.logs.configure_logging('INFO')
    gitstat.logs.configure_logging('INFO')
    loguru.logger.info('only-once')
    assert capsys.readouterr().err.count('only-once') == 1
