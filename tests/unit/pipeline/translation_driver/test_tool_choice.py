"""Regressions where declaration rewrites and tool selection must agree."""

from typing import Any

import pytest

from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.registry import default_registry
from app.pipeline.translation_driver.semantic import TranslationRefused


def responses_request(choice: object) -> dict[str, Any]:
    return {
        "model": "m",
        "input": [],
        "tools": [
            {
                "type": "function",
                "name": "ToolSearch",
                "description": "Find a tool",
                "parameters": {"type": "object"},
            },
            {
                "type": "function",
                "name": "lookup",
                "parameters": {"type": "object"},
                "defer_loading": True,
            },
        ],
        "tool_choice": choice,
        "parallel_tool_calls": False,
    }


@pytest.mark.parametrize("extra", [{}, {"future_field": 1}])
def test_equal_count_promotion_cannot_leave_a_forced_old_name(extra: dict[str, Any]) -> None:
    request = responses_request({"type": "function", "name": "ToolSearch", **extra})
    with pytest.raises(TranslationRefused, match="became tool_search") as caught:
        default_registry().translate(
            request, source=WireFormat.OPENAI_RESPONSES, target=WireFormat.OPENAI_RESPONSES
        )
    assert caught.value.code == "tool-choice-not-supported"
    assert caught.value.field_path == "tool_choice"


@pytest.mark.parametrize("extra", [{}, {"future_field": 1}])
def test_unaffected_function_choice_survives_another_tools_promotion(extra: dict[str, Any]) -> None:
    choice = {"type": "function", "name": "lookup", **extra}
    request = responses_request(choice)
    payload, _ = default_registry().translate(
        request, source=WireFormat.OPENAI_RESPONSES, target=WireFormat.OPENAI_RESPONSES
    )
    assert len(payload["tools"]) == len(request["tools"])
    assert payload["tools"][0]["type"] == "tool_search"
    assert payload["tools"][1]["name"] == "lookup"
    assert payload["tool_choice"] == choice
    assert payload["parallel_tool_calls"] is False


@pytest.mark.parametrize("choice", [None, {"type": "function", "name": ""}, {"type": []}])
def test_unclaimed_same_format_choice_without_rewrites_is_untouched(choice: object) -> None:
    payload, _ = default_registry().translate(
        {"model": "m", "input": [], "tool_choice": choice},
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["tool_choice"] == choice


@pytest.mark.parametrize("mode", ["auto", "required"])
def test_an_allowlist_cannot_refer_to_a_promoted_function(mode: str) -> None:
    choice = {"type": "allowed_tools", "mode": mode, "tools": [{"type": "function", "name": "ToolSearch"}]}
    with pytest.raises(TranslationRefused, match="allowed_tools refers to rewritten tool ToolSearch"):
        default_registry().translate(
            responses_request(choice),
            source=WireFormat.OPENAI_RESPONSES,
            target=WireFormat.OPENAI_RESPONSES,
        )


def test_an_unaffected_allowlist_survives_another_tools_promotion() -> None:
    choice = {"type": "allowed_tools", "mode": "required", "tools": [{"type": "function", "name": "lookup"}]}
    payload, _ = default_registry().translate(
        responses_request(choice),
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["tool_choice"] == choice
    assert payload["parallel_tool_calls"] is False


def test_web_search_repoint_does_not_discard_unknown_choice_fields() -> None:
    with pytest.raises(TranslationRefused, match="unsupported fields"):
        default_registry().translate(
            {
                "model": "m",
                "input": [],
                "tools": [{"type": "web_search_20250305", "name": "WebSearch"}],
                "tool_choice": {"type": "function", "name": "WebSearch", "future_field": 1},
            },
            source=WireFormat.OPENAI_RESPONSES,
            target=WireFormat.OPENAI_RESPONSES,
        )


@pytest.mark.parametrize("builtin_type", ["web_search_20250305", "tool_search_tool_regex_20251119"])
def test_a_same_named_function_remains_selectable_on_the_same_format(builtin_type: str) -> None:
    choice = {"type": "function", "name": "WebSearch"}
    payload, _ = default_registry().translate(
        {
            "model": "m",
            "input": [],
            "tools": [
                {"type": builtin_type, "name": "WebSearch"},
                {"type": "function", "name": "WebSearch", "parameters": {"type": "object"}},
            ],
            "tool_choice": choice,
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["tool_choice"] == choice
    assert any(tool.get("name") == "WebSearch" for tool in payload["tools"])


@pytest.mark.parametrize(
    "first,second",
    [
        ({"input_schema": {"type": "object"}}, {"type": "tool_search_tool_regex_20251119"}),
        ({"type": "web_search_20250305"}, {"type": "tool_search_tool_regex_20251119"}),
        ({"input_schema": {"type": "object"}}, {"type": "web_search_20250305"}),
    ],
)
def test_cross_format_choice_rejects_a_name_shared_by_declaration_kinds(
    first: dict[str, Any], second: dict[str, Any]
) -> None:
    with pytest.raises(TranslationRefused, match="ambiguous tool choice"):
        default_registry().translate(
            {
                "model": "m",
                "messages": [],
                "tools": [{"name": "shared", **first}, {"name": "shared", **second}],
                "tool_choice": {"type": "tool", "name": "shared"},
            },
            source=WireFormat.ANTHROPIC_MESSAGES,
            target=WireFormat.OPENAI_RESPONSES,
        )


@pytest.mark.parametrize("extra", [{}, {"future_field": 1}])
def test_history_only_search_name_does_not_count_as_a_rewritten_declaration(extra: dict[str, Any]) -> None:
    choice = {"type": "function", "name": "SearchOld", **extra}
    request = responses_request(choice)
    request["tools"] = request["tools"][1:]
    request["input"] = [
        {"type": "function_call", "call_id": "old", "name": "SearchOld", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "old", "output": [{"type": "tool_reference", "tool_name": "lookup"}]},
    ]
    payload, semantic = default_registry().translate(
        request, source=WireFormat.OPENAI_RESPONSES, target=WireFormat.OPENAI_RESPONSES
    )
    assert semantic.client_search_tool == "SearchOld"
    assert not any(tool["type"] == "tool_search" for tool in payload["tools"])
    assert payload["tool_choice"] == choice


@pytest.mark.parametrize(
    "choice",
    [
        {"type": "function", "name": "missing"},
        {"type": "allowed_tools", "tools": [{"type": "function", "name": "lookup"}]},
    ],
)
def test_unrepresentable_responses_choices_are_refused_on_the_anthropic_leg(choice: object) -> None:
    with pytest.raises(TranslationRefused) as caught:
        default_registry().translate(
            {
                "model": "m",
                "input": [],
                "tools": [{"type": "function", "name": "lookup", "parameters": {"type": "object"}}],
                "tool_choice": choice,
            },
            source=WireFormat.OPENAI_RESPONSES,
            target=WireFormat.ANTHROPIC_MESSAGES,
        )
    assert caught.value.code == "tool-choice-not-supported"
    assert caught.value.field_path == "tool_choice"
