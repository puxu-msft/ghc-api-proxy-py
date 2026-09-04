from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from app.pipeline.translation_driver.content import (
    OpaqueFormat,
    ReasoningContent,
    ReasoningState,
    ReasoningSummaryPart,
)
from app.pipeline.translation_driver.reasoning_carrier import (
    ANTHROPIC_REDACTED_THINKING_DATA,
    ANTHROPIC_THINKING_SIGNATURE,
    CHAT_REASONING_CONTENT,
    PROJECT_SYNTHETIC_REASONING_V2,
    RESPONSES_ENCRYPTED_CONTENT,
    RESPONSES_SUMMARY_TEXT_LAYOUT,
    CarrierRecord,
    DecodedReasoningCarrier,
    ReasoningCarrierClassification,
    decode_reasoning_carrier,
    encode_reasoning_carrier_v2,
)

ANTHROPIC_MESSAGES = "anthropic-messages"
OPENAI_CHAT_COMPLETIONS = "openai-chat-completions"
OPENAI_RESPONSES = "openai-responses"


class CarrierSlot(StrEnum):
    ANTHROPIC_SIGNATURE = "anthropic-thinking-signature"
    RESPONSES_ENCRYPTED = "responses-reasoning-encrypted-content"


class ReasoningBridgeError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class ReasoningNotPortable(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RecoveredCarrier:
    content: ReasoningContent
    classification: str


_V2_SLOT_CLASSIFICATIONS = frozenset(
    {
        "project_v2_unsupported_record",
        "project_v2_direction_mismatch",
        "project_v2_profile_mismatch",
        "project_v2_presentation_mismatch",
    }
)


def classify_anthropic_carrier(
    signature: str, thinking: str
) -> ReasoningCarrierClassification:
    """Return the structural or slot-aware class for one Anthropic signature value."""
    decoded = decode_reasoning_carrier(signature)
    if decoded.classification != "project_v2":
        return decoded.classification
    try:
        _recover_from_anthropic_v2(decoded, thinking)
    except ReasoningBridgeError as error:
        return _slot_error_classification(error)
    return "project_v2"


def classify_responses_carrier(
    encrypted_content: str,
    summary: object,
) -> ReasoningCarrierClassification:
    """Return the structural or slot-aware class for one Responses encrypted value."""
    decoded = decode_reasoning_carrier(encrypted_content)
    if decoded.classification in {
        "project_bare_v2",
        "project_v1",
        "project_bare_v1",
        "upstream_v1",
        "upstream_bare_v1",
        "upstream_legacy_bare",
    }:
        return "project_v2_direction_mismatch"
    if decoded.classification != "project_v2":
        return decoded.classification
    try:
        parts = summary_parts_from_wire(summary)
        _recover_from_responses_v2(decoded, parts)
    except ReasoningBridgeError as error:
        return _slot_error_classification(error)
    return "project_v2"


def _slot_error_classification(
    error: ReasoningBridgeError,
) -> ReasoningCarrierClassification:
    if error.code not in _V2_SLOT_CLASSIFICATIONS:
        raise error
    return cast(ReasoningCarrierClassification, error.code)


def summary_parts_from_wire(value: object) -> tuple[ReasoningSummaryPart, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ReasoningBridgeError("reasoning_summary_malformed", "reasoning summary must be a list")
    parts: list[ReasoningSummaryPart] = []
    for index, raw_part in enumerate(cast(Sequence[object], value)):
        if not isinstance(raw_part, Mapping):
            raise ReasoningBridgeError(
                "reasoning_summary_malformed", f"summary[{index}] must be an object"
            )
        part = dict[str, Any](cast(Mapping[str, Any], raw_part))
        part_type = part.pop("type", None)
        text = part.pop("text", None)
        if part_type != "summary_text" or not isinstance(text, str):
            raise ReasoningBridgeError(
                "reasoning_summary_unsupported_part",
                f"summary[{index}] must be a summary_text part with string text",
            )
        parts.append(ReasoningSummaryPart(text=text, extensions=part))
    return tuple(parts)


def visible_summary(parts: Sequence[ReasoningSummaryPart]) -> str:
    return "".join(part.text for part in parts)


def read_chat_reasoning(text: str) -> ReasoningContent:
    """One Chat Completions visible reasoning extension, with no native opaque state."""
    return ReasoningContent(
        visible_text=text,
        source_format=OPENAI_CHAT_COMPLETIONS,
        summary_parts=_canonical_summary(text),
    )


def read_anthropic_reasoning(raw: Mapping[str, Any]) -> ReasoningContent:
    kind = str(raw.get("type", ""))
    if kind == "redacted_thinking":
        data = raw.get("data")
        if not isinstance(data, str):
            raise ReasoningBridgeError(
                "anthropic_redacted_thinking_malformed",
                "redacted_thinking.data must be a string",
            )
        return ReasoningContent(
            visible_text="",
            source_format=ANTHROPIC_MESSAGES,
            state=ReasoningState(OpaqueFormat.CLAUDE_SIGNATURE, data),
            redacted=True,
        )
    if kind != "thinking":
        raise ReasoningBridgeError("anthropic_reasoning_malformed", f"unsupported block {kind!r}")

    thinking = raw.get("thinking")
    signature = raw.get("signature", "")
    if not isinstance(thinking, str) or not isinstance(signature, str):
        raise ReasoningBridgeError(
            "anthropic_thinking_malformed",
            "thinking.thinking and thinking.signature must be strings",
        )
    if not signature:
        return ReasoningContent(visible_text=thinking, source_format=ANTHROPIC_MESSAGES)

    decoded = decode_reasoning_carrier(signature)
    if decoded.classification == "foreign":
        return ReasoningContent(
            visible_text=thinking,
            source_format=ANTHROPIC_MESSAGES,
            state=ReasoningState(OpaqueFormat.CLAUDE_SIGNATURE, signature),
        )
    if decoded.classification in {"project_v1", "upstream_v1"}:
        return ReasoningContent(
            visible_text=thinking,
            source_format=OPENAI_RESPONSES,
            summary_parts=_canonical_summary(thinking),
            state=ReasoningState(
                OpaqueFormat.RESPONSES_ENCRYPTED,
                cast(str, decoded.encrypted_content),
            ),
        )
    if decoded.classification in {
        "project_bare_v1",
        "upstream_bare_v1",
        "upstream_legacy_bare",
        "project_bare_v2",
    }:
        return ReasoningContent(
            visible_text=thinking,
            source_format=OPENAI_RESPONSES,
            summary_parts=_canonical_summary(thinking),
        )
    if decoded.classification == "project_v2":
        return _recover_from_anthropic_v2(decoded, thinking).content
    raise ReasoningBridgeError(decoded.classification, "synthetic thinking carrier is not recoverable")


def read_responses_reasoning(item: Mapping[str, Any]) -> ReasoningContent:
    if item.get("type") != "reasoning":
        raise ReasoningBridgeError("responses_reasoning_malformed", "item type must be reasoning")
    parts = summary_parts_from_wire(item.get("summary"))
    visible = visible_summary(parts)
    if "encrypted_content" not in item:
        return ReasoningContent(
            visible_text=visible,
            source_format=OPENAI_RESPONSES,
            summary_parts=parts,
        )

    encrypted = item.get("encrypted_content")
    if not isinstance(encrypted, str):
        raise ReasoningBridgeError(
            "responses_encrypted_content_malformed",
            "reasoning.encrypted_content must be a string when present",
        )
    decoded = decode_reasoning_carrier(encrypted)
    if decoded.classification == "foreign":
        return ReasoningContent(
            visible_text=visible,
            source_format=OPENAI_RESPONSES,
            summary_parts=parts,
            state=ReasoningState(OpaqueFormat.RESPONSES_ENCRYPTED, encrypted),
        )
    if decoded.classification == "project_v2":
        return _recover_from_responses_v2(decoded, parts).content
    if decoded.classification == "project_bare_v2":
        raise ReasoningBridgeError(
            "project_v2_direction_mismatch",
            "bare v2 is not legal in Responses encrypted_content",
        )
    if decoded.classification in {
        "project_v1",
        "project_bare_v1",
        "upstream_v1",
        "upstream_bare_v1",
        "upstream_legacy_bare",
    }:
        raise ReasoningBridgeError(
            "project_v2_direction_mismatch",
            "an Anthropic-signature carrier cannot occupy Responses encrypted_content",
        )
    raise ReasoningBridgeError(decoded.classification, "synthetic encrypted carrier is not recoverable")


def reasoning_to_anthropic(
    content: ReasoningContent, *, bridge_for_client: bool
) -> dict[str, Any]:
    if content.source_format == ANTHROPIC_MESSAGES:
        state = content.state
        if state is None or state.format is not OpaqueFormat.CLAUDE_SIGNATURE:
            raise ReasoningNotPortable("Anthropic reasoning has no native signature state")
        if content.redacted:
            return {"type": "redacted_thinking", "data": state.value}
        return {"type": "thinking", "thinking": content.visible_text, "signature": state.value}

    if content.source_format == OPENAI_CHAT_COMPLETIONS:
        if not bridge_for_client or content.state is not None or content.redacted:
            raise ReasoningNotPortable(
                "Chat Completions reasoning cannot be sent to an Anthropic upstream"
            )
        return {
            "type": "thinking",
            "thinking": content.visible_text,
            "signature": _carrier_for_chat_anthropic_client(content),
        }

    if content.source_format != OPENAI_RESPONSES or not bridge_for_client:
        raise ReasoningNotPortable(
            f"{content.source_format or 'unknown'} reasoning cannot be sent to an Anthropic upstream"
        )
    return {
        "type": "thinking",
        "thinking": content.visible_text,
        "signature": _carrier_for_anthropic_client(content),
    }


def reasoning_to_responses(
    content: ReasoningContent, *, bridge_for_client: bool
) -> dict[str, Any]:
    if content.source_format == OPENAI_RESPONSES:
        item: dict[str, Any] = {
            "type": "reasoning",
            "summary": content.responses_summary(),
        }
        state = content.state
        if state is not None:
            if state.format is not OpaqueFormat.RESPONSES_ENCRYPTED:
                raise ReasoningNotPortable("reasoning state does not belong to Responses")
            item["encrypted_content"] = state.value
        return item

    if content.source_format == OPENAI_CHAT_COMPLETIONS:
        if not bridge_for_client or content.state is not None or content.redacted:
            raise ReasoningNotPortable(
                "Chat Completions reasoning cannot be sent to a Responses upstream"
            )
        return {
            "type": "reasoning",
            "summary": content.responses_summary(),
            "encrypted_content": encode_reasoning_carrier_v2(
                [CarrierRecord(CHAT_REASONING_CONTENT, None)]
            ),
        }

    if content.source_format != ANTHROPIC_MESSAGES or not bridge_for_client:
        raise ReasoningNotPortable("Anthropic reasoning cannot be sent to a Responses upstream")
    item = {
        "type": "reasoning",
        "summary": [] if content.redacted else content.responses_summary(),
    }
    if content.state is not None or content.redacted:
        item["encrypted_content"] = _carrier_for_responses_client(content)
    return item


def _carrier_for_chat_anthropic_client(content: ReasoningContent) -> str:
    parts = content.summary_parts
    if parts is None:
        parts = _canonical_summary(content.visible_text)
    return encode_reasoning_carrier_v2(
        [
            _summary_layout_record(parts),
            CarrierRecord(CHAT_REASONING_CONTENT, None),
        ]
    )


def _carrier_for_anthropic_client(content: ReasoningContent) -> str:
    parts = content.summary_parts
    if parts is None:
        parts = _canonical_summary(content.visible_text)
    state = content.state
    if state is None and _is_canonical_summary(parts, content.visible_text):
        return PROJECT_SYNTHETIC_REASONING_V2

    records = [_summary_layout_record(parts)]
    if state is not None:
        if state.format is not OpaqueFormat.RESPONSES_ENCRYPTED:
            raise ReasoningNotPortable("only Responses opaque state belongs in this carrier")
        records.append(CarrierRecord(RESPONSES_ENCRYPTED_CONTENT, state.value))
    return encode_reasoning_carrier_v2(records)


def _carrier_for_responses_client(content: ReasoningContent) -> str:
    state = content.state
    if state is None or state.format is not OpaqueFormat.CLAUDE_SIGNATURE:
        raise ReasoningNotPortable("Anthropic reasoning has no native state to carry")
    record_type = (
        ANTHROPIC_REDACTED_THINKING_DATA if content.redacted else ANTHROPIC_THINKING_SIGNATURE
    )
    return encode_reasoning_carrier_v2([CarrierRecord(record_type, state.value)])


def _recover_from_anthropic_v2(
    decoded: DecodedReasoningCarrier, thinking: str
) -> RecoveredCarrier:
    _reject_unknown_records(decoded)
    record_types = {record.type for record in decoded.records}
    if record_types & {ANTHROPIC_THINKING_SIGNATURE, ANTHROPIC_REDACTED_THINKING_DATA}:
        raise ReasoningBridgeError(
            "project_v2_direction_mismatch",
            "Anthropic-native records cannot occupy an Anthropic signature carrier",
        )
    chat_marker = decoded.record(CHAT_REASONING_CONTENT)
    layout = decoded.record(RESPONSES_SUMMARY_TEXT_LAYOUT)
    if chat_marker is not None:
        if record_types != {RESPONSES_SUMMARY_TEXT_LAYOUT, CHAT_REASONING_CONTENT}:
            raise ReasoningBridgeError(
                "project_v2_profile_mismatch",
                "Anthropic Chat carrier requires exactly layout and Chat marker records",
            )
        parts = _parts_from_layout(cast(CarrierRecord, layout).value, thinking)
        return RecoveredCarrier(
            ReasoningContent(
                visible_text=thinking,
                source_format=OPENAI_CHAT_COMPLETIONS,
                summary_parts=parts,
            ),
            "project_v2",
        )

    allowed = {RESPONSES_SUMMARY_TEXT_LAYOUT, RESPONSES_ENCRYPTED_CONTENT}
    if layout is None or not record_types <= allowed:
        raise ReasoningBridgeError(
            "project_v2_profile_mismatch",
            "Anthropic signature payload requires layout and optional Responses opaque state",
        )

    parts = _parts_from_layout(layout.value, thinking)
    encrypted = decoded.record(RESPONSES_ENCRYPTED_CONTENT)
    state = (
        ReasoningState(OpaqueFormat.RESPONSES_ENCRYPTED, cast(str, encrypted.value))
        if encrypted is not None
        else None
    )
    return RecoveredCarrier(
        ReasoningContent(
            visible_text=thinking,
            source_format=OPENAI_RESPONSES,
            summary_parts=parts,
            state=state,
        ),
        "project_v2",
    )


def _recover_from_responses_v2(
    decoded: DecodedReasoningCarrier,
    parts: tuple[ReasoningSummaryPart, ...],
) -> RecoveredCarrier:
    _reject_unknown_records(decoded)
    record_types = {record.type for record in decoded.records}
    chat_marker = decoded.record(CHAT_REASONING_CONTENT)
    if chat_marker is not None:
        if record_types != {CHAT_REASONING_CONTENT}:
            raise ReasoningBridgeError(
                "project_v2_profile_mismatch",
                "Responses Chat carrier requires exactly one Chat marker record",
            )
        if not _is_canonical_responses_projection(parts) or not parts:
            raise ReasoningBridgeError(
                "project_v2_presentation_mismatch",
                "Chat reasoning must use one non-empty canonical Responses summary part",
            )
        return RecoveredCarrier(
            ReasoningContent(
                visible_text=visible_summary(parts),
                source_format=OPENAI_CHAT_COMPLETIONS,
                summary_parts=parts,
            ),
            "project_v2",
        )

    if record_types & {RESPONSES_SUMMARY_TEXT_LAYOUT, RESPONSES_ENCRYPTED_CONTENT}:
        raise ReasoningBridgeError(
            "project_v2_direction_mismatch",
            "Responses-native records cannot occupy Responses encrypted_content",
        )
    signature = decoded.record(ANTHROPIC_THINKING_SIGNATURE)
    redacted = decoded.record(ANTHROPIC_REDACTED_THINKING_DATA)
    if (signature is None) == (redacted is None) or len(decoded.records) != 1:
        raise ReasoningBridgeError(
            "project_v2_profile_mismatch",
            "Responses carrier requires exactly one Anthropic native-state record",
        )
    if redacted is not None:
        if parts:
            raise ReasoningBridgeError(
                "project_v2_presentation_mismatch",
                "redacted thinking cannot carry a visible Responses summary",
            )
        return RecoveredCarrier(
            ReasoningContent(
                visible_text="",
                source_format=ANTHROPIC_MESSAGES,
                state=ReasoningState(OpaqueFormat.CLAUDE_SIGNATURE, cast(str, redacted.value)),
                redacted=True,
            ),
            "project_v2",
        )
    if not _is_canonical_responses_projection(parts):
        raise ReasoningBridgeError(
            "project_v2_presentation_mismatch",
            "Anthropic thinking must use the canonical Responses summary projection",
        )
    visible = visible_summary(parts)
    return RecoveredCarrier(
        ReasoningContent(
            visible_text=visible,
            source_format=ANTHROPIC_MESSAGES,
            state=ReasoningState(
                OpaqueFormat.CLAUDE_SIGNATURE,
                cast(str, cast(CarrierRecord, signature).value),
            ),
        ),
        "project_v2",
    )


def _reject_unknown_records(decoded: DecodedReasoningCarrier) -> None:
    if decoded.unknown_record_types:
        joined = ", ".join(decoded.unknown_record_types)
        raise ReasoningBridgeError(
            "project_v2_unsupported_record", f"unsupported v2 record type(s): {joined}"
        )


def _summary_layout_record(parts: Sequence[ReasoningSummaryPart]) -> CarrierRecord:
    return CarrierRecord(
        RESPONSES_SUMMARY_TEXT_LAYOUT,
        {
            "lengths": [len(part.text.encode()) for part in parts],
            "extensions": [dict(part.extensions) for part in parts],
        },
    )


def _parts_from_layout(value: object, thinking: str) -> tuple[ReasoningSummaryPart, ...]:
    # The structural codec already validated this shape. Keeping the cross-field validation here
    # makes profile and presentation failures distinct rather than teaching the JSON decoder about
    # the slot surrounding its payload.
    layout = cast(dict[str, object], value)
    lengths = cast(list[int], layout["lengths"])
    extensions = cast(list[dict[str, Any]], layout["extensions"])
    encoded = thinking.encode()
    if sum(lengths) != len(encoded):
        raise ReasoningBridgeError(
            "project_v2_presentation_mismatch",
            "summary layout byte lengths do not cover thinking text",
        )
    parts: list[ReasoningSummaryPart] = []
    start = 0
    for length, extension in zip(lengths, extensions, strict=True):
        chunk = encoded[start : start + length]
        try:
            text = chunk.decode()
        except UnicodeDecodeError as error:
            raise ReasoningBridgeError(
                "project_v2_presentation_mismatch",
                "summary layout splits a UTF-8 code point",
            ) from error
        parts.append(ReasoningSummaryPart(text=text, extensions=extension))
        start += length
    return tuple(parts)


def _canonical_summary(text: str) -> tuple[ReasoningSummaryPart, ...]:
    return (ReasoningSummaryPart(text),) if text else ()


def _is_canonical_summary(
    parts: Sequence[ReasoningSummaryPart], visible_text: str
) -> bool:
    return tuple(parts) == _canonical_summary(visible_text)


def _is_canonical_responses_projection(parts: Sequence[ReasoningSummaryPart]) -> bool:
    return not parts or (
        len(parts) == 1 and bool(parts[0].text) and not parts[0].extensions
    )


__all__ = [
    "ANTHROPIC_MESSAGES",
    "OPENAI_CHAT_COMPLETIONS",
    "OPENAI_RESPONSES",
    "CarrierSlot",
    "ReasoningBridgeError",
    "ReasoningNotPortable",
    "RecoveredCarrier",
    "classify_anthropic_carrier",
    "classify_responses_carrier",
    "read_anthropic_reasoning",
    "read_chat_reasoning",
    "read_responses_reasoning",
    "reasoning_to_anthropic",
    "reasoning_to_responses",
    "summary_parts_from_wire",
    "visible_summary",
]
