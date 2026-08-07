from collections.abc import Mapping

import pytest

from app.anthropic.thinking.responses_reasoning import responses_reasoning_to_anthropic
from app.protocols.responses_anthropic import (
    ResponseConversionError,
    ResponseConversionFact,
    convert_responses_response_to_anthropic,
)


def _response(
    *output: Mapping[str, object], usage: Mapping[str, object] | None = None
) -> dict[str, object]:
    response: dict[str, object] = {
        "id": "resp_123",
        "model": "gpt-test",
        "status": "completed",
        "output": list(output),
    }
    if usage is not None:
        response["usage"] = usage
    return response


def test_converts_output_text_parts_in_source_order() -> None:
    converted = convert_responses_response_to_anthropic(
        _response(
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "first"},
                    {"type": "output_text", "text": "second"},
                ],
            },
            {"type": "message", "content": [{"type": "output_text", "text": "third"}]},
        )
    )

    assert converted.message.id == "msg_HAGUmRojzlDCLGp3XE8QLxwLG9FislDW"
    assert converted.message.id.startswith("msg_")
    assert converted.message.id != converted.upstream_response_id
    assert converted.upstream_response_id == "resp_123"
    assert converted.upstream_model == "gpt-test"
    assert converted.facts == (
        ResponseConversionFact(code="response_id_transformed", field_path="id"),
    )
    assert converted.message.model == "gpt-test"
    assert converted.message.stop_reason == "end_turn"
    assert [block.model_dump(exclude_none=True) for block in converted.message.content] == [
        {"type": "text", "text": "first"},
        {"type": "text", "text": "second"},
        {"type": "text", "text": "third"},
    ]


def test_public_message_id_is_stable_and_does_not_expose_upstream_identity() -> None:
    first = convert_responses_response_to_anthropic(_response())
    second = convert_responses_response_to_anthropic(_response())
    other_response = _response()
    other_response["id"] = "resp_other"
    other = convert_responses_response_to_anthropic(other_response)

    assert first.message.id == second.message.id
    assert first.message.id != other.message.id
    assert "resp_123" not in first.message.id
    assert first.upstream_response_id == second.upstream_response_id == "resp_123"


def test_converts_function_call_and_selects_tool_use_stop_reason() -> None:
    converted = convert_responses_response_to_anthropic(
        _response(
            {
                "type": "function_call",
                "call_id": "call_123",
                "name": "weather",
                "arguments": '{"city":"Paris"}',
            }
        )
    )

    assert converted.message.stop_reason == "tool_use"
    assert converted.message.content[0].model_dump(exclude_none=True) == {
        "type": "tool_use",
        "id": "call_123",
        "name": "weather",
        "input": {"city": "Paris"},
    }


def test_preserves_reasoning_item_cardinality_order_and_encrypted_only_payload() -> None:
    first_reasoning: Mapping[str, object] = {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "first"}],
        "encrypted_content": "ENC-1",
    }
    encrypted_only: Mapping[str, object] = {
        "type": "reasoning",
        "summary": [],
        "encrypted_content": "ENC-2",
    }
    converted = convert_responses_response_to_anthropic(
        _response(
            first_reasoning,
            {"type": "message", "content": [{"type": "output_text", "text": "answer"}]},
            encrypted_only,
        )
    )

    first_blocks = responses_reasoning_to_anthropic([first_reasoning])
    encrypted_only_blocks = responses_reasoning_to_anthropic([encrypted_only])
    assert first_blocks is not None
    assert encrypted_only_blocks is not None
    assert [block.type for block in converted.message.content] == [
        "thinking",
        "text",
        "thinking",
    ]
    assert converted.message.content[0].model_dump(exclude_none=True) == first_blocks[0]
    assert converted.message.content[2].model_dump(exclude_none=True) == encrypted_only_blocks[0]


def test_maps_basic_usage_and_subtracts_cache_tokens_from_anthropic_input() -> None:
    converted = convert_responses_response_to_anthropic(
        _response(
            {"type": "message", "content": [{"type": "output_text", "text": "done"}]},
            usage={
                "input_tokens": 100,
                "output_tokens": 30,
                "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 10},
            },
        )
    )

    assert converted.message.usage is not None
    assert converted.message.usage.model_dump() == {
        "input_tokens": 70,
        "output_tokens": 30,
        "cache_creation_input_tokens": 10,
        "cache_read_input_tokens": 20,
    }


def test_rejects_unknown_output_item_explicitly() -> None:
    with pytest.raises(ResponseConversionError) as caught:
        convert_responses_response_to_anthropic(_response({"type": "future_item"}))

    assert caught.value.code == "unsupported_output_item"
    assert caught.value.field_path == "output[0].type"


def test_rejects_server_tool_item_instead_of_reviving_it() -> None:
    with pytest.raises(ResponseConversionError) as caught:
        convert_responses_response_to_anthropic(
            _response({"type": "web_search_call", "id": "ws_123"})
        )

    assert caught.value.code == "server_tool_not_supported"
    assert caught.value.field_path == "output[0]"


def test_rejects_failed_response_as_typed_error() -> None:
    response = _response()
    response["status"] = "failed"
    response["error"] = {"message": "upstream failed"}

    with pytest.raises(ResponseConversionError) as caught:
        convert_responses_response_to_anthropic(response)

    assert caught.value.code == "failed_response"
    assert caught.value.field_path == "status"