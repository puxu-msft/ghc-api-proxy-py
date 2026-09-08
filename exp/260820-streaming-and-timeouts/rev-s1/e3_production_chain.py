"""Production-shaped chain: _counted_upstream -> stream_delivery -> _tracked_delivery.

Answers:
  - after aclose() returns, is the *innermost* byte source closed, or N ticks later?
  - is the byte source closed twice?
  - how many bytes land in trace.received after accounting.finish() has read it?
"""

import asyncio
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
    chunks: list[bytes] = []
    for index, text in enumerate(texts):
        chunks.append(frame("content_block_start", {"index": index, "content_block": {"type": "text"}}))
        chunks.append(frame("content_block_delta", {"index": index, "delta": {"type": "text_delta", "text": text}}))
        chunks.append(frame("content_block_stop", {"index": index}))
    chunks.append(frame("message_delta", {"delta": {"stop_reason": "end_turn"}}))
    chunks.append(frame("message_stop", {}))
    return chunks


class Recorder:
    def __init__(self) -> None:
        self.closes = 0
        self.closed_at_tick: int | None = None
        self.received_at_close: str | None = None


TICK = 0


async def ticker() -> None:
    global TICK
    while True:
        TICK += 1
        await asyncio.sleep(0)


def fake_chain():
    return SimpleNamespace(
        active_requests=SimpleNamespace(add_bytes=lambda rid, n: None)
    )


async def scenario(*, hang: bool, feed_during_cleanup: bytes | None = None):
    global TICK
    TICK = 0
    rec = Recorder()
    trace = SimpleNamespace(received=0)
    reached = asyncio.Event()
    release = asyncio.Event()

    payloads = anthropic_stream("hello")

    async def raw() -> AsyncIterator[bytes]:
        """Stands in for httpx Response.aiter_bytes()."""
        try:
            for payload in payloads[:3]:
                yield payload
            if hang:
                reached.set()
                if feed_during_cleanup is not None:
                    # A read that completes exactly while cleanup is cancelling the pull.
                    await release.wait()
                    yield feed_during_cleanup
                    yield feed_during_cleanup
                await asyncio.Event().wait()
            else:
                for payload in payloads[3:]:
                    yield payload
        finally:
            rec.closes += 1
            rec.closed_at_tick = TICK
            rec.received_at_close = f"{trace.received}"

    counted = _counted_upstream(raw(), fake_chain(), "rid", trace)
    delivery = stream_delivery(
        counted,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0),
        message_id="m",
        model="model",
    )
    finished: list[int] = []
    accounting = SimpleNamespace(finish=lambda: finished.append(trace.received))
    tracked = _tracked_delivery(delivery, accounting)
    return rec, trace, reached, release, tracked, finished


async def case_aclose_tracked_hanging() -> None:
    """Close the outermost generator (what a well-behaved ASGI server would do)."""
    rec, trace, reached, release, tracked, finished = await scenario(hang=True)
    tick_task = asyncio.create_task(ticker())
    pump = asyncio.create_task(_drain(tracked))
    await asyncio.wait_for(reached.wait(), 2)
    await asyncio.sleep(0.02)
    pump.cancel()
    try:
        await pump
    except asyncio.CancelledError:
        pass
    t_before = TICK
    await tracked.aclose()
    t_after = TICK
    print(
        f"aclose(outer, pull in flight): closes={rec.closes} "
        f"closed_before_aclose_returned={rec.closed_at_tick is not None and rec.closed_at_tick <= t_after} "
        f"ticks_elapsed_during_aclose={t_after - t_before} finished_at={finished}"
    )
    if rec.closed_at_tick is None:
        # not yet closed -- see how many ticks it takes
        for i in range(20):
            await asyncio.sleep(0)
            if rec.closed_at_tick is not None:
                print(f"  raw source only closed {i + 1} ticks AFTER aclose() returned")
                break
        else:
            print("  raw source STILL not closed after 20 ticks")
    tick_task.cancel()


async def case_cancel_in_pull() -> None:
    """Client disconnect the way starlette 0.52 + uvicorn actually delivers it."""
    rec, trace, reached, release, tracked, finished = await scenario(hang=True)
    tick_task = asyncio.create_task(ticker())
    pump = asyncio.create_task(_drain(tracked))
    await asyncio.wait_for(reached.wait(), 2)
    await asyncio.sleep(0.02)
    pump.cancel()
    try:
        await pump
    except asyncio.CancelledError:
        pass
    # starlette does NOT aclose body_iterator; this is the honest production shape.
    t_before = TICK
    for i in range(30):
        await asyncio.sleep(0)
        if rec.closes:
            break
    print(
        f"cancel-in-pull, no aclose(): closes={rec.closes} ticks_after_cancel={TICK - t_before} "
        f"finished_at={finished} trace.received={trace.received}"
    )
    tick_task.cancel()


async def case_double_close() -> None:
    rec, trace, reached, release, tracked, finished = await scenario(hang=False)
    out = [c async for c in tracked]
    assert out
    print(f"normal end: closes={rec.closes} trace.received={trace.received} finished_at={finished}")
    await tracked.aclose()
    await tracked.aclose()
    print(f"  after two extra aclose(): closes={rec.closes}")


async def case_bytes_after_finish() -> None:
    """A pull that completes while cleanup is settling it: do its bytes land after finish()?"""
    rec, trace, reached, release, tracked, finished = await scenario(
        hang=True, feed_during_cleanup=b"event: ping\ndata: {}\n\n"
    )
    pump = asyncio.create_task(_drain(tracked))
    await asyncio.wait_for(reached.wait(), 2)
    await asyncio.sleep(0.02)
    release.set()
    pump.cancel()
    try:
        await pump
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(0.05)
    print(
        f"bytes-after-finish: finished_at={finished} final trace.received={trace.received} "
        f"delta={trace.received - (finished[0] if finished else 0)}"
    )


async def _drain(gen) -> None:
    async for _ in gen:
        pass


async def main() -> None:
    await case_double_close()
    await case_aclose_tracked_hanging()
    await case_cancel_in_pull()
    await case_bytes_after_finish()


asyncio.run(main())
