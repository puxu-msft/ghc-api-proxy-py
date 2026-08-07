from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict, cast

from app.anthropic.thinking.reasoning_carrier import (
    PROJECT_SYNTHETIC_REASONING_SIGNATURE,
    PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    ReasoningCarrierClassification,
    decode_reasoning_carrier,
    encode_reasoning_carrier,
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
    """Convert each Responses reasoning item into its own Anthropic thinking block."""
    blocks: list[AnthropicThinkingBlock] = []
    for item in items:
        if item.get("type") != "reasoning":
            continue

        summary = item.get("summary")
        if not isinstance(summary, list):
            return None

        summary_text: list[str] = []
        for part in cast(list[object], summary):
            if not isinstance(part, Mapping):
                return None
            typed_part = cast(Mapping[str, object], part)
            if typed_part.get("type") != "summary_text" or not isinstance(
                typed_part.get("text"), str
            ):
                return None
            text = cast(str, typed_part["text"])
            if text:
                summary_text.append(text)

        encrypted = item.get("encrypted_content")
        if encrypted is not None and not isinstance(encrypted, str):
            return None
        thinking = "".join(summary_text)

        blocks.append(
            {
                "type": "thinking",
                "thinking": thinking,
                "signature": encode_reasoning_carrier(encrypted),
            }
        )

    return blocks


def anthropic_thinking_to_responses(
    block: Mapping[str, object],
) -> ResponsesReasoningItem | None:
    """Recover one Responses reasoning item only from this bridge's carrier."""
    return decode_anthropic_thinking(block).item


def decode_anthropic_thinking(block: Mapping[str, object]) -> AnthropicThinkingDecode:
    """Recover one item from project v1 or supported upstream compatibility carriers."""
    if block.get("type") != "thinking":
        return AnthropicThinkingDecode(item=None)
    thinking = block.get("thinking")
    signature = block.get("signature")
    if not isinstance(thinking, str) or not isinstance(signature, str):
        return AnthropicThinkingDecode(item=None)

    decoded = decode_reasoning_carrier(signature)
    if decoded.classification in {
        "project_unknown_version",
        "project_malformed_v1",
        "upstream_malformed_v1",
        "foreign",
    }:
        return AnthropicThinkingDecode(
            item=None,
            malformed_payload=decoded.malformed,
            classification=decoded.classification,
        )

    summary: list[ResponsesSummaryText] = []
    if thinking:
        summary.append({"type": "summary_text", "text": thinking})
    item: ResponsesReasoningItem = {"type": "reasoning", "summary": summary}
    if decoded.encrypted_content is not None:
        item["encrypted_content"] = decoded.encrypted_content
    return AnthropicThinkingDecode(item=item, classification=decoded.classification)


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
