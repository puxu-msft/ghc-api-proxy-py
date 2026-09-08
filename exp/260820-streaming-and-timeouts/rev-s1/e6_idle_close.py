"""Idle-case close: no pull in flight. Does GeneratorExit reach the httpx-shaped source?"""

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
from app.server.pipeline_app import _counted_upstream


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


async def run(*, with_counted: bool) -> None:
    closed: list[str] = []
    payloads = anthropic_stream("hello", "world")

    async def raw() -> AsyncIterator[bytes]:
        """Stands in for httpx Response.aiter_bytes(): releasing it releases the connection."""
        try:
            # deliver two whole blocks at once so the consumer can stop between byte frames
            yield b"".join(payloads[:6])
            await asyncio.Event().wait()
        except BaseException as exc:  # noqa: BLE001
            closed.append(f"received:{type(exc).__name__}")
            raise
        finally:
            closed.append("closed")

    source: AsyncIterator[bytes] = raw()
    if with_counted:
        chain = SimpleNamespace(active_requests=SimpleNamespace(add_bytes=lambda *_: None))
        source = _counted_upstream(source, chain, "rid", SimpleNamespace(received=0))

    gen = stream_delivery(
        source,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0),
        message_id="m",
        model="model",
    )
    it = gen.__aiter__()
    await anext(it)  # message_start -- delivered with no pull in flight behind it
    await gen.aclose()
    label = "with _counted_upstream" if with_counted else "raw source directly"
    print(f"[idle close, {label}] at aclose() return: {closed}")
    if not closed:
        for i in range(1, 11):
            await asyncio.sleep(0)
            if closed:
                print(f"    closed {i} ticks later: {closed}")
                break
        else:
            gc.collect()
            await asyncio.sleep(0.02)
            print(f"    only after gc: {closed}")


async def main() -> None:
    await run(with_counted=False)
    await run(with_counted=True)


asyncio.run(main())
