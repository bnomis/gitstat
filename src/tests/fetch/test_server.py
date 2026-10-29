import asyncio

import aiohttp

import tests.fixtures.fetch.server

Canned = tests.fixtures.fetch.server.Canned


def get_all(server: tests.fixtures.fetch.server.ReplayServer, count: int) -> list[int]:
    async def one(session: aiohttp.ClientSession) -> int:
        async with session.get(f'{server.url}/x') as response:
            return response.status

    async def scenario() -> list[int]:
        async with aiohttp.ClientSession() as session:
            return list(await asyncio.gather(*(one(session) for _ in range(count))))

    return asyncio.run(scenario())


def serve(
    routes: dict[tuple[str, str], list[Canned]], count: int, **kwargs: object
) -> tuple[list[int], tests.fixtures.fetch.server.ReplayServer]:
    async def scenario() -> tuple[list[int], tests.fixtures.fetch.server.ReplayServer]:
        async with tests.fixtures.fetch.server.ReplayServer(routes, **kwargs) as server:  # type: ignore[arg-type]
            statuses = await asyncio.to_thread(get_all, server, count)
            return statuses, server

    return asyncio.run(scenario())


def test_a_delayed_response_holds_requests_in_flight() -> None:
    routes = {('GET', '/x'): [Canned(200, {}, delay=0.1) for _ in range(3)]}
    statuses, server = serve(routes, 3)
    assert statuses == [200, 200, 200]
    assert server.max_in_flight == 3
    assert server.in_flight == 0


def test_undelayed_requests_are_not_held_together_for_long() -> None:
    routes = {('GET', '/x'): [Canned(200, {}) for _ in range(3)]}
    statuses, server = serve(routes, 3)
    assert statuses == [200, 200, 200]
    assert server.in_flight == 0


def test_the_default_responder_answers_when_no_canned_response_is_left() -> None:
    routes = {('GET', '/x'): [Canned(201)]}
    statuses, server = serve(
        routes, 2, default=lambda received: Canned(202, {'path': received.path})
    )
    assert sorted(statuses) == [201, 202]
    assert server.unexpected == []
