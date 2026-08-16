import re
from typing import Any

import pytest

from app.pipeline.request import WireFormat
from app.pipeline.translation_driver import (
    TranslatorNotFound,
    TranslatorRegistry,
    default_registry,
    from_anthropic_messages,
    inbound_name,
    outbound_name,
    to_openai_responses,
)

# The worked example from model-translation.md.
ANTHROPIC_SYSTEM: list[dict[str, Any]] = [
    {
        "type": "text",
        "text": "You are Claude Code, Anthropic's official CLI for Claude.",
        "cache_control": {"type": "ephemeral"},
    },
    {
        "type": "text",
        "text": "\nYou are an interactive agent.",
        "cache_control": {"type": "ephemeral"},
    },
]

ANTHROPIC_REQUEST: dict[str, Any] = {
    "model": "claude-model",
    "system": ANTHROPIC_SYSTEM,
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 100,
    "stream": True,
}


def test_system_becomes_one_instructions_entry_with_the_system_role() -> None:
    payload, _ = default_registry().translate(
        ANTHROPIC_REQUEST,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    instructions = payload["instructions"]
    assert len(instructions) == 1
    assert instructions[0]["role"] == "system"
    assert [block["text"] for block in instructions[0]["content"]] == [
        "You are Claude Code, Anthropic's official CLI for Claude.",
        "\nYou are an interactive agent.",
    ]


def test_per_block_metadata_survives_the_crossing() -> None:
    # cache_control lives on each block; flattening the system prompt to a string would lose it.
    payload, _ = default_registry().translate(
        ANTHROPIC_REQUEST,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    content = payload["instructions"][0]["content"]
    assert all(block["cache_control"] == {"type": "ephemeral"} for block in content)


def test_messages_and_limits_map_to_the_responses_names() -> None:
    payload, _ = default_registry().translate(
        ANTHROPIC_REQUEST,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["input"] == [{"role": "user", "content": "hi"}]
    assert payload["max_output_tokens"] == 100
    assert payload["stream"] is True
    assert "messages" not in payload
    assert "max_tokens" not in payload


def test_round_trip_through_the_intermediate_preserves_the_request() -> None:
    # A single direction can drop a field without any assertion noticing.
    # The round trip is what makes an omission visible.
    registry = default_registry()
    crossed, _ = registry.translate(
        ANTHROPIC_REQUEST,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    back, _ = registry.translate(
        crossed,
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert back["model"] == ANTHROPIC_REQUEST["model"]
    assert back["messages"] == ANTHROPIC_REQUEST["messages"]
    assert back["max_tokens"] == 100
    assert back["stream"] is True
    assert [block["text"] for block in back["system"]] == [
        block["text"] for block in ANTHROPIC_SYSTEM
    ]


def test_unmodelled_fields_survive_a_same_format_round_trip() -> None:
    payload = {**ANTHROPIC_REQUEST, "metadata": {"user_id": "u1"}, "top_p": 0.9}
    registry = default_registry()
    result, _ = registry.translate(
        payload,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert result["metadata"] == {"user_id": "u1"}
    assert result["top_p"] == 0.9


def test_string_system_prompt_is_accepted() -> None:
    request = from_anthropic_messages({"model": "m", "system": "be brief"})
    assert [block.text for block in request.system] == ["be brief"]
    assert request.conversion.lossless is True


def test_instructions_given_as_a_string_are_accepted() -> None:
    payload, semantic = default_registry().translate(
        {"model": "m", "instructions": "be brief"},
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert payload["system"][0]["text"] == "be brief"
    assert semantic.conversion.lossless is True


def test_a_non_system_instruction_role_is_recorded_as_a_loss() -> None:
    # Capability parity is not required.
    # What cannot be carried must still be named rather than silently dropped.
    _, semantic = default_registry().translate(
        {
            "model": "m",
            "instructions": [
                {"role": "system", "content": "kept"},
                {"role": "developer", "content": "dropped"},
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert semantic.conversion.lossless is False
    assert any("developer" in loss for loss in semantic.conversion.losses)


def test_malformed_system_entry_is_recorded_as_a_loss() -> None:
    request = from_anthropic_messages({"model": "m", "system": [123]})
    assert request.conversion.lossless is False


def test_absent_optional_fields_are_not_invented() -> None:
    payload = to_openai_responses(from_anthropic_messages({"model": "m", "messages": []}))
    assert "instructions" not in payload
    assert "tools" not in payload
    assert "stream" not in payload
    assert "max_output_tokens" not in payload
    assert "temperature" not in payload


def test_registry_reports_the_spec_names() -> None:
    names = default_registry().names
    assert inbound_name(WireFormat.ANTHROPIC_MESSAGES) == "inbound.from-anthropic-messages"
    assert outbound_name(WireFormat.OPENAI_RESPONSES) == "outbound.to-openai-responses"
    assert "inbound.from-anthropic-messages" in names
    assert "outbound.to-openai-responses" in names


def test_missing_translator_is_reported_before_any_conversion_runs() -> None:
    registry = TranslatorRegistry()
    registry.register_inbound(WireFormat.ANTHROPIC_MESSAGES, from_anthropic_messages)
    with pytest.raises(TranslatorNotFound, match=re.escape("outbound.to-openai-responses")):
        registry.translate(
            ANTHROPIC_REQUEST,
            source=WireFormat.ANTHROPIC_MESSAGES,
            target=WireFormat.OPENAI_RESPONSES,
        )


def test_unregistered_inbound_format_is_reported() -> None:
    with pytest.raises(TranslatorNotFound, match=re.escape("inbound.from-openai-embeddings")):
        default_registry().translate(
            {},
            source=WireFormat.OPENAI_EMBEDDINGS,
            target=WireFormat.ANTHROPIC_MESSAGES,
        )
