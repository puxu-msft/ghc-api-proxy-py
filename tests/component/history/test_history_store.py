from pathlib import Path

import pytest

from app.errors import ApiError, ErrorCategory
from app.history.consumer import HistoryConsumer
from app.history.in_flight import InFlightHistory
from app.history.sessions import identify_session
from app.history.sqlite.writer import HistoryWriter
from app.history.store import HistoryStore
from app.history.types import HistoryEntry, ModelRef
from app.pipeline.context import (
    RequestContext,
    RequestConversionFactRecord,
    RequestState,
)


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
    import threading

    entered = threading.Event()
    release = threading.Event()

    class BlockingWriter(HistoryWriter):
        def _insert(self, entry: HistoryEntry) -> None:
            if entry.id == "inflight":
                entered.set()
                release.wait(timeout=5)
            super()._insert(entry)

    writer = BlockingWriter(tmp_path / "history.db", queue_size=1)
    await writer.start()
    try:
        with pytest.raises(ValueError, match="mandatory"):
            writer.submit_nowait(_entry("bad-api", "completed", 0), discardable=False)
        assert writer.submit_nowait(_entry("inflight", "completed", 1), discardable=True)
        assert await __import__("asyncio").to_thread(entered.wait, 1)
        assert writer.submit_nowait(_entry("queued", "completed", 2), discardable=True)
        assert writer.submit_nowait(_entry("dropped", "completed", 3), discardable=True) is False
        mandatory = __import__("asyncio").create_task(
            writer.submit(_entry("mandatory", "completed", 4))
        )
        release.set()
        await mandatory
    finally:
        release.set()
        await writer.close()


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
        with pytest.raises(OSError, match="disk hiccup"):
            await writer.submit(_entry("bad", "completed", 1))
        await writer.submit(_entry("good", "completed", 2))
        await writer.flush()
        entries = await writer.list_entries(limit=10)
    finally:
        await writer.close()

    assert writer.error_count == 1
    assert [entry.id for entry in entries] == ["good"]


@pytest.mark.asyncio
async def test_fatal_write_error_propagates_to_submit_flush_and_close(tmp_path: Path) -> None:
    class FatalWriter(HistoryWriter):
        def _insert(self, entry: HistoryEntry) -> None:
            del entry
            import sqlite3

            raise sqlite3.OperationalError("attempt to write a readonly database")

    writer = FatalWriter(tmp_path / "history.db")
    await writer.start()
    with pytest.raises(Exception, match="readonly"):
        await writer.submit(_entry("bad", "completed", 1))
    with pytest.raises(RuntimeError, match="fatal state"):
        await writer.flush()
    with pytest.raises(RuntimeError, match="fatal state"):
        await writer.close()


@pytest.mark.asyncio
async def test_busy_retry_respects_submit_deadline(tmp_path: Path) -> None:
    class BusyWriter(HistoryWriter):
        def _insert(self, entry: HistoryEntry) -> None:
            del entry
            import sqlite3

            raise sqlite3.OperationalError("database is locked")

    writer = BusyWriter(tmp_path / "history.db", busy_timeout=1)
    await writer.start()
    try:
        with pytest.raises(Exception, match="locked"):
            await writer.submit(_entry("busy", "completed", 1), timeout=0.05)
    finally:
        await writer.close()


@pytest.mark.asyncio
async def test_cancelled_submit_waiter_does_not_kill_writer(tmp_path: Path) -> None:
    import threading

    entered = threading.Event()
    release = threading.Event()

    class BlockingWriter(HistoryWriter):
        def _insert(self, entry: HistoryEntry) -> None:
            if entry.id == "cancelled":
                entered.set()
                release.wait(timeout=5)
            super()._insert(entry)

    writer = BlockingWriter(tmp_path / "history.db")
    await writer.start()
    cancelled = __import__("asyncio").create_task(
        writer.submit(_entry("cancelled", "completed", 1))
    )
    assert await __import__("asyncio").to_thread(entered.wait, 1)
    cancelled.cancel()
    with pytest.raises(__import__("asyncio").CancelledError):
        await cancelled
    release.set()
    await writer.submit(_entry("after", "completed", 2))
    await writer.flush()
    entries = await writer.list_entries(limit=10)
    await writer.close()
    assert {entry.id for entry in entries} == {"cancelled", "after"}


@pytest.mark.asyncio
async def test_submit_after_close_fails_without_hanging(tmp_path: Path) -> None:
    writer = HistoryWriter(tmp_path / "history.db")
    await writer.start()
    await writer.close()
    with pytest.raises(RuntimeError, match="not accepting"):
        await writer.submit(_entry("late", "completed", 1))
    with pytest.raises(RuntimeError, match="not accepting"):
        await writer.reap(success_limit=1, failure_limit=1)


@pytest.mark.asyncio
async def test_concurrent_close_uses_one_worker_sentinel(tmp_path: Path) -> None:
    writer = HistoryWriter(tmp_path / "history.db")
    await writer.start()

    await __import__("asyncio").gather(writer.close(), writer.close())

    assert writer.queued_jobs == 0


@pytest.mark.asyncio
async def test_a_fatal_history_write_poisons_the_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A write that fails fatally must not be followed by a clean close.

    This used to also assert that the failure marked the rolling generation failed, so the controller could keep the previous one serving. That mechanism was removed on 2026-08-19; what survives is the store's own refusal to pretend it shut down cleanly, which is what stops a caller treating a lost write as a successful one.
    """
    store = HistoryStore(tmp_path / "history.db")
    await store.start()

    def fail_insert(_entry: HistoryEntry) -> None:
        import sqlite3

        raise sqlite3.OperationalError("disk I/O error")

    def patched_insert(_writer: HistoryWriter, entry: HistoryEntry) -> None:
        fail_insert(entry)

    monkeypatch.setattr(HistoryWriter, "_insert", patched_insert)
    with pytest.raises(Exception, match="I/O"):
        await store.finalize(_entry("fatal", "failed", 1))
    with pytest.raises(RuntimeError, match="fatal state"):
        await store.close()


@pytest.mark.asyncio
async def test_persisted_pin_update_round_trips(tmp_path: Path) -> None:
    writer = HistoryWriter(tmp_path / "history.db")
    await writer.start()
    try:
        await writer.submit(_entry("pin-me", "completed", 1))
        await writer.flush()
        assert await writer.set_pinned("pin-me", True) is True
        entry = await writer.get("pin-me")
    finally:
        await writer.close()
    assert entry is not None and entry.pinned is True


@pytest.mark.asyncio
async def test_writer_round_trips_response_and_usage_summary(tmp_path: Path) -> None:
    writer = HistoryWriter(tmp_path / "history.db")
    await writer.start()
    expected = _entry("with-facts", "completed", 1)
    expected.response = {"content": [{"type": "text", "text": "hooked"}]}
    expected.usage = {
        "input_tokens": 7,
        "output_tokens": 3,
        "estimated": False,
        "inconsistent": True,
        "conversion_facts": [
            {"code": "usage_inconsistent", "field_path": "usage.total_tokens"}
        ],
    }
    try:
        await writer.submit(expected)
        await writer.flush()
        actual = await writer.get(expected.id)
    finally:
        await writer.close()

    assert actual is not None
    assert actual.response == expected.response
    assert actual.usage == expected.usage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "projection"),
    [
        (
            RequestState.COMPLETED,
            {
                "type": "message",
                "content": [{"type": "text", "text": "streamed"}],
                "delivery": {"complete": True, "uncertain": False},
                "usage": {"input_tokens": 2, "output_tokens": 1},
            },
        ),
        (
            RequestState.FAILED,
            {
                "type": "message",
                "content": [{"type": "text", "text": "committed prefix"}],
                "delivery": {"complete": False, "uncertain": False},
                "usage": {"input_tokens": 2, "output_tokens": 1},
                "error": {
                    "type": "upstream_error",
                    "message": "stream conversion failed",
                    "code": "unsupported_responses_event",
                },
            },
        ),
        (
            RequestState.FAILED,
            {
                "type": "message",
                "content": [],
                "delivery": {
                    "complete": False,
                    "uncertain": True,
                    "possibly_visible_block": {"type": "text", "text": "maybe"},
                },
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "error": {
                    "type": "api_error",
                    "message": "downstream delivery outcome is uncertain",
                    "code": "delivery_uncertain",
                },
            },
        ),
    ],
)
async def test_history_consumer_persists_explicit_stream_projection(
    tmp_path: Path,
    state: RequestState,
    projection: dict[str, object],
) -> None:
    store = HistoryStore(tmp_path / "history.db")
    await store.start()
    consumer = HistoryConsumer(store)
    context = RequestContext(
        original_model="requested",
        original_payload={"model": "requested", "stream": True},
        session_id="session",
    )
    context.resolved_model = "resolved"
    context.conversion_facts = (
        RequestConversionFactRecord(
            attempt=1,
            field_path="metadata.tenant",
            disposition="degrade",
            reason="metadata_not_allowlisted",
        ),
    )
    context.transition(RequestState.SANITIZING)
    context.transition(RequestState.EXECUTING)
    context.transition(RequestState.STREAMING)
    await consumer.started(context)
    if state is RequestState.COMPLETED:
        context.transition(RequestState.COMPLETED)
    else:
        context.fail(
            ApiError(
                "downstream delivery outcome is uncertain",
                category=ErrorCategory.NETWORK,
                status_code=499,
                code="delivery_uncertain",
            )
        )
    try:
        stream_usage = {"input_tokens": 2, "output_tokens": 1}
        await consumer.finalized(
            context,
            response=projection,
            usage=stream_usage,
            usage_estimated=state is RequestState.FAILED,
        )
        actual = await store.get(context.id)
    finally:
        await store.close()

    assert actual is not None
    assert actual.status == state.value
    assert actual.response == projection
    assert actual.usage == {
        "input_tokens": 2,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "output_tokens": 1,
        "reasoning_tokens": 0,
        "total_tokens": 3,
        "estimated": state is RequestState.FAILED,
        "inconsistent": False,
        "conversion_facts": [
            {
                "provenance": "request",
                "attempt": 1,
                "field_path": "metadata.tenant",
                "disposition": "degrade",
                "reason": "metadata_not_allowlisted",
            }
        ],
    }


@pytest.mark.asyncio
async def test_history_consumer_failure_without_projection_has_no_success_facts(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path / "history.db")
    await store.start()
    consumer = HistoryConsumer(store)
    context = RequestContext(
        original_model="requested",
        original_payload={"model": "requested"},
        session_id="session",
    )
    context.final_response_payload = {"type": "message", "content": []}
    context.transition(RequestState.SANITIZING)
    context.fail(
        ApiError(
            "invalid final response",
            category=ErrorCategory.UPSTREAM,
            status_code=502,
        )
    )
    await consumer.started(context)
    try:
        await consumer.finalized(context)
        actual = await store.get(context.id)
    finally:
        await store.close()

    assert actual is not None
    assert actual.status == "failed"
    assert actual.response is None
    assert actual.usage is None
