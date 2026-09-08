import asyncio, gc
import orjson
from app.pipeline.delivery.stream import stream_delivery, StreamSettings
from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer

state = {"closed": False}

def frame(event, data):
    return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n".encode()

async def upstream():
    frames = [
        frame("content_block_start", {"index": 0, "content_block": {"type": "text"}}),
        frame("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "hi"}}),
        frame("content_block_stop", {"index": 0}),
    ]
    try:
        for f in frames:
            yield f
        await asyncio.sleep(3600)   # a live upstream still open
    finally:
        state["closed"] = True

async def main():
    agen = stream_delivery(
        upstream(), AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=1),
        message_id="msg_x", model="m",
    )
    it = agen.__aiter__()
    print("first frame:", (await anext(it))[:30])
    await agen.aclose()
    print("right after aclose():   upstream closed? ->", state["closed"])
    for _ in range(3):
        await asyncio.sleep(0)
    gc.collect()
    for _ in range(3):
        await asyncio.sleep(0)
    print("after gc + 6 ticks:     upstream closed? ->", state["closed"])
    others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    print("tasks still alive:", [(t.get_name(), "done" if t.done() else "PENDING") for t in others])

asyncio.run(main())
