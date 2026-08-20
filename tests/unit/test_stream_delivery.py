"""Streaming delivery over a real upstream byte stream.

The invariant under test is what the client sees and when.
Nothing before the first whole block, each block as a closed group, keep-alives with no content.
"""

import asyncio
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, suppress
from types import SimpleNamespace
from typing import Any, cast

import orjson
import pytest

from app.config.schema import ContentBlockStartCompat
from app.observability.active_requests import ActiveRequestRegistry
from app.pipeline.delivery.assembler import AnthropicAssembler, ResponsesAssembler, Terminal
from app.pipeline.delivery.blocks import BlockBuffer, CompletedBlock
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.delivery.stream import (
    PING_FRAME,
    StreamSettings,
    _events_with_ping,  # pyright: ignore[reportPrivateUsage]
    _LastWrite,  # pyright: ignore[reportPrivateUsage]
    stream_delivery,
)
from app.server.pipeline_app import (
    _counted_upstream,  # pyright: ignore[reportPrivateUsage]
    _Trace,  # pyright: ignore[reportPrivateUsage]
)
from app.streaming.deadline import StreamDeadlineError, with_deadline_at
from app.streaming.idle_timeout import StreamIdleTimeoutError, with_idle_timeout


def frame(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n".encode()


def anthropic_stream(*texts: str) -> list[bytes]:
    chunks: list[bytes] = []
    for index, text in enumerate(texts):
        chunks.append(
            frame("content_block_start", {"index": index, "content_block": {"type": "text"}})
        )
        chunks.append(
            frame(
                "content_block_delta",
                {"index": index, "delta": {"type": "text_delta", "text": text}},
            )
        )
        chunks.append(frame("content_block_stop", {"index": index}))
    chunks.append(frame("message_delta", {"delta": {"stop_reason": "end_turn"}}))
    chunks.append(frame("message_stop", {}))
    return chunks


async def feed(payloads: list[bytes], *, gap: float = 0.0) -> AsyncIterator[bytes]:
    for payload in payloads:
        if gap:
            await asyncio.sleep(gap)
        yield payload


async def collect(
    payloads: list[bytes],
    *,
    policy: str = "block",
    interval: int = 0,
    gap: float = 0.0,
    initial_delay: float = 0.0,
    synthesized_response_headers_after_sec: int = 0,
    signature_compat: ContentBlockStartCompat = "signature_delta",
    assembler: str = "anthropic",
) -> list[bytes]:
    async def delayed_feed() -> AsyncIterator[bytes]:
        if initial_delay:
            await asyncio.sleep(initial_delay)
        async for payload in feed(payloads, gap=gap):
            yield payload

    return [
        chunk
        async for chunk in stream_delivery(
            delayed_feed(),
            ResponsesAssembler() if assembler == "responses" else AnthropicAssembler(),
            buffer=BlockBuffer(policy=policy),  # pyright: ignore[reportArgumentType]
            settings=StreamSettings(
                sse_ping_interval=interval,
                synthesized_response_headers_after_sec=synthesized_response_headers_after_sec,
                signature_compat=signature_compat,
            ),
            message_id="msg_1",
            model="claude-model",
        )
    ]


def events_of(chunks: list[bytes]) -> list[str]:
    return [
        line.removeprefix("event: ")
        for chunk in chunks
        for line in chunk.decode().splitlines()
        if line.startswith("event: ")
    ]


def block_start_indices(chunks: list[bytes]) -> list[int]:
    return [
        int(orjson.loads(chunk.partition(b"data: ")[2])["index"])
        for chunk in chunks
        if chunk.startswith(b"event: content_block_start\n")
    ]


@pytest.mark.asyncio
async def test_a_block_reaches_the_client_as_soon_as_it_closes() -> None:
    chunks = await collect(anthropic_stream("one", "two"))
    assert events_of(chunks) == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


@pytest.mark.asyncio
async def test_nothing_is_written_before_the_first_block_closes() -> None:
    # Only the opening events of a block, with no stop: the client must receive nothing.
    partial = [
        frame("content_block_start", {"index": 0, "content_block": {"type": "text"}}),
        frame("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "hi"}}),
    ]
    assert await collect(partial) == []


@pytest.mark.asyncio
async def test_a_late_first_block_gets_a_message_start_and_no_placeholder_content() -> None:
    """The client hears that a message began; it is not handed a block that says nothing.

    This used to synthesise `{"type":"text","text":""}` as content block zero. The client stores it as part of the turn and replays it in its next request, and upstream refuses the whole body over it — `messages: text content blocks must be non-empty`, measured in production on 2026-08-20 after a 242-second wait. `message_start` puts the same bytes in front of the client and commits us to no content, so the real block still arrives as index zero.
    """
    chunks = await collect(
        anthropic_stream("one"),
        initial_delay=1.1,
        synthesized_response_headers_after_sec=1,
    )
    assert events_of(chunks) == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    assert b'"text":"one"' in b"".join(chunks)
    assert block_start_indices(chunks) == [0]


@pytest.mark.asyncio
async def test_a_synthesized_start_that_never_gets_a_block_ends_in_an_error() -> None:
    """The degenerate line: the deadline fires and upstream then produces nothing at all.

    Pinned because it is the one shape this change alters that has no other witness. The client is left a message with no content blocks, where before it was left one that said nothing. With the deadline disabled the same silence produces no bytes at all, which is what makes "no content blocks" an existing shape rather than one introduced here.

    The stream still closes rather than hanging — that was always this test's point, and an `error` event closes it just as a terminal does. What changed is which ending: upstream never sent a terminal event, so under STR-04 this is truncation, and the synthesized `message_start` must not be followed by frames claiming the turn finished. The earlier expectation here (`message_delta` + `message_stop`) encoded that claim.
    """
    chunks = await collect([], initial_delay=1.1, synthesized_response_headers_after_sec=1)

    assert events_of(chunks) == ["message_start", "error"]
    assert b"incomplete_responses_stream" in b"".join(chunks)

    assert await collect([], initial_delay=1.1) == []


@pytest.mark.asyncio
async def test_real_block_before_synthesis_deadline_has_no_synthetic_block() -> None:
    chunks = await collect(
        anthropic_stream("one"),
        synthesized_response_headers_after_sec=1,
    )
    assert events_of(chunks).count("content_block_stop") == 1
    assert b'"text":"one"' in b"".join(chunks)
    assert block_start_indices(chunks) == [0]


@pytest.mark.asyncio
@pytest.mark.parametrize("after_sec", [0, -1])
async def test_nonpositive_synthesis_timeout_is_disabled(after_sec: int) -> None:
    chunks = await collect(
        anthropic_stream("one"),
        initial_delay=1.1,
        synthesized_response_headers_after_sec=after_sec,
    )
    assert events_of(chunks).count("content_block_stop") == 1
    assert b'"text":"one"' in b"".join(chunks)
    assert block_start_indices(chunks) == [0]


@pytest.mark.asyncio
async def test_full_policy_still_delivers_everything_at_the_end() -> None:
    chunks = await collect(anthropic_stream("one", "two"), policy="full")
    names = events_of(chunks)
    assert names[0] == "message_start"
    assert names.count("content_block_stop") == 2
    assert names[-1] == "message_stop"


@pytest.mark.asyncio
async def test_a_keep_alive_carries_no_content() -> None:
    chunks = await collect(anthropic_stream("one"), interval=1, gap=0.0)
    assert all(chunk != PING_FRAME or chunk.startswith(b":") for chunk in chunks)


async def run_with_gap(payloads_before: int, gap: float) -> list[bytes]:
    """Feed the stream with a pause after the given number of frames."""
    payloads = anthropic_stream("one")

    async def trickle() -> AsyncIterator[bytes]:
        for payload in payloads[:payloads_before]:
            yield payload
        await asyncio.sleep(gap)
        for payload in payloads[payloads_before:]:
            yield payload

    return [
        chunk
        async for chunk in stream_delivery(
            trickle(),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=1),
            message_id="m",
            model="model",
        )
    ]


@pytest.mark.asyncio
async def test_silence_after_a_block_produces_a_keep_alive() -> None:
    # Three frames is one whole block, so the response has started.
    chunks = await run_with_gap(3, 1.2)
    assert PING_FRAME in chunks
    # The ping is an SSE comment, so it cannot be read as content.
    assert PING_FRAME.startswith(b":")


@pytest.mark.asyncio
async def test_silence_before_the_first_block_produces_no_keep_alive() -> None:
    # Nothing may reach the client before the first whole block, a ping included: a comment
    # arriving first still opens the response.
    chunks = await run_with_gap(1, 1.2)
    assert PING_FRAME not in chunks
    assert events_of(chunks)[0] == "message_start"


def test_a_keep_alive_wait_leaves_no_asyncio_noise() -> None:
    """A keep-alive means the upstream pull outlived its wait, and it has to survive that quietly.

    End-of-stream reaches the pull as StopAsyncIteration, and a stale observer turns that ordinary ending into `StopAsyncIteration exception in shielded future` on the operator's stderr.

    Synchronous, with a loop of its own. A loop-wide exception handler sees whatever that loop reports, and asyncio reports an unretrieved exception when the object is collected — which can be long after whichever test created it. Installed on the shared loop, this assertion failed for things other tests left behind, on the orderings that happened to collect them here. A private loop can only report what this test put on it.
    """
    reported: list[str] = []

    async def run() -> None:
        asyncio.get_running_loop().set_exception_handler(
            lambda _loop, context: reported.append(str(context.get("message")))
        )
        assert await collect([], interval=1, initial_delay=1.2) == []
        await asyncio.sleep(0)

    asyncio.run(run())

    assert reported == []


@pytest.mark.asyncio
async def test_an_empty_upstream_stream_produces_nothing() -> None:
    assert await collect([]) == []


@pytest.mark.asyncio
async def test_responses_upstream_is_delivered_as_anthropic_blocks() -> None:
    payloads = [
        frame("response.output_item.added", {"item": {"id": "i1", "type": "message"}}),
        frame("response.output_text.delta", {"item_id": "i1", "delta": "hello"}),
        frame("response.output_item.done", {"item": {"id": "i1", "type": "message"}}),
        frame("response.completed", {"response": {}}),
    ]
    chunks = [
        chunk
        async for chunk in stream_delivery(
            feed(payloads),
            ResponsesAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            message_id="m",
            model="gpt-model",
        )
    ]
    body = b"".join(chunks).decode()
    assert "content_block_start" in body
    assert '"text":"hello"' in body.replace(" ", "")


@pytest.mark.asyncio
async def test_the_terminal_reports_what_upstream_said() -> None:
    payloads = anthropic_stream("one")
    payloads[-2] = frame("message_delta", {"delta": {"stop_reason": "max_tokens"}})
    chunks = await collect(payloads)
    body = b"".join(chunks).decode()
    assert '"stop_reason":"max_tokens"' in body.replace(" ", "")


async def _truncated_delivery(assembler: AnthropicAssembler) -> str:
    """Deliver a stream that stops after its blocks and before upstream says how it ended."""
    delivered: list[bytes] = []
    async with aclosing(
        stream_delivery(
            # Everything upstream sent before it stopped: the blocks, and neither `message_delta` nor `message_stop`.
            feed(anthropic_stream("one")[:-2]),
            assembler,
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            message_id="msg_1",
            model="claude-model",
        )
    ) as stream:
        async for chunk in stream:
            delivered.append(chunk)
    return b"".join(delivered).decode().replace(" ", "")


@pytest.mark.asyncio
async def test_delivering_a_truncated_stream_does_not_make_its_record_look_finished() -> None:
    """The durable half, and the one that outlives the gap below.

    `seen` and the stop reason are what tells the operator's console line — and, when it arrives, the STR-04 implementation — apart from a turn that genuinely ended. Running the delivery loop over the events must not set either: only upstream's own terminal event may.

    Kept in its own function on purpose. The test below pins behaviour that a later slice is meant to *reverse*, so it will be rewritten or deleted then; these assertions must stay true either way, and sharing a function with it would have taken them along.
    """
    assembler = AnthropicAssembler()
    await _truncated_delivery(assembler)

    assert assembler.terminal.seen is False, "upstream never sent a terminal event"
    assert assembler.terminal.stop_reason == "", "and so it never gave a reason"


@pytest.mark.asyncio
async def test_a_truncated_stream_ends_in_an_error_event_and_never_claims_success() -> None:
    """STR-04: an EOF with no legal terminal event is truncation, and the client must be told so.

    This test replaces one that pinned the opposite — the chain used to flush `message_delta{stop_reason: "end_turn"}` + `message_stop` here, dressing a truncated turn as a clean one and storing it in the client's history as a complete answer. That predecessor said in its own docstring that it existed to be reversed rather than preserved; this is the reversal.

    Both halves are asserted, because either alone lets the regression back. Emitting the error event while still flushing the terminal would satisfy the first half and tell the client two contradictory things; the frozen Spec rules the two mutually exclusive — 不得再发 `message_stop` 冒充成功.
    """
    body = await _truncated_delivery(AnthropicAssembler())

    assert '"type":"error"' in body
    assert "incomplete_responses_stream" in body
    assert '"stop_reason":"end_turn"' not in body
    assert "message_stop" not in body


@pytest.mark.asyncio
async def test_the_synthesized_start_goes_out_while_the_policy_holds_everything_else() -> None:
    """`full` holds content until the end — but this frame exists to arrive now.

    Putting it through the buffer delays it for exactly as long as the wait that made it
    necessary, which is the same as never synthesising it. Collecting the whole stream cannot
    see that: the events come out in the same order either way. So this one pulls the first
    chunk under a deadline while upstream is still silent.
    """

    async def silent_then_late() -> AsyncIterator[bytes]:
        await asyncio.sleep(30)
        for payload in anthropic_stream("one"):
            yield payload

    early: list[bytes] = []
    async with aclosing(
        stream_delivery(
            silent_then_late(),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="full"),
            settings=StreamSettings(synthesized_response_headers_after_sec=1),
            message_id="msg_1",
            model="claude-model",
        )
    ) as stream:
        # Deliberately shorter than upstream's silence: anything arriving here cannot have come
        # from upstream, and cannot have waited for the buffer to release.
        async with asyncio.timeout(4):
            while not any(b"message_start" in chunk for chunk in early):
                early.append(await anext(stream))

    assert events_of(early) == ["message_start"]


def thinking_stream(signature: str) -> list[bytes]:
    """Upstream's shape: the signature rides inside content_block_start, never as a delta."""
    return [
        frame(
            "content_block_start",
            {
                "index": 0,
                "content_block": {"type": "thinking", "thinking": "", "signature": signature},
            },
        ),
        frame(
            "content_block_delta",
            {"index": 0, "delta": {"type": "thinking_delta", "thinking": "pondering"}},
        ),
        frame("content_block_stop", {"index": 0}),
        frame("message_delta", {"delta": {"stop_reason": "end_turn"}}),
        frame("message_stop", {}),
    ]


def signature_deltas(chunks: list[bytes]) -> list[str]:
    signatures: list[str] = []
    for line in b"".join(chunks).split(b"\n"):
        if not line.startswith(b"data: "):
            continue
        payload: object = orjson.loads(line[len(b"data: ") :])
        if not isinstance(payload, dict):
            continue
        delta: object = cast(dict[str, Any], payload).get("delta")
        if not isinstance(delta, dict):
            continue
        typed = cast(dict[str, Any], delta)
        if typed.get("type") == "signature_delta":
            signatures.append(str(typed.get("signature", "")))
    return signatures


@pytest.mark.asyncio
async def test_a_thinking_signature_reaches_the_client_as_a_delta() -> None:
    """Claude Code reads the signature from a delta, and upstream never sends one.

    Without this the signature is on the wire — inside content_block_start — and still lost,
    which is the failure `content_block_start_compat: signature_delta` names.
    """
    chunks = await collect(thinking_stream("sig-abc"))
    assert signature_deltas(chunks) == ["sig-abc"]


@pytest.mark.asyncio
async def test_the_signature_shim_can_be_turned_off() -> None:
    # The opt-out: `false` leaves the frame exactly as the assembler built it.
    chunks = await collect(thinking_stream("sig-abc"), signature_compat=False)
    assert signature_deltas(chunks) == []


@pytest.mark.asyncio
async def test_a_thinking_block_without_a_signature_gets_no_delta() -> None:
    # The negative control: nothing is synthesised when there is no signature to carry.
    chunks = await collect(thinking_stream(""))
    assert signature_deltas(chunks) == []


def responses_stream_with_unstable_ids() -> list[bytes]:
    """A Responses stream shaped like Copilot's: `added` and `done` carry *different* item ids.

    Taken from a live capture. `output_index` is the only identifier that pairs the two, so an
    assembler keyed on the id closes nothing and the whole response renders as zero bytes.
    """
    events: list[tuple[str, dict[str, Any]]] = [
        (
            "response.output_item.added",
            {"output_index": 0, "item": {"id": "added-aaa", "type": "message"}},
        ),
        ("response.output_text.delta", {"output_index": 0, "delta": "PONG"}),
        (
            "response.output_item.done",
            {"output_index": 0, "item": {"id": "done-zzz", "type": "message"}},
        ),
        ("response.completed", {"response": {"usage": {}}}),
    ]
    return [frame(event, data) for event, data in events]


@pytest.mark.asyncio
async def test_a_response_assembles_even_when_upstream_changes_the_item_id() -> None:
    chunks = await collect(responses_stream_with_unstable_ids(), assembler="responses")
    body = b"".join(chunks)
    assert body, "the response assembled into nothing"
    assert b'"text":"PONG"' in body
    assert events_of(chunks) == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


async def _recorded_feed(payloads: list[bytes], closed: list[bool]) -> AsyncIterator[bytes]:
    try:
        for payload in payloads:
            yield payload
    finally:
        closed.append(True)


async def _hanging_upstream(closed: list[bool], reached: asyncio.Event) -> AsyncIterator[bytes]:
    """One whole block, then the silence of a model that is still thinking."""
    try:
        for payload in anthropic_stream("one")[:3]:
            yield payload
        reached.set()
        await asyncio.Event().wait()
    finally:
        closed.append(True)


def _delivery(chunks: AsyncIterator[bytes]) -> AsyncGenerator[bytes]:
    return stream_delivery(
        chunks,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0),
        message_id="m",
        model="model",
    )


@pytest.mark.asyncio
async def test_closing_the_delivery_closes_the_upstream_under_it() -> None:
    # The promise this type is a generator for. A client that goes away mid-turn is ordinary — pressing Esc is this — and what it leaves behind is an upstream response nobody will read and nobody will close, held for as long as the model keeps thinking.
    closed: list[bool] = []
    delivery = _delivery(_recorded_feed(anthropic_stream("one"), closed))

    async for _ in delivery:
        break
    assert closed == []
    await delivery.aclose()

    # Closed by the time `aclose()` returns, not a few ticks later once the collector reaches it.
    assert closed == [True]


@pytest.mark.asyncio
async def test_a_pull_in_flight_does_not_outlive_the_delivery() -> None:
    # The worse half of the same story: with a pull suspended on an upstream that has gone quiet, the pull task pinned the upstream's frame, so it could not even be collected. It stayed pending for the life of the process.
    closed: list[bool] = []
    reached = asyncio.Event()
    delivery = _delivery(_hanging_upstream(closed, reached))
    before = asyncio.all_tasks()

    pump = asyncio.create_task(_drain(delivery))
    await asyncio.wait_for(reached.wait(), 2)
    # This one fails by not finishing: settling the pull is what lets the close proceed, so a change that stops settling it leaves the close waiting on an upstream that never speaks again, and the run hangs rather than this test failing.
    # Left unbounded on purpose, having measured that bounding it does nothing: `finish_stream_cleanup` defers a cancellation it receives and keeps waiting for the cleanup it owns, which is what makes cleanup survive a second cancel — and also what makes an outer `asyncio.timeout` unable to preempt it.
    pump.cancel()
    with suppress(asyncio.CancelledError):
        await pump
    await delivery.aclose()

    assert closed == [True]
    assert asyncio.all_tasks() - before - {asyncio.current_task()} == set()


async def _drain(delivery: AsyncGenerator[bytes]) -> None:
    async for _ in delivery:
        pass


@pytest.mark.asyncio
async def test_a_client_leaving_while_the_idle_guard_is_armed_leaves_nothing_behind() -> None:
    # The guard holds an anyio cancel scope open across the `anext` it is timing, and that `anext` runs in a task this delivery creates fresh for every pull. A client leaving cancels exactly that task, mid-scope — an anyio scope entered in one task and unwound in another is the shape that strands one, so the composition is worth pinning rather than reasoning about.
    # Armed well beyond the test's own lifetime: what is under test is the cancellation, not the firing.
    closed: list[bool] = []
    reached = asyncio.Event()
    delivery = _delivery(with_idle_timeout(_hanging_upstream(closed, reached), timeout_seconds=30))
    before = asyncio.all_tasks()

    pump = asyncio.create_task(_drain(delivery))
    await asyncio.wait_for(reached.wait(), 2)
    pump.cancel()
    with suppress(asyncio.CancelledError):
        await pump
    await delivery.aclose()

    assert closed == [True]
    assert asyncio.all_tasks() - before - {asyncio.current_task()} == set()


@pytest.mark.asyncio
async def test_the_idle_guard_settles_the_stream_it_was_watching() -> None:
    # Every layer on this chain releases what it consumes when it is closed, and the guard is now one of them. Composed as production composes it — the byte counter sits between the guard and the delivery — because that is the layer that makes the difference visible at all.
    # Snapshotted immediately after `aclose()` and with no tick in between: what is under test is that the release is part of the close rather than something the collector gets to later.
    # What this does not pin: the release of a real httpx response. Measured 2026-08-20 — `aiter_raw` closes the response after its loop rather than in a `finally`, so a real upstream is released by generator finalisation whether or not this layer settles it. This test uses a source that does cascade, and so speaks only for this layer's own link.
    released: list[bool] = []

    async def source() -> AsyncIterator[bytes]:
        try:
            for payload in anthropic_stream("one"):
                yield payload
            await asyncio.Event().wait()
        finally:
            released.append(True)

    trace = _Trace(method="POST", path="/v1/messages")
    counted = _counted_upstream(
        with_idle_timeout(source(), timeout_seconds=30),
        cast(Any, SimpleNamespace(active_requests=ActiveRequestRegistry())),
        "req",
        trace,
    )
    delivery = _delivery(counted)

    async for _ in delivery:
        break
    await delivery.aclose()

    assert released == [True]


# --- The client-facing keep-alive, and the seven ways its trigger read a stand-in ---


def delivery_of(chunks: AsyncIterator[bytes]) -> AsyncGenerator[bytes]:
    """`stream_delivery` over a caller-supplied upstream, for the paths `collect` cannot reach."""
    return stream_delivery(
        chunks,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=1),
        message_id="m",
        model="model",
    )


class SlowAssembler:
    """Takes real time to assemble and never completes a block.

    A stand-in for the timing rather than for any upstream behaviour: `push` is synchronous and, on a large event or a busy machine, unbounded. The real assemblers are too fast to hold a deadline open.
    """

    def __init__(self, *, seconds: float) -> None:
        self._seconds = seconds
        self._terminal = Terminal()

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        deadline = time.monotonic() + self._seconds
        while time.monotonic() < deadline:
            pass
        return ()


async def run_with_a_talkative_upstream(*, deltas: int, gap: float) -> list[bytes]:
    """One whole block, then a second block that stays open while upstream keeps talking."""

    async def trickle() -> AsyncIterator[bytes]:
        for payload in anthropic_stream("one")[:3]:
            yield payload
        yield frame("content_block_start", {"index": 1, "content_block": {"type": "text"}})
        for _ in range(deltas):
            await asyncio.sleep(gap)
            yield frame(
                "content_block_delta",
                {"index": 1, "delta": {"type": "text_delta", "text": "x"}},
            )

    return [chunk async for chunk in delivery_of(trickle())]


@pytest.mark.asyncio
async def test_a_talkative_upstream_does_not_suppress_the_keep_alive() -> None:
    # The window a client actually times out in: upstream is sending faster than the interval, and every one of those deltas belongs to a block that has not closed, so the client is owed a keep-alive for the whole two seconds. Keying the cadence on upstream events instead of on our own writes made this case send nothing at all.
    chunks = await run_with_a_talkative_upstream(deltas=10, gap=0.2)
    assert PING_FRAME in chunks
    # And the pings really did stand in for content: the second block never closed, so only the first one was ever delivered.
    assert events_of(chunks).count("content_block_stop") == 1


async def run_with_a_ready_upstream(*, seconds: float) -> list[bytes]:
    """One whole block, then deltas that are ready the moment they are asked for."""

    async def trickle() -> AsyncIterator[bytes]:
        for payload in anthropic_stream("one")[:3]:
            yield payload
        yield frame("content_block_start", {"index": 1, "content_block": {"type": "text"}})
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            yield frame(
                "content_block_delta",
                {"index": 1, "delta": {"type": "text_delta", "text": "x"}},
            )

    return [chunk async for chunk in delivery_of(trickle())]


@pytest.mark.asyncio
async def test_an_always_ready_upstream_does_not_starve_the_keep_alive() -> None:
    # An upstream whose next event is already buffered finishes every pull in the same scheduling turn, so the branch that delivers an event is reached every time and the expired deadline below it never is. The block stays open throughout, so none of those events writes anything downstream, and the client is starved for as long as the run lasts.
    chunks = await run_with_a_ready_upstream(seconds=1.3)
    assert PING_FRAME in chunks
    assert events_of(chunks).count("content_block_stop") == 1


async def run_held_back(policy: str) -> list[bytes]:
    """One whole block that the policy holds back, then a second block upstream never closes."""

    async def trickle() -> AsyncIterator[bytes]:
        for payload in anthropic_stream("one")[:3]:
            yield payload
        yield frame("content_block_start", {"index": 1, "content_block": {"type": "text"}})
        await asyncio.sleep(2.5)

    return [
        chunk
        async for chunk in stream_delivery(
            trickle(),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy=policy),  # pyright: ignore[reportArgumentType]
            settings=StreamSettings(
                sse_ping_interval=1,
                synthesized_response_headers_after_sec=1,
            ),
            message_id="m",
            model="model",
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["full", "until-tool-use"])
async def test_a_held_back_block_does_not_disarm_both_guards(policy: str) -> None:
    # These two policies hold every block until the stream ends, so a block existing is not a byte delivered. Disarming the synthesis timer the moment the assembler produced a block turned off the preamble and the keep-alive together, and the client then had nothing at all for as long as upstream cared to talk — the one window here with no upper bound.
    chunks = await run_held_back(policy)
    assert events_of(chunks)[0] == "message_start"
    assert PING_FRAME in chunks


@pytest.mark.asyncio
async def test_a_cancelled_consumer_gets_its_cancellation_back() -> None:
    # The outer generator awaits the inner one. Cancelling the consumer must surface as CancelledError rather than being swallowed by the cleanup that runs on the way out.
    async def upstream() -> AsyncIterator[bytes]:
        yield frame("content_block_start", {"index": 0, "content_block": {"type": "text"}})
        await asyncio.sleep(60)

    async def consume() -> None:
        async with aclosing(delivery_of(upstream())) as delivery:
            async for _ in delivery:
                pass

    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_an_upstream_failure_reaches_the_caller() -> None:
    # An upstream that breaks mid-stream must not be reported as a stream that simply ended: the caller has to be able to tell a finished response from a truncated one.
    async def upstream() -> AsyncIterator[bytes]:
        for payload in anthropic_stream("one")[:3]:
            yield payload
        raise RuntimeError("upstream broke")

    with pytest.raises(RuntimeError, match="upstream broke"):
        async with aclosing(delivery_of(upstream())) as delivery:
            async for _ in delivery:
                pass


@pytest.mark.asyncio
async def test_the_schedule_adds_no_turn_between_an_event_and_an_ending() -> None:
    # Narrow on purpose. On the ready path the scheduler hands over what upstream produced and a way to ask; it does not insert a turn of its own before the next pull. It does produce an event-less turn on the other path, when a pull is still running and a deadline elapses — that is a different branch and this construction never reaches it.
    async def upstream() -> AsyncIterator[bytes]:
        yield frame("content_block_start", {"index": 0, "content_block": {"type": "text"}})

    last_write = _LastWrite(at=asyncio.get_running_loop().time())
    pulls: list[Any] = []
    async with aclosing(_events_with_ping(upstream(), 1, last_write=last_write)) as events:
        pulls.append(await anext(events))
        # Nothing is written downstream, so `last_write` stays where it was and the keep-alive falls due while the consumer is away. The next pull ends the stream.
        await asyncio.sleep(1.2)
        async for pull in events:
            pulls.append(pull)

    assert len(pulls) == 1
    assert pulls[0].event is not None


@pytest.mark.asyncio
async def test_an_unassemblable_event_fails_before_the_preamble() -> None:
    # A pull that came back with an event has not shown that the event can be delivered. Answering the due preamble first put a `message_start` in front of a stream that was about to fail on the very event whose arrival made the deadline reachable — and had that write failed, the assembler's error would never have been seen at all.
    chunks: list[bytes] = []

    async def upstream() -> AsyncIterator[bytes]:
        # Occupies the loop past the synthesis deadline without awaiting, so the deadline is due by the time the event lands.
        deadline = time.monotonic() + 1.05
        while time.monotonic() < deadline:
            pass
        yield frame(
            "content_block_start",
            {"index": "not-an-int", "content_block": {"type": "text"}},
        )

    with pytest.raises(ValueError):
        async with aclosing(
            stream_delivery(
                upstream(),
                AnthropicAssembler(),
                buffer=BlockBuffer(policy="block"),
                settings=StreamSettings(
                    sse_ping_interval=0,
                    synthesized_response_headers_after_sec=1,
                ),
                message_id="m",
                model="model",
            )
        ) as delivery:
            async for chunk in delivery:
                chunks.append(chunk)

    assert chunks == []


@pytest.mark.asyncio
async def test_a_deadline_that_falls_due_during_assembly_is_not_missed() -> None:
    # Assembling is synchronous and unbounded, so a deadline can come due while it runs. Reading the answer at pull time and acting on it after assembling asked the question before it could be answered: the keep-alive slipped by a whole assembly, which is one more interval the client spends with nothing.
    async def upstream() -> AsyncIterator[bytes]:
        for _ in range(2):
            yield frame("content_block_start", {"index": 0, "content_block": {"type": "text"}})

    start = time.monotonic()
    at: list[float] = []
    async with aclosing(
        stream_delivery(
            upstream(),
            SlowAssembler(seconds=1.05),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(
                sse_ping_interval=1,
                synthesized_response_headers_after_sec=1,
            ),
            message_id="m",
            model="model",
        )
    ) as delivery:
        async for _ in delivery:
            at.append(time.monotonic() - start)

    assert at
    # One assembly is enough to make the deadline due; waiting for a second one to notice is the defect.
    assert at[0] < 2.0


@pytest.mark.asyncio
async def test_an_always_ready_upstream_does_not_starve_the_preamble() -> None:
    # Same run of ready events, with keep-alives switched off and synthesis on. The preamble is owed on its own deadline, so settling only the keep-alive on the ready path left it starved too: the first byte of a reply whose block never closes arrived with the end of the stream.
    finished = False

    async def upstream() -> AsyncIterator[bytes]:
        nonlocal finished
        yield frame("content_block_start", {"index": 0, "content_block": {"type": "text"}})
        deadline = time.monotonic() + 1.6
        while time.monotonic() < deadline:
            yield frame(
                "content_block_delta",
                {"index": 0, "delta": {"type": "text_delta", "text": "x"}},
            )
        finished = True

    arrived_while_running: bool | None = None
    async with aclosing(
        stream_delivery(
            upstream(),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(
                sse_ping_interval=0,
                synthesized_response_headers_after_sec=1,
            ),
            message_id="m",
            model="model",
        )
    ) as delivery:
        async for _ in delivery:
            if arrived_while_running is None:
                arrived_while_running = not finished

    assert arrived_while_running is True


@pytest.mark.asyncio
async def test_a_due_preamble_goes_out_even_though_the_stream_is_already_over() -> None:
    """Freezes the accepted half of the trade-off, in the shape it actually takes.

    Whether the next pull ends the stream cannot be known without pulling, so a cue that is owed goes out first. Where the client already has bytes that costs one comment. Where it does not, the cue is `message_start`, which opens the response — and an opened response that never saw a terminal event is a truncation under STR-04. So the accepted cost is not a tidy empty message: it turns a request that would have been zero bytes into one the client sees fail. Written down here rather than discovered later.
    """

    async def upstream() -> AsyncIterator[bytes]:
        yield frame("content_block_start", {"index": 0, "content_block": {"type": "text"}})

    chunks = [
        chunk
        async for chunk in stream_delivery(
            upstream(),
            SlowAssembler(seconds=1.05),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(
                sse_ping_interval=0,
                synthesized_response_headers_after_sec=1,
            ),
            message_id="m",
            model="model",
        )
    ]

    assert PING_FRAME not in chunks
    assert events_of(chunks) == ["message_start", "error"]
async def _trickling_upstream() -> AsyncIterator[bytes]:
    """Never silent, never finished — the shape the two phase guards cannot see."""
    for payload in anthropic_stream("one")[:3]:
        yield payload
    while True:
        await asyncio.sleep(0.05)
        yield b": ping\n\n"


@pytest.mark.asyncio
async def test_the_deadline_stops_an_upstream_that_trickles_forever() -> None:
    # What `upstream_request_deadline` is for, and what nothing enforced: `response_header` is spent once the headers arrive and `stream_idle` is reset by every drip, so an upstream that keeps talking without ever finishing satisfies both.
    loop = asyncio.get_running_loop()
    delivery = _delivery(with_deadline_at(_trickling_upstream(), deadline_at=loop.time() + 0.4))

    with pytest.raises(StreamDeadlineError):
        async for _ in delivery:
            pass


@pytest.mark.asyncio
async def test_the_deadline_does_not_answer_for_the_idle_guard() -> None:
    # Nested guards both raise `TimeoutError`, so the outer one can report the inner one's expiry as its own. An operator reading that line reaches for the wrong setting and finds it already correct.
    async def goes_quiet() -> AsyncIterator[bytes]:
        for payload in anthropic_stream("one")[:3]:
            yield payload
        await asyncio.sleep(5)

    loop = asyncio.get_running_loop()
    delivery = _delivery(
        with_deadline_at(
            with_idle_timeout(goes_quiet(), timeout_seconds=1),
            deadline_at=loop.time() + 30,
        )
    )

    with pytest.raises(StreamIdleTimeoutError):
        async for _ in delivery:
            pass


@pytest.mark.asyncio
async def test_no_deadline_leaves_a_slow_stream_alone() -> None:
    delivered = [chunk async for chunk in _delivery(with_deadline_at(feed(anthropic_stream("one"), gap=0.05), None))]
    assert events_of(delivered)[-1] == "message_stop"


@pytest.mark.asyncio
async def test_the_deadline_guard_settles_the_stream_it_was_watching() -> None:
    # Same rule as every other layer on this chain, and the same reason for pinning it: nothing else on the chain notices if this one stops releasing what it consumes.
    released: list[bool] = []

    async def source() -> AsyncIterator[bytes]:
        try:
            for payload in anthropic_stream("one"):
                yield payload
            await asyncio.Event().wait()
        finally:
            released.append(True)

    trace = _Trace(method="POST", path="/v1/messages")
    counted = _counted_upstream(
        with_deadline_at(source(), deadline_at=asyncio.get_running_loop().time() + 30),
        cast(Any, SimpleNamespace(active_requests=ActiveRequestRegistry())),
        "req",
        trace,
    )
    delivery = _delivery(counted)

    async for _ in delivery:
        break
    await delivery.aclose()

    assert released == [True]
