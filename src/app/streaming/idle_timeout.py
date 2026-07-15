from collections.abc import AsyncIterator

import anyio


class StreamIdleTimeoutError(TimeoutError):
    pass


async def with_idle_timeout[T](
    stream: AsyncIterator[T],
    timeout_seconds: float,
) -> AsyncIterator[T]:
    if timeout_seconds <= 0:
        async for item in stream:
            yield item
        return

    while True:
        try:
            with anyio.fail_after(timeout_seconds):
                item = await anext(stream)
        except StopAsyncIteration:
            return
        except TimeoutError as error:
            raise StreamIdleTimeoutError(
                f"No stream item received for {timeout_seconds:g}s"
            ) from error
        yield item