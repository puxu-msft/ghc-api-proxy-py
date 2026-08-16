from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from app.core.generation_identity import GenerationIdentityError, parse_generation_id
from app.core.release_identity import ReleaseIdentityError, parse_release_id
from app.wire_json import loads


class TokenizationSnapshotError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SnapshotRef:
    generation: str
    release: str
    revision: int
    sha256: str
    path: str


@dataclass(frozen=True, slots=True)
class SnapshotReceipt:
    changed: bool
    reference: SnapshotRef
    canonical_updated: bool = False
    reason: str = "local_snapshot"


class TokenizationSnapshotStore:
    def __init__(
        self,
        root: Path,
        *,
        canonical_path: Path | None = None,
    ) -> None:
        self._root = root
        self._objects = root / "objects" / "sha256"
        self._heads = root / "generations"
        self._canonical = canonical_path

    def publish_local(
        self,
        *,
        generation: str,
        release: str,
        revision: int,
        payload: dict[str, Any],
    ) -> SnapshotReceipt:
        envelope = {
            "schema": 1,
            "generation": generation,
            "release": release,
            "revision": revision,
            "payload": payload,
        }
        data = self._canonical_json(envelope)
        digest = hashlib.sha256(data).hexdigest()
        object_path = self._objects / f"{digest}.json"
        changed = self._atomic_create(object_path, data)
        reference = SnapshotRef(
            generation=generation,
            release=release,
            revision=revision,
            sha256=digest,
            path=str(object_path),
        )
        self._verify_reference(reference)
        self._publish_live_head(reference)
        return SnapshotReceipt(changed=changed, reference=reference)

    def publish_canonical(
        self,
        reference: SnapshotRef,
        *,
        committed_generation: str,
        expected_previous_hash: str | None,
    ) -> SnapshotReceipt:
        if self._canonical is None:
            raise TokenizationSnapshotError("canonical publishing is not available in this process")
        if reference.generation != committed_generation:
            return SnapshotReceipt(
                changed=False,
                reference=reference,
                reason="losing_generation",
            )
        with self._lock(self._canonical.with_name(self._canonical.name + ".lock")):
            previous = self.load_canonical()
            previous_hash = previous.sha256 if previous is not None else None
            if previous_hash != expected_previous_hash:
                raise TokenizationSnapshotError("canonical compare-and-swap mismatch")
            self._verify_reference(reference)
            ref_payload = asdict(reference)
            ref_bytes = self._canonical_json(ref_payload)
            pointer = {
                "schema": 1,
                "reference": ref_payload,
                "checksum": hashlib.sha256(ref_bytes).hexdigest(),
            }
            self._atomic_replace(self._canonical, self._canonical_json(pointer))
        return SnapshotReceipt(
            changed=previous_hash != reference.sha256,
            reference=reference,
            canonical_updated=True,
            reason="canonical_updated",
        )

    def load_canonical(self) -> SnapshotRef | None:
        if self._canonical is None:
            raise TokenizationSnapshotError("canonical pointer is not available")
        try:
            raw = self._canonical.read_bytes()
        except FileNotFoundError:
            return None
        value = loads(raw)
        if not isinstance(value, dict):
            raise TokenizationSnapshotError("canonical pointer must be an object")
        values = cast(dict[str, object], value)
        if values.get("schema") != 1 or not isinstance(values.get("reference"), dict):
            raise TokenizationSnapshotError("canonical pointer schema is invalid")
        reference_values = cast(dict[str, object], values["reference"])
        checksum = values.get("checksum")
        if not isinstance(checksum, str) or hashlib.sha256(
            self._canonical_json(reference_values)
        ).hexdigest() != checksum:
            raise TokenizationSnapshotError("canonical pointer checksum mismatch")
        reference = self._parse_reference(reference_values)
        self._verify_reference(reference)
        return reference

    def load_payload(self, reference: SnapshotRef) -> dict[str, Any]:
        self._verify_reference(reference)
        envelope = self._load_envelope(reference)
        return cast(dict[str, Any], envelope["payload"])

    def load_payload_bytes(self, reference: SnapshotRef) -> bytes:
        payload = self.load_payload(reference).copy()
        payload["revision"] = reference.revision
        return self._canonical_json(payload)

    def _verify_reference(self, reference: SnapshotRef) -> None:
        path = Path(reference.path)
        expected = self._objects / f"{reference.sha256}.json"
        if path != expected:
            raise TokenizationSnapshotError("snapshot path does not match content address")
        try:
            data = path.read_bytes()
        except FileNotFoundError as error:
            raise TokenizationSnapshotError(f"snapshot object is missing: {path}") from error
        if hashlib.sha256(data).hexdigest() != reference.sha256:
            raise TokenizationSnapshotError("snapshot object hash mismatch")
        envelope = self._parse_envelope(data)
        if (
            envelope["generation"] != reference.generation
            or envelope["release"] != reference.release
            or envelope["revision"] != reference.revision
        ):
            raise TokenizationSnapshotError("snapshot reference does not match envelope")

    @staticmethod
    def _atomic_create(path: Path, data: bytes) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(0o600)
            try:
                os.link(temporary, path)
                changed = True
            except FileExistsError:
                changed = False
            TokenizationSnapshotStore._fsync_directory(path.parent)
            return changed
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _atomic_replace(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(0o600)
            temporary.replace(path)
            TokenizationSnapshotStore._fsync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _publish_live_head(self, reference: SnapshotRef) -> None:
        path = self._heads / reference.generation / "live-head.json"
        with self._lock(path.with_name(path.name + ".lock")):
            previous: SnapshotRef | None = None
            try:
                value = loads(path.read_bytes())
                if not isinstance(value, dict):
                    raise TokenizationSnapshotError("live-head must be an object")
                previous = self._parse_reference(cast(dict[str, object], value))
            except FileNotFoundError:
                pass
            if previous is not None:
                if previous.revision > reference.revision:
                    raise TokenizationSnapshotError("live-head revision cannot move backwards")
                if (
                    previous.revision == reference.revision
                    and previous.sha256 != reference.sha256
                ):
                    raise TokenizationSnapshotError("live-head revision has conflicting content")
            self._atomic_replace(path, self._canonical_json(asdict(reference)))

    def _load_envelope(self, reference: SnapshotRef) -> dict[str, object]:
        self._verify_reference(reference)
        return self._parse_envelope(Path(reference.path).read_bytes())

    @staticmethod
    def _parse_reference(values: dict[str, object]) -> SnapshotRef:
        for name in ("generation", "release", "sha256", "path"):
            if not isinstance(values.get(name), str):
                raise TokenizationSnapshotError(f"reference {name} must be a string")
        revision = values.get("revision")
        if type(revision) is not int or revision < 0:
            raise TokenizationSnapshotError("reference revision is invalid")
        return SnapshotRef(
            generation=cast(str, values["generation"]),
            release=cast(str, values["release"]),
            revision=revision,
            sha256=cast(str, values["sha256"]),
            path=cast(str, values["path"]),
        )

    @staticmethod
    def _parse_envelope(data: bytes) -> dict[str, object]:
        value = loads(data)
        if not isinstance(value, dict):
            raise TokenizationSnapshotError("snapshot envelope must be an object")
        envelope = cast(dict[str, object], value)
        if set(envelope) != {"schema", "generation", "release", "revision", "payload"}:
            raise TokenizationSnapshotError("snapshot envelope schema is invalid")
        if envelope["schema"] != 1:
            raise TokenizationSnapshotError("snapshot envelope version is invalid")
        generation = envelope["generation"]
        release = envelope["release"]
        if not isinstance(generation, str) or not isinstance(release, str):
            raise TokenizationSnapshotError("snapshot identity is invalid")
        try:
            parse_generation_id(generation)
            parse_release_id(release)
        except (GenerationIdentityError, ReleaseIdentityError) as error:
            raise TokenizationSnapshotError(str(error)) from error
        revision = envelope["revision"]
        if type(revision) is not int or revision < 0:
            raise TokenizationSnapshotError("snapshot revision is invalid")
        if not isinstance(envelope["payload"], dict):
            raise TokenizationSnapshotError("snapshot payload is invalid")
        return envelope

    @staticmethod
    def _canonical_json(value: object) -> bytes:
        try:
            return json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise TokenizationSnapshotError(f"snapshot is not canonical JSON: {error}") from error

    @staticmethod
    def _lock(path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)

        class Lock:
            def __enter__(self) -> None:
                fcntl.flock(descriptor, fcntl.LOCK_EX)

            def __exit__(self, *_args: object) -> None:
                os.close(descriptor)

        return Lock()
