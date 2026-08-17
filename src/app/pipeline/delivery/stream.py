"""Streaming delivery: read upstream, release each block as it completes.

The client sees a block only once it is whole, and sees nothing at all before the first one.
Between blocks the connection is kept alive with SSE comments.
They carry no content, so they cannot be mistaken for a block.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, replace
from typing import Any

from app.config.schema import ContentBlockStartCompat
from app.pipeline.delivery.anthropic_sse import block_frames, message_start, terminal_frames
from app.pipeline.delivery.assembler import BlockAssembler
from app.pipeline.delivery.blocks import BlockBuffer, CompletedBlock, DeliverySession
from app.pipeline.delivery.sse_source import SseEvent, read_events

PING_FRAME = b": ping\n\n"


@dataclass(frozen=True, slots=True)
class StreamSettings:
    sse_ping_interval: int = 15
    synthesized_response_headers_after_sec: int = 0
    signature_compat: ContentBlockStartCompat = "signature_delta"


async def _events_with_ping(
    chunks: AsyncIterator[bytes],
    interval: int,
    *,
    response_headers_deadline: float | None = None,
    response_started: asyncio.Event | None = None,
) -> AsyncIterator[SseEvent | None]:
    """Yield events, and `None` whenever an enabled deadline passes without one.

    A `None` cues the caller to send a keep-alive.
    Before the first complete block, it cues response-preamble synthesis.
    Waiting on upstream in silence is what makes a client give up on a long thinking turn.
    """
    events = read_events(chunks).__aiter__()
    loop = asyncio.get_running_loop()
    while True:
        task = asyncio.ensure_future(anext(events))
        ping_deadline = loop.time() + interval if interval > 0 else None
        try:
            while True:
                pending_deadlines = [
                    deadline
                    for deadline in (
                        ping_deadline,
                        response_headers_deadline
                        if response_started is not None and not response_started.is_set()
                        else None,
                    )
                    if deadline is not None
                ]
                timeout = (
                    max(0.0, min(pending_deadlines) - loop.time())
                    if pending_deadlines
                    else None
                )
                try:
                    yield await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
                    break
                except TimeoutError:
                    if ping_deadline is not None and loop.time() >= ping_deadline:
                        ping_deadline = loop.time() + interval
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
) -> AsyncGenerator[bytes]:
    """Turn an upstream byte stream into Anthropic SSE, one complete block at a time.

    Typed as a generator rather than a plain iterator so a caller that stops early can close
    it: abandoning it mid-stream otherwise leaves the upstream response open until the loop
    is collected.
    """
    session = DeliverySession(buffer=buffer)
    started = False
    synthetic_block_sent = False
    response_started = asyncio.Event()
    response_headers_deadline = (
        asyncio.get_running_loop().time() + settings.synthesized_response_headers_after_sec
        if settings.synthesized_response_headers_after_sec > 0
        else None
    )

    async for event in _events_with_ping(
        chunks,
        settings.sse_ping_interval,
        response_headers_deadline=response_headers_deadline,
        response_started=response_started,
    ):
        if event is None:
            if (
                response_headers_deadline is not None
                and not response_started.is_set()
                and asyncio.get_running_loop().time() >= response_headers_deadline
            ):
                response_started.set()
                synthetic_block_sent = True
                # Written straight out rather than offered to the buffer. Its whole purpose is to
                # put bytes in front of a client that would otherwise time out, and `full` or
                # `until-tool-use` would hold it back for exactly as long as the wait that made it
                # necessary — which is the same as not synthesising anything.
                for chunk in _frame_now(
                    synthesized_headers_block(),
                    message_id,
                    model,
                    started,
                    settings.signature_compat,
                ):
                    started = True
                    yield chunk
            elif started:
                yield PING_FRAME
            continue
        blocks = assembler.push(event)
        if blocks:
            # The synthesis timer ends when the first real complete block arrives.
            # It ends even if the selected buffering policy holds that block for a later commit.
            response_started.set()
        for block in blocks:
            if synthetic_block_sent:
                # Index zero belongs to the completed synthetic block already sent downstream.
                block = replace(block, index=block.index + 1)
            for chunk in _commit(
                session, block, message_id, model, started, settings.signature_compat
            ):
                if not started:
                    started = True
                yield chunk

    remaining = session.finish()
    if remaining and not started:
        # The held-back path needs the same preamble as the incremental one.
        yield message_start(message_id, model).encode()
        started = True
    for block in remaining:
        for frame in block_frames(block, signature_compat=settings.signature_compat):
            yield frame.encode()

    if started:
        terminal = assembler.terminal
        for frame in terminal_frames(
            stop_reason=terminal.stop_reason,
            usage=terminal.usage or None,
        ):
            yield frame.encode()


def _frame_now(
    block: CompletedBlock,
    message_id: str,
    model: str,
    started: bool,
    signature_compat: ContentBlockStartCompat,
) -> list[bytes]:
    """Frame one block for immediate delivery, bypassing the buffering policy.

    Only for blocks whose value is that they arrive *now*. A content block must still go through
    `_commit`, because the policy is what the operator configured for content.
    """
    chunks: list[bytes] = []
    if not started:
        chunks.append(message_start(message_id, model).encode())
    for frame in block_frames(block, signature_compat=signature_compat):
        chunks.append(frame.encode())
    return chunks


def _commit(
    session: DeliverySession,
    block: CompletedBlock,
    message_id: str,
    model: str,
    started: bool,
    signature_compat: ContentBlockStartCompat,
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
        for frame in block_frames(ready, signature_compat=signature_compat):
            chunks.append(frame.encode())
    return chunks


def synthesized_headers_block(text: str = "") -> CompletedBlock:
    """A placeholder block used when upstream has produced no headers for too long.

    Synthesising one forfeits the real upstream status code.
    It is only worth doing when the alternative is the client timing out.
    """
    payload: dict[str, Any] = {"type": "text", "text": text}
    return CompletedBlock(index=0, kind="text", payload=payload)
