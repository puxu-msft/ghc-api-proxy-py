from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ApprovalLifecycle(Protocol):
    async def quiesce(self, reason: str = "server_restarting") -> int: ...

    async def resume(self) -> None: ...


class ObserverLifecycle(Protocol):
    async def close_topics(
        self,
        topics: set[str],
        *,
        code: int,
        reason: str,
    ) -> int: ...

    def reopen_topics(self, topics: set[str]) -> None: ...


class GenerationPhase(StrEnum):
    STARTING = "starting"
    READY_ACCEPTING = "ready_accepting"
    QUIESCING = "quiescing"
    DRAINED_STANDBY = "drained_standby"
    STOPPING = "stopping"
    FAILED = "failed"


class GenerationLifecycleError(RuntimeError):
    """Raised when a generation phase transition is not legal."""


@dataclass(frozen=True, slots=True)
class GenerationSnapshot:
    phase: GenerationPhase
    accepting: bool
    active_operations: int
    revision: int
    last_error: str | None


class GenerationLifecycle:
    def __init__(self) -> None:
        self._phase = GenerationPhase.STARTING
        self._active_operations = 0
        self._operation_tasks: set[asyncio.Task[object]] = set()
        self._admission_open = False
        self._condition = asyncio.Condition()
        self._transition_lock = asyncio.Lock()
        self._revision = 0
        self._last_error: str | None = None

    @property
    def phase(self) -> GenerationPhase:
        return self._phase

    @property
    def accepting(self) -> bool:
        return self._admission_open

    @property
    def active_operations(self) -> int:
        return self._active_operations

    async def snapshot(self) -> GenerationSnapshot:
        async with self._condition:
            return self._snapshot_locked()

    async def wait_for_change(
        self,
        after_revision: int,
        timeout: float | None,
    ) -> GenerationSnapshot:
        async def wait() -> GenerationSnapshot:
            async with self._condition:
                await self._condition.wait_for(lambda: self._revision > after_revision)
                return self._snapshot_locked()

        if timeout is None:
            return await wait()
        async with asyncio.timeout(timeout):
            return await wait()

    async def mark_ready(self) -> None:
        async with self._transition_lock, self._condition:
            if self._phase is not GenerationPhase.STARTING:
                raise GenerationLifecycleError(
                    f"ready requires starting phase, got {self._phase}"
                )
            self._phase = GenerationPhase.READY_ACCEPTING
            self._admission_open = True
            self._advance_locked()
            self._condition.notify_all()

    async def quiesce(
        self,
        approval_gate: ApprovalLifecycle | None = None,
        observers: ObserverLifecycle | None = None,
    ) -> None:
        task = asyncio.create_task(self._quiesce(approval_gate, observers))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def _quiesce(
        self,
        approval_gate: ApprovalLifecycle | None,
        observers: ObserverLifecycle | None,
    ) -> None:
        async with self._transition_lock:
            async with self._condition:
                if self._phase in {
                    GenerationPhase.QUIESCING,
                    GenerationPhase.DRAINED_STANDBY,
                }:
                    if approval_gate is not None:
                        await approval_gate.quiesce("server_restarting")
                    return
                if self._phase is not GenerationPhase.READY_ACCEPTING:
                    raise GenerationLifecycleError(
                        f"quiesce requires accepting phase, got {self._phase}"
                    )
                self._phase = GenerationPhase.QUIESCING
                self._admission_open = False
                self._advance_locked()
                self._condition.notify_all()
            try:
                if approval_gate is not None:
                    await approval_gate.quiesce("server_restarting")
                if observers is not None:
                    await observers.close_topics(
                        {"history", "approval"},
                        code=1012,
                        reason="server_restarting",
                    )
            except BaseException:
                async with self._condition:
                    self._phase = GenerationPhase.FAILED
                    self._last_error = "generation quiesce failed"
                    self._advance_locked()
                    self._condition.notify_all()
                raise

    async def resume(
        self,
        approval_gate: ApprovalLifecycle | None = None,
        observers: ObserverLifecycle | None = None,
    ) -> None:
        task = asyncio.create_task(self._resume(approval_gate, observers))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def _resume(
        self,
        approval_gate: ApprovalLifecycle | None,
        observers: ObserverLifecycle | None,
    ) -> None:
        async with self._transition_lock:
            async with self._condition:
                if self._phase is GenerationPhase.READY_ACCEPTING:
                    return
                if self._phase not in {
                    GenerationPhase.QUIESCING,
                    GenerationPhase.DRAINED_STANDBY,
                }:
                    raise GenerationLifecycleError(
                        f"resume requires quiescing or standby phase, got {self._phase}"
                    )
            if approval_gate is not None:
                await approval_gate.resume()
            if observers is not None:
                observers.reopen_topics({"history", "approval"})
            async with self._condition:
                self._phase = GenerationPhase.READY_ACCEPTING
                self._admission_open = True
                self._advance_locked()
                self._condition.notify_all()

    async def start_stopping(self) -> None:
        async with self._transition_lock, self._condition:
            if self._phase in {GenerationPhase.STOPPING, GenerationPhase.FAILED}:
                return
            self._phase = GenerationPhase.STOPPING
            self._admission_open = False
            self._advance_locked()
            self._condition.notify_all()

    async def wait_for_drained(self) -> None:
        async with self._condition:
            await self._condition.wait_for(
                lambda: self._active_operations == 0
                or self._phase is GenerationPhase.STOPPING
            )

    async def cancel_active_operations(self) -> int:
        async with self._condition:
            tasks = tuple(self._operation_tasks)
        for task in tasks:
            task.cancel("generation drain timeout exceeded")
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return len(tasks)

    async def mark_failed(self, error: BaseException) -> None:
        async with self._transition_lock, self._condition:
            self._phase = GenerationPhase.FAILED
            self._admission_open = False
            self._last_error = f"{type(error).__name__}: {error}"
            self._advance_locked()
            self._condition.notify_all()

    async def mark_drained(self) -> None:
        async with self._transition_lock, self._condition:
            if self._phase is not GenerationPhase.QUIESCING:
                raise GenerationLifecycleError(
                    f"drained requires quiescing phase, got {self._phase}"
                )
            if self._active_operations != 0:
                raise GenerationLifecycleError("cannot mark drained with active operations")
            self._phase = GenerationPhase.DRAINED_STANDBY
            self._advance_locked()
            self._condition.notify_all()

    @asynccontextmanager
    async def try_admit(self) -> AsyncGenerator[bool]:
        async with self._condition:
            admitted = self._admission_open
            if admitted:
                self._active_operations += 1
                task = asyncio.current_task()
                if task is not None:
                    self._operation_tasks.add(task)
                self._advance_locked()
                self._condition.notify_all()
        try:
            yield admitted
        finally:
            if admitted:
                async with self._condition:
                    self._active_operations -= 1
                    task = asyncio.current_task()
                    if task is not None:
                        self._operation_tasks.discard(task)
                    self._advance_locked()
                    self._condition.notify_all()

    def _snapshot_locked(self) -> GenerationSnapshot:
        return GenerationSnapshot(
            phase=self._phase,
            accepting=self._admission_open,
            active_operations=self._active_operations,
            revision=self._revision,
            last_error=self._last_error,
        )

    def _advance_locked(self) -> None:
        self._revision += 1
