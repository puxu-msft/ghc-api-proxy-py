"""Abandon while a pull is genuinely in flight, and separate 'closed by aclose' from 'closed by GC'."""
import asyncio, gc, sys
import orjson
from app.pipeline.delivery.stream import stream_delivery, StreamSettings
from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer

def frame(event, data):
    return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n".encode()

async def run(do_gc: bool):
    state = {"closed": False, "pull_in_flight": False}
    async def upstream():
        frames = [
            frame("content_block_start", {"index": 0, "content_block": {"type": "text"}}),
            frame("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "hi"}}),
            frame("content_block_stop", {"index": 0}),
        ]
        try:
            for f in frames:
                yield f
            state["pull_in_flight"] = True
            await asyncio.sleep(3600)
        finally:
            state["closed"] = True

    agen = stream_delivery(
        upstream(), AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0),
        message_id="msg_x", model="m",
    )
    it = agen.__aiter__()
    got = []
    for _ in range(4):
        got.append(await anext(it))
    await asyncio.sleep(0.05)
    print(f"[gc={do_gc}] consumed {len(got)} frames; pull in flight? ->", state["pull_in_flight"])
    await agen.aclose()
    print(f"[gc={do_gc}] right after aclose():  upstream closed? ->", state["closed"])
    for _ in range(5):
        await asyncio.sleep(0)
    print(f"[gc={do_gc}] after 5 ticks:         upstream closed? ->", state["closed"])
    if do_gc:
        gc.collect()
        for _ in range(5):
            await asyncio.sleep(0)
        print(f"[gc={do_gc}] after gc.collect():    upstream closed? ->", state["closed"])
    others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    print(f"[gc={do_gc}] tasks alive:", [(t.get_name(), "done" if t.done() else "PENDING") for t in others])
    return state

async def main():
    await run(do_gc=False)
    print("---")
    await run(do_gc=True)

asyncio.run(main())
