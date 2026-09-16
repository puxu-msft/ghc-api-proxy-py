from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from app.history import (
    CaptureCapabilities,
    HistoryArchiveState,
    HistoryArchiveStore,
    HistoryDelivery,
    HistoryDurability,
    HistoryEntry,
    HistoryMutation,
    HistoryOutcome,
    HistoryRetentionCandidate,
    HistorySubmission,
    HistoryWriter,
)
from app.history.entry import CaptureAttemptCapabilities
from app.pipeline.response_observation import FrozenJsonObject, freeze_json


def _entry() -> HistoryEntry:
    usage = freeze_json({})
    empty = freeze_json([])
    assert isinstance(usage, FrozenJsonObject)
    return HistoryEntry(
        request_id="request-writer-1",
        started_at="2026-09-13T00:00:00.000Z",
        finished_at="2026-09-13T00:00:01.000Z",
        outcome=HistoryOutcome.COMPLETED,
        delivery=HistoryDelivery.COMPLETE,
        status_code=200,
        inbound_format="anthropic-messages",
        requested_model="model",
        resolved_model="model",
        provider_name="provider",
        attempts=1,
        retry_count=0,
        replaced_failures=(),
        usage=usage,
        losses=empty,
        facts=empty,
        capture=CaptureCapabilities(),
    )


@pytest.mark.asyncio
async def test_history_writer_accepts_and_durably_records_entry(tmp_path: Path) -> None:
    writer = HistoryWriter(
        database_path=tmp_path / "history.sqlite3",
        archive=HistoryArchiveStore(tmp_path / "archive"),
        queue_size=2,
    )
    await writer.start()
    try:
        entry = _entry()
        assert (
            await writer.submit(
                entry,
                session_id="session-1",
                agent_id=None,
            )
            is HistorySubmission.ACCEPTED
        )
        await writer.wait_idle()

        receipt = writer.receipt_for(entry.request_id)
        assert receipt is not None
        assert receipt.state is HistoryDurability.DURABLE
    finally:
        await writer.close()


@pytest.mark.asyncio
async def test_history_writer_round_trips_safe_attempt_capability_matrix(
    tmp_path: Path,
) -> None:
    writer = HistoryWriter(
        database_path=tmp_path / "history.sqlite3",
        archive=HistoryArchiveStore(tmp_path / "archive"),
    )
    await writer.start()
    try:
        entry = replace(
            _entry(),
            capture=CaptureCapabilities(
                status="incomplete",
                client_request_available=True,
                semantic_replay_eligible=True,
                live_replay_eligible=True,
                upstream_attempts=(
                    CaptureAttemptCapabilities(
                        attempt=0,
                        attempt_started=True,
                        request_started=True,
                        request_headers_available=True,
                        request_body_available=True,
                        response_started=True,
                        response_headers_available=True,
                        response_body_available=True,
                        response_complete=True,
                        attempt_complete=True,
                        wire_diagnostic_eligible=True,
                    ),
                    CaptureAttemptCapabilities(
                        attempt=1,
                        attempt_started=True,
                        request_started=True,
                        request_headers_available=False,
                        request_body_available=True,
                        response_started=True,
                        response_headers_available=False,
                        response_body_available=True,
                        response_complete=False,
                        attempt_complete=False,
                        wire_diagnostic_eligible=False,
                    ),
                ),
            ),
        )
        await writer.submit(entry, session_id="session-1", agent_id=None)
        await writer.wait_idle()

        indexed = await writer.get_entry(entry.request_id)

        assert indexed is not None
        assert indexed.capture == entry.capture
        projection = cast(dict[str, object], indexed.as_dict()["capture"])
        assert set(projection) == {
            "status",
            "client_request_available",
            "client_response_available",
            "wire_diagnostic_eligible",
            "semantic_replay_eligible",
            "live_replay_eligible",
            "upstream_attempts",
            "capture_ref",
        }
        assert projection["upstream_attempts"] == [
            attempt.as_dict() for attempt in entry.capture.upstream_attempts
        ]
    finally:
        await writer.close()


@pytest.mark.asyncio
async def test_history_archive_failure_is_visible_and_retryable(tmp_path: Path) -> None:
    writer = HistoryWriter(
        database_path=tmp_path / "history.sqlite3",
        archive=HistoryArchiveStore(tmp_path / "archive"),
    )
    await writer.start()
    entry = _entry()
    try:
        await writer.submit(entry, session_id="session-1", agent_id=None)
        await writer.wait_idle()
        indexed = await writer.get_entry(entry.request_id)
        assert indexed is not None
        archive_path = tmp_path / "archive" / indexed.archive_reference.relative_path
        original = archive_path.read_bytes()
        archive_path.write_bytes(original[:-1])

        assert await writer.archive_entry(entry.request_id) is HistoryMutation.ARCHIVING
        await writer.wait_archive_idle()
        failed = await writer.get_entry(entry.request_id)
        assert failed is not None
        assert failed.archive_state is HistoryArchiveState.ARCHIVE_FAILED
        assert failed.archive_error_code is not None
        assert failed.archived is False

        archive_path.write_bytes(original)
        assert await writer.archive_entry(entry.request_id) is HistoryMutation.ARCHIVING
        await writer.wait_archive_idle()
        archived = await writer.get_entry(entry.request_id, include_archived=True)
        assert archived is not None
        assert archived.archive_state is HistoryArchiveState.ARCHIVED
        assert archived.archived is True
    finally:
        await writer.close()


@pytest.mark.asyncio
async def test_retention_candidates_exclude_pinned_entries(tmp_path: Path) -> None:
    writer = HistoryWriter(
        database_path=tmp_path / "history.sqlite3",
        archive=HistoryArchiveStore(tmp_path / "archive"),
    )
    await writer.start()
    entry = _entry()
    try:
        await writer.submit(entry, session_id="session-1", agent_id=None)
        await writer.wait_idle()
        assert await writer.archive_entry(entry.request_id) is HistoryMutation.ARCHIVING
        await writer.wait_archive_idle()

        candidates = await writer.retention_candidates(
            finished_before="2026-09-14T00:00:00.000Z"
        )
        assert len(candidates) == 1
        assert isinstance(candidates[0], HistoryRetentionCandidate)
        assert candidates[0].entry_id == entry.request_id

        assert await writer.pin_entry(entry.request_id) is HistoryMutation.UPDATED
        assert (
            await writer.retention_candidates(
                finished_before="2026-09-14T00:00:00.000Z"
            )
            == ()
        )
    finally:
        await writer.close()
