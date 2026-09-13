"""Bounded asynchronous History projection writer."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.history.archive import HistoryArchiveStore
from app.history.entry import HistoryEntry

logger = logging.getLogger(__name__)


class HistoryDurability(StrEnum):
    DURABLE = "durable"
    PERSISTENCE_FAILED = "persistence_failed"


class HistorySubmission(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class HistoryDurabilityReceipt:
    entry_id: str
    state: HistoryDurability
    failure_code: str | None = None


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


def _failure_code(error: BaseException) -> str:
    return f"{type(error).__module__}.{type(error).__qualname__}"


__all__ = [
    "HistoryDurability",
    "HistoryDurabilityReceipt",
    "HistorySubmission",
    "HistoryWriter",
]
