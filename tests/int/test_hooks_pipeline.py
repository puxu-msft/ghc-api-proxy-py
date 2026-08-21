from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2
import pytest

from app.anthropic.client import AnthropicClient
from app.config.settings import AppSettings
from app.hooks.builtin import register_builtin_hooks
from app.hooks.context import HookContext
from app.hooks.executor import HooksExecutor
from app.hooks.registry import HookRegistryBuilder
from app.hooks.types import HookErrorMode, PayloadHookResult, PayloadPhase
from app.models.anthropic import MessagesRequest
from app.pipeline.executor import UpstreamResponseError, execute_anthropic_pipeline
from app.tokenization.estimators import estimate_anthropic_input
from app.tokenization.state_store import TokenizationStateStore
from app.transform.model_resolver import ModelResolver


@dataclass(frozen=True)
class MarkerHook:
    name: str
    phase: PayloadPhase
    marker: str
    order: int
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def run(
        self,
        payload: dict[str, Any],
        context: HookContext,
    ) -> PayloadHookResult:
        return PayloadHookResult(
            {**payload, self.marker: context.attempt_number},
            True,
            (self.marker,),
        )


class Target:
    def __init__(self, responses: list[httpx2.Response]) -> None:
        self.responses = responses
        self.payloads: list[dict[str, Any]] = []

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        del stream, extra_headers
        self.payloads.append(dict(payload))
        return self.responses.pop(0)


def _request() -> MessagesRequest:
    return MessagesRequest.model_validate(
        {
            "model": "claude-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "hello"}],
        }
    )


def _client(
    target: Target,
    state: TokenizationStateStore,
    *custom_hooks: MarkerHook,
) -> AnthropicClient:
    settings = AppSettings()
    builder = HookRegistryBuilder()
    register_builtin_hooks(
        builder,
        settings,
        quarantine=None,
        tokenization_state=state,
    )
    for hook in custom_hooks:
        builder.register_payload(hook)
    executor = HooksExecutor(builder.build(), user_timeout_ms=1000)
    return AnthropicClient(
        target,
        ModelResolver(available_ids={"claude-test"}, model_overrides={}),
        settings,
        hooks=executor,
    )


def _client_with_disabled_retry_factory(
    target: Target,
    state: TokenizationStateStore,
) -> AnthropicClient:
    settings = AppSettings.model_validate(
        {"hooks": {"disabled": ["builtin:poisoned_thinking"]}}
    )
    builder = HookRegistryBuilder(disabled=tuple(settings.hooks.disabled))
    register_builtin_hooks(
        builder,
        settings,
        quarantine=None,
        tokenization_state=state,
    )
    return AnthropicClient(
        target,
        ModelResolver(available_ids={"claude-test"}, model_overrides={}),
        settings,
        hooks=HooksExecutor(builder.build(), user_timeout_ms=1000),
    )


@pytest.mark.asyncio
async def test_hooks_run_at_all_payload_phases_and_success_observer_learns(
    tmp_path: Path,
) -> None:
    estimate = estimate_anthropic_input(_request())
    response = httpx2.Response(
        200,
        request=httpx2.Request("POST", "https://upstream.test/v1/messages"),
        json={
            "id": "msg",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": estimate * 2, "output_tokens": 1},
        },
    )
    target = Target([response])
    state = TokenizationStateStore(tmp_path / "state.json")
    client = _client(
        target,
        state,
        MarkerHook("pre", PayloadPhase.PRE_SANITIZE, "pre", 1000),
        MarkerHook("post", PayloadPhase.POST_SANITIZE, "post", 1001),
        MarkerHook("send", PayloadPhase.PRE_SEND, "send", 1002),
    )

    result = await execute_anthropic_pipeline(client, _request())

    assert target.payloads == [
        {
            "model": "claude-test",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 100,
            "pre": 0,
            "post": 0,
            "send": 0,
        }
    ]
    assert state.calibration.calibrate("anthropic", "claude-test", estimate) == estimate * 2
    assert {record["phase"] for record in result.context.hook_records} >= {
        "pre_sanitize",
        "post_sanitize",
        "pre_send",
        "response",
    }
    await result.response.aclose()


@pytest.mark.asyncio
async def test_prompt_limit_observer_records_error_without_changing_payload(
    tmp_path: Path,
) -> None:
    response = httpx2.Response(
        400,
        request=httpx2.Request("POST", "https://upstream.test/v1/messages"),
        json={
            "error": {
                "message": "prompt is too long: 200000 tokens > 168000 maximum"
            }
        },
    )
    target = Target([response])
    state = TokenizationStateStore(tmp_path / "state.json")
    client = _client(target, state)
    original = _request()

    with pytest.raises(UpstreamResponseError):
        await execute_anthropic_pipeline(client, original)

    observation = state.prompt_limits.get("anthropic", "claude-test")
    assert observation is not None
    assert observation.observed_limit == 168_000
    assert target.payloads[0]["messages"] == original.model_dump(mode="json")["messages"]


@pytest.mark.asyncio
async def test_disabled_poisoned_thinking_factory_does_not_retry(
    tmp_path: Path,
) -> None:
    response = httpx2.Response(
        400,
        request=httpx2.Request("POST", "https://upstream.test/v1/messages"),
        text="thinking blocks cannot be modified",
    )
    target = Target([response])
    state = TokenizationStateStore(tmp_path / "state.json")
    client = _client_with_disabled_retry_factory(target, state)
    request = MessagesRequest.model_validate(
        {
            "model": "claude-test",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "secret", "signature": "sig"},
                        {"type": "text", "text": "answer"},
                    ],
                },
                {"role": "user", "content": "continue"},
            ],
        }
    )

    with pytest.raises(UpstreamResponseError):
        await execute_anthropic_pipeline(client, request)

    assert len(target.payloads) == 1
