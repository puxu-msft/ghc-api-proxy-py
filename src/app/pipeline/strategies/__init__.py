from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from app.anthropic.thinking.quarantine import QuarantineKey, ThinkingQuarantineStore
from app.anthropic.thinking.strip_all import strip_all_thinking
from app.errors import ApiError


@dataclass(frozen=True, slots=True)
class RetryDecision:
    should_retry: bool
    payload: dict[str, object]
    modifications: tuple[str, ...] = ()
    owner: str | None = None


class RetryStrategy(Protocol):
    name: str

    def can_handle(self, error: ApiError) -> bool: ...

    async def handle(
        self,
        error: ApiError,
        payload: dict[str, object],
    ) -> RetryDecision: ...


class RetryCoordinator:
    def __init__(
        self,
        strategies: Sequence[RetryStrategy],
        *,
        max_retries: int,
    ) -> None:
        self._strategies = tuple(strategies)
        self._remaining = max_retries

    async def decide(
        self,
        error: ApiError,
        payload: dict[str, object],
    ) -> RetryDecision | None:
        if self._remaining <= 0:
            return None
        for strategy in self._strategies:
            if not strategy.can_handle(error):
                continue
            decision = await strategy.handle(error, payload)
            if decision.should_retry:
                self._remaining -= 1
                return RetryDecision(
                    True,
                    decision.payload,
                    decision.modifications,
                    owner=strategy.name,
                )
            return None
        return None

    def notify_success(self) -> None:
        for strategy in self._strategies:
            callback = getattr(strategy, "on_success", None)
            if callable(callback):
                callback()


class ResponsesNetworkTransportStrategy:
    name = "responses_network_transport"

    def can_handle(self, error: ApiError) -> bool:
        return error.code == "responses_transport_error"

    async def handle(
        self,
        error: ApiError,
        payload: dict[str, object],
    ) -> RetryDecision:
        del error
        return RetryDecision(True, payload)


class PoisonedThinkingStrategy:
    name = "poisoned_thinking"

    def __init__(
        self,
        store: ThinkingQuarantineStore | None = None,
        key: QuarantineKey | None = None,
    ) -> None:
        self._attempted = False
        self._store = store
        self._key = key

    def can_handle(self, error: ApiError) -> bool:
        message = error.message.lower()
        return (
            not self._attempted
            and "cannot be modified" in message
            and ("thinking" in message or "redacted_thinking" in message)
        )

    async def handle(
        self,
        error: ApiError,
        payload: dict[str, object],
    ) -> RetryDecision:
        del error
        self._attempted = True
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return RetryDecision(False, payload)
        stripped, count = strip_all_thinking(cast(list[dict[str, Any]], messages))
        if count == 0:
            return RetryDecision(False, payload)
        return RetryDecision(
            True,
            {**payload, "messages": stripped},
            ("strip_all_thinking",),
        )

    def on_success(self) -> None:
        if self._attempted and self._store is not None and self._key is not None:
            self._store.record(self._key)


__all__ = [
    "PoisonedThinkingStrategy",
    "ResponsesNetworkTransportStrategy",
    "RetryCoordinator",
    "RetryDecision",
    "RetryStrategy",
]