"""Loop-shutdown scenarios for the new finally, which create_task()s during aclose()."""

import asyncio
import sys
from collections.abc import AsyncIterator
from types import SimpleNamespace

sys.path.insert(0, "/tmp/rev-s1/base")

import orjson

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.server.pipeline_app import _counted_upstream

CLOSED: list[str] = []


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


def build():
    payloads = anthropic_stream("hello", "world")

    async def raw() -> AsyncIterator[bytes]:
        try:
            for p in payloads[:3]:
                yield p
            await asyncio.Event().wait()
        except BaseException as exc:  # noqa: BLE001
            CLOSED.append(f"received:{type(exc).__name__}")
            raise
        finally:
            CLOSED.append("closed")

    chain = SimpleNamespace(active_requests=SimpleNamespace(add_bytes=lambda *_: None))
    return stream_delivery(
        _counted_upstream(raw(), chain, "rid", SimpleNamespace(received=0)),
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0.05),  # type: ignore[arg-type]
        message_id="m",
        model="model",
    )


HELD = []


async def main_abandon() -> None:
    """Leave a delivery suspended with a pull in flight; asyncio.run() then shuts down asyncgens."""
    gen = build()
    it = gen.__aiter__()
    while True:
        chunk = await asyncio.wait_for(anext(it), 3)
        if chunk == b": ping\n\n":
            break
    HELD.append((gen, it))  # deliberately keep it alive so only shutdown_asyncgens can reach it
    print("main returning with delivery suspended, pull in flight; upstream:", CLOSED)


async def main_explicit_shutdown() -> None:
    gen = build()
    it = gen.__aiter__()
    while True:
        chunk = await asyncio.wait_for(anext(it), 3)
        if chunk == b": ping\n\n":
            break
    HELD.append((gen, it))
    loop = asyncio.get_running_loop()
    await asyncio.wait_for(loop.shutdown_asyncgens(), 5)
    print("after explicit shutdown_asyncgens():", CLOSED)


mode = sys.argv[1]
if mode == "abandon":
    asyncio.run(main_abandon())
    print("after asyncio.run() returned:", CLOSED)
elif mode == "explicit":
    asyncio.run(main_explicit_shutdown())
    print("after asyncio.run() returned:", CLOSED)
elif mode == "closed-loop":
    # The pathological one: aclose() attempted after the loop is gone.
    loop = asyncio.new_event_loop()

    async def setup():
        gen = build()
        it = gen.__aiter__()
        while True:
            chunk = await asyncio.wait_for(anext(it), 3)
            if chunk == b": ping\n\n":
                break
        return gen, it

    gen, it = loop.run_until_complete(setup())
    loop.close()
    print("loop closed; upstream:", CLOSED)
    loop2 = asyncio.new_event_loop()
    try:
        loop2.run_until_complete(asyncio.wait_for(gen.aclose(), 3))
    except BaseException as exc:
        print("aclose() on a dead-loop generator raised:", type(exc).__name__, exc)
    else:
        print("aclose() on a dead-loop generator returned; upstream:", CLOSED)
    loop2.close()
