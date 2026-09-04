from collections.abc import Mapping

from app.anthropic.thinking.responses_reasoning import (
    SYNTHETIC_REASONING_SIGNATURE,
    SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    anthropic_thinking_to_responses,
    decode_anthropic_thinking,
    responses_reasoning_to_anthropic,
)
from app.pipeline.translation_driver.reasoning_carrier import (
    ANTHROPIC_THINKING_SIGNATURE,
    PROJECT_SYNTHETIC_REASONING_V2,
    RESPONSES_ENCRYPTED_CONTENT,
    RESPONSES_SUMMARY_TEXT_LAYOUT,
    CarrierRecord,
    encode_reasoning_carrier_v2,
)


def test_facade_uses_v2_bare_for_canonical_summary_only_reasoning() -> None:
    blocks = responses_reasoning_to_anthropic(
        [
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "step 1... step 2..."}],
            }
        ]
    )
    assert blocks == [
        {
            "type": "thinking",
            "thinking": "step 1... step 2...",
            "signature": PROJECT_SYNTHETIC_REASONING_V2,
        }
    ]


def test_facade_round_trip_preserves_multiple_parts_empty_text_extensions_and_opaque() -> None:
    reasoning: Mapping[str, object] = {
        "type": "reasoning",
        "summary": [
            {"type": "summary_text", "text": "一", "detail": 1},
            {"type": "summary_text", "text": ""},
            {"type": "summary_text", "text": "😀二"},
        ],
        "encrypted_content": "ENC==\x00😀",
    }
    blocks = responses_reasoning_to_anthropic([reasoning])
    assert blocks is not None
    assert len(blocks) == 1
    assert blocks[0]["signature"].startswith("ghc-api-proxy:synthetic-reasoning:v2:")
    assert anthropic_thinking_to_responses(blocks[0]) == reasoning


def test_facade_preserves_reasoning_item_cardinality() -> None:
    reasoning_items: list[Mapping[str, object]] = [
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
        {"type": "reasoning", "summary": [], "encrypted_content": "ENC-ONLY"},
    ]
    blocks = responses_reasoning_to_anthropic(reasoning_items)
    assert blocks is not None
    assert [anthropic_thinking_to_responses(block) for block in blocks] == reasoning_items


def test_facade_still_consumes_copilot_v1_payload_bare_and_legacy_forms() -> None:
    assert anthropic_thinking_to_responses(
        {
            "type": "thinking",
            "thinking": "legacy summary",
            "signature": f"{SYNTHETIC_REASONING_SIGNATURE_PREFIX}RU5DPT0",
        }
    ) == {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "legacy summary"}],
        "encrypted_content": "ENC==",
    }
    assert anthropic_thinking_to_responses(
        {
            "type": "thinking",
            "thinking": "bare prefix",
            "signature": SYNTHETIC_REASONING_SIGNATURE_PREFIX,
        }
    ) == {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "bare prefix"}],
    }
    assert anthropic_thinking_to_responses(
        {
            "type": "thinking",
            "thinking": "legacy sentinel",
            "signature": SYNTHETIC_REASONING_SIGNATURE,
        }
    ) == {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "legacy sentinel"}],
    }


def test_facade_reports_slot_aware_v2_classifications() -> None:
    cases = [
        (
            encode_reasoning_carrier_v2(
                [CarrierRecord("future.provider.reasoning.detail", {"x": 1})]
            ),
            "visible",
            "project_v2_unsupported_record",
        ),
        (
            encode_reasoning_carrier_v2(
                [CarrierRecord(ANTHROPIC_THINKING_SIGNATURE, "CAIS-native")]
            ),
            "visible",
            "project_v2_direction_mismatch",
        ),
        (
            encode_reasoning_carrier_v2(
                [CarrierRecord(RESPONSES_ENCRYPTED_CONTENT, "ENC")]
            ),
            "visible",
            "project_v2_profile_mismatch",
        ),
        (
            encode_reasoning_carrier_v2(
                [
                    CarrierRecord(
                        RESPONSES_SUMMARY_TEXT_LAYOUT,
                        {"lengths": [1], "extensions": [{}]},
                    )
                ]
            ),
            "ab",
            "project_v2_presentation_mismatch",
        ),
    ]
    for signature, thinking, expected in cases:
        decoded = decode_anthropic_thinking(
            {"type": "thinking", "thinking": thinking, "signature": signature}
        )
        assert decoded.item is None
        assert decoded.classification == expected


def test_foreign_redacted_malformed_and_invalid_blocks_are_not_recovered() -> None:
    assert (
        anthropic_thinking_to_responses(
            {"type": "thinking", "thinking": "foreign", "signature": "CAIS-claude"}
        )
        is None
    )
    assert (
        anthropic_thinking_to_responses(
            {"type": "redacted_thinking", "data": "opaque-anthropic-data"}
        )
        is None
    )
    assert anthropic_thinking_to_responses({"type": "thinking", "thinking": 42}) is None
    assert (
        anthropic_thinking_to_responses(
            {
                "type": "thinking",
                "thinking": "malformed payload",
                "signature": f"{SYNTHETIC_REASONING_SIGNATURE_PREFIX}!!!",
            }
        )
        is None
    )
