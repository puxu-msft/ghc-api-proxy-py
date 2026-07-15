from collections.abc import Mapping
from typing import Any

import httpx
import pytest

from app.anthropic.token_counting import TokenCounter, estimate_input_tokens
from app.models.anthropic import MessagesRequest


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
    assert estimate_input_tokens(_request()) > 0


@pytest.mark.asyncio
async def test_token_counter_prefers_upstream_result() -> None:
    target = StubTarget(
        httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.test/count_tokens"),
            json={"input_tokens": 42, "future": True},
        )
    )
    counter = TokenCounter(target)

    result = await counter.count(_request())

    assert result == {"input_tokens": 42, "future": True}
    assert target.payload is not None


@pytest.mark.asyncio
async def test_token_counter_falls_back_for_upstream_error() -> None:
    target = StubTarget(httpx.ConnectError("offline"))
    counter = TokenCounter(target)

    result = await counter.count(_request())

    assert result["input_tokens"] > 0
    assert result["estimated"] is True