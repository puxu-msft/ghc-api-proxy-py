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
