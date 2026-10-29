import sys

import loguru


def configure_logging(level: str) -> None:
    """Replace every loguru sink with one stderr sink at `level`."""
    loguru.logger.remove()
    loguru.logger.add(sys.stderr, level=level)
