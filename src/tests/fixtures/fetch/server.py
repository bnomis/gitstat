import asyncio
import collections.abc
import dataclasses
import types

import aiohttp.test_utils
import aiohttp.web
import pytest


@dataclasses.dataclass(frozen=True, slots=True)
class Canned:
    status: int = 200
    body: object | None = None
    headers: dict[str, str] = dataclasses.field(default_factory=dict)
    delay: float = 0.0


@dataclasses.dataclass(frozen=True, slots=True)
class Received:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    json: object | None


class ReplayServer:
    """Serves canned responses in order per `(method, path)` and records each request.

    A request with no canned response left goes to `default`, when given, which answers from the
    request itself. A response with a `delay` waits that many real seconds, so a test can hold
    requests in flight; `max_in_flight` is the most requests ever in flight at once.
    """

    def __init__(
        self,
        routes: dict[tuple[str, str], list[Canned]],
        default: collections.abc.Callable[[Received], Canned] | None = None,
    ) -> None:
        self.routes = {key: list(responses) for key, responses in routes.items()}
        self.default = default
        self.received: list[Received] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.unexpected: list[str] = []
        self.server: aiohttp.test_utils.TestServer | None = None

    @property
    def url(self) -> str:
        assert self.server is not None
        return str(self.server.make_url('')).rstrip('/')

    async def handle(self, request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        body = await request.read()
        received = Received(
            request.method,
            request.path,
            dict(request.query),
            dict(request.headers),
            await request.json() if body else None,
        )
        self.received.append(received)
        queue = self.routes.get((request.method, request.path))
        if queue:
            canned = queue.pop(0)
        elif self.default is not None:
            canned = self.default(received)
        else:
            self.unexpected.append(f'{request.method} {request.path}')
            return aiohttp.web.Response(status=599)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(canned.delay)
        finally:
            self.in_flight -= 1
        if canned.body is None:
            return aiohttp.web.Response(status=canned.status, headers=canned.headers)
        return aiohttp.web.json_response(canned.body, status=canned.status, headers=canned.headers)

    async def __aenter__(self) -> ReplayServer:
        app = aiohttp.web.Application()
        app.router.add_route('*', '/{tail:.*}', self.handle)
        self.server = aiohttp.test_utils.TestServer(app)
        await self.server.start_server()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> None:
        assert self.server is not None
        await self.server.close()
        if exc is None and self.unexpected:
            pytest.fail(f'requests with no canned response left: {self.unexpected}')
