"""Cold History payload segments and their immutable references."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cbor2
import zstandard

HISTORY_ARCHIVE_SCHEMA_VERSION = 1
HISTORY_SEGMENT_SUFFIX = ".history.cborseq.zst"
HISTORY_TRANSPORT_MEDIA_TYPE = "application/cbor-seq+zstd"


@dataclass(frozen=True, slots=True)
class HistoryArchiveReference:
    relative_path: str
    offset: int
    length: int
    digest: str
    entry_id: str


@dataclass(slots=True)
class _Segment:
    number: int
    path: Path
    size: int


class HistoryArchiveStore:
    """Append immutable History envelopes to indexed compressed segments.

    The interface is deliberately small: append one already-frozen projection
    and read one reference. SQLite/index ownership and asynchronous request
    handoff belong above this adapter.
    """

    def __init__(
        self,
        root: Path,
        *,
        max_segment_bytes: int = 1024 * 1024 * 1024,
        compression_level: int = 3,
    ) -> None:
        if max_segment_bytes <= 0:
            raise ValueError("max_segment_bytes must be positive")
        if not 1 <= compression_level <= 22:
            raise ValueError("compression_level must be between 1 and 22")
        self.root = root
        self.max_segment_bytes = max_segment_bytes
        self.compression_level = compression_level
        self._lock = threading.Lock()
        self._segments: dict[tuple[str, str], _Segment] = {}

    def append(
        self,
        *,
        session_id: str | None,
        agent_id: str | None,
        entry_id: str,
        payload: Mapping[str, object],
        transport: bytes | None = None,
    ) -> HistoryArchiveReference:
        if not entry_id.strip():
            raise ValueError("entry_id must be a non-empty string")
        record: dict[str, object] = {
            "schema_version": HISTORY_ARCHIVE_SCHEMA_VERSION,
            "entry_id": entry_id,
            "session_id": session_id,
            "agent_id": agent_id,
            "payload": dict(payload),
        }
        if transport is not None:
            record["transport"] = transport
            record["transport_media_type"] = HISTORY_TRANSPORT_MEDIA_TYPE
            record["transport_contains_credentials"] = True
        encoded = cbor2.dumps(record, canonical=True)
        frame = zstandard.ZstdCompressor(level=self.compression_level).compress(encoded)
        key = (_identity_key(session_id), _identity_key(agent_id))
        with self._lock:
            segment = self._segment_for(key, len(frame))
            segment.path.parent.mkdir(parents=True, exist_ok=True)
            offset = segment.size
            with segment.path.open("ab", buffering=0) as stream:
                written = stream.write(frame)
                if written != len(frame):
                    raise OSError("short History archive segment write")
            segment.size += len(frame)
            relative = segment.path.relative_to(self.root).as_posix()
        return HistoryArchiveReference(
            relative_path=relative,
            offset=offset,
            length=len(frame),
            digest=hashlib.sha256(frame).hexdigest(),
            entry_id=entry_id,
        )

    def read(self, reference: HistoryArchiveReference) -> dict[str, Any]:
        path = self.root / reference.relative_path
        with path.open("rb") as stream:
            stream.seek(reference.offset)
            frame = stream.read(reference.length)
        if len(frame) != reference.length:
            raise ValueError("History archive reference points past segment end")
        if hashlib.sha256(frame).hexdigest() != reference.digest:
            raise ValueError("History archive frame digest mismatch")
        record = _decode_history_frame(frame)
        if record.get("schema_version") != HISTORY_ARCHIVE_SCHEMA_VERSION:
            raise ValueError("unsupported History archive schema version")
        if record.get("entry_id") != reference.entry_id:
            raise ValueError("History archive reference entry id mismatch")
        return record

    def read_transport(self, reference: HistoryArchiveReference) -> bytes | None:
        record = self.read(reference)
        transport = record.get("transport")
        if transport is None:
            return None
        if not isinstance(transport, bytes):
            raise ValueError("History archive transport is not a byte string")
        if record.get("transport_media_type") != HISTORY_TRANSPORT_MEDIA_TYPE:
            raise ValueError("unsupported History archive transport media type")
        if record.get("transport_contains_credentials") is not True:
            raise ValueError("History archive transport credential marker is invalid")
        return transport

    def iter_records(self, relative_path: str) -> Iterator[dict[str, Any]]:
        path = self.root / relative_path
        with path.open("rb") as stream:
            while True:
                frame = _read_zstd_frame(stream)
                if frame is None:
                    return
                yield _decode_history_frame(frame)

    def _segment_for(self, key: tuple[str, str], frame_length: int) -> _Segment:
        current = self._segments.get(key)
        if current is None:
            current = self._restore_current_segment(key)
            if current is not None:
                self._segments[key] = current
        if current is not None and (
            current.size == 0
            or current.size + frame_length <= self.max_segment_bytes
        ):
            return current
        number = 0 if current is None else current.number + 1
        path = (
            self.root
            / f"session-{key[0]}"
            / f"agent-{key[1]}"
            / f"history-{number:06d}{HISTORY_SEGMENT_SUFFIX}"
        )
        segment = _Segment(number=number, path=path, size=0)
        self._segments[key] = segment
        return segment

    def _restore_current_segment(self, key: tuple[str, str]) -> _Segment | None:
        directory = self.root / f"session-{key[0]}" / f"agent-{key[1]}"
        if not directory.exists():
            return None

        segments: list[_Segment] = []
        for path in directory.iterdir():
            number = _segment_number(path)
            if number is None:
                continue
            segments.append(
                _Segment(
                    number=number,
                    path=path,
                    size=_validated_segment_size(path),
                )
            )
        if not segments:
            return None
        return max(segments, key=lambda segment: segment.number)


def _identity_key(value: str | None) -> str:
    raw = value if value is not None else "<missing>"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _segment_number(path: Path) -> int | None:
    prefix = "history-"
    name = path.name
    if not path.is_file() or not name.startswith(prefix) or not name.endswith(HISTORY_SEGMENT_SUFFIX):
        return None
    number_text = name[len(prefix) : -len(HISTORY_SEGMENT_SUFFIX)]
    if len(number_text) != 6 or not number_text.isdecimal():
        return None
    return int(number_text)


def _validated_segment_size(path: Path) -> int:
    try:
        with path.open("rb") as stream:
            while True:
                frame = _read_zstd_frame(stream)
                if frame is None:
                    return stream.tell()
                _decode_history_frame(frame)
    except ValueError as error:
        raise ValueError(f"History archive segment is not safe to append: {path}") from error


def _decode_history_frame(frame: bytes) -> dict[str, Any]:
    try:
        decoded = zstandard.ZstdDecompressor().decompress(frame)
        value = cbor2.loads(decoded)
    except (cbor2.CBORDecodeError, zstandard.ZstdError) as error:
        raise ValueError("History archive frame is unreadable") from error
    if not isinstance(value, dict):
        raise ValueError("History archive frame is not a map")
    return cast(dict[str, Any], value)


def _read_zstd_frame(stream: Any) -> bytes | None:
    prefix = stream.read(4)
    if not prefix:
        return None
    if len(prefix) != 4:
        raise ValueError("History archive ends with a truncated frame")
    remaining = bytearray(prefix)
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            raise ValueError("History archive ends with a truncated frame")
        remaining.extend(chunk)
        decompressor = zstandard.ZstdDecompressor().decompressobj()
        decompressor.decompress(bytes(remaining))
        if decompressor.eof:
            unused = decompressor.unused_data
            frame_length = len(remaining) - len(unused)
            frame = bytes(remaining[:frame_length])
            if unused:
                stream.seek(-len(unused), 1)
            return frame


__all__ = [
    "HISTORY_ARCHIVE_SCHEMA_VERSION",
    "HISTORY_SEGMENT_SUFFIX",
    "HISTORY_TRANSPORT_MEDIA_TYPE",
    "HistoryArchiveReference",
    "HistoryArchiveStore",
]
