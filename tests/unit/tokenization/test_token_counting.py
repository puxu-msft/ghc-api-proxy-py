from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.models.anthropic import MessagesRequest
from app.tokenization.estimators import estimate_anthropic_input
from app.tokenization.service import AnthropicTokenCountingService
from app.tokenization.state_store import TokenizationStateStore


class StubTarget:
    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.payload: Mapping[str, Any] | None = None

    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        self.payload = payload
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _request() -> MessagesRequest:
    return MessagesRequest.model_validate(
        {
            "model": "claude-test",
            "max_tokens": 100,
            "system": "system prompt",
            "messages": [{"role": "user", "content": "hello world"}],
        }
    )


def test_local_token_estimator_returns_positive_count() -> None:
    assert estimate_anthropic_input(_request()) > 0


def _counter(
    target: StubTarget,
    tmp_path: Path,
    *,
    use_upstream: bool = True,
) -> tuple[AnthropicTokenCountingService, TokenizationStateStore]:
    state = TokenizationStateStore(tmp_path / "tokenization.json")
    return (
        AnthropicTokenCountingService(
            target,
            state,
            use_upstream=use_upstream,
        ),
        state,
    )


@pytest.mark.asyncio
async def test_token_counter_prefers_upstream_result_and_learns(
    tmp_path: Path,
) -> None:
    estimate = estimate_anthropic_input(_request())
    target = StubTarget(
        httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.test/count_tokens"),
            json={"input_tokens": estimate * 2, "future": True},
        )
    )
    counter, state = _counter(target, tmp_path)

    result = await counter.count(_request())

    assert result == {"input_tokens": estimate * 2, "future": True}
    assert target.payload is not None
    assert state.calibration.calibrate("anthropic", "claude-test", estimate) == estimate * 2


@pytest.mark.asyncio
async def test_token_counter_falls_back_for_upstream_error(tmp_path: Path) -> None:
    target = StubTarget(httpx.ConnectError("offline"))
    counter, _ = _counter(target, tmp_path)

    result = await counter.count(_request())

    assert result["input_tokens"] > 0
    assert result["estimated"] is True


@pytest.mark.asyncio
async def test_token_counter_fallback_consumes_calibration(tmp_path: Path) -> None:
    target = StubTarget(httpx.ConnectError("offline"))
    counter, state = _counter(target, tmp_path)
    estimate = estimate_anthropic_input(_request())
    state.calibration.learn("anthropic", "claude-test", estimate, estimate * 2)

    result = await counter.count(_request())

    assert result == {"input_tokens": estimate * 2, "estimated": True}


@pytest.mark.asyncio
async def test_token_counter_records_limit_error_without_rewriting(
    tmp_path: Path,
) -> None:
    target = StubTarget(
        httpx.Response(
            400,
            request=httpx.Request("POST", "https://example.test/count_tokens"),
            json={
                "error": {
                    "message": "prompt is too long: 200000 tokens > 168000 maximum"
                }
            },
        )
    )
    counter, state = _counter(target, tmp_path)

    result = await counter.count(_request())

    assert result["estimated"] is True
    observation = state.prompt_limits.get("anthropic", "claude-test")
    assert observation is not None
    assert observation.observed_limit == 168_000
    estimate = estimate_anthropic_input(_request())
    assert (
        state.calibration.calibrate("anthropic", "claude-test", estimate)
        == estimate * 3
    )
    assert target.payload is not None
    assert target.payload["messages"] == [
        {"role": "user", "content": "hello world"}
    ]
