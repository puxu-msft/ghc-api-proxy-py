"""Streaming delivery: read upstream, release each block as it completes.

The client sees a block only once it is whole, and sees nothing at all before the first one.
Between blocks the connection is kept alive with SSE comments.
They carry no content, so they cannot be mistaken for a block.

The keep-alive here is the **client-facing** one, and its cadence hangs off the last byte written to the client — never off upstream activity. Block-level delivery decouples the two sides: an upstream sending a delta every 200ms still leaves the client without a byte for however long the block takes to close. Keying the cadence on upstream events installed the guard backwards — it fired while upstream was quiet, and stayed silent while upstream was busy, which is the window a client actually gives up in. The upstream-facing keep-alive is a separate mechanism with separate settings and shares no timer with this one; see `.dev/docs/delivery-keepalive/spec.md`.
"""

import asyncio
import sys
from collections.abc import AsyncGenerator, AsyncIterator, Callable
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
    signature_compat: ContentBlockStartCompat = "signature_delta"


@dataclass(slots=True)
class _LastWrite:
    """When the client last received a byte from us.

    Mutable, and shared with `_events_with_ping`, which owns the keep-alive schedule but cannot see what the caller hands downstream: its own input is upstream bytes and its own output is events. This one number is the whole of what has to cross that boundary.
    """

    at: float


@dataclass(frozen=True, slots=True)
class _Pull:
    """One turn of the schedule: whatever upstream produced, and a way to ask whether a cue is owed.

    The question travels as a callable rather than an answer because the caller asks it at a different moment than the scheduler could: assembling an event is synchronous and unbounded, so a deadline can come due during it. Sampled at pull time, the answer was already stale by the time the caller could act on it, and the keep-alive slipped by a whole assembly. `claim` reads the clock when the caller is finally in a position to answer, and advances the schedule only if it says yes.
    """

    event: SseEvent | None
    claim: Callable[[], bool]


async def _events_with_ping(
    chunks: AsyncIterator[bytes],
    interval: int,
    *,
    last_write: _LastWrite,
) -> AsyncGenerator[_Pull]:
    """Pull upstream events, and offer a way to ask whether a deadline has come due.

    A due cue asks the caller for a keep-alive. Waiting on upstream in silence is what makes a client give up on a long thinking turn.

    Typed as a generator because the caller has to be able to close it, and an `AsyncIterator` is not required to offer that.

    The keep-alive deadline lives outside the pull loop, and only two things push it forward: firing, and the caller writing to the client. It used to be rebuilt for every upstream pull, which meant an upstream talking faster than the interval held it permanently in the future — no keep-alive was ever due, while the client waited on a block that had not closed and got nothing at all.

    Both deadlines are answered by the same question, and the caller is the one that knows which of the two it answers. Answering only the keep-alive left the preamble starving under a run of ready events — with keep-alives switched off and synthesis on, a held-back reply's first byte was pushed to the end of the stream. One deadline is left now that the synthesised preamble is gone, and the shape is kept because the reason it had two was never about how many there were: the caller is still the only one that knows whether assembling wrote anything, so it is still the one that asks.

    Nothing here decides that a cue goes out. The scheduler hands over what upstream produced and a way to ask; the caller asks once it has assembled the event and knows whether that wrote anything. That ordering is what keeps an assembler failure, an end-of-stream and a run of ready events from each defeating the guard in its own way. A cue can still land immediately before an ending the next pull has not revealed yet — accepted rather than fixed, because missing an owed keep-alive breaks the contract and sending a spare one does not, and no amount of restructuring tells you what the next pull holds.
    """
    events = read_events(chunks).__aiter__()
    loop = asyncio.get_running_loop()
    task: asyncio.Task[SseEvent] | None = None
    ping_deadline = loop.time() + interval if interval > 0 else None

    def claim() -> bool:
        """Whether a cue is owed at this instant, advancing the keep-alive schedule if that is what came due."""
        nonlocal ping_deadline
        now = loop.time()
        owed = False
        keepalive = _keepalive_due(ping_deadline, last_write, interval)
        if keepalive is not None and now >= keepalive:
            ping_deadline = now + interval
            owed = True
        return owed

    try:
        while True:
            task = asyncio.ensure_future(anext(events))
            while True:
                pending_deadlines = [
                    deadline
                    for deadline in (_keepalive_due(ping_deadline, last_write, interval),)
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
                    # Read before anything else: end-of-stream and failures leave through here, and neither should be preceded by a cue.
                    try:
                        event = task.result()
                    except StopAsyncIteration:
                        return
                    # Keeps `task is not None` meaning exactly "a pull is in flight", which is what the cleanup below reads. Not what stops a finished pull being cancelled — `finish_stream_cleanup` settles a done task without cancelling it either way.
                    task = None
                    yield _Pull(event=event, claim=claim)
                    break
                yield _Pull(event=None, claim=claim)
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


def _keepalive_due(
    ping_deadline: float | None,
    last_write: _LastWrite,
    interval: int,
) -> float | None:
    """When the next keep-alive is owed, or `None` when they are switched off.

    A write to the client discharges the same obligation a keep-alive would, so the next one is due an interval after that write rather than an interval after the last ping.
    """
    if ping_deadline is None:
        return None
    return max(ping_deadline, last_write.at + interval)


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

    Every byte the client gets leaves through the one `yield` below, which is why the keep-alive clock is stamped here rather than at each of the half-dozen places downstream bytes are produced. A seventh such place would otherwise have to remember to stamp it, and forgetting would break nothing visibly — it would quietly let the connection go silent again.

    Stamped *after* the `yield` returns rather than before it. `StreamingResponse` pulls a chunk and then awaits `send`, so this generator only resumes once that chunk has actually been handed to the server; stamping on the way out would time the keep-alive from when we produced the bytes instead of from when they left, and a slow downstream would then get a ping sooner than the interval. Nothing can go out during the gap anyway — the inner generator is suspended for all of it.
    """
    loop = asyncio.get_running_loop()
    last_write = _LastWrite(at=loop.time())
    # `aclosing` rather than a bare `async for`, which closes nothing: closing this generator throws GeneratorExit at the `yield` below, and that unwinds straight past the loop without the inner generator hearing about it.
    async with aclosing(
        _deliver(
            chunks,
            assembler,
            buffer=buffer,
            settings=settings,
            message_id=message_id,
            model=model,
            last_write=last_write,
        )
    ) as inner:
        async for chunk in inner:
            yield chunk
            last_write.at = loop.time()


async def _deliver(
    chunks: AsyncIterator[bytes],
    assembler: BlockAssembler,
    *,
    buffer: BlockBuffer,
    settings: StreamSettings,
    message_id: str,
    model: str,
    last_write: _LastWrite,
) -> AsyncGenerator[bytes]:
    """Assemble and frame the response. Wrapped by `stream_delivery`, which stamps the clock."""
    session = DeliverySession(buffer=buffer)
    # Whether the client has seen a semantic event yet. It gates the keep-alive, which cannot be sent before the response has started, and the error frame at the end, which has nothing to correct if it has not.
    #
    # This used to gate a second thing: a `message_start` synthesised on its own after a long silence, so a client waiting on a slow turn saw something. That is gone. The preamble now leaves only alongside the first complete block, so `client_has_bytes` and "a block has been delivered" became the same fact — which is what lets a retry after a torn stream stay invisible, and what makes a half-opened response unreachable rather than a state to handle.
    client_has_bytes = asyncio.Event()

    # `aclosing` for the same reason as above: the inner generator owns the upstream pull, and only closing it releases the response.
    async with aclosing(
        _events_with_ping(
            chunks,
            settings.sse_ping_interval,
            last_write=last_write,
        )
    ) as events:
        async for pull in events:
            wrote = False
            if pull.event is not None:
                # Assembled before any cue is answered. A pull that came back with an event has not shown that the event can be delivered: a malformed one makes the assembler raise right here, and that has to reach the caller ahead of a comment claiming everything is fine.
                for block in assembler.push(pull.event):
                    for chunk in _commit(
                        session,
                        block,
                        message_id,
                        model,
                        client_has_bytes.is_set(),
                        settings.signature_compat,
                    ):
                        client_has_bytes.set()
                        wrote = True
                        yield chunk
            # Asked here, and only here, because this is the first moment both answers exist: whether assembling wrote anything, and what the clock reads now that it has. Real bytes discharge the same obligation a cue would have answered, so `wrote` short-circuits and the schedule is left alone.
            if wrote or not pull.claim():
                continue
            if client_has_bytes.is_set():
                yield PING_FRAME
            # Nothing is owed to a client that has seen no bytes. The alternative — a `message_start` on its own, so a slow turn shows something — was measured and removed: it settles the response's status long before upstream has said what it is, so a 429 arriving at second 300 can no longer be answered as one. A client that waits is told the truth late; a client told 200 early is told something that cannot be taken back.

    remaining = session.finish()
    if remaining and not client_has_bytes.is_set():
        # The held-back path needs the same preamble as the incremental one.
        yield message_start(message_id, model).encode()
        client_has_bytes.set()
    for block in remaining:
        for frame in block_frames(block, signature_compat=settings.signature_compat):
            yield frame.encode()

    terminal = assembler.terminal
    if not client_has_bytes.is_set():
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
