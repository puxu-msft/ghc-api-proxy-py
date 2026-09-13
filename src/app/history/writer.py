"""Bounded asynchronous History projection writer."""

from __future__ import annotations

import asyncio
import base64
import logging
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

from app.history.archive import HistoryArchiveReference, HistoryArchiveStore
from app.history.entry import HistoryEntry

logger = logging.getLogger(__name__)


class HistoryDurability(StrEnum):
    DURABLE = "durable"
    PERSISTENCE_FAILED = "persistence_failed"


class HistorySubmission(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class HistoryMutation(StrEnum):
    UPDATED = "updated"
    ALREADY_APPLIED = "already_applied"
    NOT_FOUND = "not_found"
    PINNED = "pinned"
    ARCHIVING = "archiving"
    ARCHIVE_FAILED = "archive_failed"


class HistoryArchiveState(StrEnum):
    ACTIVE = "active"
    ARCHIVING = "archiving"
    ARCHIVED = "archived"
    ARCHIVE_FAILED = "archive_failed"


class HistoryTransportSource(Protocol):
    def export_request(self, relative_path: str, request_id: str) -> bytes:
        """Return the filtered binary transport export for one request."""
        ...


@dataclass(frozen=True, slots=True)
class HistoryPage:
    entries: tuple[HistoryIndexEntry, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class HistoryDurabilityReceipt:
    entry_id: str
    state: HistoryDurability
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class HistoryIndexEntry:
    entry_id: str
    session_id: str | None
    agent_id: str | None
    started_at: str
    finished_at: str
    outcome: str
    delivery: str
    capture_status: str
    capture_ref: str | None
    archive_reference: HistoryArchiveReference
    transport_reference: HistoryArchiveReference | None
    archive_state: HistoryArchiveState
    archive_error_code: str | None
    pinned: bool
    archived: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.entry_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outcome": self.outcome,
            "delivery": self.delivery,
            "capture_status": self.capture_status,
            "capture_ref": self.capture_ref,
            "archive": {
                "path": self.archive_reference.relative_path,
                "offset": self.archive_reference.offset,
                "length": self.archive_reference.length,
                "digest": self.archive_reference.digest,
            },
            "transport": (
                {
                    "path": self.transport_reference.relative_path,
                    "offset": self.transport_reference.offset,
                    "length": self.transport_reference.length,
                    "digest": self.transport_reference.digest,
                    "media_type": "application/cbor-seq+zstd",
                    "contains_credentials": True,
                }
                if self.transport_reference is not None
                else None
            ),
            "archive_state": self.archive_state.value,
            "archive_error_code": self.archive_error_code,
            "pinned": self.pinned,
            "archived": self.archived,
        }


@dataclass(frozen=True, slots=True)
class _HistoryWriteJob:
    entry: HistoryEntry
    session_id: str | None
    agent_id: str | None


class HistoryWriter:
    """Own the asynchronous handoff from immutable HistoryEntry to storage."""

    def __init__(
        self,
        *,
        database_path: Path,
        archive: HistoryArchiveStore,
        transport_source: HistoryTransportSource | None = None,
        queue_size: int = 1000,
    ) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        self.database_path = database_path
        self.archive = archive
        self.transport_source = transport_source
        self._queue: asyncio.Queue[_HistoryWriteJob | None] = asyncio.Queue(
            maxsize=queue_size
        )
        self._archive_queue: asyncio.Queue[str | None] = asyncio.Queue(
            maxsize=queue_size
        )
        self._connection: sqlite3.Connection | None = None
        self._task: asyncio.Task[None] | None = None
        self._archive_task: asyncio.Task[None] | None = None
        self._receipts: dict[str, HistoryDurabilityReceipt] = {}
        self._closed = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._connection = await asyncio.to_thread(self._open_connection)
        self._task = asyncio.create_task(self._run(), name="history-writer")
        self._archive_task = asyncio.create_task(
            self._run_archive(),
            name="history-archive",
        )

    async def submit(
        self,
        entry: HistoryEntry,
        *,
        session_id: str | None,
        agent_id: str | None,
    ) -> HistorySubmission:
        return self.submit_nowait(
            entry,
            session_id=session_id,
            agent_id=agent_id,
        )

    def submit_nowait(
        self,
        entry: HistoryEntry,
        *,
        session_id: str | None,
        agent_id: str | None,
    ) -> HistorySubmission:
        if self._task is None or self._closed:
            return HistorySubmission.REJECTED
        try:
            self._queue.put_nowait(
                _HistoryWriteJob(
                    entry=entry,
                    session_id=session_id,
                    agent_id=agent_id,
                )
            )
        except asyncio.QueueFull:
            return HistorySubmission.REJECTED
        return HistorySubmission.ACCEPTED

    async def wait_idle(self) -> None:
        await self._queue.join()

    async def wait_archive_idle(self) -> None:
        await self._archive_queue.join()

    def receipt_for(self, entry_id: str) -> HistoryDurabilityReceipt | None:
        return self._receipts.get(entry_id)

    async def list_entries(
        self,
        *,
        limit: int = 50,
        include_archived: bool = False,
        session_id: str | None = None,
        agent_id: str | None = None,
        outcome: str | None = None,
        delivery: str | None = None,
        capture_status: str | None = None,
    ) -> tuple[HistoryIndexEntry, ...]:
        page = await self.list_entries_page(
            limit=limit,
            include_archived=include_archived,
            session_id=session_id,
            agent_id=agent_id,
            outcome=outcome,
            delivery=delivery,
            capture_status=capture_status,
        )
        return page.entries

    async def list_entries_page(
        self,
        *,
        limit: int = 50,
        include_archived: bool = False,
        cursor: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        outcome: str | None = None,
        delivery: str | None = None,
        capture_status: str | None = None,
    ) -> HistoryPage:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if self._task is None or self._closed:
            raise RuntimeError("History writer is not running")
        return await asyncio.to_thread(
            self._list_entries_page,
            limit,
            include_archived,
            cursor,
            session_id,
            agent_id,
            outcome,
            delivery,
            capture_status,
        )

    async def get_entry(
        self,
        entry_id: str,
        *,
        include_archived: bool = False,
    ) -> HistoryIndexEntry | None:
        if self._task is None or self._closed:
            raise RuntimeError("History writer is not running")
        return await asyncio.to_thread(
            self._get_entry,
            entry_id,
            include_archived,
        )

    async def semantic_payload_for(
        self,
        entry_id: str,
        *,
        include_archived: bool = False,
    ) -> dict[str, object] | None:
        if self._task is None or self._closed:
            raise RuntimeError("History writer is not running")
        return await asyncio.to_thread(
            self._semantic_payload_for,
            entry_id,
            include_archived,
        )

    async def transport_for(
        self,
        entry_id: str,
        *,
        include_archived: bool = False,
    ) -> bytes | None:
        if self._task is None or self._closed:
            raise RuntimeError("History writer is not running")
        return await asyncio.to_thread(
            self._transport_for,
            entry_id,
            include_archived,
        )

    async def archive_entry(self, entry_id: str) -> HistoryMutation:
        if self._task is None or self._closed:
            raise RuntimeError("History writer is not running")
        mutation = await asyncio.to_thread(self._begin_archive, entry_id)
        if mutation is HistoryMutation.ARCHIVING:
            try:
                self._archive_queue.put_nowait(entry_id)
            except asyncio.QueueFull:
                await asyncio.to_thread(
                    self._mark_archive_failed,
                    entry_id,
                    "archive_queue_full",
                )
                return HistoryMutation.ARCHIVE_FAILED
        return mutation

    async def pin_entry(self, entry_id: str) -> HistoryMutation:
        if self._task is None or self._closed:
            raise RuntimeError("History writer is not running")
        return await asyncio.to_thread(self._set_pinned, entry_id, True)

    async def unpin_entry(self, entry_id: str) -> HistoryMutation:
        if self._task is None or self._closed:
            raise RuntimeError("History writer is not running")
        return await asyncio.to_thread(self._set_pinned, entry_id, False)

    async def close(self) -> None:
        if self._task is None or self._closed:
            return
        self._closed = True
        await self._queue.join()
        await self._queue.put(None)
        await self._task
        await self._archive_queue.join()
        await self._archive_queue.put(None)
        if self._archive_task is not None:
            await self._archive_task
        connection = self._connection
        if connection is not None:
            await asyncio.to_thread(connection.close)
        self._connection = None
        self._task = None
        self._archive_task = None

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job is None:
                    return
                try:
                    receipt = await asyncio.to_thread(self._persist, job)
                except Exception as error:
                    receipt = HistoryDurabilityReceipt(
                        entry_id=job.entry.request_id,
                        state=HistoryDurability.PERSISTENCE_FAILED,
                        failure_code=_failure_code(error),
                    )
                    logger.warning(
                        "History persistence failed: entry_id=%s failure_code=%s",
                        job.entry.request_id,
                        receipt.failure_code,
                    )
                self._receipts[job.entry.request_id] = receipt
            finally:
                self._queue.task_done()

    async def _run_archive(self) -> None:
        while True:
            entry_id = await self._archive_queue.get()
            try:
                if entry_id is None:
                    return
                try:
                    await asyncio.to_thread(self._complete_archive, entry_id)
                except Exception as error:
                    failure_code = _failure_code(error)
                    await asyncio.to_thread(
                        self._mark_archive_failed,
                        entry_id,
                        failure_code,
                    )
                    logger.warning(
                        "History archive failed: entry_id=%s failure_code=%s",
                        entry_id,
                        failure_code,
                    )
            finally:
                self._archive_queue.task_done()

    def _open_connection(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.database_path,
            timeout=5.0,
            check_same_thread=False,
        )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS history_entries (
                entry_id TEXT PRIMARY KEY,
                session_id TEXT,
                agent_id TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                outcome TEXT NOT NULL,
                delivery TEXT NOT NULL,
                capture_status TEXT NOT NULL,
                archive_path TEXT NOT NULL,
                archive_offset INTEGER NOT NULL,
                archive_length INTEGER NOT NULL,
                archive_digest TEXT NOT NULL,
                capture_ref TEXT,
                transport_path TEXT,
                transport_offset INTEGER,
                transport_length INTEGER,
                transport_digest TEXT,
                pinned INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                archive_state TEXT NOT NULL DEFAULT 'active',
                archive_error_code TEXT
            );
            CREATE INDEX IF NOT EXISTS history_entries_started
                ON history_entries (started_at);
            """
        )
        self._ensure_schema(connection)
        connection.commit()
        return connection

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(history_entries)").fetchall()
        }
        additions = (
            ("capture_ref", "TEXT"),
            ("transport_path", "TEXT"),
            ("transport_offset", "INTEGER"),
            ("transport_length", "INTEGER"),
            ("transport_digest", "TEXT"),
            ("archive_state", "TEXT NOT NULL DEFAULT 'active'"),
            ("archive_error_code", "TEXT"),
        )
        for name, definition in additions:
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE history_entries ADD COLUMN {name} {definition}"
                )
        connection.execute(
            """
            UPDATE history_entries
            SET archive_state = 'archived'
            WHERE archived = 1 AND archive_state = 'active'
            """
        )

    def _persist(self, job: _HistoryWriteJob) -> HistoryDurabilityReceipt:
        connection = self._connection
        if connection is None:
            raise RuntimeError("History writer is not started")
        entry = job.entry
        transport = self._transport_for_entry(entry)
        reference = self.archive.append(
            session_id=job.session_id,
            agent_id=job.agent_id,
            entry_id=entry.request_id,
            payload=entry.as_dict(),
            transport=transport,
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO history_entries (
                entry_id, session_id, agent_id, started_at, finished_at,
                outcome, delivery, capture_status, archive_path,
                archive_offset, archive_length, archive_digest, capture_ref,
                transport_path, transport_offset, transport_length, transport_digest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.request_id,
                job.session_id,
                job.agent_id,
                entry.started_at,
                entry.finished_at,
                entry.outcome.value,
                entry.delivery.value,
                entry.capture.status,
                reference.relative_path,
                reference.offset,
                reference.length,
                reference.digest,
                entry.capture_ref,
                reference.relative_path if transport is not None else None,
                reference.offset if transport is not None else None,
                reference.length if transport is not None else None,
                reference.digest if transport is not None else None,
            ),
        )
        connection.commit()
        return HistoryDurabilityReceipt(
            entry_id=entry.request_id,
            state=HistoryDurability.DURABLE,
        )

    def _list_entries_page(
        self,
        limit: int,
        include_archived: bool,
        cursor: str | None,
        session_id: str | None,
        agent_id: str | None,
        outcome: str | None,
        delivery: str | None,
        capture_status: str | None,
    ) -> HistoryPage:
        connection = self._open_read_connection()
        try:
            clauses: list[str] = []
            parameters: list[object] = []
            if not include_archived:
                clauses.append("archived = 0")
            for name, value in (
                ("session_id", session_id),
                ("agent_id", agent_id),
                ("outcome", outcome),
                ("delivery", delivery),
                ("capture_status", capture_status),
            ):
                if value is not None:
                    clauses.append(f"{name} = ?")
                    parameters.append(value)
            if cursor is not None:
                cursor_started_at, cursor_entry_id = _decode_cursor(cursor)
                clauses.append(
                    "(started_at < ? OR (started_at = ? AND entry_id < ?))"
                )
                parameters.extend(
                    [cursor_started_at, cursor_started_at, cursor_entry_id]
                )
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = connection.execute(
                f"""
                SELECT entry_id, session_id, agent_id, started_at, finished_at,
                       outcome, delivery, capture_status, archive_path,
                       archive_offset, archive_length, archive_digest, capture_ref,
                       transport_path, transport_offset, transport_length,
                       transport_digest, pinned, archived, archive_state,
                       archive_error_code
                FROM history_entries
                {where}
                ORDER BY started_at DESC, entry_id DESC
                LIMIT ?
                """,
                (*parameters, limit + 1),
            ).fetchall()
        finally:
            connection.close()
        has_next = len(rows) > limit
        visible_rows = rows[:limit]
        entries = tuple(_index_entry_from_row(row) for row in visible_rows)
        next_cursor = (
            _encode_cursor(entries[-1].started_at, entries[-1].entry_id)
            if has_next and entries
            else None
        )
        return HistoryPage(entries=entries, next_cursor=next_cursor)

    def _get_entry(
        self,
        entry_id: str,
        include_archived: bool,
    ) -> HistoryIndexEntry | None:
        connection = self._open_read_connection()
        try:
            row = connection.execute(
                """
                SELECT entry_id, session_id, agent_id, started_at, finished_at,
                       outcome, delivery, capture_status, archive_path,
                       archive_offset, archive_length, archive_digest, capture_ref,
                       transport_path, transport_offset, transport_length,
                       transport_digest, pinned, archived, archive_state,
                       archive_error_code
                FROM history_entries
                WHERE entry_id = ?
                """,
                (entry_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        entry = _index_entry_from_row(row)
        return entry if include_archived or not entry.archived else None

    def _semantic_payload_for(
        self,
        entry_id: str,
        include_archived: bool,
    ) -> dict[str, object] | None:
        entry = self._get_entry(entry_id, include_archived)
        if entry is None:
            return None
        record = self.archive.read(entry.archive_reference)
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise RuntimeError("History archive payload is not an object")
        return cast(dict[str, object], payload)

    def _transport_for(
        self,
        entry_id: str,
        include_archived: bool,
    ) -> bytes | None:
        entry = self._get_entry(entry_id, include_archived)
        if entry is None or entry.transport_reference is None:
            return None
        return self.archive.read_transport(entry.transport_reference)

    def _transport_for_entry(self, entry: HistoryEntry) -> bytes | None:
        source = self.transport_source
        capture_ref = entry.capture_ref
        if source is None or capture_ref is None:
            return None
        try:
            transport = source.export_request(capture_ref, entry.request_id)
        except Exception as error:
            logger.warning(
                "History transport export failed: entry_id=%s failure_code=%s",
                entry.request_id,
                _failure_code(error),
            )
            return None
        return transport or None

    def _open_read_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path, timeout=5.0)

    def _begin_archive(self, entry_id: str) -> HistoryMutation:
        connection = self._open_read_connection()
        try:
            row = connection.execute(
                """
                SELECT pinned, archived, archive_state
                FROM history_entries
                WHERE entry_id = ?
                """,
                (entry_id,),
            ).fetchone()
            if row is None:
                return HistoryMutation.NOT_FOUND
            pinned, archived, archive_state = row
            if (
                type(archived) is not int
                or type(pinned) is not int
                or not isinstance(archive_state, str)
            ):
                raise RuntimeError("History index contains invalid state flags")
            if archive_state == HistoryArchiveState.ARCHIVED.value or archived:
                return HistoryMutation.ALREADY_APPLIED
            if pinned:
                return HistoryMutation.PINNED
            connection.execute(
                """
                UPDATE history_entries
                SET archive_state = ?, archive_error_code = NULL
                WHERE entry_id = ?
                """,
                (HistoryArchiveState.ARCHIVING.value, entry_id),
            )
            connection.commit()
            return HistoryMutation.ARCHIVING
        finally:
            connection.close()

    def _complete_archive(self, entry_id: str) -> None:
        connection = self._open_read_connection()
        try:
            row = connection.execute(
                """
                SELECT archive_path, archive_offset, archive_length,
                       archive_digest, archive_state
                FROM history_entries
                WHERE entry_id = ?
                """,
                (entry_id,),
            )
            values = row.fetchone()
            if values is None:
                raise ValueError("History entry disappeared during archive")
            (
                archive_path,
                archive_offset,
                archive_length,
                archive_digest,
                archive_state,
            ) = values
            if archive_state != HistoryArchiveState.ARCHIVING.value:
                return
            if not (
                isinstance(archive_path, str)
                and type(archive_offset) is int
                and type(archive_length) is int
                and isinstance(archive_digest, str)
            ):
                raise ValueError("History archive reference is invalid")
            reference = HistoryArchiveReference(
                relative_path=archive_path,
                offset=archive_offset,
                length=archive_length,
                digest=archive_digest,
                entry_id=entry_id,
            )
            self.archive.read(reference)
            connection.execute(
                """
                UPDATE history_entries
                SET archived = 1, archive_state = ?, archive_error_code = NULL
                WHERE entry_id = ?
                """,
                (HistoryArchiveState.ARCHIVED.value, entry_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _mark_archive_failed(self, entry_id: str, failure_code: str) -> None:
        connection = self._open_read_connection()
        try:
            connection.execute(
                """
                UPDATE history_entries
                SET archive_state = ?, archive_error_code = ?
                WHERE entry_id = ? AND archive_state = ?
                """,
                (
                    HistoryArchiveState.ARCHIVE_FAILED.value,
                    failure_code,
                    entry_id,
                    HistoryArchiveState.ARCHIVING.value,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _set_pinned(self, entry_id: str, pinned: bool) -> HistoryMutation:
        connection = self._open_read_connection()
        try:
            row = connection.execute(
                "SELECT pinned FROM history_entries WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()
            if row is None:
                return HistoryMutation.NOT_FOUND
            current = row[0]
            if type(current) is not int:
                raise RuntimeError("History index contains an invalid pin flag")
            if bool(current) is pinned:
                return HistoryMutation.ALREADY_APPLIED
            connection.execute(
                "UPDATE history_entries SET pinned = ? WHERE entry_id = ?",
                (int(pinned), entry_id),
            )
            connection.commit()
            return HistoryMutation.UPDATED
        finally:
            connection.close()


def _failure_code(error: BaseException) -> str:
    return f"{type(error).__module__}.{type(error).__qualname__}"


def _encode_cursor(started_at: str, entry_id: str) -> str:
    raw = f"{started_at}\x00{entry_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    if not cursor:
        raise ValueError("history cursor must not be empty")
    padding = "=" * (-len(cursor) % 4)
    try:
        decoded = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
    except (ValueError, UnicodeError) as error:
        raise ValueError("history cursor is invalid") from error
    try:
        started_at, entry_id = decoded.decode("utf-8").split("\x00", 1)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("history cursor is invalid") from error
    if not started_at or not entry_id:
        raise ValueError("history cursor is invalid")
    return started_at, entry_id


def _index_entry_from_row(row: tuple[object, ...]) -> HistoryIndexEntry:
    (
        entry_id,
        session_id,
        agent_id,
        started_at,
        finished_at,
        outcome,
        delivery,
        capture_status,
        archive_path,
        archive_offset,
        archive_length,
        archive_digest,
        capture_ref,
        transport_path,
        transport_offset,
        transport_length,
        transport_digest,
        pinned,
        archived,
        archive_state,
        archive_error_code,
    ) = row
    if not (
        isinstance(entry_id, str)
        and (session_id is None or isinstance(session_id, str))
        and (agent_id is None or isinstance(agent_id, str))
        and isinstance(started_at, str)
        and isinstance(finished_at, str)
        and isinstance(outcome, str)
        and isinstance(delivery, str)
        and isinstance(capture_status, str)
        and isinstance(archive_path, str)
        and type(archive_offset) is int
        and type(archive_length) is int
        and isinstance(archive_digest, str)
        and (capture_ref is None or isinstance(capture_ref, str))
        and (transport_path is None or isinstance(transport_path, str))
        and (transport_offset is None or type(transport_offset) is int)
        and (transport_length is None or type(transport_length) is int)
        and (transport_digest is None or isinstance(transport_digest, str))
        and type(pinned) is int
        and type(archived) is int
        and isinstance(archive_state, str)
        and (archive_error_code is None or isinstance(archive_error_code, str))
    ):
        raise RuntimeError("History index contains an invalid row")
    transport_reference: HistoryArchiveReference | None = None
    transport_values = (
        transport_path,
        transport_offset,
        transport_length,
        transport_digest,
    )
    if any(value is not None for value in transport_values):
        if not all(value is not None for value in transport_values):
            raise RuntimeError("History index contains an incomplete transport reference")
        transport_reference = HistoryArchiveReference(
            relative_path=cast(str, transport_path),
            offset=cast(int, transport_offset),
            length=cast(int, transport_length),
            digest=cast(str, transport_digest),
            entry_id=entry_id,
        )
    try:
        state = HistoryArchiveState(archive_state)
    except ValueError as error:
        raise RuntimeError("History index contains an invalid archive state") from error
    return HistoryIndexEntry(
        entry_id=entry_id,
        session_id=session_id,
        agent_id=agent_id,
        started_at=started_at,
        finished_at=finished_at,
        outcome=outcome,
        delivery=delivery,
        capture_status=capture_status,
        capture_ref=capture_ref,
        archive_reference=HistoryArchiveReference(
            relative_path=archive_path,
            offset=archive_offset,
            length=archive_length,
            digest=archive_digest,
            entry_id=entry_id,
        ),
        transport_reference=transport_reference,
        archive_state=state,
        archive_error_code=archive_error_code,
        pinned=bool(pinned),
        archived=bool(archived) or state is HistoryArchiveState.ARCHIVED,
    )


__all__ = [
    "HistoryArchiveState",
    "HistoryDurability",
    "HistoryDurabilityReceipt",
    "HistoryIndexEntry",
    "HistoryMutation",
    "HistoryPage",
    "HistorySubmission",
    "HistoryTransportSource",
    "HistoryWriter",
]
