import asyncio
import sqlite3
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


class HistoryWriter:
    def __init__(self, db_path: Path, *, queue_size: int = 1000) -> None:
        self._path = db_path
        self._queue: asyncio.Queue[HistoryEntry | ReapJob | None] = asyncio.Queue(
            maxsize=queue_size
        )
        self._task: asyncio.Task[None] | None = None
        self._connection: sqlite3.Connection | None = None
        self.error_count = 0

    @property
    def started(self) -> bool:
        return self._connection is not None

    async def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await asyncio.to_thread(self._open)
        self._task = asyncio.create_task(self._run())

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, check_same_thread=False)
        connection.executescript(SCHEMA)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def submit_nowait(self, entry: HistoryEntry, *, discardable: bool) -> bool:
        try:
            self._queue.put_nowait(entry)
            return True
        except asyncio.QueueFull:
            if discardable:
                return False
            raise

    async def submit(self, entry: HistoryEntry) -> None:
        await self._queue.put(entry)

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
                    await asyncio.to_thread(self._insert, entry)
            except Exception:
                self.error_count += 1
            finally:
                self._queue.task_done()

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

    async def reap(self, *, success_limit: int, failure_limit: int) -> None:
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
        if self._task is not None:
            await self._queue.put(None)
            await self._task
        if self._connection is not None:
            await asyncio.to_thread(self._connection.close)