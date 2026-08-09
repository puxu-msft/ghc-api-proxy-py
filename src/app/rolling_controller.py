from __future__ import annotations

import asyncio
import fcntl
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from app.generation_control_client import (
    GenerationControlClient,
    GenerationControlClientError,
    GenerationStatus,
)
from app.release_identity import ReleaseIdentityError, parse_release_id
from app.rolling_frontier import RollingFrontierStore
from app.rolling_state import GenerationRecord, RollingState, RollingStateStore
from app.systemctl_adapter import SystemctlAdapter, UnitStatus


class RollingControllerError(RuntimeError):
    pass


class ColdActivationContainedError(RollingControllerError):
    """Cold candidate failed and durable failed/conflict evidence was recorded."""


@dataclass(frozen=True, slots=True)
class DryRunPlan:
    release_id: str
    committed_generation: str | None
    candidate_generation: str | None
    steps: tuple[str, ...]
    blockers: tuple[str, ...]
    apply_enabled: bool = False


class RollingController:
    def __init__(
        self,
        *,
        state_root: Path,
        runtime_root: Path,
        releases_root: Path,
        config_path: Path,
        systemctl: SystemctlAdapter | None = None,
        controls: GenerationControlClient | None = None,
    ) -> None:
        self._state_root = state_root
        self._runtime_root = runtime_root
        self._releases_root = releases_root
        self._config_path = config_path
        self._frontier = RollingFrontierStore(state_root / "frontier")
        self._state = RollingStateStore(state_root / "state.json")
        self._systemctl = systemctl or SystemctlAdapter()
        self._controls = controls or GenerationControlClient()
        self._lock_fd: int | None = None

    async def cold_activate(
        self,
        release_id: str,
        *,
        ready_timeout: float = 30,
    ) -> GenerationRecord:
        self._validate_release(release_id)
        state = self._state.load()
        if state.committed_generation is not None:
            raise RollingControllerError("cold activation requires an empty topology")
        generation_id = self._frontier.reserve_next(release_id=release_id)
        control_socket = self._control_socket(generation_id)
        state.generations[generation_id] = GenerationRecord(
            generation_id=generation_id,
            release_id=release_id,
            control_socket=str(control_socket),
            unit_name=f"ghc-api-proxy-generation@{generation_id}.service",
            role="candidate",
            phase="reserved",
            ready=False,
            accepting=False,
            pid=0,
        )
        self._state.replace(state)
        return await self._advance_cold_candidate(
            state,
            generation_id,
            ready_timeout=ready_timeout,
        )

    async def reconcile_once(self) -> dict[str, object]:
        state = self._state.load()
        observed: dict[str, str] = {}
        for generation_id, record in list(state.generations.items()):
            if state.committed_generation is None and record.role == "candidate":
                try:
                    committed = await self._advance_cold_candidate(
                        state,
                        generation_id,
                        ready_timeout=2,
                    )
                    observed[generation_id] = committed.phase
                except asyncio.CancelledError:
                    raise
                except BaseException:
                    observed[generation_id] = state.generations[generation_id].phase
                continue
            control_socket = Path(record.control_socket)
            try:
                status = await self._controls.status(control_socket)
                unit = await self._systemctl.show_generation(generation_id)
                self._validate_status(
                    status,
                    generation_id,
                    record.release_id,
                    unit=unit,
                )
                state.generations[generation_id] = self._record(
                    status,
                    control_socket=control_socket,
                    role=record.role,
                )
                observed[generation_id] = status.phase
            except RollingControllerError as error:
                state.controller_status = "degraded_conflict"
                state.conflict_error = f"{generation_id}: {error}"
                observed[generation_id] = "conflict"
            except (OSError, TimeoutError, GenerationControlClientError):
                unit = await self._systemctl.show_generation(generation_id)
                observed[generation_id] = unit.active_state
        self._state.replace(state)
        return {
            "committed_generation": state.committed_generation,
            "observed": observed,
            "apply_enabled": state.apply_enabled,
            "blockers": state.apply_blockers,
        }

    async def _advance_cold_candidate(
        self,
        state: RollingState,
        generation_id: str,
        *,
        ready_timeout: float,
    ) -> GenerationRecord:
        record = state.generations[generation_id]
        control_socket = Path(record.control_socket)
        try:
            if record.phase == "reserved":
                self._write_generation_environment(
                    generation_id,
                    record.release_id,
                    control_socket,
                )
                record = self._phase_record(record, "environment_ready")
                state.generations[generation_id] = record
                self._state.replace(state)
            if record.phase == "environment_ready":
                await self._systemctl.start_generation(generation_id)
                record = self._phase_record(record, "started")
                state.generations[generation_id] = record
                self._state.replace(state)
            if record.phase != "started":
                raise RollingControllerError(
                    f"cold candidate cannot advance from phase {record.phase!r}"
                )
            status = await self._controls.wait_ready(
                control_socket,
                timeout=ready_timeout,
            )
            unit = await self._systemctl.show_generation(generation_id)
            self._validate_status(
                status,
                generation_id,
                record.release_id,
                unit=unit,
            )
            committed = self._record(
                status,
                control_socket=control_socket,
                role="committed",
            )
            state.committed_generation = generation_id
            state.committed_release = record.release_id
            state.generations[generation_id] = committed
            self._state.replace(state)
            return committed
        except asyncio.CancelledError:
            raise
        except BaseException as primary_error:
            if state.committed_generation == generation_id:
                state.committed_generation = None
                state.committed_release = None
            cleanup_errors: list[BaseException] = []
            try:
                await self._systemctl.stop_generation(generation_id)
            except asyncio.CancelledError:
                state.controller_status = "degraded_conflict"
                state.conflict_error = (
                    f"{generation_id}: controller cancelled during candidate stop"
                )
                state.generations[generation_id] = GenerationRecord(
                    generation_id=generation_id,
                    release_id=record.release_id,
                    control_socket=str(control_socket),
                    unit_name=record.unit_name,
                    role="conflict",
                    phase="conflict",
                    ready=False,
                    accepting=False,
                    pid=0,
                    last_error=f"{type(primary_error).__name__}: {primary_error}",
                )
                self._state.replace(state)
                raise
            except BaseException as stop_error:
                cleanup_errors.append(stop_error)
            semantic_conflict = isinstance(primary_error, RollingControllerError)
            role = "conflict" if semantic_conflict or cleanup_errors else "failed"
            state.generations[generation_id] = GenerationRecord(
                generation_id=generation_id,
                release_id=record.release_id,
                control_socket=str(control_socket),
                unit_name=record.unit_name,
                role=role,
                phase=role,
                ready=False,
                accepting=False,
                pid=0,
                last_error=f"{type(primary_error).__name__}: {primary_error}",
            )
            if role == "conflict":
                state.controller_status = "degraded_conflict"
                state.conflict_error = f"{generation_id}: {primary_error}"
            self._state.replace(state)
            if cleanup_errors:
                causes = BaseExceptionGroup(
                    "cold activation and candidate stop failed",
                    [primary_error, *cleanup_errors],
                )
                raise ColdActivationContainedError(
                    f"cold generation {generation_id} entered conflict"
                ) from causes
            raise ColdActivationContainedError(
                f"cold generation {generation_id} failed"
            ) from primary_error

    @staticmethod
    def _phase_record(record: GenerationRecord, phase: str) -> GenerationRecord:
        return GenerationRecord(
            generation_id=record.generation_id,
            release_id=record.release_id,
            control_socket=record.control_socket,
            unit_name=record.unit_name,
            role=record.role,
            phase=phase,
            ready=False,
            accepting=False,
            pid=record.pid,
            last_error=record.last_error,
            verification_level=record.verification_level,
        )

    def plan_rollout(self, release_id: str) -> DryRunPlan:
        self._validate_release(release_id)
        state = self._state.load()
        steps = (
            "reserve_generation_id",
            "write_generation_environment",
            "start_candidate",
            "wait_candidate_ready",
            "run_private_canary",
            "quiesce_old_generation",
            "run_shared_dual_stack_canary",
            "publish_snapshot_and_promote",
            "commit_rollout_tuple",
        )
        return DryRunPlan(
            release_id=release_id,
            committed_generation=state.committed_generation,
            candidate_generation=None,
            steps=steps,
            blockers=tuple(state.apply_blockers),
        )

    async def run_forever(
        self,
        *,
        bootstrap_release: str | None,
        interval: float = 2,
        once: bool = False,
    ) -> None:
        self._acquire_lock()
        try:
            state = self._state.load()
            if bootstrap_release and self._can_bootstrap(state):
                await self._try_bootstrap(bootstrap_release)
            while True:
                await self.reconcile_once()
                if once:
                    return
                state = self._state.load()
                if bootstrap_release and self._can_bootstrap(state):
                    await self._try_bootstrap(bootstrap_release)
                await asyncio.sleep(interval)
        finally:
            self._release_lock()

    def _write_generation_environment(
        self,
        generation_id: str,
        release_id: str,
        control_socket: Path,
    ) -> None:
        directory = self._runtime_root / "generations"
        directory.mkdir(parents=True, exist_ok=True, mode=0o711)
        directory.chmod(0o711)
        state_directory = Path("/var/lib/ghc-api-proxy/generations") / generation_id
        lines = {
            "GHC_GENERATION_ID": generation_id,
            "GHC_RELEASE_ID": release_id,
            "GHC_RELEASE_ROOT": str(self._releases_root / release_id),
            "GHC_CONTROL_SOCKET": str(control_socket),
            "GHC_CONFIG": str(self._config_path),
            "GHC_HISTORY__DB_PATH": str(state_directory / "history.db"),
            "GHC_TOKENIZATION__STATE_PATH": str(state_directory / "tokenization.json"),
        }
        content = "".join(
            f"{key}={self._quote_environment_value(value)}\n"
            for key, value in lines.items()
        ).encode()
        destination = directory / f"{generation_id}.env"
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=directory)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(0o600)
            temporary.replace(destination)
            directory_fd = os.open(directory, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    def _control_socket(self, generation_id: str) -> Path:
        return self._runtime_root / "generations" / generation_id / "control.sock"

    @staticmethod
    def _quote_environment_value(value: str) -> str:
        if "\n" in value or "\r" in value or "\0" in value:
            raise RollingControllerError("generation environment contains an invalid value")
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    @staticmethod
    def _validate_status(
        status: GenerationStatus,
        generation_id: str,
        release_id: str,
        *,
        unit: UnitStatus,
    ) -> None:
        if status.generation != generation_id or status.release != release_id:
            raise RollingControllerError("candidate control identity mismatch")
        if not status.ready or not status.accepting:
            raise RollingControllerError("candidate is not ready and accepting")
        if status.phase != "ready_accepting":
            raise RollingControllerError("candidate phase is not ready_accepting")
        if set(status.listener_families) != {"http-v4", "http-v6"}:
            raise RollingControllerError("candidate listener families are incomplete")
        if unit.active_state != "active" or unit.main_pid != status.pid:
            raise RollingControllerError("candidate systemd identity does not match control status")

    @staticmethod
    def _record(
        status: GenerationStatus,
        *,
        control_socket: Path,
        role: str,
    ) -> GenerationRecord:
        return GenerationRecord(
            generation_id=status.generation,
            release_id=status.release,
            control_socket=str(control_socket),
            unit_name=f"ghc-api-proxy-generation@{status.generation}.service",
            role=role,
            phase=status.phase,
            ready=status.ready,
            accepting=status.accepting,
            pid=status.pid,
            last_error=status.last_error,
        )

    def _validate_release(self, release_id: str) -> None:
        try:
            parse_release_id(release_id)
        except ReleaseIdentityError as error:
            raise RollingControllerError(str(error)) from error
        release_root = self._releases_root / release_id
        if not release_root.is_dir() or release_root.is_symlink():
            raise RollingControllerError(f"release directory does not exist: {release_root}")
        if release_root.resolve().parent != self._releases_root.resolve():
            raise RollingControllerError("release directory escapes releases root")
        if not self._config_path.is_absolute():
            raise RollingControllerError("config path must be absolute")

    @staticmethod
    def _can_bootstrap(state: RollingState) -> bool:
        if state.committed_generation is not None or state.controller_status != "normal":
            return False
        return not state.generations or all(
            record.role == "failed" for record in state.generations.values()
        )

    def _acquire_lock(self) -> None:
        self._state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self._state_root / "controller.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(fd)
            raise RollingControllerError(f"controller lock is held: {path}") from error
        self._lock_fd = fd

    def _release_lock(self) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    async def _try_bootstrap(self, release_id: str) -> None:
        try:
            await self.cold_activate(release_id)
        except asyncio.CancelledError:
            raise
        except ColdActivationContainedError:
            return


def plan_to_json(plan: DryRunPlan) -> str:
    return json.dumps(asdict(plan), sort_keys=True)
