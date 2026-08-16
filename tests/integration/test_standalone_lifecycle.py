"""The stand-alone shutdown ladder against a real listener and a real in-flight request.

The ladder's unit tests prove which rung a signal sequence lands on.
These prove the rungs do different things to a request that is still running.
It is either allowed to finish, cut short, or abandoned.
"""

import asyncio
import signal
import socket
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path

import pytest
from fastapi import FastAPI
from uvicorn import Config

from app.lifecycle.entry import StandaloneOptions, run_standalone
from app.lifecycle.listener import LISTENER_NAME, bind_listener
from app.lifecycle.pidfile import PidfileEntry, PidfileError, write_pidfile
from app.lifecycle.shutdown import ShutdownStage
from app.lifecycle.standalone import ShutdownReport, StandaloneServer
from app.server_adapter import UvicornListenerAdapter


def slow_app(
    hold: asyncio.Event,
    entered: asyncio.Event,
    interrupted: asyncio.Event,
    stubborn: asyncio.Event,
) -> FastAPI:
    app = FastAPI()

    async def quick() -> dict[str, str]:
        return {"status": "ok"}

    async def slow() -> dict[str, str]:
        entered.set()
        try:
            await hold.wait()
        except asyncio.CancelledError:
            # The handler observing cancellation is the only proof the request was interrupted.
            # A count of connections told to shut down proves nothing: Uvicorn leaves a running
            # handler alone and merely clears keep_alive.
            interrupted.set()
            if stubborn.is_set():
                # Refuses to unwind, which is what makes rung 3 distinguishable from rung 2.
                await asyncio.sleep(30)
            raise
        return {"status": "done"}

    app.add_api_route("/quick", quick)
    app.add_api_route("/slow", slow)
    return app


class Harness:
    """One bound listener, one server, and the request that keeps it busy."""

    def __init__(self, cleanup_timeout: int = 0) -> None:
        self.hold = asyncio.Event()
        self.entered = asyncio.Event()
        self.interrupted = asyncio.Event()
        self.stubborn = asyncio.Event()
        self.listeners = bind_listener("127.0.0.1", 0)
        self.port = self.listeners.identities()[0].address[1]
        config = Config(
            slow_app(self.hold, self.entered, self.interrupted, self.stubborn),
            log_config=None,
        )
        self.adapter = UvicornListenerAdapter(config, self.listeners)
        self.serving = asyncio.Event()

        async def announce() -> None:
            self.serving.set()

        self.server = StandaloneServer(
            self.adapter,
            cleanup_timeout=cleanup_timeout,
            on_serving=announce,
        )

    async def request(self, path: str) -> bytes:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        try:
            writer.write(f"GET {path} HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n".encode())
            await writer.drain()
            return await reader.read()
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


@pytest.fixture
async def harness() -> AsyncIterator[Harness]:
    made = Harness()
    yield made
    made.hold.set()
    with suppress(Exception):
        made.listeners.close()


async def run_until_serving(harness: Harness) -> asyncio.Task[ShutdownReport]:
    task = asyncio.create_task(harness.server.serve())
    await asyncio.wait_for(harness.serving.wait(), 5)
    return task


@pytest.mark.asyncio
async def test_a_served_request_succeeds_before_any_signal(harness: Harness) -> None:
    serving = await run_until_serving(harness)
    try:
        response = await asyncio.wait_for(harness.request("/quick"), 5)
        assert b"200 OK" in response
    finally:
        harness.server.receive_signal(signal.SIGTERM)
        await asyncio.wait_for(serving, 5)


@pytest.mark.asyncio
async def test_the_first_signal_stops_accepting_but_lets_a_request_finish(
    harness: Harness,
) -> None:
    serving = await run_until_serving(harness)
    in_flight = asyncio.create_task(harness.request("/slow"))
    await asyncio.wait_for(harness.entered.wait(), 5)

    harness.server.receive_signal(signal.SIGTERM)
    # The drain is unbounded, so the server is still waiting on the slow request.
    await asyncio.sleep(0.2)
    assert serving.done() is False

    harness.hold.set()
    response = await asyncio.wait_for(in_flight, 5)
    assert b"200 OK" in response

    report = await asyncio.wait_for(serving, 5)
    assert report.stage is ShutdownStage.DRAINING
    assert report.interrupted_connections == 0
    assert harness.interrupted.is_set() is False
    assert report.cancelled_requests == 0
    # Rung 1 must leave the request alone entirely.
    assert harness.interrupted.is_set() is False


@pytest.mark.asyncio
async def test_a_new_connection_is_refused_once_the_drain_starts(harness: Harness) -> None:
    serving = await run_until_serving(harness)
    in_flight = asyncio.create_task(harness.request("/slow"))
    await asyncio.wait_for(harness.entered.wait(), 5)

    harness.server.receive_signal(signal.SIGTERM)
    await asyncio.sleep(0.2)

    # Accepting has stopped, so a fresh request gets nothing back.
    with pytest.raises((TimeoutError, ConnectionRefusedError, OSError)):
        await asyncio.wait_for(harness.request("/quick"), 0.5)

    harness.hold.set()
    await asyncio.wait_for(in_flight, 5)
    await asyncio.wait_for(serving, 5)


@pytest.mark.asyncio
async def test_a_restart_signal_alone_never_interrupts_the_request(harness: Harness) -> None:
    """The spec: SIGUSR2 信号不会中断优雅关闭."""
    serving = await run_until_serving(harness)
    in_flight = asyncio.create_task(harness.request("/slow"))
    await asyncio.wait_for(harness.entered.wait(), 5)

    for _ in range(3):
        harness.server.receive_signal(signal.SIGUSR2)
    await asyncio.sleep(0.2)
    assert serving.done() is False

    harness.hold.set()
    assert b"200 OK" in await asyncio.wait_for(in_flight, 5)
    report = await asyncio.wait_for(serving, 5)
    assert report.stage is ShutdownStage.DRAINING
    assert report.interrupted_connections == 0


@pytest.mark.asyncio
async def test_a_second_signal_actually_interrupts_the_running_request(harness: Harness) -> None:
    """Rung 2 must reach the handler, not merely the connection.

    The handler is never released, so the only way the shutdown can finish is if the request was
    genuinely interrupted. Counting connections would not show that.
    """
    serving = await run_until_serving(harness)
    in_flight = asyncio.create_task(harness.request("/slow"))
    await asyncio.wait_for(harness.entered.wait(), 5)

    harness.server.receive_signal(signal.SIGTERM)
    await asyncio.sleep(0.1)
    assert harness.interrupted.is_set() is False

    harness.server.receive_signal(signal.SIGTERM)

    report = await asyncio.wait_for(serving, 5)
    assert report.stage is ShutdownStage.INTERRUPTING
    assert harness.interrupted.is_set() is True
    assert report.cancelled_requests >= 1
    in_flight.cancel()
    with suppress(BaseException):
        await in_flight


@pytest.mark.asyncio
async def test_the_third_signal_abandons_a_request_that_ignores_interruption(
    harness: Harness,
) -> None:
    serving = await run_until_serving(harness)
    in_flight = asyncio.create_task(harness.request("/slow"))
    await asyncio.wait_for(harness.entered.wait(), 5)

    # This handler swallows the cancellation and keeps running, so rung 2 cannot end it.
    harness.stubborn.set()

    harness.server.receive_signal(signal.SIGTERM)
    await asyncio.sleep(0.05)
    harness.server.receive_signal(signal.SIGTERM)
    await asyncio.wait_for(harness.interrupted.wait(), 5)
    # Rung 2 interrupted it but cannot finish, because the handler refuses to unwind.
    await asyncio.sleep(0.2)
    assert serving.done() is False

    harness.server.receive_signal(signal.SIGTERM)

    # Rung 3 stops waiting, which is the only difference from rung 2.
    report = await asyncio.wait_for(serving, 5)
    assert report.stage is ShutdownStage.FINALIZING
    assert report.cleanup_timed_out is False
    in_flight.cancel()
    with suppress(BaseException):
        await in_flight


@pytest.mark.asyncio
async def test_a_burst_of_signals_does_not_stall_the_shutdown(harness: Harness) -> None:
    """Three signals inside one iteration must not leave the descent waiting on a spent event.

    An operator hammering Ctrl-C is the ordinary case, not an exotic one.
    """
    serving = await run_until_serving(harness)
    in_flight = asyncio.create_task(harness.request("/slow"))
    await asyncio.wait_for(harness.entered.wait(), 5)

    for _ in range(3):
        harness.server.receive_signal(signal.SIGTERM)

    report = await asyncio.wait_for(serving, 5)
    assert report.stage is ShutdownStage.FINALIZING
    assert report.cancelled_requests >= 1
    in_flight.cancel()


@pytest.mark.asyncio
async def test_shutdown_returns_rather_than_exiting_the_process(harness: Harness) -> None:
    # The spec forbids an unguarded exit: serve() completes and hands a report back.
    serving = await run_until_serving(harness)
    harness.server.receive_signal(signal.SIGINT)
    report = await asyncio.wait_for(serving, 5)
    assert isinstance(report, ShutdownReport)


@pytest.mark.asyncio
async def test_the_listener_is_released_after_shutdown(harness: Harness) -> None:
    serving = await run_until_serving(harness)
    harness.server.receive_signal(signal.SIGTERM)
    await asyncio.wait_for(serving, 5)

    # The port is free again, so a replacement can take it without SO_REUSEPORT tricks.
    replacement = bind_listener("127.0.0.1", harness.port, reuse_port=False)
    assert replacement.identities()[0].name == LISTENER_NAME
    replacement.close()


@pytest.mark.asyncio
async def test_a_failed_handover_leaves_the_predecessor_its_pidfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A start that never became a server must not strip the live process of its record.

    The successor overwrites the pidfile before signalling, so a failure in between would otherwise
    leave the predecessor — still serving — with no file naming it, and the next `--restart` with
    nothing to find.
    """
    predecessor = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    pidfile = tmp_path / "standalone.pid"
    try:
        await asyncio.sleep(0.5)
        write_pidfile(pidfile, predecessor.pid)
        recorded = pidfile.read_text(encoding="utf-8")

        def refuse(entry: PidfileEntry) -> bool:
            # Standing in for the predecessor having exited and its PID been reused: from here on,
            # re-deriving the token yields somebody else's. Restoring must not do that.
            def foreign_token(pid: int) -> str:
                del pid
                return "999999"

            monkeypatch.setattr("app.lifecycle.pidfile.process_start_token", foreign_token)
            raise PidfileError("handover failed")

        monkeypatch.setattr("app.lifecycle.entry.signal_restart", refuse)
        options = StandaloneOptions(port=free_port(), pidfile=pidfile, restart=True)

        with pytest.raises(PidfileError, match="handover failed"):
            await run_standalone(FastAPI(), options)

        # Byte-identical, token included: a re-derived record would carry "999999" instead.
        assert pidfile.read_text(encoding="utf-8") == recorded
    finally:
        predecessor.kill()
        predecessor.wait(timeout=5)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
