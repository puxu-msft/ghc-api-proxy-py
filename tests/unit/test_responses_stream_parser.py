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


@pytest.mark.parametrize(
    "event",
    [
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "item_id": "msg_other",
            "content_index": 0,
            "delta": "text",
        },
        _done(0, {"id": "msg_other", "type": "message", "content": []}),
    ],
)
def test_default_item_identity_rejects_mismatch(event: dict[str, object]) -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_added", "type": "message"}))

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(event)

    assert caught.value.code == "item_id_mismatch"


def test_default_item_identity_preserves_empty_event_id_as_mismatch() -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_added", "type": "message"}))

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            {
                "type": "response.output_text.delta",
                "output_index": 0,
                "item_id": "",
                "content_index": 0,
                "delta": "text",
            }
        )

    assert caught.value.code == "item_id_mismatch"


@pytest.mark.parametrize("require_stable_item_id", [True, False])
def test_missing_event_item_id_remains_allowed(
    require_stable_item_id: bool,
) -> None:
    parser = ResponsesStreamParser(
        require_stable_item_id=require_stable_item_id
    )
    parser.process(_added(0, {"id": "msg_added", "type": "message"}))

    assert parser.process(
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "content_index": 0,
            "delta": "text",
        }
    ) == ()


@pytest.mark.parametrize("require_stable_item_id", [True, False])
def test_null_event_item_id_remains_equivalent_to_missing(
    require_stable_item_id: bool,
) -> None:
    parser = ResponsesStreamParser(
        require_stable_item_id=require_stable_item_id
    )
    parser.process(_added(0, {"id": "msg_added", "type": "message"}))

    assert parser.process(
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "item_id": None,
            "content_index": 0,
            "delta": "text",
        }
    ) == ()


@pytest.mark.parametrize(
    "event",
    [
        {
            "type": "response.content_part.added",
            "output_index": 0,
            "item_id": "",
            "content_index": 0,
            "part": {"type": "output_text", "text": ""},
        },
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "item_id": "",
            "content_index": 0,
            "delta": "text",
        },
        _done(0, {"id": "", "type": "message", "content": []}),
    ],
)
def test_relaxed_item_identity_rejects_empty_present_id(
    event: dict[str, object],
) -> None:
    parser = ResponsesStreamParser(require_stable_item_id=False)
    parser.process(_added(0, {"id": "msg_added", "type": "message"}))

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(event)

    assert caught.value.code == (
        "invalid_event"
        if event["type"] == "response.output_item.done"
        else "item_id_mismatch"
    )


@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    [
        ("unknown_output_index", "unknown_output_item"),
        ("item_type", "item_type_mismatch"),
        ("function_call_id", "function_call_identity_mismatch"),
        ("function_name", "function_call_identity_mismatch"),
        ("content_index", "message_content_mismatch"),
    ],
)
def test_relaxed_item_identity_preserves_other_identity_constraints(
    scenario: str,
    expected_code: str,
) -> None:
    parser = ResponsesStreamParser(require_stable_item_id=False)
    if scenario in {"function_call_id", "function_name"}:
        parser.process(
            _added(
                0,
                {
                    "id": "fc_added",
                    "type": "function_call",
                    "call_id": "call_added",
                    "name": "weather",
                    "arguments": "",
                },
            )
        )
        event = _done(
            0,
            {
                "id": "fc_done",
                "type": "function_call",
                "call_id": (
                    "call_changed" if scenario == "function_call_id" else "call_added"
                ),
                "name": "forecast" if scenario == "function_name" else "weather",
                "arguments": "{}",
            },
        )
    else:
        parser.process(_added(0, {"id": "msg_added", "type": "message"}))
        if scenario == "unknown_output_index":
            event = {
                "type": "response.output_text.delta",
                "output_index": 1,
                "item_id": "msg_other",
                "content_index": 0,
                "delta": "text",
            }
        elif scenario == "item_type":
            event = _done(
                0,
                {
                    "id": "fc_done",
                    "type": "function_call",
                    "call_id": "call_0",
                    "name": "weather",
                    "arguments": "{}",
                },
            )
        else:
            parser.process(
                {
                    "type": "response.output_text.done",
                    "output_index": 0,
                    "item_id": "msg_text_done",
                    "content_index": 1,
                    "text": "text",
                }
            )
            event = _done(
                0,
                {
                    "id": "msg_done",
                    "type": "message",
                    "content": [{"type": "output_text", "text": "text"}],
                },
            )

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(event)

    assert caught.value.code == expected_code


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


@pytest.mark.parametrize("arguments", ["{", "[]", "null", '"value"'])
def test_function_call_rejects_arguments_that_are_not_a_json_object(
    arguments: str,
) -> None:
    parser = ResponsesStreamParser()
    item = {
        "id": "fc_bad",
        "type": "function_call",
        "call_id": "call_bad",
        "name": "weather",
        "arguments": "",
    }
    parser.process(_added(0, item))

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            {
                "type": "response.function_call_arguments.done",
                "output_index": 0,
                "item_id": "fc_bad",
                "arguments": arguments,
            }
        )

    assert caught.value.code == "invalid_tool_arguments"


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


def test_message_item_done_can_authoritatively_supply_output_text() -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_done", "type": "message", "content": []}))

    (block,) = parser.process(
        _done(
            0,
            {
                "id": "msg_done",
                "type": "message",
                "content": [{"type": "output_text", "text": "authoritative"}],
            },
        )
    )

    assert isinstance(block, CompletedBlock)
    assert block.content == TextBlock("authoritative")


def test_text_authoritative_layers_must_agree_after_block_is_emitted() -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_conflict", "type": "message", "content": []}))
    parser.process(
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_conflict",
            "content_index": 0,
            "text": "FIRST",
        }
    )

    with pytest.raises(ResponsesStreamProtocolError) as content_part_caught:
        parser.process(
            {
                "type": "response.content_part.done",
                "output_index": 0,
                "item_id": "msg_conflict",
                "content_index": 0,
                "part": {"type": "output_text", "text": "SECOND"},
            }
        )

    assert content_part_caught.value.code == "authoritative_text_mismatch"


def test_equal_text_authoritative_layers_are_accepted_without_duplicate_block() -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_equal", "type": "message", "content": []}))
    (block,) = parser.process(
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_equal",
            "content_index": 0,
            "text": "SAME",
        }
    )

    assert isinstance(block, CompletedBlock)
    assert parser.process(
        {
            "type": "response.content_part.done",
            "output_index": 0,
            "item_id": "msg_equal",
            "content_index": 0,
            "part": {"type": "output_text", "text": "SAME"},
        }
    ) == ()


def test_equal_text_authoritative_layers_are_accepted_in_reverse_order() -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_reverse", "type": "message", "content": []}))
    (block,) = parser.process(
        {
            "type": "response.content_part.done",
            "output_index": 0,
            "item_id": "msg_reverse",
            "content_index": 0,
            "part": {"type": "output_text", "text": "SAME"},
        }
    )

    assert isinstance(block, CompletedBlock)
    assert parser.process(
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_reverse",
            "content_index": 0,
            "text": "SAME",
        }
    ) == ()
    assert parser.process(
        _done(
            0,
            {
                "id": "msg_reverse",
                "type": "message",
                "content": [{"type": "output_text", "text": "SAME"}],
            },
        )
    ) == ()


@pytest.mark.parametrize("final_layer", ["content_part", "item"])
def test_empty_text_delta_conflicts_with_nonempty_authoritative_text(
    final_layer: str,
) -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_empty_delta", "type": "message"}))
    parser.process(
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "item_id": "msg_empty_delta",
            "content_index": 0,
            "delta": "",
        }
    )

    event = (
        {
            "type": "response.content_part.done",
            "output_index": 0,
            "item_id": "msg_empty_delta",
            "content_index": 0,
            "part": {"type": "output_text", "text": "NONEMPTY"},
        }
        if final_layer == "content_part"
        else _done(
            0,
            {
                "id": "msg_empty_delta",
                "type": "message",
                "content": [{"type": "output_text", "text": "NONEMPTY"}],
            },
        )
    )

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(event)

    assert caught.value.code == "authoritative_text_mismatch"


def test_empty_content_part_placeholder_allows_done_only_authoritative_text() -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_done_only", "type": "message"}))
    assert parser.process(
        {
            "type": "response.content_part.added",
            "output_index": 0,
            "item_id": "msg_done_only",
            "content_index": 0,
            "part": {"type": "output_text", "text": ""},
        }
    ) == ()

    (block,) = parser.process(
        {
            "type": "response.content_part.done",
            "output_index": 0,
            "item_id": "msg_done_only",
            "content_index": 0,
            "part": {"type": "output_text", "text": "DONE ONLY"},
        }
    )

    assert isinstance(block, CompletedBlock)
    assert block.content == TextBlock("DONE ONLY")


def test_item_done_rejects_conflict_with_content_part_done_text() -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_layer_conflict", "type": "message"}))
    parser.process(
        {
            "type": "response.content_part.done",
            "output_index": 0,
            "item_id": "msg_layer_conflict",
            "content_index": 0,
            "part": {"type": "output_text", "text": "FIRST"},
        }
    )

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            _done(
                0,
                {
                    "id": "msg_layer_conflict",
                    "type": "message",
                    "content": [{"type": "output_text", "text": "SECOND"}],
                },
            )
        )

    assert caught.value.code == "authoritative_text_mismatch"
    assert caught.value.event_type == "response.output_item.done"


def test_item_done_rejects_conflict_with_emitted_authoritative_text() -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_item_conflict", "type": "message"}))
    parser.process(
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_item_conflict",
            "content_index": 0,
            "text": "FIRST",
        }
    )

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            _done(
                0,
                {
                    "id": "msg_item_conflict",
                    "type": "message",
                    "content": [{"type": "output_text", "text": "THIRD"}],
                },
            )
        )

    assert caught.value.code == "authoritative_text_mismatch"


def test_terminal_response_id_must_match_created_response_id() -> None:
    parser = ResponsesStreamParser()
    assert parser.process(
        {
            "type": "response.created",
            "response": {"id": "resp_a", "status": "in_progress"},
        }
    ) == ()

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            {
                "type": "response.completed",
                "response": {"id": "resp_b", "status": "completed"},
            }
        )

    assert caught.value.code == "response_id_mismatch"


@pytest.mark.parametrize("require_stable_response_id", [True, False])
def test_terminal_response_id_is_required_after_created(
    require_stable_response_id: bool,
) -> None:
    parser = ResponsesStreamParser(
        require_stable_response_id=require_stable_response_id
    )
    parser.process(
        {
            "type": "response.created",
            "response": {"id": "resp_a", "status": "in_progress"},
        }
    )

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            {
                "type": "response.completed",
                "response": {"status": "completed"},
            }
        )

    assert caught.value.code == "invalid_event"


@pytest.mark.parametrize(
    "event_type",
    [
        "response.created",
        "response.in_progress",
        "response.completed",
        "response.incomplete",
        "response.failed",
    ],
)
def test_relaxed_response_identity_still_requires_nonempty_nested_id(
    event_type: str,
) -> None:
    parser = ResponsesStreamParser(require_stable_response_id=False)

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process({"type": event_type, "response": {"id": ""}})

    assert caught.value.code == "invalid_event"
    assert caught.value.event_type == event_type


def test_relaxed_response_identity_preserves_error_identity_validation() -> None:
    parser = ResponsesStreamParser(require_stable_response_id=False)
    parser.process(
        {
            "type": "response.created",
            "response": {"id": "resp_a", "status": "in_progress"},
        }
    )

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            {
                "type": "error",
                "response": {"id": "resp_b"},
                "code": "server_error",
            }
        )

    assert caught.value.code == "response_id_mismatch"
    assert caught.value.event_type == "error"


def test_unknown_message_content_part_is_a_typed_failure() -> None:
    parser = ResponsesStreamParser()
    parser.process(_added(0, {"id": "msg_future", "type": "message", "content": []}))

    with pytest.raises(ResponsesStreamProtocolError) as caught:
        parser.process(
            _done(
                0,
                {
                    "id": "msg_future",
                    "type": "message",
                    "content": [{"type": "future_part", "value": "lost"}],
                },
            )
        )

    assert caught.value.code == "unsupported_content_part"


def test_completed_response_with_only_empty_message_sources_is_incomplete() -> None:
    parser = ResponsesStreamParser()
    empty: dict[str, object] = {"id": "msg_empty", "type": "message", "content": []}
    parser.process(_added(0, empty))
    assert parser.process(_done(0, empty)) == ()

    (terminal,) = parser.process(
        {
            "type": "response.completed",
            "response": {"id": "resp_empty", "status": "completed"},
        }
    )

    assert terminal == ResponsesTerminal(
        "incomplete",
        "resp_empty",
        "completed",
        "empty_response_content",
        "response completed without content",
        (),
    )


def test_incomplete_terminal_exposes_max_output_tokens_reason() -> None:
    parser = ResponsesStreamParser()

    (terminal,) = parser.process(
        {
            "type": "response.incomplete",
            "response": {
                "id": "resp_limited",
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
            },
        }
    )

    assert isinstance(terminal, ResponsesTerminal)
    assert terminal.kind == "incomplete"
    assert terminal.error_code == "max_output_tokens"


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