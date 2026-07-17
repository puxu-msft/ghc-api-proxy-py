from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import pytest

from app.config.settings import AppSettings
from app.hooks.context import HookContext
from app.hooks.executor import HooksExecutor
from app.hooks.registry import HookRegistryBuilder
from app.hooks.types import (
    HookErrorMode,
    ObserverEvent,
    PayloadHookResult,
    PayloadPhase,
)


@dataclass(frozen=True)
class AppendHook:
    name: str
    order: int
    value: str
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST
    phase: PayloadPhase = PayloadPhase.PRE_SEND

    async def run(
        self,
        payload: dict[str, Any],
        context: HookContext,
    ) -> PayloadHookResult:
        raw_values: object = payload.get("values", [])
        values = list(cast(list[str], raw_values))
        values.append(f"{context.attempt_number}:{self.value}")
        return PayloadHookResult({**payload, "values": values}, True, (self.value,))


@dataclass(frozen=True)
class FailingObserver:
    name: str = "observer"
    order: int = 1000
    events: frozenset[ObserverEvent] = frozenset({ObserverEvent.ERROR})

    async def observe(
        self,
        event: ObserverEvent,
        context: HookContext,
        data: Mapping[str, Any],
    ) -> None:
        del event, context, data
        raise RuntimeError("observer failed")


@dataclass(frozen=True)
class MutatingFailingHook:
    name: str = "mutating"
    order: int = 1000
    phase: PayloadPhase = PayloadPhase.PRE_SEND
    error_mode: HookErrorMode = HookErrorMode.CONTINUE

    async def run(
        self,
        payload: dict[str, Any],
        context: HookContext,
    ) -> PayloadHookResult:
        del context
        payload["leaked"] = True
        raise RuntimeError("payload hook failed")


def _context(attempt: int = 0) -> HookContext:
    return HookContext(
        request_id="request",
        endpoint="anthropic-messages",
        protocol="anthropic",
        original_model="model",
        resolved_model="model",
        session_id=None,
        agent_id=None,
        attempt_number=attempt,
        settings=AppSettings(),
    )


@pytest.mark.asyncio
async def test_payload_hooks_run_in_deterministic_order() -> None:
    builder = HookRegistryBuilder()
    builder.register_payload(AppendHook("second", 1002, "second"))
    builder.register_payload(AppendHook("first", 1001, "first"))
    executor = HooksExecutor(builder.build(), user_timeout_ms=1000)

    payload, modifications = await executor.run_payload(
        PayloadPhase.PRE_SEND,
        {},
        _context(3),
    )

    assert payload == {"values": ["3:first", "3:second"]}
    assert modifications == ("first", "second")


@pytest.mark.asyncio
async def test_observer_failure_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    builder = HookRegistryBuilder()
    builder.register_observer(FailingObserver())
    executor = HooksExecutor(builder.build(), user_timeout_ms=1000)

    await executor.observe(ObserverEvent.ERROR, _context(), {})

    assert "observer failed" in caplog.text


@pytest.mark.asyncio
async def test_continue_hook_cannot_leak_in_place_mutation() -> None:
    builder = HookRegistryBuilder()
    builder.register_payload(MutatingFailingHook())
    executor = HooksExecutor(builder.build(), user_timeout_ms=1000)

    payload, _ = await executor.run_payload(
        PayloadPhase.PRE_SEND,
        {"original": True},
        _context(),
    )

    assert payload == {"original": True}
