from app.errors import ApiError, ErrorCategory
from app.pipeline.strategies import (
    PoisonedThinkingStrategy,
    RetryCoordinator,
    RetryDecision,
)


class AlwaysStrategy:
    name = "always"

    def can_handle(self, error: ApiError) -> bool:
        return True

    async def handle(self, error: ApiError, payload: dict[str, object]) -> RetryDecision:
        return RetryDecision(True, {**payload, "handled": True}, ("handled",))


class ShouldNotRun(AlwaysStrategy):
    name = "second"

    def __init__(self) -> None:
        self.called = False

    async def handle(self, error: ApiError, payload: dict[str, object]) -> RetryDecision:
        self.called = True
        return await super().handle(error, payload)


async def test_retry_coordinator_selects_single_owner_and_budget() -> None:
    second = ShouldNotRun()
    coordinator = RetryCoordinator([AlwaysStrategy(), second], max_retries=1)
    error = ApiError("temporary", category=ErrorCategory.UPSTREAM, status_code=503)

    first = await coordinator.decide(error, {"x": 1})
    second_decision = await coordinator.decide(error, {"x": 1})

    assert first is not None and first.owner == "always"
    assert second.called is False
    assert second_decision is None


async def test_poisoned_thinking_strips_all_blocks_once() -> None:
    strategy = PoisonedThinkingStrategy()
    error = ApiError("thinking blocks cannot be modified", status_code=400)
    payload: dict[str, object] = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "secret", "signature": "sig"},
                    {"type": "text", "text": "answer"},
                ],
            }
        ]
    }

    decision = await strategy.handle(error, payload)

    assert decision.should_retry is True
    assert decision.payload["messages"][0]["content"] == [  # type: ignore[index]
        {"type": "text", "text": "answer"}
    ]
    assert strategy.can_handle(error) is False