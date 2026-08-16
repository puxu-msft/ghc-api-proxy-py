"""The escalating shutdown ladder for a directly-run process.

`lifecycle.md` gives the signals a meaning rather than an action:

- SIGINT / SIGTERM mean "from a normal shutdown";
- SIGUSR2 means "from a smooth restart";
- SIGKILL means "from a forced exit", and is not ours to handle.

Repeating SIGINT / SIGTERM escalates one rung each time:

1. stop accepting, and wait for in-flight requests the ordinary way, on their own timeouts;
2. interrupt those requests, and wait for the interruption to land;
3. stop waiting; persist state, release resources, and return.

SIGUSR2 only ever starts the descent, and never escalates.
A smooth restart says "the new process is ready for new work", not "abandon what you accepted".
The spec states this directly: `SIGUSR2 信号不会中断优雅关闭`.

Nothing here exits the process.
The last rung returns so the caller can finish its own teardown.
An operator who genuinely wants an immediate stop has SIGKILL.
"""

import signal
from enum import IntEnum

# The signals that escalate, and the one that only starts the descent.
ESCALATING_SIGNALS = frozenset({signal.SIGINT, signal.SIGTERM})
RESTART_SIGNAL = signal.SIGUSR2


class ShutdownStage(IntEnum):
    """Ordered so that `>=` reads as "at least this far along"."""

    RUNNING = 0
    DRAINING = 1
    INTERRUPTING = 2
    FINALIZING = 3


class ShutdownLadder:
    """Tracks how far the shutdown has escalated.

    Deliberately holds no I/O and no async.
    Which rung we are on is a decision about the signals received so far.
    It must answer identically whether or not a drain is in progress.
    """

    def __init__(self) -> None:
        self._stage = ShutdownStage.RUNNING

    @property
    def stage(self) -> ShutdownStage:
        return self._stage

    @property
    def stopping(self) -> bool:
        return self._stage is not ShutdownStage.RUNNING

    def receive(self, sig: signal.Signals) -> ShutdownStage:
        """Apply one signal and return the rung now in effect.

        An unknown signal is ignored rather than treated as a stop.
        This ladder is installed for a named set; guessing would turn a stray signal into a stop.
        """
        if sig == RESTART_SIGNAL:
            # Starts the descent, never deepens it.
            if self._stage is ShutdownStage.RUNNING:
                self._stage = ShutdownStage.DRAINING
            return self._stage
        if sig in ESCALATING_SIGNALS:
            self._stage = ShutdownStage(min(self._stage + 1, ShutdownStage.FINALIZING))
        return self._stage
