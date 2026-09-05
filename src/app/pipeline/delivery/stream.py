"""Streaming delivery: read upstream, release each block as it completes.

The client sees a block only once it is whole, and sees no *content* before the first one.
Between blocks, and before the first, the connection is kept alive with SSE comments.
They carry no content, so they cannot be mistaken for a block.
The response itself is already open by then: it is built with upstream's own status once its headers arrive, and the framework sends `http.response.start` before pulling a single chunk. So a comment changes nothing about what the client was told, while withholding one only spends the wait in silence.

The keep-alive here is the **client-facing** one, and its cadence hangs off the last byte written to the client — never off upstream activity. Block-level delivery decouples the two sides: an upstream sending a delta every 200ms still leaves the client without a byte for however long the block takes to close. Keying the cadence on upstream events installed the guard backwards — it fired while upstream was quiet, and stayed silent while upstream was busy, which is the window a client actually gives up in. The upstream-facing keep-alive is a separate mechanism with separate settings and shares no timer with this one; see `.dev/docs/delivery-keepalive/spec.md`.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterable, Iterator
from contextlib import aclosing, suppress
from dataclasses import dataclass, replace
from typing import Any, cast

from app.errors import STATUS_FOR_CATEGORY, ErrorCategory, ErrorInfo
from app.pipeline.delivery.assembling import BlockAssembler, FailureOrigin, StreamFailure
from app.pipeline.delivery.blocks import (
    TOOL_USE,
    BlockBuffer,
    CompletedBlock,
    DeliveryError,
    DeliverySession,
    DeliveryUnit,
)
from app.pipeline.delivery.framing import OutboundFramer
from app.pipeline.delivery.sse_source import SseEvent, encode_frame, read_events
from app.pipeline.retry import RetryLedger, RetryReason, StreamEnding, decide_stream_ending
from app.streaming.deadline import ClientDeadlineError
from app.streaming.keepalive import finish_stream_cleanup, raise_with_cleanup_under

PING_FRAME = b": ping\n\n"

type FailureProvenance = Callable[[Exception], bool]
type _ExceptionGraphFingerprint = frozenset[tuple[str, int, int, int]]


def _exception_graph_fingerprint(error: BaseException) -> _ExceptionGraphFingerprint | None:
    """Capture exception-object identity and graph edges, failing closed on hostile metadata."""
    facts: set[tuple[str, int, int, int]] = set()
    seen: set[int] = set()
    pending: list[BaseException] = [error]
    try:
        while pending:
            current = pending.pop()
            current_id = id(current)
            if current_id in seen:
                continue
            seen.add(current_id)
            facts.add(("node", current_id, 0, 0))
            for kind, linked in (
                ("cause", current.__cause__),
                ("context", current.__context__),
            ):
                if linked is not None:
                    facts.add((kind, current_id, 0, id(linked)))
                    pending.append(linked)
            if isinstance(current, BaseExceptionGroup):
                group = cast(BaseExceptionGroup[BaseException], current)
                for index, nested in enumerate(group.exceptions):
                    facts.add(("member", current_id, index, id(nested)))
                    pending.append(nested)
            for index, note in enumerate(
                getattr(cast(BaseException, current), "__notes__", ())
            ):
                facts.add(("note", current_id, index, id(note)))
    except BaseException:
        return None
    return frozenset(facts)


class UpstreamSource:
    """The upstream side of the byte stream, named by the caller so that what it raises can be told from what this side raises.

    Positive identification, and on the *upstream* side rather than this one. It used to be the other way round: a marker set at each place this side ran code, so that everything unmarked defaulted to upstream's. That list is unbounded by construction — a review made this loop's own SSE reader raise and watched the bug get handed to the client as upstream's — while everything upstream produces passes through one point.

    **Which point that is, is the caller's to say, and it is not the iterator delivery receives.** `inference.py` composes four wrappers over `response.aiter_bytes()` — five objects in the stack once this one is in it — and the line does not fall at either end: the attempt deadline and the idle timeout are guards that exist to state an upstream condition, so they belong below it, while `_counted_upstream` is this side's bookkeeping and belongs above. Constructed here in the middle of that stack rather than around the whole of it, delivery is handed the composite and this object separately, and asks only this object what it raised. A bug in the byte counter is this side's again — measured, `handed_local_counter_bug` is now `False` where it was `True` at `62a457f`.

    A class rather than a generator. A generator could be written safely — `await source.__anext__()` inside the `try`, the `yield` outside it, the same shape `_commit` and the keep-alive use — but the safe and the unsafe spellings look alike, and the unsafe one records a consumer's `athrow` as upstream's. `__anext__` has no window to get wrong. `CancelledError` is not an `Exception` and is not tagged, which is what keeps `finish_stream_cleanup` cancelling the in-flight pull from reading as an upstream tear.
    """

    def __init__(self, source: AsyncIterator[bytes]) -> None:
        self._source = source.__aiter__()
        # The exception this iterator raised, if it has. Compared by identity downstream, so a later attempt's tear cannot be mistaken for this one's.
        self.tear: Exception | None = None
        # Captured where the source first raises, before this proxy's outer iterators run cleanup and can attach independent failures to the same root object.
        self._tear_fingerprint: _ExceptionGraphFingerprint | None = None

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self._source.__anext__()
        except StopAsyncIteration:
            raise
        except Exception as tear:
            self.tear = tear
            self._tear_fingerprint = _exception_graph_fingerprint(tear)
            raise

    def tear_is_unmodified(self, error: Exception) -> bool:
        """Whether no exception fact was attached after this source observed its tear."""
        return bool(
            error is self.tear
            and self._tear_fingerprint is not None
            and _exception_graph_fingerprint(error) == self._tear_fingerprint
        )

    async def aclose(self) -> None:
        """Delegated, because `read_events` closes the byte stream under it and that is what releases the upstream response."""
        closer = getattr(self._source, "aclose", None)
        if closer is not None:
            await closer()


# What one replaced attempt hands over: a fresh byte stream, the marker naming its upstream side, and the fresh assembler and buffer that go with it. Nothing from the attempt it replaces travels with them — including the marker, so a tear recorded by the previous attempt's cannot be mistaken for this one's.
# Declared here rather than beside the other contracts because it names `UpstreamSource`, and a forward reference in a `type` alias leaves the tuple partially unknown to the type checker — which then cannot see the unpack that consumes it.
# `Any` rather than a type parameter, and the invariant it gives up is real: a replacement must carry the same unit as the attempt it replaces. That is guaranteed at construction — `inference.py` builds the replacement from the same `assembler_for`/`delivery_buffer` pair as the first attempt — rather than here, because threading a parameter through `ReplaySupport` and its callback would put it in four signatures to say what one construction site already decides.
Attempt = tuple[AsyncIterator[bytes], UpstreamSource, BlockAssembler[Any], BlockBuffer[Any]]





@dataclass(frozen=True, slots=True)
class ReplaySupport:
    """What delivery needs in order to replace a torn attempt, and nothing more.

    The two halves of the decision are deliberately on opposite sides of this boundary, because they are answers to different questions and only one of them is delivery's to answer. **Whether a replay is legal at all** is a fact about position — has the client seen anything, is there a committed block, is there budget — and delivery is the only thing that knows it. **Whether this particular failure is one another attempt could answer** is a fact about upstream's error taxonomy, which delivery has no business importing: a transport tear may be replaced, a conversion error and a refusal may not, and that vocabulary belongs to the layer that speaks to upstream.

    `eligible` is asked first and costs nothing, so a failure no attempt can answer never spends budget on being told so. It answers with the reason the failure draws on rather than a yes, because the budget it will spend is the ordinary one for that reason — a torn body is a network failure at a later instant, not a kind of its own.
    """

    ledger: RetryLedger
    eligible: Callable[[Exception], RetryReason | None]
    # Given the failure it is replacing. The caller decided this one was replayable and is the only place that can record what it was: a transparent replay that succeeds neither hands over nor re-raises, so without this the exception is gone and the completion line carries an attempt count and nothing else. Being invisible to the *client* is the point of a transparent replay; being invisible to the operator is not.
    reopen: Callable[[Exception], Awaitable[Attempt | None]]


@dataclass(frozen=True, slots=True)
class ContinuationSupport:
    """Hands a turn that cannot be finished back to the client as a tool call it can act on.

    Same division as `ReplaySupport`, for the same reason. Delivery knows *whether* the client is already holding content, which is what decides that this is the only ending left. It does not know what the tool is called, whether this client declared it, or how to name the failure in the vocabulary the tool expects — all of that belongs to the layer that read the client's request.

    Returns the `tool_use` payload rather than a finished block, because the index is delivery's to assign: it is the next one after everything already committed, and nothing outside can know that.

    `None` means do not synthesise — a client whose request cannot carry this, or a failure the caller does not want handed back. The ending then falls through to whatever it would have been.
    """

    synthesize: Callable[[BaseException | None, str], dict[str, Any] | None]
    # Which upstream stop reasons mean the turn can be carried on. Carried here rather than read from a module constant, because it is an operator's setting and delivery is not where settings live. The same set decides whether the block upstream cut short may be dropped — one setting, since dropping content is only defensible when the client is handed a way to get it back.
    stop_reasons: frozenset[str] = frozenset({"max_tokens"})


class UpstreamStreamUnterminated(Exception):
    """Upstream's stream ended without ever sending its terminal event.

    **Constructed, never raised.** This ending arrives as a clean end of iteration, so there is no exception carrying it — and the hand-over needs one. Passing `error=None` instead would take the other branch of `interruption_message`, which reports `stop_reason=<x>`: on this ending upstream named no reason, so the only value available there is a synthesis, and putting it in upstream's mouth is what this project refuses to do everywhere else.

    Deliberately outside two taxonomies. Not a `DeliveryError`, which would mark this side as the one that failed. Not in `normalize_upstream_error`'s either, so `replay_reason` returns `None` and the hand-over labels it `upstream` — the right answer, and by the route `hand_over.py` already documents for a failure the retry taxonomy has no word for. Retryability is not the question here anyway: nothing re-raises this.
    """


@dataclass(frozen=True, slots=True)
class StreamSettings:
    """What the delivery loop itself needs. Framing settings belong to the framer, which owns framer."""

    sse_ping_interval: int = 15
    # What to close a message with when upstream stopped at a block boundary without ever sending its terminal event. Empty puts that ending back to an SSE error. See `client_delivery.unterminated_stream_stop_reason`, which is where the reasoning lives; carried here because it is an operator's setting and delivery is not where settings live.
    unterminated_stop_reason: str = "incomplete"


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
        # `is None` rather than `or`; see `raise_with_cleanup_under`'s neighbour in `keepalive.py` for the falsey-`__bool__` measurement.
        if primary is None:
            primary = cleanup_cancellation
        if primary is not None:
            if cleanup_error is not None:
                raise_with_cleanup_under(primary, cleanup_error)
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


async def one_shot_delivery(
    chunks: AsyncIterator[bytes], *, on_complete: Callable[[], None] | None = None
) -> AsyncGenerator[bytes]:
    """Hand the upstream stream to the client whole, once all of it has arrived.

    For a client leg this proxy has no outbound framer for. Block-level delivery needs two halves — something that knows where a block ends in the upstream's events, and something that writes one in the client's — and Chat Completions has neither: its boundaries live inside `choices[].delta`, which nothing here reads. Ruled 2026-08-22 to buffer rather than to invent them; parsing that shape is its own piece of work.

    The client asked for `stream: true` and gets its own protocol's SSE back, byte for byte, just not incrementally. That is a real loss of liveness and it is the point of the ruling — before this existed those bytes went into the Anthropic assembler, matched none of its event names, produced no block, and left the client holding a 200 with an empty body and no error frame.

    No replay and no keep-alive. Both are answers to questions block delivery raises — which block was already committed, and what to say during the silence between them — and neither has a meaning for a delivery that is a single write.

    When a guard fires — an idle upstream, an expired attempt, an expired client deadline — whatever had arrived by then still goes out, and the failure then propagates. Those bytes are upstream's own and are already valid SSE for this dialect; handing them over says more than silence and invents nothing, which is the whole constraint here. What the client does *not* get is a frame naming the failure: writing one would mean inventing an error shape for a dialect nothing here can frame, and that is the same missing half as the block boundaries. A truncated stream is visible to the client anyway — this dialect ends with `data: [DONE]`, and there will not be one.
    """
    body = bytearray()
    try:
        async for chunk in chunks:
            body += chunk
    except Exception:
        if body:
            yield bytes(body)
        raise
    if body or on_complete is not None:
        if on_complete is not None:
            # Empty is a measured whole body, not an absent one. Offer and yield it too, so its own ASGI send-return—not natural drain before Starlette sends anything—is the one-shot completion frontier.
            on_complete()
        yield bytes(body)


def _stream_error(category: ErrorCategory, message: str, *, code: str) -> ErrorInfo:
    """One mid-stream failure, in this proxy's own terms, for whichever framer is carrying this leg.

    Generic delivery used to spell the type itself, reaching into the Anthropic table — so a Responses leg got a category name from a dialect it does not speak. Now it names the category and the leg spells it.

    `status_code` is filled from the category's own row and is **not** what the client is told: the response status was fixed when the headers went out, long before this failure existed. It is here because `ErrorInfo` is one record for both surfaces, and leaving the field at a lie would be worse than filling it with the number this category would have carried had the failure happened earlier. What actually distinguishes these on the wire is `code` — see `.dev/docs/error-envelope/spec.md` §6.4.
    """
    return ErrorInfo(
        category=category,
        message=message,
        status_code=STATUS_FOR_CATEGORY[category],
        code=code,
    )


def _report_failure(
    failure: StreamFailure, *, framer: OutboundFramer[Any], passthrough: bool
) -> bytes:
    """The failure, in whichever terms this client can read.

    On a direct leg the client speaks upstream's dialect, so upstream's event name and payload go back out **as they arrived** — including the fields nothing here recognises, which is the whole of "even if we do not know it, it can still be passed on". Only the SSE wrapper is rebuilt, because frame boundaries are this side's to draw. `raw_data` rather than a re-serialised dict for the same reason: a round trip through a JSON encoder keeps the fields and not the bytes.

    On a translated leg it cannot: the client does not speak that dialect. The failure crosses the same record everything else does and the client's framer spells it.

    **`origin` comes first, and it is not the same question as `passthrough`.** That one asks whether the client could read upstream's words; this one asks whether there are any. A refusal this proxy formed — an output item it cannot carry — has no upstream event behind it, so on a direct leg the passthrough branch would emit this side's `info` under upstream's event name, or an empty `data:` line. Both are inventions. It goes through the framer on either leg.
    """
    if passthrough and failure.origin is FailureOrigin.UPSTREAM_EVENT:
        return encode_frame(failure.event, failure.raw_data)
    return framer.error(failure.info)


def _observe_without_affecting_delivery(
    callback: Callable[[SseEvent], None] | None,
    event: SseEvent,
) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception:
        # This is the last boundary before an observer bug would enter the delivery tear handler below. Reporting is itself no-throw: a broken logging handler is another observability failure, not a delivery failure.
        # No third independent reporting channel remains once the fallback logger fails.
        with suppress(Exception):
            logging.getLogger("app.response_observation").exception(
                "response observation callback failed"
            )


async def stream_delivery[UnitT: DeliveryUnit](
    chunks: AsyncIterator[bytes],
    assembler: BlockAssembler[UnitT],
    *,
    upstream: UpstreamSource,
    buffer: BlockBuffer[UnitT],
    settings: StreamSettings,
    framer: OutboundFramer[UnitT],
    replay: ReplaySupport | None = None,
    continuation: ContinuationSupport | None = None,
    on_tear_after_terminal: Callable[[Exception], None] | None = None,
    on_runtime_failure: Callable[[Exception, bool, FailureProvenance | None], None] | None = None,
    observe_event: Callable[[SseEvent], None] | None = None,
    passthrough: bool = False,
) -> AsyncGenerator[bytes]:
    """Turn an upstream byte stream into the client's SSE, one complete block at a time.

    `passthrough` says the client and upstream speak the same dialect, which is the caller's fact to supply: this loop cannot derive it. The same `ResponsesAssembler` serves a Responses client directly and a Responses upstream being translated to Anthropic, and the framer is the *client's* either way, so neither object knows. It changes exactly one thing — what happens when upstream reports a failure mid-stream, `.dev/docs/error-envelope/spec.md` §3.4.

    `framer` decides which protocol that is, and it is required. It briefly defaulted to Anthropic, built here from a `message_id`, a `model` and a setting — which meant this supposedly format-agnostic loop named one of the two formats and every caller that forgot got it. A caller has to say which client leg it is answering; `framer_for` is what answers that, selecting on the *inbound* format rather than on which upstream replied.

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
            upstream=upstream,
            buffer=buffer,
            settings=settings,
            framer=framer,
            last_write=last_write,
            replay=replay,
            continuation=continuation,
            on_tear_after_terminal=on_tear_after_terminal,
            on_runtime_failure=on_runtime_failure,
            observe_event=observe_event,
            passthrough=passthrough,
        )
    ) as inner:
        async for chunk in inner:
            yield chunk
            last_write.at = loop.time()


async def _deliver[UnitT: DeliveryUnit](
    chunks: AsyncIterator[bytes],
    assembler: BlockAssembler[UnitT],
    *,
    upstream: UpstreamSource,
    buffer: BlockBuffer[UnitT],
    settings: StreamSettings,
    framer: OutboundFramer[UnitT],
    last_write: _LastWrite,
    replay: ReplaySupport | None = None,
    continuation: ContinuationSupport | None = None,
    on_tear_after_terminal: Callable[[Exception], None] | None = None,
    on_runtime_failure: Callable[[Exception, bool, FailureProvenance | None], None] | None = None,
    observe_event: Callable[[SseEvent], None] | None = None,
    passthrough: bool = False,
) -> AsyncGenerator[bytes]:
    """Assemble and frame the response. Wrapped by `stream_delivery`, which stamps the clock."""
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
                    # The composite the caller built, not the marker inside it: this loop has to read every layer, including the ones above the marker. The marker is asked one question and never iterated.
                    chunks,
                    settings.sse_ping_interval,
                    last_write=last_write,
                )
            ) as events:
                async for pull in events:
                    wrote = False
                    if pull.event is not None:
                        # Observation is side-only and attempt-scoped. The callback resolves the current attempt on every event, so a replay cannot keep writing into the record it replaced. Its public observer contract contains ordinary parsing failures; delivery never reads the observation back.
                        _observe_without_affecting_delivery(observe_event, pull.event)
                        # Assembled before any cue is answered. A pull that came back with an event has not shown that the event can be delivered: a malformed one makes the assembler raise right here, and that has to reach the caller ahead of a comment claiming everything is fine.
                        completed = assembler.push(pull.event)
                        # The cap has to see what the assembler is holding too. On a passthrough leg an item that opens and never closes keeps every later group queued outside the buffer, and `direct-passthrough/spec.md` §8 names that queue as the first thing `buffer_cap_bytes` must bound — uncounted, the default 16MiB bounded nothing there.
                        buffer.enforce_cap_over(assembler.queued_bytes)
                        for admission_batch in _admission_batches(completed):
                            for chunk in _commit(
                                session,
                                admission_batch,
                                framer,
                                client_has_bytes.is_set(),
                            ):
                                client_has_bytes.set()
                                wrote = True
                                yield chunk
                        failure = assembler.failure
                        if failure is not None:
                            # Upstream said this turn failed. Until 2026-08-24 both assemblers logged it and returned nothing, so the loop ran on to a terminal-less ending — which, since the clean-EOF change of 2026-08-22, *looks like success*: a `message_delta` carrying a stop reason and then `message_stop`. Upstream said it failed and the client could not tell.
                            #
                            # Blocks completed by this same event go out first, above: they arrived, and dropping them would make what a client received depend on when the failure landed.
                            yield _report_failure(failure, framer=framer, passthrough=passthrough)
                            # No terminal, and that is the point rather than an omission. `.dev/docs/error-envelope/spec.md` §3.5: a turn upstream reported as failed must not end with an event that reads as a completed one.
                            return
                    # Asked here, and only here, because this is the first moment both answers exist: whether assembling wrote anything, and what the clock reads now that it has. Real bytes discharge the same obligation a cue would have answered, so `wrote` short-circuits and the schedule is left alone.
                    if wrote or not pull.claim():
                        continue
                    # Unconditional, because by the time this generator runs the client already holds a 200: the response is built with upstream's own status once its headers have arrived, and the framework sends `http.response.start` before it pulls the first chunk. Nothing here can change what the client was told, so holding the keep-alive back until a block exists buys nothing and spends the whole pre-first-block window in silence — which under `full` and `until-tool-use` is the entire turn.
                    #
                    # An SSE comment before `message_start` is still legal SSE and carries no content, so it cannot be mistaken for part of the turn. What is *not* sent early is the preamble itself: a `message_start` on its own leaves a message opened with nothing in it, and every decision after a torn stream then has to carry a case for that state.
                    yield framer.keepalive()
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
            #
            # Ahead of `terminal.seen` on purpose, and that ordering is a ruling rather than an accident of writing order: `client_request_deadline` bounds this round's total elapsed time, so once it fires the round is over whether or not upstream happened to finish first. A complete reply may be sitting assembled in the buffer, and it is dropped. Ruled 2026-08-22.
            #
            # The attempt deadline (`upstream_request_deadline`, raised by `pipeline_app`'s `with_deadline_at`) has no branch of its own here — it arrives as an ordinary tear and is classified below. It is ordered the other way round, *after* `terminal.seen`, for the opposite reason: it ends only this attempt, so a turn upstream finished must not be handed to it as something to retry.
            if on_runtime_failure is not None:
                on_runtime_failure(torn, False, None)
            yield framer.error(
                _stream_error(
                    ErrorCategory.INTERNAL,
                    str(torn) or "client request exceeded its deadline",
                    code="client_deadline_exceeded",
                )
            )
            raise torn
        if assembler.terminal.seen:
            # Upstream finished this turn and *then* the connection went. Nothing is missing, so the ending below is the real one.
            #
            # Answered here rather than from the verdict, which is where it used to be — and that was one door short. A failure the caller's taxonomy does not recognise, a bare `h2.ProtocolError` among them, never reaches the verdict at all: it is refused two lines down and raised, taking a complete reply with it. The question "did upstream finish" has to be answered before any question about the failure, because the answer does not depend on the failure.
            #
            # Still below the client deadline, and that is now a ruling rather than a deferral: see the branch above. Above the attempt deadline, though, which reaches here as an ordinary tear rather than a branch of its own — that one ends only this attempt, so a finished turn must not be handed to it as something to retry.
            #
            # Reported before breaking, because this was the one ending that discarded its exception without a word. The reply is whole and the client is owed nothing more, so nothing downstream ever sees `torn`: the loop leaves normally, the terminal frames go out, and the request is accounted a clean success. A review found this branch while refuting a claim that the hand-over was the only ending that swallowed its cause — it was the second one, and unlike the hand-over it had no field to be read from either.
            #
            # A callback rather than a field on this generator, for the same reason `ReplaySupport` and `ContinuationSupport` are callbacks: what to *do* with the fact belongs to the caller that owns the request's account, and delivery does not know there is one.
            if on_tear_after_terminal is not None:
                on_tear_after_terminal(torn)
            break
        # Whether this failure is one this side inflicted rather than suffered — the word the client reads depends on it, and so does whether the turn is handed back at all.
        #
        # **Upstream is what is positively identified**, and it is the only half that can be bounded. Everything upstream produces arrives through `_UpstreamSource`, while the other half — everything this side runs — has no finite list: assembling, committing, framing, the keep-alive, the SSE reader, the pull scheduler, and whatever is added next. Marking that side is what this used to do, and it was incomplete twice over: framing was left out with a stated reason that did not hold, and after that was fixed an independent review made the SSE reader raise and watched the bug reach the client as upstream's.
        #
        # The converse holds as far as the marker reaches, and where the caller puts it is what decides that. `inference.py` constructs it with the two guards that speak for upstream below it and this side's byte counter above, so a bug in `_counted_upstream` is `ours` — it was not, and `deferred.md` §22之六 is the entry that closed when it stopped being true. What is left below the marker and outside this repository is httpcore's own bookkeeping, which is §22之七 and is a different question.
        #
        # `DeliveryError` and its siblings are ours by type rather than by origin: they are the proxy's own protections firing, which `upstream-retry-and-continuation.md` lists under "无法继续". Another attempt would hit the same cap, and handing the turn back would invite the client to re-run something this side has already refused to hold. They are named here because a protection that fires while reading upstream would otherwise be tagged as upstream's tear.
        #
        # The direction matters for what a mistake costs. Getting it wrong towards upstream tells a client the peer failed when this side did — the reading that used to reach a client as `internal_error` for an ordinary torn socket, and that this predicate is written to make unreachable.
        ours = isinstance(torn, DeliveryError) or torn is not upstream.tear
        reason = None if ours else (replay.eligible(torn) if replay is not None else None)
        if replay is not None and reason is not None:
            verdict = decide_stream_ending(
                terminal_seen=assembler.terminal.seen,
                downstream_opened=client_has_bytes.is_set(),
                committed_blocks=session.committed_count,
                ledger=replay.ledger,
                reason=reason,
            )
            if verdict.ending is StreamEnding.COMPLETE:
                # Unreachable from here now that the same question is answered above, and kept because this is a switch over everything the verdict can say — a branch that silently fell through to the hand-over is what turned a finished turn into a synthesised interruption in the first place.
                break
            if verdict.ending is StreamEnding.REPLAY:
                replacement = await replay.reopen(torn)
                if replacement is not None:
                    # Everything the failed attempt built is dropped, not carried: a fresh assembler so no draft of its survives, and a fresh buffer so a block it completed but never delivered cannot be delivered twice. `session` goes with the buffer. Legal only because the verdict required nothing to have been committed — there is no frontier here to preserve, and none to roll back.
                    chunks, upstream, assembler, buffer = replacement
                    session = DeliverySession(buffer=buffer)
                    continue
        if not ours:
            # Asked whether or not the failure could be *named*, which is the half that used to be missing: `reason is None` sent the stream straight out of this function on a bare `raise`, so a failure the caller's taxonomy has no word for — a naked `h2.ProtocolError` is the one on record — skipped the hand-over entirely and took the client's turn with it. Naming a failure decides whether another *attempt* is worth funding; it says nothing about whether the client can carry the turn on, and only the second question belongs here.
            #
            # An unnamed failure is still not replayed. That is the narrower of the two readings and it is deliberate: a replay spends budget on a guess, while a hand-over spends nothing and leaves the decision with the client. Whether unnamed should also mean retryable is a product question, and it stays in `deferred.md` §20 rather than being answered by this edit.
            handed_over = _hand_over(continuation, session, assembler, framer, error=torn)
            if handed_over is not None:
                for chunk in handed_over:
                    yield chunk
                return
        # Every remaining ending gets a frame *and* still reaches the caller. Until 2026-08-22 it was a bare `raise`, which the client received as a 200 whose body simply stopped — byte-for-byte the same as an idle timeout, a deadline, or the proxy abandoning the response, with only the server's own log able to tell them apart (`deferred.md` 8d). The response has been open since before the first chunk, so a frame is the only channel left.
        #
        # The `raise` stays to carry the exact exception into request accounting; swapping it for the frame was tried first and logged the request `ok`, with no durable failure fact. `_tracked_delivery` may consume that same upstream exception only after the yielded frame's ASGI send returns. Local failures, a frame whose send did not return, and distinct cleanup failures continue outward. Yield first and raise second is what makes those two boundaries independently observable.
        #
        # Nothing is flushed first, for the same reason the client deadline flushes nothing: what is buffered but undelivered would make the size of this ending depend on the buffering policy, while the ending itself is a failure.
        #
        # Three codes, one per way this can end, so that a reader of a client transcript can tell them apart without the server's log beside them.
        if on_runtime_failure is not None:
            # Record the authoritative origin before yielding the error frame: its downstream send is a separate, lower-priority frontier that may fail and prevent this generator from ever resuming. The bound provenance check reaches back to the current attempt's positive marker and is re-run only if the frame's send returns.
            on_runtime_failure(
                torn,
                not ours,
                upstream.tear_is_unmodified if not ours else None,
            )
        yield framer.error(
            _stream_error(
                ErrorCategory.INTERNAL if ours else ErrorCategory.UPSTREAM,
                # Upstream's own words, or this side's. Either way the distinguishing detail lives here rather than nowhere.
                str(torn) or torn.__class__.__name__,
                code=(
                    "proxy_delivery_aborted"
                    if isinstance(torn, DeliveryError)
                    else "proxy_delivery_failed"
                    if ours
                    else "upstream_stream_failed"
                ),
            )
        )
        raise torn

    # `direct-passthrough/spec.md` §7.2's closing sequence, asked of the assembler before the buffer is drained so that whatever it releases still passes through the policy. The translating assemblers answer with nothing — what they hold is a half-built block, which every ending drops. The passthrough answers with the finished groups its queue was holding behind an item that never closed, and those were previously abandoned along with upstream's own terminal: one unclosed item produced a 200 with zero bytes.
    for admission_batch in _admission_batches(assembler.close()):
        for chunk in _commit(session, admission_batch, framer, client_has_bytes.is_set()):
            client_has_bytes.set()
            yield chunk

    remaining = session.finish()
    if remaining and not client_has_bytes.is_set():
        # The held-back path needs the same preamble as the incremental one.
        for frame in framer.preamble():
            yield frame
        client_has_bytes.set()
    for block in remaining:
        for frame in framer.block(block):
            yield frame

    terminal = assembler.terminal
    if continuation is not None and terminal.seen and terminal.stop_reason in continuation.stop_reasons:
        # Upstream finished cleanly and said it stopped because it ran out of room. Nothing failed, so nothing above catches it — but the turn is no more finished than a torn one, and the client is the only side that can carry it on. Ruled 2026-08-21: `max_tokens` always hands over.
        #
        # Asked before the empty-response return below, not after. A turn whose only block was itself the truncated one has nothing left after the drop, and that return would have answered it with a 200 and no bytes at all — which is the one outcome the keep-it-when-it-is-all-there-is rule exists to prevent, arrived at from the other side.
        handed_over = _hand_over(
            continuation, session, assembler, framer, stop_reason=terminal.stop_reason
        )
        if handed_over is not None:
            for chunk in handed_over:
                yield chunk
            return
    if not client_has_bytes.is_set():
        # Nothing was ever committed downstream, so there is no started message to correct — the same case the legacy chain leaves to its caller (`render_error` there runs only `if session.frontier.message_start_accepted`). An upstream that produced no block and no terminal still leaves the client a 200 with an empty body; that is pre-existing behaviour on a path this slice does not touch, and widening it is a separate question from STR-04's flush.
        return
    if not terminal.seen:
        if (
            not assembler.cut_mid_block
            and settings.unterminated_stop_reason
            and framer.synthesises_terminal
        ):
            # Upstream closed cleanly *between* blocks. Every block it produced is whole and already delivered, so nothing the client holds is damaged — the only thing missing is upstream's own word for why it stopped, and an error frame answers that by calling a reply truncated when nothing was cut. Ruled 2026-08-22.
            #
            # The reason on the wire is a synthesis and stays configurable so that it is chosen rather than inherited: `client_delivery.unterminated_stream_stop_reason` carries it, defaults to upstream's own `incomplete`, and going empty puts this ending back to the error below. What it must not silently become is `end_turn` — that is what `framer.terminal` fills an empty reason with, and it would claim a turn upstream never claimed.
            #
            # `cut_mid_block` rather than "did the client get whole blocks": the latter is always true under block-level delivery and so discriminates nothing.
            # Upstream's own word wins when it gave one. An Anthropic leg splits its ending — `message_delta` carries the reason, `message_stop` merely closes — so a stream that lost only the second still told us why it stopped, and overwriting that with the configured synthesis replaced an observation with an invention. The caller already ruled this way for the completion line (`inference.py`, on `terminal.stop_reason` being set), and this used to disagree with it: the log said `max_tokens` while the client was told `incomplete`.
            for frame in framer.terminal(
                replace(terminal, stop_reason=terminal.stop_reason or settings.unterminated_stop_reason)
            ):
                yield frame
            return
        # An EOF that cut through a block, or the refinement switched off. Either way this reports an error, and an error with content already in the client's hands is what the hand-over exists for.
        #
        # Asked here on exactly the same terms as the torn path above, which is the whole point: the two endings leave the client in the same place, and `retry.py` already states that it is that place — not the manner of arrival — that decides what may legally happen next. Until this branch existed, being killed by this side's own idle guard produced a *better* client outcome than upstream closing cleanly, because the guard raises and a clean EOF does not. Authority is `docs/.human-controlled/upstream-retry-and-continuation.md` line 30, which gates on 已经交付过至少一个完整块 and then prescribes 将报错合成为自制的 `tool_use` 返回给客户端; a terminal-less stream appears on neither of that document's 无法继续 lists. Spec item 7, amended 2026-08-24. Production incident req=75ccdf6f.
        #
        # **Not** asked before the block-boundary close above. That ending reports no error, so line 30's 将报错合成为 never reaches it, and the 2026-08-22 ruling that made it a clean close stands untouched.
        #
        # `_hand_over` re-asks `session.finish()`, which already ran above; it returns nothing the second time, and the call is kept rather than special-cased because the torn path reaches the same function having flushed nothing.
        #
        # Its `committed_count == 0` gate — the same one line 30 states — cannot fire from here, and the first draft of this comment claimed it could. Reaching this line means `client_has_bytes` is set, and the only thing that sets it is a block going out; a turn that committed nothing returned a dozen lines above, with an empty body and no frame of any kind. That ending is pre-existing and this change does not touch it. Measured by an independent review, 2026-08-24.
        handed_over = _hand_over(
            continuation,
            session,
            assembler,
            framer,
            error=UpstreamStreamUnterminated("upstream stream ended without a terminal event"),
        )
        if handed_over is not None:
            for chunk in handed_over:
                yield chunk
            return
        # Ported from the legacy chain rather than redesigned, as `.dev/docs/anthropic-responses-bridge/implementation.md` directs: `app/delivery/responses_anthropic_stream.py`, on `not frontier.terminal_accepted`, raises `incomplete_responses_stream` and renders an SSE error. Same code, same wire shape, same gate on the message having started — a client that already learned to read one of these does not have to learn a second.
        # `message_stop` deliberately does not follow. `.dev/docs/anthropic-responses-bridge/spec.md`, "Downstream Anthropic SSE" item 7, rules these two mutually exclusive: 不得再发 `message_stop` 冒充成功. Note that item 7 constrains what may follow an *error*; it does not make every terminal-less EOF one, which is what the branch above turns on.
        yield framer.error(
            _stream_error(
                ErrorCategory.UPSTREAM,
                # Names no upstream dialect. This function serves both legs — `framer` is the caller's — so the old wording claimed the reply came from Responses even on an Anthropic-direct turn, which is the leg the 2026-08-22 production incident was on. `deferred.md` §19.
                "upstream stream ended before a terminal event",
                code="incomplete_responses_stream",
            )
        )
        return
    # `or "end_turn"` is still a synthesis, and still visible where it happens — but it now only ever runs on a stream that really did see a terminal event, so it fills in a field upstream left empty rather than inventing an ending upstream never reached. An upstream that sends an explicit empty `stop_reason` gets `end_turn`, because `""` is not a stop reason any Anthropic consumer accepts.
    for frame in framer.terminal(terminal):
        yield frame


def _hand_over(
    continuation: ContinuationSupport | None,
    session: DeliverySession[Any],
    assembler: BlockAssembler[Any],
    framer: OutboundFramer[Any],
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
    if session.committed_count == 0 and stop_reason not in continuation.stop_reasons:
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
        chunks.extend(framer.preamble())
    for block in remaining:
        chunks.extend(framer.block(block))
    handed = CompletedBlock(index=session.committed_count, kind=TOOL_USE, payload=payload)
    chunks.extend(framer.block(handed))
    # `tool_use` as the ending, because that is what this turn now is. `synthesize` refuses any client that did not ask in Anthropic Messages, so only that framer is ever reached here.
    chunks.extend(framer.terminal(replace(assembler.terminal, stop_reason=TOOL_USE)))
    return chunks


def _admission_batches[UnitT: DeliveryUnit](
    units: Iterable[UnitT],
) -> Iterator[tuple[UnitT, ...]]:
    """Preserve ordinary per-unit admission while joining explicitly marked neighbours."""
    grouped: list[UnitT] = []
    group = ""
    for unit in units:
        unit_group = unit.admission_group if isinstance(unit, CompletedBlock) else ""
        if not unit_group:
            if grouped:
                yield tuple(grouped)
                grouped = []
                group = ""
            yield (unit,)
            continue
        if grouped and unit_group != group:
            yield tuple(grouped)
            grouped = []
        grouped.append(unit)
        group = unit_group
    if grouped:
        yield tuple(grouped)


def _commit[UnitT: DeliveryUnit](
    session: DeliverySession[UnitT],
    batch: Iterable[UnitT],
    framer: OutboundFramer[UnitT],
    started: bool,
) -> Iterator[bytes]:
    """Offer one admission batch and lazily frame each unit the buffer released.

    Admission and the policy decision cover the whole batch. Framing stays lazy to preserve the unit-to-chunk boundary: framing everything before the first yield lets side records produced while framing a later unit describe an earlier chunk whose send returns first.
    """
    released = session.offer_many(batch)
    if not released:
        return
    if not started:
        # The preamble waits for the first block.
        # A response that never produces one never looks like a message that began.
        yield from framer.preamble()
    for ready in released:
        yield from framer.block(ready)
