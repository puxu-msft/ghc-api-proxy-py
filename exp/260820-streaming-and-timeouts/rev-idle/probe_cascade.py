"""Does closing stream_delivery reach the source, in the *production* composition?

Production (after the change under review) is:
    stream_delivery( _counted_upstream( with_idle_timeout( response.aiter_bytes() ) ) )

The pinned test uses:
    stream_delivery(                     with_idle_timeout( hanging_source() )      )

`_counted_upstream` is a bare `async for` with no finally, so it is the link worth asking about.
Two scenarios per composition:
  CLOSE-ONLY : nobody is pulling; just aclose the delivery generator.
  CANCEL+CLOSE: a pump task is pulling, gets cancelled, then aclose (the pinned test's shape).
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import suppress

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.server.pipeline_app import _counted_upstream  # pyright: ignore[reportPrivateUsage]
from app.streaming.idle_timeout import with_idle_timeout

BLOCK = (
    b'event: message_start\ndata: {"message":{"id":"msg_1","usage":{}}}\n\n'
    b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text","text":""}}\n\n'
    b'event: content_block_delta\ndata: {"index":0,"delta":{"type":"text_delta","text":"hi"}}\n\n'
    b'event: content_block_stop\ndata: {"index":0}\n\n'
)


def source(closed: list[str], reached: asyncio.Event) -> AsyncGenerator[bytes]:
    async def gen() -> AsyncGenerator[bytes]:
        try:
            yield BLOCK
            reached.set()
            await asyncio.Event().wait()  # upstream still has more to send
        finally:
            closed.append("source released")

    return gen()


class _Chain:
    class _Active:
        def add_bytes(self, request_id: str, count: int) -> None: ...

    active_requests = _Active()


class _Trace:
    received = 0


def delivery(chunks: AsyncIterator[bytes]) -> AsyncGenerator[bytes]:
    return stream_delivery(
        chunks,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0),
        message_id="msg_1",
        model="claude-model",
    )


def production(closed: list[str], reached: asyncio.Event) -> AsyncGenerator[bytes]:
    return delivery(
        _counted_upstream(
            with_idle_timeout(source(closed, reached), timeout_seconds=30),
            _Chain(),  # pyright: ignore[reportArgumentType]
            "req_1",
            _Trace(),  # pyright: ignore[reportArgumentType]
        )
    )


def as_pinned(closed: list[str], reached: asyncio.Event) -> AsyncGenerator[bytes]:
    return delivery(with_idle_timeout(source(closed, reached), timeout_seconds=30))


async def close_only(build) -> list[str]:
    closed: list[str] = []
    reached = asyncio.Event()
    gen = build(closed, reached)
    assert await anext(gen)
    await gen.aclose()
    immediate = list(closed)
    await asyncio.sleep(0.05)
    return [f"immediate={immediate or ['NOT RELEASED']}", f"after_gc={closed or ['NOT RELEASED']}"]


async def cancel_then_close(build) -> list[str]:
    closed: list[str] = []
    reached = asyncio.Event()
    gen = build(closed, reached)

    async def pump() -> None:
        async for _ in gen:
            pass

    task = asyncio.create_task(pump())
    await asyncio.wait_for(reached.wait(), 2)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await gen.aclose()
    immediate = list(closed)
    await asyncio.sleep(0.05)
    return [f"immediate={immediate or ['NOT RELEASED']}", f"after_gc={closed or ['NOT RELEASED']}"]


async def main() -> None:
    for name, build in (("PRODUCTION (with _counted_upstream)", production), ("PINNED TEST shape", as_pinned)):
        for mode, run in (("close-only    ", close_only), ("cancel+close  ", cancel_then_close)):
            try:
                async with asyncio.timeout(5):
                    result = await run(build)
            except TimeoutError:
                result = ["<HUNG>"]
            print(f"{name:38s} {mode} -> {result or ['SOURCE NEVER RELEASED']}")


asyncio.run(main())
