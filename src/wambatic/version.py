import importlib.metadata

UNKNOWN_VERSION = '0+unknown'


def package_version() -> str:
    """The installed wambatic's version, or `UNKNOWN_VERSION` when it has no package metadata
    (run from a source tree that was never installed)."""
    try:
        return importlib.metadata.version('wambatic')
    except importlib.metadata.PackageNotFoundError:
        return UNKNOWN_VERSION


VERSION: str = package_version()
