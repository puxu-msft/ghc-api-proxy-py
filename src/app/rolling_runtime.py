from __future__ import annotations

import asyncio
import signal
import socket
from collections.abc import Callable, MutableMapping, Sequence
from contextlib import suppress

from fastapi import FastAPI
from uvicorn import Config

from app.server_adapter import UvicornListenerAdapter
from app.socket_activation import ActivatedSocketSet, ExpectedListener
from app.systemd_notify import notify_ready, notify_stopping

ROLLING_PORT = 4144
ROLLING_LISTENERS = (
    ExpectedListener("http-v4", socket.AF_INET, "127.0.0.1", ROLLING_PORT),
    ExpectedListener("http-v6", socket.AF_INET6, "::1", ROLLING_PORT),
)


class RollingRuntimeError(RuntimeError):
    """Raised when a rolling generation cannot become manager-ready."""


class _StopRequested(Exception):
    """Internal control flow for a normal TERM/INT observed during startup."""


class RollingRuntime:
    def __init__(
        self,
        application: FastAPI,
        activated: ActivatedSocketSet,
        *,
        notify_ready_fn: Callable[[], None] = notify_ready,
        notify_stopping_fn: Callable[[], None] = notify_stopping,
    ) -> None:
        self._application = application
        self._adapter = UvicornListenerAdapter(
            Config(application, log_config=None, timeout_graceful_shutdown=None),
            activated,
        )
        self._notify_ready = notify_ready_fn
        self._notify_stopping = notify_stopping_fn
        self._stop_event = asyncio.Event()

    @property
    def adapter(self) -> UvicornListenerAdapter:
        return self._adapter

    async def startup(self) -> None:
        await self._adapter.startup_lifespan()
        self._raise_if_stopping()
        await self._adapter.register_dormant()
        self._raise_if_stopping()
        runtime = self._application.state.runtime
        if not runtime.is_ready:
            raise RollingRuntimeError(
                f"runtime dependencies are not ready: {runtime.readiness_checks()}"
            )
        await self._adapter.arm()
        # asyncio signal handlers are scheduled callbacks. Yield once so a
        # TERM/INT delivered while arm() was completing is observed before READY.
        await asyncio.sleep(0)
        self._raise_if_stopping()
        self._notify_ready()

    async def run_until_stopped(self) -> None:
        await self._stop_event.wait()

    async def run(self) -> None:
        registered = self._install_signal_handlers()
        startup_completed = False
        try:
            try:
                await self.startup()
            except _StopRequested:
                await self._shielded_cleanup(notify_stopping=True)
                return
            except BaseException as startup_error:
                try:
                    await self._shielded_cleanup(notify_stopping=False)
                except BaseException as cleanup_error:
                    raise BaseExceptionGroup(
                        "rolling startup and cleanup failed",
                        [startup_error, cleanup_error],
                    ) from startup_error
                raise
            startup_completed = True
            await self.run_until_stopped()
        finally:
            try:
                if startup_completed:
                    await self._shielded_cleanup(notify_stopping=True)
            finally:
                self._remove_signal_handlers(registered)

    async def shutdown(self) -> None:
        await self._cleanup(notify_stopping=True)

    def request_stop(self) -> None:
        self._stop_event.set()

    def _install_signal_handlers(self) -> tuple[signal.Signals, ...]:
        loop = asyncio.get_running_loop()
        registered: list[signal.Signals] = []
        for sig in (signal.SIGTERM, signal.SIGINT):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._stop_event.set)
                registered.append(sig)
        return tuple(registered)

    @staticmethod
    def _remove_signal_handlers(registered: Sequence[signal.Signals]) -> None:
        loop = asyncio.get_running_loop()
        for sig in registered:
            with suppress(NotImplementedError):
                loop.remove_signal_handler(sig)

    def _raise_if_stopping(self) -> None:
        if self._stop_event.is_set():
            raise _StopRequested

    async def _cleanup(self, *, notify_stopping: bool) -> None:
        errors: list[BaseException] = []
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
) -> None:
    activated = ActivatedSocketSet.from_systemd_environment(
        expected,
        environ=environ,
    )
    runtime = RollingRuntime(application, activated)
    await runtime.run()
