from app.anthropic.thinking.quarantine import ThinkingQuarantineStore
from app.config.settings import AppSettings
from app.hooks.builtin.payload import (
    DeduplicateToolCallsHook,
    StripReadToolResultTagsHook,
    ThinkingDestackHook,
)
from app.hooks.builtin.retry import PoisonedThinkingRetryFactory
from app.hooks.builtin.token_calibration import (
    TokenCalibrationFailureObserver,
    TokenCalibrationSuccessObserver,
)
from app.hooks.registry import HookRegistryBuilder
from app.tokenization.state_store import TokenizationStateStore


def register_builtin_hooks(
    builder: HookRegistryBuilder,
    settings: AppSettings,
    *,
    quarantine: ThinkingQuarantineStore | None,
    tokenization_state: TokenizationStateStore,
) -> None:
    builder.register_payload(StripReadToolResultTagsHook(), builtin=True)
    builder.register_payload(
        ThinkingDestackHook(settings.anthropic.thinking_destack_strategy),
        builtin=True,
    )
    if settings.hooks.deduplicate_tool_calls:
        builder.register_payload(DeduplicateToolCallsHook(), builtin=True)
    builder.register_retry(
        PoisonedThinkingRetryFactory(quarantine),
        builtin=True,
    )
    builder.register_observer(
        TokenCalibrationSuccessObserver(tokenization_state),
        builtin=True,
    )
    builder.register_observer(
        TokenCalibrationFailureObserver(tokenization_state),
        builtin=True,
    )


__all__ = ["register_builtin_hooks"]
