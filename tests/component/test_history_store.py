from pathlib import Path

import pytest

from app.history.in_flight import InFlightHistory
from app.history.sessions import identify_session
from app.history.sqlite.writer import HistoryWriter
from app.history.types import HistoryEntry, ModelRef


def _entry(identifier: str, status: str, started_at: float) -> HistoryEntry:
    return HistoryEntry(
        id=identifier,
        session_id="session",
        agent_id="main",
        started_at=started_at,
        ended_at=started_at + 1,
        endpoint="anthropic-messages",
        status=status,
        model=ModelRef("requested", "resolved"),
        request_payload={"id": identifier},
    )


@pytest.mark.asyncio
async def test_history_writer_persists_and_reaps_status_buckets(tmp_path: Path) -> None:
    writer = HistoryWriter(tmp_path / "history.db", queue_size=2)
    await writer.start()
    try:
        for index in range(4):
            await writer.submit(_entry(f"success-{index}", "completed", float(index)))
        for index in range(3):
            await writer.submit(_entry(f"failure-{index}", "failed", float(index)))
        await writer.flush()
        await writer.reap(success_limit=2, failure_limit=1)
        entries = await writer.list_entries(limit=10)
    finally:
        await writer.close()

    assert [entry.id for entry in entries if entry.status == "completed"] == [
        "success-3",
        "success-2",
    ]
    assert [entry.id for entry in entries if entry.status == "failed"] == ["failure-2"]


@pytest.mark.asyncio
async def test_discardable_history_job_drops_when_queue_is_full(tmp_path: Path) -> None:
    writer = HistoryWriter(tmp_path / "history.db", queue_size=1)
    assert writer.submit_nowait(_entry("a", "completed", 1), discardable=False) is True
    assert writer.submit_nowait(_entry("b", "completed", 2), discardable=True) is False


def test_in_flight_and_session_identification() -> None:
    entry = _entry("id", "pending", 1)
    live = InFlightHistory()
    live.add(entry)
    assert live.get("id") is entry
    assert identify_session(
        {"x-session-id": "generic", "x-claude-code-session-id": "claude"}
    ) == ("claude", "main")


@pytest.mark.asyncio
async def test_writer_continues_after_single_job_failure(tmp_path: Path) -> None:
    class FlakyWriter(HistoryWriter):
        failed = False

        def _insert(self, entry: HistoryEntry) -> None:
            if not self.failed:
                self.failed = True
                raise OSError("disk hiccup")
            super()._insert(entry)

    writer = FlakyWriter(tmp_path / "history.db")
    await writer.start()
    try:
        await writer.submit(_entry("bad", "completed", 1))
        await writer.submit(_entry("good", "completed", 2))
        await writer.flush()
        entries = await writer.list_entries(limit=10)
    finally:
        await writer.close()

    assert writer.error_count == 1
    assert [entry.id for entry in entries] == ["good"]