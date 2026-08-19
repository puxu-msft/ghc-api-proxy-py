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
from app.pipeline.translation_driver.semantic import LossCode

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


def test_system_becomes_a_single_instructions_string() -> None:
    """The one shape the Copilot Responses endpoint accepts.

    This assertion used to require `model-translation.md`'s worked example — one entry with
    `role: system` and a `content` list of blocks. Measured 2026-08-18, that shape and five other
    array forms all get `failed to parse request`; only a string is accepted. The conflict with
    the authored spec is written up in
    `docs/.human-controlled-candidates/instructions-shape-conflict.md` and is the user's to rule
    on — this test records what upstream does, not a preference.
    """
    payload, _ = default_registry().translate(
        ANTHROPIC_REQUEST,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["instructions"] == (
        "You are Claude Code, Anthropic's official CLI for Claude.\n\n"
        "\nYou are an interactive agent."
    )


def test_the_lost_block_metadata_is_named_rather_than_dropped() -> None:
    """`cache_control` cannot survive the string form, so it has to be reported.

    The guard this replaces asserted the metadata crossed intact. It cannot any more. What is
    worth guarding instead is that the loss is visible — not because caching breaks, which was
    measured and does not (the endpoint caches by prefix on its own: the same 24082-token body
    sent twice reported `cached_tokens` 0 then 24079), but because a field that silently vanishes
    at a format boundary is how the next one gets missed.
    """
    _, semantic = default_registry().translate(
        ANTHROPIC_REQUEST,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert semantic.conversion.has(LossCode.SYSTEM_METADATA_NOT_CARRIED), semantic.conversion.losses
    assert any("cache_control" in loss.detail for loss in semantic.conversion.losses)


def test_anthropic_tools_become_responses_function_tools() -> None:
    """Passing Anthropic's `input_schema` through earns `One of the tools requested is invalid.`"""
    payload, _ = default_registry().translate(
        {
            **ANTHROPIC_REQUEST,
            "tools": [
                {
                    "name": "get_time",
                    "description": "Return the current time.",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["tools"] == [
        {
            "type": "function",
            "name": "get_time",
            "description": "Return the current time.",
            "parameters": {"type": "object", "properties": {}},
        }
    ]


def test_anthropic_only_fields_do_not_reach_a_responses_body() -> None:
    """An unclaimed key is unclaimed *in its own format*, and elsewhere it is a parse error.

    `context_management` is the measured case: the Responses endpoint answers
    `failed to parse request` to a body carrying it, so replaying every extension into whatever
    format is being written is not merely untidy.
    """
    payload, semantic = default_registry().translate(
        {**ANTHROPIC_REQUEST, "context_management": {"edits": []}},
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert "context_management" not in payload
    assert semantic.conversion.has(LossCode.EXTENSIONS_NOT_CARRIED), semantic.conversion.losses
    assert any("context_management" in loss.detail for loss in semantic.conversion.losses)


def test_messages_and_limits_map_to_the_responses_names() -> None:
    payload, _ = default_registry().translate(
        ANTHROPIC_REQUEST,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    # Anthropic's block shape does not survive as-is: upstream answers `Invalid value: 'text'`.
    assert payload["input"] == [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}
    ]
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
    # The string content comes back as an explicit text block, which is the same message said in
    # the spelling the typed model round-trips through.
    assert back["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    ]
    assert back["max_tokens"] == 100
    assert back["stream"] is True
    # The system prompt returns as one block rather than two. That is the string `instructions`
    # form doing what it must — the block boundary has nowhere to live in it. Asserted as a
    # single joined block rather than dropped from the test, so a future change that loses the
    # *text* still fails.
    assert [block["text"] for block in back["system"]] == [
        "You are Claude Code, Anthropic's official CLI for Claude.\n\n"
        "\nYou are an interactive agent."
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
    assert semantic.conversion.has(LossCode.INSTRUCTIONS_ROLE_NOT_CARRIED)


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


def test_the_system_prompt_placement_is_configurable() -> None:
    """The seam exists before the second placement does.

    `instructions-joint-string` is the only value today; the point of naming it is that adding
    `as-role-system` later changes a mapping entry rather than the shape of every call site. The
    setting is bound into the registry, so this asserts the wiring reaches the translator rather
    than that the default happens to be right.
    """
    from app.config.schema import ModelTranslationConfig, ToOpenAiResponsesConfig
    from app.pipeline.translation_driver import default_registry as build

    configured = build(
        ModelTranslationConfig(
            to_openai_responses=ToOpenAiResponsesConfig(
                system_prompts="instructions-joint-string"
            )
        )
    )
    payload, _ = configured.translate(
        ANTHROPIC_REQUEST,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert isinstance(payload["instructions"], str)


def test_an_unregistered_placement_fails_loudly() -> None:
    """A fallback would silently reshape the request instead.

    Same reasoning as `layout_strategy`: the config admits exactly the spellings the schema
    defines, so an unmapped one is a bug in this module, not an operator's typo.
    """
    request = from_anthropic_messages(ANTHROPIC_REQUEST)
    with pytest.raises(KeyError):
        to_openai_responses(request, system_prompts="as-role-system")  # type: ignore[arg-type]


# A conversation with the block types real traffic actually carries. Counted from three rehydrated
# production requests on 2026-08-18: 856 tool_use, 856 tool_result, 490 thinking, 450 text.
CONVERSATION: dict[str, Any] = {
    "model": "m",
    "max_tokens": 100,
    "messages": [
        {"role": "user", "content": [{"type": "text", "text": "read it"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "pondering", "signature": "REAL_ANTHROPIC_SIG"},
                {"type": "text", "text": "looking now"},
                {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {"path": "/x"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_1",
                    "content": [{"type": "text", "text": "file body"}],
                }
            ],
        },
    ],
}


def test_a_real_conversation_becomes_responses_input_items() -> None:
    """The shapes measured off the existing service for the same conversation.

    Anthropic's own block spelling reaching upstream is what produced
    `Invalid value: 'text'. Supported values are: 'input_text', ...` on every real request.
    """
    payload, _ = default_registry().translate(
        CONVERSATION,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["input"] == [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "read it"}]},
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "looking now"}],
        },
        {
            "type": "function_call",
            "call_id": "tu_1",
            "name": "Read",
            "arguments": '{"path": "/x"}',
        },
        {"type": "function_call_output", "call_id": "tu_1", "output": "file body"},
    ]


def test_tool_arguments_cross_as_a_json_string() -> None:
    """Asserted on its own because an object here is a 400 and the type checker cannot see it."""
    payload, _ = default_registry().translate(
        CONVERSATION,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    call = next(item for item in payload["input"] if item["type"] == "function_call")
    assert isinstance(call["arguments"], str)


def test_a_real_anthropic_signature_is_refused_rather_than_forged() -> None:
    """The safety property, not a formatting one.

    `encrypted_content` is a value only the Responses endpoint can produce. Writing Anthropic's
    signature into it would hand upstream something it never issued and cannot verify, so the
    reasoning item is dropped and the refusal is recorded instead.
    """
    payload, semantic = default_registry().translate(
        CONVERSATION,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert not [item for item in payload["input"] if item["type"] == "reasoning"]
    assert semantic.conversion.has(LossCode.REASONING_STATE_NOT_PORTABLE)


def test_a_carrier_this_proxy_issued_does_cross() -> None:
    """The other half of the same rule: recovering our own value is not inventing one."""
    from app.anthropic.thinking.reasoning_carrier import encode_reasoning_carrier

    signed = encode_reasoning_carrier("upstream-encrypted-payload")
    payload, semantic = default_registry().translate(
        {
            **CONVERSATION,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "recalled", "signature": signed}
                    ],
                }
            ],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    reasoning = next(item for item in payload["input"] if item["type"] == "reasoning")
    assert reasoning["encrypted_content"] == "upstream-encrypted-payload"
    assert not semantic.conversion.has(LossCode.REASONING_STATE_NOT_PORTABLE)


def test_an_unknown_block_is_carried_rather_than_dropped() -> None:
    """A format grows block types faster than a translator learns them.

    Same-format crossing must return what it was given, or a conversation quietly loses a turn.
    """
    payload, _ = default_registry().translate(
        {
            "model": "m",
            "messages": [
                {"role": "user", "content": [{"type": "some_future_block", "payload": 1}]}
            ],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert payload["messages"][0]["content"] == [{"type": "some_future_block", "payload": 1}]


def test_responses_input_reads_back_into_the_same_blocks() -> None:
    """Both directions, since a reader that cannot undo its writer is only half a bridge."""
    crossed, _ = default_registry().translate(
        CONVERSATION,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    back, _ = default_registry().translate(
        crossed,
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    kinds = [
        block["type"] for message in back["messages"] for block in message["content"]
    ]
    assert kinds == ["text", "text", "tool_use", "tool_result"]
    call = next(
        block
        for message in back["messages"]
        for block in message["content"]
        if block["type"] == "tool_use"
    )
    assert call["input"] == {"path": "/x"}
