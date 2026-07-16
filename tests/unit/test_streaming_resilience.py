from collections.abc import AsyncIterator

import anyio
import pytest

from app.streaming.buffered_retry import BufferLimitExceeded, collect_with_limit
from app.streaming.delayed_commit import delayed_first_item
from app.streaming.keepalive import keepalive_stream


@pytest.mark.asyncio
async def test_keepalive_emits_heartbeat_during_silence() -> None:
    async def source() -> AsyncIterator[bytes]:
        await anyio.sleep(0.03)
        yield b"data"

    stream = keepalive_stream(source(), interval_seconds=0.01, heartbeat=b": ping\n\n")
    frames: list[bytes] = []
    try:
        for _ in range(5):
            frame = await anext(stream)
            frames.append(frame)
            if frame == b"data":
                break
    finally:
        await stream.aclose()
    assert frames[-1] == b"data"
    assert frames.count(b": ping\n\n") >= 2


@pytest.mark.asyncio
async def test_delayed_commit_waits_for_first_item_only() -> None:
    async def source() -> AsyncIterator[int]:
        yield 1
        yield 2

    first, remainder = await delayed_first_item(source(), timeout_seconds=1)
    assert first == 1
    assert [item async for item in remainder] == [2]


@pytest.mark.asyncio
async def test_buffered_retry_enforces_memory_cap() -> None:
    async def source() -> AsyncIterator[bytes]:
        yield b"1234"
        yield b"5678"

    with pytest.raises(BufferLimitExceeded):
        await collect_with_limit(source(), cap_bytes=7)