import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from app.model_provider.commandcode.fingerprint import (
    FingerprintSnapshotError,
    FingerprintSnapshotStore,
    api_key_sha256,
)


def _write_snapshot(
    tmp_path: Path,
    *,
    api_key: str = "user_test",
    expires_at: str | None = None,
) -> Path:
    snapshot = {
        "schema_version": 1,
        "source": "commandcode-cli",
        "captured_at": datetime.now(UTC).isoformat(),
        "expires_at": expires_at
        or (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "api_key_sha256": api_key_sha256(api_key),
        "fingerprint": {
            "thumbmark": "cli-thumbmark",
            "components": {
                "platform": "linux",
                "arch": "x64",
                "runtime": "cli",
            },
        },
    }
    path = tmp_path / "fingerprint.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return path


def test_snapshot_store_loads_api_key_bound_unexpired_cli_snapshot(
    tmp_path: Path,
) -> None:
    path = _write_snapshot(tmp_path)

    loaded = FingerprintSnapshotStore(str(path)).load("user_test")

    assert loaded["thumbmark"] == "cli-thumbmark"
    assert loaded["components"]["runtime"] == "cli"


@pytest.mark.parametrize("kind", ["wrong_key", "expired"])
def test_snapshot_store_rejects_unusable_snapshot(tmp_path: Path, kind: str) -> None:
    path = _write_snapshot(tmp_path)
    snapshot = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    if kind == "wrong_key":
        snapshot["api_key_sha256"] = api_key_sha256("other")
    else:
        snapshot["expires_at"] = (
            datetime.now(UTC) - timedelta(seconds=1)
        ).isoformat()
    path.write_text(json.dumps(snapshot), encoding="utf-8")

    with pytest.raises(FingerprintSnapshotError):
        FingerprintSnapshotStore(str(path)).load("user_test")


def test_snapshot_store_rejects_non_cli_snapshot(tmp_path: Path) -> None:
    path = _write_snapshot(tmp_path)
    snapshot = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    snapshot["source"] = "generated"
    path.write_text(json.dumps(snapshot), encoding="utf-8")

    with pytest.raises(FingerprintSnapshotError, match="source"):
        FingerprintSnapshotStore(str(path)).load("user_test")
