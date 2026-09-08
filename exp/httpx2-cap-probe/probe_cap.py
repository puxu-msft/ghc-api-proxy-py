"""Does moving the cap predicate from is_available() into can_handle_request() restore it under httpcore2?

Reproduces the burst case the API-delta report measured: one established capped connection,
six requests queued in a single assignment pass.
"""

import sys

import httpcore2
from httpcore2 import AsyncConnectionInterface, Origin
from httpcore2._async.connection_pool import AsyncPoolRequest


class FakeInner(AsyncConnectionInterface):
    """An established, multiplexing (h2-like) connection that is always available."""

    def __init__(self, origin: Origin) -> None:
        self._origin = origin

    def can_handle_request(self, origin: Origin) -> bool:
        return origin == self._origin

    def is_available(self) -> bool:
        return True

    def has_expired(self) -> bool:
        return False

    def is_idle(self) -> bool:
        return False

    def is_closed(self) -> bool:
        return False

    def is_connected(self) -> bool:
        return True

    def can_multiplex(self) -> bool:
        return True

    def info(self) -> str:
        return "FakeInner"


class Capped(AsyncConnectionInterface):
    def __init__(self, inner, pool, max_streams, *, cap_in_can_handle: bool) -> None:
        self._inner = inner
        self._pool = pool
        self._max = max_streams
        self._cap_in_can_handle = cap_in_can_handle

    def assigned_request_count(self) -> int:
        return sum(1 for r in self._pool._requests if r.connection is self)

    def is_available(self) -> bool:
        return self._inner.is_available() and self.assigned_request_count() < self._max

    def can_handle_request(self, origin: Origin) -> bool:
        if not self._inner.can_handle_request(origin):
            return False
        if self._cap_in_can_handle:
            return self.assigned_request_count() < self._max
        return True

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


def run(cap_in_can_handle: bool, burst: int, max_streams: int) -> list[int]:
    pool = httpcore2.AsyncConnectionPool(max_connections=100)
    origin = httpcore2.URL("http://example.invalid/").origin

    made: list[Capped] = []

    def create_connection(origin: Origin) -> AsyncConnectionInterface:
        conn = Capped(FakeInner(origin), pool, max_streams, cap_in_can_handle=cap_in_can_handle)
        made.append(conn)
        return conn

    pool.create_connection = create_connection

    # One already-established capped connection, as the report's probe did.
    established = create_connection(origin)
    pool._connections.append(established)

    for _ in range(burst):
        pool._requests.append(AsyncPoolRequest(httpcore2.Request("GET", "http://example.invalid/")))

    pool._assign_requests_to_connections()

    return [c.assigned_request_count() for c in made]


def main() -> int:
    print(f"httpcore2 {httpcore2.__version__}")
    failures = 0
    for cap_in_can_handle in (False, True):
        counts = run(cap_in_can_handle, burst=6, max_streams=2)
        respected = all(n <= 2 for n in counts)
        label = "cap in can_handle_request" if cap_in_can_handle else "cap in is_available only (current code)"
        print(f"  {label:42s} -> per-connection counts {counts}  cap respected = {respected}")
        if cap_in_can_handle and not respected:
            failures += 1
        if not cap_in_can_handle and respected:
            print("    UNEXPECTED: the baseline was supposed to reproduce the failure")
            failures += 1
    return failures


async def amain() -> int:
    return main()


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(amain()))
