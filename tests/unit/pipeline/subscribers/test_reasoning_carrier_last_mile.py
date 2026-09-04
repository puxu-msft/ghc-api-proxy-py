from typing import Any

import pytest

from app.anthropic.thinking.destack import SYNTHETIC_SEPARATOR
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.reasoning_carrier import guard_and_layout_reasoning
from app.pipeline.translation_driver.reasoning_carrier import (
    ANTHROPIC_THINKING_SIGNATURE,
    CarrierRecord,
    encode_reasoning_carrier_v2,
)
from app.pipeline.translation_driver.semantic import TranslationRefused


def context(payload: dict[str, Any], target: WireFormat) -> RequestContext:
    result = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="model",
        payload=payload,
    )
    result.target_format = target
    return result


async def test_anthropic_last_mile_destacks_adjacent_native_thinking() -> None:
    request = context(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "a", "signature": "CAIS-a"},
                        {"type": "thinking", "thinking": "b", "signature": "CAIS-b"},
                    ],
                }
            ]
        },
        WireFormat.ANTHROPIC_MESSAGES,
    )
    await guard_and_layout_reasoning(
        request, assistant_message_layout="synthetic_only"
    )
    assert request.payload["messages"][0]["content"] == [
        {"type": "thinking", "thinking": "a", "signature": "CAIS-a"},
        {"type": "text", "text": SYNTHETIC_SEPARATOR},
        {"type": "thinking", "thinking": "b", "signature": "CAIS-b"},
    ]


async def test_responses_last_mile_does_not_insert_an_assistant_separator() -> None:
    request = context(
        {
            "input": [
                {"type": "reasoning", "summary": [], "encrypted_content": "native-a"},
                {"type": "reasoning", "summary": [], "encrypted_content": "native-b"},
            ]
        },
        WireFormat.OPENAI_RESPONSES,
    )
    original = list(request.payload["input"])
    await guard_and_layout_reasoning(
        request, assistant_message_layout="move_and_synthetic"
    )
    assert request.payload["input"] == original


@pytest.mark.parametrize(
    "signature",
    [
        "ghc-api-proxy:synthetic-reasoning:v2",
        "ghc-api-proxy:synthetic-reasoning:v1",
        "ghc-api-proxy:synthetic-reasoning:v9:future",
        "copilot-api:synthetic-reasoning:v1:RU5D",
        "copilot-api:synthetic-reasoning:v1:",
        "copilot-api:synthetic-reasoning:v1",
    ],
)
async def test_anthropic_last_mile_refuses_every_supported_synthetic_namespace(
    signature: str,
) -> None:
    request = context(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "visible", "signature": signature}
                    ],
                }
            ]
        },
        WireFormat.ANTHROPIC_MESSAGES,
    )
    with pytest.raises(TranslationRefused) as caught:
        await guard_and_layout_reasoning(
            request, assistant_message_layout="move_and_synthetic"
        )
    assert caught.value.code == "reasoning_carrier_not_unwrapped"
    assert caught.value.field_path == "messages.0.content.0.signature"


async def test_anthropic_last_mile_also_refuses_carrier_in_redacted_data() -> None:
    request = context(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "redacted_thinking",
                            "data": "ghc-api-proxy:synthetic-reasoning:v2",
                        }
                    ],
                }
            ]
        },
        WireFormat.ANTHROPIC_MESSAGES,
    )
    with pytest.raises(TranslationRefused) as caught:
        await guard_and_layout_reasoning(
            request, assistant_message_layout="move_and_synthetic"
        )
    assert caught.value.code == "reasoning_carrier_not_unwrapped"
    assert caught.value.field_path == "messages.0.content.0.data"


async def test_responses_last_mile_refuses_a_client_facing_project_carrier() -> None:
    encrypted = encode_reasoning_carrier_v2(
        [CarrierRecord(ANTHROPIC_THINKING_SIGNATURE, "CAIS-native")]
    )
    request = context(
        {
            "input": [
                {"type": "reasoning", "summary": [], "encrypted_content": encrypted}
            ]
        },
        WireFormat.OPENAI_RESPONSES,
    )
    with pytest.raises(TranslationRefused) as caught:
        await guard_and_layout_reasoning(
            request, assistant_message_layout="move_and_synthetic"
        )
    assert caught.value.code == "reasoning_carrier_not_unwrapped"
    assert caught.value.field_path == "input.0.encrypted_content"


async def test_responses_guard_reports_bare_v2_as_direction_mismatch() -> None:
    request = context(
        {
            "input": [
                {
                    "type": "reasoning",
                    "summary": [],
                    "encrypted_content": "ghc-api-proxy:synthetic-reasoning:v2",
                }
            ]
        },
        WireFormat.OPENAI_RESPONSES,
    )
    with pytest.raises(TranslationRefused) as caught:
        await guard_and_layout_reasoning(
            request, assistant_message_layout="move_and_synthetic"
        )
    assert "project_v2_direction_mismatch" in str(caught.value)


async def test_passthrough_layout_leaves_native_anthropic_history_unchanged() -> None:
    content = [
        {"type": "thinking", "thinking": "a", "signature": "CAIS-a"},
        {"type": "thinking", "thinking": "b", "signature": "CAIS-b"},
    ]
    request = context(
        {"messages": [{"role": "assistant", "content": content}]},
        WireFormat.ANTHROPIC_MESSAGES,
    )
    await guard_and_layout_reasoning(request, assistant_message_layout=False)
    assert request.payload["messages"][0]["content"] == content
