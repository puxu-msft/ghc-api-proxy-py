"""Capping how many concurrent requests share one upstream connection.

The predicate is small; what these mostly guard is the private surface underneath it. `pool._requests` and the `.connection` on its elements are undocumented httpcore internals, and if either moves the cap does not fail — it counts zero, answers "available" forever, and becomes a decoration that caps nothing. So the structural guard below matters more than it looks: it is the only thing between a silent httpcore rename and a protection everyone believes is on.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast

import httpcore2
import httpx2
import pytest

from app.config.schema import ProxyConfig
from app.server.composition import build_http_client, transport_options
from app.upstream.stream_cap import StreamCappedConnection, cap_streams_per_connection


class FakeInner(httpcore2.AsyncConnectionInterface):
    """Whatever httpcore would have created, reduced to the two answers the wrapper reads."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available

    def can_handle_request(self, origin: httpcore2.Origin) -> bool:
        return True

    def has_expired(self) -> bool:
        return False

    def is_idle(self) -> bool:
        return True

    def is_closed(self) -> bool:
        return False

    def info(self) -> str:
        return "fake"

    async def aclose(self) -> None:
        return None


class FakePool:
    """Only the bookkeeping the wrapper reads, so a test can put a connection at any occupancy."""

    def __init__(self) -> None:
        self._requests: list[Any] = []

    def occupy(self, connection: object, count: int) -> None:
        for _ in range(count):
            self._requests.append(type("PoolRequest", (), {"connection": connection})())


def capped(max_streams: int, *, inner: FakeInner | None = None) -> tuple[StreamCappedConnection, FakePool]:
    pool = FakePool()
    connection = StreamCappedConnection(inner or FakeInner(), pool, max_streams)  # pyright: ignore[reportArgumentType]
    return connection, pool


# --------------------------------------------------------------------------------------
# The guard that has to exist, because this failure mode is silent
# --------------------------------------------------------------------------------------


def test_httpcore_still_exposes_the_bookkeeping_the_cap_counts() -> None:
    """If httpcore renames either of these, the cap degrades into a decoration that caps nothing.

    Nothing else notices: `assigned_request_count()` would return 0 for every connection, `is_available()` would answer True forever, and every request would go back to sharing one connection — with no exception, no log line, and a config key still claiming the protection is on. httpcore's CHANGELOG has never mentioned its pool internals, including in the release that rewrote them, so an upgrade will not tell you either. This test is the notification.
    """
    pool = httpcore2.AsyncConnectionPool()
    assert isinstance(pool._requests, list), "httpcore.AsyncConnectionPool no longer keeps `_requests`"  # pyright: ignore[reportPrivateUsage]

    # The element type is only reachable through the module; the implementation deliberately does not import it, but a test may name it to assert its shape.
    from httpcore2._async.connection_pool import AsyncPoolRequest

    assert hasattr(AsyncPoolRequest(None), "connection"), (  # pyright: ignore[reportArgumentType]
        "httpcore pool requests no longer carry `.connection`"
    )


# --------------------------------------------------------------------------------------
# The predicate
# --------------------------------------------------------------------------------------


def test_a_connection_below_the_cap_is_available() -> None:
    connection, pool = capped(2)
    pool.occupy(connection, 1)
    assert connection.is_available() is True


def test_a_connection_at_the_cap_is_not() -> None:
    """The whole mechanism: the pool asks this, hears no, and creates another connection instead."""
    connection, pool = capped(2)
    pool.occupy(connection, 2)
    assert connection.is_available() is False


def test_the_inner_connection_can_still_veto() -> None:
    """The cap only ever narrows. An expired or busy h1 connection stays unavailable however empty it is."""
    connection, _ = capped(4, inner=FakeInner(available=False))
    assert connection.is_available() is False


def test_only_this_connections_requests_are_counted() -> None:
    """The pool's list holds every in-flight request in the whole pool, not just this connection's."""
    connection, pool = capped(2)
    pool.occupy(object(), 5)
    assert connection.assigned_request_count() == 0
    assert connection.is_available() is True


def test_max_concurrent_requests_answers_rather_than_going_missing() -> None:
    """Guards httpcore PR #1088, which would read this and fall back to 1 on AttributeError.

    A wrapper that did not forward it would silently limit every connection to a single in-flight request on some future upgrade — the pool catches the AttributeError and never says anything.
    """
    connection, _ = capped(3)
    assert connection.max_concurrent_requests() == 3


# --------------------------------------------------------------------------------------
# Installation
# --------------------------------------------------------------------------------------


def _connection_the_pool_creates(client: httpx2.AsyncClient) -> httpcore2.AsyncConnectionInterface:
    """Ask the client's own pool for a connection, which is the only way to see what the cap installed.

    `_transport._pool` is private on both hops and httpx offers no public equivalent — `cap_streams_per_connection` patches that exact path, so a test reaching it some other way would not be testing the thing. Written once here rather than at four call sites: pyright reports the pool as unknown, and an unknown spreads into every local it touches, which is what turned one deliberate private access into eleven diagnostics.

    Two hops needing two different answers, which is why one `# pyright: ignore` never worked here. `client._transport` is private, so it is ignored; it is declared `AsyncBaseTransport`, which has no `_pool` at all, so the second hop goes through `getattr`. The call sites used to name `reportAttributeAccessIssue` alone and suppressed nothing at all: eleven of this repository's twenty-one diagnostics came from four lines each carrying a comment that read like a decision.

    `getattr` plus `isinstance` rather than a `cast` through `Any`, on a review's suggestion. A `cast` is a promise to the type checker and nothing at runtime, so a pool that changed shape would be reported wherever it happened to break; this asserts the shape at the reach itself, which is where the reader is being told what is assumed. It costs one line and closes the gap the `Any` opened.
    """
    transport = client._transport  # pyright: ignore[reportPrivateUsage]
    pool = getattr(transport, "_pool", None)
    assert isinstance(pool, httpcore2.AsyncConnectionPool), (
        f"{type(transport).__name__} no longer carries an `AsyncConnectionPool`, which is the path the cap patches"
    )
    return pool.create_connection(httpcore2.Origin(b"https", b"example.invalid", 443))


def test_capping_wraps_what_the_pool_creates() -> None:
    client = httpx2.AsyncClient(http2=True)
    cap_streams_per_connection(client, 2)
    created = _connection_the_pool_creates(client)
    assert isinstance(created, StreamCappedConnection)


def test_capping_reaches_the_proxy_pool_too() -> None:
    """A proxy makes httpx build `AsyncHTTPProxy`, which is a pool of its own.

    Patching the live object rather than substituting a pool subclass is what makes this work without a second implementation — and without it the cap would do nothing from the day a proxy was configured, which is exactly the kind of gap nobody goes looking for.
    """
    client = httpx2.AsyncClient(http2=True, proxy="http://127.0.0.1:1080")
    cap_streams_per_connection(client, 1)
    created = _connection_the_pool_creates(client)
    assert isinstance(created, StreamCappedConnection)


def _clear_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)


def _direct_mounts(client: httpx2.AsyncClient) -> list[httpx2.AsyncBaseTransport]:
    return [
        transport
        for transport in client._mounts.values()  # pyright: ignore[reportPrivateUsage]
        if transport is not None and getattr(getattr(transport, "_pool", None), "_proxy_url", None) is None
    ]


def _connection_for(transport: httpx2.AsyncBaseTransport, host: bytes) -> Any:
    """What this transport's pool would build for an origin, without connecting.

    Typed `Any` deliberately: httpcore's pool attributes are untyped, so reading them at each call site spreads three unknown-type diagnostics per site instead of one place that says "this is third-party private state".
    """
    pool: Any = cast(Any, transport)._pool  # pyright: ignore[reportPrivateUsage]
    return pool.create_connection(httpcore2.Origin(b"https", host, 443))


def test_one_pool_is_capped_once_however_many_mounts_reach_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every `NO_PROXY` rule mounts the same direct transport, and it must still be wrapped exactly once.

    Wrapping it once per mention is not a wrong cap — the pool assigns each request to the outermost wrapper, so the inner layers count zero and only delegate — which is why nothing about the connection counts would have shown this. What it does instead is nest `create_connection` one call deeper per mention; see the test below for where that ends.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("NO_PROXY", "a.example.com,b.example.com,c.example.com")

    client = build_http_client(
        ProxyConfig.model_validate({"upstream_transport": {"max_streams_per_connection": 2}}),
        proxy_from_cli=False,
    )
    direct = _direct_mounts(client)
    # Not vacuous: there really are several mounts, and they really are one object.
    assert len(direct) >= 3
    assert len({id(transport) for transport in direct}) == 1

    created = _connection_for(direct[0], b"a.example.com")
    assert isinstance(created, StreamCappedConnection)
    assert not isinstance(created._inner, StreamCappedConnection), "the same pool was capped once per mount"  # pyright: ignore[reportPrivateUsage]


def test_a_long_no_proxy_list_still_opens_a_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """The nesting above is what makes an ordinary setting fail, so the failure itself gets an assertion.

    1100 rules is a few tens of KiB of environment variable — well inside what a shell will pass, and nothing about it is malformed. Against the un-deduplicated version this raises `RecursionError` before any socket is touched, so the operator sees a stack overflow rather than a request.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("NO_PROXY", ",".join(f"h{index}.example.com" for index in range(1100)))

    client = build_http_client(
        ProxyConfig.model_validate({"upstream_transport": {"max_streams_per_connection": 2}}),
        proxy_from_cli=False,
    )
    created = _connection_for(_direct_mounts(client)[0], b"h0.example.com")
    assert isinstance(created, StreamCappedConnection)


def test_a_transport_with_no_pool_is_refused_rather_than_silently_uncapped() -> None:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(lambda _: httpx2.Response(200)))
    with pytest.raises(TypeError, match="no connection pool"):
        cap_streams_per_connection(client, 2)


@pytest.mark.parametrize("value", [0, -1])
def test_a_cap_below_one_is_refused(value: int) -> None:
    """0 means "off" to the config and never reaches here; arriving anyway is a wiring mistake, not a request to disable."""
    client = httpx2.AsyncClient()
    with pytest.raises(ValueError, match=">= 1"):
        cap_streams_per_connection(client, value)


# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------


def test_the_cap_is_off_by_default() -> None:
    """No measurement here supports a particular number, so the default changes nothing."""
    assert transport_options(ProxyConfig(), proxy_from_cli=False).max_streams_per_connection == 0


def test_the_configured_cap_reaches_the_client() -> None:
    config = ProxyConfig.model_validate({"upstream_transport": {"max_streams_per_connection": 2}})
    assert transport_options(config, proxy_from_cli=False).max_streams_per_connection == 2
    client = build_http_client(config, proxy_from_cli=False)
    created = _connection_the_pool_creates(client)
    assert isinstance(created, StreamCappedConnection)


def test_the_default_client_is_left_alone() -> None:
    """Off must mean untouched, not capped at some large number: an uncapped pool is httpx's own behaviour and should stay literally that."""
    created = _connection_the_pool_creates(build_http_client(ProxyConfig(), proxy_from_cli=False))
    assert not isinstance(created, StreamCappedConnection)


# --------------------------------------------------------------------------------------
# Against the real pool
# --------------------------------------------------------------------------------------


class HeldOpenInner(httpcore2.AsyncConnectionInterface):
    """A connection that answers, and whose response body never ends until released.

    Only the leaf is faked. The pool doing the assigning, the `_requests` list being counted, and the wrapper under test are all the real ones — which is the point: the predicate tests above prove the wrapper answers correctly, and only this proves httpcore acts on the answer.
    """

    def __init__(self, release: asyncio.Event) -> None:
        self._release = release

    async def handle_async_request(self, request: httpcore2.Request) -> httpcore2.Response:
        async def body() -> AsyncIterator[bytes]:
            await self._release.wait()
            yield b"done"

        return httpcore2.Response(200, content=body())

    def is_available(self) -> bool:
        return True

    def can_handle_request(self, origin: httpcore2.Origin) -> bool:
        return True

    def has_expired(self) -> bool:
        return False

    def is_idle(self) -> bool:
        return False

    def is_closed(self) -> bool:
        return False

    def info(self) -> str:
        return "held-open"

    async def aclose(self) -> None:
        return None


class MeteredInner(httpcore2.AsyncConnectionInterface):
    """Records what actually overlapped on it, counted from the moment the pool hands it a request.

    Counting here rather than in the wrapper is the point: the wrapper's own bookkeeping is what is under test, so a measurement taken from it could agree with a broken cap. This counts admitted work only — the wrapper refuses before delegating — from handler entry to the close of that request's body.
    """

    def __init__(self, peaks: dict[int, int]) -> None:
        self._peaks = peaks
        self._in_flight = 0

    async def handle_async_request(self, request: httpcore2.Request) -> httpcore2.Response:
        self._in_flight += 1
        self._peaks[id(self)] = max(self._peaks.get(id(self), 0), self._in_flight)

        async def body() -> AsyncIterator[bytes]:
            try:
                # Long enough that the rest of the burst is still queued while this one is in flight, short enough that responses keep finishing and freeing slots.
                await asyncio.sleep(0.01)
                yield b"done"
            finally:
                self._in_flight -= 1

        return httpcore2.Response(200, content=body())

    def is_available(self) -> bool:
        return True

    def can_handle_request(self, origin: httpcore2.Origin) -> bool:
        return True

    def has_expired(self) -> bool:
        return False

    def is_idle(self) -> bool:
        return False

    def is_closed(self) -> bool:
        return False

    def info(self) -> str:
        return "metered"

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_the_cap_holds_when_the_pool_releases_a_queue_all_at_once() -> None:
    """A saturated pool is where answering `is_available()` alone stopped being enough.

    httpcore2 snapshots the reusable connections once per assignment pass, so a pass that has several requests queued asks the predicate once and can put all of them on one connection. That state needs a pool with no room left to open connections and responses finishing under it — one request at a time never reaches it, which is why the six-request test above passes either way and this one does not.

    `== cap` rather than `<= cap`: an off-by-one that refused at the cap instead of past it would hold every request one under it and still satisfy `<=`, leaving connections quietly carrying less than asked for.
    """
    cap = 2
    max_connections = 4
    burst = 60
    peaks: dict[int, int] = {}
    pool = httpcore2.AsyncConnectionPool(max_connections=max_connections)

    def create_connection(origin: httpcore2.Origin) -> httpcore2.AsyncConnectionInterface:
        return StreamCappedConnection(MeteredInner(peaks), pool, cap)  # pyright: ignore[reportArgumentType]

    pool.create_connection = create_connection  # pyright: ignore[reportAttributeAccessIssue]

    async def issue() -> None:
        response = await pool.handle_async_request(
            httpcore2.Request("GET", "https://example.invalid/", extensions={"timeout": {}})
        )
        await response.aread()
        await response.aclose()

    async with asyncio.timeout(30):
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(issue()) for _ in range(burst)]

    assert all(task.done() and task.exception() is None for task in tasks)
    assert max(peaks.values()) == cap



@pytest.mark.asyncio
@pytest.mark.parametrize(("cap", "expected"), [(1, 6), (2, 3), (3, 2), (6, 1)])
async def test_the_real_pool_opens_another_connection_once_one_is_full(cap: int, expected: int) -> None:
    """Six concurrent requests land on `ceil(6 / cap)` connections.

    This is the assertion the cap exists for, and the one that a fake pool cannot make: the predicate could be perfect and still cap nothing if httpcore stopped consulting `is_available()` before reusing a connection. `cap=6` is the control — at that point every request fits on one connection, so a wrapper that always answered "unavailable" would fail here rather than passing everything.
    """
    release = asyncio.Event()
    created: list[StreamCappedConnection] = []
    pool = httpcore2.AsyncConnectionPool()

    def create_connection(origin: httpcore2.Origin) -> httpcore2.AsyncConnectionInterface:
        connection = StreamCappedConnection(HeldOpenInner(release), pool, cap)  # pyright: ignore[reportArgumentType]
        created.append(connection)
        return connection

    pool.create_connection = create_connection  # pyright: ignore[reportAttributeAccessIssue]

    async def issue() -> None:
        response = await pool.handle_async_request(
            httpcore2.Request("GET", "https://example.invalid/", extensions={"timeout": {}})
        )
        await response.aread()
        await response.aclose()

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(issue()) for _ in range(6)]
        # Every request is assigned before any finishes, which is what makes the count a statement about concurrency rather than about reuse over time.
        while sum(1 for request in pool._requests if request.connection is not None) < 6:  # pyright: ignore[reportPrivateUsage]
            await asyncio.sleep(0)
        assert len(created) == expected
        release.set()

    assert all(task.done() and task.exception() is None for task in tasks)

