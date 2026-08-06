import base64
import binascii
from collections.abc import Mapping, Sequence
from typing import Literal, NotRequired, TypedDict, cast

SYNTHETIC_REASONING_SIGNATURE_PREFIX = "copilot-api:synthetic-reasoning:v1:"
SYNTHETIC_REASONING_SIGNATURE = "copilot-api:synthetic-reasoning:v1"


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


def _encode_encrypted_content(encrypted_content: str | None) -> str:
    if not encrypted_content:
        return SYNTHETIC_REASONING_SIGNATURE_PREFIX
    payload = base64.urlsafe_b64encode(encrypted_content.encode()).decode().rstrip("=")
    return f"{SYNTHETIC_REASONING_SIGNATURE_PREFIX}{payload}"


def _decode_encrypted_content(payload: str) -> str | None:
    encoded = payload.partition("=")[0]
    encoded = "".join(
        character
        for character in encoded
        if character.isascii() and (character.isalnum() or character in "-_")
    )
    if len(encoded) % 4 == 1:
        encoded = encoded[:-1]
    padding = "=" * (-len(encoded) % 4)
    try:
        decoded = base64.b64decode(
            f"{encoded}{padding}",
            altchars=b"-_",
            validate=False,
        )
    except (ValueError, binascii.Error):
        return None
    return decoded.decode(errors="replace")


def responses_reasoning_to_anthropic(
    items: Sequence[Mapping[str, object]],
) -> AnthropicThinkingBlock | None:
    """Aggregate Responses output reasoning into at most one Anthropic thinking block."""
    summary_text: list[str] = []
    encrypted_content: str | None = None
    for item in items:
        if item.get("type") != "reasoning":
            continue

        summary = item.get("summary")
        if not isinstance(summary, list):
            return None

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
        if encrypted:
            encrypted_content = encrypted

    thinking = "".join(summary_text)
    if not thinking:
        return None

    return {
        "type": "thinking",
        "thinking": thinking,
        "signature": _encode_encrypted_content(encrypted_content),
    }


def anthropic_thinking_to_responses(
    block: Mapping[str, object],
) -> ResponsesReasoningItem | None:
    """Recover one Responses reasoning item only from this bridge's carrier."""
    if block.get("type") != "thinking":
        return None
    thinking = block.get("thinking")
    signature = block.get("signature")
    if not isinstance(thinking, str) or not isinstance(signature, str):
        return None

    encrypted_content: str | None = None
    carries_payload = False
    if signature == SYNTHETIC_REASONING_SIGNATURE:
        pass
    elif signature.startswith(SYNTHETIC_REASONING_SIGNATURE_PREFIX):
        payload = signature.removeprefix(SYNTHETIC_REASONING_SIGNATURE_PREFIX)
        carries_payload = bool(payload)
        if carries_payload:
            encrypted_content = _decode_encrypted_content(payload)
    else:
        return None

    summary: list[ResponsesSummaryText] = []
    if thinking:
        summary.append({"type": "summary_text", "text": thinking})
    item: ResponsesReasoningItem = {"type": "reasoning", "summary": summary}
    if carries_payload and encrypted_content is not None:
        item["encrypted_content"] = encrypted_content
    return item
