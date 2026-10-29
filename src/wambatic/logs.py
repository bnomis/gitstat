import sys

import loguru

SHORT_FORMAT = '{level}: {message}'


def configure_logging(level: str) -> None:
    """Replace every loguru sink with one stderr sink at `level`.

    Below DEBUG's detail the lines read `LEVEL: message`; at DEBUG and under they keep loguru's
    default format, with time and source location. Tracebacks never show variable values
    (`diagnose=False`), which would print a token held in a local variable.
    """
    loguru.logger.remove()
    if loguru.logger.level(level).no <= loguru.logger.level('DEBUG').no:
        loguru.logger.add(sys.stderr, level=level, diagnose=False)
    else:
        loguru.logger.add(sys.stderr, level=level, format=SHORT_FORMAT, diagnose=False)
