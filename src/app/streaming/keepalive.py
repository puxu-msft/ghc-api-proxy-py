import asyncio
import sys
from collections.abc import AsyncGenerator, AsyncIterator

from app.streaming.idle_timeout import StreamIdleTimeoutError


async def session_liveness_stream[T](
    stream: AsyncIterator[T],
    *,
    heartbeat_interval_seconds: float,
    heartbeat: T,
    upstream_idle_timeout_seconds: float,
) -> AsyncGenerator[T]:
    """Keep the downstream active while one upstream ``anext`` remains in flight."""
    pending: asyncio.Task[T] | None = None
    loop = asyncio.get_running_loop()
    upstream_idle_deadline: float | None = None
    heartbeat_deadline: float | None = None

    async def next_item() -> T:
        return await anext(stream)

    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(next_item())
                upstream_idle_deadline = _deadline(loop, upstream_idle_timeout_seconds)
                heartbeat_deadline = _deadline(loop, heartbeat_interval_seconds)

            timeout = _next_timeout(loop, heartbeat_deadline, upstream_idle_deadline)
            await asyncio.wait({pending}, timeout=timeout)
            if pending.done():
                try:
                    item = pending.result()
                except StopAsyncIteration:
                    return
                pending = None
                yield item
                continue

            now = loop.time()
            if upstream_idle_deadline is not None and now >= upstream_idle_deadline:
                raise StreamIdleTimeoutError(
                    f"No upstream stream item received for {upstream_idle_timeout_seconds:g}s"
                )
            if heartbeat_deadline is not None and now >= heartbeat_deadline:
                heartbeat_deadline = now + heartbeat_interval_seconds
                yield heartbeat
    finally:
        # Exit priority: existing primary, cancellation received during cleanup, cleanup failure.
        # A secondary failure remains the explicit cause.
        primary = sys.exception()
        if isinstance(primary, GeneratorExit):
            primary = None
        cleanup_error, cleanup_cancellation = await _finish_cleanup(pending, stream)
        primary = primary or cleanup_cancellation
        if primary is not None:
            if cleanup_error is not None:
                raise primary from cleanup_error
            if cleanup_cancellation is not None:
                raise primary
        elif cleanup_error is not None:
            raise cleanup_error


async def _finish_cleanup[T](
    pending: asyncio.Task[T] | None,
    stream: AsyncIterator[T],
) -> tuple[BaseException | None, asyncio.CancelledError | None]:
    """Finish cleanup before returning any cancellation or cleanup failure."""

    async def cleanup() -> None:
        if pending is not None:
            await _cancel_and_observe(pending)
        await _close_iterator(stream)

    cleanup_task = asyncio.create_task(cleanup())
    current = asyncio.current_task()
    cancelling_seen = current.cancelling() if current is not None else 0
    deferred_cancellation: asyncio.CancelledError | None = None

    while not cleanup_task.done():
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError as exc:
            cancelling_now = current.cancelling() if current is not None else cancelling_seen
            if cancelling_now > cancelling_seen:
                if deferred_cancellation is None:
                    deferred_cancellation = exc
            elif cleanup_task.done():
                break
            cancelling_seen = cancelling_now
        except BaseException:
            break

    try:
        cleanup_task.result()
    except BaseException as exc:
        return exc, deferred_cancellation
    return None, deferred_cancellation


async def _cancel_and_observe[T](pending: asyncio.Task[T]) -> None:
    """Settle a pull task without replacing the exit that initiated cleanup."""
    if not pending.done():
        pending.cancel()

    current = asyncio.current_task()
    cancelling_before = current.cancelling() if current is not None else 0
    try:
        await pending
    except asyncio.CancelledError:
        if current is not None and current.cancelling() > cancelling_before:
            raise
        # The pull task's own cancellation is expected during cleanup. An outer
        # cancellation already in flight resumes after this finally block.
    except Exception:
        # Closing, cancellation, or the exception already leaving the stream
        # takes priority, but retrieving a concurrently settled error is required.
        pass


def _deadline(
    loop: asyncio.AbstractEventLoop,
    interval_seconds: float,
) -> float | None:
    if interval_seconds <= 0:
        return None
    return loop.time() + interval_seconds


def _next_timeout(
    loop: asyncio.AbstractEventLoop,
    *deadlines: float | None,
) -> float | None:
    enabled = [deadline for deadline in deadlines if deadline is not None]
    if not enabled:
        return None
    return max(0.0, min(enabled) - loop.time())


async def _close_iterator[T](stream: AsyncIterator[T]) -> None:
    close = getattr(stream, "aclose", None)
    if close is not None:
        await close()


async def keepalive_stream(
    stream: AsyncIterator[bytes],
    *,
    interval_seconds: float,
    heartbeat: bytes,
) -> AsyncGenerator[bytes]:
    inner = session_liveness_stream(
        stream,
        heartbeat_interval_seconds=interval_seconds,
        heartbeat=heartbeat,
        upstream_idle_timeout_seconds=0,
    )
    try:
        async for item in inner:
            yield item
    finally:
        await inner.aclose()
