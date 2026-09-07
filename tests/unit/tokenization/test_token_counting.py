from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx2
import pytest
import tiktoken

from app.models.anthropic import MessagesRequest
from app.tokenization.estimators import estimate_anthropic_input
from app.tokenization.service import AnthropicTokenCountingService
from app.tokenization.state_store import TokenizationStateStore
from app.wire_json import dumps

ENCODING = tiktoken.get_encoding("o200k_base")
SPECIAL_SPELLINGS = sorted(ENCODING.special_tokens_set)


def ordinary_tokens(text: str) -> int:
    return len(ENCODING.encode(text, disallowed_special=()))


class StubTarget:
    def __init__(self, response: httpx2.Response | Exception) -> None:
        self.response = response
        self.payload: Mapping[str, Any] | None = None

    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
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


def _special_anthropic_request(surface: str, spelling: str) -> tuple[MessagesRequest, int]:
    payload: dict[str, Any] = {"model": "claude-test", "max_tokens": 1, "messages": []}
    if surface == "system":
        payload["system"] = spelling
        expected = ordinary_tokens(spelling) + 4
    elif surface == "message":
        payload["messages"] = [{"role": "user", "content": spelling}]
        expected = ordinary_tokens("user") + ordinary_tokens(spelling) + 4
    elif surface == "tool-schema":
        payload["tools"] = [
            {
                "name": "lookup",
                "input_schema": {"type": "object", "description": spelling},
            }
        ]
        expected = 0
    else:
        raise AssertionError(f"unknown test surface: {surface}")
    request = MessagesRequest.model_validate(payload)
    if surface == "tool-schema":
        assert request.tools is not None
        tool_data = [tool.model_dump(mode="json", exclude_none=True) for tool in request.tools]
        expected = ordinary_tokens(dumps(tool_data).decode()) + 4
    return request, expected


@pytest.mark.parametrize("spelling", SPECIAL_SPELLINGS)
@pytest.mark.parametrize("surface", ["system", "message", "tool-schema"])
def test_configured_special_spellings_are_ordinary_text_on_every_anthropic_surface(
    spelling: str,
    surface: str,
) -> None:
    request, expected = _special_anthropic_request(surface, spelling)

    assert estimate_anthropic_input(request) == expected


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
        httpx2.Response(
            200,
            request=httpx2.Request("POST", "https://example.test/count_tokens"),
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
    target = StubTarget(httpx2.ConnectError("offline"))
    counter, _ = _counter(target, tmp_path)

    result = await counter.count(_request())

    assert result["input_tokens"] > 0
    assert result["estimated"] is True


@pytest.mark.asyncio
async def test_token_counter_fallback_consumes_calibration(tmp_path: Path) -> None:
    target = StubTarget(httpx2.ConnectError("offline"))
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
        httpx2.Response(
            400,
            request=httpx2.Request("POST", "https://example.test/count_tokens"),
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
