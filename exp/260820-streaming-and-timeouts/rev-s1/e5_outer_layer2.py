"""Refined: hold no stray references, count pending tasks absolutely."""

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


def others() -> set:
    return {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}


def build(*, wrap_tracked: bool):
    closed: list[str] = []
    trace = SimpleNamespace(received=0)
    payloads = anthropic_stream("hello", "world")

    async def raw() -> AsyncIterator[bytes]:
        try:
            for p in payloads[:3]:
                yield p
            await asyncio.Event().wait()
        except BaseException as exc:  # noqa: BLE001
            closed.append(f"received:{type(exc).__name__}")
            raise
        finally:
            closed.append("closed")

    chain = SimpleNamespace(active_requests=SimpleNamespace(add_bytes=lambda *_: None))
    gen = stream_delivery(
        _counted_upstream(raw(), chain, "rid", trace),
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0.05),  # type: ignore[arg-type]
        message_id="m",
        model="model",
    )
    if wrap_tracked:
        gen = _tracked_delivery(gen, SimpleNamespace(finish=lambda: None))
    return gen, closed


async def run(label: str, *, wrap_tracked: bool) -> None:
    gen, closed = build(wrap_tracked=wrap_tracked)
    it = gen.__aiter__()
    while True:
        chunk = await asyncio.wait_for(anext(it), 3)
        if chunk == b": ping\n\n":
            break
    pending_before = len(others())
    await gen.aclose()
    print(f"{label}: after aclose() returned -> upstream={closed} pending_tasks {pending_before} -> {len(others())}")
    del it, gen
    for i in range(1, 6):
        gc.collect()
        await asyncio.sleep(0.02)
        if closed:
            print(f"    upstream closed only after {i} gc+sleep rounds: {closed}")
            break
    else:
        print(f"    upstream STILL not closed after 5 gc+sleep rounds; pending_tasks={len(others())}")
    for t in others():
        print("      leftover:", t)
        t.cancel()
    await asyncio.sleep(0.05)


async def main() -> None:
    await run("[close stream_delivery directly]", wrap_tracked=False)
    await run("[close _tracked_delivery (production body_iterator)]", wrap_tracked=True)


asyncio.run(main())
