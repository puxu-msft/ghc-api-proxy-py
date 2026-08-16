from pathlib import Path

import pytest

from app.lifecycle.rolling.frontier import RollingFrontierError, RollingFrontierStore


def test_frontier_burns_monotonic_ids_and_recovers_from_one_bad_copy(tmp_path: Path) -> None:
    store = RollingFrontierStore(tmp_path)
    assert store.reserve_next(release_id="r1") == "g0000000000000001"
    assert store.reserve_next(release_id="r2") == "g0000000000000002"
    (tmp_path / "frontier-a.json").write_text("broken", encoding="utf-8")

    recovered = RollingFrontierStore(tmp_path)
    assert recovered.high_watermark() == 2
    assert recovered.reserve_next(release_id="r3") == "g0000000000000003"


def test_frontier_fails_closed_when_all_evidence_is_corrupt(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "frontier-a.json").write_text("broken", encoding="utf-8")
    (tmp_path / "allocations.jsonl").write_text("broken", encoding="utf-8")

    with pytest.raises(RollingFrontierError, match=r"corrupt|cannot prove"):
        RollingFrontierStore(tmp_path).reserve_next(release_id="r1")


def test_frontier_fails_closed_when_latest_allocation_fact_is_corrupt(
    tmp_path: Path,
) -> None:
    store = RollingFrontierStore(tmp_path)
    store.reserve_next(release_id="r1")
    store.reserve_next(release_id="r2")
    lines = (tmp_path / "allocations.jsonl").read_text(encoding="utf-8").splitlines()
    lines[-1] = "broken-latest-fact"
    (tmp_path / "allocations.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "frontier-a.json").write_text("broken", encoding="utf-8")

    with pytest.raises(RollingFrontierError, match="facts are corrupt"):
        store.reserve_next(release_id="r3")


def test_initialized_frontier_missing_facts_never_uses_stale_copy(tmp_path: Path) -> None:
    store = RollingFrontierStore(tmp_path)
    store.reserve_next(release_id="r1")
    stale_copy = (tmp_path / "frontier-b.json").read_bytes()
    store.reserve_next(release_id="r2")
    (tmp_path / "frontier-a.json").write_text("broken", encoding="utf-8")
    (tmp_path / "frontier-b.json").write_bytes(stale_copy)
    (tmp_path / "allocations.jsonl").unlink()

    with pytest.raises(RollingFrontierError, match="missing allocation facts"):
        store.reserve_next(release_id="r3")
