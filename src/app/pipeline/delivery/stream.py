"""Streaming delivery: read upstream, release each block as it completes.

The client sees a block only once it is whole, and sees nothing at all before the first one.
Between blocks the connection is kept alive with SSE comments.
They carry no content, so they cannot be mistaken for a block.
"""

import asyncio
import sys
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass

from app.config.schema import ContentBlockStartCompat
from app.errors import WIRE_TYPES, ErrorCategory
from app.pipeline.delivery.anthropic_sse import (
    block_frames,
    error_frame,
    message_start,
    terminal_frames,
)
from app.pipeline.delivery.assembler import BlockAssembler
from app.pipeline.delivery.blocks import BlockBuffer, CompletedBlock, DeliverySession
from app.pipeline.delivery.sse_source import SseEvent, read_events
from app.streaming.keepalive import finish_stream_cleanup

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
) -> AsyncGenerator[SseEvent | None]:
    """Yield events, and `None` whenever an enabled deadline passes without one.

    A `None` cues the caller to send a keep-alive.
    Before the first complete block, it cues response-preamble synthesis.
    Waiting on upstream in silence is what makes a client give up on a long thinking turn.

    Typed as a generator because the caller has to be able to close it, and an `AsyncIterator` is not required to offer that.
    """
    events = read_events(chunks).__aiter__()
    loop = asyncio.get_running_loop()
    task: asyncio.Task[SseEvent] | None = None
    try:
        while True:
            task = asyncio.ensure_future(anext(events))
            ping_deadline = loop.time() + interval if interval > 0 else None
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
                # Waited on directly rather than through `wait_for(shield(task), ...)`. Both leave the pull running past a timeout, but a shield whose waiter times out hands the pull a last-resort observer that reports whatever it ends with, and a later shield over the same pull installs its own observer without displacing that one. So the StopAsyncIteration that merely means end-of-stream gets reported as `StopAsyncIteration exception in shielded future` on the operator's stderr, once for every pull that outlived a keep-alive. `asyncio.wait` needs no observer, and `session_liveness_stream` already waits this way.
                await asyncio.wait({task}, timeout=timeout)
                if task.done():
                    try:
                        event = task.result()
                    except StopAsyncIteration:
                        return
                    # Keeps `task is not None` meaning exactly "a pull is in flight", which is what the cleanup below reads. Not what stops a finished pull being cancelled — `finish_stream_cleanup` settles a done task without cancelling it either way.
                    task = None
                    yield event
                    break
                if ping_deadline is not None and loop.time() >= ping_deadline:
                    ping_deadline = loop.time() + interval
                yield None
    finally:
        # The pull is this generator's to dispose of, and until this was here nothing disposed of it: a client that goes away mid-turn left the pull pending forever, holding the upstream response open through its own stack frame — which also made it unreachable for the collector. `session_liveness_stream` and `stream_response` settle theirs the same way, through the same helper.
        # Only a pull that is genuinely in flight is cancelled; a finished one is observed and left alone. The cancellation is delivered at the upstream's own await point, so every `finally` down that stack runs, which is what closes the HTTP response. It is also the only way through: `aclose()` on a generator with an `anext` in flight raises `RuntimeError`, so settling the pull first is a precondition for closing at all.
        primary = sys.exception()
        if isinstance(primary, GeneratorExit):
            primary = None
        cleanup_error, cleanup_cancellation = await finish_stream_cleanup(
            task, events, primary=primary
        )
        primary = primary or cleanup_cancellation
        if primary is not None:
            if cleanup_error is not None:
                raise primary from cleanup_error
            if cleanup_cancellation is not None:
                raise primary
        elif cleanup_error is not None:
            raise cleanup_error


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

    Typed as a generator rather than a plain iterator so a caller that stops early can close it: abandoning it mid-stream otherwise leaves the upstream response open until the loop is collected.
    """
    session = DeliverySession(buffer=buffer)
    started = False
    response_started = asyncio.Event()
    response_headers_deadline = (
        asyncio.get_running_loop().time() + settings.synthesized_response_headers_after_sec
        if settings.synthesized_response_headers_after_sec > 0
        else None
    )

    # `aclosing` rather than a bare `async for`, which closes nothing: closing this generator throws GeneratorExit at whichever `yield` below is suspended, and that unwinds straight past the loop without the inner generator hearing about it. Its cleanup would then be left to the collector, which cannot reach it either — so the promise in the docstring above held only as far as this line. `keepalive_stream` wraps its own inner generator for the same reason.
    async with aclosing(
        _events_with_ping(
            chunks,
            settings.sse_ping_interval,
            response_headers_deadline=response_headers_deadline,
            response_started=response_started,
        )
    ) as events:
        async for event in events:
            if event is None:
                if (
                    response_headers_deadline is not None
                    and not response_started.is_set()
                    and asyncio.get_running_loop().time() >= response_headers_deadline
                ):
                    response_started.set()
                    # `message_start` and nothing else. What this moment needs is bytes in front of a client that would otherwise time out, and `message_start` is the first thing every stream sends anyway — sending it early costs the client nothing and commits us to no content.
                    # It used to be a placeholder text block, which the client stores as part of the turn and replays in its next request. Measured on 2026-08-20: a 242-second wait put `{"type":"text","text":""}` into a session's history and upstream rejected the following request outright — `messages: text content blocks must be non-empty` — over a block that never carried anything.
                    # Written straight out rather than offered to the buffer, for the same reason as before: `full` or `until-tool-use` would hold it back for exactly as long as the wait that made it necessary, which is the same as not synthesising anything.
                    started = True
                    yield message_start(message_id, model).encode()
                elif started:
                    yield PING_FRAME
                continue
            blocks = assembler.push(event)
            if blocks:
                # The synthesis timer ends when the first real complete block arrives.
                # It ends even if the selected buffering policy holds that block for a later commit.
                response_started.set()
            for block in blocks:
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

    terminal = assembler.terminal
    if not started:
        # Nothing was ever committed downstream, so there is no started message to correct — the same case the legacy chain leaves to its caller (`render_error` there runs only `if session.frontier.message_start_accepted`). An upstream that produced no block and no terminal still leaves the client a 200 with an empty body; that is pre-existing behaviour on a path this slice does not touch, and widening it is a separate question from STR-04's flush.
        return
    if not terminal.seen:
        # STR-04: an EOF with no legal terminal event is truncation, not success.
        # Ported from the legacy chain rather than redesigned, as `implementation.md` directs: `app/delivery/responses_anthropic_stream.py`, on `not frontier.terminal_accepted`, raises `incomplete_responses_stream` and renders an SSE error. Same code, same wire shape, same message, same gate on the message having started — a client that already learned to read one of these does not have to learn a second.
        # `message_stop` deliberately does not follow. The frozen Spec rules these two mutually exclusive: 不得再发 `message_stop` 冒充成功.
        yield error_frame(
            error_type=WIRE_TYPES[ErrorCategory.UPSTREAM],
            message="Responses stream ended before a successful terminal event",
            code="incomplete_responses_stream",
        ).encode()
        return
    # `or "end_turn"` is still a synthesis, and still visible where it happens — but it now only ever runs on a stream that really did see a terminal event, so it fills in a field upstream left empty rather than inventing an ending upstream never reached. An upstream that sends an explicit empty `stop_reason` gets `end_turn`, because `""` is not a stop reason any Anthropic consumer accepts.
    for frame in terminal_frames(
        stop_reason=terminal.stop_reason or "end_turn",
        usage=terminal.usage or None,
    ):
        yield frame.encode()


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
