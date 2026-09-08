"""Same, but abandoning while the upstream pull is definitely in flight (the client-disconnect shape)."""
import asyncio, gc
import orjson
from app.pipeline.delivery.stream import stream_delivery, StreamSettings
from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer

def frame(event, data):
    return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n".encode()

async def main():
    state = {"closed": False, "in_flight": False}
    async def upstream():
        frames = [
            frame("content_block_start", {"index": 0, "content_block": {"type": "text"}}),
            frame("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "hi"}}),
            frame("content_block_stop", {"index": 0}),
        ]
        try:
            for f in frames:
                yield f
            state["in_flight"] = True
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
    for _ in range(4):
        await anext(it)
    waiter = asyncio.ensure_future(anext(it))     # drives the 5th pull
    await asyncio.sleep(0.05)
    print("upstream reached the hang? ->", state["in_flight"], "| waiter pending?", not waiter.done())
    waiter.cancel()                                # the client went away
    try:
        await waiter
    except asyncio.CancelledError:
        pass
    await agen.aclose()
    print("right after aclose():  upstream closed? ->", state["closed"])
    for _ in range(5):
        await asyncio.sleep(0)
    print("after 5 ticks:         upstream closed? ->", state["closed"])
    others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    print("tasks alive after aclose:", [(t.get_name(), "done" if t.done() else "PENDING") for t in others])
    gc.collect()
    for _ in range(5):
        await asyncio.sleep(0)
    print("after gc.collect():    upstream closed? ->", state["closed"])
    others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    print("tasks alive after gc:", [(t.get_name(), "done" if t.done() else "PENDING") for t in others])

asyncio.run(main())
