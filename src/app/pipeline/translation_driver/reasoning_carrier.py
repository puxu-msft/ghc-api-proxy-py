from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

PROJECT_SYNTHETIC_REASONING_NAMESPACE = "ghc-api-proxy:synthetic-reasoning:"
PROJECT_SYNTHETIC_REASONING_V1_PREFIX = f"{PROJECT_SYNTHETIC_REASONING_NAMESPACE}v1:"
PROJECT_SYNTHETIC_REASONING_V1 = f"{PROJECT_SYNTHETIC_REASONING_NAMESPACE}v1"
PROJECT_SYNTHETIC_REASONING_V2_PREFIX = f"{PROJECT_SYNTHETIC_REASONING_NAMESPACE}v2:"
PROJECT_SYNTHETIC_REASONING_V2 = f"{PROJECT_SYNTHETIC_REASONING_NAMESPACE}v2"

# Public v1 names stay stable for callers and stored histories created before v2.
PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX = PROJECT_SYNTHETIC_REASONING_V1_PREFIX
PROJECT_SYNTHETIC_REASONING_SIGNATURE = PROJECT_SYNTHETIC_REASONING_V1

UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX = "copilot-api:synthetic-reasoning:v1:"
UPSTREAM_SYNTHETIC_REASONING_SIGNATURE = "copilot-api:synthetic-reasoning:v1"

RESPONSES_ENCRYPTED_CONTENT = "openai.responses.reasoning.encrypted_content"
RESPONSES_SUMMARY_TEXT_LAYOUT = "openai.responses.reasoning.summary_text_layout"
ANTHROPIC_THINKING_SIGNATURE = "anthropic.messages.thinking.signature"
ANTHROPIC_REDACTED_THINKING_DATA = "anthropic.messages.redacted_thinking.data"
CHAT_REASONING_CONTENT = "openai.chat_completions.reasoning_content"

# Compatibility alias used by v1 tests and consumers.
REASONING_ENCRYPTED_CONTENT_TAG = RESPONSES_ENCRYPTED_CONTENT

_PROJECT_V1_FIELDS = frozenset({"tag", "encrypted_content"})
_V2_ENVELOPE_FIELDS = frozenset({"records"})
_V2_RECORD_FIELDS = frozenset({"type", "value"})
_V2_LAYOUT_FIELDS = frozenset({"lengths", "extensions"})
_KNOWN_V2_RECORD_TYPES = frozenset(
    {
        RESPONSES_ENCRYPTED_CONTENT,
        RESPONSES_SUMMARY_TEXT_LAYOUT,
        ANTHROPIC_THINKING_SIGNATURE,
        ANTHROPIC_REDACTED_THINKING_DATA,
        CHAT_REASONING_CONTENT,
    }
)
_BASE64URL_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
_RECORD_TYPE_PATTERN = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+")

type ReasoningCarrierClassification = Literal[
    "project_v2",
    "project_bare_v2",
    "project_malformed_v2",
    "project_v2_unsupported_record",
    "project_v2_direction_mismatch",
    "project_v2_profile_mismatch",
    "project_v2_presentation_mismatch",
    "project_v1",
    "project_bare_v1",
    "project_unknown_version",
    "project_malformed_v1",
    "upstream_v1",
    "upstream_bare_v1",
    "upstream_legacy_bare",
    "upstream_malformed_v1",
    "foreign",
]


@dataclass(frozen=True, slots=True)
class CarrierRecord:
    type: str
    value: Any


@dataclass(frozen=True, slots=True)
class DecodedReasoningCarrier:
    classification: ReasoningCarrierClassification
    records: tuple[CarrierRecord, ...] = ()
    encrypted_content: str | None = None

    @property
    def malformed(self) -> bool:
        return self.classification in {
            "project_malformed_v2",
            "project_malformed_v1",
            "upstream_malformed_v1",
        }

    @property
    def synthetic(self) -> bool:
        return self.classification != "foreign"

    @property
    def unknown_record_types(self) -> tuple[str, ...]:
        return tuple(record.type for record in self.records if record.type not in _KNOWN_V2_RECORD_TYPES)

    def record(self, record_type: str) -> CarrierRecord | None:
        return next((record for record in self.records if record.type == record_type), None)


class _DuplicateKeyError(ValueError):
    pass


class _NonJsonConstantError(ValueError):
    pass


def encode_reasoning_carrier(encrypted_content: str | None) -> str:
    """Encode the legacy project v1 carrier for compatibility tests and staged rollback."""
    if not encrypted_content:
        return PROJECT_SYNTHETIC_REASONING_V1
    payload = {
        "tag": RESPONSES_ENCRYPTED_CONTENT,
        "encrypted_content": encrypted_content,
    }
    return f"{PROJECT_SYNTHETIC_REASONING_V1_PREFIX}{_encode_document(payload)}"


def encode_reasoning_carrier_v2(records: Iterable[CarrierRecord]) -> str:
    """Encode a non-empty, typed v2 record envelope in its canonical producer spelling."""
    ordered = sorted(records, key=lambda record: record.type)
    if not ordered:
        raise ValueError("a v2 payload carrier requires at least one record")
    document = {
        "records": [{"type": record.type, "value": record.value} for record in ordered]
    }
    parsed = _records_from_v2_document(document)
    if parsed is None or len(parsed) != len(ordered):
        raise ValueError("records do not satisfy the v2 carrier schema")
    return f"{PROJECT_SYNTHETIC_REASONING_V2_PREFIX}{_encode_document(document)}"


def is_synthetic_reasoning_carrier(value: str) -> bool:
    """Whether a string belongs to either proxy carrier namespace rather than a provider."""
    return decode_reasoning_carrier(value).synthetic


def is_direct_messages_synthetic_signature(signature: str) -> bool:
    """Compatibility name for the resident last-mile guard predicate."""
    return is_synthetic_reasoning_carrier(signature)


def decode_reasoning_carrier(value: str) -> DecodedReasoningCarrier:
    """Classify project v2, project v1, supported upstream v1, then foreign values."""
    if value == PROJECT_SYNTHETIC_REASONING_V2:
        return DecodedReasoningCarrier("project_bare_v2")
    if value.startswith(PROJECT_SYNTHETIC_REASONING_V2_PREFIX):
        payload = value.removeprefix(PROJECT_SYNTHETIC_REASONING_V2_PREFIX)
        document = _decode_json_document(payload)
        records = _records_from_v2_document(document)
        if records is None:
            return DecodedReasoningCarrier("project_malformed_v2")
        return DecodedReasoningCarrier("project_v2", records=records)

    if value == PROJECT_SYNTHETIC_REASONING_V1:
        return DecodedReasoningCarrier("project_bare_v1")
    if value.startswith(PROJECT_SYNTHETIC_REASONING_V1_PREFIX):
        payload = value.removeprefix(PROJECT_SYNTHETIC_REASONING_V1_PREFIX)
        encrypted_content = _decode_project_v1_payload(payload)
        if encrypted_content is None:
            return DecodedReasoningCarrier("project_malformed_v1")
        return DecodedReasoningCarrier("project_v1", encrypted_content=encrypted_content)
    if value.startswith(PROJECT_SYNTHETIC_REASONING_NAMESPACE):
        return DecodedReasoningCarrier("project_unknown_version")

    if value.startswith(UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX):
        payload = value.removeprefix(UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX)
        if not payload:
            return DecodedReasoningCarrier("upstream_bare_v1")
        encrypted_content = _decode_upstream_payload(payload)
        if encrypted_content is None:
            return DecodedReasoningCarrier("upstream_malformed_v1")
        return DecodedReasoningCarrier("upstream_v1", encrypted_content=encrypted_content)
    if value == UPSTREAM_SYNTHETIC_REASONING_SIGNATURE:
        return DecodedReasoningCarrier("upstream_legacy_bare")
    return DecodedReasoningCarrier("foreign")


def _encode_document(document: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(serialized).decode().rstrip("=")


def _decode_json_document(payload: str) -> object | None:
    decoded = _decode_canonical_base64url(payload)
    if decoded is None:
        return None
    try:
        text = decoded.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_json_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateKeyError,
        _NonJsonConstantError,
    ):
        return None


def _reject_non_json_constant(value: str) -> object:
    raise _NonJsonConstantError(value)


def _decode_project_v1_payload(payload: str) -> str | None:
    document = _decode_json_document(payload)
    if not isinstance(document, dict) or document.keys() != _PROJECT_V1_FIELDS:
        return None
    typed_document = cast(dict[str, object], document)
    if typed_document.get("tag") != RESPONSES_ENCRYPTED_CONTENT:
        return None
    encrypted_content = typed_document.get("encrypted_content")
    if not isinstance(encrypted_content, str) or not encrypted_content:
        return None
    return encrypted_content


def _records_from_v2_document(document: object) -> tuple[CarrierRecord, ...] | None:
    if not isinstance(document, dict) or document.keys() != _V2_ENVELOPE_FIELDS:
        return None
    raw_records = cast(dict[str, object], document).get("records")
    if not isinstance(raw_records, list) or not raw_records:
        return None

    records: list[CarrierRecord] = []
    seen: set[str] = set()
    for raw_record in cast(list[object], raw_records):
        if not isinstance(raw_record, dict) or raw_record.keys() != _V2_RECORD_FIELDS:
            return None
        record = cast(dict[str, object], raw_record)
        record_type = record.get("type")
        if (
            not isinstance(record_type, str)
            or _RECORD_TYPE_PATTERN.fullmatch(record_type) is None
            or record_type in seen
        ):
            return None
        value = record.get("value")
        if not _valid_record_value(record_type, value):
            return None
        seen.add(record_type)
        records.append(CarrierRecord(record_type, value))
    return tuple(records)


def _valid_record_value(record_type: str, value: object) -> bool:
    if record_type == RESPONSES_ENCRYPTED_CONTENT:
        return isinstance(value, str)
    if record_type in {ANTHROPIC_THINKING_SIGNATURE, ANTHROPIC_REDACTED_THINKING_DATA}:
        return isinstance(value, str) and bool(value)
    if record_type == CHAT_REASONING_CONTENT:
        return value is None
    if record_type != RESPONSES_SUMMARY_TEXT_LAYOUT:
        return True
    if not isinstance(value, dict) or value.keys() != _V2_LAYOUT_FIELDS:
        return False
    layout = cast(dict[str, object], value)
    lengths = layout.get("lengths")
    extensions = layout.get("extensions")
    if not isinstance(lengths, list) or not isinstance(extensions, list):
        return False
    typed_lengths = cast(list[object], lengths)
    typed_extensions = cast(list[object], extensions)
    if len(typed_lengths) != len(typed_extensions):
        return False
    if any(
        not isinstance(length, int) or isinstance(length, bool) or length < 0
        for length in typed_lengths
    ):
        return False
    for extension in typed_extensions:
        if not isinstance(extension, dict):
            return False
        typed_extension = cast(dict[str, object], extension)
        if "type" in typed_extension or "text" in typed_extension:
            return False
    return True


def _decode_upstream_payload(payload: str) -> str | None:
    decoded = _decode_canonical_base64url(payload)
    if decoded is None:
        return None
    try:
        return decoded.decode()
    except UnicodeDecodeError:
        return None


def _decode_canonical_base64url(payload: str) -> bytes | None:
    if not _BASE64URL_PATTERN.fullmatch(payload):
        return None
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.b64decode(f"{payload}{padding}", altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        return None
    if base64.urlsafe_b64encode(decoded).decode().rstrip("=") != payload:
        return None
    return decoded


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise _DuplicateKeyError(key)
        document[key] = value
    return document


__all__ = [
    "ANTHROPIC_REDACTED_THINKING_DATA",
    "ANTHROPIC_THINKING_SIGNATURE",
    "CHAT_REASONING_CONTENT",
    "PROJECT_SYNTHETIC_REASONING_NAMESPACE",
    "PROJECT_SYNTHETIC_REASONING_SIGNATURE",
    "PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX",
    "PROJECT_SYNTHETIC_REASONING_V1",
    "PROJECT_SYNTHETIC_REASONING_V1_PREFIX",
    "PROJECT_SYNTHETIC_REASONING_V2",
    "PROJECT_SYNTHETIC_REASONING_V2_PREFIX",
    "REASONING_ENCRYPTED_CONTENT_TAG",
    "RESPONSES_ENCRYPTED_CONTENT",
    "RESPONSES_SUMMARY_TEXT_LAYOUT",
    "UPSTREAM_SYNTHETIC_REASONING_SIGNATURE",
    "UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX",
    "CarrierRecord",
    "DecodedReasoningCarrier",
    "ReasoningCarrierClassification",
    "decode_reasoning_carrier",
    "encode_reasoning_carrier",
    "encode_reasoning_carrier_v2",
    "is_direct_messages_synthetic_signature",
    "is_synthetic_reasoning_carrier",
]
