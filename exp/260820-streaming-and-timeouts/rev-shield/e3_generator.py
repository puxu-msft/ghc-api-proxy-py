"""Generator-level probes against the real app.pipeline.delivery.stream module."""
import asyncio, contextlib, gc, sys
from collections.abc import AsyncIterator

from app.pipeline.delivery.stream import _events_with_ping, stream_delivery, StreamSettings, PING_FRAME
from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
import orjson

def frame(event, data):
    return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n".encode()

async def slow_feed(delay, payloads):
    for p in payloads:
        await asyncio.sleep(delay)
        yield p

def install(loop):
    seen = []
    loop.set_exception_handler(lambda l, ctx: seen.append(ctx.get("message")))
    return seen

async def probe_close_midwait():
    """(d) consumer closes the generator while a pull is in flight."""
    loop = asyncio.get_running_loop()
    seen = install(loop)
    cancelled = {"pull": False}

    async def feed():
        try:
            await asyncio.sleep(5.0)
            yield b""
        except asyncio.CancelledError:
            cancelled["pull"] = True
            raise

    agen = _events_with_ping(feed(), 1)
    consumer_saw = []
    async def consume():
        async for e in agen:
            consumer_saw.append(e)
    t = asyncio.ensure_future(consume())
    await asyncio.sleep(1.3)          # one keep-alive has fired
    t.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await t
    await agen.aclose()
    await asyncio.sleep(0.05)
    gc.collect()
    await asyncio.sleep(0.05)
    print("d_close: pings=", consumer_saw, "feed_cancelled=", cancelled["pull"], "handler=", seen)

async def probe_pending_task_after_close():
    """(d2) after close, does the abandoned pull task leave noise when it ends?"""
    loop = asyncio.get_running_loop()
    seen = install(loop)

    async def feed():
        await asyncio.sleep(1.4)
        return
        yield b""

    agen = _events_with_ping(feed(), 1)
    got = []
    async def consume():
        async for e in agen:
            got.append(e)
    t = asyncio.ensure_future(consume())
    await asyncio.sleep(1.2)   # after first keep-alive, pull still in flight
    t.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await t
    await agen.aclose()
    await asyncio.sleep(0.6)   # the abandoned pull would end around now
    gc.collect(); await asyncio.sleep(0.1); gc.collect(); await asyncio.sleep(0.1)
    print("d2_abandoned: yielded=", got, "handler=", seen)

async def probe_ping_timing():
    """(3) ping / synthesized message_start counts and ordering."""
    loop = asyncio.get_running_loop()
    seen = install(loop)
    payloads = [
        frame("content_block_start", {"index": 0, "content_block": {"type": "text"}}),
        frame("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "hi"}}),
        frame("content_block_stop", {"index": 0}),
        frame("message_delta", {"delta": {"stop_reason": "end_turn"}}),
        frame("message_stop", {}),
    ]
    out = []
    async for chunk in stream_delivery(
        slow_feed(0.45, payloads),
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=1, synthesized_response_headers_after_sec=1),
        message_id="msg_1", model="m",
    ):
        out.append(chunk)
    pings = sum(1 for c in out if c == PING_FRAME)
    events = [l.removeprefix("event: ") for c in out for l in c.decode().splitlines() if l.startswith("event: ")]
    print("ping_timing: pings=", pings, "events=", events, "handler=", seen)

async def probe_spin():
    """(2) busy-spin check: deadline already passed, count loop iterations."""
    loop = asyncio.get_running_loop()
    seen = install(loop)
    ticks = 0
    async def counter():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)
    c = asyncio.ensure_future(counter())
    payloads = [frame("message_stop", {})]
    out = [chunk async for chunk in stream_delivery(
        slow_feed(0.5, payloads), AnthropicAssembler(), buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0, synthesized_response_headers_after_sec=1),
        message_id="msg_1", model="m")]
    c.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await c
    print("spin: loop_ticks_in_0.5s=", ticks, "out_events=", len(out), "handler=", seen)

async def main():
    for p in (probe_close_midwait, probe_pending_task_after_close, probe_ping_timing, probe_spin):
        await p()

asyncio.run(main())
