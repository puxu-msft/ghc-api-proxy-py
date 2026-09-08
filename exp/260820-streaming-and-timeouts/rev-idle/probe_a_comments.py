"""(a) Does read_events discard SSE comment frames?"""
import asyncio
from collections.abc import AsyncIterator
from app.pipeline.delivery.sse_source import read_events


async def upstream() -> AsyncIterator[bytes]:
    yield b": ping\n\n"
    yield b": ping\n\n"
    yield b'event: message_start\ndata: {"x":1}\n\n'
    yield b": ping\n\n"


async def main() -> None:
    events = [event async for event in read_events(upstream())]
    print(f"chunks fed: 4 (3 comment frames + 1 real event)")
    print(f"events yielded: {len(events)} -> {events}")


asyncio.run(main())
