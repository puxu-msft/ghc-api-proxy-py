"""Item 4: how many bytes can land in trace.received after accounting.finish() read it?

Constructed to hit the window: the outer generator is closed (which runs finish()),
while a pull is still in flight and about to complete with several counted chunks.
"""

import asyncio
import gc
import sys
from collections.abc import AsyncIterator
from types import SimpleNamespace

sys.path.insert(0, "/tmp/rev-s1/base")

import orjson

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.server.pipeline_app import _counted_upstream, _tracked_delivery


def frame(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n".encode()


def anthropic_stream(*texts: str) -> list[bytes]:
    out: list[bytes] = []
    for i, t in enumerate(texts):
        out.append(frame("content_block_start", {"index": i, "content_block": {"type": "text"}}))
        out.append(frame("content_block_delta", {"index": i, "delta": {"type": "text_delta", "text": t}}))
        out.append(frame("content_block_stop", {"index": i}))
    return out


async def run(*, split_into: int, release_before_close: bool) -> None:
    trace = SimpleNamespace(received=0)
    finished: list[int] = []
    release = asyncio.Event()
    at_ping = asyncio.Event()

    head = anthropic_stream("hello")
    # One more whole block, sliced into `split_into` pieces so a single pull spans many chunks.
    tail = b"".join(anthropic_stream("x" * 4000)[0:3])
    step = max(1, len(tail) // split_into)
    slices = [tail[i : i + step] for i in range(0, len(tail), step)]

    async def raw() -> AsyncIterator[bytes]:
        for p in head:
            yield p
        at_ping.set()
        await release.wait()
        for s in slices:
            await asyncio.sleep(0)
            yield s
        await asyncio.Event().wait()

    chain = SimpleNamespace(active_requests=SimpleNamespace(add_bytes=lambda *_: None))
    tracked = _tracked_delivery(
        stream_delivery(
            _counted_upstream(raw(), chain, "rid", trace),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0.02),  # type: ignore[arg-type]
            message_id="m",
            model="model",
        ),
        SimpleNamespace(finish=lambda: finished.append(trace.received)),
    )
    it = tracked.__aiter__()
    while True:
        chunk = await asyncio.wait_for(anext(it), 3)
        if chunk == b": ping\n\n":
            break
    if release_before_close:
        release.set()
    await tracked.aclose()  # runs finish()
    if not release_before_close:
        release.set()
    for _ in range(10):
        gc.collect()
        await asyncio.sleep(0.02)
    print(
        f"split_into={split_into:3d} release_before_close={release_before_close!s:5s} "
        f"tail_bytes={len(tail):5d} finish()_saw={finished} final={trace.received} "
        f"lost_from_the_log_line={trace.received - finished[0]}"
    )
    for t in {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}:
        t.cancel()
    await asyncio.sleep(0.02)


async def main() -> None:
    await run(split_into=1, release_before_close=False)
    await run(split_into=1, release_before_close=True)
    await run(split_into=40, release_before_close=True)


asyncio.run(main())
