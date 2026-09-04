from typing import Any

import pytest

from app.pipeline.translation_driver.content import (
    ReasoningContent,
    ReasoningSummaryPart,
)
from app.pipeline.translation_driver.reasoning_bridge import (
    ReasoningBridgeError,
    ReasoningNotPortable,
    classify_responses_carrier,
    read_anthropic_reasoning,
    read_chat_reasoning,
    read_responses_reasoning,
    reasoning_to_anthropic,
    reasoning_to_responses,
)
from app.pipeline.translation_driver.reasoning_carrier import (
    ANTHROPIC_THINKING_SIGNATURE,
    CHAT_REASONING_CONTENT,
    PROJECT_SYNTHETIC_REASONING_SIGNATURE,
    PROJECT_SYNTHETIC_REASONING_V2,
    RESPONSES_SUMMARY_TEXT_LAYOUT,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    CarrierRecord,
    decode_reasoning_carrier,
    encode_reasoning_carrier,
    encode_reasoning_carrier_v2,
)


def test_responses_summary_parts_and_opaque_state_round_trip_value_exact() -> None:
    original = {
        "type": "reasoning",
        "summary": [
            {"type": "summary_text", "text": "一", "detail": 1},
            {"type": "summary_text", "text": ""},
            {"type": "summary_text", "text": "😀二"},
        ],
        "encrypted_content": "ENC==",
    }

    content = read_responses_reasoning(original)
    anthropic = reasoning_to_anthropic(content, bridge_for_client=True)
    recovered = read_anthropic_reasoning(anthropic)

    assert anthropic["thinking"] == "一😀二"
    assert reasoning_to_responses(recovered, bridge_for_client=False) == original


def test_canonical_summary_only_responses_reasoning_uses_bare_v2() -> None:
    content = read_responses_reasoning(
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "visible"}]}
    )
    anthropic = reasoning_to_anthropic(content, bridge_for_client=True)
    assert anthropic == {
        "type": "thinking",
        "thinking": "visible",
        "signature": PROJECT_SYNTHETIC_REASONING_V2,
    }
    recovered = read_anthropic_reasoning(anthropic)
    assert reasoning_to_responses(recovered, bridge_for_client=False) == {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "visible"}],
    }


def test_one_empty_summary_part_is_not_collapsed_into_bare_shape() -> None:
    original = {"type": "reasoning", "summary": [{"type": "summary_text", "text": ""}]}
    content = read_responses_reasoning(original)
    anthropic = reasoning_to_anthropic(content, bridge_for_client=True)
    assert anthropic["signature"] != PROJECT_SYNTHETIC_REASONING_V2
    recovered = read_anthropic_reasoning(anthropic)
    assert reasoning_to_responses(recovered, bridge_for_client=False) == original


def test_present_empty_encrypted_content_stays_distinct_from_absent() -> None:
    original: dict[str, Any] = {
        "type": "reasoning",
        "summary": [],
        "encrypted_content": "",
    }
    content = read_responses_reasoning(original)
    anthropic = reasoning_to_anthropic(content, bridge_for_client=True)
    recovered = read_anthropic_reasoning(anthropic)
    assert reasoning_to_responses(recovered, bridge_for_client=False) == original


def test_native_anthropic_signature_round_trips_through_responses_client_shape() -> None:
    original = {"type": "thinking", "thinking": "visible", "signature": "CAIS-native"}
    content = read_anthropic_reasoning(original)
    responses = reasoning_to_responses(content, bridge_for_client=True)
    recovered = read_responses_reasoning(responses)
    assert responses["encrypted_content"].startswith("ghc-api-proxy:synthetic-reasoning:v2:")
    assert reasoning_to_anthropic(recovered, bridge_for_client=False) == original


def test_native_redacted_thinking_round_trips_without_visible_summary() -> None:
    original = {"type": "redacted_thinking", "data": "opaque-redacted"}
    content = read_anthropic_reasoning(original)
    responses = reasoning_to_responses(content, bridge_for_client=True)
    recovered = read_responses_reasoning(responses)
    assert responses["summary"] == []
    assert reasoning_to_anthropic(recovered, bridge_for_client=False) == original


def test_chat_visible_reasoning_preserves_origin_through_both_client_wires() -> None:
    content = read_chat_reasoning("hidden chain")
    assert content.state is None

    anthropic = reasoning_to_anthropic(content, bridge_for_client=True)
    assert anthropic["type"] == "thinking"
    assert anthropic["thinking"] == "hidden chain"
    anthropic_carrier = decode_reasoning_carrier(anthropic["signature"])
    assert {record.type for record in anthropic_carrier.records} == {
        CHAT_REASONING_CONTENT,
        RESPONSES_SUMMARY_TEXT_LAYOUT,
    }
    from_anthropic = read_anthropic_reasoning(anthropic)
    assert from_anthropic == content
    with pytest.raises(ReasoningNotPortable):
        reasoning_to_responses(from_anthropic, bridge_for_client=False)

    responses = reasoning_to_responses(content, bridge_for_client=True)
    assert responses["summary"] == [{"type": "summary_text", "text": "hidden chain"}]
    responses_carrier = decode_reasoning_carrier(responses["encrypted_content"])
    assert responses_carrier.records == (CarrierRecord(CHAT_REASONING_CONTENT, None),)
    from_responses = read_responses_reasoning(responses)
    assert from_responses == ReasoningContent(
        visible_text="hidden chain",
        source_format="openai-chat-completions",
        summary_parts=(ReasoningSummaryPart("hidden chain"),),
    )
    with pytest.raises(ReasoningNotPortable):
        reasoning_to_responses(from_responses, bridge_for_client=False)

    with pytest.raises(ReasoningNotPortable):
        reasoning_to_anthropic(content, bridge_for_client=False)
    with pytest.raises(ReasoningNotPortable):
        reasoning_to_responses(content, bridge_for_client=False)


def test_native_opaque_state_is_not_forged_into_the_other_upstream_slot() -> None:
    anthropic = read_anthropic_reasoning(
        {"type": "thinking", "thinking": "visible", "signature": "CAIS-native"}
    )
    responses = read_responses_reasoning(
        {"type": "reasoning", "summary": [], "encrypted_content": "ENC"}
    )
    with pytest.raises(ReasoningNotPortable):
        reasoning_to_responses(anthropic, bridge_for_client=False)
    with pytest.raises(ReasoningNotPortable):
        reasoning_to_anthropic(responses, bridge_for_client=False)


def test_layout_and_visible_text_mismatch_has_a_stable_classification() -> None:
    original = {
        "type": "reasoning",
        "summary": [
            {"type": "summary_text", "text": "a"},
            {"type": "summary_text", "text": "b"},
        ],
    }
    anthropic = reasoning_to_anthropic(
        read_responses_reasoning(original), bridge_for_client=True
    )
    anthropic["thinking"] = "abc"
    with pytest.raises(ReasoningBridgeError) as caught:
        read_anthropic_reasoning(anthropic)
    assert caught.value.code == "project_v2_presentation_mismatch"


def test_utf8_layout_cannot_split_a_code_point() -> None:
    # Two bytes cannot decode the first UTF-8 part of 😀; the lengths still cover the whole text.
    signature = encode_reasoning_carrier_v2(
        [
            CarrierRecord(
                RESPONSES_SUMMARY_TEXT_LAYOUT,
                {"lengths": [2, 2], "extensions": [{}, {}]},
            )
        ]
    )
    with pytest.raises(ReasoningBridgeError) as caught:
        read_anthropic_reasoning(
            {"type": "thinking", "thinking": "😀", "signature": signature}
        )
    assert caught.value.code == "project_v2_presentation_mismatch"


def test_unknown_record_is_unsupported_not_malformed() -> None:
    signature = encode_reasoning_carrier_v2(
        [CarrierRecord("future.provider.reasoning.detail", {"x": 1})]
    )
    with pytest.raises(ReasoningBridgeError) as caught:
        read_anthropic_reasoning(
            {"type": "thinking", "thinking": "visible", "signature": signature}
        )
    assert caught.value.code == "project_v2_unsupported_record"


def test_anthropic_record_in_anthropic_slot_is_direction_mismatch() -> None:
    signature = encode_reasoning_carrier_v2(
        [CarrierRecord(ANTHROPIC_THINKING_SIGNATURE, "CAIS")]
    )
    with pytest.raises(ReasoningBridgeError) as caught:
        read_anthropic_reasoning(
            {"type": "thinking", "thinking": "visible", "signature": signature}
        )
    assert caught.value.code == "project_v2_direction_mismatch"


@pytest.mark.parametrize(
    "carrier",
    [
        PROJECT_SYNTHETIC_REASONING_V2,
        encode_reasoning_carrier("ENC"),
        PROJECT_SYNTHETIC_REASONING_SIGNATURE,
        f"{UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX}RU5D",
        UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
        UPSTREAM_SYNTHETIC_REASONING_SIGNATURE,
    ],
)
def test_anthropic_signature_carriers_are_direction_mismatches_in_responses_slot(
    carrier: str,
) -> None:
    assert (
        classify_responses_carrier(carrier, [])
        == "project_v2_direction_mismatch"
    )
    with pytest.raises(ReasoningBridgeError) as caught:
        read_responses_reasoning(
            {"type": "reasoning", "summary": [], "encrypted_content": carrier}
        )
    assert caught.value.code == "project_v2_direction_mismatch"


def test_responses_encrypted_content_null_is_rejected_instead_of_becoming_string_none() -> None:
    with pytest.raises(ReasoningBridgeError) as caught:
        read_responses_reasoning(
            {"type": "reasoning", "summary": [], "encrypted_content": None}
        )
    assert caught.value.code == "responses_encrypted_content_malformed"
