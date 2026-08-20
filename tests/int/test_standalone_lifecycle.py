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
from starlette.responses import StreamingResponse
from uvicorn import Config

from app.lifecycle.adapter import UvicornListenerAdapter
from app.lifecycle.entry import StandaloneOptions, run_standalone
from app.lifecycle.listener import LISTENER_NAME, bind_listener
from app.lifecycle.pidfile import PidfileEntry, PidfileError, write_pidfile
from app.lifecycle.shutdown import ShutdownStage
from app.lifecycle.standalone import ShutdownReport, StandaloneServer

# Enough blocks that a truncation lands visibly short rather than off by one.
STREAM_BLOCKS = 9


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

    async def stream() -> StreamingResponse:
        async def blocks() -> AsyncIterator[bytes]:
            # The first block is out — and therefore the response has started — before anything signals. Every other route here is still deciding what to say when the signal lands, which is a different state of the connection and the one already covered.
            yield b"data: block-00\n\n"
            entered.set()
            await hold.wait()
            for index in range(1, STREAM_BLOCKS):
                yield f"data: block-{index:02d}\n\n".encode()
            yield b"data: [DONE]\n\n"

        return StreamingResponse(blocks(), media_type="text/event-stream")

    app.add_api_route("/quick", quick)
    app.add_api_route("/slow", slow)
    app.add_api_route("/stream", stream)
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

    async def pooled(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """A connection the client keeps, the way a real pooled client keeps one between requests.

        The connection is what makes the shutdown path interesting, and only a completed keep-alive request produces one: the protocol object is live and accepted, so a later request on it reaches the application without going anywhere near the listener.
        """
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /quick HTTP/1.1\r\nHost: test\r\n\r\n")
        await writer.drain()
        await _read_response(reader)
        return reader, writer


async def _read_response(reader: asyncio.StreamReader) -> bytes:
    """One whole HTTP response off a connection that stays open, headers and body."""
    head = await reader.readuntil(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n"):
        name, _, value = line.partition(b":")
        if name.lower() == b"content-length":
            length = int(value.strip())
    return head + await reader.readexactly(length)


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
async def test_a_pooled_connection_that_sends_mid_drain_does_not_hold_the_shutdown_open(
    harness: Harness,
) -> None:
    """The drain must end even though a client kept a connection and used it after the signal.

    This is the shape of the incident, end to end: a pooled connection outlives the signal, the client sends on it, and the shutdown has to finish anyway. What it catches is a regression in the mechanism as a whole — removing either half of `stop_admitting` on its own leaves this green, and only removing both turns it red.

    On unmutated code the connection is already closed by the time this writes its second request, so those bytes land in a closed socket and no second handler runs. That is a description of the path taken, not a claim that it is the only path that would save it: the refusal covers the same client arriving a moment earlier, and `test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting` is where that half is pinned on its own.
    """
    serving = await run_until_serving(harness)
    _, pooled_writer = await harness.pooled()
    in_flight = asyncio.create_task(harness.request("/slow"))
    await asyncio.wait_for(harness.entered.wait(), 5)

    harness.server.receive_signal(signal.SIGTERM)
    await asyncio.sleep(0.2)
    pooled_writer.write(b"GET /quick HTTP/1.1\r\nHost: test\r\n\r\n")
    with suppress(Exception):
        await pooled_writer.drain()

    harness.hold.set()
    assert b"200 OK" in await asyncio.wait_for(in_flight, 5)
    report = await asyncio.wait_for(serving, 5)

    # Rung 1 throughout: nothing was cut short to get here.
    assert report.stage is ShutdownStage.DRAINING
    assert report.cancelled_requests == 0
    assert harness.interrupted.is_set() is False
    pooled_writer.close()


@pytest.mark.asyncio
async def test_the_drain_lets_go_of_an_idle_pooled_connection(harness: Harness) -> None:
    """A client holding an idle connection is told to go at the drain, not at the teardown.

    Both halves of that sentence need a witness, and the timing is the harder one. `shutdown_lifespan` closes the connections too, so an EOF observed after `serve()` returns proves nothing about rung 1 — a build that never closed a connection during the drain produces exactly the same EOF a moment later. Measured: with the closing removed, the earlier version of this test passed ten times out of ten.

    So the slow request is here to hold the drain open. While it runs, `serve()` cannot return, the teardown cannot have run, and an EOF on the pooled connection has only one possible source.
    """
    serving = await run_until_serving(harness)
    pooled_reader, pooled_writer = await harness.pooled()
    in_flight = asyncio.create_task(harness.request("/slow"))
    await asyncio.wait_for(harness.entered.wait(), 5)
    assert harness.adapter.connection_count() == 2

    harness.server.receive_signal(signal.SIGTERM)
    # The client's own socket is the proof; a count the server kept could be true of a connection it never actually closed.
    assert await asyncio.wait_for(pooled_reader.read(), 2) == b""
    assert serving.done() is False, "the drain must still be running for that EOF to mean anything"

    harness.hold.set()
    assert b"200 OK" in await asyncio.wait_for(in_flight, 5)
    report = await asyncio.wait_for(serving, 5)
    assert report.connections_asked_to_close == 2
    pooled_writer.close()


@pytest.mark.asyncio
async def test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting(
    harness: Harness,
) -> None:
    """The window the incident fell into: admission is shut, and a pooled client sends anyway.

    Driven against the adapter rather than through a signal because the window is between two of its calls, and a test that waited for the right microsecond would be testing the scheduler. The barrier is reached the same way either way — an accepted connection, a second request on it.
    """
    serving = await run_until_serving(harness)
    pooled_reader, pooled_writer = await harness.pooled()

    # Admission is now shut and, on the rolling path, would reopen on resume.
    await harness.adapter.stop_accepting()
    pooled_writer.write(b"GET /quick HTTP/1.1\r\nHost: test\r\n\r\n")
    await pooled_writer.drain()
    held = asyncio.create_task(_read_response(pooled_reader))
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(held), 0.3)

    # No resume is coming, and saying so is what releases the request.
    assert await harness.adapter.stop_admitting() == 1
    response = await asyncio.wait_for(held, 2)
    assert b"503" in response.split(b"\r\n")[0]
    assert b"connection: close" in response.lower()
    assert b"shutting down" in response
    # The count exists so a shutdown can report this, and nothing else in the suite ever makes it non-zero — the closing of the pooled connections normally beats a request to the barrier, which is exactly why the refusal path needs its own witness here.
    assert harness.adapter.refused_requests() == 1

    harness.server.receive_signal(signal.SIGTERM)
    report = await asyncio.wait_for(serving, 5)
    # Zero, and that is the point: the adapter's counter runs for its whole life, while the report describes one shutdown. This refusal happened before that shutdown began, so reporting it here would attribute somebody else's quiesce to this stop.
    assert report.refused_requests == 0
    pooled_writer.close()


@pytest.mark.asyncio
async def test_rung_one_delivers_a_response_that_had_already_started_streaming(
    harness: Harness,
) -> None:
    """A stream already on the wire when the signal lands must arrive whole.

    The other rung-1 tests here catch a request that has not begun answering yet, and that is a different state of the connection: Uvicorn's `shutdown` closes the transport outright when no response is in progress, and only clears `keep_alive` when one is. Nothing covered the second branch, so cutting a response mid-flight passed every test in the suite while a stream stopped at its second block.

    For this proxy that is the severe end of the failure space, since a complete content block is the delivery unit and a truncated stream is a wrong answer rather than a slow one.
    """
    serving = await run_until_serving(harness)
    reader, writer = await asyncio.open_connection("127.0.0.1", harness.port)
    writer.write(b"GET /stream HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n")
    await writer.drain()
    # The first block is out, so the response has started and cannot be restarted.
    await asyncio.wait_for(harness.entered.wait(), 5)

    harness.server.receive_signal(signal.SIGTERM)
    await asyncio.sleep(0.2)
    harness.hold.set()

    delivered = await asyncio.wait_for(reader.read(), 5)
    writer.close()
    with suppress(Exception):
        await writer.wait_closed()

    assert delivered.count(b"data: block-") == STREAM_BLOCKS
    assert b"data: [DONE]" in delivered
    # Chunked framing has its own terminator, and a stream cut after its last block would still carry every block while losing this.
    assert delivered.endswith(b"0\r\n\r\n")

    report = await asyncio.wait_for(serving, 5)
    assert report.stage is ShutdownStage.DRAINING
    assert report.cancelled_requests == 0


@pytest.mark.asyncio
async def test_a_connection_closed_over_an_unread_request_is_counted_as_severed(
    harness: Harness,
) -> None:
    """The cost the drain imposes on a client that had already sent, told apart from the cost it does not.

    Both connections are idle pooled ones and both are closed, so `connections_asked_to_close` cannot tell them apart. Only one of them has a request sitting in the kernel that nobody has read, and closing that one makes the kernel answer with an RST — the client sees a reset rather than an answer, which for a `POST` is not safely retryable, and those bytes reach nothing else in this process that could report them.

    The write goes through the transport but is never drained, and nothing is awaited between it and the signal. Both halves matter: asyncio's transport sends straight to the kernel when its buffer is empty, and the wakeup that resumes `serve()` was queued before the socket became readable, so the shutdown reaches its peek before the event loop reads those bytes and turns them into a request that would have been refused instead.
    """
    serving = await run_until_serving(harness)
    quiet_reader, quiet_writer = await harness.pooled()
    loud_reader, loud_writer = await harness.pooled()
    assert harness.adapter.connection_count() == 2

    loud_writer.write(b"GET /quick HTTP/1.1\r\nHost: test\r\n\r\n")
    harness.server.receive_signal(signal.SIGTERM)
    report = await asyncio.wait_for(serving, 5)

    assert report.connections_asked_to_close == 2
    # One of the two, not both: the other was genuinely idle, and a probe that could not tell them apart would say two.
    assert report.severed_connections == 1
    # Those bytes never reached the barrier, which is the whole reason this count has to exist alongside that one.
    assert report.refused_requests == 0
    for writer in (quiet_writer, loud_writer):
        writer.close()
    del quiet_reader, loud_reader


@pytest.mark.asyncio
async def test_an_ordinary_idle_connection_is_not_counted_as_severed(harness: Harness) -> None:
    # The negative control for the probe above: without it, "everything is severed" would pass too.
    serving = await run_until_serving(harness)
    _, pooled_writer = await harness.pooled()

    harness.server.receive_signal(signal.SIGTERM)
    report = await asyncio.wait_for(serving, 5)

    assert report.connections_asked_to_close == 1
    assert report.severed_connections == 0
    pooled_writer.close()


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
