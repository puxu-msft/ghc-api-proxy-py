"""Upstream SSE parsing and block assembly.

Two invariants under test.
A frame parses whether or not upstream puts a space after `data:`.
A block is emitted only when its closing event arrives.
"""

from collections.abc import AsyncIterator
from typing import Any

import orjson
import pytest

from app.pipeline.delivery.assembling import ReplyDialect
from app.pipeline.delivery.blocks import CompletedBlock
from app.pipeline.delivery.formats.anthropic_messages import (
    AnthropicAssembler,
    terminal_from_anthropic,
)
from app.pipeline.delivery.formats.openai_responses import ResponsesAssembler
from app.pipeline.delivery.sse_source import SseEvent, parse_frame, read_events
from app.pipeline.reply import blocks_from_anthropic


def frame(event: str, data: dict[str, Any], *, space: bool = True) -> bytes:
    separator = " " if space else ""
    return f"event: {event}\ndata:{separator}{orjson.dumps(data).decode()}\n\n".encode()


async def chunks(*payloads: bytes) -> AsyncIterator[bytes]:
    for payload in payloads:
        yield payload


# --- frame parsing ---------------------------------------------------------


def test_data_parses_with_a_space_after_the_colon() -> None:
    event = parse_frame(b'event: ping\ndata: {"a":1}')
    assert event is not None
    assert event.json() == {"a": 1}


def test_data_parses_without_a_space_after_the_colon() -> None:
    # The space is optional in the SSE spec; requiring it silently drops such a frame.
    event = parse_frame(b'event: ping\ndata:{"a":1}')
    assert event is not None
    assert event.json() == {"a": 1}


def test_multiple_data_lines_join_with_a_newline() -> None:
    event = parse_frame(b"data: one\ndata: two")
    assert event is not None
    assert event.data == "one\ntwo"


def test_comment_lines_are_ignored() -> None:
    event = parse_frame(b': keep-alive\ndata: {"a":1}')
    assert event is not None
    assert event.json() == {"a": 1}


def test_a_frame_without_data_yields_no_event() -> None:
    assert parse_frame(b"event: ping") is None


def test_malformed_json_decodes_to_an_empty_mapping() -> None:
    assert SseEvent(event="x", data="not json").json() == {}


@pytest.mark.asyncio
async def test_a_frame_split_across_chunks_still_parses() -> None:
    # Chunk boundaries are arbitrary, so a frame can arrive in pieces.
    raw = frame("content_block_stop", {"type": "content_block_stop", "index": 0})
    events = [e async for e in read_events(chunks(raw[:12], raw[12:]))]
    assert [e.event for e in events] == ["content_block_stop"]


@pytest.mark.asyncio
async def test_a_trailing_frame_without_a_separator_is_still_read() -> None:
    raw = b'event: message_stop\ndata: {"type":"message_stop"}'
    events = [e async for e in read_events(chunks(raw))]
    assert [e.event for e in events] == ["message_stop"]


# --- anthropic assembly ----------------------------------------------------


def anthropic_events() -> list[SseEvent]:
    return [
        SseEvent("content_block_start", orjson.dumps(
            {"index": 0, "content_block": {"type": "text", "text": ""}}
        ).decode()),
        SseEvent("content_block_delta", orjson.dumps(
            {"index": 0, "delta": {"type": "text_delta", "text": "hel"}}
        ).decode()),
        SseEvent("content_block_delta", orjson.dumps(
            {"index": 0, "delta": {"type": "text_delta", "text": "lo"}}
        ).decode()),
        SseEvent("content_block_stop", orjson.dumps({"index": 0}).decode()),
    ]


def test_no_block_is_emitted_before_its_stop_event() -> None:
    # The invariant the whole delivery rests on.
    assembler = AnthropicAssembler()
    events = anthropic_events()
    assert assembler.push(events[0]) == ()
    assert assembler.push(events[1]) == ()
    assert assembler.push(events[2]) == ()
    emitted = assembler.push(events[3])
    assert len(emitted) == 1


def test_deltas_are_joined_into_the_finished_block() -> None:
    assembler = AnthropicAssembler()
    blocks = [b for event in anthropic_events() for b in assembler.push(event)]
    assert blocks[0].payload["text"] == "hello"


def test_tool_use_arguments_are_decoded_at_the_stop() -> None:
    assembler = AnthropicAssembler()
    assembler.push(SseEvent("content_block_start", orjson.dumps(
        {"index": 0, "content_block": {"type": "tool_use", "name": "Read", "input": {}}}
    ).decode()))
    for piece in ('{"pa', 'th":"/tmp/x"}'):
        assembler.push(SseEvent("content_block_delta", orjson.dumps(
            {"index": 0, "delta": {"type": "input_json_delta", "partial_json": piece}}
        ).decode()))
    blocks = assembler.push(SseEvent("content_block_stop", orjson.dumps({"index": 0}).decode()))
    assert blocks[0].payload["input"] == {"path": "/tmp/x"}


def test_signature_delta_lands_on_the_thinking_block() -> None:
    assembler = AnthropicAssembler()
    assembler.push(SseEvent("content_block_start", orjson.dumps(
        {"index": 0, "content_block": {"type": "thinking", "thinking": ""}}
    ).decode()))
    assembler.push(SseEvent("content_block_delta", orjson.dumps(
        {"index": 0, "delta": {"type": "signature_delta", "signature": "sig"}}
    ).decode()))
    blocks = assembler.push(SseEvent("content_block_stop", orjson.dumps({"index": 0}).decode()))
    assert blocks[0].payload["signature"] == "sig"


def test_terminal_carries_the_stop_reason_and_usage() -> None:
    assembler = AnthropicAssembler()
    assembler.push(SseEvent("message_delta", orjson.dumps(
        {"delta": {"stop_reason": "max_tokens"}, "usage": {"output_tokens": 9}}
    ).decode()))
    assembler.push(SseEvent("message_stop", orjson.dumps({}).decode()))
    assert assembler.terminal.stop_reason == "max_tokens"
    assert assembler.terminal.usage == {"output_tokens": 9}
    assert assembler.terminal.seen is True


def test_interleaved_blocks_close_independently() -> None:
    assembler = AnthropicAssembler()
    for index in (0, 1):
        assembler.push(SseEvent("content_block_start", orjson.dumps(
            {"index": index, "content_block": {"type": "text", "text": ""}}
        ).decode()))
    assembler.push(SseEvent("content_block_delta", orjson.dumps(
        {"index": 1, "delta": {"type": "text_delta", "text": "second"}}
    ).decode()))
    assembler.push(SseEvent("content_block_delta", orjson.dumps(
        {"index": 0, "delta": {"type": "text_delta", "text": "first"}}
    ).decode()))
    # Block 1 finishes first even though it opened second.
    emitted = assembler.push(SseEvent("content_block_stop", orjson.dumps({"index": 1}).decode()))
    assert emitted[0].payload["text"] == "second"
    assert assembler.push(SseEvent("content_block_stop", orjson.dumps({"index": 0}).decode()))[
        0
    ].payload["text"] == "first"


# --- responses assembly ----------------------------------------------------


def test_responses_item_completes_only_on_done() -> None:
    assembler = ResponsesAssembler()
    assembler.push(SseEvent("response.output_item.added", orjson.dumps(
        {"item": {"id": "i1", "type": "message"}}
    ).decode()))
    assert assembler.push(SseEvent("response.output_text.delta", orjson.dumps(
        {"item_id": "i1", "delta": "partial"}
    ).decode())) == ()
    blocks = assembler.push(SseEvent("response.output_item.done", orjson.dumps(
        {"item": {"id": "i1", "type": "message"}}
    ).decode()))
    assert blocks[0].payload == {"type": "text", "text": "partial"}


def test_responses_function_call_becomes_a_tool_use_block() -> None:
    assembler = ResponsesAssembler()
    assembler.push(SseEvent("response.output_item.added", orjson.dumps(
        {"item": {"id": "i1", "type": "function_call", "call_id": "c1", "name": "Read"}}
    ).decode()))
    assembler.push(SseEvent("response.function_call_arguments.delta", orjson.dumps(
        {"item_id": "i1", "delta": '{"path":"/x"}'}
    ).decode()))
    blocks = assembler.push(SseEvent("response.output_item.done", orjson.dumps(
        {"item": {"id": "i1", "type": "function_call", "call_id": "c1", "name": "Read"}}
    ).decode()))
    assert blocks[0].kind == "tool_use"
    assert blocks[0].payload["input"] == {"path": "/x"}
    assert blocks[0].payload["id"] == "c1"


def test_responses_incomplete_maps_to_max_tokens() -> None:
    # `.dev/docs/anthropic-responses-bridge/spec.md` fixes this direction.
    assembler = ResponsesAssembler()
    assembler.push(SseEvent("response.incomplete", orjson.dumps(
        {"response": {"incomplete_details": {"reason": "max_output_tokens"}}}
    ).decode()))
    assert assembler.terminal.stop_reason == "max_tokens"


def test_any_other_incomplete_reason_reaches_the_client_in_upstream_s_own_words() -> None:
    """The output-token limit is the only reason with an Anthropic spelling, so it is the only one translated.

    Every other reason used to become `end_turn`, which told the client a turn upstream had cut short was one it had finished. `.dev/docs/anthropic-responses-bridge/spec.md` forbids exactly that: a content filter or an unknown reason must keep the reason as a fact rather than be flattened into a clean ending.
    """
    assembler = ResponsesAssembler()
    assembler.push(SseEvent("response.incomplete", orjson.dumps(
        {"response": {"incomplete_details": {"reason": "content_filter"}}}
    ).decode()))
    assert assembler.terminal.stop_reason == "content_filter"


def test_an_incomplete_response_that_gives_no_reason_still_does_not_read_as_finished() -> None:
    """Upstream said the response is incomplete and did not say why, which is not the same as ending cleanly.

    An empty reason cannot be left empty here: `stream_delivery` fills an empty one with `end_turn`, which is right for a stream that finished without naming a reason and wrong for this. `incomplete` is upstream's own word — the event is `response.incomplete` and the response carries `status: "incomplete"` — so nothing is invented to say it.
    """
    assembler = ResponsesAssembler()
    assembler.push(SseEvent("response.incomplete", orjson.dumps({"response": {}}).decode()))
    assert assembler.terminal.stop_reason == "incomplete"


def test_responses_tool_call_sets_the_tool_use_stop_reason() -> None:
    assembler = ResponsesAssembler()
    assembler.push(SseEvent("response.output_item.added", orjson.dumps(
        {"item": {"id": "i1", "type": "function_call", "call_id": "c", "name": "Read"}}
    ).decode()))
    assembler.push(SseEvent("response.output_item.done", orjson.dumps(
        {"item": {"id": "i1", "type": "function_call", "call_id": "c", "name": "Read"}}
    ).decode()))
    assembler.push(SseEvent("response.completed", orjson.dumps({"response": {}}).decode()))
    assert assembler.terminal.stop_reason == "tool_use"


def test_malformed_tool_arguments_are_kept_rather_than_dropped() -> None:
    assembler = ResponsesAssembler()
    assembler.push(SseEvent("response.output_item.added", orjson.dumps(
        {"item": {"id": "i1", "type": "function_call", "call_id": "c", "name": "Read"}}
    ).decode()))
    assembler.push(SseEvent("response.function_call_arguments.delta", orjson.dumps(
        {"item_id": "i1", "delta": "{not json"}
    ).decode()))
    blocks = assembler.push(SseEvent("response.output_item.done", orjson.dumps(
        {"item": {"id": "i1", "type": "function_call", "call_id": "c", "name": "Read"}}
    ).decode()))
    assert blocks[0].payload["input"] == {"__raw": "{not json"}


# --- one summary, two ways in ----------------------------------------------


def test_a_reply_summarises_the_same_whether_it_streamed_or_arrived_whole() -> None:
    """The buffered path used to answer this question with its own code.

    Both paths feed one console line, and while each classified blocks for itself the two descriptions of the same reply were free to drift — a fix to one leaving the other quietly wrong. Asserting them equal, rather than asserting each against a literal, is what makes that drift a failure rather than a discrepancy nobody compares.
    """
    content: list[dict[str, Any]] = [
        {"type": "thinking", "thinking": "let me work this out", "signature": "sig-a"},
        # Sealed reasoning: same cost, nothing readable. The kinds have to be told apart identically on both paths.
        {"type": "thinking", "thinking": "", "signature": "sig-b"},
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {}},
        {"type": "text", "text": "done"},
    ]
    body = {"content": content, "stop_reason": "tool_use", "usage": {"output_tokens": 12}}

    streamed = AnthropicAssembler()
    for index, block in enumerate(content):
        opening = {key: value for key, value in block.items() if key != "thinking"}
        streamed.push(SseEvent("content_block_start", orjson.dumps(
            {"index": index, "content_block": opening}
        ).decode()))
        if block["type"] == "thinking" and block["thinking"]:
            streamed.push(SseEvent("content_block_delta", orjson.dumps(
                {"index": index, "delta": {"type": "thinking_delta", "thinking": block["thinking"]}}
            ).decode()))
        streamed.push(SseEvent("content_block_stop", orjson.dumps({"index": index}).decode()))
    streamed.push(SseEvent("message_delta", orjson.dumps(
        {"delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 12}}
    ).decode()))
    streamed.push(SseEvent("message_stop", orjson.dumps({}).decode()))

    buffered = terminal_from_anthropic(body, blocks_from_anthropic(body))

    assert buffered.tools == streamed.terminal.tools == ["Bash", "Bash"]
    assert buffered.thinking == streamed.terminal.thinking == ["txt", "enc"]
    assert buffered.stop_reason == streamed.terminal.stop_reason == "tool_use"
    assert buffered.usage == streamed.terminal.usage == {"output_tokens": 12}
    assert buffered.seen is streamed.terminal.seen is True


def test_a_stream_cut_off_before_its_ending_still_says_what_it_did_produce() -> None:
    """What upstream never said, and what it did — two facts, not one.

    The console line used to be gated on `seen`, so a stream that stopped mid-turn reported nothing at all: no tokens, no reason, no reasoning, no tools. But the blocks that closed *did* close, and the record already held them. Only the ending was ever unknown, and only the ending should be missing.

    `stop_reason` empty is the load-bearing half. It used to default to `end_turn`, which made "upstream said the turn ended cleanly" and "upstream never said anything" the same value — and nothing downstream of this record could tell them apart.
    """
    streamed = AnthropicAssembler()
    streamed.push(SseEvent("content_block_start", orjson.dumps(
        {"index": 0, "content_block": {"type": "thinking", "thinking": ""}}
    ).decode()))
    streamed.push(SseEvent("content_block_delta", orjson.dumps(
        {"index": 0, "delta": {"type": "thinking_delta", "thinking": "weighing it up"}}
    ).decode()))
    streamed.push(SseEvent("content_block_stop", orjson.dumps({"index": 0}).decode()))
    streamed.push(SseEvent("content_block_start", orjson.dumps(
        {"index": 1, "content_block": {"type": "tool_use", "name": "Bash", "id": "toolu_1"}}
    ).decode()))
    streamed.push(SseEvent("content_block_stop", orjson.dumps({"index": 1}).decode()))
    # And then upstream stopped. No `message_delta`, no `message_stop`.

    assert streamed.terminal.seen is False
    assert streamed.terminal.stop_reason == "", "an ending nobody reported must not read as one that was"
    assert streamed.terminal.usage == {}
    assert streamed.terminal.thinking == ["txt"]
    assert streamed.terminal.tools == ["Bash"]


def test_each_assembler_says_whose_reply_it_assembled() -> None:
    """The streaming path's half of the wording decision.

    An assembler is picked per upstream and can only ever describe that one, so the dialect belongs to the record it builds rather than being handed to the console line separately — which would leave two places able to disagree about who answered.
    """
    assert AnthropicAssembler().terminal.dialect is ReplyDialect.ANTHROPIC
    assert ResponsesAssembler().terminal.dialect is ReplyDialect.RESPONSES
    # A buffered reply has to be told, because by the time it is read back it looks Anthropic-shaped whatever answered.
    assert terminal_from_anthropic({}, (), dialect=ReplyDialect.RESPONSES).dialect is ReplyDialect.RESPONSES


def test_responses_token_counts_are_recorded_in_the_keys_every_reader_expects() -> None:
    """The reported gap: a translated stream's line showed one input figure and no cache at all.

    `Terminal.usage` is read as Anthropic reports it, and a Responses usage read that way is not merely missing the cache fields — its `input_tokens` is the total *including* what came from cache, so a 97%-cached turn was being reported as having sent all of it fresh. The conversion is the one the buffered path already does.
    """
    assembler = ResponsesAssembler()
    assembler.push(SseEvent("response.completed", orjson.dumps({
        "response": {"usage": {
            "input_tokens": 138_500,
            "input_tokens_details": {"cached_tokens": 135_000},
            "output_tokens": 2_700,
            "total_tokens": 141_200,
        }}
    }).decode()))
    assert assembler.terminal.usage == {
        # 138_500 total less the 135_000 that came from cache: what was actually sent fresh.
        "input_tokens": 3_500,
        "cache_read_input_tokens": 135_000,
        "cache_creation_input_tokens": 0,
        "output_tokens": 2_700,
    }


def test_a_malformed_usage_costs_the_counts_and_not_the_response() -> None:
    # This runs on the terminal event of a stream whose blocks have already gone out. Raising here would trade a delivered reply for a log field nobody is waiting on.
    assembler = ResponsesAssembler()
    assembler.push(SseEvent("response.completed", orjson.dumps(
        {"response": {"usage": {"input_tokens": "lots"}}}
    ).decode()))
    assert assembler.terminal.usage == {}
    assert assembler.terminal.seen is True


def test_a_search_that_closes_without_ever_opening_is_still_delivered() -> None:
    """A `web_search_call` is whole on `done`: it has no deltas and nothing to accumulate, so the `added` it may skip carried nothing the close needs.

    Refusing to close it would throw away a search that actually ran, and throw it away silently — the same regression is on record in the reference project, where the item vanished with no observation of any kind. The cost of tolerating the shape is nothing; the cost of not tolerating it is the turn's search.
    """
    assembler = ResponsesAssembler()
    blocks = assembler.push(
        SseEvent(
            "response.output_item.done",
            orjson.dumps(
                {
                    "output_index": 0,
                    "item": {
                        "type": "web_search_call",
                        "id": "z" * 416,
                        "status": "completed",
                        "action": {"type": "search", "query": "orphan query"},
                    },
                }
            ).decode(),
        )
    )
    assert [block.payload["text"] for block in blocks] == ["[web_search] orphan query"]


def test_an_ordinary_item_that_closes_without_opening_is_still_ignored() -> None:
    """The control. Tolerating the whole-item shape is specific to the one item type that arrives that way — widening it would make every unpaired close synthesise a block out of nothing."""
    assembler = ResponsesAssembler()
    assert (
        assembler.push(
            SseEvent(
                "response.output_item.done",
                orjson.dumps(
                    {"output_index": 0, "item": {"type": "message", "role": "assistant"}}
                ).decode(),
            )
        )
        == ()
    )


def _responses_item(assembler: ResponsesAssembler, index: int, item: dict[str, object]) -> tuple[CompletedBlock, ...]:
    """Open and close one Responses output item, returning whatever closing it produced."""
    added = {"output_index": index, "item": {k: v for k, v in item.items() if k != "status"}}
    assembler.push(SseEvent("response.output_item.added", orjson.dumps(added).decode()))
    return assembler.push(
        SseEvent("response.output_item.done", orjson.dumps({"output_index": index, "item": item}).decode())
    )


def _terminal(assembler: ResponsesAssembler, reason: str) -> tuple[CompletedBlock, ...]:
    return assembler.push(
        SseEvent(
            "response.incomplete",
            orjson.dumps({"response": {"incomplete_details": {"reason": reason}}}).decode(),
        )
    )


def test_an_item_upstream_cut_short_is_dropped_when_the_turn_will_be_handed_back() -> None:
    """Half a sentence is not what the client asked for, and the next turn produces it again — but only because there *is* a next turn.

    Upstream says so on the closing event, `status: "incomplete"` on the item it cut short. It cannot be answered there, though: at that moment this side does not yet know why the response is incomplete, and that is what decides whether anything will bring the passage back. So it is held, and answered on the terminal event.
    """
    assembler = ResponsesAssembler()
    whole = _responses_item(assembler, 0, {"type": "message", "id": "m1", "status": "completed"})
    assert len(whole) == 1

    cut = _responses_item(
        assembler,
        1,
        {"type": "function_call", "id": "fc1", "call_id": "c1", "name": "Bash", "status": "incomplete"},
    )
    assert cut == ()
    assert _terminal(assembler, "max_output_tokens") == ()
    # Not counted either: a block nobody received is not a block delivered.
    assert assembler.terminal.blocks == 1


def test_an_item_upstream_cut_short_is_given_back_when_nothing_will_hand_the_turn_over() -> None:
    """The other half of the same rule, and the reason it is one setting rather than two.

    A `content_filter` ending is not carried on by default, so dropping the passage would lose it for good — the client could not ask for it again, and the line would read as an ordinary success. Held and then released, so nothing is lost.
    """
    assembler = ResponsesAssembler()
    _responses_item(assembler, 0, {"type": "message", "id": "m1", "status": "completed"})
    assert _responses_item(assembler, 1, {"type": "message", "id": "m2", "status": "incomplete"}) == ()

    released = _terminal(assembler, "content_filter")
    assert len(released) == 1
    assert assembler.terminal.blocks == 2


def test_the_endings_that_hand_over_are_an_operator_s_to_choose() -> None:
    """Configured, so an operator who decides a filtered turn *is* worth carrying on gets the drop that goes with it."""
    assembler = ResponsesAssembler(hand_over_stop_reasons=frozenset({"content_filter"}))
    _responses_item(assembler, 0, {"type": "message", "id": "m1", "status": "completed"})
    _responses_item(assembler, 1, {"type": "message", "id": "m2", "status": "incomplete"})
    assert _terminal(assembler, "content_filter") == ()
    assert assembler.terminal.blocks == 1


def test_an_item_upstream_cut_short_is_kept_when_it_is_all_there_is() -> None:
    """The rule reverses when dropping would leave the client an empty answer: half a sentence beats nothing."""
    assembler = ResponsesAssembler()
    only = _responses_item(assembler, 0, {"type": "message", "id": "m1", "status": "incomplete"})
    assert len(only) == 1
    assert assembler.terminal.blocks == 1
    # Nothing held, so the terminal has nothing to give back.
    assert _terminal(assembler, "max_output_tokens") == ()


def test_a_whole_item_is_never_dropped_however_many_came_before() -> None:
    """The control. Without it the rule above would pass just as well if it dropped on position alone."""
    assembler = ResponsesAssembler()
    _responses_item(assembler, 0, {"type": "message", "id": "m1", "status": "completed"})
    second = _responses_item(assembler, 1, {"type": "message", "id": "m2", "status": "completed"})
    assert len(second) == 1
    assert assembler.terminal.blocks == 2


# --- upstream failure events must not pass unseen ---------------------------
#
# Neither leg acts on these yet: the client still receives the same truncation frame a torn connection produces. What is pinned here is only that they are *reported* — ruled 2026-08-22, because a path we knowingly do not handle must still be observable, or "this never happens" and "it happens and we cannot tell" stay the same observation.


def test_an_anthropic_error_event_is_reported_with_upstream_s_own_words(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assembler = AnthropicAssembler()
    payload = {"type": "error", "error": {"type": "overloaded_error", "message": "slow down"}}
    with caplog.at_level("WARNING"):
        assert assembler.push(SseEvent(event="error", data=orjson.dumps(payload).decode())) == ()

    assert "overloaded_error" in caplog.text, "upstream's own code"
    assert "slow down" in caplog.text, "and its own message"
    # The half deliberately left unimplemented: this is still not a terminal event.
    assert assembler.terminal.seen is False


@pytest.mark.parametrize(
    ("kind", "payload", "code"),
    [
        # CAPI's shape, and the one we actually expect: the words are nested under `error`.
        ("error", {"error": {"code": "rate_limited", "message": "boom"}}, "rate_limited"),
        # OpenAI's public SDK declares the same event flat. Both are read; nothing sends both.
        ("error", {"code": "server_error", "message": "boom"}, "server_error"),
        (
            "response.failed",
            {"response": {"error": {"code": "rate_limit_exceeded", "message": "boom"}}},
            "rate_limit_exceeded",
        ),
        (
            "response.cancelled",
            {"response": {"error": {"code": "cancelled", "message": "boom"}}},
            "cancelled",
        ),
    ],
)
def test_a_responses_failure_event_is_reported_with_upstream_s_own_words(
    caplog: pytest.LogCaptureFixture, kind: str, payload: dict[str, Any], code: str
) -> None:
    """Three events, three places upstream puts the words — nested under `error` for CAPI, flat for the public SDK, and under `response.error` for the other two.

    The first case is the load-bearing one: reading only the flat shape printed `code='' message=''` on the shape this upstream actually sends, which is the whole of what the line carries. `response.cancelled`'s `code` is invented — no recording of one exists — so that row pins dispatch and extraction position, not the value upstream would really use.
    """
    assembler = ResponsesAssembler()
    with caplog.at_level("WARNING"):
        assert assembler.push(SseEvent(event=kind, data=orjson.dumps(payload).decode())) == ()

    assert code in caplog.text
    assert "boom" in caplog.text
    assert assembler.terminal.seen is False


def test_a_null_code_reads_as_absent_rather_than_as_the_word_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`code` is `str | None` in the SDK's own model, so a null is an ordinary value, not a malformed one."""
    assembler = ResponsesAssembler()
    payload = {"error": {"code": None, "message": "boom"}}
    with caplog.at_level("WARNING"):
        assembler.push(SseEvent(event="error", data=orjson.dumps(payload).decode()))

    assert "None" not in caplog.text
    assert "boom" in caplog.text


def test_a_failure_event_that_says_nothing_still_gets_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The shapes above are second-hand — no cassette in this repository contains one — so reporting must not depend on upstream having filled them in."""
    assembler = ResponsesAssembler()
    with caplog.at_level("WARNING"):
        assert assembler.push(SseEvent(event="response.failed", data="{}")) == ()

    assert "response.failed" in caplog.text
