from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Literal, cast

PROJECT_SYNTHETIC_REASONING_NAMESPACE = "ghc-api-proxy:synthetic-reasoning:"
PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX = (
    f"{PROJECT_SYNTHETIC_REASONING_NAMESPACE}v1:"
)
PROJECT_SYNTHETIC_REASONING_SIGNATURE = f"{PROJECT_SYNTHETIC_REASONING_NAMESPACE}v1"
UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX = "copilot-api:synthetic-reasoning:v1:"
UPSTREAM_SYNTHETIC_REASONING_SIGNATURE = "copilot-api:synthetic-reasoning:v1"
REASONING_ENCRYPTED_CONTENT_TAG = "openai.responses.reasoning.encrypted_content"

_PROJECT_V1_FIELDS = frozenset({"tag", "encrypted_content"})
_BASE64URL_PATTERN = re.compile(r"[A-Za-z0-9_-]+")

type ReasoningCarrierClassification = Literal[
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
class DecodedReasoningCarrier:
    classification: ReasoningCarrierClassification
    encrypted_content: str | None = None

    @property
    def malformed(self) -> bool:
        return self.classification in {
            "project_malformed_v1",
            "upstream_malformed_v1",
        }


class _DuplicateKeyError(ValueError):
    pass


def encode_reasoning_carrier(encrypted_content: str | None) -> str:
    """Encode a continuation payload using the project's canonical v1 carrier."""
    if not encrypted_content:
        return PROJECT_SYNTHETIC_REASONING_SIGNATURE
    payload = {
        "tag": REASONING_ENCRYPTED_CONTENT_TAG,
        "encrypted_content": encrypted_content,
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(serialized).decode().rstrip("=")
    return f"{PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX}{encoded}"


def is_direct_messages_synthetic_signature(signature: str) -> bool:
    """Return whether a proxy-owned carrier must be removed from the Messages leg."""
    return signature.startswith(PROJECT_SYNTHETIC_REASONING_NAMESPACE) or (
        signature == UPSTREAM_SYNTHETIC_REASONING_SIGNATURE
        or signature.startswith(UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX)
    )


def decode_reasoning_carrier(signature: str) -> DecodedReasoningCarrier:
    """Classify and decode project v1 before supported upstream compatibility forms."""
    if signature == PROJECT_SYNTHETIC_REASONING_SIGNATURE:
        return DecodedReasoningCarrier("project_bare_v1")
    if signature.startswith(PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX):
        payload = signature.removeprefix(PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX)
        encrypted_content = _decode_project_payload(payload)
        if encrypted_content is None:
            return DecodedReasoningCarrier("project_malformed_v1")
        return DecodedReasoningCarrier("project_v1", encrypted_content)
    if signature.startswith(PROJECT_SYNTHETIC_REASONING_NAMESPACE):
        return DecodedReasoningCarrier("project_unknown_version")

    if signature.startswith(UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX):
        payload = signature.removeprefix(UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX)
        if not payload:
            return DecodedReasoningCarrier("upstream_bare_v1")
        encrypted_content = _decode_upstream_payload(payload)
        if encrypted_content is None:
            return DecodedReasoningCarrier("upstream_malformed_v1")
        return DecodedReasoningCarrier("upstream_v1", encrypted_content)
    if signature == UPSTREAM_SYNTHETIC_REASONING_SIGNATURE:
        return DecodedReasoningCarrier("upstream_legacy_bare")
    return DecodedReasoningCarrier("foreign")


def _decode_project_payload(payload: str) -> str | None:
    decoded = _decode_canonical_base64url(payload)
    if decoded is None:
        return None
    try:
        document = json.loads(decoded, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKeyError):
        return None
    if not isinstance(document, dict) or document.keys() != _PROJECT_V1_FIELDS:
        return None
    typed_document = cast(dict[str, object], document)
    if typed_document.get("tag") != REASONING_ENCRYPTED_CONTENT_TAG:
        return None
    encrypted_content = typed_document.get("encrypted_content")
    if not isinstance(encrypted_content, str) or not encrypted_content:
        return None
    return encrypted_content


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
    "PROJECT_SYNTHETIC_REASONING_NAMESPACE",
    "PROJECT_SYNTHETIC_REASONING_SIGNATURE",
    "PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX",
    "REASONING_ENCRYPTED_CONTENT_TAG",
    "UPSTREAM_SYNTHETIC_REASONING_SIGNATURE",
    "UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX",
    "DecodedReasoningCarrier",
    "ReasoningCarrierClassification",
    "decode_reasoning_carrier",
    "encode_reasoning_carrier",
    "is_direct_messages_synthetic_signature",
]
