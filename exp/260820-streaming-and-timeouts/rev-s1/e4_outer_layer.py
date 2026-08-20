"""Does closing the OUTERMOST generator reach the byte source?

_tracked_delivery uses a bare `async for` over stream_delivery, exactly the shape
the S1 fix replaced one layer down. This measures whether that matters.
"""

import asyncio
import gc
import sys
from collections.abc import AsyncIterator
from types import SimpleNamespace

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/src")

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
    out.append(frame("message_delta", {"delta": {"stop_reason": "end_turn"}}))
    out.append(frame("message_stop", {}))
    return out


def build(hang_after_first_block: bool):
    closed: list[str] = []
    trace = SimpleNamespace(received=0)
    reached = asyncio.Event()
    payloads = anthropic_stream("hello", "world")

    async def raw() -> AsyncIterator[bytes]:
        try:
            for p in payloads[:3]:
                yield p
            reached.set()
            if hang_after_first_block:
                await asyncio.Event().wait()
            for p in payloads[3:]:
                yield p
        except BaseException as exc:  # noqa: BLE001
            closed.append(f"received:{type(exc).__name__}")
            raise
        finally:
            closed.append("closed")

    chain = SimpleNamespace(active_requests=SimpleNamespace(add_bytes=lambda *_: None))
    counted = _counted_upstream(raw(), chain, "rid", trace)
    delivery = stream_delivery(
        counted,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        # sse_ping_interval is seconds; a fractional value is arithmetically identical
        # and only shortens the wait. Production uses 15.
        settings=StreamSettings(sse_ping_interval=0.05),  # type: ignore[arg-type]
        message_id="m",
        model="model",
    )
    accounting = SimpleNamespace(finish=lambda: None)
    tracked = _tracked_delivery(delivery, accounting)
    return tracked, delivery, closed, reached


async def case_outer_aclose_with_pull_in_flight() -> None:
    """Consumer stops holding a ping frame; a pull is in flight behind it."""
    tracked, delivery, closed, reached = build(hang_after_first_block=True)
    seen: list[bytes] = []
    it = tracked.__aiter__()
    # pull until a ping frame arrives -- that is the state with a pull in flight
    while True:
        chunk = await asyncio.wait_for(anext(it), 3)
        seen.append(chunk)
        if chunk == b": ping\n\n":
            break
    before = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
    await tracked.aclose()
    print(f"[outer aclose, pull in flight] upstream after aclose() returned: {closed}")
    leaked = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()} - before
    print(f"    tasks created and still alive: {len(leaked)}")
    for i in range(1, 21):
        await asyncio.sleep(0)
        if closed:
            print(f"    upstream closed {i} ticks after aclose() returned")
            break
    else:
        print("    upstream STILL not closed 20 ticks later")
    del it
    gc.collect()
    await asyncio.sleep(0.05)
    print(f"    after gc.collect() + a sleep: {closed}")
    still = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()} - before
    print(f"    tasks still alive after gc: {len(still)}")
    for t in still:
        print("      ", t)
        t.cancel()
    await asyncio.sleep(0.05)


async def case_outer_aclose_idle() -> None:
    """Same, but stopped on a content chunk (no pull in flight)."""
    tracked, delivery, closed, reached = build(hang_after_first_block=False)
    it = tracked.__aiter__()
    await anext(it)
    before = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
    await tracked.aclose()
    print(f"[outer aclose, idle] upstream after aclose() returned: {closed}")
    for i in range(1, 21):
        await asyncio.sleep(0)
        if closed:
            print(f"    upstream closed {i} ticks after aclose() returned")
            break
    else:
        print("    upstream STILL not closed 20 ticks later")
    del it
    gc.collect()
    await asyncio.sleep(0.05)
    print(f"    after gc.collect() + a sleep: {closed}")


async def case_inner_aclose_control() -> None:
    """Control: closing stream_delivery itself (what the fix guarantees)."""
    tracked, delivery, closed, reached = build(hang_after_first_block=True)
    it = delivery.__aiter__()
    while True:
        chunk = await asyncio.wait_for(anext(it), 3)
        if chunk == b": ping\n\n":
            break
    await delivery.aclose()
    print(f"[inner aclose, pull in flight] upstream after aclose() returned: {closed}")


async def main() -> None:
    await case_inner_aclose_control()
    await case_outer_aclose_idle()
    await case_outer_aclose_with_pull_in_flight()


asyncio.run(main())
