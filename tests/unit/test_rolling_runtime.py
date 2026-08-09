from __future__ import annotations

import signal
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI

from app.rolling_runtime import (
    ROLLING_LISTENERS,
    ROLLING_PORT,
    RollingRuntime,
    RollingRuntimeError,
    run_systemd_generation,
)
from app.socket_activation import ActivatedSocketSet, ExpectedListener


@dataclass
class _RuntimeState:
    is_ready: bool

    def readiness_checks(self) -> dict[str, bool]:
        return {"ready": self.is_ready}


def _app(*, ready: bool) -> FastAPI:
    application = FastAPI()
    application.state.runtime = _RuntimeState(ready)
    return application


def _adapter_factory(adapter: Mock):
    def factory(_config: object, _activated: ActivatedSocketSet) -> Mock:
        return adapter

    return factory


@pytest.mark.asyncio
async def test_startup_arms_then_notifies(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    adapter = Mock()
    adapter.startup_lifespan = AsyncMock(side_effect=lambda: events.append("lifespan"))
    adapter.register_dormant = AsyncMock(side_effect=lambda: events.append("dormant"))
    adapter.arm = AsyncMock(side_effect=lambda: events.append("arm"))
    adapter.shutdown_lifespan = AsyncMock()
    adapter.close_masters = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    runtime: RollingRuntime

    def ready() -> None:
        events.append("ready")
        runtime.request_stop()

    runtime = RollingRuntime(
        _app(ready=True),
        Mock(),
        notify_ready_fn=ready,
        notify_stopping_fn=Mock(),
    )

    await runtime.run()

    assert events == ["lifespan", "dormant", "arm", "ready"]
    adapter.shutdown_lifespan.assert_awaited_once_with(drain_timeout=None)
    adapter.close_masters.assert_awaited_once()


@pytest.mark.asyncio
async def test_unready_dependencies_never_arm_or_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = Mock()
    adapter.startup_lifespan = AsyncMock()
    adapter.register_dormant = AsyncMock()
    adapter.arm = AsyncMock()
    adapter.shutdown_lifespan = AsyncMock()
    adapter.close_masters = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    notify_ready = Mock()
    runtime = RollingRuntime(_app(ready=False), Mock(), notify_ready_fn=notify_ready)

    with pytest.raises(RollingRuntimeError, match="not ready"):
        await runtime.run()

    adapter.arm.assert_not_awaited()
    notify_ready.assert_not_called()
    adapter.shutdown_lifespan.assert_awaited_once_with(drain_timeout=None)
    adapter.close_masters.assert_awaited_once()


@pytest.mark.asyncio
async def test_notify_failure_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = Mock()
    adapter.startup_lifespan = AsyncMock()
    adapter.register_dormant = AsyncMock()
    adapter.arm = AsyncMock()
    adapter.shutdown_lifespan = AsyncMock()
    adapter.close_masters = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    runtime = RollingRuntime(
        _app(ready=True),
        Mock(),
        notify_ready_fn=Mock(side_effect=RuntimeError("notify failed")),
    )

    with pytest.raises(RuntimeError, match="notify failed"):
        await runtime.run()

    adapter.shutdown_lifespan.assert_awaited_once_with(drain_timeout=None)
    adapter.close_masters.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_stop_unblocks_wait_and_shutdown_notifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    adapter = Mock()
    adapter.startup_lifespan = AsyncMock()
    adapter.register_dormant = AsyncMock()
    adapter.arm = AsyncMock()

    async def cleanup(*, drain_timeout: float | None) -> None:
        assert drain_timeout is None
        events.append("cleanup")

    adapter.shutdown_lifespan = AsyncMock(side_effect=cleanup)
    adapter.close_masters = AsyncMock(side_effect=lambda: events.append("close"))
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    stopping = Mock(side_effect=lambda: events.append("stopping"))
    runtime = RollingRuntime(
        _app(ready=True),
        Mock(),
        notify_ready_fn=Mock(),
        notify_stopping_fn=stopping,
    )

    runtime.request_stop()
    await runtime.run_until_stopped()
    await runtime.shutdown()

    stopping.assert_called_once()
    assert events == ["stopping", "cleanup", "close"]
    adapter.shutdown_lifespan.assert_awaited_once_with(drain_timeout=None)
    adapter.close_masters.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["register_dormant", "arm"])
async def test_startup_failure_always_cleans_up(
    failure_point: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    adapter.startup_lifespan = AsyncMock()
    adapter.register_dormant = AsyncMock()
    adapter.arm = AsyncMock()
    getattr(adapter, failure_point).side_effect = RuntimeError(f"{failure_point} failed")
    adapter.shutdown_lifespan = AsyncMock()
    adapter.close_masters = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    runtime = RollingRuntime(_app(ready=True), Mock(), notify_ready_fn=Mock())

    with pytest.raises(RuntimeError, match=f"{failure_point} failed"):
        await runtime.run()

    adapter.shutdown_lifespan.assert_awaited_once_with(drain_timeout=None)
    adapter.close_masters.assert_awaited_once()


@pytest.mark.asyncio
async def test_stopping_notify_failure_does_not_block_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    adapter = Mock()
    adapter.startup_lifespan = AsyncMock()
    adapter.register_dormant = AsyncMock()
    adapter.arm = AsyncMock()

    async def cleanup(*, drain_timeout: float | None) -> None:
        assert drain_timeout is None
        events.append("cleanup")

    adapter.shutdown_lifespan = AsyncMock(side_effect=cleanup)
    adapter.close_masters = AsyncMock(side_effect=lambda: events.append("close"))
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    runtime: RollingRuntime

    def ready() -> None:
        runtime.request_stop()

    def stopping() -> None:
        events.append("stopping-failed")
        raise RuntimeError("stopping notify failed")

    runtime = RollingRuntime(
        _app(ready=True),
        Mock(),
        notify_ready_fn=ready,
        notify_stopping_fn=stopping,
    )

    with pytest.raises(BaseExceptionGroup, match="cleanup failed"):
        await runtime.run()

    assert events == ["stopping-failed", "cleanup", "close"]


@pytest.mark.asyncio
async def test_signal_handlers_are_installed_before_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    adapter = Mock()
    adapter.startup_lifespan = AsyncMock(side_effect=lambda: events.append("lifespan"))
    adapter.register_dormant = AsyncMock()
    adapter.arm = AsyncMock()
    adapter.shutdown_lifespan = AsyncMock()
    adapter.close_masters = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    loop = __import__("asyncio").get_running_loop()
    original_add = loop.add_signal_handler

    def record_add(sig: signal.Signals, callback: Callable[[], None]) -> None:
        events.append(f"handler:{sig}")
        original_add(sig, callback)

    monkeypatch.setattr(loop, "add_signal_handler", record_add)
    runtime: RollingRuntime

    def ready() -> None:
        runtime.request_stop()

    runtime = RollingRuntime(
        _app(ready=True),
        Mock(),
        notify_ready_fn=ready,
        notify_stopping_fn=Mock(),
    )
    await runtime.run()

    assert events.index("lifespan") > events.index("handler:15")
    assert events.index("lifespan") > events.index("handler:2")


@pytest.mark.asyncio
async def test_stop_scheduled_during_arm_prevents_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    adapter.startup_lifespan = AsyncMock()
    adapter.register_dormant = AsyncMock()
    adapter.shutdown_lifespan = AsyncMock()
    adapter.close_masters = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    notify_ready = Mock()
    notify_stopping = Mock()
    runtime: RollingRuntime

    async def arm() -> None:
        __import__("asyncio").get_running_loop().call_soon(runtime.request_stop)

    adapter.arm = AsyncMock(side_effect=arm)
    runtime = RollingRuntime(
        _app(ready=True),
        Mock(),
        notify_ready_fn=notify_ready,
        notify_stopping_fn=notify_stopping,
    )

    await runtime.run()

    notify_ready.assert_not_called()
    notify_stopping.assert_called_once()
    adapter.shutdown_lifespan.assert_awaited_once_with(drain_timeout=None)
    adapter.close_masters.assert_awaited_once()


def test_production_listener_profile_is_fixed_dual_stack_4144() -> None:
    assert ROLLING_PORT == 4144
    assert [(item.name, item.host, item.port) for item in ROLLING_LISTENERS] == [
        ("http-v4", "127.0.0.1", 4144),
        ("http-v6", "::1", 4144),
    ]


@pytest.mark.asyncio
async def test_run_generation_consumes_supplied_environment_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment: dict[str, str] = {
        "LISTEN_PID": "1",
        "LISTEN_FDS": "2",
        "LISTEN_FDNAMES": "http-v4:http-v6",
        "KEEP": "yes",
    }
    activated = Mock()

    def collect(
        _expected: Sequence[ExpectedListener],
        *,
        environ: MutableMapping[str, str],
    ) -> Mock:
        assert environ is environment
        for key in ("LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES"):
            environ.pop(key)
        return activated

    run = AsyncMock()
    monkeypatch.setattr(
        "app.rolling_runtime.ActivatedSocketSet.from_systemd_environment",
        collect,
    )
    monkeypatch.setattr("app.rolling_runtime.RollingRuntime.run", run)

    await run_systemd_generation(_app(ready=True), environ=environment)

    assert environment == {"KEEP": "yes"}
    run.assert_awaited_once()
