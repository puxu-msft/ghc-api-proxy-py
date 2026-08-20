"""Capping how many concurrent requests share one upstream connection.

The predicate is small; what these mostly guard is the private surface underneath it. `pool._requests` and the `.connection` on its elements are undocumented httpcore internals, and if either moves the cap does not fail — it counts zero, answers "available" forever, and becomes a decoration that caps nothing. So the structural guard below matters more than it looks: it is the only thing between a silent httpcore rename and a protection everyone believes is on.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast

import httpcore
import httpx
import pytest

from app.config.schema import ProxyConfig
from app.server.composition import build_http_client, transport_options
from app.upstream.stream_cap import StreamCappedConnection, cap_streams_per_connection


class FakeInner(httpcore.AsyncConnectionInterface):
    """Whatever httpcore would have created, reduced to the two answers the wrapper reads."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available

    def can_handle_request(self, origin: httpcore.Origin) -> bool:
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
    pool = httpcore.AsyncConnectionPool()
    assert isinstance(pool._requests, list), "httpcore.AsyncConnectionPool no longer keeps `_requests`"

    # The element type is only reachable through the module; the implementation deliberately does not import it, but a test may name it to assert its shape.
    from httpcore._async.connection_pool import AsyncPoolRequest

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


def test_capping_wraps_what_the_pool_creates() -> None:
    client = httpx.AsyncClient(http2=True)
    cap_streams_per_connection(client, 2)
    created = client._transport._pool.create_connection(httpcore.Origin(b"https", b"example.invalid", 443))  # pyright: ignore[reportAttributeAccessIssue]
    assert isinstance(created, StreamCappedConnection)


def test_capping_reaches_the_proxy_pool_too() -> None:
    """A proxy makes httpx build `AsyncHTTPProxy`, which is a pool of its own.

    Patching the live object rather than substituting a pool subclass is what makes this work without a second implementation — and without it the cap would do nothing from the day a proxy was configured, which is exactly the kind of gap nobody goes looking for.
    """
    client = httpx.AsyncClient(http2=True, proxy="http://127.0.0.1:1080")
    cap_streams_per_connection(client, 1)
    created = client._transport._pool.create_connection(httpcore.Origin(b"https", b"example.invalid", 443))  # pyright: ignore[reportAttributeAccessIssue]
    assert isinstance(created, StreamCappedConnection)


def _clear_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)


def _direct_mounts(client: httpx.AsyncClient) -> list[httpx.AsyncBaseTransport]:
    return [
        transport
        for transport in client._mounts.values()  # pyright: ignore[reportPrivateUsage]
        if transport is not None and getattr(getattr(transport, "_pool", None), "_proxy_url", None) is None
    ]


def _connection_for(transport: httpx.AsyncBaseTransport, host: bytes) -> Any:
    """What this transport's pool would build for an origin, without connecting.

    Typed `Any` deliberately: httpcore's pool attributes are untyped, so reading them at each call site spreads three unknown-type diagnostics per site instead of one place that says "this is third-party private state".
    """
    pool: Any = cast(Any, transport)._pool  # pyright: ignore[reportPrivateUsage]
    return pool.create_connection(httpcore.Origin(b"https", host, 443))


def test_one_pool_is_capped_once_however_many_mounts_reach_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every `NO_PROXY` rule mounts the same direct transport, and it must still be wrapped exactly once.

    Wrapping it once per mention is not a wrong cap — the pool assigns each request to the outermost wrapper, so the inner layers count zero and only delegate — which is why nothing about the connection counts would have shown this. What it does instead is nest `create_connection` one call deeper per mention; see the test below for where that ends.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("NO_PROXY", "a.example.com,b.example.com,c.example.com")

    client = build_http_client(
        ProxyConfig.model_validate({"upstream_transport": {"max_streams_per_connection": 2}})
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
        ProxyConfig.model_validate({"upstream_transport": {"max_streams_per_connection": 2}})
    )
    created = _connection_for(_direct_mounts(client)[0], b"h0.example.com")
    assert isinstance(created, StreamCappedConnection)


def test_a_transport_with_no_pool_is_refused_rather_than_silently_uncapped() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    with pytest.raises(TypeError, match="no connection pool"):
        cap_streams_per_connection(client, 2)


@pytest.mark.parametrize("value", [0, -1])
def test_a_cap_below_one_is_refused(value: int) -> None:
    """0 means "off" to the config and never reaches here; arriving anyway is a wiring mistake, not a request to disable."""
    client = httpx.AsyncClient()
    with pytest.raises(ValueError, match=">= 1"):
        cap_streams_per_connection(client, value)


# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------


def test_the_cap_is_off_by_default() -> None:
    """No measurement here supports a particular number, so the default changes nothing."""
    assert transport_options(ProxyConfig()).max_streams_per_connection == 0


def test_the_configured_cap_reaches_the_client() -> None:
    config = ProxyConfig.model_validate({"upstream_transport": {"max_streams_per_connection": 2}})
    assert transport_options(config).max_streams_per_connection == 2
    client = build_http_client(config)
    created = client._transport._pool.create_connection(httpcore.Origin(b"https", b"example.invalid", 443))  # pyright: ignore[reportAttributeAccessIssue]
    assert isinstance(created, StreamCappedConnection)


def test_the_default_client_is_left_alone() -> None:
    """Off must mean untouched, not capped at some large number: an uncapped pool is httpx's own behaviour and should stay literally that."""
    created = build_http_client(ProxyConfig())._transport._pool.create_connection(  # pyright: ignore[reportAttributeAccessIssue]
        httpcore.Origin(b"https", b"example.invalid", 443)
    )
    assert not isinstance(created, StreamCappedConnection)


# --------------------------------------------------------------------------------------
# Against the real pool
# --------------------------------------------------------------------------------------


class HeldOpenInner(httpcore.AsyncConnectionInterface):
    """A connection that answers, and whose response body never ends until released.

    Only the leaf is faked. The pool doing the assigning, the `_requests` list being counted, and the wrapper under test are all the real ones — which is the point: the predicate tests above prove the wrapper answers correctly, and only this proves httpcore acts on the answer.
    """

    def __init__(self, release: asyncio.Event) -> None:
        self._release = release

    async def handle_async_request(self, request: httpcore.Request) -> httpcore.Response:
        async def body() -> AsyncIterator[bytes]:
            await self._release.wait()
            yield b"done"

        return httpcore.Response(200, content=body())

    def is_available(self) -> bool:
        return True

    def can_handle_request(self, origin: httpcore.Origin) -> bool:
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


@pytest.mark.asyncio
@pytest.mark.parametrize(("cap", "expected"), [(1, 6), (2, 3), (3, 2), (6, 1)])
async def test_the_real_pool_opens_another_connection_once_one_is_full(cap: int, expected: int) -> None:
    """Six concurrent requests land on `ceil(6 / cap)` connections.

    This is the assertion the cap exists for, and the one that a fake pool cannot make: the predicate could be perfect and still cap nothing if httpcore stopped consulting `is_available()` before reusing a connection. `cap=6` is the control — at that point every request fits on one connection, so a wrapper that always answered "unavailable" would fail here rather than passing everything.
    """
    release = asyncio.Event()
    created: list[StreamCappedConnection] = []
    pool = httpcore.AsyncConnectionPool()

    def create_connection(origin: httpcore.Origin) -> httpcore.AsyncConnectionInterface:
        connection = StreamCappedConnection(HeldOpenInner(release), pool, cap)  # pyright: ignore[reportArgumentType]
        created.append(connection)
        return connection

    pool.create_connection = create_connection  # pyright: ignore[reportAttributeAccessIssue]

    async def issue() -> None:
        response = await pool.handle_async_request(
            httpcore.Request("GET", "https://example.invalid/", extensions={"timeout": {}})
        )
        await response.aread()
        await response.aclose()

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(issue()) for _ in range(6)]
        # Every request is assigned before any finishes, which is what makes the count a statement about concurrency rather than about reuse over time.
        while sum(1 for request in pool._requests if request.connection is not None) < 6:
            await asyncio.sleep(0)
        assert len(created) == expected
        release.set()

    assert all(task.done() and task.exception() is None for task in tasks)

