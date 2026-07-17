import copy
import logging
import time
from collections.abc import Mapping
from typing import Any

import anyio

from app.hooks.context import HookContext
from app.hooks.registry import HookRegistry
from app.hooks.types import (
    HookErrorMode,
    ObserverEvent,
    PayloadPhase,
    ResponseHookResult,
)

logger = logging.getLogger(__name__)


class HooksExecutor:
    def __init__(self, registry: HookRegistry, *, user_timeout_ms: int) -> None:
        self.registry = registry
        self._timeout_seconds = user_timeout_ms / 1000

    def _timeout(self, name: str) -> float | None:
        return None if name.startswith("builtin:") else self._timeout_seconds

    @staticmethod
    def _record(
        records: list[dict[str, Any]] | None,
        *,
        name: str,
        hook_type: str,
        phase: str,
        started: float,
        modified: bool = False,
        error: str | None = None,
    ) -> None:
        if records is None:
            return
        records.append(
            {
                "name": name,
                "type": hook_type,
                "phase": phase,
                "duration_ms": (time.perf_counter() - started) * 1000,
                "modified": modified,
                "error": error,
            }
        )

    async def run_payload(
        self,
        phase: PayloadPhase,
        payload: dict[str, Any],
        context: HookContext,
        *,
        records: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        current = payload
        modifications: list[str] = []
        for hook in self.registry.for_phase(phase):
            started = time.perf_counter()
            try:
                with anyio.fail_after(self._timeout(hook.name)):
                    result = await hook.run(copy.deepcopy(current), context)
            except Exception as error:
                self._record(
                    records,
                    name=hook.name,
                    hook_type="payload",
                    phase=phase.value,
                    started=started,
                    error=str(error),
                )
                if hook.error_mode is HookErrorMode.CONTINUE:
                    logger.warning("payload hook %s failed: %s", hook.name, error)
                    continue
                raise
            current = result.payload
            modifications.extend(result.modifications)
            self._record(
                records,
                name=hook.name,
                hook_type="payload",
                phase=phase.value,
                started=started,
                modified=result.modified,
            )
        return current, tuple(modifications)

    async def run_response(
        self,
        body: bytes,
        status_code: int,
        context: HookContext,
        *,
        records: list[dict[str, Any]] | None = None,
    ) -> ResponseHookResult:
        current = body
        modifications: list[str] = []
        modified = False
        for hook in self.registry.response_hooks:
            started = time.perf_counter()
            try:
                with anyio.fail_after(self._timeout(hook.name)):
                    result = await hook.transform(current, status_code, context)
            except Exception as error:
                self._record(
                    records,
                    name=hook.name,
                    hook_type="response",
                    phase=ObserverEvent.RESPONSE.value,
                    started=started,
                    error=str(error),
                )
                if hook.error_mode is HookErrorMode.CONTINUE:
                    logger.warning("response hook %s failed: %s", hook.name, error)
                    continue
                raise
            current = result.body
            modified = modified or result.modified
            modifications.extend(result.modifications)
            self._record(
                records,
                name=hook.name,
                hook_type="response",
                phase=ObserverEvent.RESPONSE.value,
                started=started,
                modified=result.modified,
            )
        return ResponseHookResult(current, modified, tuple(modifications))

    async def observe(
        self,
        event: ObserverEvent,
        context: HookContext,
        data: Mapping[str, Any],
        *,
        records: list[dict[str, Any]] | None = None,
    ) -> None:
        for hook in self.registry.observers:
            if event not in hook.events:
                continue
            started = time.perf_counter()
            try:
                with anyio.fail_after(self._timeout(hook.name)):
                    await hook.observe(event, context, data)
            except Exception as error:
                logger.warning("observer hook %s failed: %s", hook.name, error)
                self._record(
                    records,
                    name=hook.name,
                    hook_type="observer",
                    phase=event.value,
                    started=started,
                    error=str(error),
                )
                continue
            self._record(
                records,
                name=hook.name,
                hook_type="observer",
                phase=event.value,
                started=started,
            )
