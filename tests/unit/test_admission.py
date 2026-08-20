"""How many client requests run at once, and what happens to the rest.

This replaced byte-level memory accounting on 2026-08-19. The assertion that matters is not that
the limit holds — a semaphore holds — but that a request over it **waits**: it is not refused, not
answered 429, and its connection is not closed. A client that gets a connection error retries and
makes the overload worse; this proxy's own client treats a dropped connection as a failed turn.
"""

import asyncio

import pytest
from starlette.types import Receive, Scope, Send

from app.server.admission import InFlightLimit


class _Counting:
    """An app that reports how many calls are inside it at once."""

    def __init__(self) -> None:
        self.concurrent = 0
        self.peak = 0
        self.calls = 0
        self.release = asyncio.Event()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.calls += 1
        self.concurrent += 1
        self.peak = max(self.peak, self.concurrent)
        try:
            await self.release.wait()
        finally:
            self.concurrent -= 1


def _http() -> Scope:
    return {"type": "http", "method": "POST", "path": "/v1/messages"}


async def _noop_receive() -> dict[str, object]:
    return {"type": "http.request"}


async def _noop_send(message: object) -> None:
    del message


@pytest.mark.asyncio
async def test_requests_over_the_limit_wait_rather_than_being_refused() -> None:
    """The whole point. Nothing is raised, nothing is answered, nothing is closed — they queue."""
    app = _Counting()
    gate = InFlightLimit(app, max_inflight=2)

    running = [
        asyncio.create_task(gate(_http(), _noop_receive, _noop_send)) for _ in range(5)
    ]
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert app.peak == 2, "the limit did not hold"
    assert app.calls == 2, "a request over the limit reached the app instead of waiting"
    assert not any(task.done() for task in running), "a waiting request was resolved early"

    app.release.set()
    await asyncio.gather(*running)
    assert app.calls == 5, "a waiting request was dropped rather than served"


@pytest.mark.asyncio
async def test_a_freed_slot_admits_the_next_waiter() -> None:
    app = _Counting()
    gate = InFlightLimit(app, max_inflight=1)

    first = asyncio.create_task(gate(_http(), _noop_receive, _noop_send))
    second = asyncio.create_task(gate(_http(), _noop_receive, _noop_send))
    await asyncio.sleep(0)
    assert app.calls == 1

    app.release.set()
    await asyncio.gather(first, second)
    assert app.calls == 2


@pytest.mark.asyncio
async def test_zero_disables_the_gate() -> None:
    """0 means unbounded, not "admit nothing" — the difference is a hung proxy."""
    app = _Counting()
    app.release.set()
    gate = InFlightLimit(app, max_inflight=0)

    await asyncio.gather(*(gate(_http(), _noop_receive, _noop_send) for _ in range(8)))

    assert app.calls == 8


@pytest.mark.asyncio
async def test_lifespan_is_not_gated() -> None:
    """Startup is the server talking to itself; holding it behind a request slot would deadlock."""
    app = _Counting()
    gate = InFlightLimit(app, max_inflight=1)

    held = asyncio.create_task(gate(_http(), _noop_receive, _noop_send))
    await asyncio.sleep(0)

    app.release.set()
    await gate({"type": "lifespan"}, _noop_receive, _noop_send)
    await held
    assert app.calls == 2


@pytest.mark.asyncio
async def test_a_slot_is_released_when_the_request_fails() -> None:
    """A raising request must not leak its slot, or the proxy wedges after enough errors."""

    async def failing(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive, send
        raise RuntimeError("boom")

    gate = InFlightLimit(failing, max_inflight=1)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await gate(_http(), _noop_receive, _noop_send)

    served = _Counting()
    served.release.set()
    await InFlightLimit(served, max_inflight=1)(_http(), _noop_receive, _noop_send)
    assert served.calls == 1
