import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import suppress


async def keepalive_stream(
    stream: AsyncIterator[bytes],
    *,
    interval_seconds: float,
    heartbeat: bytes,
) -> AsyncGenerator[bytes]:
    pending: asyncio.Task[bytes] | None = None

    async def next_item() -> bytes:
        return await anext(stream)

    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(next_item())
            try:
                item = await asyncio.wait_for(
                    asyncio.shield(pending),
                    timeout=interval_seconds,
                )
            except TimeoutError:
                yield heartbeat
                continue
            except StopAsyncIteration:
                return
            pending = None
            yield item
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with suppress(asyncio.CancelledError):
                await pending