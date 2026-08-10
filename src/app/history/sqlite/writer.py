import asyncio
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.history.sqlite.schema import SCHEMA
from app.history.types import HistoryEntry, ModelRef
from app.wire_json import dumps, loads


@dataclass(frozen=True, slots=True)
class ReapJob:
    success_limit: int
    failure_limit: int


@dataclass(frozen=True, slots=True)
class InsertJob:
    entry: HistoryEntry
    acknowledgement: asyncio.Future[None] | None
    deadline: float | None


class HistoryWriter:
    def __init__(
        self,
        db_path: Path,
        *,
        queue_size: int = 1000,
        busy_timeout: float = 5.0,
        on_fatal: Callable[[BaseException], Awaitable[None]] | None = None,
    ) -> None:
        self._path = db_path
        self._queue: asyncio.Queue[InsertJob | ReapJob | None] = asyncio.Queue(
            maxsize=queue_size
        )
        self._task: asyncio.Task[None] | None = None
        self._connection: sqlite3.Connection | None = None
        self.error_count = 0
        self._busy_timeout = busy_timeout
        self._fatal_error: BaseException | None = None
        self._state = "new"
        self._lifecycle_lock = asyncio.Lock()
        self._on_fatal = on_fatal
        self._close_task: asyncio.Task[None] | None = None

    @property
    def started(self) -> bool:
        return self._connection is not None

    @property
    def queued_jobs(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await asyncio.to_thread(self._open)
        self._task = asyncio.create_task(self._run())
        self._state = "running"

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, check_same_thread=False)
        connection.executescript(SCHEMA)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=0")
        return connection

    def submit_nowait(self, entry: HistoryEntry, *, discardable: bool) -> bool:
        if not discardable:
            raise ValueError(
                "mandatory history writes must use submit() for durable acknowledgement"
            )
        self._raise_if_not_running()
        self._raise_if_fatal()
        try:
            self._queue.put_nowait(InsertJob(entry, None, None))
            return True
        except asyncio.QueueFull:
            if discardable:
                return False
            raise

    async def submit(self, entry: HistoryEntry, *, timeout: float | None = None) -> None:
        async with self._lifecycle_lock:
            self._raise_if_not_running()
            self._raise_if_fatal()
            acknowledgement: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            deadline = None if timeout is None else time.monotonic() + timeout
            await self._queue.put(InsertJob(entry, acknowledgement, deadline))
        await asyncio.shield(acknowledgement)

    async def _run(self) -> None:
        while True:
            entry = await self._queue.get()
            try:
                if entry is None:
                    return
                if isinstance(entry, ReapJob):
                    await asyncio.to_thread(
                        self._reap,
                        entry.success_limit,
                        entry.failure_limit,
                    )
                else:
                    await asyncio.to_thread(self._insert_with_retry, entry)
                    self._complete_ack(entry.acknowledgement)
            except Exception as error:
                self.error_count += 1
                if self._is_fatal(error):
                    self._fatal_error = error
                    self._state = "fatal"
                    if self._on_fatal is not None:
                        await self._on_fatal(error)
                if isinstance(entry, InsertJob) and entry.acknowledgement is not None:
                    self._complete_ack(entry.acknowledgement, error)
            finally:
                self._queue.task_done()

    def _insert_with_retry(self, job: InsertJob) -> None:
        deadline = job.deadline or (time.monotonic() + self._busy_timeout)
        while True:
            try:
                self._insert(job.entry)
                return
            except sqlite3.OperationalError as error:
                if not self._is_busy(error) or time.monotonic() >= deadline:
                    raise
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))

    def _insert(self, entry: HistoryEntry) -> None:
        assert self._connection is not None
        self._connection.execute(
            """INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.id, entry.session_id, entry.agent_id, entry.started_at, entry.ended_at,
                entry.endpoint, entry.status, entry.model.requested, entry.model.resolved,
                dumps(entry.request_payload),
                dumps(entry.response) if entry.response is not None else None,
                dumps(entry.usage) if entry.usage is not None else None,
                entry.error_message,
                int(entry.pinned),
            ),
        )
        self._connection.commit()

    async def flush(self) -> None:
        await self._queue.join()
        self._raise_if_fatal()

    async def reap(self, *, success_limit: int, failure_limit: int) -> None:
        async with self._lifecycle_lock:
            self._raise_if_not_running()
            await self._queue.put(ReapJob(success_limit, failure_limit))
        await self._queue.join()

    def _reap(self, success_limit: int, failure_limit: int) -> None:
        assert self._connection is not None
        for clause, limit in (
            ("status = 'completed'", success_limit),
            ("status IN ('failed','aborted','interrupted')", failure_limit),
        ):
            if limit <= 0:
                continue
            self._connection.execute(
                f"""DELETE FROM entries WHERE id IN (
                    SELECT id FROM entries
                    WHERE {clause} AND pinned = 0
                    ORDER BY started_at DESC
                    LIMIT -1 OFFSET ?
                )""",
                (limit,),
            )
        self._connection.commit()

    async def list_entries(self, *, limit: int) -> list[HistoryEntry]:
        return await asyncio.to_thread(self._list_entries, limit)

    def _list_entries(self, limit: int) -> list[HistoryEntry]:
        assert self._connection is not None
        rows = self._connection.execute(
            "SELECT * FROM entries ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._from_row(row) for row in rows]

    async def get(self, entry_id: str) -> HistoryEntry | None:
        return await asyncio.to_thread(self._get, entry_id)

    def _get(self, entry_id: str) -> HistoryEntry | None:
        assert self._connection is not None
        row = self._connection.execute(
            "SELECT * FROM entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        return self._from_row(row) if row is not None else None

    async def set_pinned(self, entry_id: str, pinned: bool) -> bool:
        return await asyncio.to_thread(self._set_pinned, entry_id, pinned)

    def _set_pinned(self, entry_id: str, pinned: bool) -> bool:
        assert self._connection is not None
        cursor = self._connection.execute(
            "UPDATE entries SET pinned = ? WHERE id = ?",
            (int(pinned), entry_id),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _from_row(row: tuple[Any, ...]) -> HistoryEntry:
        request_payload = loads(row[9])
        response = loads(row[10]) if row[10] else None
        usage = loads(row[11]) if row[11] else None
        if not isinstance(request_payload, dict):
            raise ValueError("history request_payload must be an object")
        if response is not None and not isinstance(response, dict):
            raise ValueError("history response must be an object")
        if usage is not None and not isinstance(usage, dict):
            raise ValueError("history usage must be an object")
        return HistoryEntry(
            id=row[0], session_id=row[1], agent_id=row[2], started_at=row[3], ended_at=row[4],
            endpoint=row[5], status=row[6], model=ModelRef(row[7], row[8]),
            request_payload=request_payload,
            response=response,
            usage=usage,
            error_message=row[12],
            pinned=bool(row[13]),
        )

    async def close(self) -> None:
        async with self._lifecycle_lock:
            if self._state == "closed":
                return
            if self._close_task is None:
                if self._state != "fatal":
                    self._state = "closing"
                self._close_task = asyncio.create_task(self._close_impl())
            task = self._close_task
        await asyncio.shield(task)

    async def _close_impl(self) -> None:
        if self._task is not None and not self._task.done():
            await self._queue.put(None)
        if self._task is not None:
            await self._task
        if self._connection is not None:
            await asyncio.to_thread(self._connection.close)
            self._connection = None
        fatal = self._fatal_error
        self._state = "closed"
        if fatal is not None:
            raise RuntimeError("history writer is in a fatal state") from fatal

    def _raise_if_fatal(self) -> None:
        if self._fatal_error is not None:
            raise RuntimeError("history writer is in a fatal state") from self._fatal_error

    def _raise_if_not_running(self) -> None:
        if self._state != "running":
            raise RuntimeError(f"history writer is not accepting jobs: {self._state}")

    @staticmethod
    def _complete_ack(
        acknowledgement: asyncio.Future[None] | None,
        error: BaseException | None = None,
    ) -> None:
        if acknowledgement is None or acknowledgement.done():
            return
        if error is None:
            acknowledgement.set_result(None)
        else:
            acknowledgement.set_exception(error)

    @staticmethod
    def _is_busy(error: sqlite3.OperationalError) -> bool:
        code = getattr(error, "sqlite_errorcode", None)
        primary = None if code is None else code & 0xFF
        return primary in {
            sqlite3.SQLITE_BUSY,
            sqlite3.SQLITE_LOCKED,
        } or "locked" in str(error).lower()

    @staticmethod
    def _is_fatal(error: BaseException) -> bool:
        if isinstance(error, sqlite3.Error):
            code = getattr(error, "sqlite_errorcode", None)
            primary = None if code is None else code & 0xFF
            if primary in {
                sqlite3.SQLITE_IOERR,
                sqlite3.SQLITE_READONLY,
                sqlite3.SQLITE_CORRUPT,
                sqlite3.SQLITE_FULL,
            }:
                return True
            message = str(error).lower()
            return any(
                marker in message
                for marker in ("readonly", "disk i/o", "database disk image is malformed", "full")
            )
        return False