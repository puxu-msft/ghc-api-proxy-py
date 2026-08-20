"""Isolate the *close* path: the source is suspended at a `yield`, not at an `await`.

A cancellation of the in-flight pull cannot reach it, so only an explicit `aclose()` down the chain runs its `finally`. This is the shape `test_closing_the_delivery_closes_the_upstream_under_it` uses.
"""
import asyncio
import gc
from collections.abc import AsyncIterator

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.streaming.idle_timeout import with_idle_timeout


async def counted(chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Same shape as `_counted_upstream`: a bare `async for` passthrough."""
    async for chunk in chunks:
        yield chunk


def frames(n: int) -> list[bytes]:
    out: list[bytes] = []
    for i in range(n):
        out += [
            b'event: content_block_start\ndata: {"index":%d,"content_block":{"type":"text"}}\n\n' % i,
            b'event: content_block_delta\ndata: {"index":%d,"delta":{"type":"text_delta","text":"x"}}\n\n' % i,
            b'event: content_block_stop\ndata: {"index":%d}\n\n' % i,
        ]
    return out


async def source(log: list[str]) -> AsyncIterator[bytes]:
    try:
        for f in frames(6):
            yield f
    finally:
        log.append("source closed")


def delivery(chunks):
    return stream_delivery(
        chunks, AnthropicAssembler(), buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0), message_id="m", model="model",
    )


async def run(with_counted: bool, hold_ref: bool) -> None:
    log: list[str] = []
    src = source(log)
    guarded = with_idle_timeout(src, timeout_seconds=30)
    chunks = counted(guarded) if with_counted else guarded
    d = delivery(chunks)
    if not hold_ref:
        del guarded, chunks, src

    async for _ in d:
        break                      # one block delivered; the client now goes away
    await d.aclose()

    label = f"counted={with_counted} hold_ref={hold_ref}"
    print(f"{label}: right after aclose() -> {log!r}")
    for _ in range(20):
        await asyncio.sleep(0)
    gc.collect()
    for _ in range(20):
        await asyncio.sleep(0)
    print(f"{label}: after ticks + gc      -> {log!r}")
    print()


async def main() -> None:
    await run(with_counted=False, hold_ref=True)
    await run(with_counted=True, hold_ref=True)
    await run(with_counted=True, hold_ref=False)


asyncio.run(main())
