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


def test_info_lines_read_level_then_message_only(capsys: pytest.CaptureFixture[str]) -> None:
    gitstat.logs.configure_logging('INFO')
    loguru.logger.info('Synced it')
    loguru.logger.error('Broke {braces}')
    assert capsys.readouterr().err.splitlines() == ['INFO: Synced it', 'ERROR: Broke {braces}']


def test_warning_lines_use_the_short_format(capsys: pytest.CaptureFixture[str]) -> None:
    gitstat.logs.configure_logging('WARNING')
    loguru.logger.warning('careful')
    assert capsys.readouterr().err == 'WARNING: careful\n'


def test_debug_lines_keep_the_time_and_source_location(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gitstat.logs.configure_logging('DEBUG')
    loguru.logger.debug('detail')
    (line,) = capsys.readouterr().err.splitlines()
    assert line.endswith('- detail')
    assert 'DEBUG' in line
    assert 'test_logs:test_debug_lines_keep_the_time_and_source_location' in line
    assert line != 'DEBUG: detail'


def test_a_traceback_follows_the_short_line(capsys: pytest.CaptureFixture[str]) -> None:
    gitstat.logs.configure_logging('INFO')
    try:
        raise RuntimeError('boom')
    except RuntimeError:
        loguru.logger.exception('failed')
    err = capsys.readouterr().err
    assert err.startswith('ERROR: failed\n')
    assert 'Traceback' in err
    assert 'RuntimeError: boom' in err


def test_a_traceback_does_not_show_the_values_of_local_variables(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gitstat.logs.configure_logging('INFO')
    try:
        secret = 'sentinel-value-1234'
        raise RuntimeError(len(secret))
    except RuntimeError:
        loguru.logger.exception('failed')
    assert 'sentinel-value-1234' not in capsys.readouterr().err
