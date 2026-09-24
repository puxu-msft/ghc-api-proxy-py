from typing import Any

import pytest

from app.anthropic.thinking.destack import SYNTHETIC_SEPARATOR
from app.observability.request_trace import RequestTrace
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.reasoning_carrier import guard_and_layout_reasoning
from app.pipeline.translation_driver.reasoning_bridge import (
    read_responses_reasoning,
    reasoning_to_anthropic,
)
from app.pipeline.translation_driver.reasoning_carrier import (
    ANTHROPIC_THINKING_SIGNATURE,
    CarrierRecord,
    encode_reasoning_carrier_v2,
)
from app.pipeline.translation_driver.semantic import (
    NONPORTABLE_REASONING_REQUEST_DETAIL,
    LossCode,
    TranslationRefused,
)


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
async def test_strict_anthropic_last_mile_refuses_every_supported_synthetic_namespace(
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
            request,
            assistant_message_layout="move_and_synthetic",
            unportable_reasoning_carrier="refuse",
        )
    assert caught.value.code == "reasoning_carrier_not_unwrapped"
    assert caught.value.field_path == "messages.0.content.0.signature"


async def test_default_anthropic_last_mile_records_one_loss_per_request() -> None:
    carrier = reasoning_to_anthropic(
        read_responses_reasoning(
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "visible"}],
                "encrypted_content": "native-responses-state",
            }
        ),
        bridge_for_client=True,
    )
    text = {"type": "text", "text": "answer"}
    tool: dict[str, Any] = {"type": "tool_use", "id": "tool_1", "name": "run", "input": {}}
    request = context(
        {"messages": [{"role": "assistant", "content": [carrier, text, carrier, tool]}]},
        WireFormat.ANTHROPIC_MESSAGES,
    )

    await guard_and_layout_reasoning(request, assistant_message_layout="move_and_synthetic")

    assert request.payload["messages"][0]["content"] == [text, tool]
    assert [(loss.code, loss.detail) for loss in request.extras["conversion_losses"]] == [
        (LossCode.REASONING_STATE_NOT_PORTABLE, NONPORTABLE_REASONING_REQUEST_DETAIL)
    ]
    trace = RequestTrace(method="POST", path="/v1/messages")
    trace.absorb_conversion(request)
    assert trace.losses == (
        {"direction": "request", "code": "reasoning-state-not-portable", "detail": NONPORTABLE_REASONING_REQUEST_DETAIL},
    )

    request.payload["messages"][0]["content"] = [carrier, text, carrier, tool]
    await guard_and_layout_reasoning(request, assistant_message_layout="move_and_synthetic")
    assert len(request.extras["conversion_losses"]) == 1


async def test_default_loss_keeps_an_assistant_turn_that_becomes_empty() -> None:
    carrier = reasoning_to_anthropic(
        read_responses_reasoning(
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "visible"}]}
        ),
        bridge_for_client=True,
    )
    request = context(
        {"messages": [{"role": "assistant", "content": [carrier]}]},
        WireFormat.ANTHROPIC_MESSAGES,
    )

    await guard_and_layout_reasoning(request, assistant_message_layout="move_and_synthetic")

    assert request.payload["messages"] == [{"role": "assistant", "content": []}]
    assert [loss.code for loss in request.extras["conversion_losses"]] == [
        LossCode.REASONING_STATE_NOT_PORTABLE
    ]


async def test_malformed_carrier_is_not_turned_into_a_named_loss() -> None:
    original = {"type": "thinking", "thinking": "visible", "signature": "ghc-api-proxy:synthetic-reasoning:v9:future"}
    request = context(
        {"messages": [{"role": "assistant", "content": [original]}]},
        WireFormat.ANTHROPIC_MESSAGES,
    )

    with pytest.raises(TranslationRefused):
        await guard_and_layout_reasoning(request, assistant_message_layout="move_and_synthetic")

    assert request.payload["messages"][0]["content"] == [original]
    assert "conversion_losses" not in request.extras


async def test_carrier_in_a_user_turn_is_not_dropped_as_assistant_history() -> None:
    carrier = reasoning_to_anthropic(
        read_responses_reasoning(
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "visible"}]}
        ),
        bridge_for_client=True,
    )
    request = context(
        {"messages": [{"role": "user", "content": [carrier]}]},
        WireFormat.ANTHROPIC_MESSAGES,
    )

    with pytest.raises(TranslationRefused):
        await guard_and_layout_reasoning(request, assistant_message_layout="move_and_synthetic")
    assert request.payload["messages"][0]["content"] == [carrier]
    assert "conversion_losses" not in request.extras


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
