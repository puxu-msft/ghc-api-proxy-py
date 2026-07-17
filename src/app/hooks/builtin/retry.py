from dataclasses import dataclass

from app.anthropic.thinking.quarantine import (
    QuarantineKey,
    ThinkingQuarantineStore,
)
from app.hooks.context import HookContext
from app.pipeline.strategies import PoisonedThinkingStrategy, RetryStrategy


@dataclass(frozen=True, slots=True)
class PoisonedThinkingRetryFactory:
    store: ThinkingQuarantineStore | None
    name: str = "builtin:poisoned_thinking"
    order: int = 500

    def create(self, context: HookContext) -> RetryStrategy:
        key = (
            QuarantineKey(context.session_id, context.agent_id or "")
            if context.session_id
            else None
        )
        return PoisonedThinkingStrategy(self.store, key)
