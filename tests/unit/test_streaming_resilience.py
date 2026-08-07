import asyncio
from collections.abc import AsyncIterator, Coroutine, Generator
from typing import Any, Literal

import anyio
import pytest

from app.streaming.buffered_retry import BufferLimitExceeded, collect_with_limit
from app.streaming.delayed_commit import delayed_first_item
from app.streaming.idle_timeout import StreamIdleTimeoutError
from app.streaming.keepalive import keepalive_stream, session_liveness_stream


@pytest.mark.asyncio
async def test_keepalive_emits_heartbeat_during_silence() -> None:
    async def source() -> AsyncIterator[bytes]:
        await anyio.sleep(0.03)
        yield b"data"

    stream = keepalive_stream(source(), interval_seconds=0.01, heartbeat=b": ping\n\n")
    frames: list[bytes] = []
    try:
        for _ in range(5):
            frame = await anext(stream)
            frames.append(frame)
            if frame == b"data":
                break
    finally:
        await stream.aclose()
    assert frames[-1] == b"data"
    assert frames.count(b": ping\n\n") >= 2


@pytest.mark.asyncio
async def test_keepalive_close_waits_for_upstream_cleanup() -> None:
    cleaned = anyio.Event()

    async def stalled() -> AsyncIterator[bytes]:
        try:
            await anyio.sleep_forever()
            yield b"unreachable"
        finally:
            cleaned.set()

    stream = keepalive_stream(
        stalled(),
        interval_seconds=0.01,
        heartbeat=b": ping\n\n",
    )

    assert await anext(stream) == b": ping\n\n"
    await stream.aclose()

    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_session_liveness_emits_multiple_heartbeats_without_restarting_upstream() -> None:
    release = anyio.Event()
    next_attempts = 0

    async def source() -> AsyncIterator[bytes]:
        nonlocal next_attempts
        next_attempts += 1
        await release.wait()
        yield b"data"

    stream = session_liveness_stream(
        source(),
        heartbeat_interval_seconds=0.01,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )

    assert [await anext(stream) for _ in range(3)] == [b"heartbeat"] * 3
    assert next_attempts == 1

    release.set()
    assert await anext(stream) == b"data"
    await stream.aclose()


@pytest.mark.asyncio
async def test_session_liveness_preserves_upstream_order_after_silence() -> None:
    async def source() -> AsyncIterator[bytes]:
        await anyio.sleep(0.025)
        yield b"first"
        yield b"second"

    stream = session_liveness_stream(
        source(),
        heartbeat_interval_seconds=0.01,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )

    frames = [item async for item in stream]

    assert frames[-2:] == [b"first", b"second"]
    assert len(frames[:-2]) >= 2
    assert all(frame == b"heartbeat" for frame in frames[:-2])


@pytest.mark.asyncio
async def test_session_liveness_stops_when_upstream_ends() -> None:
    async def source() -> AsyncIterator[bytes]:
        if False:
            yield b"unreachable"

    stream = session_liveness_stream(
        source(),
        heartbeat_interval_seconds=0.01,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )

    assert [item async for item in stream] == []


@pytest.mark.asyncio
async def test_session_liveness_enforces_upstream_idle_deadline() -> None:
    cleaned = anyio.Event()

    async def stalled() -> AsyncIterator[bytes]:
        try:
            await anyio.sleep_forever()
            yield b"unreachable"
        finally:
            cleaned.set()

    stream = session_liveness_stream(
        stalled(),
        heartbeat_interval_seconds=0.005,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=0.03,
    )
    frames: list[bytes] = []

    with pytest.raises(StreamIdleTimeoutError, match=r"0\.03s"):
        async for frame in stream:
            frames.append(frame)

    assert len(frames) >= 2
    assert all(frame == b"heartbeat" for frame in frames)
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_session_liveness_resets_idle_deadline_after_upstream_activity() -> None:
    async def source() -> AsyncIterator[bytes]:
        await anyio.sleep(0.03)
        yield b"first"
        await anyio.sleep(0.03)
        yield b"second"

    stream = session_liveness_stream(
        source(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=0.05,
    )

    assert [item async for item in stream] == [b"first", b"second"]


@pytest.mark.asyncio
async def test_session_liveness_does_not_count_downstream_pause_as_upstream_idle() -> None:
    async def source() -> AsyncIterator[bytes]:
        yield b"first"
        await anyio.sleep(0.005)
        yield b"second"

    stream = session_liveness_stream(
        source(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=0.03,
    )

    assert await anext(stream) == b"first"
    await anyio.sleep(0.04)
    assert await anext(stream) == b"second"


@pytest.mark.asyncio
async def test_session_liveness_prefers_item_completed_at_idle_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def source() -> AsyncIterator[bytes]:
        yield b"data"

    async def timeout_after_tasks_complete(
        tasks: set[asyncio.Task[bytes]],
        *,
        timeout: float | None,
    ) -> tuple[set[asyncio.Task[bytes]], set[asyncio.Task[bytes]]]:
        del timeout
        await asyncio.gather(*tasks)
        return set(), tasks

    monkeypatch.setattr(asyncio, "wait", timeout_after_tasks_complete)
    stream = session_liveness_stream(
        source(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=0.000_001,
    )

    assert await anext(stream) == b"data"


@pytest.mark.asyncio
async def test_session_liveness_close_closes_upstream_iterator() -> None:
    cleaned = anyio.Event()

    async def stalled() -> AsyncIterator[bytes]:
        try:
            await anyio.sleep_forever()
            yield b"unreachable"
        finally:
            cleaned.set()

    stream = session_liveness_stream(
        stalled(),
        heartbeat_interval_seconds=0.01,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )

    assert await anext(stream) == b"heartbeat"
    await stream.aclose()

    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_session_liveness_cancellation_closes_upstream_iterator() -> None:
    started = anyio.Event()
    cleaned = anyio.Event()

    async def stalled() -> AsyncIterator[bytes]:
        try:
            started.set()
            await anyio.sleep_forever()
            yield b"unreachable"
        finally:
            cleaned.set()

    stream = session_liveness_stream(
        stalled(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )
    consumer = asyncio.create_task(anext(stream))
    await started.wait()

    consumer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer

    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_session_liveness_second_cancellation_does_not_interrupt_cleanup() -> None:
    pull_started = anyio.Event()
    cleanup_started = anyio.Event()
    allow_cleanup = anyio.Event()
    cleanup_finished = anyio.Event()

    async def stalled() -> AsyncIterator[bytes]:
        try:
            pull_started.set()
            await anyio.sleep_forever()
            yield b"unreachable"
        finally:
            cleanup_started.set()
            await allow_cleanup.wait()
            cleanup_finished.set()

    stream = session_liveness_stream(
        stalled(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )
    consumer = asyncio.create_task(anext(stream))
    await pull_started.wait()

    consumer.cancel()
    await cleanup_started.wait()
    consumer.cancel()
    allow_cleanup.set()

    with pytest.raises(asyncio.CancelledError):
        await consumer

    assert cleanup_finished.is_set()


@pytest.mark.asyncio
async def test_session_liveness_keeps_consumer_cancellation_primary_when_close_fails() -> None:
    pull_started = anyio.Event()

    class CloseFailsAfterCancellation(AsyncIterator[bytes]):
        async def __anext__(self) -> bytes:
            pull_started.set()
            await anyio.sleep_forever()
            return b"unreachable"

        async def aclose(self) -> None:
            raise RuntimeError("close failed")

    stream = session_liveness_stream(
        CloseFailsAfterCancellation(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )
    consumer = asyncio.create_task(anext(stream))
    await pull_started.wait()

    consumer.cancel()

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await consumer

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "close failed"


@pytest.mark.asyncio
async def test_session_liveness_chains_pull_unwind_failure_after_cancellation() -> None:
    pull_started = anyio.Event()
    closed = False

    class PullFinalizeFails(AsyncIterator[bytes]):
        async def __anext__(self) -> bytes:
            try:
                pull_started.set()
                await anyio.sleep_forever()
                return b"unreachable"
            finally:
                await anyio.sleep(0)
                raise RuntimeError("pull finalization failed")

        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    stream = session_liveness_stream(
        PullFinalizeFails(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )
    consumer = asyncio.create_task(anext(stream))
    await pull_started.wait()

    consumer.cancel()

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await consumer

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "pull finalization failed"
    assert closed is True


@pytest.mark.asyncio
async def test_session_liveness_keeps_upstream_error_primary_when_close_fails() -> None:
    class PullAndCloseFail(AsyncIterator[bytes]):
        async def __anext__(self) -> bytes:
            raise ValueError("pull failed")

        async def aclose(self) -> None:
            raise RuntimeError("close failed")

    stream = session_liveness_stream(
        PullAndCloseFail(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )

    with pytest.raises(ValueError, match="pull failed") as exc_info:
        await anext(stream)

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "close failed"


@pytest.mark.asyncio
async def test_session_liveness_propagates_close_error_without_primary_error() -> None:
    class CloseFails(AsyncIterator[bytes]):
        async def __anext__(self) -> bytes:
            raise StopAsyncIteration

        async def aclose(self) -> None:
            raise RuntimeError("close failed")

    stream = session_liveness_stream(
        CloseFails(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )

    with pytest.raises(RuntimeError, match="close failed"):
        await anext(stream)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["item", "stop", "error"])
async def test_session_liveness_cancellation_observes_synchronously_completed_pull(
    monkeypatch: pytest.MonkeyPatch,
    outcome: Literal["item", "stop", "error"],
) -> None:
    loop = asyncio.get_running_loop()
    pull_created = False
    pull_awaited = False

    class ObservedTask(asyncio.Task[bytes]):
        def __await__(self) -> Generator[Any, None, bytes]:
            nonlocal pull_awaited
            pull_awaited = True
            return super().__await__()

    def create_observed_task(
        coroutine: Coroutine[Any, Any, bytes],
    ) -> asyncio.Task[bytes]:
        nonlocal pull_created
        pull_created = True
        return ObservedTask(coroutine)

    async def source() -> AsyncIterator[bytes]:
        if outcome == "item":
            yield b"late item"
        elif outcome == "error":
            raise RuntimeError("upstream failed while consumer was cancelled")

    async def cancel_after_pull_settles(
        tasks: set[asyncio.Task[bytes]],
        *,
        timeout: float | None,
    ) -> tuple[set[asyncio.Task[bytes]], set[asyncio.Task[bytes]]]:
        del timeout
        while not all(task.done() for task in tasks):
            await asyncio.sleep(0)
        consumer = asyncio.current_task()
        assert consumer is not None
        consumer.cancel()
        await asyncio.sleep(0)
        raise AssertionError("consumer cancellation was not delivered")

    monkeypatch.setattr(asyncio, "create_task", create_observed_task)
    monkeypatch.setattr(asyncio, "wait", cancel_after_pull_settles)
    stream = session_liveness_stream(
        source(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )
    consumer = loop.create_task(anext(stream))

    with pytest.raises(asyncio.CancelledError):
        await consumer

    assert pull_created is True
    assert pull_awaited is True


@pytest.mark.asyncio
async def test_session_liveness_can_disable_heartbeats() -> None:
    async def source() -> AsyncIterator[bytes]:
        await anyio.sleep(0.02)
        yield b"data"

    stream = session_liveness_stream(
        source(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )

    assert [item async for item in stream] == [b"data"]


@pytest.mark.asyncio
async def test_delayed_commit_waits_for_first_item_only() -> None:
    async def source() -> AsyncIterator[int]:
        yield 1
        yield 2

    first, remainder = await delayed_first_item(source(), timeout_seconds=1)
    assert first == 1
    assert [item async for item in remainder] == [2]


@pytest.mark.asyncio
async def test_buffered_retry_enforces_memory_cap() -> None:
    async def source() -> AsyncIterator[bytes]:
        yield b"1234"
        yield b"5678"

    with pytest.raises(BufferLimitExceeded):
        await collect_with_limit(source(), cap_bytes=7)
