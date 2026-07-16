from collections.abc import Callable
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
    ) -> None:
        self.current_phase: ShutdownPhase | None = None
        self._on_phase = on_phase

    async def run(self) -> None:
        for phase in ShutdownPhase:
            self.current_phase = phase
            if self._on_phase is not None:
                self._on_phase(phase)