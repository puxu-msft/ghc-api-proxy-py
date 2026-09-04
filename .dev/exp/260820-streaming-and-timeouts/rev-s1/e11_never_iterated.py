"""Edge: closing a delivery that was never iterated."""

import asyncio
import sys
from collections.abc import AsyncIterator
from types import SimpleNamespace

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/src")

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.server.pipeline_app import _counted_upstream


async def main() -> None:
    started: list[str] = []
    closed: list[str] = []

    async def raw() -> AsyncIterator[bytes]:
        started.append("started")
        try:
            yield b"event: ping\ndata: {}\n\n"
        finally:
            closed.append("closed")

    chain = SimpleNamespace(active_requests=SimpleNamespace(add_bytes=lambda *_: None))
    source = _counted_upstream(raw(), chain, "rid", SimpleNamespace(received=0))
    gen = stream_delivery(
        source,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0),
        message_id="m",
        model="model",
    )
    await gen.aclose()
    print(f"never-iterated delivery: aclose() ran -> upstream started={started} closed={closed}")


asyncio.run(main())
