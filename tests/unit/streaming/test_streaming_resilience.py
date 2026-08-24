import asyncio
from collections.abc import AsyncIterator, Coroutine, Generator
from contextlib import suppress
from typing import Any, Literal

import anyio
import pytest

from app.streaming.buffered_retry import BufferLimitExceeded, collect_with_limit
from app.streaming.delayed_commit import delayed_first_item
from app.streaming.idle_timeout import StreamIdleTimeoutError
from app.streaming.keepalive import (
    finish_stream_cleanup,
    keepalive_stream,
    raise_with_cleanup_under,
    session_liveness_stream,
)


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
    """And keeps the cause the pull already had, which this used to assert away.

    A review pointed out that asserting the close failure *becomes* `__cause__` pins the exact loss `raise_with_cleanup_under` exists to prevent: with a pull that carried its own explicit cause, that spelling made the root unreachable. The pull here now carries one, so the assertion says both — the root the author chose, and the close failure recorded under it.
    """
    root = OSError("[Errno 104] Connection reset by peer")

    class PullAndCloseFail(AsyncIterator[bytes]):
        async def __anext__(self) -> bytes:
            raise ValueError("pull failed") from root

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

    assert exc_info.value.__cause__ is root, "the reason the pull failed is still the reason"
    assert isinstance(exc_info.value.__context__, RuntimeError)
    assert str(exc_info.value.__context__) == "close failed"


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


def test_a_cleanup_failure_never_displaces_a_cause_the_author_chose() -> None:
    """`raise primary from cleanup_error` is the obvious spelling, and it silently deletes an explicit `__cause__`.

    The exit that started cleanup often already carries the reason it happened — `raise UpstreamError(...) from OSError(...)` is the shape this proxy's own normalisation produces. Overwriting that with "and then the close also failed" trades the cause an operator needs for a consequence of it. Measured before this helper existed: the root was no longer reachable from the chain at all.

    Both fields are used because they mean different things. `__cause__` is "this is why", which belongs to whoever raised the primary; `__context__` is "this also happened while unwinding", which is what a cleanup failure is.
    """
    root = OSError("[Errno 104] Connection reset by peer")
    primary = RuntimeError("upstream tore the stream")
    primary.__cause__ = root
    cleanup = RuntimeError("and the body could not be closed")

    with pytest.raises(RuntimeError) as caught:
        raise_with_cleanup_under(primary, cleanup)

    assert caught.value is primary
    assert caught.value.__cause__ is root, "the author's cause survives"
    assert caught.value.__context__ is cleanup, "and the cleanup failure is still recorded"


def test_a_cleanup_failure_becomes_the_cause_when_nothing_is_there() -> None:
    """With no cause of its own, the primary gets one — which is what makes the pair readable at all."""
    primary = RuntimeError("upstream tore the stream")
    cleanup = RuntimeError("and the body could not be closed")

    with pytest.raises(RuntimeError) as caught:
        raise_with_cleanup_under(primary, cleanup)

    assert caught.value is primary
    assert caught.value.__cause__ is cleanup


def test_a_cleanup_failure_does_not_displace_an_earlier_one() -> None:
    """Two cleanup failures on one primary. The first used to vanish from the chain entirely.

    `__context__` holds one link, so writing the second over the first is a loss rather than an update. The second now carries the first, which keeps both reachable and in the order they happened.
    """
    primary = RuntimeError("upstream tore the stream")
    primary.__cause__ = OSError("[Errno 104] Connection reset by peer")
    first = RuntimeError("the body could not be closed")
    second = RuntimeError("and neither could the pull")

    with pytest.raises(RuntimeError):
        raise_with_cleanup_under(primary, first)
    with pytest.raises(RuntimeError):
        raise_with_cleanup_under(primary, second)

    assert primary.__context__ is second
    assert second.__context__ is first, "the earlier cleanup failure is still reachable"


def _reachable(error: BaseException) -> list[str]:
    """Everything reachable from `error` by either link.

    Both links, because the question these tests ask is reachability. Following `__cause__` in preference — which is what a printer does, and what `hand_over.one_line` does — hid the entire result of one of them while it was being written.
    """
    found: list[str] = []
    seen: set[int] = set()
    stack: list[BaseException | None] = [error]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        found.append(str(current))
        stack.extend([current.__cause__, current.__context__])
    return found


def test_an_earlier_cleanup_survives_a_second_one_raised_while_the_primary_propagates() -> None:
    """The shape the call sites actually produce, which the quiet two-calls-in-a-row test could not reach.

    A close that fails inside `except primary` gets `primary` as its own implicit `__context__` before this helper sees it. That made `cleanup_error.__context__ is None` false, so the carry — written for exactly this case — skipped it, and the earlier cleanup failure was dropped after all. A review measured `earlier_reachable=False` on the version that had a passing test for the quiet case.

    Clearing that temporary edge first is what makes the slot readable. Re-raising drops it anyway, so nothing is lost by doing it here.
    """
    root = Exception("root")
    earlier = Exception("earlier cleanup")
    primary = Exception("primary")
    primary.__cause__ = root
    primary.__context__ = earlier

    with pytest.raises(Exception) as caught:
        try:
            raise primary
        except Exception:
            try:
                raise Exception("new cleanup")
            except Exception as new_cleanup:
                raise_with_cleanup_under(primary, new_cleanup)

    reachable = _reachable(caught.value)
    assert "new cleanup" in reachable
    assert "earlier cleanup" in reachable, "the earlier cleanup failure is still reachable"
    assert "root" in reachable, "and so is the cause the author chose"


def test_a_cleanup_that_already_points_at_the_primary_is_noted_rather_than_linked() -> None:
    """`cleanup.__cause__ = primary` is a back-edge Python will not undo, unlike the implicit one.

    Linking the other direction would close a two-object cycle that survives the re-raise — a real one, not the temporary shape above. The pairing still has to be recorded, so it goes in a note, which says the same thing and cannot be walked in circles.
    """
    primary = Exception("primary")
    cleanup = Exception("cleanup")
    cleanup.__cause__ = primary

    with pytest.raises(Exception) as caught:
        raise_with_cleanup_under(primary, cleanup)

    assert caught.value is primary
    assert caught.value.__cause__ is None, "no link back, because that one would be a cycle"
    assert caught.value.__context__ is None
    assert any("cleanup" in note for note in getattr(caught.value, "__notes__", [])), (
        "and the cleanup failure is still on the record"
    )


def test_pairing_an_exception_with_itself_does_not_make_it_its_own_cause() -> None:
    """Python accepts `raise x from x`; a reader following the chain then walks in place.

    Nothing is being recorded when the two are the same object — the cleanup failure *is* the exit — so it is raised as it stands.
    """
    only = RuntimeError("the same object on both sides")

    with pytest.raises(RuntimeError) as caught:
        raise_with_cleanup_under(only, only)

    assert caught.value is only
    assert caught.value.__cause__ is not only
    assert caught.value.__context__ is not only


@pytest.mark.asyncio
async def test_a_falsey_primary_is_still_the_exit_that_propagates() -> None:
    """`primary or cleanup_cancellation` conflates "is there one" with "which one wins".

    A `BaseException` subclass may define `__bool__`, and `or` then silently promotes the cleanup failure over the exception that actually ended the stream — inverting the exit priority the comment beside it claims to state. No exception exercised in this repository does this, which is exactly why it would not be noticed — that is a claim about the sample, not an exhaustive statement about the standard library.
    """

    class Falsey(Exception):
        def __bool__(self) -> bool:
            return False

    class FalseyPullAndCloseFail(AsyncIterator[bytes]):
        """Shaped like `PullAndCloseFail` above; only the pull's truthiness differs."""

        async def __anext__(self) -> bytes:
            raise Falsey("upstream tore the stream")

        async def aclose(self) -> None:
            raise RuntimeError("and the body could not be closed")

    stream = session_liveness_stream(
        FalseyPullAndCloseFail(),
        heartbeat_interval_seconds=0,
        heartbeat=b"heartbeat",
        upstream_idle_timeout_seconds=1,
    )
    with pytest.raises(Falsey) as caught:
        await anext(stream)

    assert isinstance(caught.value.__cause__, RuntimeError), "the close failure is recorded under it"
    assert str(caught.value.__cause__) == "and the body could not be closed"


@pytest.mark.asyncio
async def test_cleanup_that_fails_after_a_cancellation_leaves_no_unconsumed_future() -> None:
    """The chained exception was right, and the operator got a second, contradictory line beside it.

    `asyncio.shield` keeps cleanup running through a cancellation and abandons its outer future doing so. When the cleanup then *fails*, that abandoned future reports the failure as never consumed — `RuntimeError exception in shielded future` on stderr — while this function is at the same moment returning the same exception for the caller to chain properly. Two accounts of one failure, one of them reading like a bug in the proxy, in the middle of a slice whose whole subject is diagnostic clarity.

    Both halves are needed to see it: a cancellation *and* a cleanup that fails afterwards. A cancel-then-succeed leaves nothing to report, which is why the second-cancel regression next door stayed green through this.

    Driven with events rather than sleeps so "the cancellation landed inside the close" is a precondition rather than a race.
    """
    reports: list[dict[str, Any]] = []
    asyncio.get_running_loop().set_exception_handler(lambda loop, context: reports.append(context))

    release = asyncio.Event()
    entered = asyncio.Event()

    class SlowFailingClose(AsyncIterator[bytes]):
        async def __anext__(self) -> bytes:
            raise StopAsyncIteration

        async def aclose(self) -> None:
            entered.set()
            await release.wait()
            raise RuntimeError("close failed")

    stream = SlowFailingClose()

    async def cleanup() -> None:
        await finish_stream_cleanup(None, stream)

    task = asyncio.create_task(cleanup())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    # Only now does the close fail, which is the half that produces the report.
    release.set()
    with suppress(BaseException):
        await task
    # The abandoned future reports from a callback, so give the loop room to run them.
    for _ in range(5):
        await asyncio.sleep(0)

    assert reports == [], f"the loop was told about an exception nobody read: {reports}"
