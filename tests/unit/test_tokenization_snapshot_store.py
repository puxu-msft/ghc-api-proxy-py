from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.tokenization.snapshot_store import (
    SnapshotRef,
    TokenizationSnapshotError,
    TokenizationSnapshotStore,
)


def _payload(value: int = 1) -> dict[str, object]:
    return {"version": 1, "calibration": {"value": value}, "prompt_limits": {}}


def test_content_addressed_snapshot_is_stable_and_idempotent(tmp_path: Path) -> None:
    store = TokenizationSnapshotStore(tmp_path)
    first = store.publish_local(
        generation="g0000000000000001",
        release="release-a",
        revision=3,
        payload=_payload(),
    )
    second = store.publish_local(
        generation="g0000000000000001",
        release="release-a",
        revision=3,
        payload=_payload(),
    )

    assert first.changed is True
    assert second.changed is False
    assert first.reference == second.reference
    assert Path(first.reference.path).read_bytes()
    assert store.load_payload(first.reference) == _payload()


def test_only_committed_generation_can_advance_canonical_pointer(tmp_path: Path) -> None:
    store = TokenizationSnapshotStore(
        tmp_path,
        canonical_path=tmp_path / "controller" / "canonical.json",
    )
    old = store.publish_local(
        generation="g0000000000000001",
        release="release-a",
        revision=1,
        payload=_payload(1),
    ).reference
    new = store.publish_local(
        generation="g0000000000000002",
        release="release-b",
        revision=2,
        payload=_payload(2),
    ).reference
    assert store.publish_canonical(
        old,
        committed_generation=old.generation,
        expected_previous_hash=None,
    ).canonical_updated

    denied = store.publish_canonical(
        old,
        committed_generation=new.generation,
        expected_previous_hash=old.sha256,
    )
    assert denied.canonical_updated is False
    assert denied.reason == "losing_generation"
    assert store.load_canonical() == old

    promoted = store.publish_canonical(
        new,
        committed_generation=new.generation,
        expected_previous_hash=old.sha256,
    )
    assert promoted.canonical_updated is True
    assert store.load_canonical() == new


def test_canonical_compare_and_swap_and_hash_validation_fail_closed(tmp_path: Path) -> None:
    store = TokenizationSnapshotStore(
        tmp_path,
        canonical_path=tmp_path / "controller" / "canonical.json",
    )
    reference = store.publish_local(
        generation="g0000000000000001",
        release="release-a",
        revision=1,
        payload=_payload(),
    ).reference
    with pytest.raises(TokenizationSnapshotError, match="compare-and-swap"):
        store.publish_canonical(
            reference,
            committed_generation=reference.generation,
            expected_previous_hash="wrong",
        )

    path = Path(reference.path)
    path.write_bytes(b"corrupt")
    with pytest.raises(TokenizationSnapshotError, match="hash mismatch"):
        store.load_payload(reference)


def test_reference_path_cannot_escape_object_store(tmp_path: Path) -> None:
    store = TokenizationSnapshotStore(tmp_path)
    reference = SnapshotRef(
        generation="g0000000000000001",
        release="release-a",
        revision=1,
        sha256="0" * 64,
        path=str(tmp_path / "outside.json"),
    )
    with pytest.raises(TokenizationSnapshotError, match="content address"):
        store.load_payload(reference)


def test_semantically_equal_payload_key_order_has_same_hash(tmp_path: Path) -> None:
    store = TokenizationSnapshotStore(tmp_path)
    first = {"version": 1, "calibration": {"a": 1, "b": 2}, "prompt_limits": {}}
    second = {"prompt_limits": {}, "calibration": {"b": 2, "a": 1}, "version": 1}
    a = store.publish_local(
        generation="g0000000000000001",
        release="release-a",
        revision=1,
        payload=first,
    )
    b = store.publish_local(
        generation="g0000000000000002",
        release="release-a",
        revision=1,
        payload=second,
    )
    assert a.reference.sha256 != b.reference.sha256  # generation identity is hash-bound

    same_generation = store.publish_local(
        generation="g0000000000000001",
        release="release-a",
        revision=1,
        payload=second,
    )
    assert same_generation.reference.sha256 == a.reference.sha256


def test_concurrent_same_object_publish_is_complete_and_idempotent(tmp_path: Path) -> None:
    store = TokenizationSnapshotStore(tmp_path)

    def publish():
        return store.publish_local(
            generation="g0000000000000001",
            release="release-a",
            revision=1,
            payload=_payload(),
        )

    def publish_index(_index: int):
        return publish()

    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = list(executor.map(publish_index, range(16)))
    assert sum(receipt.changed for receipt in receipts) == 1
    assert len({receipt.reference.sha256 for receipt in receipts}) == 1
    store.load_payload(receipts[0].reference)


def test_canonical_cas_has_single_winner_under_concurrency(tmp_path: Path) -> None:
    store = TokenizationSnapshotStore(
        tmp_path,
        canonical_path=tmp_path / "controller" / "canonical.json",
    )
    base = store.publish_local(
        generation="g0000000000000001",
        release="release-a",
        revision=1,
        payload=_payload(1),
    ).reference
    candidates = [
        store.publish_local(
            generation="g0000000000000001",
            release="release-a",
            revision=revision,
            payload=_payload(revision),
        ).reference
        for revision in (2, 3)
    ]
    store.publish_canonical(
        base,
        committed_generation=base.generation,
        expected_previous_hash=None,
    )

    def advance(reference: SnapshotRef) -> bool:
        try:
            store.publish_canonical(
                reference,
                committed_generation=reference.generation,
                expected_previous_hash=base.sha256,
            )
            return True
        except TokenizationSnapshotError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(advance, candidates))
    assert outcomes.count(True) == 1


def test_live_head_rejects_revision_rollback_and_conflict(tmp_path: Path) -> None:
    store = TokenizationSnapshotStore(tmp_path)
    store.publish_local(
        generation="g0000000000000001",
        release="release-a",
        revision=2,
        payload=_payload(2),
    )
    with pytest.raises(TokenizationSnapshotError, match="backwards"):
        store.publish_local(
            generation="g0000000000000001",
            release="release-a",
            revision=1,
            payload=_payload(1),
        )
    with pytest.raises(TokenizationSnapshotError, match="conflicting"):
        store.publish_local(
            generation="g0000000000000001",
            release="release-a",
            revision=2,
            payload=_payload(99),
        )


def test_forged_reference_metadata_and_canonical_checksum_are_rejected(tmp_path: Path) -> None:
    canonical_path = tmp_path / "controller" / "canonical.json"
    store = TokenizationSnapshotStore(tmp_path, canonical_path=canonical_path)
    reference = store.publish_local(
        generation="g0000000000000001",
        release="release-a",
        revision=1,
        payload=_payload(),
    ).reference
    forged = SnapshotRef(
        generation="g0000000000000002",
        release=reference.release,
        revision=2,
        sha256=reference.sha256,
        path=reference.path,
    )
    with pytest.raises(TokenizationSnapshotError, match="does not match envelope"):
        store.load_payload(forged)

    store.publish_canonical(
        reference,
        committed_generation=reference.generation,
        expected_previous_hash=None,
    )
    canonical_path.write_text('{"schema":1,"reference":{},"checksum":"bad"}', encoding="utf-8")
    with pytest.raises(TokenizationSnapshotError, match=r"checksum|reference"):
        store.load_canonical()
