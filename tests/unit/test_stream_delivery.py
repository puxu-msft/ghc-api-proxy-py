"""Streaming delivery over a real upstream byte stream.

The invariant under test is what the client sees and when.
Nothing before the first whole block, each block as a closed group, keep-alives with no content.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any, cast

import orjson
import pytest

from app.config.schema import ContentBlockStartCompat
from app.pipeline.delivery.assembler import AnthropicAssembler, ResponsesAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import PING_FRAME, StreamSettings, stream_delivery


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
async def test_a_synthesized_start_that_never_gets_a_block_still_ends_the_message() -> None:
    """The degenerate line: the deadline fires and upstream then produces nothing at all.

    Pinned because it is the one shape this change alters that has no other witness. The client is left a message with no content blocks, where before it was left one that said nothing — and the terminal frames still arrive either way, so the stream closes rather than hanging. With the deadline disabled the same silence produces no bytes at all, which is what makes "no content blocks" an existing shape rather than one introduced here.
    """
    chunks = await collect([], initial_delay=1.1, synthesized_response_headers_after_sec=1)

    assert events_of(chunks) == ["message_start", "message_delta", "message_stop"]

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
