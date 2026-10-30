class UsageError(Exception):
    """A command line that parses but cannot be run; exit status 2."""


class OutputError(Exception):
    """A report that was built but could not be written; exit status 1."""


class ServeError(Exception):
    """A web app that cannot listen on its address; exit status 1."""
