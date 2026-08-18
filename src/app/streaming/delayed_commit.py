from collections.abc import AsyncIterator

import anyio


async def delayed_first_item[T](
    stream: AsyncIterator[T],
    *,
    timeout_seconds: float,
) -> tuple[T, AsyncIterator[T]]:
    with anyio.fail_after(timeout_seconds):
        first = await anext(stream)
    return first, stream
