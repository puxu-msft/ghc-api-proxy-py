import pytest

from app.anthropic.thinking.responses_reasoning import responses_reasoning_to_anthropic
from app.models.anthropic import AnthropicMessage, AnthropicTool, MessagesRequest, SystemBlock
from app.protocols.anthropic_responses import (
    ConversionFact,
    ReasoningCapabilityFacts,
    ReasoningEffortBand,
    RequestConversionError,
    ToolNameMapper,
    ToolNameMappingFact,
    convert_messages_request_to_responses,
)

REASONING_CAPABILITIES = ReasoningCapabilityFacts(
    supported_efforts=("low", "medium", "high"),
    budget_limits_known=True,
    min_budget_tokens=1_024,
    max_budget_tokens=32_768,
    enabled_budget_bands=(
        ReasoningEffortBand(max_budget_tokens=4_096, effort="low"),
        ReasoningEffortBand(max_budget_tokens=16_384, effort="medium"),
        ReasoningEffortBand(max_budget_tokens=None, effort="high"),
    ),
    adaptive_effort="high",
)


def test_converts_text_system_and_metadata_without_mutating_request() -> None:
    request = MessagesRequest.model_validate(
        {
            "model": "gpt-test",
            "max_tokens": 512,
            "system": [
                {"type": "text", "text": "first"},
                {"type": "text", "text": ""},
                {"type": "text", "text": "third"},
            ],
            "messages": [
                {"role": "user", "content": "hello"},
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hi"}],
                },
            ],
            "metadata": {"user_id": "user-1", "trace": "local-only"},
        }
    )
    before = request.model_dump(mode="json", exclude_none=True)

    converted = convert_messages_request_to_responses(request)

    assert converted.wire == {
        "model": "gpt-test",
        "include": ["reasoning.encrypted_content"],
        "instructions": "first\n\n\n\nthird",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hi"}],
            },
        ],
        "max_output_tokens": 512,
        "stream": False,
        "user": "user-1",
    }
    assert converted.facts == (
        ConversionFact(
            field_path="metadata.trace",
            disposition="degrade",
            reason="metadata_not_allowlisted",
        ),
    )
    assert request.model_dump(mode="json", exclude_none=True) == before


def test_requests_reasoning_encrypted_content_for_public_carrier_round_trip() -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hello"}],
        }
    )

    assert converted.wire["include"] == ["reasoning.encrypted_content"]


@pytest.mark.parametrize("empty_role", ["user", "assistant"])
def test_rejects_empty_content_list_without_dropping_or_merging_turns(
    empty_role: str,
) -> None:
    surrounding_role = "assistant" if empty_role == "user" else "user"
    request = MessagesRequest.model_validate(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [
                {"role": surrounding_role, "content": "first"},
                {"role": empty_role, "content": []},
                {"role": surrounding_role, "content": "second"},
            ],
        }
    )

    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(request)

    assert caught.value.code == "invalid_content"
    assert caught.value.field_path == "messages[1].content"


def test_preserves_interleaved_tool_round_trip_order() -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 256,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "weather",
                            "input": {"city": "Paris"},
                        },
                        {"type": "text", "text": "checking"},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "please continue"},
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "content": [{"type": "text", "text": "sunny"}],
                        },
                    ],
                },
            ],
            "tools": [
                {
                    "name": "weather",
                    "description": "Read weather",
                    "input_schema": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                }
            ],
            "tool_choice": {"type": "tool", "name": "weather"},
        }
    )

    assert converted.wire["tools"] == [
        {
            "type": "function",
            "name": "weather",
            "description": "Read weather",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ]
    assert converted.wire["tool_choice"] == {"type": "function", "name": "weather"}
    assert converted.wire["input"] == [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "weather",
            "arguments": '{"city":"Paris"}',
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "checking"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "please continue"}],
        },
        {"type": "function_call_output", "call_id": "call_1", "output": "sunny"},
    ]


def test_marks_tool_errors_in_function_call_output() -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "content": "failed",
                            "is_error": True,
                        }
                    ],
                }
            ],
        }
    )

    assert converted.wire["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "[tool_error] failed",
        }
    ]


def test_converts_parallel_tool_choice_flag() -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"name": "lookup", "input_schema": {"type": "object"}}],
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
        }
    )

    assert converted.wire["tool_choice"] == "auto"
    assert converted.wire["parallel_tool_calls"] is False


def test_converts_base64_and_url_images() -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-vision",
            "max_tokens": 128,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "AAEC",
                            },
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": "https://example.test/image.jpg",
                            },
                        },
                    ],
                }
            ],
        }
    )

    assert converted.wire["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": "data:image/png;base64,AAEC"},
                {"type": "input_image", "image_url": "https://example.test/image.jpg"},
            ],
        }
    ]


def test_converts_stream_limits_and_sampling_fields() -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 4096,
            "temperature": 0.25,
            "top_p": 0.8,
            "stream": True,
            "messages": [{"role": "user", "content": "hello"}],
        }
    )

    assert converted.wire["max_output_tokens"] == 4096
    assert converted.wire["temperature"] == 0.25
    assert converted.wire["top_p"] == 0.8
    assert converted.wire["stream"] is True


@pytest.mark.parametrize(
    ("thinking", "expected_reasoning"),
    [
        (
            {"type": "enabled", "budget_tokens": 8_192},
            {"effort": "medium", "summary": "auto"},
        ),
        ({"type": "adaptive"}, {"effort": "high", "summary": "auto"}),
        ({"type": "disabled"}, None),
    ],
)
def test_maps_thinking_from_explicit_reasoning_capability_facts(
    thinking: dict[str, object], expected_reasoning: dict[str, str] | None
) -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "resolved-model",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hello"}],
            "thinking": thinking,
        },
        reasoning_capabilities=REASONING_CAPABILITIES,
    )

    if expected_reasoning is None:
        assert "reasoning" not in converted.wire
    else:
        assert converted.wire["reasoning"] == expected_reasoning


def test_rejects_enabled_thinking_without_reasoning_capability_facts() -> None:
    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "name-must-not-imply-capability",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "hello"}],
                "thinking": {"type": "enabled", "budget_tokens": 8_192},
            }
        )

    assert caught.value.code == "reasoning_not_supported"
    assert caught.value.field_path == "thinking"


@pytest.mark.parametrize("budget", [0, -1])
def test_rejects_non_positive_enabled_thinking_budget_before_capability_lookup(
    budget: int,
) -> None:
    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "capability-must-not-mask-invalid-input",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "hello"}],
                "thinking": {"type": "enabled", "budget_tokens": budget},
            }
        )

    assert caught.value.code == "invalid_thinking"
    assert caught.value.field_path == "thinking.budget_tokens"


def test_rejects_unknown_thinking_type_before_capability_lookup() -> None:
    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "gpt-test",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "hello"}],
                "thinking": {"type": "future_mode"},
            }
        )

    assert caught.value.code == "unsupported_thinking"
    assert caught.value.field_path == "thinking.type"


@pytest.mark.parametrize("budget", [1_023, 32_769])
def test_rejects_thinking_budget_outside_explicit_capability_limits(budget: int) -> None:
    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "resolved-model",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "hello"}],
                "thinking": {"type": "enabled", "budget_tokens": budget},
            },
            reasoning_capabilities=REASONING_CAPABILITIES,
        )

    assert caught.value.code == "reasoning_budget_not_supported"
    assert caught.value.field_path == "thinking.budget_tokens"


@pytest.mark.parametrize(
    ("min_budget_tokens", "max_budget_tokens"),
    [(None, None), (1_024, None), (None, 32_768)],
)
def test_rejects_enabled_thinking_when_budget_limits_are_unknown(
    min_budget_tokens: int | None,
    max_budget_tokens: int | None,
) -> None:
    capabilities = ReasoningCapabilityFacts(
        supported_efforts=("low",),
        budget_limits_known=False,
        min_budget_tokens=min_budget_tokens,
        max_budget_tokens=max_budget_tokens,
        enabled_budget_bands=(
            ReasoningEffortBand(max_budget_tokens=None, effort="low"),
        ),
        adaptive_effort=None,
    )

    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "resolved-model-with-incomplete-catalog-facts",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "hello"}],
                "thinking": {"type": "enabled", "budget_tokens": 8_192},
            },
            reasoning_capabilities=capabilities,
        )

    assert caught.value.code == "reasoning_not_supported"
    assert caught.value.field_path == "thinking"


@pytest.mark.parametrize(
    ("min_budget_tokens", "max_budget_tokens"),
    [(None, None), (1_024, None), (None, 32_768)],
)
def test_maps_enabled_thinking_with_explicitly_unbounded_budget_limits(
    min_budget_tokens: int | None,
    max_budget_tokens: int | None,
) -> None:
    capabilities = ReasoningCapabilityFacts(
        supported_efforts=("low",),
        budget_limits_known=True,
        min_budget_tokens=min_budget_tokens,
        max_budget_tokens=max_budget_tokens,
        enabled_budget_bands=(
            ReasoningEffortBand(max_budget_tokens=None, effort="low"),
        ),
        adaptive_effort=None,
    )

    converted = convert_messages_request_to_responses(
        {
            "model": "resolved-model-with-explicit-unbounded-limits",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hello"}],
            "thinking": {"type": "enabled", "budget_tokens": 8_192},
        },
        reasoning_capabilities=capabilities,
    )

    assert converted.wire["reasoning"] == {"effort": "low", "summary": "auto"}


@pytest.mark.parametrize(
    ("budget", "expected_effort"),
    [(1_024, "low"), (32_768, "high")],
)
def test_accepts_exact_explicit_reasoning_budget_boundaries(
    budget: int,
    expected_effort: str,
) -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "resolved-model",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hello"}],
            "thinking": {"type": "enabled", "budget_tokens": budget},
        },
        reasoning_capabilities=REASONING_CAPABILITIES,
    )

    assert converted.wire["reasoning"] == {
        "effort": expected_effort,
        "summary": "auto",
    }


def test_rejects_reasoning_effort_not_advertised_by_capability_facts() -> None:
    with pytest.raises(ValueError, match="band is not supported"):
        ReasoningCapabilityFacts(
            supported_efforts=("low",),
            budget_limits_known=True,
            min_budget_tokens=None,
            max_budget_tokens=None,
            enabled_budget_bands=(ReasoningEffortBand(max_budget_tokens=None, effort="high"),),
            adaptive_effort=None,
        )


def test_rejects_unknown_top_level_field_preserved_by_pydantic() -> None:
    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "gpt-test",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "hello"}],
                "future_option": {"enabled": True},
            }
        )

    assert caught.value.code == "unsupported_field"
    assert caught.value.field_path == "future_option"


class _FutureMessagesRequest(MessagesRequest):
    future_request_option: str


class _FutureAnthropicMessage(AnthropicMessage):
    future_message_option: str


class _FutureSystemBlock(SystemBlock):
    future_system_option: str


class _FutureAnthropicTool(AnthropicTool):
    future_tool_option: str


@pytest.mark.parametrize(
    ("candidate", "expected_path"),
    [
        (
            _FutureMessagesRequest(
                model="gpt-test",
                max_tokens=32,
                messages=[AnthropicMessage(role="user", content="hello")],
                future_request_option="must-not-disappear",
            ),
            "future_request_option",
        ),
        (
            MessagesRequest(
                model="gpt-test",
                max_tokens=32,
                messages=[
                    _FutureAnthropicMessage(
                        role="user",
                        content="hello",
                        future_message_option="must-not-disappear",
                    )
                ],
            ),
            "messages[0].future_message_option",
        ),
        (
            MessagesRequest(
                model="gpt-test",
                max_tokens=32,
                messages=[AnthropicMessage(role="user", content="hello")],
                system=[
                    _FutureSystemBlock(
                        text="system",
                        future_system_option="must-not-disappear",
                    )
                ],
            ),
            "system[0].future_system_option",
        ),
        (
            MessagesRequest(
                model="gpt-test",
                max_tokens=32,
                messages=[AnthropicMessage(role="user", content="hello")],
                tools=[
                    _FutureAnthropicTool(
                        name="lookup",
                        future_tool_option="must-not-disappear",
                    )
                ],
            ),
            "tools[0].future_tool_option",
        ),
    ],
)
def test_rejects_new_formal_model_fields_until_converter_consumes_them(
    candidate: MessagesRequest, expected_path: str
) -> None:
    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(candidate)

    assert caught.value.code == "unsupported_field"
    assert caught.value.field_path == expected_path


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("top_k", 40),
        ("stop_sequences", ["STOP"]),
        ("context_management", {"edits": []}),
    ],
)
def test_rejects_non_default_fields_without_responses_equivalent(field: str, value: object) -> None:
    payload = {
        "model": "gpt-test",
        "max_tokens": 32,
        "messages": [{"role": "user", "content": "hello"}],
        field: value,
    }

    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(payload)

    assert caught.value.code == "unsupported_field"
    assert caught.value.field_path == field


@pytest.mark.parametrize(
    "payload",
    [
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {
                    "name": "web_search",
                    "type": "web_search_20250305",
                    "input_schema": {"type": "object"},
                }
            ],
        },
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "server_tool_use",
                            "id": "srv_1",
                            "name": "web_search",
                            "input": {"query": "news"},
                        }
                    ],
                }
            ],
        },
    ],
)
def test_rejects_server_tools_instead_of_reviving_them(payload: dict[str, object]) -> None:
    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(payload)

    assert caught.value.code == "server_tool_not_supported"


def test_reconstructs_upstream_compatible_reasoning_carrier() -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "summary",
                            "signature": "copilot-api:synthetic-reasoning:v1:RU5DPT0",
                        }
                    ],
                }
            ],
        }
    )

    assert converted.wire["input"] == [
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "summary"}],
            "encrypted_content": "ENC==",
        }
    ]


def test_preserves_reasoning_cardinality_and_encrypted_only_items() -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "first",
                            "signature": "copilot-api:synthetic-reasoning:v1:RU5DLTE",
                        },
                        {
                            "type": "thinking",
                            "thinking": "",
                            "signature": "copilot-api:synthetic-reasoning:v1:RU5DLTI",
                        },
                    ],
                }
            ],
        }
    )

    assert converted.wire["input"] == [
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "first"}],
            "encrypted_content": "ENC-1",
        },
        {
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "ENC-2",
        },
    ]


def test_reasoning_forward_blocks_round_trip_through_messages_request_converter() -> None:
    reasoning_items: list[dict[str, object]] = [
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "first"}],
            "encrypted_content": "ENC-1",
        },
        {
            "type": "reasoning",
            "summary": [
                {"type": "summary_text", "text": "second"},
                {"type": "summary_text", "text": " + detail"},
            ],
            "encrypted_content": "ENC-2",
        },
        {
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "ENC-ONLY",
        },
    ]
    thinking_blocks = responses_reasoning_to_anthropic(reasoning_items)
    assert thinking_blocks is not None
    request = MessagesRequest.model_validate(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [{"role": "assistant", "content": thinking_blocks}],
        }
    )

    converted = convert_messages_request_to_responses(request)

    assert len(converted.wire["input"]) == len(reasoning_items)
    assert converted.wire["input"] == [
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "first"}],
            "encrypted_content": "ENC-1",
        },
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "second + detail"}],
            "encrypted_content": "ENC-2",
        },
        {
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "ENC-ONLY",
        },
    ]


@pytest.mark.parametrize(
    "payload",
    [
        "A",
        "YWJjZA=garbage",
        "_w",
        "/w",
        "+w",
        "你好",
    ],
)
def test_malformed_upstream_reasoning_carriers_are_dropped_with_classification(
    payload: str,
) -> None:
    # The 2026-08-07 carrier decision supersedes Node's permissive malformed vectors:
    # recognized malformed carriers must not restore summary or encrypted content.
    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "summary",
                            "signature": f"copilot-api:synthetic-reasoning:v1:{payload}",
                        }
                    ],
                }
            ],
        }
    )

    assert converted.wire["input"] == []
    assert converted.facts == (
        ConversionFact(
            field_path="messages[0].content[0]",
            disposition="degrade",
            reason="upstream_malformed_v1",
        ),
    )


def test_applies_one_request_scoped_tool_name_bijection_atomically() -> None:
    mapper = ToolNameMapper({"mcp.weather/tool": "mcp_weather_tool"})

    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "mcp.weather/tool",
                            "input": {"city": "Paris"},
                        }
                    ],
                }
            ],
            "tools": [
                {
                    "name": "mcp.weather/tool",
                    "input_schema": {"type": "object"},
                }
            ],
            "tool_choice": {"type": "tool", "name": "mcp.weather/tool"},
        },
        tool_name_mapper=mapper,
    )

    assert converted.wire["tools"] == [
        {
            "type": "function",
            "name": "mcp_weather_tool",
            "parameters": {"type": "object"},
        }
    ]
    assert converted.wire["input"] == [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "mcp_weather_tool",
            "arguments": '{"city":"Paris"}',
        }
    ]
    assert converted.wire["tool_choice"] == {
        "type": "function",
        "name": "mcp_weather_tool",
    }
    assert converted.tool_name_mapping == (
        ToolNameMappingFact(original_name="mcp.weather/tool", wire_name="mcp_weather_tool"),
    )
    assert mapper.restore("mcp_weather_tool") == "mcp.weather/tool"


def test_allows_inactive_mapping_collision_and_publishes_only_active_fact() -> None:
    mapper = ToolNameMapper({"first.tool": "shared_name", "second/tool": "shared_name"})

    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"name": "first.tool", "input_schema": {"type": "object"}}],
        },
        tool_name_mapper=mapper,
    )

    assert converted.tool_name_mapping == (
        ToolNameMappingFact(original_name="first.tool", wire_name="shared_name"),
    )


def test_rejects_active_non_bijective_tool_name_mapping() -> None:
    mapper = ToolNameMapper({"first.tool": "shared_name", "second/tool": "shared_name"})

    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "gpt-test",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "hello"}],
                "tools": [
                    {"name": "first.tool", "input_schema": {"type": "object"}},
                    {"name": "second/tool", "input_schema": {"type": "object"}},
                ],
            },
            tool_name_mapper=mapper,
        )

    assert caught.value.code == "tool_name_collision"
    assert caught.value.field_path == "tool_names"


def test_rejects_reusing_request_scoped_tool_name_mapper() -> None:
    mapper = ToolNameMapper({"first.tool": "first_tool"})
    payload = {
        "model": "gpt-test",
        "max_tokens": 32,
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [{"name": "first.tool", "input_schema": {"type": "object"}}],
    }

    convert_messages_request_to_responses(payload, tool_name_mapper=mapper)
    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(payload, tool_name_mapper=mapper)

    assert caught.value.code == "tool_name_collision"
    assert caught.value.field_path == "tool_names"


def test_rejects_tool_declaration_collision_after_mapping() -> None:
    mapper = ToolNameMapper({"first.tool": "second_tool"})

    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "gpt-test",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "hello"}],
                "tools": [
                    {"name": "first.tool", "input_schema": {"type": "object"}},
                    {"name": "second_tool", "input_schema": {"type": "object"}},
                ],
            },
            tool_name_mapper=mapper,
        )

    assert caught.value.code == "tool_name_collision"
    assert caught.value.field_path == "tool_names"


def test_rejects_identity_collision_across_declaration_and_historical_call() -> None:
    mapper = ToolNameMapper({"first.tool": "shared_name"})

    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "gpt-test",
                "max_tokens": 32,
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call_1",
                                "name": "shared_name",
                                "input": {},
                            }
                        ],
                    }
                ],
                "tools": [{"name": "first.tool", "input_schema": {"type": "object"}}],
            },
            tool_name_mapper=mapper,
        )

    assert caught.value.code == "tool_name_collision"
    assert caught.value.field_path == "tool_names"


def test_does_not_publish_unused_tool_name_mappings() -> None:
    mapper = ToolNameMapper({"unused.tool": "lookup"})

    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"name": "lookup", "input_schema": {"type": "object"}}],
        },
        tool_name_mapper=mapper,
    )

    assert converted.tool_name_mapping == ()
    assert mapper.restore("lookup") == "lookup"


def test_degrades_foreign_thinking_without_forwarding_signature() -> None:
    converted = convert_messages_request_to_responses(
        {
            "model": "gpt-test",
            "max_tokens": 32,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "private",
                            "signature": "foreign-signature",
                        }
                    ],
                }
            ],
        }
    )

    assert converted.wire["input"] == []
    assert converted.facts == (
        ConversionFact(
            field_path="messages[0].content[0]",
            disposition="degrade",
            reason="foreign",
        ),
    )


def test_rejects_unknown_content_block() -> None:
    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "gpt-test",
                "max_tokens": 32,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "document", "source": {"data": "x"}}],
                    }
                ],
            }
        )

    assert caught.value.code == "unsupported_content_block"
    assert caught.value.field_path == "messages[0].content[0]"


def test_rejects_field_that_belongs_to_a_different_content_block_variant() -> None:
    with pytest.raises(RequestConversionError) as caught:
        convert_messages_request_to_responses(
            {
                "model": "gpt-test",
                "max_tokens": 32,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "hello",
                                "tool_use_id": "must-not-disappear",
                            }
                        ],
                    }
                ],
            }
        )

    assert caught.value.code == "unsupported_field"
    assert caught.value.field_path == "messages[0].content[0].tool_use_id"
