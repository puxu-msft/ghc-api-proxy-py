import json
import re
from typing import Any, cast

import pytest

from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.anthropic_messages import from_anthropic_messages
from app.pipeline.translation_driver.openai_responses import to_openai_responses
from app.pipeline.translation_driver.reasoning_carrier import decode_reasoning_carrier
from app.pipeline.translation_driver.registry import (
    TranslatorNotFound,
    TranslatorRegistry,
    default_registry,
    inbound_name,
    outbound_name,
)
from app.pipeline.translation_driver.semantic import (
    LossCode,
    SemanticRequest,
    TranslationRefused,
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


def test_system_becomes_a_single_instructions_string() -> None:
    """The one shape the Copilot Responses endpoint accepts.

    This assertion used to require `model-translation.md`'s worked example — one entry with
    `role: system` and a `content` list of blocks. Measured 2026-08-18, that shape and five other
    array forms all get `failed to parse request`; only a string is accepted. The conflict with
    the authored spec is written up in
    `.dev/human-controlled-docs-candidates/instructions-shape-conflict.md` and is the user's to rule
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
    configured = default_registry(
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
    from app.pipeline.translation_driver.reasoning_carrier import encode_reasoning_carrier

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


RESPONSES_RESPONSE: dict[str, Any] = {
    "id": "resp_1",
    "model": "gpt-5.6-terra",
    "status": "completed",
    "output": [
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "thought"}],
            "encrypted_content": "ENC123",
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "hi"}],
        },
        {
            "type": "function_call",
            "call_id": "call_9",
            "name": "Read",
            "arguments": '{"path":"/y"}',
        },
    ],
    "usage": {"input_tokens": 5, "output_tokens": 7},
}


def test_a_responses_reasoning_item_reaches_anthropic_with_its_state_intact() -> None:
    """The signature used to be written as `""`, which threw the continuation state away.

    `encrypted_content` has no Anthropic spelling, so it rides inside a carrier this proxy signs —
    the reverse of the refusal on the way out, and legitimate for the same reason: the value is
    upstream's own, recovered rather than invented.
    """
    payload, _ = default_registry().translate_response(
        RESPONSES_RESPONSE,
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    thinking = next(block for block in payload["content"] if block["type"] == "thinking")
    assert thinking["thinking"] == "thought"
    assert thinking["signature"], "the continuation state was dropped"
    assert decode_reasoning_carrier(thinking["signature"]).encrypted_content == "ENC123"


def test_a_reply_with_nothing_to_say_carries_no_content_rather_than_an_empty_block() -> None:
    """The two delivery paths used to answer this differently, and one of the answers poisoned the next turn.

    `spec.md:266` permits either — such a reply *may* carry the protocol's empty text block — so it is measurement that decides. The client stores this turn and replays it, and upstream refuses an assistant turn holding a blank text block (400, `messages: text content blocks must be non-empty`) while accepting one whose content is empty (200, both mid-conversation and last): `exp/260820-empty-text-probe/` F3 against F6 and F4, 2026-08-20.

    The streaming path already answers this way — it opens no content block when there is nothing to open. This pins the buffered one to the same answer.
    """
    payload, _ = default_registry().translate_response(
        {"id": "resp_1", "model": "gpt-model", "output": [], "status": "completed"},
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )

    assert payload["content"] == []
    assert payload["role"] == "assistant"


def test_a_response_round_trip_keeps_the_reasoning_payload() -> None:
    """Losing it here is invisible until the next turn cannot continue the reasoning."""
    registry = default_registry()
    crossed, _ = registry.translate_response(
        RESPONSES_RESPONSE,
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    back, semantic = registry.translate_response(
        crossed,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    reasoning = next(item for item in back["output"] if item["type"] == "reasoning")
    assert reasoning["encrypted_content"] == "ENC123"
    assert semantic.conversion.lossless, semantic.conversion.losses


def test_a_response_tool_call_leaves_as_a_json_string() -> None:
    """It used to leave as an object, which the wire refuses."""
    payload, _ = default_registry().translate_response(
        RESPONSES_RESPONSE,
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    tool_use = next(block for block in payload["content"] if block["type"] == "tool_use")
    assert tool_use["input"] == {"path": "/y"}

    back, _ = default_registry().translate_response(
        payload,
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    call = next(item for item in back["output"] if item["type"] == "function_call")
    assert call["arguments"] == '{"path": "/y"}'


def test_a_tool_call_in_the_response_sets_the_anthropic_stop_reason() -> None:
    payload, _ = default_registry().translate_response(
        RESPONSES_RESPONSE,
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert payload["stop_reason"] == "tool_use"


def test_an_anthropic_web_search_declaration_becomes_the_spelling_this_endpoint_runs() -> None:
    """`Invalid value: 'web_search_20250305'` — 400, measured 2026-08-20 against gpt-5.6-sol, while `{"type": "web_search"}` returns 200 and really executes the search.

    The declaration carries no `input_schema`, which is what the function-tool rewrite keys on, so it used to travel across untouched and cost the whole turn.

    The function tool beside it is the other half: translating the declaration must not disturb the client's real tools.
    """
    payload, _ = default_registry().translate(
        {
            **ANTHROPIC_REQUEST,
            "tools": [
                {"type": "web_search_20250305", "name": "web_search"},
                {"name": "get_time", "input_schema": {"type": "object"}},
            ],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["tools"] == [
        {"type": "web_search"},
        {"type": "function", "name": "get_time", "parameters": {"type": "object"}},
    ]


def test_the_next_dated_version_of_the_declaration_maps_too() -> None:
    """Anthropic dates its server tools, so matching today's value literally would go quiet on the day it issues the next one."""
    request = SemanticRequest(
        model="gpt-5.6-sol",
        tools=[{"type": "web_search_20991231", "name": "web_search"}],
    )
    assert to_openai_responses(request)["tools"] == [{"type": "web_search"}]


def test_the_endpoints_own_web_search_spellings_are_left_alone() -> None:
    """The reason the predicate reads the date suffix and not the `web_search_` prefix.

    All three are values this endpoint accepts — the last two appear by name in the enumeration it prints when it refuses one — and a prefix test would have rewritten them on a Responses-to-Responses crossing that had every right to them.
    """
    request = SemanticRequest(
        model="gpt-5.6-sol",
        tools=[
            {"type": "web_search"},
            {"type": "web_search_preview"},
            {"type": "web_search_preview_2025_03_11"},
        ],
    )
    payload = to_openai_responses(request)
    assert payload["tools"] == request.tools
    assert request.conversion.lossless, request.conversion.losses


def test_a_user_location_travels_but_an_unknown_sub_key_does_not() -> None:
    """`user_location` is echoed back verbatim in the 200, so it is forwarded; an unknown sub-parameter is measured to 400 the whole request, so it is removed rather than risked."""
    request = SemanticRequest(
        model="gpt-5.6-sol",
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "user_location": {
                    "type": "approximate",
                    "city": "Toronto",
                    "region": None,
                    "invented_key": "x",
                },
            }
        ],
    )
    assert to_openai_responses(request)["tools"] == [
        {
            "type": "web_search",
            # `region: None` is kept: upstream's own default echo contains nulls, so they are legal.
            "user_location": {"type": "approximate", "city": "Toronto", "region": None},
        }
    ]
    assert request.conversion.has(LossCode.SERVER_TOOL_CONSTRAINT_DROPPED)


# The declaration every real Claude Code web search sub-request sends. Measured over 190 of them on
# 2026-08-20: the shape is identical every time, and `allowed_domains` is non-empty in all 190 —
# the client attaches it unconditionally, as part of how its WebSearch tool is built.
REAL_WEB_SEARCH_DECLARATION: dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 8,
    "allowed_domains": ["docs.anthropic.com"],
    "blocked_domains": [],
}


def test_by_default_a_domain_restriction_is_dropped_so_the_search_can_still_run() -> None:
    """The default is `drop_fields`, and the reason is what the client actually sends.

    The spec's D1 ruling chose `error`, reading a domain list as a restriction deliberately added for one search. All 190 measured sub-requests carry one, so under `error` web search is not occasionally refused — it never works at all. That is not the trade the ruling was making, and the setting exists so it can be made either way.
    """
    request = SemanticRequest(model="gpt-5.6-sol", tools=[dict(REAL_WEB_SEARCH_DECLARATION)])
    assert to_openai_responses(request)["tools"] == [{"type": "web_search"}]
    assert request.conversion.has(LossCode.SERVER_TOOL_CONSTRAINT_DROPPED)


def test_the_error_setting_refuses_before_upstream_is_called() -> None:
    """What the D1 ruling asked for, still available: the restriction cannot be sent, and its loss cannot be detected afterwards, so refusing is a defensible answer for an operator who wants it."""
    request = SemanticRequest(model="gpt-5.6-sol", tools=[dict(REAL_WEB_SEARCH_DECLARATION)])
    with pytest.raises(TranslationRefused) as caught:
        to_openai_responses(request, web_search_domain_restrictions="error")
    assert caught.value.code == "server_tool_constraint_not_representable"
    assert caught.value.field_path == "tools.web_search_20250305.allowed_domains"



def test_an_empty_domain_restriction_restricts_nothing_and_does_not_refuse() -> None:
    """An empty list narrows nothing, so nothing is lost by not sending it. Refusing over one would fail a request that asked for no restriction at all."""
    request = SemanticRequest(
        model="gpt-5.6-sol",
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "blocked_domains": []},
        ],
    )
    assert to_openai_responses(request)["tools"] == [{"type": "web_search"}]
    assert request.conversion.has(LossCode.SERVER_TOOL_CONSTRAINT_DROPPED)


def test_max_uses_is_dropped_rather_than_refused() -> None:
    """The other side of the line. It cannot be sent either, but it is a ceiling on *cost*: losing it means more searches and more latency, and reverses no claim the client made. Upstream reports `tool_usage.web_search.num_requests` back, so what happened stays observable."""
    request = SemanticRequest(
        model="gpt-5.6-sol",
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
    )
    assert to_openai_responses(request)["tools"] == [{"type": "web_search"}]
    assert any(
        "max_uses" in loss.detail
        for loss in request.conversion.losses
        if loss.code is LossCode.SERVER_TOOL_CONSTRAINT_DROPPED
    ), request.conversion.losses


def test_a_field_outside_the_allowed_set_refuses_rather_than_being_stripped() -> None:
    """An unknown field today is a field with meaning tomorrow. Removing one silently turns whatever it asked for into a no-op — the same failure as the domain lists, arriving later and with nobody watching for it."""
    request = SemanticRequest(
        model="gpt-5.6-sol",
        tools=[{"type": "web_search_20250305", "name": "web_search", "future_field": 1}],
    )
    with pytest.raises(TranslationRefused) as caught:
        to_openai_responses(request)
    assert caught.value.code == "unsupported_field"
    assert caught.value.field_path == "tools.web_search_20250305.future_field"


def test_two_declarations_become_one_builtin() -> None:
    """Two identical `{"type": "web_search"}` entries is a shape upstream has never been asked about, and the second says nothing the first did not."""
    request = SemanticRequest(
        model="gpt-5.6-sol",
        tools=[
            {"type": "web_search_20250305", "name": "web_search"},
            {"type": "web_search_20260101", "name": "web_search"},
        ],
    )
    assert to_openai_responses(request)["tools"] == [{"type": "web_search"}]
    assert request.conversion.has(LossCode.SERVER_TOOL_CONSTRAINT_DROPPED)


def test_a_choice_that_named_the_declaration_follows_it_into_the_builtin_spelling() -> None:
    """A builtin tool object has no `name`, so a choice that named the declaration would point at nothing and cost the turn on its own account — the mapping trading one rejection for another.

    `{"type": "web_search"}` in the choice position is measured 200, echoed back normalised as `web_search_preview`, with `num_requests` of 1 and a `web_search_call` in the output: it really does force the search.
    """
    payload, _ = default_registry().translate(
        {
            "model": "gpt-5.6-sol",
            "input": [],
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "tool_choice": {"type": "function", "name": "web_search"},
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["tools"] == [{"type": "web_search"}]
    assert payload["tool_choice"] == {"type": "web_search"}


def test_a_choice_that_still_names_a_declared_tool_is_left_alone() -> None:
    """The control. Rewriting a choice that resolves would change what the client asked for, to no purpose."""
    payload, _ = default_registry().translate(
        {
            "model": "gpt-5.6-sol",
            "input": [],
            "tools": [
                {"type": "web_search_20250305", "name": "web_search"},
                {"type": "function", "name": "get_time", "parameters": {"type": "object"}},
            ],
            "tool_choice": {"type": "function", "name": "get_time"},
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["tool_choice"] == {"type": "function", "name": "get_time"}


def test_web_fetch_is_left_for_its_own_repair() -> None:
    """This endpoint refuses `web_fetch` under every spelling tried, so unlike web search there is nothing to map it to.

    `hosted-web-search-spec.md` §13 has that family refused locally rather than removed quietly, which is its own piece of work. Asserted rather than left implicit because the obvious edit is to add `web_fetch_` to the family list — it is one word and it looks like a completion.
    """
    request = SemanticRequest(
        model="gpt-5.6-sol",
        tools=[{"type": "web_fetch_20250910", "name": "web_fetch"}],
    )
    assert to_openai_responses(request)["tools"] == [
        {"type": "web_fetch_20250910", "name": "web_fetch"}
    ]


def test_a_search_the_upstream_ran_is_reported_rather_than_dropped() -> None:
    """The item has no Anthropic spelling and nothing to revive: it carries a query, a status and an opaque id, and the results are not in it — they reached the model directly and are already folded into the answer that follows.

    So what is left to say is what was searched for, in the same words `builtin:server-tool-capability` flattens the Anthropic leg's history into. One wording, because the same conversation moves between the two legs when a client switches model.
    """
    payload, semantic = default_registry().translate_response(
        {
            "id": "resp_1",
            "model": "gpt-5.6-sol",
            "output": [
                {
                    "type": "web_search_call",
                    "id": "x" * 416,
                    "status": "completed",
                    "action": {"type": "search", "query": "bun release notes", "queries": ["bun release notes"]},
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Bun 1.3 is out.", "annotations": []}],
                },
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert payload["content"] == [
        {"type": "text", "text": "[web_search] bun release notes"},
        {"type": "text", "text": "Bun 1.3 is out."},
    ]
    # The 416-character upstream handle must not reach the client: it means nothing to the model, it
    # inflates every later request, and this project carries no continuation that could spend it.
    assert "x" * 32 not in json.dumps(payload)
    assert semantic.conversion.lossless, semantic.conversion.losses


def test_a_choice_is_left_alone_when_its_name_also_belongs_to_a_function_tool() -> None:
    """The trap the spec names: a client may call an ordinary function tool `web_search`.

    With both declared, which one the choice meant is the client's own ambiguity, and answering it by forcing a hosted search would be this proxy inventing the answer — turning a call the client wrote into a search it never asked for.
    """
    payload, _ = default_registry().translate(
        {
            "model": "gpt-5.6-sol",
            "input": [],
            "tools": [
                {"type": "web_search_20250305", "name": "web_search"},
                {"type": "function", "name": "web_search", "parameters": {"type": "object"}},
            ],
            "tool_choice": {"type": "function", "name": "web_search"},
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["tool_choice"] == {"type": "function", "name": "web_search"}


def test_a_forced_search_survives_the_format_boundary() -> None:
    """`tool_choice` is nobody's modelled field, so it rides in `extensions` and is dropped whole when the formats differ. Correct in general, wrong here.

    Measured over 190 real Claude Code sub-requests, 95 force the search this way — and those requests exist for no other purpose: the turn they carry says `Perform a web search for the query: X`. A model no longer obliged to search may answer from memory instead, and the client renders whatever comes back under a `Web search results for query:` heading either way. This is one of the ways that heading ends up over text nothing searched for.
    """
    payload, _ = default_registry().translate(
        {
            "model": "gpt-5.6-sol",
            "messages": [{"role": "user", "content": "Perform a web search for the query: bun"}],
            "max_tokens": 1024,
            "tools": [dict(REAL_WEB_SEARCH_DECLARATION)],
            "tool_choice": {"type": "tool", "name": "web_search"},
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["tools"] == [{"type": "web_search"}]
    assert payload["tool_choice"] == {"type": "web_search"}


def test_a_forced_choice_is_not_carried_when_the_name_is_ambiguous() -> None:
    """The same trap as the same-format case: a client may call an ordinary function tool `web_search`. Which one it meant is its own ambiguity, and forcing a hosted search would be answering it on its behalf."""
    payload, _ = default_registry().translate(
        {
            "model": "gpt-5.6-sol",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1024,
            "tools": [
                dict(REAL_WEB_SEARCH_DECLARATION),
                {"name": "web_search", "input_schema": {"type": "object"}},
            ],
            "tool_choice": {"type": "tool", "name": "web_search"},
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    assert "tool_choice" not in payload


def test_a_replayed_failed_search_still_says_it_happened() -> None:
    """These blocks arrive because *we sent them*, so dropping them loses a fact we chose to state.

    When a search cannot run this proxy answers with a `server_tool_use` paired with a failed `web_search_tool_result`, and the client replays that turn verbatim. Responses has no `server_tool_use`, so without flattening the whole assistant turn goes — not just the two blocks, since a message left with no content is not carried either. The model would then see two consecutive user turns, no trace of the attempt, and every reason to try again: same failure, dropped the same way.
    """
    payload, semantic = default_registry().translate(
        {
            "model": "gpt-5.6-sol",
            "max_tokens": 64,
            "messages": [
                {"role": "user", "content": "search for bun"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "server_tool_use",
                            "id": "srvtoolu_x",
                            "name": "web_search",
                            "input": {"query": "bun 1.3"},
                        },
                        {
                            "type": "web_search_tool_result",
                            "tool_use_id": "srvtoolu_x",
                            "content": {
                                "type": "web_search_tool_result_error",
                                "error_code": "unavailable",
                            },
                        },
                    ],
                },
                {"role": "user", "content": "so what did you find"},
            ],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    texts: list[str] = [
        str(cast(dict[str, Any], part)["text"])
        for item in cast(list[Any], payload["input"])
        for part in cast(list[Any], cast(dict[str, Any], item).get("content", []))
        if isinstance(part, dict) and "text" in cast(dict[str, Any], part)
    ]
    assert "[web_search] bun 1.3" in texts, texts
    assert "[web_search failed: unavailable]" in texts, texts
    assert semantic.conversion.has(LossCode.SERVER_TOOL_NOT_CARRIED)
