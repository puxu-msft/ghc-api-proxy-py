from collections.abc import Awaitable, Callable
from enum import StrEnum


class ShutdownPhase(StrEnum):
    SETUP = "setup"
    GRACEFUL_WAIT = "graceful_wait"
    ABORT = "abort"
    FORCE_CLOSE = "force_close"


class ShutdownManager:
    def __init__(
        self,
        *,
        on_phase: Callable[[ShutdownPhase], object] | None = None,
        setup: Callable[[], Awaitable[None]] | None = None,
        graceful_wait: Callable[[], Awaitable[None]] | None = None,
        abort: Callable[[], Awaitable[None]] | None = None,
        force_close: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.current_phase: ShutdownPhase | None = None
        self._on_phase = on_phase
        self._callbacks = {
            ShutdownPhase.SETUP: setup,
            ShutdownPhase.GRACEFUL_WAIT: graceful_wait,
            ShutdownPhase.ABORT: abort,
            ShutdownPhase.FORCE_CLOSE: force_close,
        }

    async def run(self) -> None:
        for phase in ShutdownPhase:
            self.current_phase = phase
            if self._on_phase is not None:
                self._on_phase(phase)
            callback = self._callbacks[phase]
            if callback is not None:
                await callback()