from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from app.history.sqlite.writer import HistoryWriter
from app.history.types import HistoryEntry, ModelRef


def _worker_script() -> str:
    return textwrap.dedent(
        """
        import asyncio
        import json
        import sys
        from pathlib import Path
        from app.history.sqlite.writer import HistoryWriter
        from app.history.types import HistoryEntry, ModelRef

        async def main():
            db = Path(sys.argv[1])
            ids = json.loads(sys.argv[2])
            writer = HistoryWriter(db, busy_timeout=10)
            await writer.start()
            try:
                for index, identifier in enumerate(ids):
                    await writer.submit(
                        HistoryEntry(
                            id=identifier,
                            session_id="session",
                            agent_id="main",
                            started_at=float(index),
                            ended_at=float(index + 1),
                            endpoint="anthropic-messages",
                            status="completed",
                            model=ModelRef("requested", "resolved"),
                            request_payload={"id": identifier},
                        ),
                        timeout=10,
                    )
                await writer.flush()
            finally:
                await writer.close()
        asyncio.run(main())
        """
    )


def test_shared_wal_two_processes_preserve_complete_terminal_id_set(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    ids_a = [f"a-{index:03d}" for index in range(40)]
    ids_b = [f"b-{index:03d}" for index in range(40)]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", _worker_script(), str(db), json.dumps(ids)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for ids in (ids_a, ids_b)
    ]
    results = [process.communicate(timeout=20) for process in processes]
    for process, (_stdout, stderr) in zip(processes, results, strict=True):
        assert process.returncode == 0, stderr

    connection = sqlite3.connect(db)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        actual = {row[0] for row in connection.execute("SELECT id FROM entries")}
    finally:
        connection.close()
    assert actual == set(ids_a) | set(ids_b)


@pytest.mark.asyncio
async def test_real_busy_lock_respects_deadline_and_writer_recovers(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    insert_entered = threading.Event()

    class ObservedWriter(HistoryWriter):
        def _insert(self, entry: HistoryEntry) -> None:
            insert_entered.set()
            super()._insert(entry)

    writer = ObservedWriter(db, busy_timeout=1)
    await writer.start()
    locker = sqlite3.connect(db, check_same_thread=False)
    locker.execute("BEGIN IMMEDIATE")

    def entry(identifier: str) -> HistoryEntry:
        return HistoryEntry(
            id=identifier,
            session_id="session",
            agent_id="main",
            started_at=1,
            ended_at=2,
            endpoint="anthropic-messages",
            status="completed",
            model=ModelRef("requested", "resolved"),
            request_payload={"id": identifier},
        )

    try:
        pending = __import__("asyncio").create_task(
            writer.submit(entry("released-before-deadline"), timeout=1)
        )
        assert await __import__("asyncio").to_thread(insert_entered.wait, 0.5)
        assert not pending.done()
        locker.rollback()
        await pending
        assert await writer.get("released-before-deadline") is not None

        locker.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            await writer.submit(entry("deadline"), timeout=0.05)
        locker.rollback()
        await writer.submit(entry("after-lock"), timeout=1)
        await writer.flush()
        assert await writer.get("after-lock") is not None
    finally:
        locker.close()
        await writer.close()
