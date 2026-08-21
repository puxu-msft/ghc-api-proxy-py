"""Which cap design actually holds under httpcore2's single-pass allocator?

Drives the real `AsyncConnectionPool.handle_async_request` loop with a fake connection, so the pool's own assignment, re-queue and close paths all run. Three designs are compared:

  is_available      the cap lives only in `is_available()` — what the repo does today
  can_handle        the cap also answers `can_handle_request()` — the first fix considered
  not_available     the cap also raises `ConnectionNotAvailable` at send time — httpcore's own idiom

What is measured, per design:

  peak            the most requests ever in flight at once on a single connection (the cap's whole purpose: a GOAWAY takes out everything in flight on one connection)
  conns           how many connections were created (amplification)
  closed_in_use   connections the pool closed while it still held requests assigned to them (a broken reservation invariant)
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator

import importlib
import os

# Which stack to drive. The cap has to hold on both: httpcore 1.0.9 is what ships today and
# httpcore2 is what the migration lands on.
httpcore2 = importlib.import_module(os.environ.get("PROBE_CORE", "httpcore2"))
AsyncConnectionInterface = httpcore2.AsyncConnectionInterface
ConnectionNotAvailable = httpcore2.ConnectionNotAvailable
Origin = httpcore2.Origin
Request = httpcore2.Request
Response = httpcore2.Response

MAX_STREAMS = 4


class Meter:
    """Shared tally of what actually happened, independent of what the pool believed."""

    def __init__(self) -> None:
        self.in_flight: dict[int, int] = {}
        self.peak = 0
        self.connections = 0
        self.closed_in_use = 0

    def enter(self, key: int) -> None:
        self.in_flight[key] = self.in_flight.get(key, 0) + 1
        self.peak = max(self.peak, self.in_flight[key])

    def leave(self, key: int) -> None:
        self.in_flight[key] -= 1


class FakeInner(AsyncConnectionInterface):
    """An established multiplexing connection that never refuses anything on its own."""

    def __init__(self, origin: Origin, meter: Meter, idle: bool) -> None:
        self._origin = origin
        self._meter = meter
        self._idle = idle

    def can_handle_request(self, origin: Origin) -> bool:
        return origin == self._origin

    def is_available(self) -> bool:
        return True

    def has_expired(self) -> bool:
        return False

    def is_idle(self) -> bool:
        return self._idle

    def is_closed(self) -> bool:
        return False

    def is_connected(self) -> bool:
        return True

    def can_multiplex(self) -> bool:
        return True

    def info(self) -> str:
        return "FakeInner"

    async def aclose(self) -> None:
        return None

    async def handle_async_request(self, request: Request) -> Response:
        key = id(self)

        async def body() -> AsyncIterator[bytes]:
            self._meter.enter(key)
            try:
                # Hold the stream open long enough for the whole burst to overlap.
                await asyncio.sleep(0.05)
                yield b"ok"
            finally:
                self._meter.leave(key)

        return Response(status=200, headers=[], content=body())


class Capped(AsyncConnectionInterface):
    def __init__(self, inner: FakeInner, pool, max_streams: int, design: str, meter: Meter) -> None:
        self._inner = inner
        self._pool = pool
        self._max = max_streams
        self._design = design
        self._meter = meter

    def assigned_request_count(self) -> int:
        return sum(1 for request in self._pool._requests if request.connection is self)

    def is_available(self) -> bool:
        return self._inner.is_available() and self.assigned_request_count() < self._max

    def can_handle_request(self, origin: Origin) -> bool:
        if not self._inner.can_handle_request(origin):
            return False
        if self._design == "can_handle":
            return self.assigned_request_count() < self._max
        return True

    async def handle_async_request(self, request: Request) -> Response:
        if self._design == "not_available" and self.assigned_request_count() > self._max:
            raise ConnectionNotAvailable()
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        if self.assigned_request_count() > 0:
            self._meter.closed_in_use += 1
        await self._inner.aclose()

    def has_expired(self) -> bool:
        return self._inner.has_expired()

    def is_idle(self) -> bool:
        return self._inner.is_idle()

    def is_closed(self) -> bool:
        return self._inner.is_closed()

    def is_connected(self) -> bool:
        return self._inner.is_connected()

    def can_multiplex(self) -> bool:
        return self._inner.can_multiplex()

    def info(self) -> str:
        return f"{self._inner.info()} [capped {self.assigned_request_count()}/{self._max}]"


async def run(design: str, burst: int, *, inner_idle: bool, max_connections: int) -> Meter:
    meter = Meter()
    pool = httpcore2.AsyncConnectionPool(max_connections=max_connections)

    def create_connection(origin: Origin) -> AsyncConnectionInterface:
        meter.connections += 1
        return Capped(FakeInner(origin, meter, inner_idle), pool, MAX_STREAMS, design, meter)

    pool.create_connection = create_connection

    async def one() -> None:
        response = await pool.handle_async_request(Request("GET", "http://example.invalid/"))
        async for _ in response.stream:
            pass
        await response.aclose()

    async with asyncio.TaskGroup() as group:
        for _ in range(burst):
            group.create_task(one())

    return meter


async def main() -> int:
    print(f"httpcore2 {httpcore2.__version__}, cap = {MAX_STREAMS} streams per connection\n")
    failures = 0
    for burst, max_connections in ((24, 100), (100, 100), (24, 2), (100, 4), (100, 8)):
        for inner_idle in (False, True):
            print(f"burst={burst} max_connections={max_connections} inner.is_idle()={inner_idle}")
            for design in ("is_available", "can_handle", "not_available"):
                meter = await run(design, burst, inner_idle=inner_idle, max_connections=max_connections)
                held = meter.peak <= MAX_STREAMS
                print(
                    f"  {design:14s} peak={meter.peak:<4d} conns={meter.connections:<4d}"
                    f" closed_in_use={meter.closed_in_use:<3d} cap held={held}"
                )
                if design == "not_available" and (not held or meter.closed_in_use):
                    failures += 1
            print()
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
