"""Opt-in raw request and response capture for forensic replay."""

from __future__ import annotations

import base64
import hashlib
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from queue import Full, Queue
from threading import Lock, Thread
from typing import Any

import orjson
import zstandard

logger = logging.getLogger(__name__)

AGENT_ID_HEADERS = ("x-claude-code-agent-id", "x-agent-id")


def agent_id_from_headers(headers: Mapping[str, str]) -> str | None:
    lowered = {name.lower(): value.strip() for name, value in headers.items()}
    for name in AGENT_ID_HEADERS:
        value = lowered.get(name, "")
        if value:
            return value
    return None


class RawCaptureStore:
    """Append length-independent zstd frames grouped by session and agent."""

    def __init__(
        self,
        root: Path,
        *,
        compression_level: int = 3,
        max_file_bytes: int = 512 * 1024 * 1024,
        max_total_bytes: int = 4 * 1024 * 1024 * 1024,
    ) -> None:
        self.root = root
        self.compression_level = compression_level
        self._lock = Lock()
        self._queue: Queue[tuple[Path, bytes] | None] = Queue(maxsize=1024)
        self._reserved_file_bytes: dict[Path, int] = {}
        self._reserved_total_bytes = sum(
            path.stat().st_size for path in root.rglob("*.jsonl.zst") if path.is_file()
        ) if root.is_dir() else 0
        self._max_file_bytes = max_file_bytes
        self._max_total_bytes = max_total_bytes
        self._closed = False
        self._worker = Thread(target=self._write_loop, name="raw-capture-writer", daemon=True)
        self._worker.start()

    def start(
        self,
        *,
        session_id: str,
        agent_id: str,
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

    def _path_for(self, session_id: str, agent_id: str) -> Path:
        session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
        agent_key = hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:24]
        return self.root / f"session-{session_key}" / f"agent-{agent_key}.jsonl.zst"

    def append(self, capture: RawRequestCapture, event: dict[str, Any]) -> bool:
        record = {
            "schema_version": 1,
            "at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "request_id": capture.request_id,
            "session_id": capture.session_id,
            "agent_id": capture.agent_id,
            **event,
        }
        try:
            serialized = orjson.dumps(record) + b"\n"
            path = self._path_for(capture.session_id, capture.agent_id)
            with self._lock:
                if self._closed:
                    return False
                current_file_bytes = self._reserved_file_bytes.get(
                    path,
                    path.stat().st_size if path.is_file() else 0,
                )
                if (
                    self._max_file_bytes > 0
                    and current_file_bytes + len(serialized) > self._max_file_bytes
                ):
                    logger.warning("raw request capture file quota exceeded: %s", path)
                    return False
                if (
                    self._max_total_bytes > 0
                    and self._reserved_total_bytes + len(serialized) > self._max_total_bytes
                ):
                    logger.warning("raw request capture total quota exceeded: %s", self.root)
                    return False
                try:
                    self._queue.put_nowait((path, serialized))
                except Full:
                    logger.warning("raw request capture writer queue is full: %s", self.root)
                    return False
                self._reserved_file_bytes[path] = current_file_bytes + len(serialized)
                self._reserved_total_bytes += len(serialized)
        except (OSError, TypeError, zstandard.ZstdError) as error:
            logger.warning("could not keep raw request capture: %s", error)
            return False
        return True

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
                path, serialized = item
                compressed = zstandard.ZstdCompressor(level=self.compression_level).compress(
                    serialized
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("ab") as stream:
                    stream.write(compressed)
            except OSError as error:
                logger.warning("could not keep raw request capture: %s", error)
            finally:
                self._queue.task_done()


class RawRequestCapture:
    """One request's raw body events in a session-agent append stream."""

    def __init__(
        self,
        *,
        store: RawCaptureStore,
        session_id: str,
        agent_id: str,
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
        self._enabled = True
        self._finished = False
        self._request_body_finished = False

    def append_event(self, event: dict[str, Any]) -> None:
        if not self._enabled:
            return
        if not self.store.append(self, event):
            self._enabled = False

    def request_body(self, body: bytes) -> None:
        self.request_body_chunk(body, more_body=False)

    def request_body_chunk(self, body: bytes, *, more_body: bool) -> None:
        self.append_event(
            {
                "event": "request.body",
                "body": _encoded(body),
                "more_body": more_body,
            }
        )

    def request_body_end(self, *, complete: bool) -> None:
        if self._request_body_finished:
            return
        self._request_body_finished = True
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
        self.append_event(
            {
                "event": "upstream.request.body",
                "attempt": attempt,
                "body": _encoded(body),
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
                "body": _encoded(body),
            }
        )

    def upstream_response_end(
        self,
        *,
        complete: bool = True,
        attempt: int | None = None,
    ) -> None:
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
                "body": _encoded(body),
                "more_body": more_body,
            }
        )

    def finish(self, *, status_code: int | None, complete: bool) -> None:
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


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


__all__ = ["RawCaptureStore", "RawRequestCapture"]
