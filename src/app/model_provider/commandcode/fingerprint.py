"""Load a validated fingerprint snapshot captured from a Command Code CLI."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from app.config.paths import expand_user_path

FINGERPRINT_SCHEMA_VERSION = 1


class FingerprintSnapshotError(ValueError):
    """The configured fingerprint snapshot is missing or unsafe to use."""


class FingerprintSnapshotStore:
    def __init__(self, path: str) -> None:
        self._path = expand_user_path(path)

    def load(self, api_key: str) -> dict[str, Any]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except OSError as error:
            raise FingerprintSnapshotError(
                f"cannot read fingerprint snapshot {self._path}"
            ) from error
        except json.JSONDecodeError as error:
            raise FingerprintSnapshotError(
                f"fingerprint snapshot {self._path} is not valid JSON"
            ) from error

        if not isinstance(raw, dict):
            raise FingerprintSnapshotError("fingerprint snapshot must be an object")
        snapshot = cast(dict[str, Any], raw)
        if snapshot.get("schema_version") != FINGERPRINT_SCHEMA_VERSION:
            raise FingerprintSnapshotError("unsupported fingerprint snapshot schema")
        if snapshot.get("source") != "commandcode-cli":
            raise FingerprintSnapshotError("fingerprint snapshot source is not Command Code CLI")

        expected_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        if snapshot.get("api_key_sha256") != expected_key_hash:
            raise FingerprintSnapshotError(
                "fingerprint snapshot does not belong to the configured API key"
            )

        captured_at = snapshot.get("captured_at")
        if not isinstance(captured_at, str):
            raise FingerprintSnapshotError("fingerprint snapshot has no capture time")
        try:
            captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise FingerprintSnapshotError(
                "fingerprint snapshot capture time is not an ISO-8601 timestamp"
            ) from error
        if captured.tzinfo is None:
            raise FingerprintSnapshotError(
                "fingerprint snapshot capture time has no timezone"
            )

        expires_at = snapshot.get("expires_at")
        if not isinstance(expires_at, str):
            raise FingerprintSnapshotError("fingerprint snapshot has no expiry")
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise FingerprintSnapshotError(
                "fingerprint snapshot expiry is not an ISO-8601 timestamp"
            ) from error
        if expiry.tzinfo is None:
            raise FingerprintSnapshotError("fingerprint snapshot expiry has no timezone")
        if expiry.astimezone(UTC) <= datetime.now(UTC):
            raise FingerprintSnapshotError("fingerprint snapshot has expired")

        fingerprint = snapshot.get("fingerprint")
        if not isinstance(fingerprint, dict):
            raise FingerprintSnapshotError("fingerprint snapshot has no fingerprint")
        typed_fingerprint = cast(dict[str, Any], fingerprint)
        thumbmark = typed_fingerprint.get("thumbmark")
        components = typed_fingerprint.get("components")
        if not isinstance(thumbmark, str) or not thumbmark:
            raise FingerprintSnapshotError("fingerprint thumbmark must be a string")
        if not isinstance(components, Mapping):
            raise FingerprintSnapshotError("fingerprint components must be an object")
        return {
            "thumbmark": thumbmark,
            "components": dict(cast(Mapping[str, Any], components)),
        }


def api_key_sha256(api_key: str) -> str:
    """Return the redacted API-key binding used by capture snapshots."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
