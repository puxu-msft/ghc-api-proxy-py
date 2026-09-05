from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict, cast

from app.pipeline.translation_driver.reasoning_bridge import (
    OPENAI_RESPONSES,
    ReasoningBridgeError,
    ReasoningNotPortable,
    classify_anthropic_carrier,
    read_anthropic_reasoning,
    read_responses_reasoning,
    reasoning_to_anthropic,
    reasoning_to_responses,
)
from app.pipeline.translation_driver.reasoning_carrier import (
    PROJECT_SYNTHETIC_REASONING_SIGNATURE,
    PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    ReasoningCarrierClassification,
    decode_reasoning_carrier,
)

SYNTHETIC_REASONING_SIGNATURE_PREFIX = UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX
SYNTHETIC_REASONING_SIGNATURE = UPSTREAM_SYNTHETIC_REASONING_SIGNATURE


class ResponsesSummaryText(TypedDict):
    type: Literal["summary_text"]
    text: str


class ResponsesReasoningItem(TypedDict):
    type: Literal["reasoning"]
    summary: list[ResponsesSummaryText]
    encrypted_content: NotRequired[str]


class AnthropicThinkingBlock(TypedDict):
    type: Literal["thinking"]
    thinking: str
    signature: str


@dataclass(frozen=True, slots=True)
class AnthropicThinkingDecode:
    item: ResponsesReasoningItem | None
    malformed_payload: bool = False
    classification: ReasoningCarrierClassification | None = None


def responses_reasoning_to_anthropic(
    items: Sequence[Mapping[str, object]],
) -> list[AnthropicThinkingBlock] | None:
    """Compatibility facade over the canonical typed bridge."""
    blocks: list[AnthropicThinkingBlock] = []
    try:
        for item in items:
            if item.get("type") != "reasoning":
                continue
            content = read_responses_reasoning(item)
            block = reasoning_to_anthropic(content, bridge_for_client=True)
            if block.get("type") != "thinking":
                return None
            blocks.append(cast(AnthropicThinkingBlock, block))
    except (ReasoningBridgeError, ReasoningNotPortable):
        return None
    return blocks


def anthropic_thinking_to_responses(
    block: Mapping[str, object],
) -> ResponsesReasoningItem | None:
    """Recover one Responses item through the canonical typed bridge."""
    return decode_anthropic_thinking(block).item


def decode_anthropic_thinking(block: Mapping[str, object]) -> AnthropicThinkingDecode:
    """Compatibility facade that keeps the legacy diagnostic result shape."""
    signature = block.get("signature")
    thinking = block.get("thinking")
    decoded = decode_reasoning_carrier(signature) if isinstance(signature, str) else None
    classification = (
        classify_anthropic_carrier(signature, thinking)
        if isinstance(signature, str) and isinstance(thinking, str)
        else decoded.classification
        if decoded is not None
        else None
    )
    try:
        content = read_anthropic_reasoning(block)
        if content.source_format != OPENAI_RESPONSES:
            return AnthropicThinkingDecode(item=None, classification=classification)
        item = reasoning_to_responses(content, bridge_for_client=False)
        return AnthropicThinkingDecode(
            item=cast(ResponsesReasoningItem, item),
            classification=classification,
        )
    except (ReasoningBridgeError, ReasoningNotPortable):
        return AnthropicThinkingDecode(
            item=None,
            malformed_payload=bool(decoded and decoded.malformed),
            classification=classification,
        )


__all__ = [
    "PROJECT_SYNTHETIC_REASONING_SIGNATURE",
    "PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX",
    "SYNTHETIC_REASONING_SIGNATURE",
    "SYNTHETIC_REASONING_SIGNATURE_PREFIX",
    "AnthropicThinkingBlock",
    "AnthropicThinkingDecode",
    "ResponsesReasoningItem",
    "ResponsesSummaryText",
    "anthropic_thinking_to_responses",
    "decode_anthropic_thinking",
    "responses_reasoning_to_anthropic",
]
