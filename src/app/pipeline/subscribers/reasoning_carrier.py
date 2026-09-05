"""Last-mile reasoning carrier guard and Anthropic thinking layout repair."""

from collections.abc import Mapping
from typing import Any, cast

from app.anthropic.thinking.destack import DestackStrategy, destack_content
from app.config.schema import AssistantMessageLayout
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.translation_driver.reasoning_bridge import (
    ReasoningBridgeError,
    classify_anthropic_carrier,
    classify_responses_carrier,
)
from app.pipeline.translation_driver.reasoning_carrier import decode_reasoning_carrier
from app.pipeline.translation_driver.semantic import TranslationRefused

SUBSCRIBER_ID = "builtin:reasoning-carrier-last-mile"

_LAYOUT_STRATEGY: dict[AssistantMessageLayout, DestackStrategy] = {
    False: "passthrough",
    "move_and_synthetic": "move_blocks",
    "synthetic_only": "insert_text",
}


def layout_strategy(layout: AssistantMessageLayout) -> DestackStrategy:
    """Map every configured layout spelling onto the existing deterministic transform."""
    return _LAYOUT_STRATEGY[layout]


async def guard_and_layout_reasoning(
    context: RequestContext,
    *,
    assistant_message_layout: AssistantMessageLayout,
) -> None:
    """Refuse leaked proxy carriers, then repair Anthropic-only thinking adjacency."""
    if context.target_format is WireFormat.ANTHROPIC_MESSAGES:
        _guard_anthropic_signatures(context.payload)
        _destack_anthropic_messages(context.payload, assistant_message_layout)
        return
    if context.target_format is WireFormat.OPENAI_RESPONSES:
        _guard_responses_encrypted_content(context.payload)


def _guard_anthropic_signatures(payload: Mapping[str, Any]) -> None:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return
    for message_index, raw_message in enumerate(cast(list[object], messages)):
        if not isinstance(raw_message, Mapping):
            continue
        content = cast(Mapping[str, Any], raw_message).get("content")
        if not isinstance(content, list):
            continue
        for block_index, raw_block in enumerate(cast(list[object], content)):
            if not isinstance(raw_block, Mapping):
                continue
            block = cast(Mapping[str, Any], raw_block)
            if block.get("type") == "thinking":
                signature = block.get("signature")
                thinking = block.get("thinking")
                if isinstance(signature, str):
                    classification = (
                        classify_anthropic_carrier(signature, thinking)
                        if isinstance(thinking, str)
                        else decode_reasoning_carrier(signature).classification
                    )
                    _reject_synthetic(
                        signature,
                        f"messages.{message_index}.content.{block_index}.signature",
                        classification=classification,
                    )
                continue
            if block.get("type") == "redacted_thinking":
                data = block.get("data")
                if isinstance(data, str):
                    _reject_synthetic(
                        data,
                        f"messages.{message_index}.content.{block_index}.data",
                    )


def _guard_responses_encrypted_content(payload: Mapping[str, Any]) -> None:
    items = payload.get("input")
    if not isinstance(items, list):
        return
    for item_index, raw_item in enumerate(cast(list[object], items)):
        if not isinstance(raw_item, Mapping):
            continue
        item = cast(Mapping[str, Any], raw_item)
        if item.get("type") != "reasoning":
            continue
        encrypted = item.get("encrypted_content")
        if isinstance(encrypted, str):
            try:
                classification = classify_responses_carrier(
                    encrypted,
                    item.get("summary"),
                )
            except ReasoningBridgeError:
                classification = decode_reasoning_carrier(encrypted).classification
            _reject_synthetic(
                encrypted,
                f"input.{item_index}.encrypted_content",
                classification=classification,
            )


def _reject_synthetic(
    value: str,
    field_path: str,
    *,
    classification: str | None = None,
) -> None:
    decoded = decode_reasoning_carrier(value)
    if not decoded.synthetic:
        return
    raise TranslationRefused(
        f"synthetic reasoning carrier {classification or decoded.classification} reached provider last-mile",
        code="reasoning_carrier_not_unwrapped",
        field_path=field_path,
    )


def _destack_anthropic_messages(
    payload: dict[str, Any], layout: AssistantMessageLayout
) -> None:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return
    strategy = layout_strategy(layout)
    for raw_message in cast(list[object], messages):
        if not isinstance(raw_message, dict):
            continue
        message = cast(dict[str, Any], raw_message)
        content = message.get("content")
        if message.get("role") != "assistant" or not isinstance(content, list):
            continue
        destacked, _ = destack_content(cast(list[Mapping[str, Any]], content), strategy)
        message["content"] = destacked


__all__ = [
    "SUBSCRIBER_ID",
    "guard_and_layout_reasoning",
    "layout_strategy",
]
