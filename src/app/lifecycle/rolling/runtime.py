from __future__ import annotations

import asyncio
import os
import signal
import socket
from collections.abc import Callable, MutableMapping, Sequence
from contextlib import suppress
from enum import StrEnum
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from uvicorn import Config
from uvicorn._types import ASGI3Application

from app.lifecycle.rolling.generation.admission import GenerationAdmissionMiddleware
from app.lifecycle.rolling.generation.control import GenerationControlServer
from app.lifecycle.rolling.generation.phases import (
    GenerationLifecycle,
    GenerationPhase,
)
from app.server_adapter import UvicornListenerAdapter
from app.socket_activation import ActivatedSocketSet, ExpectedListener
from app.systemd_notify import notify_ready, notify_stopping
from app.tokenization.snapshot_store import TokenizationSnapshotStore

ROLLING_PORT = 4144
ROLLING_LISTENERS = (
    ExpectedListener("http-v4", socket.AF_INET, "127.0.0.1", ROLLING_PORT),
    ExpectedListener("http-v6", socket.AF_INET6, "::1", ROLLING_PORT),
)


class RollingRuntimeError(RuntimeError):
    """Raised when a rolling generation cannot become manager-ready."""


class _StopRequested(Exception):
    """Internal control flow for a normal TERM/INT observed during startup."""


class RuntimeCommand(StrEnum):
    QUIESCE = "quiesce"
    RESUME = "resume"
    TERMINATE = "terminate"


class RollingRuntime:
    def __init__(
        self,
        application: FastAPI,
        activated: ActivatedSocketSet,
        *,
        notify_ready_fn: Callable[[], None] = notify_ready,
        notify_stopping_fn: Callable[[], None] = notify_stopping,
        generation_id: str = "test-generation",
        release_id: str = "test-release",
        control_path: Path | None = None,
        control_server: GenerationControlServer | None = None,
        exit_fn: Callable[[int], None] = os._exit,
    ) -> None:
        self._application = application
        lifecycle = application.state.runtime.generation_lifecycle
        if not isinstance(lifecycle, GenerationLifecycle):
            raise RollingRuntimeError("rolling application requires generation lifecycle")
        self._lifecycle = lifecycle
        self._adapter = UvicornListenerAdapter(
            Config(
                GenerationAdmissionMiddleware(
                    cast(ASGI3Application, application),
                    lifecycle,
                ),
                log_config=None,
                timeout_graceful_shutdown=None,
            ),
            activated,
        )
        self._notify_ready = notify_ready_fn
        self._notify_stopping = notify_stopping_fn
        self._generation_id = generation_id
        self._release_id = release_id
        self._transition_lock = asyncio.Lock()
        self._drain_timer: asyncio.Task[None] | None = None
        self._commands: asyncio.Queue[RuntimeCommand] = asyncio.Queue()
        self._termination_signals = 0
        self._exit = exit_fn
        self._control = control_server or (
            GenerationControlServer(
                control_path,
                lifecycle,
                generation_id=generation_id,
                release_id=release_id,
                listener_families=tuple(
                    identity.name for identity in activated.identities()
                ),
                flush_tokenization=self.flush_tokenization_snapshot,
            )
            if control_path is not None
            else None
        )

    @property
    def adapter(self) -> UvicornListenerAdapter:
        return self._adapter

    async def startup(self) -> None:
        await self._adapter.startup_lifespan()
        approval_gate = self._application.state.runtime.approval_gate
        if approval_gate is not None:
            approval_gate.set_creation_predicate(lambda: self._lifecycle.accepting)
        self._raise_if_stopping()
        await self._adapter.register_dormant()
        self._raise_if_stopping()
        runtime = self._application.state.runtime
        if not runtime.dependencies_ready:
            raise RollingRuntimeError(
                f"runtime dependencies are not ready: {runtime.readiness_checks()}"
            )
        await self._adapter.arm()
        # asyncio signal handlers are scheduled callbacks. Yield once so a
        # TERM/INT delivered while arm() was completing is observed before READY.
        await asyncio.sleep(0)
        self._raise_if_stopping()
        await self._lifecycle.mark_ready()
        self._notify_ready()

    async def run_until_stopped(self) -> None:
        while True:
            command = await self._commands.get()
            try:
                if command is RuntimeCommand.QUIESCE:
                    await self.quiesce()
                elif command is RuntimeCommand.RESUME:
                    await self.resume()
                else:
                    await self._terminate_gracefully()
                    return
            except BaseException:
                snapshot = await self._lifecycle.snapshot()
                if snapshot.phase is not GenerationPhase.FAILED:
                    raise

    async def run(self) -> None:
        registered = self._install_signal_handlers()
        startup_completed = False
        control_started = False
        cleanup_completed = False
        errors: list[BaseException] = []
        if self._control is not None:
            try:
                await self._control.start()
                control_started = True
            except BaseException as error:
                errors.append(error)
                try:
                    await self._adapter.close_masters()
                except BaseException as close_error:
                    errors.append(close_error)
        if not errors:
            try:
                await self.startup()
            except _StopRequested:
                startup_completed = True
            except BaseException as error:
                errors.append(error)
                try:
                    await self._shielded_cleanup(notify_stopping=False)
                    cleanup_completed = True
                except BaseException as cleanup_error:
                    errors.append(cleanup_error)
            else:
                startup_completed = True
                try:
                    await self.run_until_stopped()
                except BaseException as error:
                    errors.append(error)
        if startup_completed and not cleanup_completed:
            try:
                await self._shielded_cleanup(notify_stopping=True)
            except BaseException as error:
                errors.append(error)
        if self._control is not None and control_started:
            try:
                await self._control.close()
            except BaseException as error:
                errors.append(error)
        try:
            self._remove_signal_handlers(registered)
        except BaseException as error:
            errors.append(error)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise BaseExceptionGroup("rolling runtime failed", errors)

    async def shutdown(self) -> None:
        await self._cleanup(notify_stopping=True)

    async def quiesce(self) -> None:
        task = asyncio.create_task(self._quiesce())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def _quiesce(self) -> None:
        runtime = self._application.state.runtime
        async with self._transition_lock:
            errors: list[BaseException] = []
            try:
                await self._lifecycle.quiesce(
                    runtime.approval_gate,
                    runtime.websocket_manager,
                )
            except BaseException as error:
                errors.append(error)
            try:
                await self._adapter.stop_accepting()
            except BaseException as error:
                errors.append(error)
            if errors:
                raise BaseExceptionGroup("rolling quiesce failed", errors)
            self._start_drain_timer()

    async def resume(self) -> None:
        task = asyncio.create_task(self._resume())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def _resume(self) -> None:
        runtime = self._application.state.runtime
        async with self._transition_lock:
            await self._cancel_drain_timer()
            try:
                await self._adapter.resume_accepting()
                await self._lifecycle.resume(
                    runtime.approval_gate,
                    runtime.websocket_manager,
                )
            except BaseException as resume_error:
                errors: list[BaseException] = [resume_error]
                try:
                    await self._adapter.stop_accepting()
                except BaseException as stop_error:
                    errors.append(stop_error)
                await self._lifecycle.mark_failed(resume_error)
                raise BaseExceptionGroup("rolling resume failed", errors) from resume_error

    def request_stop(self) -> None:
        self.request_termination(signal.SIGTERM)

    def request_termination(self, sig: signal.Signals) -> None:
        self._on_termination_signal(sig)

    def request_quiesce(self) -> None:
        self._commands.put_nowait(RuntimeCommand.QUIESCE)

    def request_resume(self) -> None:
        self._commands.put_nowait(RuntimeCommand.RESUME)

    def _install_signal_handlers(self) -> tuple[signal.Signals, ...]:
        loop = asyncio.get_running_loop()
        registered: list[signal.Signals] = []
        for sig in (signal.SIGTERM, signal.SIGINT):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._on_termination_signal, sig)
                registered.append(sig)
        for sig, command in (
            (signal.SIGUSR2, self.request_quiesce),
            (signal.SIGUSR1, self.request_resume),
        ):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, command)
                registered.append(sig)
        return tuple(registered)

    @staticmethod
    def _remove_signal_handlers(registered: Sequence[signal.Signals]) -> None:
        loop = asyncio.get_running_loop()
        for sig in registered:
            with suppress(NotImplementedError):
                loop.remove_signal_handler(sig)

    def _raise_if_stopping(self) -> None:
        if self._termination_signals > 0:
            raise _StopRequested

    def _on_termination_signal(self, sig: signal.Signals) -> None:
        self._termination_signals += 1
        if self._termination_signals > 1:
            self._exit(128 + int(sig))
            return
        self._commands.put_nowait(RuntimeCommand.TERMINATE)

    async def _terminate_gracefully(self) -> None:
        if self._lifecycle.accepting:
            await self.quiesce()
        await self._cancel_drain_timer()
        timeout_seconds = self._application.state.runtime.settings.shutdown.drain_timeout
        if timeout_seconds == 0:
            await self._lifecycle.wait_for_drained()
            return
        try:
            async with asyncio.timeout(timeout_seconds):
                await self._lifecycle.wait_for_drained()
        except TimeoutError:
            await self._lifecycle.cancel_active_operations()
            await self._lifecycle.wait_for_drained()

    async def flush_tokenization_snapshot(self) -> dict[str, object]:
        runtime = self._application.state.runtime
        state = runtime.tokenization_state
        if state is None:
            raise RollingRuntimeError("tokenization state is not initialized")
        snapshot_root = runtime.settings.tokenization.snapshot_root
        if not snapshot_root:
            raise RollingRuntimeError("tokenization snapshot_root is not configured")
        await state.flush()
        receipt = TokenizationSnapshotStore(Path(snapshot_root)).publish_local(
            generation=self._generation_id,
            release=self._release_id,
            revision=state.revision,
            payload=state.snapshot(),
        )
        return {
            "changed": receipt.changed,
            "revision": receipt.reference.revision,
            "sha256": receipt.reference.sha256,
            "path": receipt.reference.path,
            "canonical_updated": False,
            "reason": receipt.reason,
        }

    def _start_drain_timer(self) -> None:
        timeout_seconds = self._application.state.runtime.settings.shutdown.drain_timeout
        if timeout_seconds == 0 or self._drain_timer is not None:
            return
        self._drain_timer = asyncio.create_task(
            self._cancel_after_drain_timeout(timeout_seconds)
        )

    async def _cancel_after_drain_timeout(self, timeout_seconds: int) -> None:
        try:
            await asyncio.sleep(timeout_seconds)
            async with self._transition_lock:
                snapshot = await self._lifecycle.snapshot()
                if snapshot.phase is GenerationPhase.QUIESCING:
                    await self._lifecycle.cancel_active_operations()
        finally:
            self._drain_timer = None

    async def _cancel_drain_timer(self) -> None:
        task, self._drain_timer = self._drain_timer, None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _cleanup(self, *, notify_stopping: bool) -> None:
        errors: list[BaseException] = []
        async with self._transition_lock:
            await self._cancel_drain_timer()
            try:
                await self._lifecycle.start_stopping()
            except BaseException as error:
                errors.append(error)
            if notify_stopping:
                try:
                    self._notify_stopping()
                except BaseException as error:
                    errors.append(error)
            try:
                await self._adapter.shutdown_lifespan(drain_timeout=None)
            except BaseException as error:
                errors.append(error)
            try:
                await self._adapter.close_masters()
            except BaseException as error:
                errors.append(error)
        if errors:
            raise BaseExceptionGroup("rolling cleanup failed", errors)

    async def _shielded_cleanup(self, *, notify_stopping: bool) -> None:
        cleanup_task = asyncio.create_task(self._cleanup(notify_stopping=notify_stopping))
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            await cleanup_task
            raise


async def run_systemd_generation(
    application: FastAPI,
    *,
    expected: Sequence[ExpectedListener] = ROLLING_LISTENERS,
    environ: MutableMapping[str, str] | None = None,
    generation_id: str = "test-generation",
    release_id: str = "test-release",
    control_path: Path | None = None,
) -> None:
    activated = ActivatedSocketSet.from_systemd_environment(
        expected,
        environ=environ,
    )
    runtime = RollingRuntime(
        application,
        activated,
        generation_id=generation_id,
        release_id=release_id,
        control_path=control_path,
    )
    await runtime.run()
