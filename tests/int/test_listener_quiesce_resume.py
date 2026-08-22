from __future__ import annotations

import asyncio
import os
import socket
import ssl
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from uvicorn import Config

from app.lifecycle.activation import ActivatedSocketSet, ExpectedListener, SocketActivationError
from app.lifecycle.adapter import ListenerState, UvicornListenerAdapter
from app.lifecycle.listener import FirstByteRoutingAdapter
from app.lifecycle.tls import build_server_ssl_context, generate_self_signed


def _listeners() -> tuple[socket.socket, socket.socket]:
    ipv4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ipv4.bind(("127.0.0.1", 0))
    ipv4.listen(32)
    ipv6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    ipv6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    ipv6.bind(("::1", 0))
    ipv6.listen(32)
    return ipv4, ipv6


def _activated(ipv4: socket.socket, ipv6: socket.socket) -> ActivatedSocketSet:
    v4_address = ipv4.getsockname()
    v6_address = ipv6.getsockname()
    return ActivatedSocketSet(
        {"http-v4": ipv4, "http-v6": ipv6},
        [
            ExpectedListener("http-v4", socket.AF_INET, "127.0.0.1", v4_address[1]),
            ExpectedListener("http-v6", socket.AF_INET6, "::1", v6_address[1]),
        ],
    )


async def _request(host: str, port: int) -> bytes:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(b"GET /health/liveness HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n")
        await writer.drain()
        return await reader.read()
    finally:
        writer.close()
        await writer.wait_closed()


async def _tls_request(host: str, port: int) -> bytes:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    reader, writer = await asyncio.open_connection(
        host,
        port,
        ssl=context,
        server_hostname="localhost",
    )
    try:
        writer.write(b"GET /health/liveness HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n")
        await writer.drain()
        return await reader.read()
    finally:
        writer.close()
        await writer.wait_closed()


async def _keep_alive_request(host: str, port: int):  # type: ignore[no-untyped-def]
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(b"GET /health/liveness HTTP/1.1\r\nHost: test\r\n\r\n")
    await writer.drain()
    response = await reader.readuntil(b"\r\n\r\n")
    response += await reader.readexactly(15)
    return response, reader, writer


def _app(
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    app.add_api_route("/health/liveness", liveness)
    return app


@pytest.mark.asyncio
async def test_dormant_dual_stack_arm_stop_and_resume() -> None:
    ipv4, ipv6 = _listeners()
    activated = _activated(ipv4, ipv6)
    adapter = UvicornListenerAdapter(Config(_app(), log_config=None), activated)
    v4_port = ipv4.getsockname()[1]
    v6_port = ipv6.getsockname()[1]
    try:
        await adapter.startup_lifespan()
        await adapter.register_dormant()
        assert adapter.accepting is False

        dormant_v4 = asyncio.create_task(_request("127.0.0.1", v4_port))
        dormant_v6 = asyncio.create_task(_request("::1", v6_port))
        for dormant in (dormant_v4, dormant_v6):
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(dormant), 0.05)

        await adapter.arm()
        assert b"200 OK" in await asyncio.wait_for(dormant_v4, 2)
        assert b"200 OK" in await asyncio.wait_for(dormant_v6, 2)

        identities_before = adapter.listener_identities
        master_inodes = sorted((identity.device, identity.inode) for identity in identities_before)
        assert list(adapter.registration_identities()) == master_inodes
        await adapter.stop_accepting()
        assert adapter.accepting is False
        queued_v4 = asyncio.create_task(_request("127.0.0.1", v4_port))
        queued_v6 = asyncio.create_task(_request("::1", v6_port))
        for queued in (queued_v4, queued_v6):
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(queued), 0.05)

        await adapter.resume_accepting()
        assert adapter.accepting is True
        assert adapter.listener_identities == identities_before
        assert list(adapter.registration_identities()) == master_inodes
        assert b"200 OK" in await asyncio.wait_for(queued_v4, 2)
        assert b"200 OK" in await asyncio.wait_for(queued_v6, 2)
    finally:
        await adapter.shutdown_lifespan()
        await adapter.close_masters()
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_tls_router_stop_accepting_preserves_masters_and_resumes(tmp_path: Path) -> None:
    ipv4, ipv6 = _listeners()
    activated = _activated(ipv4, ipv6)
    material = generate_self_signed(tmp_path / "tls")
    uvicorn_adapter = UvicornListenerAdapter(Config(_app(), log_config=None), activated)
    adapter = FirstByteRoutingAdapter(
        uvicorn_adapter,
        activated,
        build_server_ssl_context(material),
    )
    queued: asyncio.Task[bytes] | None = None
    try:
        await adapter.startup_lifespan()
        await adapter.register_dormant()
        await adapter.arm()
        port = ipv4.getsockname()[1]
        assert b"200 OK" in await asyncio.wait_for(_tls_request("127.0.0.1", port), 2)

        identities_before = adapter.listener_identities
        master_inodes = sorted((identity.device, identity.inode) for identity in identities_before)
        assert list(adapter.registration_identities()) == master_inodes
        await adapter.stop_accepting()
        queued = asyncio.create_task(_tls_request("127.0.0.1", port))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(queued), 0.05)

        await adapter.resume_accepting()
        assert adapter.listener_identities == identities_before
        assert list(adapter.registration_identities()) == master_inodes
        assert b"200 OK" in await asyncio.wait_for(queued, 2)
    finally:
        if queued is not None and not queued.done():
            queued.cancel()
            await asyncio.gather(queued, return_exceptions=True)
        await adapter.shutdown_lifespan()
        await adapter.close_masters()
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_a_resume_after_a_refusal_serves_again_rather_than_answering_503(
    tmp_path: Path,
) -> None:
    """A refusal is undone by the resume that follows it, on the TLS router as much as on the adapter.

    The router keeps its own `_arm_locked` and never calls the wrapped adapter's, so the two fields of the barrier were reopened by different code paths — the event by the router, the refusal only by the adapter. A refusal raised and then resumed past left a listener accepting normally while every request on it answered 503 for ever, which is the failure mode that looks healthiest from outside.

    Only `stop_admitting` ever raises a refusal, and today it is only called on the way out. `lifecycle.md` lists `RESUME` as a runtime signal, so this pins the pairing before the control plane reaches it.
    """
    ipv4, ipv6 = _listeners()
    activated = _activated(ipv4, ipv6)
    material = generate_self_signed(tmp_path / "tls")
    uvicorn_adapter = UvicornListenerAdapter(Config(_app(), log_config=None), activated)
    adapter = FirstByteRoutingAdapter(
        uvicorn_adapter,
        activated,
        build_server_ssl_context(material),
    )
    try:
        await adapter.startup_lifespan()
        await adapter.register_dormant()
        await adapter.arm()
        port = ipv4.getsockname()[1]
        assert b"200 OK" in await asyncio.wait_for(_tls_request("127.0.0.1", port), 2)

        await adapter.stop_accepting()
        await adapter.stop_admitting()
        await adapter.resume_accepting()

        # Not merely "answers something": a stuck refusal answers 503 promptly and looks alive.
        resumed = await asyncio.wait_for(_tls_request("127.0.0.1", port), 2)
        assert b"200 OK" in resumed
        assert b"503" not in resumed
        assert uvicorn_adapter.refused_requests() == 0
    finally:
        await adapter.shutdown_lifespan()
        await adapter.close_masters()
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_resume_fails_after_master_listener_close() -> None:
    ipv4, ipv6 = _listeners()
    activated = _activated(ipv4, ipv6)
    adapter = UvicornListenerAdapter(Config(_app(), log_config=None), activated)
    try:
        await adapter.startup_lifespan()
        await adapter.register_dormant()
        await adapter.arm()
        await adapter.stop_accepting()
        await adapter.close_masters()

        with pytest.raises(SocketActivationError, match="masters are closed"):
            await adapter.resume_accepting()
    finally:
        await adapter.shutdown_lifespan()
        ipv4.close()
        ipv6.close()


def test_reuseaddr_is_not_a_live_overlap_mechanism() -> None:
    first = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    first.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    first.bind(("127.0.0.1", 0))
    first.listen(16)
    second = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    second.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        with pytest.raises(OSError):
            second.bind(first.getsockname())
    finally:
        second.close()
        first.close()


@pytest.mark.skipif(not hasattr(socket, "SO_REUSEPORT"), reason="SO_REUSEPORT unavailable")
def test_reuseport_creates_distinct_listener_identity() -> None:
    first = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    first.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    first.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    first.bind(("127.0.0.1", 0))
    first.listen(16)
    second = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    second.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    second.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    second.bind(first.getsockname())
    second.listen(16)
    try:
        first_stat = os.fstat(first.fileno())
        second_stat = os.fstat(second.fileno())
        assert (first_stat.st_dev, first_stat.st_ino) != (
            second_stat.st_dev,
            second_stat.st_ino,
        )
    finally:
        second.close()
        first.close()


@pytest.mark.asyncio
async def test_stop_accepting_returns_with_idle_accepted_connection() -> None:
    ipv4, ipv6 = _listeners()
    adapter = UvicornListenerAdapter(Config(_app(), log_config=None), _activated(ipv4, ipv6))
    writer = None
    try:
        await adapter.startup_lifespan()
        await adapter.register_dormant()
        await adapter.arm()
        _reader, writer = await asyncio.open_connection("127.0.0.1", ipv4.getsockname()[1])
        await asyncio.sleep(0.05)

        await asyncio.wait_for(adapter.stop_accepting(), 0.2)
        assert adapter.state is ListenerState.STOPPED
        assert adapter.server_state.connections
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        await adapter.shutdown_lifespan(drain_timeout=1)
        await adapter.close_masters()
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_partial_arm_failure_rolls_back_all_registrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ipv4, ipv6 = _listeners()
    adapter = UvicornListenerAdapter(Config(_app(), log_config=None), _activated(ipv4, ipv6))
    try:
        await adapter.startup_lifespan()
        await adapter.register_dormant()
        second = adapter.registrations[1]
        release_failure = asyncio.Event()

        async def fail_after_first_accept() -> None:
            await release_failure.wait()
            raise OSError("arm failed")

        monkeypatch.setattr(second, "start_serving", AsyncMock(side_effect=fail_after_first_accept))
        queued_v4 = asyncio.create_task(_request("127.0.0.1", ipv4.getsockname()[1]))
        queued_v6 = asyncio.create_task(_request("::1", ipv6.getsockname()[1]))
        arm = asyncio.create_task(adapter.arm())
        for _ in range(100):
            if adapter.server_state.tasks:
                break
            await asyncio.sleep(0.01)
        assert adapter.server_state.tasks
        release_failure.set()
        with pytest.raises(OSError, match="arm failed"):
            await arm

        assert adapter.state is ListenerState.FAILED
        assert adapter.registration_identities() == ()
        v4_result = await asyncio.wait_for(
            asyncio.gather(queued_v4, return_exceptions=True),
            1,
        )
        assert isinstance(v4_result[0], BaseException) or b"200 OK" not in v4_result[0]
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(queued_v6), 0.05)
        queued_v6.cancel()
        await asyncio.gather(queued_v6, return_exceptions=True)
        await asyncio.wait_for(adapter.shutdown_lifespan(drain_timeout=1), 2)
        assert not adapter.server_state.tasks
        assert not adapter.server_state.connections
    finally:
        if adapter.state is not ListenerState.CLOSED:
            await adapter.shutdown_lifespan(drain_timeout=1)
        await adapter.close_masters()
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_concurrent_resume_creates_one_registration_set() -> None:
    ipv4, ipv6 = _listeners()
    adapter = UvicornListenerAdapter(Config(_app(), log_config=None), _activated(ipv4, ipv6))
    try:
        await adapter.startup_lifespan()
        await adapter.register_dormant()
        await adapter.arm()
        await adapter.stop_accepting()
        await asyncio.gather(adapter.resume_accepting(), adapter.resume_accepting())

        assert adapter.state is ListenerState.ACCEPTING
        assert len(adapter.registration_identities()) == 2
    finally:
        await adapter.shutdown_lifespan()
        await adapter.close_masters()
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_headers_ticks_lifespan_and_fd_count_are_stable() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
        events.append("startup")
        yield
        events.append("shutdown")

    initial_fd_count = len(list(Path("/proc/self/fd").iterdir()))
    ipv4, ipv6 = _listeners()
    adapter = UvicornListenerAdapter(
        Config(_app(lifespan), log_config=None, headers=[("x-probe", "yes")]),
        _activated(ipv4, ipv6),
    )
    try:
        await adapter.startup_lifespan()
        for _ in range(12):
            await adapter.register_dormant()
            await adapter.arm()
            response = await _request("127.0.0.1", ipv4.getsockname()[1])
            assert b"server: uvicorn" in response.lower()
            assert b"x-probe: yes" in response.lower()
            await adapter.stop_accepting()
        assert events == ["startup"]
    finally:
        await adapter.shutdown_lifespan()
        await adapter.close_masters()
        ipv4.close()
        ipv6.close()
    assert events == ["startup", "shutdown"]
    # The guard is that twelve arm/stop cycles leak nothing, and a leak makes this grow. Equality
    # would also fail when the count *drops*, which happens whenever another test's client is
    # collected while this one runs — a false red that says nothing about this adapter.
    assert len(list(Path("/proc/self/fd").iterdir())) <= initial_fd_count


@pytest.mark.asyncio
async def test_lifespan_shutdown_failure_is_explicit() -> None:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
        yield
        raise RuntimeError("shutdown failed")

    ipv4, ipv6 = _listeners()
    adapter = UvicornListenerAdapter(
        Config(_app(lifespan), log_config=None, lifespan="on"),
        _activated(ipv4, ipv6),
    )
    try:
        await adapter.startup_lifespan()
        await adapter.register_dormant()
        await adapter.arm()
        with pytest.raises(Exception, match=r"shutdown failed|lifespan failed"):
            await adapter.shutdown_lifespan()
        assert adapter.state is ListenerState.FAILED
    finally:
        if adapter.state is not ListenerState.CLOSED:
            await adapter.stop_accepting()
        await adapter.close_masters()
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_shutdown_state_rejects_concurrent_resume() -> None:
    ipv4, ipv6 = _listeners()
    adapter = UvicornListenerAdapter(Config(_app(), log_config=None), _activated(ipv4, ipv6))
    blocker = asyncio.Event()

    async def active_task() -> None:
        await blocker.wait()

    try:
        await adapter.startup_lifespan()
        await adapter.register_dormant()
        await adapter.arm()
        task = asyncio.create_task(active_task())
        adapter.server_state.tasks.add(task)
        shutdown = asyncio.create_task(adapter.shutdown_lifespan())
        while adapter.state is not ListenerState.STOPPING:
            await asyncio.sleep(0)

        await adapter.stop_accepting()
        assert adapter.state is ListenerState.STOPPING
        with pytest.raises(Exception, match="resume requires stopped"):
            await adapter.resume_accepting()
        assert adapter.registrations == ()
        blocker.set()
        await task
        adapter.server_state.tasks.discard(task)
        await shutdown
    finally:
        if adapter.state is not ListenerState.CLOSED:
            blocker.set()
            await adapter.stop_accepting()
        await adapter.close_masters()
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_completed_keep_alive_connection_does_not_block_drain() -> None:
    ipv4, ipv6 = _listeners()
    adapter = UvicornListenerAdapter(Config(_app(), log_config=None), _activated(ipv4, ipv6))
    writer = None
    try:
        await adapter.startup_lifespan()
        await adapter.register_dormant()
        await adapter.arm()
        response, _reader, writer = await _keep_alive_request(
            "127.0.0.1", ipv4.getsockname()[1]
        )
        assert b"200 OK" in response
        assert adapter.server_state.connections
        assert not adapter.server_state.tasks

        await adapter.stop_accepting()
        await asyncio.wait_for(adapter.wait_drained(), 0.1)
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        await adapter.shutdown_lifespan(drain_timeout=1)
        await adapter.close_masters()
        ipv4.close()
        ipv6.close()
