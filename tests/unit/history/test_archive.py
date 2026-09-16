from __future__ import annotations

from pathlib import Path

import pytest

from app.history.archive import HistoryArchiveStore


def test_history_archive_round_trips_payload_and_reference(tmp_path: Path) -> None:
    store = HistoryArchiveStore(tmp_path, max_segment_bytes=256)

    reference = store.append(
        session_id="session-1",
        agent_id="agent-1",
        entry_id="request-1",
        payload={"outcome": "completed", "semantic": {"text": "hello"}},
    )

    assert reference.entry_id == "request-1"
    assert reference.relative_path.endswith(".history.cborseq.zst")
    assert store.read(reference)["payload"] == {
        "outcome": "completed",
        "semantic": {"text": "hello"},
    }


def test_history_archive_round_trips_credential_bearing_transport_envelope(
    tmp_path: Path,
) -> None:
    store = HistoryArchiveStore(tmp_path)
    transport = b"\x28\xb5\x2f\xfdtransport"

    reference = store.append(
        session_id="session-transport",
        agent_id=None,
        entry_id="request-transport",
        payload={"outcome": "completed"},
        transport=transport,
    )

    assert store.read_transport(reference) == transport
    record = store.read(reference)
    assert record["transport_media_type"] == "application/cbor-seq+zstd"
    assert record["transport_contains_credentials"] is True


def test_history_archive_rolls_over_and_keeps_previous_segment_readable(
    tmp_path: Path,
) -> None:
    store = HistoryArchiveStore(tmp_path, max_segment_bytes=1)

    first = store.append(
        session_id="session-1",
        agent_id=None,
        entry_id="request-1",
        payload={"value": "one"},
    )
    second = store.append(
        session_id="session-1",
        agent_id=None,
        entry_id="request-2",
        payload={"value": "two"},
    )

    assert first.relative_path != second.relative_path
    assert store.read(first)["entry_id"] == "request-1"
    assert store.read(second)["entry_id"] == "request-2"


def test_history_archive_restores_existing_segment_before_appending(tmp_path: Path) -> None:
    original = HistoryArchiveStore(tmp_path)
    first = original.append(
        session_id="session-restart",
        agent_id="agent-restart",
        entry_id="request-1",
        payload={"value": "one"},
    )

    restarted = HistoryArchiveStore(tmp_path)
    second = restarted.append(
        session_id="session-restart",
        agent_id="agent-restart",
        entry_id="request-2",
        payload={"value": "two"},
    )

    assert second.relative_path == first.relative_path
    assert second.offset == first.length
    assert restarted.read(first)["payload"] == {"value": "one"}
    assert restarted.read(second)["payload"] == {"value": "two"}


def test_history_archive_scans_existing_segments_and_rotates_from_full_latest_segment(
    tmp_path: Path,
) -> None:
    original = HistoryArchiveStore(tmp_path, max_segment_bytes=1)
    first = original.append(
        session_id="session-rotation",
        agent_id=None,
        entry_id="request-1",
        payload={"value": "one"},
    )
    second = original.append(
        session_id="session-rotation",
        agent_id=None,
        entry_id="request-2",
        payload={"value": "two"},
    )

    restarted = HistoryArchiveStore(tmp_path, max_segment_bytes=second.length)
    third = restarted.append(
        session_id="session-rotation",
        agent_id=None,
        entry_id="request-3",
        payload={"value": "three"},
    )

    assert first.relative_path.endswith("history-000000.history.cborseq.zst")
    assert second.relative_path.endswith("history-000001.history.cborseq.zst")
    assert third.relative_path.endswith("history-000002.history.cborseq.zst")
    assert restarted.read(first)["entry_id"] == "request-1"
    assert restarted.read(second)["entry_id"] == "request-2"
    assert restarted.read(third)["entry_id"] == "request-3"


def test_history_archive_refuses_to_append_after_truncated_existing_tail(tmp_path: Path) -> None:
    original = HistoryArchiveStore(tmp_path)
    reference = original.append(
        session_id="session-corrupt",
        agent_id=None,
        entry_id="request-1",
        payload={"value": "safe"},
    )
    path = tmp_path / reference.relative_path
    corrupted = path.read_bytes() + b"\x28\xb5"
    path.write_bytes(corrupted)

    restarted = HistoryArchiveStore(tmp_path)

    with pytest.raises(ValueError, match="not safe to append"):
        restarted.append(
            session_id="session-corrupt",
            agent_id=None,
            entry_id="request-2",
            payload={"value": "must not overwrite"},
        )

    assert path.read_bytes() == corrupted
    assert restarted.read(reference)["payload"] == {"value": "safe"}


def test_history_archive_rejects_tampered_frame(tmp_path: Path) -> None:
    store = HistoryArchiveStore(tmp_path)
    reference = store.append(
        session_id="session-1",
        agent_id="agent-1",
        entry_id="request-1",
        payload={"value": "safe"},
    )
    path = tmp_path / reference.relative_path
    data = bytearray(path.read_bytes())
    data[reference.offset] ^= 0x01
    path.write_bytes(data)

    with pytest.raises(ValueError, match="digest mismatch"):
        store.read(reference)
