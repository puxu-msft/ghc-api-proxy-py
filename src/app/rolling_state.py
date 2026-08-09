from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast


class RollingStateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GenerationRecord:
    generation_id: str
    release_id: str
    control_socket: str
    unit_name: str
    role: str
    phase: str
    ready: bool
    accepting: bool
    pid: int
    last_error: str | None = None
    verification_level: str = "status_only"


@dataclass(slots=True)
class RollingState:
    schema: int = 1
    revision: int = 0
    controller_status: str = "normal"
    conflict_error: str | None = None
    apply_enabled: bool = False
    apply_blockers: list[str] = field(
        default_factory=lambda: [
            "missing_private_canary_command",
            "missing_snapshot_isolation_contract",
            "missing_promote_demote_commands",
            "apply_gate_disabled_until_stage6",
        ]
    )
    committed_generation: str | None = None
    committed_release: str | None = None
    generations: dict[str, GenerationRecord] = field(
        default_factory=lambda: {},
    )


class RollingStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._checkpoint = path.with_name(path.name + ".checkpoint")
        self._initialized = path.with_name(path.name + ".initialized")

    def load(self) -> RollingState:
        if (
            not self._initialized.exists()
            and not self._path.exists()
            and not self._checkpoint.exists()
        ):
            return RollingState()
        valid: list[RollingState] = []
        for candidate in (self._path, self._checkpoint):
            try:
                state = self._load_path(candidate)
                self._validate_state(state)
            except RollingStateError:
                continue
            valid.append(state)
        if valid:
            return max(valid, key=lambda state: state.revision)
        raise RollingStateError("initialized rolling state has no valid primary or checkpoint")

    def _load_path(self, path: Path) -> RollingState:
        if not path.is_file():
            raise RollingStateError(f"rolling state artifact is missing: {path}")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            payload = cast(dict[str, Any], record["payload"])
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256(canonical.encode()).hexdigest() != record["checksum"]:
                raise RollingStateError("rolling state checksum mismatch")
            if payload.get("schema") != 1:
                raise RollingStateError("unsupported rolling state schema")
            self._validate_payload_types(payload)
            generation_values = cast(dict[str, dict[str, Any]], payload["generations"])
            generations: dict[str, GenerationRecord] = {
                key: GenerationRecord(**value)
                for key, value in generation_values.items()
            }
            return RollingState(
                schema=1,
                revision=cast(int, payload["revision"]),
                controller_status=cast(str, payload["controller_status"]),
                conflict_error=cast(str | None, payload["conflict_error"]),
                apply_enabled=cast(bool, payload["apply_enabled"]),
                apply_blockers=cast(list[str], payload["apply_blockers"]),
                committed_generation=payload.get("committed_generation"),
                committed_release=payload.get("committed_release"),
                generations=generations,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RollingStateError(f"invalid rolling state: {error}") from error

    def replace(self, state: RollingState) -> None:
        self._validate_state(state)
        state.revision += 1
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = asdict(state)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        content = json.dumps(
            {"payload": payload, "checksum": hashlib.sha256(canonical.encode()).hexdigest()},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self._replace_path(self._checkpoint, content)
        self._replace_path(self._path, content)
        if not self._initialized.exists():
            self._replace_path(self._initialized, b"initialized\n")

    def _replace_path(self, path: Path, content: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            dir=path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(path)
            directory_fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _validate_state(state: RollingState) -> None:
        if state.revision < 0:
            raise RollingStateError("state revision must be non-negative")
        if state.controller_status not in {"normal", "degraded_conflict"}:
            raise RollingStateError("invalid controller status")
        if state.controller_status == "degraded_conflict" and not state.conflict_error:
            raise RollingStateError("degraded conflict requires evidence")
        for key, record in state.generations.items():
            if key != record.generation_id:
                raise RollingStateError("generation map key does not match record identity")
            RollingStateStore._validate_generation_record(record)
        committed_records = [
            record
            for record in state.generations.values()
            if record.role == "committed"
        ]
        if state.committed_generation is None:
            if state.committed_release is not None:
                raise RollingStateError("committed release exists without generation")
            if committed_records:
                raise RollingStateError("committed record exists without committed tuple")
            return
        if len(committed_records) != 1:
            raise RollingStateError("committed tuple requires exactly one committed record")
        record = state.generations.get(state.committed_generation)
        if record is None:
            raise RollingStateError("committed generation is missing from generation map")
        if record.release_id != state.committed_release or record.role != "committed":
            raise RollingStateError("committed generation tuple is inconsistent")

    @staticmethod
    def _validate_generation_record(record: GenerationRecord) -> None:
        allowed_phases = {
            "reserved",
            "environment_ready",
            "started",
            "ready_accepting",
            "quiescing",
            "drained_standby",
            "stopping",
            "failed",
            "conflict",
            "exited",
        }
        allowed_roles = {"candidate", "committed", "draining", "failed", "conflict"}
        if record.role not in allowed_roles or record.phase not in allowed_phases:
            raise RollingStateError("generation role or phase is invalid")
        if record.pid < 0:
            raise RollingStateError("generation pid is invalid")
        if record.role == "candidate":
            if record.phase not in {"reserved", "environment_ready", "started"}:
                raise RollingStateError("candidate phase is invalid")
            if record.ready or record.accepting:
                raise RollingStateError("candidate cannot be ready before commit")
        elif record.role == "committed":
            if (
                record.phase != "ready_accepting"
                or not record.ready
                or not record.accepting
                or record.pid <= 0
            ):
                raise RollingStateError("committed generation state is invalid")
        elif record.role in {"failed", "conflict"}:
            if record.phase != record.role or record.ready or record.accepting:
                raise RollingStateError("failed/conflict generation state is invalid")
        elif record.role == "draining":
            if record.phase not in {"quiescing", "drained_standby", "stopping", "failed"}:
                raise RollingStateError("draining generation phase is invalid")
            if record.ready or record.accepting:
                raise RollingStateError("draining generation cannot be ready or accepting")

    @staticmethod
    def _validate_payload_types(payload: dict[str, Any]) -> None:
        exact_types = {
            "schema": int,
            "revision": int,
            "controller_status": str,
            "apply_enabled": bool,
            "apply_blockers": list,
            "generations": dict,
        }
        for name, expected in exact_types.items():
            if type(payload.get(name)) is not expected:
                raise RollingStateError(f"{name} has an invalid type")
        if payload.get("conflict_error") is not None and not isinstance(
            payload["conflict_error"], str
        ):
            raise RollingStateError("conflict_error has an invalid type")
        for name in ("committed_generation", "committed_release"):
            if payload.get(name) is not None and not isinstance(payload[name], str):
                raise RollingStateError(f"{name} has an invalid type")
        if not all(isinstance(value, str) for value in payload["apply_blockers"]):
            raise RollingStateError("apply blockers must be strings")
        generation_objects = cast(dict[str, object], payload["generations"])
        for _key, value_object in generation_objects.items():
            if not isinstance(value_object, dict):
                raise RollingStateError("generation map has invalid entries")
            value = cast(dict[str, object], value_object)
            string_fields = {
                "generation_id",
                "release_id",
                "control_socket",
                "unit_name",
                "role",
                "phase",
                "verification_level",
            }
            if not all(isinstance(value.get(field), str) for field in string_fields):
                raise RollingStateError("generation record string field is invalid")
            if type(value.get("ready")) is not bool or type(value.get("accepting")) is not bool:
                raise RollingStateError("generation readiness field is invalid")
            pid = value.get("pid")
            if type(pid) is not int or pid < 0:
                raise RollingStateError("generation pid is invalid")
            if value.get("last_error") is not None and not isinstance(value["last_error"], str):
                raise RollingStateError("generation last_error is invalid")
