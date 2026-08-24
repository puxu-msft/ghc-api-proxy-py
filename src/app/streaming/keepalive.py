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
        cleanup_error, cleanup_cancellation = await finish_stream_cleanup(
            pending, stream, primary=primary
        )
        # `is None` rather than `or`, which conflates "is there one" with "which wins". A `BaseException` subclass may define a falsey `__bool__`, and `or` then picks the cleanup failure — measured on the real `_counted_upstream`: a falsey primary came out as `CleanupError` with the primary demoted to its context, which is precisely the exit-priority this comment claims to state.
        if primary is None:
            primary = cleanup_cancellation
        if primary is not None:
            if cleanup_error is not None:
                raise_with_cleanup_under(primary, cleanup_error)
            if cleanup_cancellation is not None:
                raise primary
        elif cleanup_error is not None:
            raise cleanup_error


def _reaches(start: BaseException, target: BaseException) -> bool:
    """Whether `target` is already somewhere under `start`, following both links.

    Asked before writing a link, because the chain is walked by readers that do not all guard against cycles — this module's own `one_line` does, `traceback` does, and a hand-written loop in a log formatter is exactly the kind of thing that does not.
    """
    seen: set[int] = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current is target:
            return True
        if id(current) in seen:
            continue
        seen.add(id(current))
        stack.extend(link for link in (current.__cause__, current.__context__) if link is not None)
    return False


def raise_with_cleanup_under(primary: BaseException, cleanup_error: BaseException) -> None:
    """Re-raise the exit that started cleanup, with the cleanup failure recorded under it and nothing already reachable lost.

    `raise primary from cleanup_error` is the obvious spelling and it overwrites `primary.__cause__`. A review constructed `PrimaryError from RootError`, let the close fail, and found `RootError` no longer reachable from the chain at all — the explicit cause an author had chosen, replaced by a consequence of the ending it described.

    So the cleanup failure goes on `__cause__` only when nothing is there, and on `__context__` otherwise. `__context__` is the weaker link and the right one for "this also happened while unwinding"; overwriting it is what Python's own implicit chaining does anyway.

    **Three cases the first version got wrong, all found by a review probing the helper rather than its callers.**

    *The same object on both sides.* `raise primary from primary` is accepted by Python and produces an exception that is its own cause; a reader following the chain then walks in place. Nothing is being recorded in that case anyway — the cleanup failure *is* the exit — so it is simply raised.

    *An existing `__context__`.* Overwriting it dropped the earlier one entirely, which a second cleanup failure on the same primary reproduced: the first became unreachable. It is now carried under the new one instead, so both stay in the chain in the order they happened. A test that calls this helper twice in a row proves only the quiet case — a review measured that the live one, where the second cleanup is raised *while the primary is propagating*, took a different branch and lost the first anyway.

    *A link that would close a loop.* This one took two attempts and both failures are worth keeping. The first version checked `_reaches` before every write, and fired on the **normal** path — a close that fails while the primary is being handled gets `primary` as its own implicit `__context__`, so the cleanup failure always appears to reach the primary — which discarded the cleanup failure outright and turned three existing tests red. Narrowing the check to the carry then went too far the other way, as a second review showed: that same temporary edge also made `cleanup_error.__context__ is None` false, so the carry never ran in the one shape it exists for, and an explicit `cleanup_error.__cause__ = primary` could still close a two-object cycle. The rule is not "guard everything" or "guard nothing" — it is **clear the temporary edge first, then ask**, and record a note rather than a link when what remains is a back-edge Python will not undo.

    One implementation because the same pairing had grown five spellings across this repository, and the reason each exists is the same reason.
    """
    if cleanup_error is primary:
        raise primary

    # Python's implicit chaining has *already* pointed the cleanup failure back at the primary, because at every call site here the close ran while the primary was being handled. That edge is temporary — re-raising drops it, and a review measured it gone from the final object graph — but while it is set, a `__context__ is None` test cannot tell it from a slot that is genuinely occupied. That is what made the carry below skip the one shape it was written for and keep only the quiet one.
    if cleanup_error.__context__ is primary:
        cleanup_error.__context__ = None

    if _reaches(cleanup_error, primary):
        # Something stronger than that temporary edge leads from the cleanup failure back to the primary — an explicit `__cause__`, or a longer chain. Python will not undo those, so linking the other direction closes a real cycle. The pairing is recorded as a note instead, which says the same thing and cannot be walked in circles.
        primary.add_note(f"cleanup also failed: {cleanup_error!r}")
        raise primary

    if primary.__cause__ is None:
        raise primary from cleanup_error

    displaced = primary.__context__
    if (
        displaced is not None
        and displaced is not cleanup_error
        and cleanup_error.__context__ is None
        and not _reaches(displaced, cleanup_error)
    ):
        # Carried rather than dropped: the earlier cleanup failure keeps its place under the newer one.
        cleanup_error.__context__ = displaced
    primary.__context__ = cleanup_error
    raise primary


async def finish_stream_cleanup[T](
    pending: asyncio.Task[T] | None,
    stream: AsyncIterator[T],
    *,
    primary: BaseException | None = None,
) -> tuple[BaseException | None, asyncio.CancelledError | None]:
    """Finish cleanup before returning any cancellation or cleanup failure."""

    async def cleanup() -> None:
        pending_error: BaseException | None = None
        if pending is not None:
            pending_error = await _cancel_and_observe(pending)
            if pending_error is primary:
                pending_error = None
        try:
            await _close_iterator(stream)
        except BaseException as close_error:
            if pending_error is not None:
                raise pending_error from close_error
            raise
        if pending_error is not None:
            raise pending_error

    cleanup_task = asyncio.create_task(cleanup())
    current = asyncio.current_task()
    cancelling_seen = current.cancelling() if current is not None else 0
    deferred_cancellation: asyncio.CancelledError | None = None

    while not cleanup_task.done():
        try:
            # `asyncio.wait` rather than `asyncio.shield`, which both keep the cleanup running through a cancellation — but a cancelled `shield` leaves its outer future behind, and when the inner task later *fails*, that abandoned future reports the failure as unconsumed: `RuntimeError exception in shielded future` on stderr, alongside the very same exception this function is about to return properly chained. A review caught it by cancelling during a close that then failed. `asyncio.wait` registers a done-callback and removes it, so nothing is left holding a result nobody read.
            #
            # `_events_with_ping` already avoids the same trap for its pull, and says so where it does.
            await asyncio.wait({cleanup_task})
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


async def _cancel_and_observe[T](pending: asyncio.Task[T]) -> BaseException | None:
    """Settle a pull task without replacing the exit that initiated cleanup."""
    if not pending.done():
        pending.cancel()

    current = asyncio.current_task()
    cancelling_before = current.cancelling() if current is not None else 0
    try:
        await pending
    except StopAsyncIteration:
        return None
    except asyncio.CancelledError:
        if current is not None and current.cancelling() > cancelling_before:
            raise
        # The pull task's own cancellation is expected during cleanup. An outer cancellation already in flight resumes after this finally block.
    except Exception as error:
        return error
    return None


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
