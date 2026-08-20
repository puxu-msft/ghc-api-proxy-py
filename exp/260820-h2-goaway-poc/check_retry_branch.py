"""Unit-level check of httpcore's own retry-vs-fatal branch in AsyncHTTP2Connection._receive_events.

This does NOT go over the network. It instantiates httpcore's real `AsyncHTTP2Connection` class (the exact class from the production traceback), directly sets its private `_connection_terminated` attribute to a `ConnectionTerminated` event with a chosen `last_stream_id`, and calls the real `_receive_events()` coroutine to see which branch it takes for a given `stream_id`. This isolates the branch in httpcore/_async/http2.py:342-355 from network/timing concerns, complementing the full end-to-end network PoC in run_poc.py.

Evidence tier: this is real code execution against httpcore's own class, not a re-implementation or a mock of its logic -- but it manipulates a private attribute directly rather than driving it via the network, so treat it as a narrower, whitebox confirmation of the wider network-level finding, not a replacement for it.

SCOPE LIMIT (added 2026-08-20 after independent review, finding F8). This check answers exactly one question: *which branch does `_receive_events` take?* It does NOT answer *what happens to a stream in production*, because the production entry point is `_receive_stream_event`, which consumes already-queued events first:

    while not self._events.get(stream_id):
        await self._receive_events(request, stream_id)

When that queue is non-empty, `_receive_events` is never called and the termination check never fires. Measured consequence: a stream whose `DataReceived`+`StreamEnded` landed in the same socket read *ahead of* the GOAWAY completes normally even under the sentinel `last_stream_id`. Calling `_receive_events` directly, as this file does, bypasses that queue -- so these four results must not be generalised into "there is no path that reads a stream to completion". They were, once, and that conclusion was wrong.

Run: /home/xp/src/ghc-api-proxy-py/.venv/bin/python check_retry_branch.py
"""

from __future__ import annotations

import asyncio

import h2.events
import httpcore
from httpcore._async.http2 import AsyncHTTP2Connection


class FakeStream:
    """Never actually read/written in this check; _receive_events short-circuits before touching the network once _connection_terminated is set."""

    async def read(self, n, timeout=None):
        raise AssertionError("should not be called in this unit check")

    async def write(self, data, timeout=None):
        pass

    async def aclose(self):
        pass


async def check(label: str, last_stream_id: int, stream_id: int) -> None:
    conn = AsyncHTTP2Connection(
        origin=httpcore.Origin(b"https", b"example.invalid", 443),
        stream=FakeStream(),
    )
    req = httpcore.Request("GET", "https://example.invalid/")

    event = h2.events.ConnectionTerminated()
    event.error_code = 0
    event.last_stream_id = last_stream_id
    conn._connection_terminated = event

    try:
        await conn._receive_events(req, stream_id=stream_id)
        print(f"{label}: no exception raised (unexpected)")
    except Exception as exc:
        qualname = f"{type(exc).__module__}.{type(exc).__qualname__}"
        print(f"{label}: {qualname}: {exc!r}")


async def main() -> None:
    # Labels corrected 2026-08-20 after review: RFC 9113 sec 6.8 says streams at or below the last stream identifier "might have been processed in some way" -- not that the peer accepted them and will finish them. Nothing in this check makes a server accept anything.
    await check("last_stream_id=2**31-1 (RFC 9113 sec 6.8 sentinel), stream_id=1", 2**31 - 1, 1)
    await check("last_stream_id=0 (legitimate 'nothing processed yet'), stream_id=1", 0, 1)
    await check("last_stream_id=1 (truthy), stream_id=3 (above it: peer will not process)", 1, 3)
    await check("last_stream_id=1 (truthy), stream_id=1 (at it: peer might have processed)", 1, 1)


if __name__ == "__main__":
    asyncio.run(main())
