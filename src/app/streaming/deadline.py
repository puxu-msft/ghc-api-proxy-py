"""Absolute ends enforced over a body: one for an upstream attempt, one for the whole client request.

Separate from `idle_timeout` because the two answer different questions. The idle guard asks how long upstream may say nothing; these ask how long something may live in total, however busy it is. An upstream that trickles a byte every second forever satisfies the first and is exactly what these are for.

Two of them, and they are deliberately not one. They belong to different owners and mean different things — `upstream_request_deadline` bounds *this attempt*, and is re-fixed each time an attempt opens; `client_request_deadline` bounds *this client request*, across however many attempts it takes. A single guard could only report one of those names, and the name is the whole of what an operator gets when a stream ends early.
"""

import asyncio
from collections.abc import AsyncIterator, Callable


class StreamDeadlineError(TimeoutError):
    """One upstream attempt outlived `upstream_request_deadline`."""


class ClientDeadlineError(TimeoutError):
    """The client request outlived `client_request_deadline` while its body was still arriving.

    Its own type because the client is owed something the attempt deadline does not owe it. By the time this can fire the response has been open for a while and its status is long settled, so the only way left to say what happened is an SSE error frame — which delivery sends for this and for nothing else. Ruled 2026-08-22.
    """


async def _bounded[T](
    stream: AsyncIterator[T],
    deadline_at: float | None,
    expired: Callable[[], TimeoutError],
) -> AsyncIterator[T]:
    """Fail the stream once `deadline_at` has passed. `None` means nothing bounds it.

    The instant is the caller's, taken from the loop clock, because the same lifetime may be guarded in more than one place and all of them have to mean the same moment.

    The bound is held across each pull and never across a `yield`: a cancel scope left open while the consumer runs would be entered in this task and unwound in whichever one closes the generator. Time the consumer spends between pulls still counts — it is measured at the next pull rather than interrupting it.

    Closing this closes the stream under it, as every other layer on this chain does.
    """
    close = getattr(stream, "aclose", None)
    try:
        if deadline_at is None:
            async for item in stream:
                yield item
            return

        while True:
            bound = asyncio.timeout_at(deadline_at)
            try:
                async with bound:
                    item = await anext(stream)
            except StopAsyncIteration:
                return
            except TimeoutError as error:
                # Only when this bound is what expired. A guard nested inside this one reports its own timeout as a `TimeoutError` too — `StreamIdleTimeoutError` and the other of these two are both one — and relabelling it here would name the wrong setting in the one line an operator gets.
                if not bound.expired():
                    raise
                raise expired() from error
            yield item
    finally:
        if close is not None:
            await close()


def with_deadline_at[T](
    stream: AsyncIterator[T],
    deadline_at: float | None,
) -> AsyncIterator[T]:
    """Bound one upstream attempt's body by the instant that attempt was opened against."""
    return _bounded(stream, deadline_at, lambda: StreamDeadlineError("attempt exceeded its deadline"))


def with_client_deadline_at[T](
    stream: AsyncIterator[T],
    deadline_at: float | None,
) -> AsyncIterator[T]:
    """Bound the whole client request, across every attempt it takes.

    Outermost of the guards on this chain, because it is the longest-lived of them: an attempt's deadline may expire and be replaced by another attempt's, and this one does not move.
    """
    return _bounded(stream, deadline_at, lambda: ClientDeadlineError("client request exceeded its deadline"))
