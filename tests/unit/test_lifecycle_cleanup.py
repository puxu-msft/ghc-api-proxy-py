"""The final teardown's failure paths, which the happy-path tests never reach.

The spec's last rung has to persist state and release resources.
A budget that runs out is a reason to stop waiting, not a reason to cancel that teardown.
A teardown that fails must not be reported as a clean stop.

Driven through a stand-in adapter: the interesting cases are a cleanup that overruns and one that
raises, neither of which a real listener produces on demand.
"""

import asyncio
import signal

import pytest

from app.lifecycle.shutdown import ShutdownStage
from app.lifecycle.standalone import StandaloneServer


class StubAdapter:
    """Enough of the adapter surface for the descent, with a controllable teardown."""

    def __init__(
        self,
        *,
        cleanup_delay: float = 0.0,
        cleanup_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.cleanup_delay = cleanup_delay
        self.cleanup_error = cleanup_error
        self.close_error = close_error
        self.cleanup_started = False
        self.cleanup_finished = False
        self.masters_closed = False
        self.stopped_accepting = False

    async def startup_lifespan(self) -> None:
        return None

    async def register_dormant(self) -> None:
        return None

    async def arm(self) -> None:
        return None

    async def stop_accepting(self) -> None:
        self.stopped_accepting = True

    async def wait_drained(self, timeout: float | None = None) -> None:
        del timeout
        return None

    def interrupt_connections(self) -> int:
        return 0

    def cancel_requests(self) -> int:
        return 0

    async def shutdown_lifespan(self, *, drain_timeout: float | None = None) -> None:
        del drain_timeout
        self.cleanup_started = True
        if self.cleanup_delay:
            await asyncio.sleep(self.cleanup_delay)
        if self.cleanup_error is not None:
            raise self.cleanup_error
        self.cleanup_finished = True

    async def close_masters(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.masters_closed = True


def server_for(adapter: StubAdapter, *, cleanup_timeout: int = 0) -> StandaloneServer:
    return StandaloneServer(adapter, cleanup_timeout=cleanup_timeout)  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
async def test_cleanup_is_not_cancelled_when_the_budget_runs_out() -> None:
    """Exceeding the budget stops the waiting, not the teardown.

    Cancelling it would abandon exactly the state persistence the last rung exists to do.
    """
    adapter = StubAdapter(cleanup_delay=0.4)
    server = server_for(adapter, cleanup_timeout=1)
    serving = asyncio.create_task(server.serve())
    await asyncio.sleep(0.05)
    server.receive_signal(signal.SIGTERM)

    report = await asyncio.wait_for(serving, 5)
    assert report.cleanup_timed_out is False
    assert adapter.cleanup_finished is True


@pytest.mark.asyncio
async def test_an_overrunning_cleanup_is_reported_and_still_completes() -> None:
    adapter = StubAdapter(cleanup_delay=0.6)
    server = server_for(adapter, cleanup_timeout=0)
    # cleanup_timeout=0 means wait forever, per the spec's "0 = 无限等".
    serving = asyncio.create_task(server.serve())
    await asyncio.sleep(0.05)
    server.receive_signal(signal.SIGTERM)
    report = await asyncio.wait_for(serving, 5)
    assert report.cleanup_timed_out is False
    assert report.cleanup_completed is True
    assert adapter.cleanup_finished is True


@pytest.mark.asyncio
async def test_a_budget_that_expires_is_reported_and_the_teardown_still_finishes() -> None:
    """The budget marks that cleanup ran long; it never decides to skip it.

    Returning while the teardown is merely pending would be no better than cancelling it: the
    composition root's runner closes the loop on the way out and cancels it there instead. So the
    guarded invariant is the stronger one — over budget is reported, and cleanup has still run by
    the time `serve()` returns.
    """
    started = asyncio.Event()

    class SlowAdapter(StubAdapter):
        async def shutdown_lifespan(self, *, drain_timeout: float | None = None) -> None:
            del drain_timeout
            self.cleanup_started = True
            started.set()
            await asyncio.sleep(1)
            self.cleanup_finished = True

    adapter = SlowAdapter()
    server = server_for(adapter, cleanup_timeout=1)
    serving = asyncio.create_task(server.serve())
    await asyncio.sleep(0.05)
    server.receive_signal(signal.SIGTERM)

    report = await asyncio.wait_for(serving, 5)
    assert report.cleanup_timed_out is True
    assert started.is_set() is True
    # Waited out rather than abandoned: exiting at the budget is what loses the state.
    assert report.cleanup_completed is True
    assert adapter.cleanup_finished is True
    assert adapter.masters_closed is True


@pytest.mark.asyncio
async def test_a_failing_cleanup_is_reported_rather_than_swallowed() -> None:
    adapter = StubAdapter(cleanup_error=RuntimeError("lifespan teardown blew up"))
    server = server_for(adapter)
    serving = asyncio.create_task(server.serve())
    await asyncio.sleep(0.05)
    server.receive_signal(signal.SIGTERM)

    report = await asyncio.wait_for(serving, 5)
    assert "lifespan teardown blew up" in report.cleanup_error
    assert report.stage is ShutdownStage.DRAINING


@pytest.mark.asyncio
async def test_a_failing_listener_release_is_reported_rather_than_swallowed() -> None:
    # Previously suppressed outright, so a listener left open looked like a clean stop.
    adapter = StubAdapter(close_error=OSError("cannot close listener"))
    server = server_for(adapter)
    serving = asyncio.create_task(server.serve())
    await asyncio.sleep(0.05)
    server.receive_signal(signal.SIGTERM)

    report = await asyncio.wait_for(serving, 5)
    assert "cannot close listener" in report.cleanup_error


@pytest.mark.asyncio
async def test_a_clean_shutdown_reports_no_error() -> None:
    # The positive control: the three assertions above must not fire on a healthy stop.
    adapter = StubAdapter()
    server = server_for(adapter)
    serving = asyncio.create_task(server.serve())
    await asyncio.sleep(0.05)
    server.receive_signal(signal.SIGTERM)

    report = await asyncio.wait_for(serving, 5)
    assert report.cleanup_error == ""
    assert report.cleanup_completed is True
    assert report.cleanup_timed_out is False
    assert adapter.masters_closed is True


@pytest.mark.asyncio
async def test_a_failing_serving_hook_releases_the_listener() -> None:
    """Past `arm()` the port is answering, so a failed start must not leave it that way.

    Without the teardown the exception escapes with the listener still armed: a port that accepts
    while nobody drives it, which is worse than the start having failed outright.
    """
    adapter = StubAdapter()

    async def refuse() -> None:
        raise RuntimeError("cannot announce")

    server = StandaloneServer(adapter, on_serving=refuse)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="cannot announce"):
        await server.serve()

    assert adapter.stopped_accepting is True
    assert adapter.cleanup_started is True
    assert adapter.masters_closed is True
