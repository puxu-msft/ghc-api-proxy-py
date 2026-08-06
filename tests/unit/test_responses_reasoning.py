from app.anthropic.thinking.responses_reasoning import (
    SYNTHETIC_REASONING_SIGNATURE,
    SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    anthropic_thinking_to_responses,
    responses_reasoning_to_anthropic,
)


def test_plain_summary_becomes_thinking_with_bare_carrier() -> None:
    block = responses_reasoning_to_anthropic(
        [
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "step 1... step 2..."}],
            }
        ]
    )
    assert block == {
        "type": "thinking",
        "thinking": "step 1... step 2...",
        "signature": SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    }


def test_encrypted_only_reasoning_does_not_create_an_empty_thinking_block() -> None:
    block = responses_reasoning_to_anthropic(
        [{"type": "reasoning", "summary": [], "encrypted_content": "ENC=="}]
    )

    assert block is None


def test_encrypted_content_is_recovered_from_an_empty_thinking_carrier() -> None:
    assert anthropic_thinking_to_responses(
        {
            "type": "thinking",
            "thinking": "",
            "signature": f"{SYNTHETIC_REASONING_SIGNATURE_PREFIX}RU5DPT0",
        }
    ) == {"type": "reasoning", "summary": [], "encrypted_content": "ENC=="}


def test_mixed_reasoning_joins_summary_and_carries_encrypted_content() -> None:
    block = responses_reasoning_to_anthropic(
        [
            {
                "type": "reasoning",
                "summary": [
                    {"type": "summary_text", "text": "first"},
                    {"type": "summary_text", "text": " + second"},
                ],
                "encrypted_content": "opaque-😀",
            }
        ]
    )

    assert block == {
        "type": "thinking",
        "thinking": "first + second",
        "signature": f"{SYNTHETIC_REASONING_SIGNATURE_PREFIX}b3BhcXVlLfCfmIA",
    }


def test_reasoning_items_aggregate_into_one_leading_block() -> None:
    block = responses_reasoning_to_anthropic(
        [
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "first"}],
                "encrypted_content": "ENC-1",
            },
            {"type": "message", "content": [{"type": "output_text", "text": "answer"}]},
            {
                "type": "reasoning",
                "summary": [
                    {"type": "summary_text", "text": " + second"},
                    {"type": "summary_text", "text": ""},
                ],
            },
            {"type": "reasoning", "summary": [], "encrypted_content": "ENC-2"},
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": " + third"}],
                "encrypted_content": "",
            },
        ]
    )

    assert block == {
        "type": "thinking",
        "thinking": "first + second + third",
        "signature": f"{SYNTHETIC_REASONING_SIGNATURE_PREFIX}RU5DLTI",
    }


def test_carrier_round_trip_is_field_and_byte_compatible() -> None:
    reasoning = {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "visible"}],
        "encrypted_content": "ENC==\x00😀",
    }

    block = responses_reasoning_to_anthropic([reasoning])

    assert block is not None
    assert anthropic_thinking_to_responses(block) == reasoning


def test_foreign_and_redacted_thinking_are_not_recovered() -> None:
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


def test_invalid_blocks_and_legacy_carrier_follow_upstream_compatibility() -> None:
    assert anthropic_thinking_to_responses({"type": "thinking", "thinking": 42}) is None
    assert (
        anthropic_thinking_to_responses(
            {
                "type": "thinking",
                "thinking": "legacy summary",
                "signature": SYNTHETIC_REASONING_SIGNATURE,
            }
        )
        == {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "legacy summary"}],
        }
    )
    assert (
        anthropic_thinking_to_responses(
            {
                "type": "thinking",
                "thinking": "malformed payload",
                "signature": f"{SYNTHETIC_REASONING_SIGNATURE_PREFIX}!!!",
            }
        )
        == {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "malformed payload"}],
            "encrypted_content": "",
        }
    )
    assert (
        anthropic_thinking_to_responses(
            {
                "type": "thinking",
                "thinking": "truncated payload",
                "signature": f"{SYNTHETIC_REASONING_SIGNATURE_PREFIX}A",
            }
        )
        == {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "truncated payload"}],
            "encrypted_content": "",
        }
    )


# These malformed carriers intentionally mirror Node's permissive base64url decoder.
