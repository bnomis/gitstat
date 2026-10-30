import asyncio
import collections.abc
import pathlib
import socket
import threading

import playwright.sync_api
import pytest
import uvicorn

import tests.conftest
import tests.fixtures.fetch.server
import tests.fixtures.fetch.upstream
import tests.fixtures.reports
import wambatic.fetch.cache
import wambatic.reports.web
import wambatic.settings

pytestmark = pytest.mark.browser

SMALL_ORG_REPOS = 6
HISTORY_DELAY = 0.3
STATES = [
    'Waiting for another sync to finish',
    'Listing repositories',
    'Syncing repositories',
    'Done, loading the report',
]
EVERY_CHART_DRAWN = """() => {
  const plots = [...document.querySelectorAll('.plot')];
  return plots.length > 0 && plots.every((plot) => plot.querySelector('.main-svg'));
}"""
PROGRESS_SHOWN = """(states) => {
  const element = document.getElementById('state');
  return element !== null && states.includes(element.textContent);
}"""


@pytest.fixture
def running_server(
    monkeypatch: pytest.MonkeyPatch, make_client: tests.conftest.MakeClient, tmp_path: pathlib.Path
) -> collections.abc.Iterator[str]:
    """The base URL of a real uvicorn server for an empty cache and a fake GitHub with a small
    org whose history responses are slow, so the progress page is shown for a moment."""
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    upstream = tests.fixtures.fetch.upstream.large_org(SMALL_ORG_REPOS)
    upstream.history_delay = HISTORY_DELAY
    settings = wambatic.settings.load_settings(None, {'fetch': {'max_age': '0s'}})
    cache = wambatic.fetch.cache.Cache.open(tmp_path / 'web' / 'cache.sqlite3')
    sock = socket.create_server(('127.0.0.1', 0))
    config_holder: list[uvicorn.Server] = []
    started = threading.Event()

    async def serve() -> None:
        async with tests.fixtures.fetch.server.ReplayServer({}, upstream.respond) as replay:
            tests.fixtures.reports.install_replay(monkeypatch, make_client, replay)
            app = wambatic.reports.web.make_app(settings, cache)
            config = uvicorn.Config(
                app,
                loop='asyncio',
                lifespan='on',
                log_config=None,
                access_log=False,
                log_level='warning',
            )
            server = uvicorn.Server(config)
            config_holder.append(server)
            started.set()
            await server.serve(sockets=[sock])

    thread = threading.Thread(target=lambda: asyncio.run(serve()), daemon=True)
    thread.start()
    assert started.wait(10)
    yield f'http://127.0.0.1:{sock.getsockname()[1]}'
    config_holder[0].should_exit = True
    thread.join(10)
    sock.close()
    cache.close()


def test_the_progress_page_becomes_the_report_with_every_chart_drawn(
    running_server: str, chromium: playwright.sync_api.Browser
) -> None:
    context = chromium.new_context()
    try:
        page = context.new_page()
        foreign: list[str] = []
        problems: list[str] = []

        def route(route: playwright.sync_api.Route) -> None:
            if route.request.url.startswith(running_server):
                route.continue_()
            else:
                foreign.append(route.request.url)
                route.abort()

        page.route('**/*', route)
        page.on('console', lambda m: problems.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: problems.append(str(e)))
        response = page.goto(f'{running_server}/report?target=org:octo-org')
        assert response is not None
        assert response.status == 202
        page.wait_for_function(PROGRESS_SHOWN, arg=STATES)
        page.wait_for_selector('#activity-commits .main-svg', timeout=60000)
        page.wait_for_function(EVERY_CHART_DRAWN)
        assert '&job=' in page.url
        assert foreign == []
        assert problems == []
    finally:
        context.close()
