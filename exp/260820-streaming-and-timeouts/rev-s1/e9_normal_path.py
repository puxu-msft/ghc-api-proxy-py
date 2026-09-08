"""Item 3: a complete, ordinary stream with real pings. The upstream must never see a cancel."""

import asyncio
import sys
from collections.abc import AsyncIterator

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/src")

import orjson

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import PING_FRAME, StreamSettings, stream_delivery


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


async def run(interval: float, gap: float, label: str) -> None:
    seen: list[str] = []
    payloads = anthropic_stream("alpha", "beta", "gamma")

    async def raw() -> AsyncIterator[bytes]:
        try:
            for p in payloads:
                await asyncio.sleep(gap)
                yield p
            seen.append("exhausted-naturally")
        except BaseException as exc:  # noqa: BLE001
            seen.append(f"received:{type(exc).__name__}")
            raise
        finally:
            seen.append("finally-ran")

    out = [
        c
        async for c in stream_delivery(
            raw(),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=interval),  # type: ignore[arg-type]
            message_id="m",
            model="model",
        )
    ]
    pings = sum(1 for c in out if c == PING_FRAME)
    kinds = [c.split(b"\n", 1)[0].decode() for c in out if c != PING_FRAME]
    print(f"{label}: pings={pings} frames={len(out)} upstream={seen}")
    print(f"    events: {[k.removeprefix('event: ') for k in kinds]}")
    assert "received:CancelledError" not in seen, "upstream was CANCELLED on the normal path"
    assert "received:GeneratorExit" not in seen, "upstream got GeneratorExit on the normal path"
    assert seen[0] == "exhausted-naturally"
    assert pings > 0 or interval == 0, "no pings were produced -- the case was not exercised"


async def main() -> None:
    await run(0, 0.0, "no ping, no gap        ")
    await run(0.05, 0.12, "ping interval 0.05, gap 0.12")
    await run(1, 1.2, "ping interval 1s (production shape), gap 1.2s")


asyncio.run(main())
