"""Streaming delivery: read upstream, release each block as it completes.

The client sees a block only once it is whole, and sees nothing at all before the first one.
Between blocks the connection is kept alive with SSE comments.
They carry no content, so they cannot be mistaken for a block.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.pipeline.delivery.anthropic_sse import block_frames, message_start, terminal_frames
from app.pipeline.delivery.assembler import BlockAssembler
from app.pipeline.delivery.blocks import BlockBuffer, CompletedBlock, DeliverySession
from app.pipeline.delivery.sse_source import SseEvent, read_events

PING_FRAME = b": ping\n\n"


@dataclass(frozen=True, slots=True)
class StreamSettings:
    sse_ping_interval: int = 15
    synthesized_response_headers_after_sec: int = 0


async def _events_with_ping(
    chunks: AsyncIterator[bytes],
    interval: int,
) -> AsyncIterator[SseEvent | None]:
    """Yield events, and `None` whenever the interval passes without one.

    A `None` is the caller's cue to send a keep-alive.
    Waiting on upstream in silence is what makes a client give up on a long thinking turn.
    """
    events = read_events(chunks).__aiter__()
    while True:
        task = asyncio.ensure_future(anext(events))
        try:
            while True:
                try:
                    yield await asyncio.wait_for(asyncio.shield(task), timeout=interval or None)
                    break
                except TimeoutError:
                    yield None
        except StopAsyncIteration:
            return
        finally:
            if task.done() and not task.cancelled():
                task.exception()


async def stream_delivery(
    chunks: AsyncIterator[bytes],
    assembler: BlockAssembler,
    *,
    buffer: BlockBuffer,
    settings: StreamSettings,
    message_id: str,
    model: str,
) -> AsyncIterator[bytes]:
    """Turn an upstream byte stream into Anthropic SSE, one complete block at a time."""
    session = DeliverySession(buffer=buffer)
    started = False

    async for event in _events_with_ping(chunks, settings.sse_ping_interval):
        if event is None:
            if started:
                yield PING_FRAME
            continue
        for block in assembler.push(event):
            for chunk in _commit(session, block, message_id, model, started):
                if not started:
                    started = True
                yield chunk

    remaining = session.finish()
    if remaining and not started:
        # The held-back path needs the same preamble as the incremental one.
        yield message_start(message_id, model).encode()
        started = True
    for block in remaining:
        for frame in block_frames(block):
            yield frame.encode()

    if started:
        terminal = assembler.terminal
        for frame in terminal_frames(
            stop_reason=terminal.stop_reason,
            usage=terminal.usage or None,
        ):
            yield frame.encode()


def _commit(
    session: DeliverySession,
    block: CompletedBlock,
    message_id: str,
    model: str,
    started: bool,
) -> list[bytes]:
    """Offer one block and frame whatever the buffer released."""
    released = session.offer(block)
    if not released:
        return []
    chunks: list[bytes] = []
    if not started:
        # message_start waits for the first block.
        # A response that never produces one never looks like a message that began.
        chunks.append(message_start(message_id, model).encode())
    for ready in released:
        for frame in block_frames(ready):
            chunks.append(frame.encode())
    return chunks


def synthesized_headers_block(text: str = "") -> CompletedBlock:
    """A placeholder block used when upstream has produced no headers for too long.

    Synthesising one forfeits the real upstream status code.
    It is only worth doing when the alternative is the client timing out.
    """
    payload: dict[str, Any] = {"type": "text", "text": text}
    return CompletedBlock(index=0, kind="text", payload=payload)
