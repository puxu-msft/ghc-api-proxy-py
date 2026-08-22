from dataclasses import FrozenInstanceError, dataclass

import pytest

from app.config.settings import AppSettings
from app.hooks.context import HookContext
from app.hooks.registry import HookRegistryBuilder
from app.hooks.types import HookErrorMode, PayloadHookResult, PayloadPhase


@dataclass(frozen=True)
class StubPayloadHook:
    name: str
    order: int
    phase: PayloadPhase = PayloadPhase.POST_SANITIZE
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def run(
        self,
        payload: dict[str, object],
        context: HookContext,
    ) -> PayloadHookResult:
        del context
        return PayloadHookResult(dict(payload))


def test_registry_orders_hooks_and_freezes_builder() -> None:
    builder = HookRegistryBuilder()
    builder.register_payload(StubPayloadHook("z", 1002))
    builder.register_payload(StubPayloadHook("a", 1001))

    registry = builder.build()

    assert [hook.name for hook in registry.for_phase(PayloadPhase.POST_SANITIZE)] == [
        "a",
        "z",
    ]
    with pytest.raises(RuntimeError, match="finalized"):
        builder.register_payload(StubPayloadHook("later", 1003))


def test_registry_enforces_namespaces_orders_and_uniqueness() -> None:
    builder = HookRegistryBuilder()
    with pytest.raises(ValueError, match="order"):
        builder.register_payload(StubPayloadHook("user", 999))
    with pytest.raises(ValueError, match=r"builtin:\*"):
        builder.register_payload(StubPayloadHook("builtin:fake", 1000))

    builder.register_payload(StubPayloadHook("user", 1000))
    with pytest.raises(ValueError, match="duplicate"):
        builder.register_payload(StubPayloadHook("user", 1001))


def test_disabled_hook_is_absent() -> None:
    builder = HookRegistryBuilder(disabled=("builtin:test",))
    builder.register_payload(
        StubPayloadHook("builtin:test", 1),
        builtin=True,
    )

    assert builder.build().for_phase(PayloadPhase.POST_SANITIZE) == ()


def test_hook_context_is_frozen() -> None:
    context = HookContext(
        request_id="request",
        endpoint="anthropic-messages",
        protocol="anthropic",
        original_model="alias",
        resolved_model="model",
        session_id=None,
        agent_id=None,
        attempt_number=0,
        settings=AppSettings(),
    )

    attribute = "attempt_number"
    with pytest.raises(FrozenInstanceError):
        setattr(context, attribute, 1)
