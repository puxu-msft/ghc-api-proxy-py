from __future__ import annotations

from pathlib import Path

import pytest

from app.generation_control_client import (
    GenerationControlClientError,
    GenerationStatus,
    TokenizationFlushReceipt,
)
from app.rolling_controller import (
    ColdActivationContainedError,
    RollingController,
    RollingControllerError,
)
from app.rolling_state import GenerationRecord, RollingStateStore
from app.systemctl_adapter import UnitStatus
from app.tokenization.snapshot_store import TokenizationSnapshotStore
from app.wire_json import loads


class FakeSystemctl:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.stop_error: BaseException | None = None

    async def start_generation(self, generation_id: str) -> None:
        self.started.append(generation_id)

    async def stop_generation(self, generation_id: str) -> None:
        self.stopped.append(generation_id)
        if self.stop_error is not None:
            raise self.stop_error

    async def show_generation(self, generation_id: str) -> UnitStatus:
        return UnitStatus(
            unit=f"ghc-api-proxy-generation@{generation_id}.service",
            active_state="active",
            sub_state="running",
            main_pid=42,
            invocation_id="invocation",
            control_group=f"/ghc/{generation_id}",
        )


class FakeControls:
    def __init__(self) -> None:
        self.statuses: dict[str, GenerationStatus] = {}
        self.flush_receipt: TokenizationFlushReceipt | None = None

    async def wait_ready(self, path: Path, *, timeout: float) -> GenerationStatus:
        del timeout
        generation = path.parent.name
        try:
            return self.statuses[generation]
        except KeyError as error:
            raise FileNotFoundError(path) from error

    async def status(self, path: Path) -> GenerationStatus:
        try:
            return self.statuses[path.parent.name]
        except KeyError as error:
            raise FileNotFoundError(path) from error

    async def flush_tokenization(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> TokenizationFlushReceipt:
        if self.flush_receipt is None:
            raise RuntimeError("no flush receipt")
        return self.flush_receipt


def _status(generation: str, release: str) -> GenerationStatus:
    return GenerationStatus(
        generation=generation,
        release=release,
        pid=42,
        phase="ready_accepting",
        ready=True,
        accepting=True,
        active_operations=0,
        listener_families=("http-v4", "http-v6"),
        last_error=None,
        revision=1,
    )


def _controller(
    tmp_path: Path,
    systemctl: FakeSystemctl,
    controls: FakeControls,
) -> RollingController:
    releases = tmp_path / "releases"
    (releases / "release-a").mkdir(parents=True)
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    return RollingController(
        state_root=tmp_path / "state",
        runtime_root=tmp_path / "run",
        releases_root=releases,
        config_path=config,
        generation_state_root=tmp_path / "generation-state",
        systemctl=systemctl,  # type: ignore[arg-type]
        controls=controls,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_cold_activation_burns_id_waits_ready_and_commits_status_only(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()
    controls = FakeControls()
    controls.statuses["g0000000000000001"] = _status(
        "g0000000000000001",
        "release-a",
    )
    controller = _controller(tmp_path, systemctl, controls)

    record = await controller.cold_activate("release-a")

    assert systemctl.started == ["g0000000000000001"]
    assert record.verification_level == "status_only"
    state = RollingStateStore(tmp_path / "state" / "state.json").load()
    assert state.committed_generation == "g0000000000000001"
    env = tmp_path / "run" / "generations" / "g0000000000000001.env"
    assert env.stat().st_mode & 0o777 == 0o600
    assert 'GHC_RELEASE_ID="release-a"' in env.read_text(encoding="utf-8")
    assert env.parent.stat().st_mode & 0o777 == 0o711


def test_replace_rollout_plan_is_always_blocked_without_side_effects(tmp_path: Path) -> None:
    systemctl = FakeSystemctl()
    controls = FakeControls()
    controller = _controller(tmp_path, systemctl, controls)

    plan = controller.plan_rollout("release-a")

    assert plan.apply_enabled is False
    assert "missing_private_canary_command" in plan.blockers
    assert "apply_gate_disabled_until_stage6" in plan.blockers
    assert "quiesce_old_generation" in plan.steps
    assert systemctl.started == []
    assert not (tmp_path / "state" / "frontier").exists()


@pytest.mark.asyncio
async def test_failed_candidate_never_commits_and_is_stopped(tmp_path: Path) -> None:
    systemctl = FakeSystemctl()
    controls = FakeControls()
    controller = _controller(tmp_path, systemctl, controls)

    with pytest.raises(ColdActivationContainedError):
        await controller.cold_activate("release-a", ready_timeout=0.01)

    assert systemctl.stopped == ["g0000000000000001"]
    state = RollingStateStore(tmp_path / "state" / "state.json").load()
    assert state.committed_generation is None
    assert state.generations["g0000000000000001"].role == "failed"


@pytest.mark.asyncio
async def test_reconcile_adopts_ready_cold_candidate_after_controller_crash(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()
    controls = FakeControls()
    controller = _controller(tmp_path, systemctl, controls)
    state_store = RollingStateStore(tmp_path / "state" / "state.json")
    state = state_store.load()
    generation = "g0000000000000001"
    control = tmp_path / "run" / "generations" / generation / "control.sock"
    state.generations[generation] = GenerationRecord(
        generation_id=generation,
        release_id="release-a",
        control_socket=str(control),
        unit_name=f"ghc-api-proxy-generation@{generation}.service",
        role="candidate",
        phase="started",
        ready=False,
        accepting=False,
        pid=0,
    )
    state_store.replace(state)
    controls.statuses[generation] = _status(generation, "release-a")

    await controller.reconcile_once()

    recovered = state_store.load()
    assert recovered.committed_generation == generation
    assert recovered.generations[generation].role == "committed"


@pytest.mark.asyncio
async def test_reconcile_continues_reserved_cold_candidate_after_crash(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()
    controls = FakeControls()
    controller = _controller(tmp_path, systemctl, controls)
    state_store = RollingStateStore(tmp_path / "state" / "state.json")
    state = state_store.load()
    generation = "g0000000000000001"
    control = tmp_path / "run" / "generations" / generation / "control.sock"
    state.generations[generation] = GenerationRecord(
        generation_id=generation,
        release_id="release-a",
        control_socket=str(control),
        unit_name=f"ghc-api-proxy-generation@{generation}.service",
        role="candidate",
        phase="reserved",
        ready=False,
        accepting=False,
        pid=0,
    )
    state_store.replace(state)
    controls.statuses[generation] = _status(generation, "release-a")

    await controller.reconcile_once()

    recovered = state_store.load()
    assert systemctl.started == [generation]
    assert recovered.committed_generation == generation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_status",
    [
        _status("g0000000000000002", "release-a"),
        _status("g0000000000000001", "release-b"),
        GenerationStatus(
            generation="g0000000000000001",
            release="release-a",
            pid=42,
            phase="starting",
            ready=False,
            accepting=False,
            active_operations=0,
            listener_families=("http-v4",),
            last_error=None,
            revision=1,
        ),
    ],
)
async def test_reconcile_never_commits_unproven_candidate_identity(
    tmp_path: Path,
    bad_status: GenerationStatus,
) -> None:
    systemctl = FakeSystemctl()
    controls = FakeControls()
    controller = _controller(tmp_path, systemctl, controls)
    state_store = RollingStateStore(tmp_path / "state" / "state.json")
    state = state_store.load()
    generation = "g0000000000000001"
    control = tmp_path / "run" / "generations" / generation / "control.sock"
    state.generations[generation] = GenerationRecord(
        generation_id=generation,
        release_id="release-a",
        control_socket=str(control),
        unit_name=f"ghc-api-proxy-generation@{generation}.service",
        role="candidate",
        phase="started",
        ready=False,
        accepting=False,
        pid=0,
    )
    state_store.replace(state)
    controls.statuses[generation] = bad_status

    await controller.reconcile_once()

    recovered = state_store.load()
    assert recovered.committed_generation is None
    assert recovered.generations[generation].role == "conflict"
    assert recovered.controller_status == "degraded_conflict"


@pytest.mark.asyncio
async def test_candidate_stop_failure_is_persisted_as_conflict_and_aggregated(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()
    systemctl.stop_error = RuntimeError("stop failed")
    controls = FakeControls()
    controller = _controller(tmp_path, systemctl, controls)

    with pytest.raises(ColdActivationContainedError) as captured:
        await controller.cold_activate("release-a", ready_timeout=0.01)

    assert captured.value.__cause__ is not None
    assert "stop failed" in repr(captured.value.__cause__)
    state = RollingStateStore(tmp_path / "state" / "state.json").load()
    record = state.generations["g0000000000000001"]
    assert record.role == "conflict"
    assert state.committed_generation is None


@pytest.mark.asyncio
async def test_failed_initial_candidate_bootstraps_new_generation_id(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()
    controls = FakeControls()
    controller = _controller(tmp_path, systemctl, controls)
    with pytest.raises(ColdActivationContainedError):
        await controller.cold_activate("release-a", ready_timeout=0.01)
    controls.statuses["g0000000000000002"] = _status(
        "g0000000000000002",
        "release-a",
    )

    await controller.run_forever(
        bootstrap_release="release-a",
        once=True,
    )

    state = RollingStateStore(tmp_path / "state" / "state.json").load()
    assert state.committed_generation == "g0000000000000002"
    assert systemctl.started == [
        "g0000000000000001",
        "g0000000000000002",
    ]


@pytest.mark.asyncio
async def test_committed_identity_conflict_persists_without_breaking_commit_tuple(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()
    controls = FakeControls()
    controller = _controller(tmp_path, systemctl, controls)
    generation = "g0000000000000001"
    controls.statuses[generation] = _status(generation, "release-a")
    await controller.cold_activate("release-a")
    controls.statuses[generation] = _status("g0000000000000002", "release-a")

    await controller.reconcile_once()

    state = RollingStateStore(tmp_path / "state" / "state.json").load()
    assert state.committed_generation == generation
    assert state.generations[generation].role == "committed"
    assert state.controller_status == "degraded_conflict"
    assert generation in (state.conflict_error or "")


@pytest.mark.asyncio
async def test_controller_cancellation_does_not_stop_candidate(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()
    entered = __import__("asyncio").Event()

    class BlockingControls(FakeControls):
        async def wait_ready(self, path: Path, *, timeout: float) -> GenerationStatus:
            del path, timeout
            entered.set()
            await __import__("asyncio").Event().wait()
            raise AssertionError("unreachable")

    controls = BlockingControls()
    controller = _controller(tmp_path, systemctl, controls)
    activation = __import__("asyncio").create_task(controller.cold_activate("release-a"))
    await entered.wait()
    activation.cancel()
    with pytest.raises(__import__("asyncio").CancelledError):
        await activation

    assert systemctl.stopped == []
    state = RollingStateStore(tmp_path / "state" / "state.json").load()
    assert state.generations["g0000000000000001"].phase == "started"


@pytest.mark.asyncio
async def test_run_forever_contains_malformed_candidate_failure(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()

    class MalformedControls(FakeControls):
        async def wait_ready(self, path: Path, *, timeout: float) -> GenerationStatus:
            del path, timeout
            raise GenerationControlClientError("malformed response")

    controller = _controller(tmp_path, systemctl, MalformedControls())

    await controller.run_forever(
        bootstrap_release="release-a",
        once=True,
    )

    state = RollingStateStore(tmp_path / "state" / "state.json").load()
    assert state.committed_generation is None
    assert state.generations["g0000000000000001"].role == "failed"


@pytest.mark.asyncio
async def test_run_forever_propagates_unpersisted_bootstrap_configuration_error(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, FakeSystemctl(), FakeControls())

    with pytest.raises(RollingControllerError, match="does not exist"):
        await controller.run_forever(
            bootstrap_release="release-missing",
            once=True,
        )

    assert not (tmp_path / "state" / "state.json").exists()


@pytest.mark.asyncio
async def test_cold_generation_bootstraps_from_canonical_tokenization_snapshot(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()
    controls = FakeControls()
    controls.statuses["g0000000000000001"] = _status(
        "g0000000000000001",
        "release-a",
    )
    snapshots = TokenizationSnapshotStore(
        tmp_path / "tokenization" / "snapshots",
        canonical_path=tmp_path / "state" / "tokenization-canonical.json",
    )
    reference = snapshots.publish_local(
        generation="g0000000000000000",
        release="release-old",
        revision=3,
        payload={"version": 1, "calibration": {}, "prompt_limits": {}},
    ).reference
    snapshots.publish_canonical(
        reference,
        committed_generation=reference.generation,
        expected_previous_hash=None,
    )
    controller = _controller(tmp_path, systemctl, controls)

    await controller.cold_activate("release-a")

    local_state = (
        tmp_path
        / "generation-state"
        / "g0000000000000001"
        / "tokenization.json"
    )
    assert loads(local_state.read_bytes()) == {
        "version": 1,
        "revision": 3,
        "calibration": {},
        "prompt_limits": {},
    }


@pytest.mark.asyncio
async def test_controller_flushes_only_committed_generation_to_canonical(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()
    controls = FakeControls()
    generation = "g0000000000000001"
    controls.statuses[generation] = _status(generation, "release-a")
    controller = _controller(tmp_path, systemctl, controls)
    await controller.cold_activate("release-a")
    snapshots = TokenizationSnapshotStore(tmp_path / "tokenization" / "snapshots")
    local = snapshots.publish_local(
        generation=generation,
        release="release-a",
        revision=2,
        payload={"version": 1, "revision": 2, "calibration": {}, "prompt_limits": {}},
    ).reference
    controls.flush_receipt = TokenizationFlushReceipt(
        generation=local.generation,
        release=local.release,
        revision=local.revision,
        sha256=local.sha256,
        path=local.path,
        changed=True,
    )

    published = await controller.flush_committed_tokenization()

    assert published.canonical_updated is True
    canonical = TokenizationSnapshotStore(
        tmp_path / "tokenization" / "snapshots",
        canonical_path=tmp_path / "state" / "tokenization-canonical.json",
    ).load_canonical()
    assert canonical == local

    controls.flush_receipt = TokenizationFlushReceipt(
        generation="g0000000000000002",
        release="release-b",
        revision=3,
        sha256=local.sha256,
        path=local.path,
        changed=True,
    )
    denied = await controller.flush_committed_tokenization()
    assert denied.canonical_updated is False
    assert denied.reason == "losing_generation"


@pytest.mark.asyncio
async def test_inflight_old_flush_is_rejected_after_durable_commit_switch(
    tmp_path: Path,
) -> None:
    systemctl = FakeSystemctl()
    entered = __import__("asyncio").Event()
    release = __import__("asyncio").Event()

    class BlockingFlushControls(FakeControls):
        async def flush_tokenization(
            self,
            *_args: object,
            **_kwargs: object,
        ) -> TokenizationFlushReceipt:
            entered.set()
            await release.wait()
            assert self.flush_receipt is not None
            return self.flush_receipt

    controls = BlockingFlushControls()
    old = "g0000000000000001"
    new = "g0000000000000002"
    controls.statuses[old] = _status(old, "release-a")
    controller = _controller(tmp_path, systemctl, controls)
    await controller.cold_activate("release-a")
    snapshots = TokenizationSnapshotStore(tmp_path / "tokenization" / "snapshots")
    local = snapshots.publish_local(
        generation=old,
        release="release-a",
        revision=2,
        payload={"version": 1, "revision": 2, "calibration": {}, "prompt_limits": {}},
    ).reference
    controls.flush_receipt = TokenizationFlushReceipt(
        generation=old,
        release="release-a",
        revision=2,
        sha256=local.sha256,
        path=local.path,
        changed=True,
    )
    flushing = __import__("asyncio").create_task(
        controller.flush_committed_tokenization()
    )
    await entered.wait()

    state_store = RollingStateStore(tmp_path / "state" / "state.json")
    state = state_store.load()
    old_record = state.generations[old]
    state.generations[old] = GenerationRecord(
        generation_id=old,
        release_id="release-a",
        control_socket=old_record.control_socket,
        unit_name=old_record.unit_name,
        role="draining",
        phase="quiescing",
        ready=False,
        accepting=False,
        pid=old_record.pid,
    )
    state.generations[new] = GenerationRecord(
        generation_id=new,
        release_id="release-b",
        control_socket=str(tmp_path / "run" / "generations" / new / "control.sock"),
        unit_name=f"ghc-api-proxy-generation@{new}.service",
        role="committed",
        phase="ready_accepting",
        ready=True,
        accepting=True,
        pid=84,
    )
    state.committed_generation = new
    state.committed_release = "release-b"
    state_store.replace(state)
    release.set()

    result = await flushing

    assert result.canonical_updated is False
    assert result.reason == "losing_generation"
    assert not (tmp_path / "state" / "tokenization-canonical.json").exists()


@pytest.mark.asyncio
async def test_cancellation_during_failed_candidate_stop_propagates(
    tmp_path: Path,
) -> None:
    entered = __import__("asyncio").Event()

    class BlockingStopSystemctl(FakeSystemctl):
        async def stop_generation(self, generation_id: str) -> None:
            self.stopped.append(generation_id)
            entered.set()
            await __import__("asyncio").Event().wait()

    systemctl = BlockingStopSystemctl()

    class MalformedControls(FakeControls):
        async def wait_ready(self, path: Path, *, timeout: float) -> GenerationStatus:
            del path, timeout
            raise GenerationControlClientError("malformed response")

    controller = _controller(tmp_path, systemctl, MalformedControls())
    running = __import__("asyncio").create_task(
        controller.run_forever(bootstrap_release="release-a", once=True)
    )
    await entered.wait()
    running.cancel()
    with pytest.raises(__import__("asyncio").CancelledError):
        await running

    state = RollingStateStore(tmp_path / "state" / "state.json").load()
    assert state.controller_status == "degraded_conflict"
    assert state.generations["g0000000000000001"].role == "conflict"
