"""The Chat Completions translators: the request writer, the response reader, and
the losses each records rather than drops silently.
"""

from typing import Any

import pytest

from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.anthropic_messages import from_anthropic_messages
from app.pipeline.translation_driver.content import BlockKind, ContentBlock
from app.pipeline.translation_driver.openai_chat_completions import (
    chat_usage_to_anthropic,
    from_chat_completions_response,
    from_openai_chat_completions,
    to_openai_chat_completions,
    to_openai_chat_completions_response,
)
from app.pipeline.translation_driver.reasoning_carrier import (
    CHAT_REASONING_CONTENT,
    RESPONSES_SUMMARY_TEXT_LAYOUT,
    decode_reasoning_carrier,
)
from app.pipeline.translation_driver.registry import default_registry
from app.pipeline.translation_driver.responses import SemanticResponse
from app.pipeline.translation_driver.semantic import LossCode, TranslationRefused


def anthropic_request(body: dict[str, Any]):
    return from_anthropic_messages(body)


def test_a_minimal_anthropic_request_becomes_a_chat_body() -> None:
    request = anthropic_request(
        {
            "model": "glm-5.2",
            "max_tokens": 128,
            "messages": [{"role": "user", "content": "hello"}],
        }
    )

    body = to_openai_chat_completions(request)

    assert body["model"] == "glm-5.2"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["max_tokens"] == 128
    assert body["stream"] is False
    assert request.conversion.lossless


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "user", "content": []}],
    ],
)
def test_chat_refuses_when_translation_has_no_messages(
    messages: list[dict[str, Any]],
) -> None:
    request = anthropic_request({"model": "m", "messages": messages})

    with pytest.raises(TranslationRefused, match="messages must be non-empty") as caught:
        to_openai_chat_completions(request)

    assert caught.value.code == "messages-empty"
    assert caught.value.field_path == "messages"


def test_chat_refusal_does_not_consume_source_extensions() -> None:
    request = anthropic_request(
        {"model": "m", "messages": [], "stop_sequences": ["do not consume"]}
    )

    with pytest.raises(TranslationRefused, match="messages must be non-empty"):
        to_openai_chat_completions(request)

    assert request.extensions["stop_sequences"] == ["do not consume"]


def test_chat_refuses_empty_responses_input_using_the_source_field() -> None:
    with pytest.raises(TranslationRefused, match="input must be non-empty") as caught:
        default_registry().translate(
            {"model": "m", "input": []},
            source=WireFormat.OPENAI_RESPONSES,
            target=WireFormat.OPENAI_CHAT_COMPLETIONS,
        )

    assert caught.value.code == "input-empty"
    assert caught.value.field_path == "input"


def test_the_system_field_becomes_the_first_message() -> None:
    request = anthropic_request(
        {
            "model": "m",
            "max_tokens": 8,
            "system": [{"type": "text", "text": "be brief"}, {"type": "text", "text": "be kind"}],
            "messages": [{"role": "user", "content": "hi"}],
        }
    )

    body = to_openai_chat_completions(request)

    assert body["messages"][0] == {"role": "system", "content": "be brief\nbe kind"}


def test_tool_use_and_tool_result_round_trip_into_chat_roles() -> None:
    request = anthropic_request(
        {
            "model": "m",
            "max_tokens": 8,
            "messages": [
                {"role": "user", "content": "what is the weather"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "checking"},
                        {
                            "type": "tool_use",
                            "id": "call-1",
                            "name": "weather",
                            "input": {"city": "shenzhen"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "call-1", "content": "sunny"}
                    ],
                },
            ],
        }
    )

    body = to_openai_chat_completions(request)

    user, assistant, tool = body["messages"]
    assert user == {"role": "user", "content": "what is the weather"}
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "checking"
    assert assistant["tool_calls"] == [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "weather", "arguments": '{"city": "shenzhen"}'},
        }
    ]
    assert tool == {"role": "tool", "tool_call_id": "call-1", "content": "sunny"}
    assert request.conversion.lossless


def test_anthropic_tools_become_function_declarations() -> None:
    request = anthropic_request(
        {
            "model": "m",
            "max_tokens": 8,
            "tools": [
                {
                    "name": "weather",
                    "description": "look it up",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
            "messages": [{"role": "user", "content": "hi"}],
        }
    )

    body = to_openai_chat_completions(request)

    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "look it up",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


def test_tool_choice_spellings_map_onto_chat() -> None:
    cases = [
        ({"type": "auto"}, "auto"),
        ({"type": "any"}, "required"),
        ({"type": "none"}, "none"),
        ({"type": "tool", "name": "weather"}, {"type": "function", "function": {"name": "weather"}}),
    ]
    for anthropic_choice, chat_choice in cases:
        request = anthropic_request(
            {
                "model": "m",
                "max_tokens": 8,
                "tool_choice": anthropic_choice,
                "tools": [{"name": "weather", "input_schema": {"type": "object"}}],
                "messages": [{"role": "user", "content": "hi"}],
            }
        )

        body = to_openai_chat_completions(request)

        assert body["tool_choice"] == chat_choice, anthropic_choice


def test_disable_parallel_tool_use_becomes_parallel_tool_calls_false() -> None:
    request = anthropic_request(
        {
            "model": "m",
            "max_tokens": 8,
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
            "tools": [{"name": "weather", "input_schema": {"type": "object"}}],
            "messages": [{"role": "user", "content": "hi"}],
        }
    )

    body = to_openai_chat_completions(request)

    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is False


def test_a_responses_named_choice_and_parallel_limit_reach_chat() -> None:
    parameters = {"type": "object", "properties": {"city": {"type": "string"}}}
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hi"}],
                }
            ],
            "tools": [{"type": "function", "name": "weather", "parameters": parameters}],
            "tool_choice": {"type": "function", "name": "weather"},
            "parallel_tool_calls": False,
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_CHAT_COMPLETIONS,
    )
    assert body["tool_choice"] == {"type": "function", "function": {"name": "weather"}}
    assert body["parallel_tool_calls"] is False
    assert body["tools"][0]["function"]["parameters"] == parameters
    assert semantic.conversion.lossless


@pytest.mark.parametrize(
    "choice",
    [
        {"type": "tool", "name": "missing"},
        {"type": "tool", "name": "weather", "future_field": 1},
        {"type": "function", "name": "weather"},
    ],
)
def test_chat_refuses_unrepresentable_anthropic_choices(choice: dict[str, Any]) -> None:
    request = anthropic_request(
        {
            "model": "m",
            "messages": [],
            "tools": [{"name": "weather", "input_schema": {"type": "object"}}],
            "tool_choice": choice,
        }
    )
    with pytest.raises(TranslationRefused) as caught:
        to_openai_chat_completions(request)
    assert caught.value.code == "tool-choice-not-supported"
    assert caught.value.field_path == "tool_choice"


def test_an_error_tool_result_is_marked_and_recorded() -> None:
    request = anthropic_request(
        {
            "model": "m",
            "max_tokens": 8,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call-1",
                            "content": "boom",
                            "is_error": True,
                        }
                    ],
                }
            ],
        }
    )

    body = to_openai_chat_completions(request)

    assert body["messages"][0]["content"] == "[tool_error] boom"
    assert request.conversion.has(LossCode.SYNTHETIC_TURN_ADDED)


def test_a_structured_tool_result_flattens_with_a_loss() -> None:
    request = anthropic_request(
        {
            "model": "m",
            "max_tokens": 8,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call-1",
                            "content": [{"type": "text", "text": "the answer"}],
                        }
                    ],
                }
            ],
        }
    )

    body = to_openai_chat_completions(request)

    assert body["messages"][0]["content"] == "the answer"
    assert request.conversion.has(LossCode.TOOL_RESULT_CONTENT_FLATTENED)


def test_an_image_block_is_lost_loudly() -> None:
    request = anthropic_request(
        {
            "model": "m",
            "max_tokens": 8,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "data": "..."}},
                        {"type": "text", "text": "describe"},
                    ],
                }
            ],
        }
    )

    body = to_openai_chat_completions(request)

    assert body["messages"] == [{"role": "user", "content": "describe"}]
    assert request.conversion.has(LossCode.BLOCK_NOT_CARRIED)


def test_stop_sequences_are_claimed_from_extensions() -> None:
    request = anthropic_request(
        {
            "model": "m",
            "max_tokens": 8,
            "stop_sequences": ["END", "STOP"],
            "messages": [{"role": "user", "content": "hi"}],
        }
    )

    body = to_openai_chat_completions(request)

    assert body["stop"] == ["END", "STOP"]
    assert not request.conversion.has(LossCode.EXTENSIONS_NOT_CARRIED)


def test_unmodelled_extensions_are_recorded_rather_than_sent() -> None:
    request = anthropic_request(
        {
            "model": "m",
            "max_tokens": 8,
            "metadata": {"user_id": "u"},
            "messages": [{"role": "user", "content": "hi"}],
        }
    )

    body = to_openai_chat_completions(request)

    assert "metadata" not in body
    assert request.conversion.has(LossCode.EXTENSIONS_NOT_CARRIED)


def test_a_reasoning_intent_is_not_sent_and_is_recorded() -> None:
    request = anthropic_request(
        {
            "model": "m",
            "max_tokens": 8,
            "thinking": {"type": "enabled", "budget_tokens": 2000},
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    assert request.thinking_effort is not None  # the reader read the thinking field

    body = to_openai_chat_completions(request)

    assert "reasoning" not in body
    assert "reasoning_effort" not in body
    assert request.conversion.has(LossCode.REASONING_INTENT_NOT_CARRIED)


def test_a_whole_chat_completion_reads_back_into_the_intermediate_form() -> None:
    payload = {
        "id": "chatcmpl-1",
        "model": "glm-5.2",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "hello there"},
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }

    response = from_chat_completions_response(payload)

    assert response.id == "chatcmpl-1"
    assert response.stop_reason == "end_turn"
    assert [(block.kind.value, block.text) for block in response.blocks] == [("text", "hello there")]
    assert response.usage == {"input_tokens": 12, "output_tokens": 3}


def test_buffered_chat_reasoning_reaches_both_client_formats_as_typed_content() -> None:
    payload = {
        "id": "chatcmpl-reasoning",
        "model": "glm-5.2",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "reasoning_content": "hidden chain",
                    "content": "answer",
                },
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }
    semantic = from_chat_completions_response(payload)
    assert semantic.blocks[0].reasoning is not None
    assert semantic.blocks[0].reasoning.visible_text == "hidden chain"
    assert semantic.blocks[0].reasoning.source_format == "openai-chat-completions"
    assert semantic.blocks[0].reasoning.state is None

    registry = default_registry()
    anthropic, anthropic_semantic = registry.translate_response(
        payload,
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert [block["type"] for block in anthropic["content"]] == ["thinking", "text"]
    thinking = anthropic["content"][0]
    assert thinking["thinking"] == "hidden chain"
    anthropic_carrier = decode_reasoning_carrier(thinking["signature"])
    assert {record.type for record in anthropic_carrier.records} == {
        CHAT_REASONING_CONTENT,
        RESPONSES_SUMMARY_TEXT_LAYOUT,
    }
    assert anthropic["content"][1] == {"type": "text", "text": "answer"}
    assert not anthropic_semantic.conversion.has(LossCode.BLOCK_NOT_CARRIED)

    responses, responses_semantic = registry.translate_response(
        payload,
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert responses["output"][0]["type"] == "reasoning"
    assert responses["output"][0]["summary"] == [
        {"type": "summary_text", "text": "hidden chain"}
    ]
    responses_carrier = decode_reasoning_carrier(
        responses["output"][0]["encrypted_content"]
    )
    assert [(record.type, record.value) for record in responses_carrier.records] == [
        (CHAT_REASONING_CONTENT, None)
    ]
    assert responses["output"][1]["type"] == "message"
    assert responses["output"][1]["content"] == [
        {"type": "output_text", "text": "answer"}
    ]
    assert not responses_semantic.conversion.has(LossCode.BLOCK_NOT_CARRIED)


def test_tool_calls_read_back_with_decoded_arguments() -> None:
    payload = {
        "id": "chatcmpl-2",
        "model": "glm-5.2",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "weather", "arguments": '{"city": "sz"}'},
                        }
                    ],
                },
            }
        ],
    }

    response = from_chat_completions_response(payload)

    assert response.stop_reason == "tool_use"
    block = response.blocks[0]
    assert block.kind.value == "tool_use"
    assert block.call_id == "c1"
    assert block.name == "weather"
    assert block.arguments == {"city": "sz"}


def test_undecodable_arguments_record_a_loss_and_read_as_empty() -> None:
    payload = {
        "id": "x",
        "model": "m",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{oops"}}
                    ],
                },
            }
        ],
    }

    response = from_chat_completions_response(payload)

    assert response.blocks[0].arguments == {}
    assert response.conversion.has(LossCode.UPSTREAM_ERROR_NOT_INTERPRETED)


def test_finish_reasons_map_onto_anthropic_words() -> None:
    cases = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}
    for finish, stop_reason in cases.items():
        response = from_chat_completions_response(
            {
                "id": "x",
                "model": "m",
                "choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": "y"}}],
            }
        )
        assert response.stop_reason == stop_reason, finish


def test_content_filter_keeps_upstreams_own_word() -> None:
    response = from_chat_completions_response(
        {
            "id": "x",
            "model": "m",
            "choices": [{"finish_reason": "content_filter", "message": {"role": "assistant", "content": ""}}],
        }
    )

    assert response.stop_reason == "content_filter"


def test_cached_input_is_reported_as_cache_read() -> None:
    converted = chat_usage_to_anthropic(
        {
            "prompt_tokens": 100,
            "completion_tokens": 5,
            "prompt_tokens_details": {"cached_tokens": 40},
        }
    )

    assert converted == {
        "input_tokens": 100,
        "output_tokens": 5,
        "cache_read_input_tokens": 40,
    }


def test_a_malformed_usage_reads_as_empty() -> None:
    assert chat_usage_to_anthropic({"prompt_tokens": "many"}) == {}


def test_the_registry_serves_the_chat_pair() -> None:
    registry = default_registry()

    assert f"outbound.to-{WireFormat.OPENAI_CHAT_COMPLETIONS.value}" in registry.names
    body, _ = registry.translate(
        {
            "model": "m",
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "hi"}],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_CHAT_COMPLETIONS,
    )
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    translated, _ = registry.translate_response(
        {
            "id": "x",
            "model": "m",
            "choices": [
                {"finish_reason": "stop", "message": {"role": "assistant", "content": "hello"}}
            ],
        },
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert translated["content"] == [{"type": "text", "text": "hello"}]
    assert translated["stop_reason"] == "end_turn"


def test_chat_request_decoder_and_same_format_round_trip_use_the_ir() -> None:
    registry = default_registry()

    source = {
        "model": "m",
        "messages": [
            {"role": "system", "content": "be concise"},
            {"role": "user", "content": "hello"},
        ],
        "temperature": 0.2,
        "future_field": {"kept": True},
    }

    translated, semantic = registry.translate(
        source,
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.OPENAI_CHAT_COMPLETIONS,
    )

    assert [message.role for message in semantic.messages] == ["user"]
    assert translated["messages"] == [
        {"role": "system", "content": "be concise"},
        {"role": "user", "content": "hello"},
    ]
    assert translated["future_field"] == {"kept": True}


def test_chat_named_tool_choice_and_stop_cross_to_anthropic_and_responses() -> None:
    source = {
        "model": "m",
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "look it up",
                    "parameters": {"type": "object"},
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "weather"}},
        "stop": "DONE",
    }
    registry = default_registry()

    anthropic, anthropic_semantic = registry.translate(
        source,
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert anthropic["tool_choice"] == {"type": "tool", "name": "weather"}
    assert anthropic["stop_sequences"] == ["DONE"]
    assert anthropic_semantic.conversion.lossless

    responses, responses_semantic = registry.translate(
        source,
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert responses["tool_choice"] == {"type": "function", "name": "weather"}
    assert "stop" not in responses
    assert responses_semantic.conversion.has(LossCode.EXTENSIONS_NOT_CARRIED)


def test_chat_named_tool_choice_and_stop_same_format_round_trip_exactly() -> None:
    source = {
        "model": "m",
        "messages": [{"role": "user", "content": "hello"}],
        "tool_choice": {"type": "function", "function": {"name": "weather"}},
        "parallel_tool_calls": False,
        "stop": ["DONE", "STOP"],
    }

    translated, semantic = default_registry().translate(
        source,
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.OPENAI_CHAT_COMPLETIONS,
    )

    assert translated["tool_choice"] == source["tool_choice"]
    assert translated["parallel_tool_calls"] is False
    assert translated["stop"] == source["stop"]
    assert semantic.tool_choice is not None
    assert semantic.tool_choice.mode == "tool"
    assert semantic.tool_choice.name == "weather"


@pytest.mark.parametrize(
    ("choice", "mode", "name"),
    [
        ("auto", "auto", None),
        ("required", "any", None),
        ("none", "none", None),
        ({"type": "function", "function": {"name": "weather"}}, "tool", "weather"),
    ],
)
def test_chat_decoder_claims_chat_tool_choice_shapes(
    choice: object,
    mode: str,
    name: str | None,
) -> None:
    request = from_openai_chat_completions(
        {
            "model": "m",
            "messages": [{"role": "user", "content": "hello"}],
            "tool_choice": choice,
        }
    )

    assert request.tool_choice is not None
    assert request.tool_choice.mode == mode
    assert request.tool_choice.name == name
    assert "tool_choice" not in request.unknown_fields


def test_chat_response_encoder_records_skipped_image_and_unknown_blocks() -> None:
    response = SemanticResponse(
        id="r",
        model="m",
        source_format="openai-responses",
        blocks=[
            ContentBlock(BlockKind.IMAGE, raw={"type": "input_image"}),
            ContentBlock(BlockKind.UNKNOWN, raw={"type": "future"}),
        ],
    )

    encoded = to_openai_chat_completions_response(response)

    assert encoded["choices"][0]["message"]["content"] is None
    assert response.conversion.has(LossCode.BLOCK_NOT_CARRIED)
    assert [warning.code for warning in response.conversion.warnings] == [
        "unsupported-semantic-block",
        "unsupported-semantic-block",
    ]


def test_chat_response_same_format_round_trip_preserves_unknown_fields() -> None:
    payload = {
        "id": "chatcmpl-opaque",
        "model": "m",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "ok",
                    "future_message_field": {"value": 1},
                },
                "finish_reason": "stop",
            }
        ],
        "future_top_level": True,
    }

    translated, semantic = default_registry().translate_response(
        payload,
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.OPENAI_CHAT_COMPLETIONS,
    )

    assert translated["choices"][0]["message"]["future_message_field"] == {"value": 1}
    assert translated["future_top_level"] is True
    assert semantic.conversion.warnings == []
