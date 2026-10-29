import os
import subprocess

import wambatic.fetch.errors


def resolve_token() -> str:
    """GITHUB_TOKEN from the environment, else `gh auth token`; raises AuthError if neither."""
    token = os.environ.get('GITHUB_TOKEN', '').strip()
    if token:
        return token
    try:
        result = subprocess.run(
            ['gh', 'auth', 'token'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError, subprocess.TimeoutExpired:
        raise wambatic.fetch.errors.AuthError(wambatic.fetch.errors.NO_TOKEN_MESSAGE) from None
    token = result.stdout.strip()
    if result.returncode == 0 and token:
        return token
    raise wambatic.fetch.errors.AuthError(wambatic.fetch.errors.NO_TOKEN_MESSAGE)


def redact(text: str, token: str) -> str:
    """`text` with every occurrence of `token` replaced by `***`."""
    if not token:
        return text
    return text.replace(token, '***')
