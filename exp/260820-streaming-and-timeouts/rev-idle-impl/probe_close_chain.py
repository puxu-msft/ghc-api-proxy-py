"""Does closing the delivery chain release the idle-guarded source, the way commit 926cabf promises?

Builds the production composition from pipeline_app.py:277-301 with real functions.
"""
import asyncio
from collections.abc import AsyncIterator

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.streaming.idle_timeout import with_idle_timeout


async def counted(chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Byte-identical in shape to `_counted_upstream`: a bare `async for` passthrough."""
    async for chunk in chunks:
        yield chunk


FRAMES = [
    b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n',
    b'event: content_block_delta\ndata: {"index":0,"delta":{"type":"text_delta","text":"one"}}\n\n',
    b'event: content_block_stop\ndata: {"index":0}\n\n',
]


async def source(log: list[str], reached: asyncio.Event) -> AsyncIterator[bytes]:
    try:
        for f in FRAMES:
            yield f
        reached.set()
        await asyncio.Event().wait()
    finally:
        log.append("source closed")


def delivery(chunks):
    return stream_delivery(
        chunks, AnthropicAssembler(), buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0), message_id="m", model="model",
    )


async def run(with_counted: bool) -> None:
    log: list[str] = []
    reached = asyncio.Event()
    src = source(log, reached)
    guarded = with_idle_timeout(src, timeout_seconds=30)
    chunks = counted(guarded) if with_counted else guarded
    d = delivery(chunks)

    async def pump():
        async for _ in d:
            pass

    task = asyncio.create_task(pump())
    await asyncio.wait_for(reached.wait(), 2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await d.aclose()
    label = "production shape (_counted_upstream present)" if with_counted else "unit-test shape (no _counted_upstream)"
    print(f"{label}: after aclose() returned -> {log!r}")
    # give the asyncgen finalizer hooks a chance
    for _ in range(20):
        await asyncio.sleep(0)
    print(f"{label}: after 20 loop ticks       -> {log!r}")
    del guarded, src, chunks, d
    for _ in range(20):
        await asyncio.sleep(0)
    print(f"{label}: after dropping refs       -> {log!r}")
    print()


async def main() -> None:
    await run(with_counted=False)
    await run(with_counted=True)


asyncio.run(main())
