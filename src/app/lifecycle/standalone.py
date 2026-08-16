"""Running the proxy directly, per `lifecycle.md`'s stand-alone section.

The process binds its own listener, serves, and walks down a shutdown ladder as signals arrive.
Each rung is a different action, and the operator picks how far to go by how many times they signal.

- `DRAINING` stops accepting and waits on the requests' own timeouts;
- `INTERRUPTING` cuts the in-flight requests short and waits for that to land;
- `FINALIZING` gives up waiting, cancels what is left, and runs cleanup regardless.

`graceful_cleanup_timeout` bounds only what happens *after* the drain, which is what it measures.
The drain itself is deliberately unbounded.
A request already carries its own deadline.
A second wall-clock limit stacked on top would cut off legitimate long work, while the operator
still has escalation available anyway.

Nothing here calls `sys.exit` or `os._exit`.
`serve()` returns and the caller unwinds normally; a forced stop is SIGKILL and the operator's call.
"""

import asyncio
import signal
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass

from app.lifecycle.shutdown import ESCALATING_SIGNALS, RESTART_SIGNAL, ShutdownLadder, ShutdownStage
from app.server_adapter import UvicornListenerAdapter

HANDLED_SIGNALS = (*sorted(ESCALATING_SIGNALS), RESTART_SIGNAL)

type Hook = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CleanupOutcome:
    """What the final teardown managed to do within its budget."""

    timed_out: bool
    completed: bool
    error: str


@dataclass(frozen=True, slots=True)
class ShutdownReport:
    """What the shutdown actually did, so a caller can log it rather than guess."""

    stage: ShutdownStage
    interrupted_connections: int = 0
    cancelled_requests: int = 0
    cleanup_timed_out: bool = False
    cleanup_completed: bool = True
    # Errors are reported rather than swallowed; cleanup failing must not look like success.
    cleanup_error: str = ""


class StandaloneServer:
    """Drives one listener through serve and shutdown."""

    def __init__(
        self,
        adapter: UvicornListenerAdapter,
        *,
        cleanup_timeout: int = 0,
        on_serving: Hook | None = None,
    ) -> None:
        self._adapter = adapter
        self._cleanup_timeout = cleanup_timeout
        self._on_serving = on_serving
        self._ladder = ShutdownLadder()
        self._advanced = asyncio.Event()

    @property
    def ladder(self) -> ShutdownLadder:
        return self._ladder

    def receive_signal(self, sig: signal.Signals) -> None:
        """Apply a signal and wake whatever is waiting.

        Split from handler registration.
        A test can then drive the ladder without signalling the process running the test.
        """
        before = self._ladder.stage
        after = self._ladder.receive(sig)
        if after is not before:
            self._advanced.set()

    async def serve(self) -> ShutdownReport:
        await self._adapter.startup_lifespan()
        await self._adapter.register_dormant()
        await self._adapter.arm()
        if self._on_serving is not None:
            await self._on_serving()

        with self._signal_handlers():
            await self._await_advance()
            await self._adapter.stop_accepting()
            return await self._descend()

    async def _descend(self) -> ShutdownReport:
        interrupted = 0
        cancelled = 0

        # Driven by the rung currently in effect rather than by a fixed sequence of waits.
        # Signals can arrive faster than this loop runs, so the ladder is read, never assumed.
        while True:
            stage = self._ladder.stage
            if stage is ShutdownStage.FINALIZING:
                # Stop waiting for the requests. The interruption still happens.
                cancelled += self._adapter.cancel_requests()
                break
            if stage is ShutdownStage.INTERRUPTING and interrupted == 0:
                # Interrupt the requests, then wait for the interruption to land.
                # Closing the connection is not enough: Uvicorn leaves a running handler alone,
                # so the request is only actually interrupted by cancelling its task.
                interrupted = self._adapter.interrupt_connections()
                cancelled += self._adapter.cancel_requests()
            if await self._drained_before_advance(stage):
                break

        outcome = await self._finalize()
        return ShutdownReport(
            stage=self._ladder.stage,
            interrupted_connections=interrupted,
            cancelled_requests=cancelled,
            cleanup_timed_out=outcome.timed_out,
            cleanup_completed=outcome.completed,
            cleanup_error=outcome.error,
        )

    async def _finalize(self) -> CleanupOutcome:
        """Run lifespan shutdown and release the listener.

        The budget bounds how long we *wait*, not how long cleanup may take.
        The spec requires the last rung to persist state and release resources, so the cleanup task
        is shielded: exceeding the budget stops the waiting and is reported, and never cancels the
        teardown that the rung exists to perform.
        """
        cleanup = asyncio.ensure_future(self._adapter.shutdown_lifespan(drain_timeout=None))
        timed_out = False
        try:
            await asyncio.wait_for(asyncio.shield(cleanup), self._cleanup_timeout or None)
        except (TimeoutError, Exception):
            # Both outcomes are read off the task below rather than raised onward.
            # A failed teardown is reported to the caller; it must not abort the rest of the stop.
            # The budget expiring cancels the shield, never `cleanup`, so `done()` tells them apart.
            timed_out = not cleanup.done()

        error = ""
        failure = cleanup.exception() if cleanup.done() and not cleanup.cancelled() else None
        if failure is not None:
            error = f"{type(failure).__name__}: {failure}"
        if not timed_out and not error:
            try:
                await self._adapter.close_masters()
            except Exception as failure:
                error = f"{type(failure).__name__}: {failure}"
        return CleanupOutcome(timed_out=timed_out, completed=cleanup.done(), error=error)

    async def _await_advance(self) -> None:
        """Wait until the shutdown starts at all."""
        while not self._ladder.stopping:
            self._advanced.clear()
            await self._advanced.wait()

    async def _advanced_from(self, stage: ShutdownStage) -> None:
        """Return once the ladder has moved off `stage`.

        The rung to compare against is passed in rather than read here.
        Reading it here would re-anchor to whatever the ladder has already reached, and the wait
        would then be for an advance that has happened, which nothing is left to announce.
        """
        while self._ladder.stage is stage:
            self._advanced.clear()
            await self._advanced.wait()

    async def _drained_before_advance(self, stage: ShutdownStage) -> bool:
        """Wait for the drain, but stop early if the operator escalates.

        Returns True when everything drained, False when a further signal arrived first.
        """
        drain = asyncio.ensure_future(self._adapter.wait_drained())
        advance = asyncio.ensure_future(self._advanced_from(stage))
        try:
            await asyncio.wait({drain, advance}, return_when=asyncio.FIRST_COMPLETED)
            drained = drain.done() and not drain.cancelled()
        finally:
            for task in (drain, advance):
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
        return drained and self._ladder.stage is stage

    @contextmanager
    def _signal_handlers(self) -> Generator[None]:
        """Install the handlers for the run, and take them off again afterwards.

        A platform without signal support is not an error.
        The ladder is then driven by the caller, which is also how the tests drive it.
        """
        loop = asyncio.get_running_loop()
        registered: list[signal.Signals] = []
        for sig in HANDLED_SIGNALS:
            try:
                loop.add_signal_handler(sig, self.receive_signal, sig)
            except NotImplementedError:
                continue
            registered.append(sig)
        try:
            yield
        finally:
            for sig in registered:
                with suppress(NotImplementedError):
                    loop.remove_signal_handler(sig)
