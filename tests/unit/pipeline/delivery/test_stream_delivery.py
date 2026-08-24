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

import httpx2
import orjson
import pytest

from app.config.schema import ContentBlockStartCompat, UpstreamRequestRetryConfig
from app.errors import ANTHROPIC_ERROR_TYPES, ErrorCategory
from app.model_provider.ghc_client.errors import normalize_upstream_error
from app.observability.active_requests import ActiveRequestRegistry
from app.observability.request_trace import RequestTrace
from app.pipeline.delivery import stream as stream_module
from app.pipeline.delivery.assembling import BlockAssembler, Terminal
from app.pipeline.delivery.blocks import BlockBuffer, CompletedBlock
from app.pipeline.delivery.formats.anthropic_messages import AnthropicAssembler, AnthropicFramer
from app.pipeline.delivery.formats.openai_responses import ResponsesAssembler
from app.pipeline.delivery.framing import OutboundFramer
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.delivery.stream import (
    PING_FRAME,
    Attempt,
    ContinuationSupport,
    ReplaySupport,
    StreamSettings,
    UpstreamSource,
    _events_with_ping,  # pyright: ignore[reportPrivateUsage]
    _LastWrite,  # pyright: ignore[reportPrivateUsage]
    stream_delivery,
)
from app.pipeline.retry import RetryLedger, RetryReason, reason_for
from app.server.routes.inference import (
    _counted_upstream,  # pyright: ignore[reportPrivateUsage]
)
from app.streaming.deadline import (
    ClientDeadlineError,
    StreamDeadlineError,
    with_client_deadline_at,
    with_deadline_at,
)
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
        async for chunk in delivering(
            delayed_feed(),
            ResponsesAssembler() if assembler == "responses" else AnthropicAssembler(),
            buffer=BlockBuffer(policy=policy),  # pyright: ignore[reportArgumentType]
            settings=StreamSettings(sse_ping_interval=interval),
            framer=AnthropicFramer(
                message_id="msg_1",
                model="claude-model",
                signature_compat=signature_compat,
            ),
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
        async for chunk in delivering(
            trickle(),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=1),
            framer=AnthropicFramer(message_id="m", model="model"),
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
async def test_silence_before_the_first_block_is_still_kept_alive() -> None:
    """A comment goes out while the client waits on a block that has not closed yet.

    This used to assert the opposite, on the grounds that a comment arriving first would open the response. It does not: `StreamingResponse.stream_response` sends `http.response.start` before it pulls a single chunk, so the client already holds the status — upstream's own, since the response is built with it once its headers arrive. Nothing written here can change what the client was told, and withholding the keep-alive only spends the wait in silence.

    What still may not go out early is `message_start`, which would open a message with no content in it. A comment is not an event and cannot be mistaken for one.
    """
    chunks = await run_with_gap(1, 1.2)
    assert PING_FRAME in chunks
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
        # The keep-alive is what makes the pull outlive its wait, which is the whole subject here; upstream then ends without ever producing a block.
        assert await collect([], interval=1, initial_delay=1.2) == [PING_FRAME]
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
        async for chunk in delivering(
            feed(payloads),
            ResponsesAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="m", model="gpt-model"),
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


def _closing_stop_reason(body: str) -> str | None:
    """The `stop_reason` on the one `message_delta` a close emits, or `None` if there was no close."""
    for line in body.splitlines():
        if line.startswith("data:") and '"message_delta"' in line:
            return cast(str | None, orjson.loads(line.removeprefix("data:"))["delta"]["stop_reason"])
    return None


async def _truncated_delivery(assembler: AnthropicAssembler) -> str:
    """Deliver a stream that stops after its blocks and before upstream says how it ended."""
    # Everything upstream sent before it stopped: the blocks, and neither `message_delta` nor `message_stop`.
    return await _truncated_delivery_of(anthropic_stream("one")[:-2], assembler)


async def _truncated_delivery_of(payloads: list[bytes], assembler: AnthropicAssembler) -> str:
    """The same, for a caller that chooses how much of the ending upstream managed to send."""
    delivered: list[bytes] = []
    async with aclosing(
        delivering(
            feed(payloads),
            assembler,
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
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
async def test_an_eof_between_blocks_closes_the_message_without_claiming_success() -> None:
    """Upstream stopped at a block boundary without saying why. Every block it produced is whole, so nothing the client holds is damaged and an error frame would call a reply truncated when nothing was cut. Ruled 2026-08-22.

    The invariant that outlives the ruling is the one this test has carried through two rewrites: **never dress a turn upstream did not finish as one it did.** The chain originally flushed `end_turn` here, which stored a truncated answer in the client's history as a complete one; the fix made it an error; this makes it a clean close under upstream's own word for it. `end_turn` staying absent is what makes the third version a refinement of the second rather than a reversion to the first, and it is asserted for that reason.
    """
    body = await _truncated_delivery(AnthropicAssembler())

    assert '"type":"error"' not in body
    assert "incomplete_responses_stream" not in body
    assert "message_stop" in body
    # Read off the frame rather than matched as a substring. Asserting `"incomplete" in body` and then `"end_turn" not in body` looked like two checks and was one: only one `stop_reason` is ever emitted, so the second was strictly implied by the first and could never fail on its own. An equality pins both directions at once — the reason it must be, and every reason it must not be, `end_turn` above all.
    assert _closing_stop_reason(body) == "incomplete"


@pytest.mark.asyncio
async def test_an_eof_through_a_block_is_still_a_truncation() -> None:
    """The other side of the same judgement, and the pair is what gives either one meaning.

    Cut here with a block still open, so the assembler is holding a draft. That is a reply severed mid-sentence rather than one that simply stopped being explained, and it keeps the ending it always had.
    """
    # Everything up to and including the delta, but not the `content_block_stop`: a draft is left open.
    delivered: list[bytes] = []
    async with aclosing(
        delivering(
            feed(anthropic_stream("one", "two")[:4]),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
        )
    ) as stream:
        async for chunk in stream:
            delivered.append(chunk)
    body = b"".join(delivered).decode().replace(" ", "")

    assert '"type":"error"' in body
    assert "incomplete_responses_stream" in body
    assert "message_stop" not in body


@pytest.mark.asyncio
async def test_an_empty_stop_reason_puts_the_clean_eof_back_to_an_error() -> None:
    """The off-switch, asserted because a setting nobody exercises is a setting nobody can trust.

    An operator who would rather see a loud truncation than a quiet close sets `client_delivery.unterminated_stream_stop_reason` empty and gets the pre-2026-08-22 ending back.
    """
    delivered: list[bytes] = []
    async with aclosing(
        delivering(
            feed(anthropic_stream("one")[:-2]),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0, unterminated_stop_reason=""),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
        )
    ) as stream:
        async for chunk in stream:
            delivered.append(chunk)
    body = b"".join(delivered).decode().replace(" ", "")

    assert "incomplete_responses_stream" in body
    assert "message_stop" not in body


@pytest.mark.asyncio
async def test_a_reason_upstream_gave_survives_the_clean_close() -> None:
    """An Anthropic leg splits its ending: `message_delta` carries the reason, `message_stop` merely closes. A stream that loses only the second still told us why it stopped.

    The configured reason is for the case where upstream said *nothing*. Applying it unconditionally replaced an observation with an invention — and disagreed with this project's own completion line, which already treats a set `stop_reason` as the turn having said what it needed to. Measured before the fix: the log read `max_tokens` while the client was told `incomplete`, out of one turn.
    """
    # `max_tokens` rather than `end_turn`, which the framer also synthesises for an empty reason — a test whose expected value collides with the fallback cannot tell a passthrough from a coincidence.
    upstream = [
        *anthropic_stream("one")[:-2],
        frame("message_delta", {"delta": {"stop_reason": "max_tokens"}}),
    ]
    body = await _truncated_delivery_of(upstream, AnthropicAssembler())

    assert _closing_stop_reason(body) == "max_tokens"
    assert '"type":"error"' not in body


def _responses_item(index: int, item_id: str, *, status: str) -> list[bytes]:
    """One Responses text item, opened and closed, with upstream's own verdict on whether it finished."""
    return [
        frame(
            "response.output_item.added",
            {"output_index": index, "item": {"type": "message", "id": item_id, "content": []}},
        ),
        frame(
            "response.output_text.delta",
            {"output_index": index, "item_id": item_id, "delta": f"part{index}"},
        ),
        frame(
            "response.output_item.done",
            {
                "output_index": index,
                "item": {
                    "type": "message",
                    "id": item_id,
                    "status": status,
                    "content": [{"type": "output_text", "text": f"part{index}"}],
                },
            },
        ),
    ]


async def _responses_delivery(payloads: list[bytes]) -> str:
    delivered: list[bytes] = []
    async with aclosing(
        delivering(
            feed(payloads),
            ResponsesAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
        )
    ) as stream:
        async for chunk in stream:
            delivered.append(chunk)
    return b"".join(delivered).decode().replace(" ", "")


@pytest.mark.asyncio
async def test_a_responses_eof_between_whole_items_closes_the_message() -> None:
    """The same ruling on the leg it actually fires on.

    Measured over 133 929 recorded upstream streams: of the 109 that ended without a terminal event, the four that stopped at a block boundary were **all** on this leg — the Anthropic leg's 32 were every one of them mid-block. So the refinement's only real-world trigger had no test at all until this one, and both formats' `cut_mid_block` needs its own.
    """
    body = await _responses_delivery(
        _responses_item(0, "msg_a", status="completed") + _responses_item(1, "msg_b", status="completed")
    )

    assert '"type":"error"' not in body
    assert _closing_stop_reason(body) == "incomplete"
    assert '"text":"part0"' in body
    assert '"text":"part1"' in body


@pytest.mark.asyncio
async def test_a_responses_item_upstream_called_incomplete_is_not_a_block_boundary() -> None:
    """Upstream said in so many words that it cut this item short, and then the connection ended without a terminal event.

    This leg has a state the other does not: `output_item.done` pops the draft and, when the item is marked `incomplete`, parks the block rather than releasing it. So `_drafts` is empty while a block sits cut short and undelivered, and a `cut_mid_block` reading only `_drafts` answered "boundary" here — the clean close then dropped that block in silence, where the old ending had at least been loud. **Turning a loud truncation into quiet content loss is the worst direction this could have failed in**, and it is why this test exists rather than being folded into the one above.
    """
    body = await _responses_delivery(
        _responses_item(0, "msg_a", status="completed") + _responses_item(1, "msg_b", status="incomplete")
    )

    assert "incomplete_responses_stream" in body
    assert "message_stop" not in body
    # What upstream did finish is still delivered; only the ending changes.
    assert '"text":"part0"' in body


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

    Without this the signature is on the wire — inside content_block_start — and still lost, which is the failure `content_block_start_compat: signature_delta` names.
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

    Taken from a live capture. `output_index` is the only identifier that pairs the two, so an assembler keyed on the id closes nothing and the whole response renders as zero bytes.
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
    return delivering(
        chunks,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0),
        framer=AnthropicFramer(message_id="m", model="model"),
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

    trace = RequestTrace(method="POST", path="/v1/messages")
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
    return delivering(
        chunks,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=1),
        framer=AnthropicFramer(message_id="m", model="model"),
    )


class SlowAssembler:
    """Takes real time to assemble, and completes at most the one block it is asked for.

    A stand-in for the timing rather than for any upstream behaviour: `push` is synchronous and, on a large event or a busy machine, unbounded. The real assemblers are too fast to hold a deadline open.

    `first_block` exists because the keep-alive is only observable once the client holds bytes, and the client holds no bytes until a block has been delivered. A stand-in that never completes one can no longer be used to watch the schedule at all.
    """

    @property
    def cut_mid_block(self) -> bool:
        """Never mid-block: this stand-in exists for the timing, and completes its block or nothing."""
        return False

    def __init__(self, *, seconds: float, first_block: bool = False) -> None:
        self._seconds = seconds
        self._terminal = Terminal()
        self._pending = (
            (CompletedBlock(index=0, kind="text", payload={"type": "text", "text": "one"}),)
            if first_block
            else ()
        )

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        deadline = time.monotonic() + self._seconds
        while time.monotonic() < deadline:
            pass
        blocks, self._pending = self._pending, ()
        return blocks


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
        async for chunk in delivering(
            trickle(),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy=policy),  # pyright: ignore[reportArgumentType]
            settings=StreamSettings(
                sse_ping_interval=1,
            ),
            framer=AnthropicFramer(message_id="m", model="model"),
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["full", "until-tool-use"])
async def test_a_held_back_policy_is_still_kept_alive_before_its_first_block(policy: str) -> None:
    """These two policies hold every block until the stream ends, so a block existing is not a byte delivered — and the keep-alive is the only thing standing between the client and the whole turn in silence.

    It goes out before `message_start` here, and that is the point: the client already holds a 200, so a comment costs nothing and changes nothing. What does not go out early is the preamble, which would open a message with nothing in it.
    """
    chunks = await run_held_back(policy)
    assert PING_FRAME in chunks
    # The preamble still travels with the flush at the end, and the comment before it is not an event.
    assert events_of(chunks)[0] == "message_start"
    assert chunks.index(PING_FRAME) < chunks.index(next(c for c in chunks if b"message_start" in c))


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
            delivering(
                upstream(),
                AnthropicAssembler(),
                buffer=BlockBuffer(policy="block"),
                settings=StreamSettings(
                    sse_ping_interval=0,
                ),
                framer=AnthropicFramer(message_id="m", model="model"),
            )
        ) as delivery:
            async for chunk in delivery:
                chunks.append(chunk)

    body = b"".join(chunks).decode()
    # The invariant is unchanged: no message is opened for a stream that failed before it had content.
    assert "message_start" not in body
    # What is new is that the client is told at all. It used to get a 200 whose body simply stopped.
    # `proxy_delivery_failed`, not an upstream code: a bad index out of our own assembler is this side's bug, and the one word a client can read must not blame upstream for it.
    assert "proxy_delivery_failed" in body


@pytest.mark.asyncio
async def test_a_deadline_that_falls_due_during_assembly_is_not_missed() -> None:
    # Assembling is synchronous and unbounded, so a deadline can come due while it runs. Reading the answer at pull time and acting on it after assembling asked the question before it could be answered: the keep-alive slipped by a whole assembly, which is one more interval the client spends with nothing.
    #
    # The first push completes a block, because a keep-alive cannot go out to a client that has received nothing: the first byte settles the response's status, and until a block exists there is nothing to settle it with. Three pushes rather than two, so there is still an assembly after the one that delivered.
    async def upstream() -> AsyncIterator[bytes]:
        for _ in range(3):
            yield frame("content_block_start", {"index": 0, "content_block": {"type": "text"}})

    start = time.monotonic()
    at: list[float] = []
    async with aclosing(
        delivering(
            upstream(),
            SlowAssembler(seconds=1.05, first_block=True),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(
                sse_ping_interval=1,
            ),
            framer=AnthropicFramer(message_id="m", model="model"),
        )
    ) as delivery:
        async for _ in delivery:
            at.append(time.monotonic() - start)

    assert at
    # One assembly is enough to make the deadline due; waiting for a second one to notice is the defect.
    assert at[0] < 2.0


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

    trace = RequestTrace(method="POST", path="/v1/messages")
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


# --- How the upstream stream was paced, which the duration alone cannot say ---


@pytest.mark.asyncio
async def test_a_silence_in_the_middle_of_the_stream_is_recorded_apart_from_the_wait_for_its_first_byte() -> None:
    """On 2026-08-20 upstream went quiet mid-stream for 242 seconds and nothing on this side could say so afterwards.

    Two mistakes are pinned here rather than one, because both produce a plausible-looking number. Timing from the start of the request folds the wait for the first byte into the answer, and then every request's maximum is the time it spent routing — so the long sleep before the first chunk is deliberately the longest wait in this stream, and the assertion refuses it. Keeping only the latest gap reports the last one, which here is nothing at all.

    Real sleeps rather than a fake clock: `time.monotonic` is read through the `time` module, so substituting it would replace it for the whole process, and the interval needed is two hundred milliseconds.
    """
    before_first, mid_stream = 0.15, 0.06

    async def source() -> AsyncIterator[bytes]:
        await asyncio.sleep(before_first)
        yield b"first"
        await asyncio.sleep(mid_stream)
        yield b"second"
        yield b"third"

    trace = RequestTrace(method="POST", path="/v1/messages", started=time.monotonic())
    counted = _counted_upstream(
        source(),
        cast(Any, SimpleNamespace(active_requests=ActiveRequestRegistry())),
        "req",
        trace,
    )

    async with aclosing(counted):
        received = [chunk async for chunk in counted]

    assert received == [b"first", b"second", b"third"]
    assert trace.upstream_chunks == 3
    assert trace.first_upstream_byte_s is not None
    assert trace.first_upstream_byte_s >= before_first
    assert trace.upstream_max_gap_s is not None
    assert mid_stream <= trace.upstream_max_gap_s < before_first


@pytest.mark.asyncio
async def test_a_stream_of_one_chunk_reports_no_gap_rather_than_a_gap_of_zero() -> None:
    """There is no interval between two arrivals when there was only one arrival, and `0.0` would read as "upstream never paused" — a measurement nobody took."""
    async def source() -> AsyncIterator[bytes]:
        yield b"only"

    trace = RequestTrace(method="POST", path="/v1/messages", started=time.monotonic())
    counted = _counted_upstream(
        source(),
        cast(Any, SimpleNamespace(active_requests=ActiveRequestRegistry())),
        "req",
        trace,
    )

    async with aclosing(counted):
        assert [chunk async for chunk in counted] == [b"only"]

    assert trace.upstream_chunks == 1
    assert trace.upstream_max_gap_s is None


def _replay_over(attempts: list[list[bytes]]) -> ReplaySupport:
    """Hand out one fresh attempt per call, each with its own assembler and buffer."""
    remaining = list(attempts)

    async def reopen(_replacing: Exception) -> Attempt | None:
        if not remaining:
            return None
        # Its own marker, as production gives a replayed attempt: a tear the previous attempt recorded must not read as this one's.
        source = UpstreamSource(feed(remaining.pop(0)))
        return (source, source, AnthropicAssembler(), BlockBuffer(policy="block"))

    return ReplaySupport(
        ledger=RetryLedger(UpstreamRequestRetryConfig.model_validate({})),
        eligible=lambda error: RetryReason.NETWORK if isinstance(error, ConnectionError) else None,
        reopen=reopen,
    )


async def _tears_after(payloads: list[bytes]) -> AsyncIterator[bytes]:
    for payload in payloads:
        yield payload
    raise ConnectionError("upstream tore")


@pytest.mark.asyncio
async def test_a_stream_the_client_never_saw_is_replaced_without_a_trace() -> None:
    """The whole of what a traceless retry means: one message on the wire, one preamble, and the failed attempt's output nowhere in it.

    The first attempt tears after opening a block it never closes, so nothing was ever delivered. A second attempt answers the same request and the client cannot tell there were two.
    """
    chunks = [
        chunk
        async for chunk in delivering(
            _tears_after(anthropic_stream("lost")[:2]),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
            replay=_replay_over([anthropic_stream("kept")]),
        )
    ]
    body = b"".join(chunks)
    assert events_of(chunks).count("message_start") == 1
    assert b'"text":"kept"' in body
    assert b"lost" not in body
    assert events_of(chunks)[-1] == "message_stop"


@pytest.mark.asyncio
async def test_a_stream_the_client_already_saw_is_not_replaced() -> None:
    """Once a block has been delivered there is no traceless anything: a second attempt would send the client a second copy of what it holds.

    The sample stops before upstream's terminal event on purpose. `anthropic_stream` appends one, and a turn upstream *finished* before the connection went is not this case at all — it is complete, and this test used to pass on such a sample only because a finished ending was being folded in with an abandoned one.
    """
    torn = _tears_after(anthropic_stream("first")[:3] + anthropic_stream("second")[:2])
    with pytest.raises(ConnectionError):
        _ = [
            chunk
            async for chunk in delivering(
                torn,
                AnthropicAssembler(),
                buffer=BlockBuffer(policy="block"),
                settings=StreamSettings(sse_ping_interval=0),
                framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
                replay=_replay_over([anthropic_stream("kept")]),
            )
        ]


@pytest.mark.asyncio
async def test_a_failure_no_second_attempt_could_answer_is_not_replaced() -> None:
    """Eligibility is the caller's to answer, and a failure it refuses buys no second attempt even though the position would allow one.

    The raise is still asserted, and it is now the *second* half of the ending rather than the whole of it: the client is framed first and the caller learns the failure after. With no `continuation` configured there is nothing between the two.
    """
    replay = _replay_over([anthropic_stream("kept")])
    refusing = ReplaySupport(ledger=replay.ledger, eligible=lambda _error: None, reopen=replay.reopen)
    with pytest.raises(ConnectionError):
        _ = [
            chunk
            async for chunk in delivering(
                _tears_after(anthropic_stream("lost")[:2]),
                AnthropicAssembler(),
                buffer=BlockBuffer(policy="block"),
                settings=StreamSettings(sse_ping_interval=0),
                framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
                replay=refusing,
            )
        ]


class _FramerWithABug(AnthropicFramer):
    """A framer whose `block` raises, which is the one way this side's own code fails mid-delivery."""

    def block(self, block: CompletedBlock) -> tuple[bytes, ...]:
        raise TypeError("OutboundFramer.block() bug")


@pytest.mark.asyncio
async def test_a_bug_in_framing_is_not_charged_to_upstream() -> None:
    """The proxy's own bug used to reach the client wearing upstream's name, and wearing two names at once.

    `from_assembly` tagged `assembler.push` and nothing else, so an exception out of the framer fell through to the `not ours` default: the error frame called it `upstream_stream_failed` and the hand-over block called it `internal`. Two exits, opposite answers, one bug — and the client can only read the frame.

    The stated reason for the limit was that widening the tagged region "means wrapping a `yield`". It did not: `_commit` returns a list, so every framer call inside it has already run by the time the first chunk leaves. `deferred.md` §22之二.
    """
    handed: list[BaseException | None] = []

    def synthesize(error: BaseException | None, _stop_reason: str) -> dict[str, Any]:
        handed.append(error)
        return {"type": "tool_use", "id": "toolu_x", "name": "carry_on", "input": {}}

    with pytest.raises(TypeError):
        _ = [
            chunk
            async for chunk in delivering(
                feed(anthropic_stream("first")),
                AnthropicAssembler(),
                buffer=BlockBuffer(policy="block"),
                settings=StreamSettings(sse_ping_interval=0),
                framer=_FramerWithABug(message_id="msg_1", model="claude-model"),
                continuation=ContinuationSupport(synthesize=synthesize),
            )
        ]

    # Not handed back either: another attempt at a turn this side cannot frame would fail the same way, which is why `ours` gates the hand-over rather than only the wording.
    assert handed == [], "a bug here is not the client's to carry on from"


@pytest.mark.asyncio
async def test_a_bug_in_framing_says_so_on_the_frame_it_does_send() -> None:
    """The other half of the same fix: the frame the client can read must name the right party."""
    chunks: list[bytes] = []

    async def collect() -> None:
        async for chunk in delivering(
            feed(anthropic_stream("first")),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=_FramerWithABug(message_id="msg_1", model="claude-model"),
        ):
            chunks.append(chunk)

    with pytest.raises(TypeError):
        await collect()

    body = b"".join(chunks).decode()
    # `code` is what names the party, and on this path it is the *only* thing that can.
    # It used to be `type`: `WIRE_TYPES` spelled `INTERNAL` as `internal_error` and `UPSTREAM` as `upstream_error`, so `"upstream_error" not in body` was a real discriminator. Both of those are inventions — neither is in Anthropic's declared vocabulary — and correcting the table collapses both onto `api_error`, because Anthropic draws no such distinction.
    # Elsewhere the HTTP status carries what the dialect cannot (`.dev/docs/error-envelope/spec.md` §6.2). Not here: the status was fixed at 200 when the response headers went out, long before this failure existed. So a mid-stream frame has exactly one channel for "whose fault", and it is this extension field.
    assert '"code":"proxy_delivery_failed"' in body
    assert '"code":"upstream_stream_failed"' not in body
    assert f'"type":"{ANTHROPIC_ERROR_TYPES[ErrorCategory.INTERNAL]}"' in body


class _FramerWhoseKeepaliveFails(AnthropicFramer):
    """The keep-alive is this side's code too, and it runs where nothing had marked it."""

    def keepalive(self) -> bytes:
        raise TypeError("OutboundFramer.keepalive() bug")


@pytest.mark.asyncio
async def test_a_bug_in_the_keepalive_is_this_sides_too() -> None:
    """One of the places the old marker-per-site approach had missed, kept as a case after the predicate was inverted.

    It is here because the list of places this side runs code is what proved unbounded. Framing was left out of the old marker on a stated reason that did not hold; the keep-alive was marked in the same commit that fixed framing, and what was missing was this test — a review found it by mutating the marker away and watching the suite stay green. Nothing is marked now, upstream is what is identified, so this passes for a structural reason rather than because someone remembered.
    """
    chunks: list[bytes] = []

    payloads = anthropic_stream("one")

    async def silent_after_a_block() -> AsyncIterator[bytes]:
        # Three frames is one whole block, then a gap longer than the interval — the same shape `run_with_gap` uses, because a cue is only owed once one is due.
        for payload in payloads[:3]:
            yield payload
        await asyncio.sleep(1.2)
        for payload in payloads[3:]:
            yield payload

    with pytest.raises(TypeError):
        async for chunk in delivering(
            silent_after_a_block(),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=1),
            framer=_FramerWhoseKeepaliveFails(message_id="msg_1", model="claude-model"),
        ):
            chunks.append(chunk)

    body = b"".join(chunks).decode()
    # See the note in `test_a_bug_in_framing_says_so_on_the_frame_it_does_send`: `type` cannot tell these apart in Anthropic's own vocabulary, and on a mid-stream frame the status is already spent.
    assert '"code":"proxy_delivery_failed"' in body
    assert '"code":"upstream_stream_failed"' not in body


@pytest.mark.asyncio
async def test_a_bug_in_this_sides_sse_reader_is_not_handed_over_as_upstreams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reader between the socket and the assembler is this side's, and marking each of this side's places had missed it.

    An independent review built this against the marker-per-site version: the reader raised after a whole block had gone out, and the client received a hand-over blaming upstream for a bug in this proxy. Reproduced here through the same production wiring, with the reader replaced rather than the exception injected from outside — a `raise` from the upstream iterator would be upstream's by definition and would prove nothing.
    """
    handed: list[BaseException | None] = []

    def synthesize(error: BaseException | None, _stop_reason: str) -> dict[str, Any]:
        handed.append(error)
        return {"type": "tool_use", "id": "toolu_x", "name": "carry_on", "input": {}}

    real_read_events = stream_module.read_events

    def failing_reader(source: AsyncIterator[bytes]) -> AsyncIterator[SseEvent]:
        async def reader() -> AsyncIterator[SseEvent]:
            seen = 0
            async for event in real_read_events(source):
                seen += 1
                if seen > 3:
                    raise LookupError("bug in this side's SSE reader")
                yield event

        return reader()

    monkeypatch.setattr(stream_module, "read_events", failing_reader)

    with pytest.raises(LookupError):
        async for _ in delivering(
            feed(anthropic_stream("first", "second")),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
            continuation=ContinuationSupport(synthesize=synthesize),
        ):
            pass

    assert handed == [], "this side's bug is not the client's to carry on from"


@pytest.mark.asyncio
async def test_a_client_that_leaves_releases_the_upstream_through_every_layer() -> None:
    """The release chain has to survive the composition production actually uses, not the one tests find convenient.

    `delivering(...)` makes the marker and the composite the same object, so every existing close test walks a one-layer chain and cannot see this. Production stacks four — client deadline, counter, marker, then the two guards over the raw response — and `_counted_upstream` was the one that consumed its iterator with a bare `async for` — it closed itself and released nothing under it. `read_events` closes the outermost, the client deadline closes the counter, and the chain stopped there: the marker, both guards and the upstream response stayed open until the collector reached them.

    Measured at `1a34042` and at its parent alike, so it was not introduced by naming the marker — but the docstring on `UpstreamSource.aclose` claimed `read_events` closed the byte stream under it, and in this composition it did not.
    """
    closed: list[bool] = []

    async def raw() -> AsyncIterator[bytes]:
        try:
            for payload in anthropic_stream("first")[:3]:
                yield payload
            # Still open as far as upstream is concerned, which is the state a client leaves behind.
            await asyncio.sleep(30)
        finally:
            closed.append(True)

    def counted(request_id: str, count: int) -> None:
        """The registry call `_counted_upstream` makes; this test is about the close chain, not the counting."""

    chain = cast(Any, SimpleNamespace(active_requests=SimpleNamespace(add_bytes=counted)))
    trace = RequestTrace(method="POST", path="/v1/messages", request_id="probe", started=time.monotonic())
    marker = UpstreamSource(
        with_deadline_at(with_idle_timeout(raw(), timeout_seconds=0), deadline_at=None)
    )
    delivery = stream_delivery(
        # All four layers, in production's order. An earlier version of this test stopped at the counter and its docstring still claimed to compose what production composes; a review counted them.
        with_client_deadline_at(
            _counted_upstream(marker, chain, "probe", trace), deadline_at=None
        ),
        AnthropicAssembler(),
        upstream=marker,
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0),
        framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
    )
    async for _ in delivery:
        break
    assert closed == [], "the premise: upstream is still open while the client is reading"

    await delivery.aclose()
    # Immediately, not after a tick: an owner still holding the source keeps it open for as long as it holds it, so a collector cannot be what releases the connection.
    assert closed == [True]


class _ExplodingRegistry:
    """Stands in for `ActiveRequestRegistry` so the real `_counted_upstream` can be driven into a bug."""

    def __init__(self, boom_at: int) -> None:
        self.seen = 0
        self.boom_at = boom_at

    def add_bytes(self, request_id: str, count: int) -> None:
        self.seen += 1
        if self.seen >= self.boom_at:
            raise LookupError("bug in this side's byte counter")


@pytest.mark.asyncio
async def test_a_bug_below_the_marker_but_above_the_source_is_still_ours() -> None:
    """The seam two reviews found, closed by where the marker sits rather than by another list of places.

    Production composes four layers over the raw response, and `_counted_upstream` is one of them — this side's bookkeeping, not upstream's. While the marker wrapped the whole composite, a `LookupError` raised by the byte counter was tagged as upstream's tear and handed to the client, which returned cleanly with the exception gone. Measured at `62a457f`: `handed_count=1`, `returned_cleanly=True`.

    Driven through the real `_counted_upstream`, not a stand-in for it: the defect was that the marker sat on the wrong side of that exact function.
    """
    handed: list[BaseException | None] = []

    def synthesize(error: BaseException | None, _stop_reason: str) -> dict[str, Any]:
        handed.append(error)
        return {"type": "tool_use", "id": "toolu_x", "name": "carry_on", "input": {}}

    chain = cast(Any, SimpleNamespace(active_requests=_ExplodingRegistry(boom_at=4)))
    trace = RequestTrace(method="POST", path="/v1/messages", request_id="probe", started=time.monotonic())
    source = UpstreamSource(feed(anthropic_stream("first")))

    with pytest.raises(LookupError):
        async for _ in stream_delivery(
            _counted_upstream(source, chain, "probe", trace),
            AnthropicAssembler(),
            upstream=source,
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
            continuation=ContinuationSupport(synthesize=synthesize),
        ):
            pass

    assert handed == [], "this side's counter is not upstream, and its bug is not the client's to carry on from"


@pytest.mark.asyncio
async def test_a_failure_nobody_can_name_still_reaches_the_hand_over() -> None:
    """Whether a failure can be *named* decides whether another attempt is worth funding. It says nothing about whether the client can carry the turn on, and only the second question belongs at this door.

    Before 2026-08-22 the two were one: `eligible` returning `None` sent the stream straight out on a bare raise, so a failure the caller's taxonomy has no word for — a naked `h2.ProtocolError` is the one on record — skipped the hand-over entirely and took the client's turn with it. The client held a whole block and got no way to continue from it.

    Asserted through a refusing `eligible`, which is the same shape an unrecognised exception produces and does not depend on which exception types the caller happens to recognise this week.
    """
    synthesised: list[BaseException | None] = []

    def synthesize(error: BaseException | None, _stop_reason: str) -> dict[str, Any]:
        synthesised.append(error)
        return {"type": "tool_use", "id": "toolu_x", "name": "carry_on", "input": {}}

    replay = _replay_over([anthropic_stream("kept")])
    refusing = ReplaySupport(ledger=replay.ledger, eligible=lambda _error: None, reopen=replay.reopen)
    chunks = [
        chunk
        async for chunk in delivering(
            _tears_after(anthropic_stream("held")[:3]),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
            replay=refusing,
            continuation=ContinuationSupport(synthesize=synthesize),
        )
    ]
    body = b"".join(chunks).decode()

    assert len(synthesised) == 1, "the hand-over was never consulted"
    assert "carry_on" in body
    # A hand-over is an ending, not a failure: nothing is raised and no error frame goes out.
    assert '"type":"error"' not in body
    # And what the client already held is still there.
    assert '"text":"held"' in body


async def _hits_the_client_deadline_after(payloads: list[bytes]) -> AsyncIterator[bytes]:
    for payload in payloads:
        yield payload
    raise ClientDeadlineError("client request exceeded its deadline")


@pytest.mark.asyncio
async def test_the_client_deadline_is_the_one_ending_that_says_so() -> None:
    """By the time this can fire the response has been open a while and its status is long settled, so an SSE error frame is the only way left to say what happened.

    Without it this ending is byte-for-byte the same as upstream tearing — measured 2026-08-22 — and only the proxy's own log could tell them apart. Ruled the same day.

    The sample stops two events short of upstream's terminal so this is a deadline landing mid-turn, which is what the name claims. Whether a deadline landing *after* upstream finished ends the same way is the sibling test's question, and it is a separate ruling.
    """
    chunks = [
        chunk
        async for chunk in delivering(
            _hits_the_client_deadline_after(anthropic_stream("one")[:-2]),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
        )
    ]
    assert events_of(chunks)[-1] == "error"
    assert b"client_deadline_exceeded" in b"".join(chunks)
    # Not a `message_stop`: the turn did not finish, and saying it did is the defect this whole area exists to avoid.
    assert "message_stop" not in events_of(chunks)


@pytest.mark.asyncio
async def test_the_client_deadline_outranks_an_upstream_that_just_finished() -> None:
    """`client_request_deadline` bounds this round's total elapsed time, so once it fires the round is over — whether or not upstream happened to write its last byte first. Ruled 2026-08-22.

    The cost is real and accepted: a complete reply sits assembled in the buffer and is dropped in favour of the error frame. The upstream deadline is ordered the other way round for the opposite reason — it ends only *this attempt*, so a finished turn has to be recognised before anything asks what went wrong.

    Pins the ordering directly. The two tests above it also go red if the branches are swapped, but they say nothing about ordering in their names, and an ordering nobody named is an ordering the next reader will reshuffle.
    """
    chunks = [
        chunk
        async for chunk in delivering(
            _hits_the_client_deadline_after(anthropic_stream("one")),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
        )
    ]
    assert events_of(chunks)[-1] == "error"
    assert b"client_deadline_exceeded" in b"".join(chunks)
    assert "message_stop" not in events_of(chunks)


@pytest.mark.asyncio
async def test_an_upstream_tear_is_framed_and_then_raised() -> None:
    """Both halves, because either alone is a defect this project has already shipped once.

    The frame alone would leave the caller with nothing: it reads this exception to decide the request's verdict and to put a reason on the completion line, so a stream that framed and returned cleanly logged `ok` with the failure recorded nowhere.

    The raise alone is what the client used to get — a 200 whose body simply stopped, byte-for-byte identical to an idle timeout, a deadline, or the proxy abandoning the response. Ruled 2026-08-22: every ending that reaches here gets a frame. This test's predecessor was named for the opposite and said in its own docstring that widening the frame was "a separate question with its own answer to find"; the answer arrived.

    The sample stops before upstream's terminal event: a turn upstream finished is not torn, whatever happens to the connection afterwards.
    """
    chunks: list[bytes] = []
    with pytest.raises(ConnectionError):
        async with aclosing(
            delivering(
                _tears_after(anthropic_stream("one")[:3]),
                AnthropicAssembler(),
                buffer=BlockBuffer(policy="block"),
                settings=StreamSettings(sse_ping_interval=0),
                framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
            )
        ) as delivery:
            async for chunk in delivery:
                chunks.append(chunk)

    body = b"".join(chunks).decode()
    assert '"type":"error"' in body
    # Upstream's, not this side's: the party named on the wire is the one the client can act on.
    assert "upstream_stream_failed" in body
    # And the block the client had already been given is not taken back.
    assert '"text":"one"' in body


@pytest.mark.parametrize("policy", ["full", "until-tool-use"])
@pytest.mark.asyncio
async def test_a_held_back_policy_still_hears_the_client_deadline(policy: str) -> None:
    """The frame is owed once the response headers are out, not once a block has been delivered.

    `client-side-block-delivery.md` puts the condition at the headers, and those go out before this generator runs. Gated on a delivered block instead, these two policies — which hold every block until the stream ends — timed out having sent the client zero bytes and no frame at all.

    Mid-turn sample on purpose: this is about the policies, so it should not also depend on how a finished turn is ranked against the deadline.
    """
    chunks = [
        chunk
        async for chunk in delivering(
            _hits_the_client_deadline_after(anthropic_stream("one")[:-2]),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy=policy),  # pyright: ignore[reportArgumentType]
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
        )
    ]
    assert b"client_deadline_exceeded" in b"".join(chunks)
    # The buffered block is dropped rather than flushed first, which is what the document says to do.
    assert b'"text":"one"' not in b"".join(chunks)


async def _finishes_then_tears(error: Exception) -> AsyncIterator[bytes]:
    for payload in anthropic_stream("complete"):
        yield payload
    raise error


@pytest.mark.parametrize("policy", ["block", "full"])
@pytest.mark.asyncio
async def test_a_finished_turn_survives_a_failure_nothing_recognises(policy: str) -> None:
    """Whether upstream finished does not depend on what the failure was, so it has to be answered before anything asks.

    Answered from the verdict instead, this was one door short: a failure the caller's taxonomy refuses never reaches the verdict at all — it is raised first, and a complete reply goes with it. The client loses an answer it was owed, over an exception classifier that had never heard of the exception.

    The classifier is production's own, and the failure is a real one it cannot name: `httpx2.DecodingError`, raised from nine places in `httpx2/_decoders.py` when upstream's gzip, br, zstd or deflate body will not decompress. It reaches this loop as itself — `DecodingError` descends from `RequestError`, not `TransportError`, so the `_CONNECTION_ERRORS` tuple does not catch it. A stand-in exception paired with a stand-in taxonomy would assert the premise rather than prove it, and would keep passing once `normalize_upstream_error` learned to name the carrier — so the premise is asserted out loud, first.

    That is not hypothetical: the carrier used to be the bare `h2.ProtocolError` hyper-h2 raises through the gap in httpcore's guard, and on 2026-08-23 production learned to name it (`H2Error` joined `_CONNECTION_ERRORS`, closing `deferred.md` §22). The premise assertion is what said so, on the same day, instead of leaving this test passing for a reason that no longer held. **The subject has not changed** — it is still that `terminal.seen` must be answered before the taxonomy is consulted — only the exception carrying it.

    Both policies, because they lose different amounts through different code. Under `block` the client already holds the content and only the ending goes; under `full` nothing has been delivered yet, so the whole reply does — and recovering it runs the flush after the loop, which `block` never exercises because it has nothing held back.

    `reopen` counts rather than serves: reaching it would mean a second attempt was opened for a turn that was already whole, which no assertion on the bytes would show.
    """
    reopened = 0

    async def reopen(_replacing: Exception) -> Attempt | None:
        nonlocal reopened
        reopened += 1
        return None

    def eligible(error: Exception) -> RetryReason | None:
        known = normalize_upstream_error(error)
        return reason_for(known) if known is not None else None

    torn = httpx2.DecodingError("nothing upstream of here knows what this is")
    assert eligible(torn) is None, "the premise: production cannot name this failure"

    chunks = [
        chunk
        async for chunk in delivering(
            _finishes_then_tears(torn),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy=policy),  # pyright: ignore[reportArgumentType]
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
            replay=ReplaySupport(
                ledger=RetryLedger(UpstreamRequestRetryConfig.model_validate({})),
                eligible=eligible,
                reopen=reopen,
            ),
        )
    ]

    assert reopened == 0, "a reply that is already whole needs no second attempt"
    # Exact, because the claim is that the whole of it arrived and nothing else did.
    assert events_of(chunks) == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    assert b'"text":"complete"' in b"".join(chunks)


def delivering(
    chunks: AsyncIterator[bytes],
    assembler: BlockAssembler,
    *,
    buffer: BlockBuffer,
    settings: StreamSettings,
    framer: OutboundFramer,
    replay: ReplaySupport | None = None,
    continuation: ContinuationSupport | None = None,
) -> AsyncGenerator[bytes]:
    """`stream_delivery` with the upstream side named, which in a test is the whole of what was passed.

    Production composes four layers over the raw response and puts the marker in the middle of them, because `_counted_upstream` above it is this side's bookkeeping. A test hands over one iterator and nothing wraps it, so the marker is that iterator — which is exactly why it is spelled out here rather than defaulted inside `stream_delivery`: the default that is right for every test is the one that was wrong in production.
    """
    source = UpstreamSource(chunks)
    return stream_delivery(
        source,
        assembler,
        upstream=source,
        buffer=buffer,
        settings=settings,
        framer=framer,
        replay=replay,
        continuation=continuation,
    )
