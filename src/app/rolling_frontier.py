from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from app.core.generation_identity import parse_generation_id


class RollingFrontierError(RuntimeError):
    pass


class RollingFrontierStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._copies = (root / "frontier-a.json", root / "frontier-b.json")
        self._facts = root / "allocations.jsonl"
        self._initialized = root / "frontier.initialized"

    def reserve_next(self, *, release_id: str) -> str:
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        sequence = self.high_watermark() + 1
        generation_id = f"g{sequence:016d}"
        fact: dict[str, object] = {
            "sequence": sequence,
            "generation": generation_id,
            "release": release_id,
        }
        self._append_fact(fact)
        if not self._initialized.exists():
            self._write_marker()
        for path in self._copies:
            self._write_copy(path, sequence)
        return generation_id

    def high_watermark(self) -> int:
        if self._initialized.exists() and not self._facts.is_file():
            raise RollingFrontierError("initialized frontier is missing allocation facts")
        values = [value for path in self._copies if (value := self._read_copy(path)) is not None]
        fact_values, facts_corrupt = self._read_facts()
        if facts_corrupt:
            raise RollingFrontierError("allocation facts are corrupt; high watermark is unknown")
        values.extend(fact_values)
        if not values and (self._facts.exists() or any(path.exists() for path in self._copies)):
            raise RollingFrontierError("cannot prove the generation ID high watermark")
        return max(values, default=0)

    def _write_marker(self) -> None:
        descriptor = os.open(
            self._initialized,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, b"initialized\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory_fd = os.open(self._root, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _append_fact(self, fact: dict[str, object]) -> None:
        payload = json.dumps(fact, sort_keys=True, separators=(",", ":"))
        record = json.dumps(
            {"payload": fact, "checksum": hashlib.sha256(payload.encode()).hexdigest()},
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._facts.open("a", encoding="utf-8") as output:
            output.write(record + "\n")
            output.flush()
            os.fsync(output.fileno())

    def _read_facts(self) -> tuple[list[int], bool]:
        if not self._facts.is_file():
            return [], False
        values: list[int] = []
        for line in self._facts.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                fact = record["payload"]
                payload = json.dumps(fact, sort_keys=True, separators=(",", ":"))
                if hashlib.sha256(payload.encode()).hexdigest() != record["checksum"]:
                    return values, True
                generation = str(fact["generation"])
                sequence = int(fact["sequence"])
                if parse_generation_id(generation) != sequence:
                    return values, True
                values.append(sequence)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return values, True
        return values, False

    def _write_copy(self, path: Path, sequence: int) -> None:
        payload = {"schema": 1, "high_watermark": sequence}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        content = json.dumps(
            {"payload": payload, "checksum": hashlib.sha256(canonical.encode()).hexdigest()},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=self._root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(path)
            directory_fd = os.open(self._root, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _read_copy(path: Path) -> int | None:
        if not path.is_file():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            payload = record["payload"]
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256(canonical.encode()).hexdigest() != record["checksum"]:
                return None
            if payload["schema"] != 1:
                return None
            value = int(payload["high_watermark"])
            return value if value >= 0 else None
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
