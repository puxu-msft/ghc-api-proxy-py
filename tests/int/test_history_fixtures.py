"""The pipeline against streams taken from the history database rather than a fresh call.

Recording needs credentials and a live upstream. The service already kept what upstream sent, so
these fixtures come from `~/.local/share/copilot-api/history-v3*.db` via
`recorded/from_history.py` — which is also why they are cheap to add and cheap to keep.

They prove less than a live recording in exactly one way, and it is written into the cassette
rather than left to memory: history stores one object per SSE event, so these replay one frame per
chunk. How the bytes actually fell on the wire is a question only a recording can answer, and
`test_recorded_upstream.py` is where that is asked.

The text is gone. These are the operator's real conversations, so every string that is not
structural was replaced when the fixture was built. What survives is the protocol, which is the
part that could not be imagined correctly.
"""

from collections.abc import AsyncIterator
from typing import Any, cast

import orjson
import pytest
from recorded.cassettes import Cassette
from recorded.recorded_provider import cassette_path

from app.pipeline.delivery.assembling import BlockAssembler
from app.pipeline.delivery.blocks import BlockBuffer, CompletedBlock
from app.pipeline.delivery.formats.anthropic_messages import AnthropicAssembler
from app.pipeline.delivery.formats.openai_responses import ResponsesAssembler
from app.pipeline.delivery.sse_source import parse_frame
from app.pipeline.delivery.stream import StreamSettings, stream_delivery

RESPONSES = "history_responses_stream"
ANTHROPIC = "history_anthropic_stream"


def upstream_chunks(name: str) -> list[bytes]:
    cassette = Cassette.read(cassette_path(name))
    assert len(cassette.interactions) == 1, "these fixtures carry one response each"
    return cassette.interactions[0].chunks


async def deliver(name: str, assembler: BlockAssembler) -> bytes:
    """Put a recorded upstream stream through the delivery layer, as the server does."""

    async def feed() -> AsyncIterator[bytes]:
        for chunk in upstream_chunks(name):
            yield chunk

    return b"".join(
        [
            chunk
            async for chunk in stream_delivery(
                feed(),
                assembler,
                buffer=BlockBuffer(policy="block"),
                settings=StreamSettings(),
                message_id="msg_test",
                model="test-model",
            )
        ]
    )


def events_of(body: bytes) -> list[str]:
    return [
        line.removeprefix(b"event: ").decode()
        for line in body.splitlines()
        if line.startswith(b"event: ")
    ]


def test_every_history_fixture_says_where_it_came_from() -> None:
    """A frame-derived fixture and a wire recording do not prove the same thing.

    Both are cassettes and both replay, so nothing about the file itself distinguishes them. The
    provenance is the only place that distinction lives, and a fixture that lost it would quietly
    be taken for evidence about chunking that it cannot supply.
    """
    for name in (RESPONSES, ANTHROPIC):
        cassette = Cassette.read(cassette_path(name))
        source = cassette.interactions[0].source
        assert source.startswith("history:"), f"{name} does not say it came from history"
        assert source.count(":") >= 2, f"{name} names no operation to trace it back to"


def test_a_history_fixture_carries_no_prose() -> None:
    """These began as real conversations, so what is left has to be structure only.

    Naming the fields to remove missed `description`, `instructions` and `definition` — a tool
    definition and a system prompt, echoed back inside the response — so the builder keeps an
    allowlist instead. This checks the outcome rather than the list.
    """
    for name in (RESPONSES, ANTHROPIC):
        body = b"".join(upstream_chunks(name)).decode("utf-8", errors="replace")
        assert "/home/" not in body, f"{name} carries a filesystem path"
        assert not any("一" <= ch <= "鿿" for ch in body), f"{name} carries prose"


@pytest.mark.asyncio
async def test_a_history_responses_stream_assembles_into_blocks() -> None:
    """The primary path end to end: Anthropic SSE out of a real Responses stream."""
    body = await deliver(RESPONSES, ResponsesAssembler())

    events = events_of(body)
    assert events[0] == "message_start"
    assert events[-1] == "message_stop"
    assert events.count("content_block_stop") == 2, events


@pytest.mark.asyncio
async def test_a_history_anthropic_stream_assembles_into_blocks() -> None:
    """The passthrough path, from the most recent capture that still holds frames.

    One text block, so the count is asserted rather than merely being non-zero — this capture
    delivers nothing at all if block assembly breaks, and `>= 1` could not tell the difference.
    """
    body = await deliver(ANTHROPIC, AnthropicAssembler())

    events = events_of(body)
    assert events[0] == "message_start"
    assert events[-1] == "message_stop"
    assert events.count("content_block_stop") == 1, events


def test_the_responses_fixture_carries_the_id_change() -> None:
    """This capture has upstream changing an item's id between `added` and `done`.

    It is the property the whole fixture exists for, and it is easy to lose: history stores each
    event again for every client-side transform that touched it, and one of those transforms is the
    existing service's own id repair. Building from all of them yields a stream where the ids look
    stable, so an assembler keyed on the id would pass. Asserting the change here means a rebuilt
    fixture that quietly picked up the repaired copies goes red rather than green.
    """
    added: dict[str, str] = {}
    done: dict[str, str] = {}
    for chunk in upstream_chunks(RESPONSES):
        event = parse_frame(chunk)
        if event is None:
            continue
        payload = event.json()
        item = payload.get("item")
        if not isinstance(item, dict):
            continue
        index = str(payload.get("output_index", ""))
        identifier = str(cast(dict[str, Any], item).get("id", ""))
        kind = str(payload.get("type", ""))
        if kind == "response.output_item.added":
            added[index] = identifier
        elif kind == "response.output_item.done":
            done[index] = identifier

    paired = {index: (added[index], done[index]) for index in added.keys() & done.keys()}
    assert paired, "the fixture has no item that was both opened and closed"
    assert all(opened != closed for opened, closed in paired.values()), (
        f"the ids no longer change, so this fixture proves nothing about pairing: {paired}"
    )


def test_the_responses_fixture_holds_one_upstream_response() -> None:
    """One `response.created`, not one per recorded copy of it.

    A stream that opens three times is not something upstream ever sent, and it is what the naive
    read of the history timeline produces.
    """
    kinds = [
        str(event.json().get("type", ""))
        for chunk in upstream_chunks(RESPONSES)
        if (event := parse_frame(chunk)) is not None
    ]
    assert kinds.count("response.created") == 1
    assert kinds.count("response.completed") == 1


@pytest.mark.asyncio
async def test_the_assembler_pairs_the_recorded_items_despite_the_id_change() -> None:
    """Both items close, because the assembler keys on `output_index` rather than on the id.

    Counted rather than merely non-empty: with the pre-fix key this capture yields zero blocks,
    which is exactly the production symptom — HTTP 200 and no bytes.
    """
    assembler = ResponsesAssembler()
    blocks: list[CompletedBlock] = []
    for chunk in upstream_chunks(RESPONSES):
        event = parse_frame(chunk)
        if event is not None:
            blocks.extend(assembler.push(event))

    assert len(blocks) == 2, f"expected the reasoning and text items to close, got {blocks}"
    assert [block.kind for block in blocks] == ["thinking", "text"]
    assert orjson.dumps(blocks[0].payload), "a block came out unserialisable"


@pytest.mark.asyncio
async def test_the_recorded_usage_is_read_as_the_upstream_actually_reports_it() -> None:
    """What the token figures mean, checked against a capture rather than against what we believe.

    This is the one property a hand-written usage cannot establish: Responses counts the cached
    portion *inside* `input_tokens`, so reading that object with Anthropic keys reports a heavily
    cached prompt as having been sent whole. This capture is 55680 of 56919 served from cache — a
    turn that costs almost nothing, and that the log line called full price before the conversion
    went in.

    It also carries no `cache_write_tokens` key at all, which is why the converter defaults it
    rather than requiring it. A fixture written from memory would have included it.
    """
    assembler = ResponsesAssembler()
    await deliver(RESPONSES, assembler)

    assert assembler.terminal.usage == {
        "input_tokens": 1_239,
        "cache_read_input_tokens": 55_680,
        "cache_creation_input_tokens": 0,
        "output_tokens": 637,
    }
