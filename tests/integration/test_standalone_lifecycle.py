"""The stand-alone shutdown ladder against a real listener and a real in-flight request.

The ladder's unit tests prove which rung a signal sequence lands on.
These prove the rungs do different things to a request that is still running.
It is either allowed to finish, cut short, or abandoned.
"""

import asyncio
import signal
from collections.abc import AsyncIterator
from contextlib import suppress

import pytest
from fastapi import FastAPI
from uvicorn import Config

from app.lifecycle.listener import LISTENER_NAME, bind_listener
from app.lifecycle.shutdown import ShutdownStage
from app.lifecycle.standalone import ShutdownReport, StandaloneServer
from app.server_adapter import UvicornListenerAdapter


def slow_app(hold: asyncio.Event, entered: asyncio.Event) -> FastAPI:
    app = FastAPI()

    async def quick() -> dict[str, str]:
        return {"status": "ok"}

    async def slow() -> dict[str, str]:
        entered.set()
        await hold.wait()
        return {"status": "done"}

    app.add_api_route("/quick", quick)
    app.add_api_route("/slow", slow)
    return app


class Harness:
    """One bound listener, one server, and the request that keeps it busy."""

    def __init__(self, cleanup_timeout: int = 0) -> None:
        self.hold = asyncio.Event()
        self.entered = asyncio.Event()
        self.listeners = bind_listener("127.0.0.1", 0)
        self.port = self.listeners.identities()[0].address[1]
        config = Config(slow_app(self.hold, self.entered), log_config=None)
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
            writer.write(
                f"GET {path} HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n".encode()
            )
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
    assert report.abandoned_requests == 0


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
async def test_a_second_signal_interrupts_without_abandoning(harness: Harness) -> None:
    serving = await run_until_serving(harness)
    in_flight = asyncio.create_task(harness.request("/slow"))
    await asyncio.wait_for(harness.entered.wait(), 5)

    harness.server.receive_signal(signal.SIGTERM)
    await asyncio.sleep(0.1)
    harness.server.receive_signal(signal.SIGTERM)
    await asyncio.sleep(0.2)

    # Interrupting the connection does not end a handler that is still awaiting something.
    # That is precisely why a third rung exists, and why this one must not cancel.
    assert serving.done() is False

    harness.hold.set()
    report = await asyncio.wait_for(serving, 5)
    assert report.stage is ShutdownStage.INTERRUPTING
    assert report.interrupted_connections >= 1
    assert report.abandoned_requests == 0
    in_flight.cancel()


@pytest.mark.asyncio
async def test_the_third_signal_abandons_a_request_that_ignores_interruption(
    harness: Harness,
) -> None:
    serving = await run_until_serving(harness)
    in_flight = asyncio.create_task(harness.request("/slow"))
    await asyncio.wait_for(harness.entered.wait(), 5)

    for _ in range(3):
        harness.server.receive_signal(signal.SIGTERM)
        await asyncio.sleep(0.05)

    # The request is never released, yet the server stops waiting for it.
    report = await asyncio.wait_for(serving, 5)
    assert report.stage is ShutdownStage.FINALIZING
    assert report.abandoned_requests >= 1
    # Cleanup still ran: the point of cancelling rather than walking away.
    assert report.cleanup_timed_out is False
    in_flight.cancel()


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
    assert report.abandoned_requests >= 1
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
