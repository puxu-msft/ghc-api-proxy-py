"""How many client requests may be in flight at once.

Replaces byte-level memory accounting. Ruled 2026-08-19: bounding resident bytes is too
fine-grained, and bounding concurrency reaches the same place — a request costs roughly what a
request costs, and fifty of them is already past anything this proxy sees. Today's real traffic is
429 requests across a day, so the limit is a ceiling for a pathological client, not a throttle.

The waiting is the design, not a side effect. A request over the limit **waits**; it is not
refused, not answered 429, and its connection is not closed. A client that gets a connection error
retries and makes the overload worse, while one that is simply slow to be served does not — and
this proxy's own client is Claude Code, which treats a dropped connection as a failed turn.

Gated in the ASGI app rather than at `accept()`. Both entry points reach it there — `start` owns
its listener through `app.lifecycle`, `--fd` hands it to uvicorn, and only the app is common to
both. It also means the bound counts *requests* rather than connections, which is what was ruled:
with keep-alive one connection carries many, and it is the requests that cost.
"""

import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send

# What a request is, for this bound. A lifespan message is the server talking to itself.
GATED_SCOPES = frozenset({"http", "websocket"})


class InFlightLimit:
    """An ASGI gate that holds a request until a slot frees up.

    A semaphore rather than a counter and a condition: `acquire` already queues waiters in arrival
    order, so a request that has waited does not lose its place to one that just arrived.
    """

    def __init__(self, app: ASGIApp, *, max_inflight: int) -> None:
        self._app = app
        self._max_inflight = max_inflight
        # `None` disables the gate outright rather than standing a semaphore of unbounded size,
        # so a disabled limit costs nothing per request.
        self._slots = asyncio.Semaphore(max_inflight) if max_inflight > 0 else None

    @property
    def max_inflight(self) -> int:
        return self._max_inflight

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._slots is None or scope["type"] not in GATED_SCOPES:
            await self._app(scope, receive, send)
            return
        async with self._slots:
            await self._app(scope, receive, send)


def limit_in_flight(app: ASGIApp, *, max_inflight: int) -> ASGIApp:
    """Wrap `app` so at most `max_inflight` client requests run at once. 0 disables."""
    return InFlightLimit(app, max_inflight=max_inflight)


__all__ = ["InFlightLimit", "limit_in_flight"]
