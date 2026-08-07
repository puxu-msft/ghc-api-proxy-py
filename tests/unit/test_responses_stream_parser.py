from collections.abc import Mapping
from dataclasses import FrozenInstanceError

import pytest

from app.anthropic.thinking.responses_reasoning import (
    PROJECT_SYNTHETIC_REASONING_SIGNATURE,
)
from app.openai.responses_stream_parser import (
    BlockIdentity,
    CompletedBlock,
    FunctionCallBlock,
    ReasoningBlock,
    ResponsesStreamParser,
    ResponsesStreamProtocolError,
    ResponsesTerminal,
    SourceOpened,
    TextBlock,
    UnsupportedResponsesEvent,
)
from app.protocols.responses_anthropic import (
    ResponseConversionError,
    convert_responses_response_to_anthropic,
)


def _added(output_index: int, item: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "response.output_item.added",
        "output_index": output_index,
        "item": item,
    }


def _done(output_index: int, item: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "response.output_item.done",
        "output_index": output_index,
        "item": item,
    }


def test_text_block_is_emitted_only_after_authoritative_done() -> None:
    parser = ResponsesStreamParser()
    assert parser.process(_added(0, {"id": "msg_0", "type": "message"})) == (
        SourceOpened(BlockIdentity(0, "msg_0", None), source_order=0),
    )
    assert parser.process(
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "item_id": "msg_0",
            "content_index": 2,
            "delta": "hel",
        }
    ) == ()

    (block,) = parser.process(
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_0",
            "content_index": 2,
            "text": "hel",
        }
    )

    assert isinstance(block, CompletedBlock)
    assert block == CompletedBlock(
        identity=block.identity,
        content=TextBlock("hel"),
        first_observed_order=0,
        completion_order=0,
    )
    assert block.identity.output_index == 0
    assert block.identity.item_id == "msg_0"
    assert block.identity.content_index == 2
    with pytest.raises(FrozenInstanceError):
        block.completion_order = 2  # type: ignore[misc]


def test_function_call_waits_for_arguments_done_and_item_done() -> None:
    parser = ResponsesStreamParser()
    item = {
        "id": "fc_0",
        "type": "function_call",
        "call_id": "call_0",
        "name": "weather",
        "arguments": "",
    }
    assert parser.process(_added(0, item)) == (
        SourceOpened(BlockIdentity(0, "fc_0", None), source_order=0),
    )
    assert parser.process(
        {
            "type": "response.function_call_arguments.delta",
            "output_index": 0,
            "item_id": "fc_0",
            "delta": '{"city":',
        }
    ) == ()
    assert parser.process(
        {
            "type": "response.function_call_arguments.delta",
            "output_index": 0,
            "item_id": "fc_0",
            "delta": '"Paris"}',
        }
    ) == ()
    assert parser.process(
        {
            "type": "response.function_call_arguments.done",
            "output_index": 0,
            "item_id": "fc_0",
            "arguments": '{"city":"Paris"}',
        }
    ) == ()

    (block,) = parser.process(
        _done(0, {**item, "arguments": '{"city":"Paris"}'})
    )

    assert isinstance(block, CompletedBlock)
    assert block.content == FunctionCallBlock(
        call_id="call_0", name="weather", arguments='{"city":"Paris"}'
    )


def test_function_call_accepts_authoritative_arguments_without_deltas() -> None:
    parser = ResponsesStreamParser()
    item = {
        "id": "fc_0",
        "type": "function_call",
        "call_id": "call_0",
        "name": "weather",
        "arguments": "",
    }
    parser.process(_added(0, item))
    assert parser.process(
        {
            "type": "response.function_call_arguments.done",
            "output_index": 0,
            "item_id": "fc_0",
            "arguments": '{"city":"Paris"}',
        }
    ) == ()

    (block,) = parser.process(_done(0, {**item, "arguments": '{"city":"Paris"}'}))

    assert isinstance(block, CompletedBlock)
    assert block.content == FunctionCallBlock(
        call_id="call_0", name="weather", arguments='{"city":"Paris"}'
    )


def test_function_call_accepts_arguments_only_from_item_done() -> None:
    parser = ResponsesStreamParser()
    item = {
        "id": "fc_0",
        "type": "function_call",
        "call_id": "call_0",
        "name": "weather",
        "arguments": "",
    }
    parser.process(_added(0, item))

    (block,) = parser.process(_done(0, {**item, "arguments": '{"city":"Paris"}'}))

    assert isinstance(block, CompletedBlock)
    assert block.content == FunctionCallBlock(
        call_id="call_0", name="weather", arguments='{"city":"Paris"}'
    )


def test_function_call_rejects_delta_and_authoritative_arguments_conflict() -> None:
    parser = ResponsesStreamParser()
    parser.process(
        _added(
            0,
            {
                "id": "fc_0",
                "type": "function_call",
                "call_id": "call_0",
                "name": "weather",
                "arguments": "",
            },
        )
    )
    parser.process(
        {
            "type": "response.function_call_arguments.delta",
            "output_index": 0,
            "item_id": "fc_0",
            "delta": '{"city":"Paris"}',
        }
    )

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            {
                "type": "response.function_call_arguments.done",
                "output_index": 0,
                "item_id": "fc_0",
                "arguments": '{"city":"London"}',
            }
        )

    assert caught.value.code == "authoritative_arguments_mismatch"
    assert caught.value.event_type == "response.function_call_arguments.done"


def test_reasoning_uses_item_done_for_authoritative_summary_and_ciphertext() -> None:
    parser = ResponsesStreamParser()
    assert parser.process(
        _added(
            0,
            {
                "id": "rs_0",
                "type": "reasoning",
                "summary": [],
                "encrypted_content": "mid-state",
            },
        )
    ) == (SourceOpened(BlockIdentity(0, "rs_0", None), source_order=0),)
    assert parser.process(
        {
            "type": "response.reasoning_summary_text.delta",
            "output_index": 0,
            "item_id": "rs_0",
            "summary_index": 0,
            "delta": "visible",
        }
    ) == ()
    assert parser.process(
        {
            "type": "response.reasoning_summary_text.done",
            "output_index": 0,
            "item_id": "rs_0",
            "summary_index": 0,
            "text": "visible",
        }
    ) == ()

    (block,) = parser.process(
        _done(
            0,
            {
                "id": "rs_0",
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "visible"}],
                "encrypted_content": "authoritative",
            },
        )
    )

    assert isinstance(block, CompletedBlock)
    assert block.content == ReasoningBlock("visible", "authoritative")


def test_reasoning_accepts_authoritative_item_done_without_summary_events() -> None:
    parser = ResponsesStreamParser()
    parser.process(
        _added(
            0,
            {
                "id": "rs_0",
                "type": "reasoning",
                "summary": [],
                "encrypted_content": None,
            },
        )
    )

    (block,) = parser.process(
        _done(
            0,
            {
                "id": "rs_0",
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "visible"}],
                "encrypted_content": None,
            },
        )
    )

    assert isinstance(block, CompletedBlock)
    assert block.content == ReasoningBlock("visible", None)


def test_unknown_reasoning_summary_part_is_rejected_by_stream_and_nonstream() -> None:
    item = {
        "id": "rs_future",
        "type": "reasoning",
        "summary": [{"type": "future_summary", "text": "accepted?"}],
        "encrypted_content": None,
    }

    with pytest.raises(ResponseConversionError) as nonstream_caught:
        convert_responses_response_to_anthropic(
            {
                "id": "resp_future",
                "model": "gpt-test",
                "status": "completed",
                "output": [item],
            }
        )

    assert nonstream_caught.value.code == "invalid_reasoning"
    assert nonstream_caught.value.field_path == "output[0]"

    parser = ResponsesStreamParser()
    parser.process(_added(0, item))
    with pytest.raises(ResponsesStreamProtocolError) as stream_caught:
        parser.process(_done(0, item))

    assert stream_caught.value.code == "invalid_reasoning"
    assert stream_caught.value.event_type == "response.output_item.done"


@pytest.mark.parametrize("encrypted_content", [pytest.param(None, id="absent"), ""])
def test_empty_reasoning_has_stream_nonstream_semantic_parity(
    encrypted_content: str | None,
) -> None:
    item: dict[str, object] = {
        "id": "rs_empty",
        "type": "reasoning",
        "summary": [],
    }
    if encrypted_content is not None:
        item["encrypted_content"] = encrypted_content
    nonstream = convert_responses_response_to_anthropic(
        {
            "id": "resp_empty",
            "model": "gpt-test",
            "status": "completed",
            "output": [item],
        }
    )

    parser = ResponsesStreamParser()
    parser.process(_added(0, item))
    (stream_block,) = parser.process(_done(0, item))

    assert isinstance(stream_block, CompletedBlock)
    assert stream_block.content == ReasoningBlock("", None)
    assert [
        block.model_dump(exclude_none=True) for block in nonstream.message.content
    ] == [
        {
            "type": "thinking",
            "thinking": "",
            "signature": PROJECT_SYNTHETIC_REASONING_SIGNATURE,
        }
    ]


def test_reasoning_rejects_summary_done_and_item_done_conflict() -> None:
    parser = ResponsesStreamParser()
    parser.process(
        _added(
            0,
            {
                "id": "rs_0",
                "type": "reasoning",
                "summary": [],
                "encrypted_content": None,
            },
        )
    )
    parser.process(
        {
            "type": "response.reasoning_summary_text.delta",
            "output_index": 0,
            "item_id": "rs_0",
            "summary_index": 0,
            "delta": "first",
        }
    )
    parser.process(
        {
            "type": "response.reasoning_summary_text.done",
            "output_index": 0,
            "item_id": "rs_0",
            "summary_index": 0,
            "text": "first",
        }
    )

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            _done(
                0,
                {
                    "id": "rs_0",
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "second"}],
                    "encrypted_content": None,
                },
            )
        )

    assert caught.value.code == "authoritative_reasoning_mismatch"
    assert caught.value.event_type == "response.output_item.done"


def test_reasoning_rejects_item_done_that_changes_summary_part_boundaries() -> None:
    parser = ResponsesStreamParser()
    parser.process(
        _added(
            0,
            {
                "id": "rs_0",
                "type": "reasoning",
                "summary": [],
                "encrypted_content": None,
            },
        )
    )
    for summary_index, text in enumerate(("a", "bc")):
        parser.process(
            {
                "type": "response.reasoning_summary_text.done",
                "output_index": 0,
                "item_id": "rs_0",
                "summary_index": summary_index,
                "text": text,
            }
        )

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            _done(
                0,
                {
                    "id": "rs_0",
                    "type": "reasoning",
                    "summary": [
                        {"type": "summary_text", "text": "ab"},
                        {"type": "summary_text", "text": "c"},
                    ],
                    "encrypted_content": None,
                },
            )
        )

    assert caught.value.code == "authoritative_reasoning_mismatch"
    assert caught.value.event_type == "response.output_item.done"


def test_interleaved_items_keep_source_and_completion_order_facts() -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(3, {"id": "msg_a", "type": "message"}))
    parser.process(_added(8, {"id": "msg_b", "type": "message"}))
    parser.process(
        {
            "type": "response.output_text.delta",
            "output_index": 3,
            "item_id": "msg_a",
            "content_index": 0,
            "delta": "A",
        }
    )
    parser.process(
        {
            "type": "response.output_text.delta",
            "output_index": 8,
            "item_id": "msg_b",
            "content_index": 0,
            "delta": "B",
        }
    )

    (block_b,) = parser.process(
        {
            "type": "response.output_text.done",
            "output_index": 8,
            "item_id": "msg_b",
            "content_index": 0,
            "text": "B",
        }
    )
    (block_a,) = parser.process(
        {
            "type": "response.output_text.done",
            "output_index": 3,
            "item_id": "msg_a",
            "content_index": 0,
            "text": "A",
        }
    )

    assert isinstance(block_a, CompletedBlock)
    assert isinstance(block_b, CompletedBlock)
    assert (block_a.identity.output_index, block_b.identity.output_index) == (3, 8)
    assert (block_a.first_observed_order, block_b.first_observed_order) == (0, 1)
    assert (block_b.completion_order, block_a.completion_order) == (0, 1)


@pytest.mark.parametrize("later_kind", ["function_call", "reasoning"])
def test_later_tool_or_reasoning_cannot_hide_earlier_open_message(
    later_kind: str,
) -> None:
    parser = ResponsesStreamParser()
    message_identity = BlockIdentity(0, "msg_a", None)
    assert parser.process(_added(0, {"id": "msg_a", "type": "message"})) == (
        SourceOpened(message_identity, source_order=0),
    )

    if later_kind == "function_call":
        later_item: dict[str, object] = {
            "id": "fc_b",
            "type": "function_call",
            "call_id": "call_b",
            "name": "weather",
            "arguments": "",
        }
    else:
        later_item = {
            "id": "rs_b",
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "ciphertext",
        }
    later_identity = BlockIdentity(1, str(later_item["id"]), None)
    assert parser.process(_added(1, later_item)) == (
        SourceOpened(later_identity, source_order=1),
    )

    if later_kind == "function_call":
        assert parser.process(
            {
                "type": "response.function_call_arguments.done",
                "output_index": 1,
                "item_id": "fc_b",
                "arguments": "{}",
            }
        ) == ()
        (later_block,) = parser.process(_done(1, {**later_item, "arguments": "{}"}))
    else:
        (later_block,) = parser.process(_done(1, later_item))

    assert isinstance(later_block, CompletedBlock)
    assert later_block.first_observed_order == 1
    assert parser.open_blocks == (message_identity,)

    (message_block,) = parser.process(
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_a",
            "content_index": 0,
            "text": "A",
        }
    )
    assert isinstance(message_block, CompletedBlock)
    assert message_block.first_observed_order == 0
    assert parser.process(_done(0, {"id": "msg_a", "type": "message"})) == ()
    assert parser.open_blocks == ()


def test_completed_terminal_reports_added_only_message_as_incomplete() -> None:
    parser = ResponsesStreamParser()
    identity = BlockIdentity(0, "msg_0", None)
    assert parser.process(_added(0, {"id": "msg_0", "type": "message"})) == (
        SourceOpened(identity, source_order=0),
    )

    (terminal,) = parser.process(
        {
            "type": "response.completed",
            "response": {"id": "resp_0", "status": "completed"},
        }
    )

    assert terminal == ResponsesTerminal(
        kind="incomplete",
        response_id="resp_0",
        status="completed",
        error_code="incomplete_lifecycle",
        message="response completed with open output items",
        open_blocks=(identity,),
    )


def test_unknown_item_done_stays_typed_and_terminal_is_incomplete() -> None:
    parser = ResponsesStreamParser()
    item = {"id": "future_item", "type": "future_server_tool"}
    (unsupported_added,) = parser.process(_added(3, item))
    assert unsupported_added == UnsupportedResponsesEvent(
        event_type="response.output_item.added",
        output_index=3,
        item_id="future_item",
        content_index=None,
    )

    (unsupported_done,) = parser.process(_done(3, item))
    assert unsupported_done == UnsupportedResponsesEvent(
        event_type="response.output_item.done",
        output_index=3,
        item_id="future_item",
        content_index=None,
    )

    (terminal,) = parser.process(
        {
            "type": "response.completed",
            "response": {"id": "resp_unknown", "status": "completed"},
        }
    )
    assert terminal == ResponsesTerminal(
        kind="incomplete",
        response_id="resp_unknown",
        status="completed",
        error_code="unsupported_output_item",
        message="response contains unsupported output items",
        open_blocks=(BlockIdentity(3, "future_item", None),),
    )


def test_unknown_and_terminal_events_remain_typed() -> None:
    parser = ResponsesStreamParser()
    (unsupported,) = parser.process(
        {
            "type": "response.future.delta",
            "output_index": 4,
            "item_id": "future_0",
            "content_index": 1,
        }
    )
    assert unsupported == UnsupportedResponsesEvent(
        event_type="response.future.delta",
        output_index=4,
        item_id="future_0",
        content_index=1,
    )

    (terminal,) = parser.process(
        {
            "type": "response.completed",
            "response": {"id": "resp_0", "status": "completed"},
        }
    )
    assert terminal == ResponsesTerminal(
        kind="completed",
        response_id="resp_0",
        status="completed",
        error_code=None,
        message=None,
        open_blocks=(),
    )


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (
            {
                "type": "response.failed",
                "response": {
                    "id": "resp_failed",
                    "status": "failed",
                    "error": {"code": "server_error", "message": "failed"},
                },
            },
            ResponsesTerminal(
                "failed", "resp_failed", "failed", "server_error", "failed", ()
            ),
        ),
        (
            {"type": "error", "code": "overloaded", "message": "try later"},
            ResponsesTerminal("error", None, None, "overloaded", "try later", ()),
        ),
    ],
)
def test_failed_and_error_are_typed_terminals(
    event: dict[str, object], expected: ResponsesTerminal
) -> None:
    assert ResponsesStreamParser().process(event) == (expected,)