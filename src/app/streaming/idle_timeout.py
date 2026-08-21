import asyncio
from collections.abc import AsyncIterator

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

    What that buys is this layer's link in the cascade, and rather more than it used to. Measured 2026-08-20 against a real server on httpx 0.28.1: closing `aiter_bytes()` did not close the response, because `aiter_raw` ran `await self.aclose()` after its loop rather than in a `finally`, so the response was released by generator finalisation either way and a reader watching the socket saw no difference. httpx2 moved that `aclose()` into a `finally` and closes the inner stream with it, so closing here now releases the response at this point rather than whenever the generator is collected. Nothing in this function changed; where the upstream connection is released did.
    """
    close = getattr(stream, "aclose", None)
    try:
        if timeout_seconds <= 0:
            async for item in stream:
                yield item
            return

        while True:
            bound = asyncio.timeout(timeout_seconds)
            try:
                async with bound:
                    item = await anext(stream)
            except StopAsyncIteration:
                return
            except TimeoutError as error:
                # Only when this bound is what expired. Whatever is nested inside may report its own expiry as a `TimeoutError` too — `StreamDeadlineError` is one — and claiming it here would send an operator to a setting that is already correct. Without this the two guards could only be composed in one order, and nothing said so.
                if not bound.expired():
                    raise
                raise StreamIdleTimeoutError(
                    f"No stream item received for {timeout_seconds:g}s"
                ) from error
            yield item
    finally:
        if close is not None:
            await close()
