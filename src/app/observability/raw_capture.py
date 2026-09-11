"""Opt-in CBOR Sequence request and response capture for forensic replay."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Generator, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from queue import Full, Queue
from threading import Condition, Lock, Thread
from typing import Any, cast

import cbor2
import httpx2
import zstandard

logger = logging.getLogger(__name__)

AGENT_ID_HEADERS = ("x-claude-code-agent-id", "x-agent-id")
CAPTURE_FILE_SUFFIX = ".cborseq.zst"
CAPTURE_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class _UpstreamCaptureScope:
    capture: RawRequestCapture | None
    attempt: int


_pending_upstream_capture: ContextVar[_UpstreamCaptureScope | None] = ContextVar(
    "pending_upstream_capture",
    default=None,
)
_active_upstream_capture: ContextVar[_UpstreamCaptureScope | None] = ContextVar(
    "active_upstream_capture",
    default=None,
)


@contextmanager
def pending_upstream_capture(
    capture: RawRequestCapture | None,
    attempt: int,
) -> Generator[None]:
    """Make one driver attempt available to its provider transport boundary."""
    token = _pending_upstream_capture.set(
        _UpstreamCaptureScope(capture=capture, attempt=attempt)
    )
    try:
        yield
    finally:
        _pending_upstream_capture.reset(token)


@contextmanager
def activate_pending_upstream_capture() -> Generator[None]:
    """Allow a prepared inference send to observe its pending capture scope."""
    token = _active_upstream_capture.set(_pending_upstream_capture.get())
    try:
        yield
    finally:
        _active_upstream_capture.reset(token)


def observe_active_upstream_request(request: httpx2.Request) -> None:
    """Record request bytes at an active inference transport boundary only."""
    scope = _active_upstream_capture.get()
    if scope is None or scope.capture is None:
        return
    try:
        scope.capture.upstream_request_body(request.content, attempt=scope.attempt)
    except BaseException:
        return


async def observe_active_upstream_request_hook(request: httpx2.Request) -> None:
    observe_active_upstream_request(request)


@dataclass(frozen=True, slots=True)
class _QueuedCaptureFrame:
    path: Path
    compressed: bytes
    capture: RawRequestCapture
    event_type: str
    reserved_bytes: int


def agent_id_from_headers(headers: Mapping[str, str]) -> str | None:
    lowered = {name.lower(): value.strip() for name, value in headers.items()}
    for name in AGENT_ID_HEADERS:
        value = lowered.get(name, "")
        if value:
            return value
    return None


class RawCaptureStore:
    """Append independently compressed CBOR items grouped by session and agent."""

    def __init__(
        self,
        root: Path,
        *,
        compression_level: int = 3,
        max_file_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        self.root = root
        self.compression_level = compression_level
        self._lock = Lock()
        self._queue: Queue[_QueuedCaptureFrame | None] = Queue(maxsize=1024)
        self._reserved_file_bytes: dict[Path, int] = {}
        self._poisoned_paths: set[Path] = set()
        self._validated_paths: set[Path] = set()
        self._max_file_bytes = max_file_bytes
        self._closed = False
        self._worker = Thread(target=self._write_loop, name="raw-capture-writer", daemon=True)
        self._worker.start()

    def start(
        self,
        *,
        session_id: str,
        agent_id: str | None,
        request_id: str,
        method: str,
        path: str,
    ) -> RawRequestCapture:
        capture = RawRequestCapture(
            store=self,
            session_id=session_id,
            agent_id=agent_id,
            request_id=request_id,
            method=method,
            path=path,
        )
        capture.append_event(
            {
                "event": "request.start",
                "method": method,
                "path": path,
            }
        )
        return capture

    def _path_for(self, session_id: str, agent_id: str | None) -> Path:
        session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
        if agent_id is None:
            agent_key = f"missing-{hashlib.sha256(b'missing-agent-id').hexdigest()[:24]}"
        else:
            agent_key = hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:24]
        return self.root / f"session-{session_key}" / f"agent-{agent_key}{CAPTURE_FILE_SUFFIX}"

    def append(
        self,
        capture: RawRequestCapture,
        event: dict[str, Any],
    ) -> tuple[bool, str | None]:
        event_type = str(event.get("event", "unknown"))
        record = {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "request_id": capture.request_id,
            "session_id": capture.session_id,
            "agent_id": capture.agent_id,
            **event,
        }
        try:
            serialized = cbor2.dumps(record, canonical=True)
            compressed = zstandard.ZstdCompressor(level=self.compression_level).compress(
                serialized
            )
            path = self._path_for(capture.session_id, capture.agent_id)
            queued = _QueuedCaptureFrame(
                path=path,
                compressed=compressed,
                capture=capture,
                event_type=event_type,
                reserved_bytes=len(compressed),
            )
            with self._lock:
                if self._closed:
                    return False, "store_closed"
                self._validate_existing_path(path)
                if path in self._poisoned_paths:
                    return False, "path_poisoned"
                current_file_bytes = self._reserved_file_bytes.get(
                    path,
                    path.stat().st_size if path.is_file() else 0,
                )
                if (
                    self._max_file_bytes > 0
                    and current_file_bytes + queued.reserved_bytes > self._max_file_bytes
                ):
                    self._log_prepare_warning(
                        capture,
                        event_type,
                        "file_quota_exceeded",
                    )
                    return False, "file_quota_exceeded"
                try:
                    self._queue.put_nowait(queued)
                except Full as error:
                    self._log_prepare_warning(
                        capture,
                        event_type,
                        "writer_queue_full",
                        error=error,
                    )
                    return False, "writer_queue_full"
                self._reserved_file_bytes[path] = current_file_bytes + queued.reserved_bytes
                capture.note_writer_frame_queued()
        except (cbor2.CBOREncodeError, OSError, TypeError, zstandard.ZstdError) as error:
            self._log_prepare_warning(
                capture,
                event_type,
                "capture_error",
                error=error,
            )
            return False, "capture_error"
        return True, None

    @staticmethod
    def _log_prepare_warning(
        capture: RawRequestCapture,
        event_type: str,
        reason: str,
        *,
        error: BaseException | None = None,
    ) -> None:
        logger.warning(
            "could not keep raw request capture frame: "
            "request_id=%s event=%s reason=%s exception_type=%s errno=%s",
            capture.request_id,
            event_type,
            reason,
            type(error).__qualname__ if error is not None else None,
            getattr(error, "errno", None) if error is not None else None,
        )

    def _validate_existing_path(self, path: Path) -> None:
        if path in self._validated_paths:
            return
        self._validated_paths.add(path)
        if not path.is_file():
            return
        try:
            for _record in iter_raw_capture_records(path):
                pass
        except (
            OSError,
            ValueError,
            cbor2.CBORDecodeError,
            zstandard.ZstdError,
        ):
            self._poisoned_paths.add(path)

    def flush(self) -> None:
        self._queue.join()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.flush()
        self._queue.put(None)
        self._worker.join()

    def _write_loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                if self._path_is_poisoned(item.path):
                    self._complete_write(
                        item,
                        persisted_bytes=0,
                        drop_reason="path_poisoned",
                    )
                    continue
                if item.capture.has_writer_failure():
                    self._complete_write(
                        item,
                        persisted_bytes=0,
                        drop_reason="writer_error",
                    )
                    continue

                persisted_bytes = 0
                writer_error: OSError | None = None
                try:
                    item.path.parent.mkdir(parents=True, exist_ok=True)
                    with item.path.open("ab", buffering=0) as stream:
                        written = stream.write(item.compressed)
                        persisted_bytes = 0 if written is None else written
                        if persisted_bytes != len(item.compressed):
                            raise OSError("short raw capture frame write")
                except OSError as error:
                    writer_error = error

                if writer_error is not None:
                    logger.warning(
                        "could not keep raw request capture frame: "
                        "request_id=%s event=%s reason=writer_error "
                        "exception_type=%s errno=%s",
                        item.capture.request_id,
                        item.event_type,
                        type(writer_error).__qualname__,
                        writer_error.errno,
                    )
                self._complete_write(
                    item,
                    persisted_bytes=persisted_bytes,
                    drop_reason=(
                        "writer_error" if writer_error is not None else None
                    ),
                    poison_path=(
                        0 < persisted_bytes < item.reserved_bytes
                    ),
                )
            finally:
                self._queue.task_done()

    def _path_is_poisoned(self, path: Path) -> bool:
        with self._lock:
            return path in self._poisoned_paths

    def _complete_write(
        self,
        item: _QueuedCaptureFrame,
        *,
        persisted_bytes: int,
        drop_reason: str | None,
        poison_path: bool = False,
    ) -> None:
        with self._lock:
            if poison_path:
                self._poisoned_paths.add(item.path)
            released_bytes = item.reserved_bytes - persisted_bytes
            if released_bytes:
                remaining_file_bytes = (
                    self._reserved_file_bytes[item.path] - released_bytes
                )
                if remaining_file_bytes:
                    self._reserved_file_bytes[item.path] = remaining_file_bytes
                else:
                    del self._reserved_file_bytes[item.path]
            item.capture.note_writer_frame_completed(
                item.event_type,
                drop_reason=drop_reason,
            )


class RawRequestCapture:
    """One request's raw body events in a session-agent append stream."""

    def __init__(
        self,
        *,
        store: RawCaptureStore,
        session_id: str,
        agent_id: str | None,
        request_id: str,
        method: str,
        path: str,
    ) -> None:
        self.store = store
        self.session_id = session_id
        self.agent_id = agent_id
        self.request_id = request_id
        self.method = method
        self.path = path
        self._condition = Condition()
        self._pending_writes = 0
        self._enabled = True
        self._finished = False
        self._request_body_finished = False
        self._drop_reason: str | None = None
        self._first_dropped_event: str | None = None
        self._writer_error_event: str | None = None
        self._missing_event_types: set[str] = set()
        self._committed_event_types: set[str] = set()
        self._upstream_request_body_attempts: set[int | None] = set()
        self._incomplete_reason: str | None = None
        self._first_incomplete_event: str | None = None

    def append_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("event", "unknown"))
        with self._condition:
            if not self._enabled:
                self._missing_event_types.add(event_type)
                return
        stored, drop_reason = self.store.append(self, event)
        if not stored:
            self._mark_drop(drop_reason or "unknown", event_type)

    def note_writer_frame_queued(self) -> None:
        with self._condition:
            self._pending_writes += 1

    def note_writer_frame_completed(
        self,
        event_type: str,
        *,
        drop_reason: str | None,
    ) -> None:
        with self._condition:
            if drop_reason is not None:
                self._mark_drop_locked(drop_reason, event_type)
            else:
                self._committed_event_types.add(event_type)
            self._pending_writes -= 1
            self._condition.notify_all()

    def has_writer_failure(self) -> bool:
        with self._condition:
            return self._writer_error_event is not None

    def _mark_drop(self, reason: str, event_type: str) -> None:
        with self._condition:
            self._mark_drop_locked(reason, event_type)

    def _mark_drop_locked(self, reason: str, event_type: str) -> None:
        self._enabled = False
        if reason == "writer_error" and self._writer_error_event is None:
            self._writer_error_event = event_type
        if self._drop_reason is None:
            self._drop_reason = reason
            self._first_dropped_event = event_type
        self._missing_event_types.add(event_type)

    def _note_incomplete(self, event_type: str) -> None:
        with self._condition:
            if self._incomplete_reason is None:
                self._incomplete_reason = "upstream_incomplete"
                self._first_incomplete_event = event_type

    def _wait_for_writes(self) -> None:
        with self._condition:
            self._condition.wait_for(lambda: self._pending_writes == 0)

    def request_body(self, body: bytes) -> None:
        self.request_body_chunk(body, more_body=False)

    def request_body_chunk(self, body: bytes, *, more_body: bool) -> None:
        self.append_event(
            {
                "event": "request.body",
                "body": body,
                "more_body": more_body,
            }
        )

    def request_body_end(self, *, complete: bool) -> None:
        if self._request_body_finished:
            return
        self._request_body_finished = True
        if not complete:
            self._note_incomplete("request.body.end")
        self.append_event({"event": "request.body.end", "complete": complete})

    def upstream_attempt_start(self, attempt: int) -> None:
        self.append_event({"event": "upstream.attempt.start", "attempt": attempt})

    def upstream_attempt_end(self, attempt: int, *, complete: bool) -> None:
        self.append_event(
            {
                "event": "upstream.attempt.end",
                "attempt": attempt,
                "complete": complete,
            }
        )

    def upstream_request_body(self, body: bytes, *, attempt: int | None = None) -> None:
        with self._condition:
            if attempt in self._upstream_request_body_attempts:
                return
            self._upstream_request_body_attempts.add(attempt)
        self.append_event(
            {
                "event": "upstream.request.body",
                "attempt": attempt,
                "body": body,
            }
        )

    def upstream_response_start(self, status_code: int, *, attempt: int | None = None) -> None:
        self.append_event(
            {
                "event": "upstream.response.start",
                "attempt": attempt,
                "status_code": status_code,
            }
        )

    def upstream_response_body(self, body: bytes, *, attempt: int | None = None) -> None:
        self.append_event(
            {
                "event": "upstream.response.body",
                "attempt": attempt,
                "body": body,
            }
        )

    def upstream_response_end(
        self,
        *,
        complete: bool = True,
        attempt: int | None = None,
    ) -> None:
        if not complete:
            self._note_incomplete("upstream.response.end")
        self.append_event(
            {
                "event": "upstream.response.end",
                "attempt": attempt,
                "complete": complete,
            }
        )

    def client_response_start(self, status_code: int) -> None:
        self.append_event({"event": "client.response.start", "status_code": status_code})

    def client_response_body(self, body: bytes, *, more_body: bool) -> None:
        self.append_event(
            {
                "event": "client.response.body",
                "body": body,
                "more_body": more_body,
            }
        )

    def finish(self, *, status_code: int | None, complete: bool) -> None:
        with self._condition:
            if self._finished:
                return
            self._finished = True
        self.append_event(
            {
                "event": "request.end",
                "status_code": status_code,
                "complete": complete,
            }
        )
        if not complete:
            self._mark_drop("request_incomplete", "request.end")
        self._wait_for_writes()
        with self._condition:
            drop_reason = self._drop_reason or self._incomplete_reason
            first_dropped_event = (
                self._first_dropped_event or self._first_incomplete_event
            )
            writer_error = self._writer_error_event is not None
            response_body_event_types = {
                "upstream.response.body",
                "client.response.body",
            }
            committed_response_body = bool(
                response_body_event_types & self._committed_event_types
            )
            missing_response_body = bool(
                response_body_event_types & self._missing_event_types
            )
            response_body_incomplete = self._incomplete_reason is not None
            response_body_complete = (
                committed_response_body
                and not missing_response_body
                and not response_body_incomplete
                and complete
            )
        if drop_reason is not None:
            logger.warning(
                "raw request capture incomplete at request completion: "
                "request_id=%s reason=%s first_dropped_event=%s "
                "writer_error=%s response_body_capture_complete=%s "
                "forensic_replay_complete=false",
                self.request_id,
                drop_reason,
                first_dropped_event,
                str(writer_error).lower(),
                str(response_body_complete).lower(),
            )


def iter_raw_capture_records(path: Path) -> Iterator[dict[str, Any]]:
    """Decode complete maps from a zstd-compressed RFC 8742 CBOR Sequence."""

    with path.open("rb") as stream:
        pending = b""
        while True:
            decompressor = zstandard.ZstdDecompressor().decompressobj()
            decoded = bytearray()
            saw_frame_bytes = False
            while not decompressor.eof:
                chunk = pending or stream.read(64 * 1024)
                pending = b""
                if not chunk:
                    if saw_frame_bytes:
                        raise ValueError("raw capture ends with an incomplete zstd frame")
                    return
                saw_frame_bytes = True
                decoded.extend(decompressor.decompress(chunk))
                pending = decompressor.unused_data

            item = BytesIO(decoded)
            record: object = cbor2.CBORDecoder(item).decode()
            if item.read(1):
                raise ValueError("raw capture zstd frame must contain exactly one CBOR item")
            if not isinstance(record, dict):
                raise ValueError("raw capture CBOR Sequence item must be a map")
            yield cast(dict[str, Any], record)


__all__ = ["RawCaptureStore", "RawRequestCapture", "iter_raw_capture_records"]
