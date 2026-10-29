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


@dataclasses.dataclass(frozen=True, slots=True)
class Received:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    json: object | None


class ReplayServer:
    """Serves canned responses in order per `(method, path)` and records each request."""

    def __init__(self, routes: dict[tuple[str, str], list[Canned]]) -> None:
        self.routes = {key: list(responses) for key, responses in routes.items()}
        self.received: list[Received] = []
        self.unexpected: list[str] = []
        self.server: aiohttp.test_utils.TestServer | None = None

    @property
    def url(self) -> str:
        assert self.server is not None
        return str(self.server.make_url('')).rstrip('/')

    async def handle(self, request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        body = await request.read()
        self.received.append(
            Received(
                request.method,
                request.path,
                dict(request.query),
                dict(request.headers),
                await request.json() if body else None,
            )
        )
        queue = self.routes.get((request.method, request.path))
        if not queue:
            self.unexpected.append(f'{request.method} {request.path}')
            return aiohttp.web.Response(status=599)
        canned = queue.pop(0)
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
