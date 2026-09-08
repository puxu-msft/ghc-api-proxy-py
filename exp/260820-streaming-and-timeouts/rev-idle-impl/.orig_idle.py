from collections.abc import AsyncIterator

import anyio

from app.config.settings import TimeoutConfig


class StreamIdleTimeoutError(TimeoutError):
    pass


def resolve_stream_idle(model: str, settings: TimeoutConfig) -> int:
    for key, value in settings.stream_idle_overrides.items():
        if key in model:
            return value
    return settings.stream_idle


async def with_idle_timeout[T](
    stream: AsyncIterator[T],
    timeout_seconds: float,
) -> AsyncIterator[T]:
    """Fail the stream when upstream goes quiet for longer than the timeout.

    Closing this closes the stream under it, including on the timeout — giving up on an upstream and leaving its response open would hold the connection for exactly as long as the wait that made us give up. A bare `async for` closes nothing when GeneratorExit unwinds past it, so the close is explicit.
    """
    close = getattr(stream, "aclose", None)
    try:
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
    finally:
        if close is not None:
            await close()
