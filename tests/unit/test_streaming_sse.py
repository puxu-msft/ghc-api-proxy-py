from collections.abc import AsyncIterator

import anyio
import pytest

from app.config.settings import TimeoutConfig
from app.streaming.idle_timeout import (
    StreamIdleTimeoutError,
    resolve_stream_idle,
    with_idle_timeout,
)
from app.streaming.sse import create_sse_response, format_sse_event, passthrough_bytes


def test_format_sse_event_handles_multiline_data() -> None:
    assert format_sse_event("line1\nline2", event="delta") == (
        b"event: delta\ndata: line1\ndata: line2\n\n"
    )


@pytest.mark.asyncio
async def test_passthrough_bytes_yields_each_upstream_chunk_immediately() -> None:
    sent = anyio.Event()
    release = anyio.Event()

    async def upstream() -> AsyncIterator[bytes]:
        sent.set()
        yield b"first"
        await release.wait()
        yield b"second"

    stream = passthrough_bytes(upstream())
    assert await anext(stream) == b"first"
    await sent.wait()
    release.set()
    assert await anext(stream) == b"second"


def test_sse_response_sets_no_buffering_headers() -> None:
    async def empty() -> AsyncIterator[bytes]:
        if False:
            yield b""

    response = create_sse_response(empty())

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


@pytest.mark.asyncio
async def test_idle_timeout_is_per_item_not_total_duration() -> None:
    async def source() -> AsyncIterator[int]:
        yield 1
        await anyio.sleep(0.01)
        yield 2

    assert [item async for item in with_idle_timeout(source(), 0.1)] == [1, 2]


@pytest.mark.asyncio
async def test_idle_timeout_raises_when_next_item_stalls() -> None:
    async def stalled() -> AsyncIterator[int]:
        await anyio.sleep(1)
        yield 1

    with pytest.raises(StreamIdleTimeoutError):
        _ = [item async for item in with_idle_timeout(stalled(), 0.01)]


def test_resolve_stream_idle_prefers_model_override() -> None:
    settings = TimeoutConfig(
        stream_idle=300,
        stream_idle_overrides={"gpt-5.5": 600, "claude-test": 120},
    )

    assert resolve_stream_idle("claude-test-v2", settings) == 120
    assert resolve_stream_idle("other", settings) == 300