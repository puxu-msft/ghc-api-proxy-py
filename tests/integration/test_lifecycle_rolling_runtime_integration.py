from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.config.settings import AppSettings
from app.lifecycle.rolling.generation.phases import GenerationLifecycle
from app.lifecycle.rolling.runtime import RollingRuntime, RollingRuntimeError
from app.socket_activation import ActivatedSocketSet, ExpectedListener
from app.systemd_notify import notify_ready, notify_stopping


@dataclass
class _ReadyState:
    dependencies_ready: bool
    generation_lifecycle: GenerationLifecycle
    approval_gate: None = None
    websocket_manager: None = None
    settings: AppSettings = field(default_factory=AppSettings)

    def readiness_checks(self) -> dict[str, bool]:
        return {"ready": self.dependencies_ready}


def _listener(family: socket.AddressFamily) -> socket.socket:
    listener = socket.socket(family, socket.SOCK_STREAM)
    if family == socket.AF_INET6:
        listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind(("::1", 0))
    else:
        listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    return listener


def _activated(ipv4: socket.socket, ipv6: socket.socket) -> ActivatedSocketSet:
    return ActivatedSocketSet(
        {"http-v4": ipv4, "http-v6": ipv6},
        [
            ExpectedListener(
                "http-v4",
                socket.AF_INET,
                "127.0.0.1",
                ipv4.getsockname()[1],
            ),
            ExpectedListener(
                "http-v6",
                socket.AF_INET6,
                "::1",
                ipv6.getsockname()[1],
            ),
        ],
    )


def _app(*, ready: bool) -> FastAPI:
    app = FastAPI()
    app.state.runtime = _ReadyState(ready, GenerationLifecycle())

    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    app.add_api_route("/health/liveness", liveness)
    return app


async def _request(host: str, port: int) -> bytes:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(b"GET /health/liveness HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n")
        await writer.drain()
        return await reader.read()
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_runtime_notifies_ready_after_dual_stack_arm_and_stopping_before_shutdown(
    tmp_path: Path,
) -> None:
    path = tmp_path / "notify.sock"
    notifications = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    notifications.bind(str(path))
    notifications.setblocking(False)
    loop = asyncio.get_running_loop()
    ipv4 = _listener(socket.AF_INET)
    ipv6 = _listener(socket.AF_INET6)
    environ = {"NOTIFY_SOCKET": str(path)}
    runtime = RollingRuntime(
        _app(ready=True),
        _activated(ipv4, ipv6),
        notify_ready_fn=lambda: notify_ready(environ=environ),
        notify_stopping_fn=lambda: notify_stopping(environ=environ),
    )
    try:
        await runtime.startup()
        assert await loop.sock_recv(notifications, 64) == b"READY=1"
        assert b"200 OK" in await _request("127.0.0.1", ipv4.getsockname()[1])
        assert b"200 OK" in await _request("::1", ipv6.getsockname()[1])

        runtime.request_stop()
        await runtime.run_until_stopped()
        await runtime.shutdown()
        assert await loop.sock_recv(notifications, 64) == b"STOPPING=1"
    finally:
        notifications.close()
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_unready_runtime_never_arms_listener_or_notifies(
    tmp_path: Path,
) -> None:
    path = tmp_path / "notify.sock"
    notifications = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    notifications.bind(str(path))
    notifications.setblocking(False)
    ipv4 = _listener(socket.AF_INET)
    ipv6 = _listener(socket.AF_INET6)
    runtime = RollingRuntime(
        _app(ready=False),
        _activated(ipv4, ipv6),
        notify_ready_fn=lambda: notify_ready(environ={"NOTIFY_SOCKET": str(path)}),
    )
    try:
        with pytest.raises(RollingRuntimeError, match="not ready"):
            await runtime.startup()
        assert runtime.adapter.accepting is False
        pending = asyncio.create_task(_request("127.0.0.1", ipv4.getsockname()[1]))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(pending), 0.05)
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                asyncio.get_running_loop().sock_recv(notifications, 64),
                0.05,
            )
    finally:
        notifications.close()
        ipv4.close()
        ipv6.close()
