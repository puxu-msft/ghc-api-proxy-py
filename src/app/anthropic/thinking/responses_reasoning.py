import base64
import binascii
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class AnthropicThinkingDecode:
    item: ResponsesReasoningItem | None
    malformed_payload: bool = False


def _encode_encrypted_content(encrypted_content: str | None) -> str:
    if not encrypted_content:
        return SYNTHETIC_REASONING_SIGNATURE_PREFIX
    payload = base64.urlsafe_b64encode(encrypted_content.encode()).decode().rstrip("=")
    return f"{SYNTHETIC_REASONING_SIGNATURE_PREFIX}{payload}"


def _decode_encrypted_content(payload: str) -> tuple[str | None, bool]:
    encoded = payload.partition("=")[0]
    encoded = "".join(
        character
        for character in encoded
        if character.isascii() and (character.isalnum() or character in "-_+/")
    )
    malformed = encoded != payload or any(character in "+/" for character in encoded)
    if len(encoded) % 4 == 1:
        encoded = encoded[:-1]
        malformed = True
    padding = "=" * (-len(encoded) % 4)
    try:
        decoded = base64.b64decode(
            f"{encoded}{padding}",
            altchars=b"-_",
            validate=False,
        )
    except (ValueError, binascii.Error):
        return None, True
    try:
        return decoded.decode(), malformed
    except UnicodeDecodeError:
        return decoded.decode(errors="replace"), True


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
        if not thinking and not encrypted:
            continue

        blocks.append(
            {
                "type": "thinking",
                "thinking": thinking,
                "signature": _encode_encrypted_content(encrypted),
            }
        )

    return blocks


def anthropic_thinking_to_responses(
    block: Mapping[str, object],
) -> ResponsesReasoningItem | None:
    """Recover one Responses reasoning item only from this bridge's carrier."""
    return decode_anthropic_thinking(block).item


def decode_anthropic_thinking(block: Mapping[str, object]) -> AnthropicThinkingDecode:
    """Recover one item and classify non-canonical payloads without rejecting Node vectors."""
    if block.get("type") != "thinking":
        return AnthropicThinkingDecode(item=None)
    thinking = block.get("thinking")
    signature = block.get("signature")
    if not isinstance(thinking, str) or not isinstance(signature, str):
        return AnthropicThinkingDecode(item=None)

    encrypted_content: str | None = None
    carries_payload = False
    malformed_payload = False
    if signature == SYNTHETIC_REASONING_SIGNATURE:
        pass
    elif signature.startswith(SYNTHETIC_REASONING_SIGNATURE_PREFIX):
        payload = signature.removeprefix(SYNTHETIC_REASONING_SIGNATURE_PREFIX)
        carries_payload = bool(payload)
        if carries_payload:
            encrypted_content, malformed_payload = _decode_encrypted_content(payload)
    else:
        return AnthropicThinkingDecode(item=None)

    summary: list[ResponsesSummaryText] = []
    if thinking:
        summary.append({"type": "summary_text", "text": thinking})
    item: ResponsesReasoningItem = {"type": "reasoning", "summary": summary}
    if carries_payload and encrypted_content is not None:
        item["encrypted_content"] = encrypted_content
    return AnthropicThinkingDecode(item=item, malformed_payload=malformed_payload)
