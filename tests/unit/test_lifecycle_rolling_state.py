import hashlib
import json
from pathlib import Path

import pytest

from app.lifecycle.rolling.state import (
    GenerationRecord,
    RollingState,
    RollingStateError,
    RollingStateStore,
)


def test_state_roundtrip_keeps_apply_gate_disabled(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = RollingStateStore(path)
    state = RollingState(
        committed_generation="g0000000000000001",
        committed_release="release-a",
    )
    generation_id = "g0000000000000001"
    state.generations[generation_id] = GenerationRecord(
        generation_id=generation_id,
        release_id="release-a",
        control_socket="/run/g1/control.sock",
        unit_name="ghc-api-proxy-generation@g0000000000000001.service",
        role="committed",
        phase="ready_accepting",
        ready=True,
        accepting=True,
        pid=42,
    )
    store.replace(state)

    loaded = store.load()

    assert loaded.apply_enabled is False
    assert "apply_gate_disabled_until_stage6" in loaded.apply_blockers
    assert loaded.generations[generation_id].pid == 42


def test_state_checksum_corruption_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = RollingStateStore(path)
    store.replace(RollingState())
    record = json.loads(path.read_text(encoding="utf-8"))
    record["payload"]["apply_enabled"] = True
    path.write_text(json.dumps(record), encoding="utf-8")
    checkpoint = path.with_name(path.name + ".checkpoint")
    checkpoint.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(RollingStateError, match=r"no valid|checksum"):
        store.load()


def test_initialized_state_recovers_missing_primary_from_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = RollingStateStore(path)
    store.replace(RollingState())
    path.unlink()

    assert store.load().committed_generation is None


def test_initialized_state_without_primary_or_checkpoint_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = RollingStateStore(path)
    store.replace(RollingState())
    path.unlink()
    path.with_name(path.name + ".checkpoint").unlink()

    with pytest.raises(RollingStateError, match="no valid"):
        store.load()


def test_state_rejects_generation_map_identity_mismatch(tmp_path: Path) -> None:
    state = RollingState()
    state.generations["g0000000000000001"] = GenerationRecord(
        generation_id="g0000000000000002",
        release_id="release-a",
        control_socket="/run/g2/control.sock",
        unit_name="unit",
        role="candidate",
        phase="reserved",
        ready=False,
        accepting=False,
        pid=0,
    )
    with pytest.raises(RollingStateError, match="map key"):
        RollingStateStore(tmp_path / "state.json").replace(state)


def test_loader_chooses_newer_checkpoint_over_valid_old_primary(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = RollingStateStore(path)
    first = RollingState()
    store.replace(first)
    old_primary = path.read_bytes()
    second = store.load()
    second.apply_blockers.append("newer-checkpoint")
    store.replace(second)
    path.write_bytes(old_primary)

    loaded = store.load()
    assert "newer-checkpoint" in loaded.apply_blockers


def test_loader_skips_domain_invalid_primary_and_uses_valid_checkpoint(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    store = RollingStateStore(path)
    store.replace(RollingState())
    record = json.loads(path.read_text(encoding="utf-8"))
    record["payload"]["controller_status"] = "degraded_conflict"
    record["payload"]["conflict_error"] = None
    canonical = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"))
    record["checksum"] = hashlib.sha256(canonical.encode()).hexdigest()
    path.write_text(json.dumps(record), encoding="utf-8")

    loaded = store.load()

    assert loaded.controller_status == "normal"


def test_loader_skips_newer_primary_with_unknown_generation_role_and_phase(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    store = RollingStateStore(path)
    store.replace(RollingState())
    record = json.loads(path.read_text(encoding="utf-8"))
    record["payload"]["revision"] += 1
    record["payload"]["generations"] = {
        "g0000000000000001": {
            "generation_id": "g0000000000000001",
            "release_id": "release-a",
            "control_socket": "/run/control.sock",
            "unit_name": "unit",
            "role": "not-a-role",
            "phase": "not-a-phase",
            "ready": False,
            "accepting": False,
            "pid": 0,
            "last_error": None,
            "verification_level": "status_only",
        }
    }
    canonical = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"))
    record["checksum"] = hashlib.sha256(canonical.encode()).hexdigest()
    path.write_text(json.dumps(record), encoding="utf-8")

    loaded = store.load()

    assert loaded.generations == {}


@pytest.mark.parametrize(
    ("role", "phase", "ready", "accepting"),
    [
        ("committed", "ready_accepting", True, True),
        ("draining", "quiescing", True, False),
    ],
)
def test_loader_skips_newer_primary_with_cross_field_record_conflict(
    tmp_path: Path,
    role: str,
    phase: str,
    ready: bool,
    accepting: bool,
) -> None:
    path = tmp_path / "state.json"
    store = RollingStateStore(path)
    store.replace(RollingState())
    record = json.loads(path.read_text(encoding="utf-8"))
    record["payload"]["revision"] += 1
    record["payload"]["generations"] = {
        "g0000000000000001": {
            "generation_id": "g0000000000000001",
            "release_id": "release-a",
            "control_socket": "/run/control.sock",
            "unit_name": "unit",
            "role": role,
            "phase": phase,
            "ready": ready,
            "accepting": accepting,
            "pid": 42,
            "last_error": None,
            "verification_level": "status_only",
        }
    }
    canonical = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"))
    record["checksum"] = hashlib.sha256(canonical.encode()).hexdigest()
    path.write_text(json.dumps(record), encoding="utf-8")

    assert store.load().generations == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("apply_enabled", "false"),
        ("apply_blockers", "blocked"),
        ("revision", True),
    ],
)
def test_state_rejects_checksum_valid_but_wrong_schema_types(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    path = tmp_path / "state.json"
    store = RollingStateStore(path)
    store.replace(RollingState())
    for artifact in (path, path.with_name(path.name + ".checkpoint")):
        record = json.loads(artifact.read_text(encoding="utf-8"))
        record["payload"][field] = value
        canonical = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"))
        record["checksum"] = hashlib.sha256(canonical.encode()).hexdigest()
        artifact.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(RollingStateError, match="no valid"):
        store.load()
