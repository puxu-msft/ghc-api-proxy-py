import pytest
from openai.types.chat import ChatCompletion
from openai.types.responses import Response

from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.commandcode import from_commandcode_response
from app.pipeline.translation_driver.registry import default_registry
from app.pipeline.translation_driver.semantic import (
    LossCode,
    TranslationRefused,
    TranslationTarget,
)


def test_commandcode_encoder_projects_the_ir_into_its_native_envelope() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "deepseek/deepseek-v4-flash",
            "system": "be concise",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 128,
            "stream": False,
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"] == {
        "model": "deepseek/deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "hello"}]}
        ],
        "max_tokens": 128,
        "stream": True,
        "system": "be concise",
    }
    assert semantic.conversion.has(LossCode.COMMANDCODE_STREAM_FORCED)
    assert not semantic.conversion.has(LossCode.REASONING_INTENT_NOT_CARRIED)


def test_commandcode_accepts_responses_string_and_easy_input_items() -> None:
    body, _ = default_registry().translate(
        {"model": "m", "input": "hello"},
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "hello"}]}
    ]


def test_commandcode_accepts_responses_instructions_without_input() -> None:
    body, semantic = default_registry().translate(
        {"model": "m", "instructions": "follow these rules"},
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["system"] == "follow these rules"
    assert body["params"]["messages"] == []
    assert not semantic.conversion.has(LossCode.BLOCK_NOT_CARRIED)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("background", True),
        ("context_management", [{"type": "compaction"}]),
        ("conversation", "conv_1"),
        ("include", ["message.output_text.logprobs"]),
        ("max_tool_calls", 1),
        ("moderation", {"model": "omni-moderation-latest"}),
        ("prompt", {"id": "pmpt_1"}),
        ("stream_options", {"include_obfuscation": False}),
        (
            "text",
            {
                "format": {
                    "type": "json_schema",
                    "name": "answer",
                    "schema": {"type": "object"},
                }
            },
        ),
        ("top_logprobs", 1),
        ("top_p", 0.5),
        ("truncation", "auto"),
    ],
)
def test_commandcode_refuses_unrepresentable_responses_controls(
    field: str,
    value: object,
) -> None:
    with pytest.raises(TranslationRefused) as caught:
        default_registry().translate(
            {"model": "m", "input": "hello", field: value},
            source=WireFormat.OPENAI_RESPONSES,
            target=WireFormat.COMMANDCODE,
        )

    assert caught.value.code == "commandcode-responses-control-not-supported"
    assert caught.value.field_path == field


def test_commandcode_records_loss_for_advisory_responses_fields() -> None:
    _, semantic = default_registry().translate(
        {
            "model": "m",
            "input": "hello",
            "metadata": {"request": "one"},
            "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
            "prompt_cache_retention": "24h",
            "safety_identifier": "user-1",
            "service_tier": "priority",
            "user": "user-1",
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    details = "\n".join(loss.detail for loss in semantic.conversion.losses)
    assert all(
        field in details
        for field in (
            "metadata",
            "prompt_cache_options",
            "prompt_cache_retention",
            "safety_identifier",
            "service_tier",
            "user",
        )
    )


@pytest.mark.parametrize(
    "choice",
    [
        {"type": "custom", "name": "apply_patch"},
        {"type": "web_search_preview"},
        {"type": "mcp", "server_label": "server"},
    ],
)
def test_commandcode_refuses_forced_responses_non_function_tool_choices(
    choice: dict[str, object],
) -> None:
    with pytest.raises(TranslationRefused) as caught:
        default_registry().translate(
            {
                "model": "m",
                "input": "use a tool",
                "tools": [
                    {"type": choice["type"], "name": choice.get("name", "server")}
                ],
                "tool_choice": choice,
            },
            source=WireFormat.OPENAI_RESPONSES,
            target=WireFormat.COMMANDCODE,
        )

    assert caught.value.code == "commandcode-tool-choice-not-supported"
    assert caught.value.field_path == "tool_choice"


def test_commandcode_refuses_forced_choice_for_a_filtered_responses_tool() -> None:
    with pytest.raises(TranslationRefused) as caught:
        default_registry().translate(
            {
                "model": "m",
                "input": "use a tool",
                "tools": [{"type": "custom", "name": "apply_patch"}],
                "tool_choice": {"type": "function", "name": "apply_patch"},
            },
            source=WireFormat.OPENAI_RESPONSES,
            target=WireFormat.COMMANDCODE,
        )

    assert caught.value.code == "commandcode-tool-choice-not-supported"
    assert caught.value.field_path == "tool_choice"


def test_commandcode_keeps_forced_choice_for_a_final_function_tool() -> None:
    body, _ = default_registry().translate(
        {
            "model": "m",
            "input": "use a tool",
            "tools": [
                {
                    "type": "function",
                    "name": "weather",
                    "parameters": {"type": "object"},
                }
            ],
            "tool_choice": {"type": "function", "name": "weather"},
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["tool_choice"] == {"type": "tool", "name": "weather"}


@pytest.mark.parametrize("call_id", [None, ""])
def test_commandcode_refuses_responses_tool_outputs_without_a_call_id(
    call_id: str | None,
) -> None:
    item = {
        "type": "function_call_output",
        "output": "result",
    }
    if call_id is not None:
        item["call_id"] = call_id

    with pytest.raises(TranslationRefused) as caught:
        default_registry().translate(
            {
                "model": "m",
                "input": [item],
            },
            source=WireFormat.OPENAI_RESPONSES,
            target=WireFormat.COMMANDCODE,
        )

    assert caught.value.code == "function-call-output-call-id-missing"
    assert caught.value.field_path == "input[].call_id"


def test_commandcode_merges_responses_assistant_items_and_maps_system_roles() -> None:
    body, _ = default_registry().translate(
        {
            "model": "alias",
            "input": [
                {"role": "system", "content": "system rules"},
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "developer rules"}],
                },
                {"role": "user", "content": "question"},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "answer"}],
                },
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "think"}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "weather",
                    "arguments": '{"city":"Seattle"}',
                },
            ],
            "parallel_tool_calls": False,
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["system"] == "system rules\n\ndeveloper rules"
    assert [message["role"] for message in body["params"]["messages"]] == [
        "user",
        "assistant",
    ]
    assistant = body["params"]["messages"][1]
    assert [part["type"] for part in assistant["content"]] == [
        "reasoning",
        "text",
        "tool-call",
    ]
    assert body["params"]["parallel_tool_calls"] is False


def test_commandcode_uses_the_resolved_target_model_after_mapping() -> None:
    body, _ = default_registry().translate(
        {
            "model": "alias",
            "messages": [{"role": "user", "content": "hello"}],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.COMMANDCODE,
        target_model=TranslationTarget(model_id="real-model"),
    )

    assert body["params"]["model"] == "real-model"


def test_commandcode_encoder_keeps_reasoning_before_text_and_maps_tools() -> None:
    body, _ = default_registry().translate(
        {
            "model": "m",
            "messages": [
                {"role": "user", "content": "use the tool"},
            ],
            "tools": [
                {
                    "name": "weather",
                    "description": "Get weather",
                    "input_schema": {"type": "object"},
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "weather"}},
            "stream": True,
        },
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["tools"] == [
        {
            "type": "function",
            "name": "weather",
            "description": "Get weather",
            "input_schema": {"type": "object"},
        }
    ]
    assert body["params"]["tool_choice"] == {"type": "tool", "name": "weather"}


def test_commandcode_only_projects_responses_function_tools() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "input": "use a tool",
            "tools": [
                {
                    "type": "function",
                    "name": "weather",
                    "description": "Get weather",
                    "parameters": {"type": "object"},
                },
                {"type": "web_search_preview"},
                {"type": "custom", "name": "apply_patch", "format": {"type": "text"}},
                {"type": "mcp", "server_url": "https://example.test/mcp"},
                {"type": "tool_search", "execution": "server"},
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["tools"] == [
        {
            "type": "function",
            "name": "weather",
            "description": "Get weather",
            "input_schema": {"type": "object"},
        }
    ]
    assert semantic.conversion.has(LossCode.ITEM_NOT_CARRIED)
    assert all(tool["name"] for tool in body["params"]["tools"])


def test_commandcode_function_tool_nullable_fields_use_safe_values_and_record_losses() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "input": "use a tool",
            "tools": [
                {
                    "type": "function",
                    "name": "weather",
                    "description": None,
                    "parameters": None,
                    "strict": True,
                    "allowed_callers": ["model"],
                    "output_schema": {"type": "object"},
                    "defer_loading": True,
                }
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["tools"] == [
        {
            "type": "function",
            "name": "weather",
            "description": "",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]
    details = "\n".join(loss.detail for loss in semantic.conversion.losses)
    assert semantic.conversion.has(LossCode.EXTENSIONS_NOT_CARRIED)
    assert all(field in details for field in ("strict", "allowed_callers", "output_schema", "defer_loading"))
    assert '"None"' not in details


def test_commandcode_preserves_chat_function_tool_extensions_until_the_target_records_loss() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "messages": [{"role": "user", "content": "use a tool"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "weather",
                        "description": None,
                        "parameters": None,
                        "strict": True,
                        "allowed_callers": ["model"],
                    },
                }
            ],
        },
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["tools"][0]["description"] == ""
    assert body["params"]["tools"][0]["input_schema"] == {
        "type": "object",
        "properties": {},
    }
    assert semantic.conversion.has(LossCode.EXTENSIONS_NOT_CARRIED)
    assert all(
        field in "\n".join(loss.detail for loss in semantic.conversion.losses)
        for field in ("strict", "allowed_callers")
    )


def test_commandcode_records_unconsumed_chat_extensions_as_losses() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "messages": [{"role": "user", "content": "hello"}],
            "stop": ["DONE"],
            "vendor_extension": {"mode": "fast"},
        },
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.COMMANDCODE,
    )

    details = "\n".join(loss.detail for loss in semantic.conversion.losses)
    assert "stop" in details
    assert "vendor_extension" in details
    assert "stop" not in body["params"]
    assert "vendor_extension" not in body["params"]


def test_commandcode_records_unconsumed_responses_extensions_without_repeating_mappings() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "input": "hello",
            "prompt_cache_key": "cache-key",
            "service_tier": "priority",
            "reasoning": {"effort": "medium", "vendor_flag": True},
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    details = "\n".join(loss.detail for loss in semantic.conversion.losses)
    assert "service_tier" in details
    assert "reasoning.vendor_flag" in details
    assert "prompt_cache_key" not in details
    assert "reasoning.effort" not in details
    assert body["params"]["messages"][0]["content"][-1]["cache_control"] == {
        "type": "ephemeral"
    }
    assert "prompt_cache_key" not in body["params"]


def test_commandcode_does_not_emit_an_empty_function_for_unrepresentable_tools() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "input": "hello",
            "tools": [{"type": "web_search_preview"}],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert "tools" not in body["params"]
    assert semantic.conversion.has(LossCode.ITEM_NOT_CARRIED)


@pytest.mark.parametrize(
    "image_url",
    ["data:image/png;base64,abc", "https://example.test/image.png"],
)
def test_commandcode_supports_responses_input_image_url_strings(
    image_url: str,
) -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": image_url,
                        }
                    ],
                }
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["messages"][0]["content"] == [
        {"type": "image", "image": image_url}
    ]
    assert not semantic.conversion.has(LossCode.BLOCK_NOT_CARRIED)


def test_commandcode_records_responses_image_field_losses_without_dropping_image_url() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": "https://example.test/image.png",
                            "detail": "high",
                            "prompt_cache_breakpoint": {"index": 1},
                        }
                    ],
                }
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["messages"][0]["content"] == [
        {"type": "image", "image": "https://example.test/image.png"}
    ]
    details = "\n".join(loss.detail for loss in semantic.conversion.losses)
    assert "input[].content[].detail" in details
    assert "input[].content[].prompt_cache_breakpoint" in details


def test_commandcode_records_loss_for_responses_image_file_ids() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_image", "file_id": "file_1"},
                        {"type": "input_text", "text": "describe it"},
                    ],
                }
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["messages"][0]["content"] == [
        {"type": "text", "text": "describe it"}
    ]
    assert semantic.conversion.has(LossCode.BLOCK_NOT_CARRIED)


@pytest.mark.parametrize(
    ("source", "payload_key"),
    [
        (WireFormat.ANTHROPIC_MESSAGES, "max_tokens"),
        (WireFormat.OPENAI_RESPONSES, "max_output_tokens"),
    ],
)
def test_commandcode_caps_max_tokens_at_200000(
    source: WireFormat,
    payload_key: str,
) -> None:
    request = (
        {
            "model": "m",
            "messages": [{"role": "user", "content": "hello"}],
            payload_key: 200001,
        }
        if source is WireFormat.ANTHROPIC_MESSAGES
        else {
            "model": "m",
            "input": "hello",
            payload_key: 200001,
        }
    )

    body, _ = default_registry().translate(
        request,
        source=source,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["max_tokens"] == 200000


def test_commandcode_encoder_preserves_tool_result_names_images_and_cache_markers() -> None:
    body, _ = default_registry().translate(
        {
            "model": "m",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "weather",
                            "input": {"city": "Seattle"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "content": "sunny",
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "abc",
                            },
                        },
                    ],
                },
            ],
            "stream": True,
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["messages"][1]["role"] == "tool"
    assert body["params"]["messages"][1]["content"][0]["toolName"] == "weather"
    assert body["params"]["messages"][2]["content"][0] == {
        "type": "image",
        "image": "data:image/png;base64,abc",
    }


def test_commandcode_tool_results_keep_block_order_across_roles() -> None:
    body, _ = default_registry().translate(
        {
            "model": "m",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "weather",
                            "input": {},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "before"},
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "content": "sunny",
                        },
                        {"type": "text", "text": "after"},
                    ],
                },
            ],
            "stream": True,
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.COMMANDCODE,
    )

    messages = body["params"]["messages"]
    assert [message["role"] for message in messages] == [
        "assistant",
        "tool",
        "user",
    ]
    assert messages[1]["content"][0]["toolName"] == "weather"


def test_commandcode_response_events_cross_back_to_all_client_wires() -> None:
    upstream = {
        "model": "m",
        "events": [
            {"type": "reasoning-delta", "text": "think"},
            {"type": "text-delta", "text": "answer"},
            {
                "type": "tool-call",
                "toolCallId": "call_1",
                "toolName": "weather",
                "input": {"city": "Seattle"},
            },
            {
                "type": "finish",
                "finishReason": "tool-calls",
                "totalUsage": {
                    "inputTokens": 100,
                    "outputTokens": 12,
                    "cachedInputTokens": 40,
                },
            },
        ],
    }
    registry = default_registry()

    anthropic, _ = registry.translate_response(
        upstream,
        source=WireFormat.COMMANDCODE,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert [block["type"] for block in anthropic["content"]] == [
        "thinking",
        "text",
        "tool_use",
    ]
    assert anthropic["content"][2]["input"] == {"city": "Seattle"}
    assert anthropic["stop_reason"] == "tool_use"
    assert anthropic["usage"] == {
        "input_tokens": 60,
        "output_tokens": 12,
        "cache_read_input_tokens": 40,
    }

    responses, _ = registry.translate_response(
        upstream,
        source=WireFormat.COMMANDCODE,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert responses["status"] == "completed"
    assert [item["type"] for item in responses["output"]] == [
        "reasoning",
        "message",
        "function_call",
    ]

    chat, _ = registry.translate_response(
        upstream,
        source=WireFormat.COMMANDCODE,
        target=WireFormat.OPENAI_CHAT_COMPLETIONS,
    )
    assert chat["choices"][0]["finish_reason"] == "tool_calls"
    assert chat["choices"][0]["message"]["tool_calls"][0]["id"] == "call_1"


@pytest.mark.parametrize(
    "usage",
    [
        {
            "inputTokens": 100,
            "outputTokens": 12,
            "inputTokenDetails": {
                "cacheReadTokens": 20,
                "cacheWriteTokens": 3,
                "noCacheTokens": 55,
            },
        },
        {
            "input_tokens": 100,
            "output_tokens": 12,
            "input_tokens_details": {
                "cache_read_tokens": 20,
                "cache_write_tokens": 3,
                "no_cache_tokens": 55,
            },
        },
    ],
)
def test_commandcode_usage_projects_detail_aliases_with_no_cache_priority(
    usage: dict[str, object],
) -> None:
    upstream = {
        "model": "m",
        "events": [
            {"type": "text-delta", "text": "answer"},
            {"type": "finish", "finishReason": "stop", "totalUsage": usage},
        ],
    }
    registry = default_registry()

    anthropic, _ = registry.translate_response(
        upstream,
        source=WireFormat.COMMANDCODE,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert anthropic["usage"] == {
        "input_tokens": 55,
        "output_tokens": 12,
        "cache_read_input_tokens": 20,
        "cache_creation_input_tokens": 3,
    }

    responses, _ = registry.translate_response(
        upstream,
        source=WireFormat.COMMANDCODE,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert responses["usage"] == {
        "input_tokens": 78,
        "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 3},
        "output_tokens": 12,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 90,
    }

    chat, _ = registry.translate_response(
        upstream,
        source=WireFormat.COMMANDCODE,
        target=WireFormat.OPENAI_CHAT_COMPLETIONS,
    )
    assert chat["usage"]["prompt_tokens"] == 78
    assert chat["usage"]["completion_tokens"] == 12
    assert chat["usage"]["total_tokens"] == 90


def test_commandcode_buffered_outputs_validate_against_openai_schemas() -> None:
    upstream = {
        "model": "m",
        "events": [
            {"type": "reasoning-delta", "text": "think"},
            {"type": "text-delta", "text": "answer"},
            {
                "type": "tool-call",
                "toolCallId": "call_1",
                "toolName": "weather",
                "input": {"city": "Seattle"},
            },
            {
                "type": "finish",
                "finishReason": "tool-calls",
                "totalUsage": {
                    "inputTokens": 100,
                    "outputTokens": 12,
                    "cachedInputTokens": 40,
                    "inputTokenDetails": {"cacheWriteTokens": 5},
                    "outputTokenDetails": {"reasoningTokens": 3},
                },
            },
        ],
    }
    registry = default_registry()

    responses, _ = registry.translate_response(
        upstream,
        source=WireFormat.COMMANDCODE,
        target=WireFormat.OPENAI_RESPONSES,
    )
    parsed_responses = Response.model_validate(responses)
    assert parsed_responses.usage is not None
    assert parsed_responses.usage.input_tokens == 100
    assert parsed_responses.usage.input_tokens_details.cached_tokens == 40
    assert parsed_responses.usage.input_tokens_details.cache_write_tokens == 5
    assert parsed_responses.usage.output_tokens_details.reasoning_tokens == 3

    chat, _ = registry.translate_response(
        upstream,
        source=WireFormat.COMMANDCODE,
        target=WireFormat.OPENAI_CHAT_COMPLETIONS,
    )
    parsed_chat = ChatCompletion.model_validate(chat)
    assert parsed_chat.created > 0
    assert parsed_chat.usage is not None
    assert parsed_chat.usage.prompt_tokens == 100
    assert parsed_chat.usage.completion_tokens == 12
    assert parsed_chat.usage.total_tokens == 112


@pytest.mark.parametrize(
    ("budget", "effort"),
    [(2000, "low"), (5000, "medium"), (10000, "high")],
)
def test_commandcode_maps_anthropic_thinking_budgets(
    budget: int,
    effort: str,
) -> None:
    body, _ = default_registry().translate(
        {
            "model": "m",
            "thinking": {"type": "enabled", "budget_tokens": budget},
            "messages": [{"role": "user", "content": "hello"}],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["reasoning_effort"] == effort


def test_commandcode_maps_anthropic_adaptive_thinking_to_medium_effort() -> None:
    body, _ = default_registry().translate(
        {
            "model": "m",
            "thinking": {"type": "adaptive"},
            "messages": [{"role": "user", "content": "hello"}],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["reasoning_effort"] == "medium"


def test_commandcode_preserves_chat_reasoning_effort() -> None:
    body, _ = default_registry().translate(
        {
            "model": "m",
            "reasoning_effort": "medium",
            "messages": [{"role": "user", "content": "hello"}],
        },
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["reasoning_effort"] == "medium"


@pytest.mark.parametrize(
    ("source", "payload_key"),
    [
        (WireFormat.ANTHROPIC_MESSAGES, "max_tokens"),
        (WireFormat.OPENAI_RESPONSES, "max_output_tokens"),
        (WireFormat.OPENAI_CHAT_COMPLETIONS, "max_tokens"),
    ],
)
@pytest.mark.parametrize("value", [0, -1])
def test_commandcode_refuses_non_positive_explicit_output_limits(
    source: WireFormat,
    payload_key: str,
    value: int,
) -> None:
    request = {
        "model": "m",
        "messages": [{"role": "user", "content": "hello"}],
        payload_key: value,
    }
    if source is WireFormat.OPENAI_RESPONSES:
        request = {
            "model": "m",
            "input": "hello",
            payload_key: value,
        }

    with pytest.raises(TranslationRefused) as caught:
        default_registry().translate(
            request,
            source=source,
            target=WireFormat.COMMANDCODE,
        )

    assert caught.value.code == "commandcode-max-output-tokens-invalid"
    assert caught.value.field_path == (
        "max_output_tokens" if source is WireFormat.OPENAI_RESPONSES else "max_tokens"
    )


def test_commandcode_uses_the_default_only_when_output_limit_is_absent() -> None:
    body, _ = default_registry().translate(
        {
            "model": "m",
            "messages": [{"role": "user", "content": "hello"}],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["max_tokens"] == 64000


def test_commandcode_preserves_chat_parallel_tool_calls_without_tool_choice() -> None:
    body, _ = default_registry().translate(
        {
            "model": "m",
            "messages": [{"role": "user", "content": "hello"}],
            "parallel_tool_calls": False,
        },
        source=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["parallel_tool_calls"] is False


def test_commandcode_never_exposes_internal_incomplete_stop_reasons() -> None:
    registry = default_registry()
    upstream = {
        "model": "m",
        "events": [{"type": "text-delta", "text": "partial"}],
    }

    anthropic, _ = registry.translate_response(
        upstream,
        source=WireFormat.COMMANDCODE,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert anthropic["stop_reason"] == "end_turn"

    chat, _ = registry.translate_response(
        upstream,
        source=WireFormat.COMMANDCODE,
        target=WireFormat.OPENAI_CHAT_COMPLETIONS,
    )
    assert chat["choices"][0]["finish_reason"] == "stop"


def test_commandcode_response_reader_marks_missing_terminal_as_incomplete() -> None:
    response = from_commandcode_response(
        {
            "model": "m",
            "events": [{"type": "text-delta", "text": "partial"}],
        }
    )

    assert response.stop_reason == "incomplete"
    assert response.blocks == []


def test_commandcode_response_reader_flushes_open_block_at_finish() -> None:
    response = from_commandcode_response(
        {
            "model": "m",
            "events": [
                {"type": "text-delta", "text": "answer"},
                {
                    "type": "finish",
                    "finishReason": "stop",
                    "totalUsage": {"inputTokens": 1, "outputTokens": 1},
                },
            ],
        }
    )

    assert [block.text for block in response.blocks] == ["answer"]
    assert response.stop_reason == "end_turn"


def test_commandcode_response_reader_preserves_malformed_tool_input_evidence() -> None:
    response = from_commandcode_response(
        {
            "model": "m",
            "events": [
                {
                    "type": "tool-call",
                    "toolCallId": "call_1",
                    "toolName": "weather",
                    "input": '{"city":',
                },
                {
                    "type": "finish",
                    "finishReason": "tool-calls",
                    "totalUsage": {"inputTokens": 1, "outputTokens": 1},
                },
            ],
        }
    )

    assert response.blocks[0].arguments == {"__raw": '{"city":'}
    assert response.conversion.has(LossCode.UPSTREAM_ERROR_NOT_INTERPRETED)


def test_commandcode_malformed_tool_input_is_raw_in_buffered_responses_output() -> None:
    responses, _ = default_registry().translate_response(
        {
            "model": "m",
            "events": [
                {
                    "type": "tool-call",
                    "toolCallId": "call_1",
                    "toolName": "weather",
                    "input": '{"city":',
                },
                {
                    "type": "finish",
                    "finishReason": "tool-calls",
                    "totalUsage": {"inputTokens": 1, "outputTokens": 1},
                },
            ],
        },
        source=WireFormat.COMMANDCODE,
        target=WireFormat.OPENAI_RESPONSES,
    )

    call = next(item for item in responses["output"] if item["type"] == "function_call")
    assert call["arguments"] == '{"city":'


def test_commandcode_response_reader_uses_stable_fallback_for_missing_tool_id() -> None:
    response = from_commandcode_response(
        {
            "model": "m",
            "events": [
                {
                    "type": "tool-input-start",
                    "toolName": "weather",
                },
                {"type": "tool-input-delta", "input": '{"city":"Seattle"}'},
                {
                    "type": "finish",
                    "finishReason": "tool-calls",
                    "totalUsage": {"inputTokens": 1, "outputTokens": 1},
                },
            ],
        }
    )

    assert response.blocks[0].call_id == "call_0"
    assert response.blocks[0].arguments == {"city": "Seattle"}


def test_commandcode_preserves_structured_responses_tool_output_text() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": [
                        {"type": "input_text", "text": "first"},
                        {"type": "output_text", "text": " second"},
                    ],
                }
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["messages"][0]["content"][0]["output"] == {
        "type": "text",
        "value": "first second",
    }
    assert not semantic.conversion.has(LossCode.TOOL_RESULT_CONTENT_FLATTENED)


def test_commandcode_records_loss_for_unrepresentable_structured_tool_output() -> None:
    body, semantic = default_registry().translate(
        {
            "model": "m",
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": [
                        {"type": "input_text", "text": "visible"},
                        {
                            "type": "input_image",
                            "image_url": "data:image/png;base64,abc",
                        },
                    ],
                }
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )

    assert body["params"]["messages"][0]["content"][0]["output"]["value"] == "visible"
    assert semantic.conversion.has(LossCode.TOOL_RESULT_CONTENT_FLATTENED)


def test_commandcode_refuses_stateful_responses_requests() -> None:
    with pytest.raises(TranslationRefused) as caught:
        default_registry().translate(
            {
                "model": "m",
                "input": "hello",
                "store": True,
                "previous_response_id": "resp_old",
            },
            source=WireFormat.OPENAI_RESPONSES,
            target=WireFormat.COMMANDCODE,
        )

    assert caught.value.field_path in {"store", "previous_response_id"}


def test_commandcode_refuses_encrypted_only_responses_reasoning_history() -> None:
    with pytest.raises(TranslationRefused) as caught:
        default_registry().translate(
            {
                "model": "m",
                "input": [
                    {
                        "type": "reasoning",
                        "summary": [],
                        "encrypted_content": "provider-sealed-history",
                    },
                    {"type": "message", "role": "user", "content": "continue"},
                ],
            },
            source=WireFormat.OPENAI_RESPONSES,
            target=WireFormat.COMMANDCODE,
        )

    assert caught.value.code == "commandcode-reasoning-state-not-supported"
    assert caught.value.field_path == "input.reasoning.encrypted_content"


def test_responses_easy_input_message_phase_is_preserved_or_recorded_as_loss() -> None:
    request = {
        "model": "m",
        "input": [
            {
                "role": "user",
                "phase": "commentary",
                "content": "hello",
            }
        ],
    }

    same_wire, same_semantic = default_registry().translate(
        request,
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert same_wire["input"][0]["phase"] == "commentary"
    assert same_semantic.conversion.lossless

    commandcode, commandcode_semantic = default_registry().translate(
        request,
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.COMMANDCODE,
    )
    assert commandcode["params"]["messages"][0]["content"][0]["text"] == "hello"
    assert commandcode_semantic.conversion.has(LossCode.MESSAGE_PHASE_NOT_CARRIED)
