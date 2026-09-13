from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import orjson
import pytest

from app.pipeline.delivery.blocks import BlockBuffer, CompletedBlock
from app.pipeline.delivery.formats.anthropic_messages import (
    AnthropicAssembler,
    AnthropicFramer,
)
from app.pipeline.delivery.stream import (
    StreamSettings,
    UpstreamSource,
    stream_delivery,
)


def _frame(event: str, data: dict[str, Any]) -> bytes:
    return (
        f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n"
    ).encode()


async def _anthropic_source() -> AsyncIterator[bytes]:
    yield _frame(
        "content_block_start",
        {"index": 0, "content_block": {"type": "text"}},
    )
    yield _frame(
        "content_block_delta",
        {"index": 0, "delta": {"type": "text_delta", "text": "hello"}},
    )
    yield _frame("content_block_stop", {"index": 0})
    yield _frame("message_delta", {"delta": {"stop_reason": "end_turn"}})
    yield _frame("message_stop", {})


@pytest.mark.asyncio
async def test_stream_delivery_reports_only_client_committed_blocks() -> None:
    source = UpstreamSource(_anthropic_source())
    committed: list[tuple[object, ...]] = []

    chunks = [
        chunk
        async for chunk in stream_delivery(
            source,
            AnthropicAssembler(),
            upstream=source,
            buffer=BlockBuffer("block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="model"),
            on_committed=committed.append,
        )
    ]

    assert chunks
    assert len(committed) == 1
    [unit] = committed[0]
    assert isinstance(unit, CompletedBlock)
    assert unit.payload == {"type": "text", "text": "hello"}
