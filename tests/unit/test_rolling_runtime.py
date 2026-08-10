from __future__ import annotations

import signal
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI

from app.config.settings import AppSettings
from app.generation import GenerationLifecycle
from app.rolling_runtime import (
    ROLLING_LISTENERS,
    ROLLING_PORT,
    RollingRuntime,
    RollingRuntimeError,
    run_systemd_generation,
)
from app.socket_activation import ActivatedSocketSet, ExpectedListener
from app.tokenization.state_store import TokenizationStateStore


@dataclass
class _RuntimeState:
    dependencies_ready: bool
    generation_lifecycle: GenerationLifecycle
    approval_gate: None = None
    websocket_manager: object | None = None
    settings: AppSettings = field(default_factory=AppSettings)
    tokenization_state: TokenizationStateStore | None = None

    def readiness_checks(self) -> dict[str, bool]:
        return {"ready": self.dependencies_ready}


def _app(*, ready: bool, drain_timeout: int = 0) -> FastAPI:
    application = FastAPI()
    application.state.runtime = _RuntimeState(
        ready,
        GenerationLifecycle(),
        settings=AppSettings.model_validate(
            {"shutdown": {"drain_timeout": drain_timeout}}
        ),
    )
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
    adapter.stop_accepting = AsyncMock()
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
    adapter.stop_accepting = AsyncMock()
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
    adapter.stop_accepting = AsyncMock()
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

    with pytest.raises(BaseExceptionGroup, match="runtime failed"):
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
    adapter.stop_accepting = AsyncMock()
    adapter.shutdown_lifespan = AsyncMock()
    adapter.close_masters = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    loop = __import__("asyncio").get_running_loop()
    original_add = loop.add_signal_handler

    def record_add(
        sig: signal.Signals,
        callback: Callable[..., None],
        *args: object,
    ) -> None:
        events.append(f"handler:{sig}")
        original_add(sig, callback, *args)

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


@pytest.mark.asyncio
async def test_runtime_quiesce_resume_is_one_serial_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    entered_stop = __import__("asyncio").Event()
    release_stop = __import__("asyncio").Event()
    adapter = Mock()

    async def stop_accepting() -> None:
        events.append("stop-enter")
        entered_stop.set()
        await release_stop.wait()
        events.append("stop-complete")

    async def resume_accepting() -> None:
        events.append("resume-adapter")

    adapter.stop_accepting = AsyncMock(side_effect=stop_accepting)
    adapter.resume_accepting = AsyncMock(side_effect=resume_accepting)
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    application = _app(ready=True)
    lifecycle = application.state.runtime.generation_lifecycle
    await lifecycle.mark_ready()
    runtime = RollingRuntime(application, Mock(), notify_stopping_fn=Mock())

    quiesce = __import__("asyncio").create_task(runtime.quiesce())
    await entered_stop.wait()
    resume = __import__("asyncio").create_task(runtime.resume())
    quiesce.cancel()
    await __import__("asyncio").sleep(0)
    assert not resume.done()
    release_stop.set()
    with pytest.raises(__import__("asyncio").CancelledError):
        await quiesce
    await resume

    assert events == ["stop-enter", "stop-complete", "resume-adapter"]
    assert lifecycle.phase.value == "ready_accepting"
    assert lifecycle.accepting is True


@pytest.mark.asyncio
async def test_usr_commands_quiesce_and_resume_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    adapter.stop_accepting = AsyncMock()
    adapter.resume_accepting = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    application = _app(ready=True)
    lifecycle = application.state.runtime.generation_lifecycle
    await lifecycle.mark_ready()
    runtime = RollingRuntime(application, Mock(), exit_fn=Mock())
    commands = __import__("asyncio").create_task(runtime.run_until_stopped())

    runtime.request_quiesce()
    while adapter.stop_accepting.await_count == 0:
        await __import__("asyncio").sleep(0)
    assert lifecycle.phase.value == "quiescing"
    adapter.stop_accepting.assert_awaited_once()

    before_resume = await lifecycle.snapshot()
    runtime.request_resume()
    resumed = await lifecycle.wait_for_change(before_resume.revision, 1)
    assert resumed.phase.value == "ready_accepting"
    adapter.resume_accepting.assert_awaited_once()

    runtime.request_stop()
    await commands
    assert lifecycle.phase.value == "quiescing"


@pytest.mark.asyncio
async def test_first_termination_waits_for_active_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    adapter.stop_accepting = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    application = _app(ready=True)
    lifecycle = application.state.runtime.generation_lifecycle
    await lifecycle.mark_ready()
    release = __import__("asyncio").Event()

    async def operation() -> None:
        async with lifecycle.try_admit() as admitted:
            assert admitted
            await release.wait()

    active = __import__("asyncio").create_task(operation())
    while lifecycle.active_operations == 0:
        await __import__("asyncio").sleep(0)
    runtime = RollingRuntime(application, Mock(), exit_fn=Mock())
    commands = __import__("asyncio").create_task(runtime.run_until_stopped())
    runtime.request_stop()
    await __import__("asyncio").sleep(0)
    assert not commands.done()
    release.set()
    await active
    await commands


@pytest.mark.asyncio
async def test_positive_drain_timeout_cancels_active_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    adapter.stop_accepting = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    application = _app(ready=True, drain_timeout=1)
    lifecycle = application.state.runtime.generation_lifecycle
    await lifecycle.mark_ready()

    async def operation() -> None:
        async with lifecycle.try_admit() as admitted:
            assert admitted
            await __import__("asyncio").Event().wait()

    active = __import__("asyncio").create_task(operation())
    while lifecycle.active_operations == 0:
        await __import__("asyncio").sleep(0)
    runtime = RollingRuntime(application, Mock(), exit_fn=Mock())
    commands = __import__("asyncio").create_task(runtime.run_until_stopped())
    runtime.request_stop()
    await commands
    assert active.cancelled()
    assert lifecycle.active_operations == 0


def test_second_termination_signal_exits_immediately_with_second_signal_code() -> None:
    exit_fn = Mock()
    runtime = RollingRuntime(_app(ready=True), Mock(), exit_fn=exit_fn)

    runtime.request_termination(signal.SIGTERM)
    runtime.request_termination(signal.SIGINT)

    exit_fn.assert_called_once_with(130)


@pytest.mark.asyncio
async def test_runtime_flushes_generation_local_tokenization_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    application = _app(ready=True)
    state = TokenizationStateStore(tmp_path / "local" / "tokenization.json")
    state.calibration.learn("anthropic", "model", 10, 12)
    application.state.runtime.tokenization_state = state
    application.state.runtime.settings = AppSettings.model_validate(
        {"tokenization": {"snapshot_root": str(tmp_path / "snapshots")}}
    )
    runtime = RollingRuntime(
        application,
        Mock(),
        generation_id="g0000000000000001",
        release_id="release-a",
    )

    receipt = await runtime.flush_tokenization_snapshot()

    assert receipt["revision"] == 1
    assert isinstance(receipt["sha256"], str)
    assert Path(str(receipt["path"])).is_file()
    assert receipt["canonical_updated"] is False


@pytest.mark.asyncio
async def test_run_aggregates_primary_cleanup_and_control_close_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    adapter.startup_lifespan = AsyncMock(side_effect=RuntimeError("primary failure"))
    adapter.shutdown_lifespan = AsyncMock(side_effect=RuntimeError("cleanup failure"))
    adapter.close_masters = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    control = Mock()
    control.start = AsyncMock()
    control.close = AsyncMock(side_effect=RuntimeError("control close failure"))
    runtime = RollingRuntime(
        _app(ready=True),
        Mock(),
        control_server=control,
        notify_ready_fn=Mock(),
    )

    with pytest.raises(BaseExceptionGroup) as captured:
        await runtime.run()

    rendered = repr(captured.value)
    for message in (
        "primary failure",
        "cleanup failure",
        "control close failure",
    ):
        assert message in rendered


@pytest.mark.asyncio
async def test_quiesce_failure_still_stops_accepting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    adapter.stop_accepting = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    application = _app(ready=True)
    lifecycle = application.state.runtime.generation_lifecycle
    await lifecycle.mark_ready()

    class FailingObservers:
        async def close_topics(
            self,
            _topics: set[str],
            *,
            code: int,
            reason: str,
        ) -> int:
            assert code == 1012
            assert reason == "server_restarting"
            raise RuntimeError("observer close failed")

        def reopen_topics(self, _topics: set[str]) -> None:
            return None

    application.state.runtime.websocket_manager = FailingObservers()
    runtime = RollingRuntime(application, Mock(), exit_fn=Mock())

    with pytest.raises(BaseExceptionGroup, match="quiesce failed"):
        await runtime.quiesce()

    adapter.stop_accepting.assert_awaited_once()
    assert lifecycle.phase.value == "failed"
    assert lifecycle.accepting is False


@pytest.mark.asyncio
async def test_adapter_resume_failure_marks_generation_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    adapter.resume_accepting = AsyncMock(side_effect=RuntimeError("resume failed"))
    adapter.stop_accepting = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    application = _app(ready=True)
    lifecycle = application.state.runtime.generation_lifecycle
    await lifecycle.mark_ready()
    await lifecycle.quiesce()
    runtime = RollingRuntime(application, Mock(), exit_fn=Mock())

    with pytest.raises(BaseExceptionGroup, match="resume failed"):
        await runtime.resume()

    assert lifecycle.phase.value == "failed"
    snapshot = await lifecycle.snapshot()
    assert snapshot.last_error == "RuntimeError: resume failed"
    adapter.stop_accepting.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_cancels_pending_usr2_drain_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    adapter.stop_accepting = AsyncMock()
    adapter.resume_accepting = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    application = _app(ready=True, drain_timeout=1)
    lifecycle = application.state.runtime.generation_lifecycle
    await lifecycle.mark_ready()
    runtime = RollingRuntime(application, Mock(), exit_fn=Mock())
    release = __import__("asyncio").Event()

    async def operation() -> None:
        async with lifecycle.try_admit() as admitted:
            assert admitted
            await release.wait()

    active = __import__("asyncio").create_task(operation())
    while lifecycle.active_operations == 0:
        await __import__("asyncio").sleep(0)
    await runtime.quiesce()
    await runtime.resume()
    await __import__("asyncio").sleep(1.1)

    assert not active.cancelled()
    release.set()
    await active


@pytest.mark.asyncio
async def test_full_run_preserves_failed_phase_until_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Mock()
    adapter.startup_lifespan = AsyncMock()
    adapter.register_dormant = AsyncMock()
    adapter.arm = AsyncMock()
    adapter.stop_accepting = AsyncMock()
    adapter.resume_accepting = AsyncMock(side_effect=RuntimeError("resume failed"))
    adapter.shutdown_lifespan = AsyncMock()
    adapter.close_masters = AsyncMock()
    monkeypatch.setattr("app.rolling_runtime.UvicornListenerAdapter", _adapter_factory(adapter))
    application = _app(ready=True)
    lifecycle = application.state.runtime.generation_lifecycle
    ready = __import__("asyncio").Event()
    runtime = RollingRuntime(
        application,
        Mock(),
        notify_ready_fn=ready.set,
        notify_stopping_fn=Mock(),
        exit_fn=Mock(),
    )
    running = __import__("asyncio").create_task(runtime.run())
    await ready.wait()

    runtime.request_quiesce()
    while lifecycle.phase.value != "quiescing":
        await __import__("asyncio").sleep(0)
    quiesced = await lifecycle.snapshot()
    runtime.request_resume()
    failed = await lifecycle.wait_for_change(quiesced.revision, 1)
    assert failed.phase.value == "failed"
    assert not running.done()
    snapshot = await lifecycle.snapshot()
    assert snapshot.last_error == "RuntimeError: resume failed"

    runtime.request_stop()
    await running
    final = await lifecycle.snapshot()
    assert final.phase.value == "failed"
    assert final.last_error == "RuntimeError: resume failed"
