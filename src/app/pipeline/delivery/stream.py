"""Streaming delivery: read upstream, release each block as it completes.

The client sees a block only once it is whole, and sees no *content* before the first one.
Between blocks, and before the first, the connection is kept alive with SSE comments.
They carry no content, so they cannot be mistaken for a block.
The response itself is already open by then: it is built with upstream's own status once its headers arrive, and the framework sends `http.response.start` before pulling a single chunk. So a comment changes nothing about what the client was told, while withholding one only spends the wait in silence.

The keep-alive here is the **client-facing** one, and its cadence hangs off the last byte written to the client — never off upstream activity. Block-level delivery decouples the two sides: an upstream sending a delta every 200ms still leaves the client without a byte for however long the block takes to close. Keying the cadence on upstream events installed the guard backwards — it fired while upstream was quiet, and stayed silent while upstream was busy, which is the window a client actually gives up in. The upstream-facing keep-alive is a separate mechanism with separate settings and shares no timer with this one; see `.dev/docs/delivery-keepalive/spec.md`.
"""

import asyncio
import sys
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass, replace
from typing import Any

from app.config.schema import ContentBlockStartCompat
from app.errors import WIRE_TYPES, ErrorCategory
from app.pipeline.delivery.anthropic_sse import AnthropicFramer
from app.pipeline.delivery.assembler import BlockAssembler
from app.pipeline.delivery.blocks import BlockBuffer, CompletedBlock, DeliverySession
from app.pipeline.delivery.framing import OutboundFramer
from app.pipeline.delivery.sse_source import SseEvent, read_events
from app.pipeline.retry import RetryLedger, RetryReason, StreamEnding, decide_stream_ending
from app.streaming.deadline import ClientDeadlineError
from app.streaming.keepalive import finish_stream_cleanup

PING_FRAME = b": ping\n\n"
# The Anthropic name for both the block kind and the stop reason that goes with it.
TOOL_USE_KIND = "tool_use"


# What one replaced attempt hands over: a fresh byte stream, and the fresh assembler and buffer that go with it. Nothing from the attempt it replaces travels with them.
type Attempt = tuple[AsyncIterator[bytes], BlockAssembler, BlockBuffer]


@dataclass(frozen=True, slots=True)
class ReplaySupport:
    """What delivery needs in order to replace a torn attempt, and nothing more.

    The two halves of the decision are deliberately on opposite sides of this boundary, because they are answers to different questions and only one of them is delivery's to answer. **Whether a replay is legal at all** is a fact about position — has the client seen anything, is there a committed block, is there budget — and delivery is the only thing that knows it. **Whether this particular failure is one another attempt could answer** is a fact about upstream's error taxonomy, which delivery has no business importing: a transport tear may be replaced, a conversion error and a refusal may not, and that vocabulary belongs to the layer that speaks to upstream.

    `eligible` is asked first and costs nothing, so a failure no attempt can answer never spends budget on being told so. It answers with the reason the failure draws on rather than a yes, because the budget it will spend is the ordinary one for that reason — a torn body is a network failure at a later instant, not a kind of its own.
    """

    ledger: RetryLedger
    eligible: Callable[[Exception], RetryReason | None]
    reopen: Callable[[], Awaitable[Attempt | None]]


@dataclass(frozen=True, slots=True)
class ContinuationSupport:
    """Hands a turn that cannot be finished back to the client as a tool call it can act on.

    Same division as `ReplaySupport`, for the same reason. Delivery knows *whether* the client is already holding content, which is what decides that this is the only ending left. It does not know what the tool is called, whether this client declared it, or how to name the failure in the vocabulary the tool expects — all of that belongs to the layer that read the client's request.

    Returns the `tool_use` payload rather than a finished block, because the index is delivery's to assign: it is the next one after everything already committed, and nothing outside can know that.

    `None` means do not synthesise — a client whose request cannot carry this, or a failure the caller does not want handed back. The ending then falls through to whatever it would have been.
    """

    synthesize: Callable[[BaseException | None, str], dict[str, Any] | None]


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


async def one_shot_delivery(chunks: AsyncIterator[bytes]) -> AsyncGenerator[bytes]:
    """Hand the upstream stream to the client whole, once all of it has arrived.

    For a client leg this proxy has no outbound framer for. Block-level delivery needs two halves — something that knows where a block ends in the upstream's events, and something that writes one in the client's — and Chat Completions has neither: its boundaries live inside `choices[].delta`, which nothing here reads. Ruled 2026-08-22 to buffer rather than to invent them; parsing that shape is its own piece of work.

    The client asked for `stream: true` and gets its own protocol's SSE back, byte for byte, just not incrementally. That is a real loss of liveness and it is the point of the ruling — before this existed those bytes went into the Anthropic assembler, matched none of its event names, produced no block, and left the client holding a 200 with an empty body and no error frame.

    No replay and no keep-alive. Both are answers to questions block delivery raises — which block was already committed, and what to say during the silence between them — and neither has a meaning for a delivery that is a single write.
    """
    body = bytearray()
    async for chunk in chunks:
        body += chunk
    if body:
        yield bytes(body)


async def stream_delivery(
    chunks: AsyncIterator[bytes],
    assembler: BlockAssembler,
    *,
    buffer: BlockBuffer,
    settings: StreamSettings,
    message_id: str,
    model: str,
    framer: OutboundFramer | None = None,
    replay: ReplaySupport | None = None,
    continuation: ContinuationSupport | None = None,
) -> AsyncGenerator[bytes]:
    """Turn an upstream byte stream into the client's SSE, one complete block at a time.

    `framer` decides which protocol that is. Absent, it is Anthropic built from `message_id`, `model` and `settings.signature_compat` — the shape every caller had before there was a second client leg, and why those three parameters are still here.
    A caller whose client asked on `/responses` passes a `ResponsesFramer` instead; see `framer_for`, which selects on the *inbound* format rather than on which upstream answered.

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
            framer=framer,
            last_write=last_write,
            replay=replay,
            continuation=continuation,
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
    framer: OutboundFramer | None,
    last_write: _LastWrite,
    replay: ReplaySupport | None = None,
    continuation: ContinuationSupport | None = None,
) -> AsyncGenerator[bytes]:
    """Assemble and frame the response. Wrapped by `stream_delivery`, which stamps the clock."""
    framing = framer or AnthropicFramer(
        message_id=message_id, model=model, signature_compat=settings.signature_compat
    )
    session = DeliverySession(buffer=buffer)
    # Whether the client has seen a semantic event yet. It gates the error frame at the end, which has nothing to correct if the message never started, and it is half of what decides whether a torn stream may be replayed.
    #
    # It used to gate a `message_start` synthesised on its own after a long silence. That is gone, so the preamble now leaves only alongside the first complete block and this became the same fact as "a block has been delivered" — which is exactly what makes a replay invisible when it is legal, and what keeps a half-opened response from being a state every decision has to carry a case for.
    client_has_bytes = asyncio.Event()

    while True:
        torn: Exception | None = None
        # `aclosing` for the same reason as above: the inner generator owns the upstream pull, and only closing it releases the response. On the way out of a torn attempt this is what hands the old response back before another is opened.
        try:
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
                                framing,
                                client_has_bytes.is_set(),
                            ):
                                client_has_bytes.set()
                                wrote = True
                                yield chunk
                    # Asked here, and only here, because this is the first moment both answers exist: whether assembling wrote anything, and what the clock reads now that it has. Real bytes discharge the same obligation a cue would have answered, so `wrote` short-circuits and the schedule is left alone.
                    if wrote or not pull.claim():
                        continue
                    # Unconditional, because by the time this generator runs the client already holds a 200: the response is built with upstream's own status once its headers have arrived, and the framework sends `http.response.start` before it pulls the first chunk. Nothing here can change what the client was told, so holding the keep-alive back until a block exists buys nothing and spends the whole pre-first-block window in silence — which under `full` and `until-tool-use` is the entire turn.
                    #
                    # An SSE comment before `message_start` is still legal SSE and carries no content, so it cannot be mistaken for part of the turn. What is *not* sent early is the preamble itself: a `message_start` on its own leaves a message opened with nothing in it, and every decision after a torn stream then has to carry a case for that state.
                    yield framing.keepalive()
        except Exception as error:
            # `Exception`, not `BaseException`, and that is the whole of how this side's own endings stay out. A client that goes away and a process that is shutting down both arrive as `CancelledError`, and a generator being closed arrives as `GeneratorExit`; neither derives from `Exception`, so neither reaches here and neither can be mistaken for upstream tearing. The spec calls that distinction `LOCAL_ABORT` and warns that the *position* facts of the two are identical — this is the one place the difference is still visible, so it is read here rather than inferred later.
            torn = error
        if torn is None:
            break
        if isinstance(torn, ClientDeadlineError):
            # The one ending that gets said out loud, and it is answered before anything else — a replay cannot help a request that has run out of time, and asking whether one is legal would put this branch behind a `replay` nobody has to configure.
            #
            # Not gated on a block having been delivered. `client-side-block-delivery.md` puts the condition at the response headers, and by the time this generator runs those have gone out: the response is built with upstream's own status once its headers arrive, and the framework sends `http.response.start` before pulling a chunk. Gating on a delivered block instead meant `full` and `until-tool-use` — which deliver nothing until the stream ends — timed out having sent the client zero bytes and no frame at all.
            #
            # Deliberately only this one. The other endings that reach here remain indistinguishable from each other on the wire, and widening the frame to cover them is a separate question with its own answer to find. Nothing is flushed first either: what is buffered but undelivered would make the size of this ending depend on the buffering policy, while the ending itself is a clock event.
            yield framing.error(
                error_type=WIRE_TYPES[ErrorCategory.INTERNAL],
                message=str(torn) or "client request exceeded its deadline",
                code="client_deadline_exceeded",
            )
            return
        reason = replay.eligible(torn) if replay is not None else None
        if replay is None or reason is None:
            raise torn
        verdict = decide_stream_ending(
            terminal_seen=assembler.terminal.seen,
            downstream_opened=client_has_bytes.is_set(),
            committed_blocks=session.committed_count,
            ledger=replay.ledger,
            reason=reason,
        )
        if verdict.ending is StreamEnding.COMPLETE:
            # Upstream finished this turn and *then* the connection went. Nothing is missing, so nothing is handed over — a tool call here would tell the client to carry on from an answer that is already whole, and it would look exactly like a real one. The ending below is the real one.
            #
            # Read before the replay, because `decide_stream_ending` answers all three and only one of them is a reason to do anything: folding COMPLETE in with ABANDON is what turned a finished turn into a synthesised interruption.
            break
        if verdict.ending is StreamEnding.REPLAY:
            replacement = await replay.reopen()
            if replacement is not None:
                # Everything the failed attempt built is dropped, not carried: a fresh assembler so no draft of its survives, and a fresh buffer so a block it completed but never delivered cannot be delivered twice. `session` goes with the buffer. Legal only because the verdict required nothing to have been committed — there is no frontier here to preserve, and none to roll back.
                chunks, assembler, buffer = replacement
                session = DeliverySession(buffer=buffer)
                continue
        # No second attempt is available, and the client is holding content this side cannot take back. Handing the failure over as a tool call is the only ending that leaves the turn recoverable — by the client, in its own next request. Reached for a failure the caller called continuable and a position that refused a replay, which is exactly the pair the document divides on.
        handed_over = _hand_over(
            continuation, session, assembler, framing, error=torn
        )
        if handed_over is not None:
            for chunk in handed_over:
                yield chunk
            return
        raise torn

    remaining = session.finish()
    if remaining and not client_has_bytes.is_set():
        # The held-back path needs the same preamble as the incremental one.
        for frame in framing.preamble():
            yield frame
        client_has_bytes.set()
    for block in remaining:
        for frame in framing.block(block):
            yield frame

    terminal = assembler.terminal
    if terminal.seen and terminal.stop_reason in _HANDED_OVER_STOP_REASONS:
        # Upstream finished cleanly and said it stopped because it ran out of room. Nothing failed, so nothing above catches it — but the turn is no more finished than a torn one, and the client is the only side that can carry it on. Ruled 2026-08-21: `max_tokens` always hands over.
        #
        # Asked before the empty-response return below, not after. A turn whose only block was itself the truncated one has nothing left after the drop, and that return would have answered it with a 200 and no bytes at all — which is the one outcome the keep-it-when-it-is-all-there-is rule exists to prevent, arrived at from the other side.
        handed_over = _hand_over(
            continuation, session, assembler, framing, stop_reason=terminal.stop_reason
        )
        if handed_over is not None:
            for chunk in handed_over:
                yield chunk
            return
    if not client_has_bytes.is_set():
        # Nothing was ever committed downstream, so there is no started message to correct — the same case the legacy chain leaves to its caller (`render_error` there runs only `if session.frontier.message_start_accepted`). An upstream that produced no block and no terminal still leaves the client a 200 with an empty body; that is pre-existing behaviour on a path this slice does not touch, and widening it is a separate question from STR-04's flush.
        return
    if not terminal.seen:
        # STR-04: an EOF with no legal terminal event is truncation, not success.
        # Ported from the legacy chain rather than redesigned, as `implementation.md` directs: `app/delivery/responses_anthropic_stream.py`, on `not frontier.terminal_accepted`, raises `incomplete_responses_stream` and renders an SSE error. Same code, same wire shape, same message, same gate on the message having started — a client that already learned to read one of these does not have to learn a second.
        # `message_stop` deliberately does not follow. The frozen Spec rules these two mutually exclusive: 不得再发 `message_stop` 冒充成功.
        yield framing.error(
            error_type=WIRE_TYPES[ErrorCategory.UPSTREAM],
            message="Responses stream ended before a successful terminal event",
            code="incomplete_responses_stream",
        )
        return
    # `or "end_turn"` is still a synthesis, and still visible where it happens — but it now only ever runs on a stream that really did see a terminal event, so it fills in a field upstream left empty rather than inventing an ending upstream never reached. An upstream that sends an explicit empty `stop_reason` gets `end_turn`, because `""` is not a stop reason any Anthropic consumer accepts.
    for frame in framing.terminal(terminal):
        yield frame


# The clean endings that are not endings. Upstream said it stopped for want of room, which leaves the turn exactly as unfinished as a torn one does — the difference is only that nothing raised.
_HANDED_OVER_STOP_REASONS = frozenset({"max_tokens"})


def _hand_over(
    continuation: ContinuationSupport | None,
    session: DeliverySession,
    assembler: BlockAssembler,
    framing: OutboundFramer,
    *,
    error: BaseException | None = None,
    stop_reason: str = "",
) -> list[bytes] | None:
    """Frame the whole ending: whatever is still buffered, the synthesised call, and the close.

    `None` when there is nothing to hand over — no support configured, nothing delivered for the client to carry on from, or a caller that declined. The ending then falls through to whatever it would have been, which is the point: this adds an ending, it does not replace the ones that were there.

    The buffered blocks go out first. They are whole, the client is owed them, and holding them back would make the size of this ending depend on the buffering policy.
    """
    if continuation is None:
        return None
    if session.committed_count == 0 and stop_reason not in _HANDED_OVER_STOP_REASONS:
        # Nothing whole ever reached the client, so there is nothing for it to carry on from and the tool call would be the entire turn. Asked before the caller is, so a hand-over it would have recorded is not recorded for an ending that does not happen. The exception is a turn upstream cut short for want of room, where the truncated block was kept precisely so this would not be empty.
        return None
    payload = continuation.synthesize(error, stop_reason)
    if payload is None:
        return None
    chunks: list[bytes] = []
    # Read before the flush, because the flush is what sets it. Asked afterwards this is always true, so the preamble it guards never went out — and the one ending that reaches here with nothing yet delivered is precisely the one that needs it.
    started = session.started
    remaining = session.finish()
    if not started:
        chunks.extend(framing.preamble())
    for block in remaining:
        chunks.extend(framing.block(block))
    handed = CompletedBlock(index=session.committed_count, kind=TOOL_USE_KIND, payload=payload)
    chunks.extend(framing.block(handed))
    # `tool_use` as the ending, because that is what this turn now is. `synthesize` refuses any client that did not ask in Anthropic Messages, so only that framer is ever reached here.
    chunks.extend(framing.terminal(replace(assembler.terminal, stop_reason=TOOL_USE_KIND)))
    return chunks


def _commit(
    session: DeliverySession,
    block: CompletedBlock,
    framing: OutboundFramer,
    started: bool,
) -> list[bytes]:
    """Offer one block and frame whatever the buffer released."""
    released = session.offer(block)
    if not released:
        return []
    chunks: list[bytes] = []
    if not started:
        # The preamble waits for the first block.
        # A response that never produces one never looks like a message that began.
        chunks.extend(framing.preamble())
    for ready in released:
        chunks.extend(framing.block(ready))
    return chunks
