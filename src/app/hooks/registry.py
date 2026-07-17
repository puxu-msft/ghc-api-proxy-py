from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from app.hooks.types import (
    ObserverHook,
    PayloadHook,
    PayloadPhase,
    ResponseHook,
    RetryStrategyFactory,
)


@dataclass(frozen=True, slots=True)
class HookRegistry:
    payload_hooks: Mapping[PayloadPhase, tuple[PayloadHook, ...]]
    retry_factories: tuple[RetryStrategyFactory, ...]
    response_hooks: tuple[ResponseHook, ...]
    observers: tuple[ObserverHook, ...]

    def for_phase(self, phase: PayloadPhase) -> tuple[PayloadHook, ...]:
        return self.payload_hooks.get(phase, ())


class HookRegistryBuilder:
    def __init__(self, *, disabled: tuple[str, ...] = ()) -> None:
        self._disabled = frozenset(disabled)
        self._names: set[str] = set()
        self._payload: dict[PayloadPhase, list[PayloadHook]] = {
            phase: [] for phase in PayloadPhase
        }
        self._retry: list[RetryStrategyFactory] = []
        self._response: list[ResponseHook] = []
        self._observers: list[ObserverHook] = []
        self._built = False

    def _register_name(self, name: str, order: int, *, builtin: bool) -> bool:
        if self._built:
            raise RuntimeError("hook registry builder is already finalized")
        if not name or name in self._names:
            raise ValueError(f"duplicate or empty hook name: {name}")
        if builtin:
            if not name.startswith("builtin:") or not 0 <= order <= 999:
                raise ValueError("built-in hooks require builtin:* names and order 0..999")
        elif name.startswith("builtin:") or order < 1000:
            raise ValueError("user hooks cannot use builtin:* and require order >= 1000")
        self._names.add(name)
        return name not in self._disabled

    def register_payload(self, hook: PayloadHook, *, builtin: bool = False) -> None:
        if self._register_name(hook.name, hook.order, builtin=builtin):
            self._payload[hook.phase].append(hook)

    def register_retry(
        self,
        factory: RetryStrategyFactory,
        *,
        builtin: bool = False,
    ) -> None:
        if self._register_name(factory.name, factory.order, builtin=builtin):
            self._retry.append(factory)

    def register_response(self, hook: ResponseHook, *, builtin: bool = False) -> None:
        if self._register_name(hook.name, hook.order, builtin=builtin):
            self._response.append(hook)

    def register_observer(self, hook: ObserverHook, *, builtin: bool = False) -> None:
        if self._register_name(hook.name, hook.order, builtin=builtin):
            self._observers.append(hook)

    def build(self) -> HookRegistry:
        if self._built:
            raise RuntimeError("hook registry builder is already finalized")
        self._built = True
        payload = {
            phase: tuple(sorted(hooks, key=lambda hook: (hook.order, hook.name)))
            for phase, hooks in self._payload.items()
        }
        return HookRegistry(
            payload_hooks=cast(
                Mapping[PayloadPhase, tuple[PayloadHook, ...]],
                MappingProxyType(payload),
            ),
            retry_factories=tuple(
                sorted(self._retry, key=lambda hook: (hook.order, hook.name))
            ),
            response_hooks=tuple(
                sorted(self._response, key=lambda hook: (hook.order, hook.name))
            ),
            observers=tuple(
                sorted(self._observers, key=lambda hook: (hook.order, hook.name))
            ),
        )
