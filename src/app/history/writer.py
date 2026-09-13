"""Bounded asynchronous History projection writer."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

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
    archive_reference: HistoryArchiveReference
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
            "archive": {
                "path": self.archive_reference.relative_path,
                "offset": self.archive_reference.offset,
                "length": self.archive_reference.length,
                "digest": self.archive_reference.digest,
            },
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
        queue_size: int = 1000,
    ) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        self.database_path = database_path
        self.archive = archive
        self._queue: asyncio.Queue[_HistoryWriteJob | None] = asyncio.Queue(
            maxsize=queue_size
        )
        self._connection: sqlite3.Connection | None = None
        self._task: asyncio.Task[None] | None = None
        self._receipts: dict[str, HistoryDurabilityReceipt] = {}
        self._closed = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._connection = await asyncio.to_thread(self._open_connection)
        self._task = asyncio.create_task(self._run(), name="history-writer")

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

    def receipt_for(self, entry_id: str) -> HistoryDurabilityReceipt | None:
        return self._receipts.get(entry_id)

    async def list_entries(
        self,
        *,
        limit: int = 50,
        include_archived: bool = False,
    ) -> tuple[HistoryIndexEntry, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if self._task is None or self._closed:
            raise RuntimeError("History writer is not running")
        return await asyncio.to_thread(
            self._list_entries,
            limit,
            include_archived,
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

    async def archive_entry(self, entry_id: str) -> HistoryMutation:
        if self._task is None or self._closed:
            raise RuntimeError("History writer is not running")
        return await asyncio.to_thread(self._archive_entry, entry_id)

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
        connection = self._connection
        if connection is not None:
            await asyncio.to_thread(connection.close)
        self._connection = None
        self._task = None

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
                pinned INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS history_entries_started
                ON history_entries (started_at);
            """
        )
        connection.commit()
        return connection

    def _persist(self, job: _HistoryWriteJob) -> HistoryDurabilityReceipt:
        connection = self._connection
        if connection is None:
            raise RuntimeError("History writer is not started")
        entry = job.entry
        reference = self.archive.append(
            session_id=job.session_id,
            agent_id=job.agent_id,
            entry_id=entry.request_id,
            payload=entry.as_dict(),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO history_entries (
                entry_id, session_id, agent_id, started_at, finished_at,
                outcome, delivery, capture_status, archive_path,
                archive_offset, archive_length, archive_digest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        connection.commit()
        return HistoryDurabilityReceipt(
            entry_id=entry.request_id,
            state=HistoryDurability.DURABLE,
        )

    def _list_entries(
        self,
        limit: int,
        include_archived: bool,
    ) -> tuple[HistoryIndexEntry, ...]:
        connection = self._open_read_connection()
        try:
            clause = "" if include_archived else "WHERE archived = 0"
            rows = connection.execute(
                f"""
                SELECT entry_id, session_id, agent_id, started_at, finished_at,
                       outcome, delivery, capture_status, archive_path,
                       archive_offset, archive_length, archive_digest,
                       pinned, archived
                FROM history_entries
                {clause}
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(_index_entry_from_row(row) for row in rows)

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
                       archive_offset, archive_length, archive_digest,
                       pinned, archived
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

    def _open_read_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path, timeout=5.0)

    def _archive_entry(self, entry_id: str) -> HistoryMutation:
        connection = self._open_read_connection()
        try:
            row = connection.execute(
                "SELECT pinned, archived FROM history_entries WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()
            if row is None:
                return HistoryMutation.NOT_FOUND
            pinned, archived = row
            if type(archived) is not int or type(pinned) is not int:
                raise RuntimeError("History index contains invalid state flags")
            if archived:
                return HistoryMutation.ALREADY_APPLIED
            if pinned:
                return HistoryMutation.PINNED
            connection.execute(
                "UPDATE history_entries SET archived = 1 WHERE entry_id = ?",
                (entry_id,),
            )
            connection.commit()
            return HistoryMutation.UPDATED
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
        pinned,
        archived,
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
        and type(pinned) is int
        and type(archived) is int
    ):
        raise RuntimeError("History index contains an invalid row")
    return HistoryIndexEntry(
        entry_id=entry_id,
        session_id=session_id,
        agent_id=agent_id,
        started_at=started_at,
        finished_at=finished_at,
        outcome=outcome,
        delivery=delivery,
        capture_status=capture_status,
        archive_reference=HistoryArchiveReference(
            relative_path=archive_path,
            offset=archive_offset,
            length=archive_length,
            digest=archive_digest,
            entry_id=entry_id,
        ),
        pinned=bool(pinned),
        archived=bool(archived),
    )


__all__ = [
    "HistoryDurability",
    "HistoryDurabilityReceipt",
    "HistoryIndexEntry",
    "HistoryMutation",
    "HistorySubmission",
    "HistoryWriter",
]
