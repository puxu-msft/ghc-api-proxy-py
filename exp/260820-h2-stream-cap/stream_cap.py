"""Candidate 2 under test: cap how many concurrent streams share one HTTP/2 connection.

The whole mechanism is one predicate. httpcore's pool decides where a queued request goes in `AsyncConnectionPool._assign_requests_to_connections`, and the only question it asks each existing connection is `can_handle_request(origin) and is_available()` (httpcore 1.0.9, `_async/connection_pool.py:305-308` -- that is the *only* call site of `is_available()` outside the delegating wrappers). Answer `False` once a connection already carries N requests and the pool falls through to its next case, "create a new connection".

Two things make this work at the right moment, and both are worth stating because getting either wrong produces a cap that silently does nothing:

- The count has to come from the *pool's* bookkeeping, not the connection's. httpcore's `AsyncHTTPConnection` does not know its own in-flight stream count until the TLS handshake has completed and an `AsyncHTTP2Connection` exists behind it; before that `is_available()` returns a flat `True` for any http2-capable connection (`_async/connection.py:175-185`). A burst of N requests arriving while the first connection is still handshaking would therefore all pile onto it. `pool._requests` already holds exactly the right fact -- every accepted-but-not-yet-finished request, with `.connection` naming its assignment -- and it is populated at assignment time.
- The count has to *drop* when a response finishes. It does: `PoolByteStream.aclose()` removes the request from `pool._requests` (`_async/connection_pool.py:409-417`), which is also where the pool re-runs assignment for anything still queued.

`is_available()` is called inside the pool's `_optional_thread_lock`, so reading `_requests` here needs no extra synchronisation.
"""

from __future__ import annotations

import ssl
import typing

import httpcore
import httpx

# All four are in `httpcore.__all__`, so this import line adds no private-API exposure. The private surface this file does depend on is listed in the report and is exactly: `pool._requests`, `AsyncPoolRequest.connection`, and `httpx.AsyncHTTPTransport._pool`.
from httpcore import AsyncConnectionInterface, Origin, Request, Response


class StreamCappedConnection(AsyncConnectionInterface):
    """Delegates every connection-interface method, and lies about one of them.

    A wrapper rather than a subclass of `AsyncHTTPConnection`: the surface it depends on is then exactly `AsyncConnectionInterface`, which is httpcore's own extension point for pluggable connections, instead of whatever `AsyncHTTPConnection.__init__` happens to accept this release.
    """

    def __init__(
        self,
        inner: AsyncConnectionInterface,
        pool: httpcore.AsyncConnectionPool,
        max_streams: int,
    ) -> None:
        self._inner = inner
        self._pool = pool
        self._max_streams = max_streams

    def assigned_request_count(self) -> int:
        return sum(1 for r in self._pool._requests if r.connection is self)

    # The one method whose answer we change.
    def is_available(self) -> bool:
        if not self._inner.is_available():
            return False
        return self.assigned_request_count() < self._max_streams

    # Straight delegation from here down.
    async def handle_async_request(self, request: Request) -> Response:
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

    def max_concurrent_requests(self) -> int:
        """Forwarded defensively against httpcore PR #1088.

        That PR (open since 2026-06-13, no maintainer response) adds `max_concurrent_requests()` to `AsyncConnectionInterface` and has the pool call it as `try: connection.max_concurrent_requests() except AttributeError: return 1`. A wrapper that only overrode `is_available()` would answer with the *wrapper's* missing attribute, the pool would fall back to 1, and every connection would silently be limited to one in-flight request -- no error, just a cap nobody asked for. Forwarding costs three lines; not forwarding costs a silent behaviour change on some future upgrade. The method does not exist in httpcore 1.0.9, hence the getattr.
        """
        inner = getattr(self._inner, "max_concurrent_requests", None)
        return inner() if inner is not None else self._max_streams

    def __repr__(self) -> str:
        return f"<StreamCappedConnection {self.info()}>"


class _StreamCapMixin:
    """The cap, factored out so it can be mixed into any of httpcore's three pool classes.

    `AsyncHTTPProxy` and `AsyncSOCKSProxy` both subclass `AsyncConnectionPool` and both override `create_connection`, so the same `super()` hop works for all three. This matters here because the production client passes `proxy=`, and httpx then builds `AsyncHTTPProxy` rather than `AsyncConnectionPool` -- a cap that only ever subclassed the plain pool would silently do nothing the day a proxy is configured. (Read from httpcore source; only the direct-connection path below is exercised by the PoC.)
    """

    _max_streams_per_connection: int

    def create_connection(self, origin: Origin) -> AsyncConnectionInterface:
        inner = super().create_connection(origin)  # type: ignore[misc]
        return StreamCappedConnection(inner, self, self._max_streams_per_connection)  # type: ignore[arg-type]


class StreamCappedPool(_StreamCapMixin, httpcore.AsyncConnectionPool):
    """A pool whose connections refuse a request once they already carry `max_streams_per_connection`."""

    def __init__(self, *args: typing.Any, max_streams_per_connection: int, **kwargs: typing.Any) -> None:
        super().__init__(*args, **kwargs)
        if max_streams_per_connection < 1:
            raise ValueError("max_streams_per_connection must be >= 1")
        self._max_streams_per_connection = max_streams_per_connection


class StreamCappedHTTPProxy(_StreamCapMixin, httpcore.AsyncHTTPProxy):
    """Same cap for the `proxy=` path. Untested by the PoC; included so the shape of the real integration is explicit rather than assumed."""

    def __init__(self, *args: typing.Any, max_streams_per_connection: int, **kwargs: typing.Any) -> None:
        super().__init__(*args, **kwargs)
        if max_streams_per_connection < 1:
            raise ValueError("max_streams_per_connection must be >= 1")
        self._max_streams_per_connection = max_streams_per_connection


def build_capped_client(
    *,
    ssl_context: ssl.SSLContext,
    max_streams_per_connection: int,
    max_connections: int | None = None,
    keepalive_expiry: float | None = None,
    timeout: float = 30.0,
) -> httpx.AsyncClient:
    """Wire the capped pool into httpx.

    `httpx.AsyncHTTPTransport` builds its own `httpcore.AsyncConnectionPool` in `__init__` and offers no seam to supply one, so the pool is replaced afterwards. That is the single httpx-private dependency of this approach; the alternative -- reimplementing `AsyncBaseTransport` -- means owning httpx's request/extension/timeout mapping, which is a far larger surface to keep correct.
    """
    transport = httpx.AsyncHTTPTransport(verify=ssl_context, http2=True)
    transport._pool = StreamCappedPool(
        ssl_context=ssl_context,
        max_connections=max_connections,
        keepalive_expiry=keepalive_expiry,
        http1=True,
        http2=True,
        max_streams_per_connection=max_streams_per_connection,
    )
    return httpx.AsyncClient(transport=transport, timeout=timeout)
