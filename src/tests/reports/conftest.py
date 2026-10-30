import collections.abc
import pathlib

import playwright.sync_api
import pytest

# The Chromium that Claude Code's cloud environment preinstalls; Playwright's own is tried first.
PREINSTALLED_CHROMIUM = pathlib.Path('/opt/pw-browsers/chromium')


@pytest.fixture
def chromium() -> collections.abc.Iterator[playwright.sync_api.Browser]:
    """A launched Chromium. It is per test, not per session: Playwright's sync API runs an event
    loop while it is open, and computing the report (`asyncio.run`) cannot happen then, so tests
    ask for their report fixtures before this one."""
    with playwright.sync_api.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch()
        except playwright.sync_api.Error as first:
            if not PREINSTALLED_CHROMIUM.exists():
                pytest.skip(f'no Chromium can be launched: {str(first).splitlines()[0]}')
            try:
                browser = driver.chromium.launch(executable_path=str(PREINSTALLED_CHROMIUM))
            except playwright.sync_api.Error as second:
                pytest.skip(f'no Chromium can be launched: {str(second).splitlines()[0]}')
        yield browser
        browser.close()
