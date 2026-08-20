"""The absolute end of one upstream attempt, enforced over the body.

Separate from `idle_timeout` because the two answer different questions. The idle guard asks how long upstream may say nothing; this one asks how long the attempt may live in total, however busy it is. An upstream that trickles a byte every second forever satisfies the first and is exactly what the second is for.
"""

import asyncio
from collections.abc import AsyncIterator


class StreamDeadlineError(TimeoutError):
    pass


async def with_deadline_at[T](
    stream: AsyncIterator[T],
    deadline_at: float | None,
) -> AsyncIterator[T]:
    """Fail the stream once the attempt's deadline has passed. `None` means nothing bounds it.

    The instant is the caller's, taken from the loop clock, because the same attempt is also guarded before its headers arrive and both places have to mean the same moment.

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
                # Only when this bound is what expired. A guard nested inside this one reports its own timeout as a `TimeoutError` too — `StreamIdleTimeoutError` is one — and relabelling it here would name the wrong setting in the one line an operator gets.
                if not bound.expired():
                    raise
                raise StreamDeadlineError("attempt exceeded its deadline") from error
            yield item
    finally:
        if close is not None:
            await close()
