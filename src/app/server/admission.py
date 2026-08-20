"""How many client requests may be in flight at once.

Replaces byte-level memory accounting. Ruled 2026-08-19: bounding resident bytes is too fine-grained, and bounding concurrency reaches the same place — a request costs roughly what a request costs, and fifty of them is already past anything this proxy sees. Today's real traffic is 429 requests across a day, so the limit is a ceiling for a pathological client, not a throttle.

The waiting is the design, not a side effect. A request over the limit **waits**; it is not refused, not answered 429, and its connection is not closed. A client that gets a connection error retries and makes the overload worse, while one that is simply slow to be served does not — and this proxy's own client is Claude Code, which treats a dropped connection as a failed turn.

Gated in the ASGI app rather than at `accept()`. Both entry points reach it there — `start` owns its listener through `app.lifecycle`, `--fd` hands it to uvicorn, and only the app is common to both. It also means the bound counts *requests* rather than connections, which is what was ruled: with keep-alive one connection carries many, and it is the requests that cost.
"""

import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send

# What a request is, for this bound. A lifespan message is the server talking to itself.
GATED_SCOPES = frozenset({"http", "websocket"})

# The routes a supervisor polls, which the bound must never hold.
#
# Measured, not assumed: with the gate over the whole app, one occupied slot made `/health` wait for the inference request ahead of it. At `max_inflight` that is the saturated case — precisely when systemd or a monitor asks whether the process is still alive, and precisely when a queued answer reads as "dead". Answering these costs nothing and does no upstream work, so they are not what the bound is counting.
#
# Exact paths rather than a prefix: `/health` must not be spelt in a way that also exempts some future `/healthcheck-and-run-inference`. `/models` is deliberately absent — it is a client-facing call that can reach upstream, so it belongs inside the bound.
UNGATED_PATHS = frozenset({"/health", "/health/liveness", "/health/readiness", "/metrics"})


class InFlightLimit:
    """An ASGI gate that holds a request until a slot frees up.

    A semaphore rather than a counter and a condition: `acquire` already queues waiters in arrival order, so a request that has waited does not lose its place to one that just arrived.
    """

    def __init__(self, app: ASGIApp, *, max_inflight: int) -> None:
        self._app = app
        self._max_inflight = max_inflight
        # `None` disables the gate outright rather than standing a semaphore of unbounded size, so a disabled limit costs nothing per request.
        self._slots = asyncio.Semaphore(max_inflight) if max_inflight > 0 else None

    @property
    def max_inflight(self) -> int:
        return self._max_inflight

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._slots is None or scope["type"] not in GATED_SCOPES:
            await self._app(scope, receive, send)
            return
        if scope.get("path") in UNGATED_PATHS:
            await self._app(scope, receive, send)
            return
        async with self._slots:
            await self._app(scope, receive, send)


def limit_in_flight(app: ASGIApp, *, max_inflight: int) -> ASGIApp:
    """Wrap `app` so at most `max_inflight` client requests run at once. 0 disables."""
    return InFlightLimit(app, max_inflight=max_inflight)


__all__ = ["InFlightLimit", "limit_in_flight"]
