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

    Closing this closes the stream under it, including on the timeout: every other layer on this chain settles what it consumes, and a guard that gives up on an upstream without releasing what it was reading is the one that gets stepped on when the chain is next recomposed.

    What that buys is this layer's link in the cascade, and no more. Measured 2026-08-20 against a real server: when the source is `httpx`'s `aiter_bytes()`, closing it does not close the response — `aiter_raw` runs `await self.aclose()` after its loop rather than in a `finally`, so the response is released by generator finalisation either way. A reader checking this at the socket sees no difference; the difference is at the generator.
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
