"""Cap how many concurrent requests share one upstream connection.

HTTP/2 multiplexes every concurrent request onto one connection, so one connection-level event is one blast radius: on 2026-08-20 a single graceful-shutdown GOAWAY ended four in-flight streams at the same instant. Capping the streams per connection spreads them, so such an event takes down at most `max_streams_per_connection` of them.

This is **not** the same choice as turning HTTP/2 off. A capped connection is still HTTP/2 — binary framing, HPACK, stream-level resets that do not kill the connection, and whatever the upstream edge does differently for h2. `upstream_transport.http2: false` abandons the protocol; this bounds it. The sibling service made the same distinction and picked h2 with a cap rather than HTTP/1.1 (`copilot-api-js@b5892380f`, 2026-07-22, which measured batch failures falling from 57.6% to 5.9%).

The mechanism is one predicate asked in two places. httpcore's pool decides where a queued request goes in `_assign_requests_to_connections`, and what it asks each existing connection is `can_handle_request(origin) and is_available()`. Answering `is_available()` with `False` once a connection already carries N requests makes the pool fall through to "create a new connection".

That alone was the whole mechanism until httpcore2. **httpcore2 2.3.0 rewrote the assignment loop to snapshot the reusable connections once per pass** (PR #974) instead of re-deriving them for each queued request, so `is_available()` is asked once and a pass that releases several queued requests at once can put all of them on one connection. It does not fail while requests arrive one at a time — each arrival runs its own pass with one request queued — but it fails completely once the pool saturates and a finishing response frees several at once. Measured against the real pool loop with `max_connections=100` and a cap of 1: a burst of 500 put **400** requests on a single connection, which is the blast radius this module exists to bound. The probe is `.dev/exp/httpx2-migration/probe_cap_designs.py`.

So the cap is also enforced where the pool cannot snapshot it away: `handle_async_request` refuses over-cap work with `ConnectionNotAvailable`, which is httpcore's own way for a connection to say it accepted an assignment it cannot serve — `AsyncHTTP2Connection` raises exactly this when its state will not take another stream. The pool answers by clearing the assignment and re-queueing (`connection_pool.py`), so nothing is lost and no extra socket is opened; the cost is re-running assignment for that request. At the settings above the same burst of 500 cost 1309 extra assignment rounds and held the cap at 1. Refusing in `can_handle_request` instead was measured and rejected: it pushes the request into the pool's "close an idle connection to make room" branch, which closes connections that still have requests assigned to them.

Two things make the count right, and getting either wrong produces a cap that silently does nothing:

- **The count comes from the pool, not the connection.** `AsyncHTTPConnection` does not know its own in-flight stream count until the TLS handshake completes and an `AsyncHTTP2Connection` exists behind it; before that `is_available()` is a flat `True` for any http2-capable connection. A burst arriving while the first connection is still handshaking would all pile onto it. `pool._requests` holds the right fact and is populated at assignment time.
- **The count drops when a response finishes.** `PoolByteStream.aclose()` removes the request from `pool._requests`, which is also where the pool re-runs assignment for anything still queued.

`is_available()` is called inside the pool's own lock, so reading `_requests` needs no extra synchronisation.

**Private surface, named so an upgrade knows what to check.** `pool._requests` and the `.connection` on its elements. Both have existed since httpcore's 0.14 redesign (2021-11-11), survived the 2024 pool rewrite (#880) that renamed the element class around them, and survived the fork to httpcore2. Neither is documented, and httpcore's CHANGELOG has never once mentioned the pool internals — including in the release that rewrote them — so **upgrading httpcore means diffing its source, not reading its release notes**. The 2.3.0 snapshot above is exactly that: a CHANGELOG line about loop complexity that silently disabled this cap. `tests/unit/upstream/test_stream_cap.py` carries a structural guard that fails loudly if either name moves, and a saturated-burst case that fails if the cap stops being enforced; the structural guard alone stayed green right through the snapshot change.
"""

from typing import Any, Protocol, cast

import httpx2
from httpcore2 import (
    AsyncConnectionInterface,
    ConnectionNotAvailable,
    Origin,
    Request,
    Response,
)


class _PoolWithRequests(Protocol):
    """The two private names this module reads, stated as a type so the guard test can name them too."""

    _requests: list[Any]


class StreamCappedConnection(AsyncConnectionInterface):
    """Delegates every connection-interface method, and changes the answer to one of them.

    A wrapper rather than a subclass of `AsyncHTTPConnection`: what it then depends on is exactly `AsyncConnectionInterface`, which is httpcore's own extension point for pluggable connections, instead of whatever `AsyncHTTPConnection.__init__` happens to accept this release.
    """

    def __init__(
        self,
        inner: AsyncConnectionInterface,
        pool: _PoolWithRequests,
        max_streams: int,
    ) -> None:
        self._inner = inner
        self._pool = pool
        self._max_streams = max_streams

    def assigned_request_count(self) -> int:
        """How many accepted requests the pool has assigned to this connection right now."""
        # The private name is the whole point of `_PoolWithRequests`, whose docstring says so; the module header says which httpcore releases it has survived and what an upgrade has to check.
        return sum(1 for request in self._pool._requests if request.connection is self)  # pyright: ignore[reportPrivateUsage]

    def is_available(self) -> bool:
        """The one answer that differs: full means unavailable, however the inner connection feels about it."""
        if not self._inner.is_available():
            return False
        return self.assigned_request_count() < self._max_streams

    async def handle_async_request(self, request: Request) -> Response:
        if self.assigned_request_count() > self._max_streams:
            # Over the cap because the pool assigned past it, which httpcore2 can do within one assignment pass. `>` not `>=`: this request is already in `pool._requests` pointing here, so the count includes it, and a count equal to the cap is the last one allowed.
            #
            # The two predicates have to agree on where the cap is, or the pool livelocks. `is_available()` says a connection at the cap takes nothing more; refusing at `>=` here would refuse the request that brings it *to* the cap, while `is_available()` still called that connection free — so the pool would assign it, get refused, re-queue, and assign it right back, forever. Measured: swapping this one character hangs the burst test below rather than failing it.
            raise ConnectionNotAvailable()
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()

    def info(self) -> str:
        return f"{self._inner.info()} [capped {self.assigned_request_count()}/{self._max_streams}]"

    def can_handle_request(self, origin: Origin) -> bool:
        return self._inner.can_handle_request(origin)

    def has_expired(self) -> bool:
        return self._inner.has_expired()

    def is_idle(self) -> bool:
        return self._inner.is_idle()

    def is_closed(self) -> bool:
        return self._inner.is_closed()

    def is_connected(self) -> bool:
        """Added by httpcore2. The base answers `not is_closed()`, which is wrong for a connection still in NEW state, and the pool uses it to drop connections whose request was cancelled before the handshake finished — a branch that would never fire for a capped one."""
        return self._inner.is_connected()

    def can_multiplex(self) -> bool:
        """Added by httpcore2. The base answers `False`, which would have the pool treat an established HTTP/2 connection as if it served one request at a time."""
        return self._inner.can_multiplex()

    def max_concurrent_requests(self) -> int:
        """Forwarded defensively against httpcore PR #1088.

        That PR adds `max_concurrent_requests()` to `AsyncConnectionInterface` and has the pool call it as `try: connection.max_concurrent_requests() except AttributeError: return 1`. A wrapper that only overrode `is_available()` would answer with its own missing attribute, the pool would fall back to 1, and every connection would silently be limited to a single in-flight request — no error, just a cap nobody asked for. Three lines against a future silent behaviour change. The method does not exist in httpcore 1.0.9, hence the lookup.
        """
        inner = getattr(self._inner, "max_concurrent_requests", None)
        return cast(int, inner()) if inner is not None else self._max_streams

    def __repr__(self) -> str:
        return f"<StreamCappedConnection {self.info()}>"


def cap_streams_per_connection(client: httpx2.AsyncClient, max_streams: int) -> None:
    """Make the client's pool refuse to put more than `max_streams` requests on one connection.

    Patches the live pool's `create_connection` rather than substituting a pool subclass, and that is the point: `httpx.AsyncHTTPTransport.__init__` builds its pool with ten-odd settings — `max_keepalive_connections`, `retries`, `socket_options`, `local_address`, `uds` among them — and a replacement pool has to reproduce every one of them. Anything forgotten is lost silently and stays lost as httpx gains settings. Wrapping the object httpx already configured keeps all of it, and works the same for `AsyncHTTPProxy` and `AsyncSOCKSProxy`, which are pools too and would otherwise need their own subclass each. That matters here: this client is built with `proxy=` when one is configured, and a cap that only knew about the plain pool would do nothing from the day a proxy was set.

    Raises rather than silently doing nothing if the transport is not the one that carries a pool — a mock transport in a test, say. A cap that quietly is not there is the failure this whole module is written against.
    """
    if max_streams < 1:
        raise ValueError(f"max_streams must be >= 1, got {max_streams}")

    # Mounted transports as well as the default one. A client built with explicit `mounts` — which is how the composition root keeps `HTTP_PROXY` / `HTTPS_PROXY` working while handing httpx a transport of its own — routes proxied traffic through them and not through `_transport`, so capping only the default would leave the cap doing nothing for exactly the destinations a proxy serves.
    #
    # Once per pool, not once per name that reaches it. The composition root deliberately gives every `NO_PROXY` rule the *same* direct transport, and that transport is usually `_transport` too, so a plain walk wraps one pool as many times as it is mentioned. The extra layers do not change the cap — the pool assigns each request to the outermost wrapper, so the inner ones count zero and only delegate — but they nest `create_connection` calls one deep per mention, and a legitimate `NO_PROXY` list long enough (measured: 1100 rules) raises `RecursionError` before any connection is attempted.
    #
    # Keyed by `id()` rather than put in a set, because identity is the property meant here and a set would spell it as equality. Transports have no `__eq__` today, so the two agree; a future httpx that gave them value equality *and* a matching `__hash__` would have a set fold two distinct pools into one and leave the second uncapped — silently, which is the failure this whole module is written against. (With `__eq__` alone the set would raise instead, which is at least loud.) Every transport is kept alive by `client` for the duration, so the ids cannot be reused underneath us.
    pools_to_cap: dict[int, httpx2.AsyncBaseTransport] = {}
    # Private on both names, and httpx offers no public way to reach either. The comment above says why both are needed; there is no reading of this module under which it stops touching them.
    for transport in (client._transport, *client._mounts.values()):  # pyright: ignore[reportPrivateUsage]
        if transport is not None:
            pools_to_cap.setdefault(id(transport), transport)
    for transport in pools_to_cap.values():
        _cap_one(transport, max_streams)


def _cap_one(transport: httpx2.AsyncBaseTransport, max_streams: int) -> None:
    pool = getattr(transport, "_pool", None)
    if pool is None:
        raise TypeError(f"{type(transport).__name__} carries no connection pool to cap")

    inner_create = pool.create_connection

    def create_connection(origin: Origin) -> AsyncConnectionInterface:
        return StreamCappedConnection(inner_create(origin), cast(_PoolWithRequests, pool), max_streams)

    pool.create_connection = create_connection
