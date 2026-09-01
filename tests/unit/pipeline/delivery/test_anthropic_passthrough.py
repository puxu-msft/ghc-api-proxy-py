"""The `anthropic-messages` vocabulary on the direct-leg passthrough engine.

The engine itself is exercised in `test_responses_passthrough.py`; this module tests only what the Anthropic vocabulary answers differently, and the two structural differences that make a shared engine worth checking twice.
"""

import orjson

from app.pipeline.delivery.formats.anthropic_messages import AnthropicFramer
from app.pipeline.delivery.formats.anthropic_messages_passthrough import (
    ANTHROPIC_DIALECT,
    anthropic_passthrough_assembler,
    requires_client_action,
)
from app.pipeline.delivery.passthrough import PassthroughAssembler, PassthroughFramer, RawEventBatch
from app.pipeline.delivery.sse_source import SseEvent, parse_frame


def event(name: str, **payload: object) -> SseEvent:
    return SseEvent(event=name, data=orjson.dumps(payload).decode())


def drain(assembler: PassthroughAssembler, events: list[SseEvent]) -> list[SseEvent]:
    out: list[SseEvent] = []
    for one in events:
        for batch in assembler.push(one):
            out.extend(batch.events)
    return out


def test_a_content_block_kind_nothing_here_knows_reaches_the_client_intact() -> None:
    """The reason this leg is in scope at all, and it is not a hypothetical one.

    `claude-sonnet-5` does not support the Responses API, so Claude models can only be served direct — and this leg runs the same round trip issues #1 through #3 landed on, where `AnthropicFramer` refuses a block kind it has no shape for. Nothing here recognises kinds, so a 2027 block type is carried without anything having to know it.

    Asserted on the released events being the input events, identically and in order. A weaker assertion — that *something* came out — would pass on an implementation that dropped the deltas and kept the envelope.
    """
    sent = [
        event("message_start", message={"id": "msg_1"}),
        event("content_block_start", index=0, content_block={"type": "some_2027_block"}),
        event("content_block_delta", index=0, delta={"type": "some_2027_delta", "payload": "x"}),
        event("content_block_stop", index=0),
        event("message_delta", delta={"stop_reason": "end_turn"}, usage={"output_tokens": 3}),
        event("message_stop"),
    ]

    assert drain(anthropic_passthrough_assembler(), sent) == sent


def test_events_are_grouped_by_index_not_by_the_responses_field() -> None:
    """The one-line difference that would otherwise make every event unattributable.

    This dialect keys on `index`; the Responses one keys on `output_index`. Reading the wrong field would put every content-block event into "cannot attribute", where §4 holds it to the terminal — so the client would receive one enormous batch at the end instead of block-level delivery, and the assembler would report a permanently open item.
    """
    assembler = anthropic_passthrough_assembler()
    assembler.push(event("message_start", message={"id": "msg_1"}))
    assembler.push(event("content_block_start", index=0, content_block={"type": "text"}))

    assert assembler.cut_mid_block is True
    assert assembler.unattributed == ()

    released = assembler.push(event("content_block_stop", index=0))

    assert len(released) == 1
    assert [e.event for e in released[0].events] == [
        "message_start",
        "content_block_start",
        "content_block_stop",
    ]


def test_message_delta_carries_the_stop_reason_without_ending_the_response() -> None:
    """This dialect splits its ending in two, and only the second half releases the hold.

    `message_delta` states the stop reason and the usage; `message_stop` closes. If `message_delta` were treated as a terminal, a prefix containing nothing but it would be delivered on its own — which §4 forbids, because the client would then have seen a native event of this attempt and §5 would call the attempt committed.

    Both halves asserted: the facts land, and nothing goes out until the closing event.
    """
    assembler = anthropic_passthrough_assembler()
    assembler.push(event("message_start", message={"id": "msg_1"}))

    held = assembler.push(
        event("message_delta", delta={"stop_reason": "max_tokens"}, usage={"output_tokens": 9})
    )

    assert held == ()
    assert assembler.terminal.stop_reason == "max_tokens"
    assert assembler.terminal.usage == {"output_tokens": 9}
    assert assembler.terminal.seen is False

    released = assembler.push(event("message_stop"))

    assert assembler.terminal.seen is True
    assert [e.event for e in released[0].events] == ["message_start", "message_delta", "message_stop"]


def test_only_a_tool_use_block_asks_the_client_for_anything() -> None:
    """One line rather than §7.1's whole section, because this dialect has no conditional field.

    The pair matters: if everything answered `True`, `until-tool-use` would release on the first block and mean nothing.
    """
    assert requires_client_action({"type": "tool_use"}) is True
    assert requires_client_action({"type": "text"}) is False
    assert requires_client_action({"type": "thinking"}) is False


def test_a_batch_finds_the_block_type_on_the_opening_event() -> None:
    """Where this dialect puts the deciding field, and why the predicate cannot read the closing one.

    `content_block_stop` carries only an index. A batch predicate that asked only the closing event would answer `False` for every Anthropic tool call, and `until-tool-use` would never release on this leg.
    """
    batch = RawEventBatch(
        events=(
            event("content_block_start", index=0, content_block={"type": "tool_use", "name": "f"}),
            event("content_block_stop", index=0),
        ),
        dialect=ANTHROPIC_DIALECT,
    )

    assert batch.requires_client_action is True


def test_an_upstream_error_event_is_carried_with_its_payload() -> None:
    """What makes verbatim replay possible: the record keeps upstream's payload as text."""
    assembler = anthropic_passthrough_assembler()
    raw = '{"type":"error","error":{"type":"overloaded_error","message":"busy"}}'

    assembler.push(SseEvent(event="error", data=raw))

    failure = assembler.failure
    assert failure is not None
    assert failure.raw_data == raw
    assert failure.info.code == "overloaded_error"


def test_the_framer_delegates_this_dialects_own_frames() -> None:
    """The keep-alive and the error frame are this side's inventions, and this dialect already spells them."""
    delegate = AnthropicFramer(message_id="msg_1", model="m")
    framer = PassthroughFramer(delegate=delegate)

    assert framer.preamble() == ()
    assert framer.keepalive() == delegate.keepalive()


def test_a_batch_goes_out_as_the_frames_it_arrived_as() -> None:
    """Byte fidelity on this leg too: the event name and the payload text, only the SSE wrapper rebuilt."""
    batch = RawEventBatch(
        events=(
            SseEvent(event="content_block_delta", data='{"index":0,"delta":{"text":"hi"}}'),
            SseEvent(event="x.unknown", data="first\nsecond"),
        ),
        dialect=ANTHROPIC_DIALECT,
    )

    wire = b"".join(PassthroughFramer(delegate=AnthropicFramer(message_id="m", model="m")).block(batch))
    frames = [parse_frame(f) for f in wire.split(b"\n\n") if f.strip()]

    assert [(f.event, f.data) for f in frames if f is not None] == [
        ("content_block_delta", '{"index":0,"delta":{"text":"hi"}}'),
        ("x.unknown", "first\nsecond"),
    ]
