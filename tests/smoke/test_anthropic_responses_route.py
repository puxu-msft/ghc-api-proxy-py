from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from app.anthropic.client import AnthropicClient
from app.config.settings import AppSettings
from app.deps import get_anthropic_client
from app.hooks.context import HookContext
from app.hooks.executor import HooksExecutor
from app.hooks.registry import HookRegistryBuilder
from app.hooks.types import (
    HookErrorMode,
    ObserverEvent,
    PayloadHookResult,
    PayloadPhase,
)
from app.pipeline.approval import ApprovalGate, ApprovalResult
from app.pipeline.context import RequestContext, RequestState
from app.server import create_app
from app.transform.model_resolver import ModelResolver
from app.upstream.models_api import ModelCatalog


@dataclass(slots=True)
class RecordingTarget:
    anthropic_payloads: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    responses_payloads: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    responses_status: int = 200

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        del stream, extra_headers
        self.anthropic_payloads.append(dict(payload))
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "request-id": "req_messages",
                "x-messages-existing": "preserved",
            },
            request=httpx.Request("POST", "https://upstream.test/v1/messages"),
            json={
                "id": "msg_direct",
                "type": "message",
                "role": "assistant",
                "model": payload["model"],
                "content": [{"type": "text", "text": "direct Messages"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 2, "output_tokens": 2},
            },
        )

    async def send_responses_headers(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        self.responses_payloads.append(dict(payload))
        if self.responses_status != 200:
            return httpx.Response(
                self.responses_status,
                headers={
                    "content-type": "application/json",
                    "retry-after": "3",
                    "x-internal-openai": "must-not-forward",
                },
                request=httpx.Request("POST", "https://upstream.test/responses"),
                json={
                    "error": {
                        "message": "Responses quota exhausted",
                        "code": "responses_quota",
                    }
                },
            )
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-length": "99999",
                "request-id": "req_responses",
                "x-ratelimit-remaining-requests": "8",
                "x-internal-openai": "must-not-forward",
            },
            request=httpx.Request("POST", "https://upstream.test/responses"),
            json={
                "id": "resp_vertical",
                "model": payload["model"],
                "status": "completed",
                "output": [
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "checked"}],
                        "encrypted_content": "opaque-state",
                    },
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "hello bridge"}],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_weather",
                        "name": "weather",
                        "arguments": '{"city":"Paris"}',
                    },
                ],
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 7,
                    "total_tokens": 19,
                },
            },
        )


@dataclass(slots=True)
class RecordingHistory:
    started_contexts: list[RequestContext] = field(
        default_factory=lambda: list[RequestContext]()
    )
    finalized_contexts: list[RequestContext] = field(
        default_factory=lambda: list[RequestContext]()
    )

    async def started(self, context: RequestContext) -> None:
        self.started_contexts.append(context)

    async def finalized(
        self,
        context: RequestContext,
        *,
        response: dict[str, Any] | None = None,
    ) -> None:
        del response
        self.finalized_contexts.append(context)


@dataclass(slots=True)
class RecordingApproval:
    enabled: bool = True
    contexts: list[RequestContext] = field(default_factory=lambda: list[RequestContext]())

    async def wait_for_approval(self, context: RequestContext) -> ApprovalResult:
        self.contexts.append(context)
        return ApprovalResult("approved")


@dataclass(slots=True)
class RecordingObserver:
    name: str = "route-smoke-observer"
    order: int = 1001
    events: frozenset[ObserverEvent] = frozenset(
        {
            ObserverEvent.REQUEST_RECEIVED,
            ObserverEvent.RESPONSE,
            ObserverEvent.ERROR,
            ObserverEvent.FINALIZE,
        }
    )
    seen: list[tuple[ObserverEvent, HookContext, Mapping[str, Any]]] = field(
        default_factory=lambda: list[
            tuple[ObserverEvent, HookContext, Mapping[str, Any]]
        ]()
    )

    async def observe(
        self,
        event: ObserverEvent,
        context: HookContext,
        data: Mapping[str, Any],
    ) -> None:
        self.seen.append((event, context, data))


@dataclass(frozen=True, slots=True)
class FailingTerminalObserver:
    name: str = "route-smoke-failing-terminal-observer"
    order: int = 1000
    events: frozenset[ObserverEvent] = frozenset(
        {ObserverEvent.ERROR, ObserverEvent.FINALIZE}
    )

    async def observe(
        self,
        event: ObserverEvent,
        context: HookContext,
        data: Mapping[str, Any],
    ) -> None:
        del event, context, data
        raise RuntimeError("terminal observer failed")


@dataclass(frozen=True, slots=True)
class PreSendPayloadHook:
    name: str = "route-smoke-pre-send"
    phase: PayloadPhase = PayloadPhase.PRE_SEND
    order: int = 1001
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST
    thinking: dict[str, Any] | None = None

    async def run(
        self,
        payload: dict[str, Any],
        context: HookContext,
    ) -> PayloadHookResult:
        assert context.attempt_number == 0
        updated = {**payload, "max_tokens": 32}
        modifications = ["max_tokens"]
        if self.thinking is not None:
            updated["thinking"] = self.thinking
            modifications.append("thinking")
        return PayloadHookResult(
            payload=updated,
            modified=True,
            modifications=tuple(modifications),
        )


@dataclass(slots=True)
class Harness:
    client: TestClient
    target: RecordingTarget
    history: RecordingHistory
    approval: RecordingApproval
    observer: RecordingObserver


def _harness(
    *,
    endpoints: list[str],
    route_override: str = "auto",
    responses_status: int = 200,
    failing_terminal_observer: bool = False,
    model_id: str = "resolved-model",
    supports: Mapping[str, Any] | None = None,
    pre_send_thinking: dict[str, Any] | None = None,
) -> Harness:
    settings = AppSettings.model_validate(
        {
            "anthropic": {"route_override": route_override},
            "history": {"enabled": False},
        }
    )
    catalog = ModelCatalog(None, "https://upstream.test")
    model: dict[str, Any] = {
        "id": model_id,
        "vendor": "test",
        "supported_endpoints": endpoints,
    }
    if supports is not None:
        model["capabilities"] = {"supports": dict(supports)}
    catalog.replace_from_data({"object": "list", "data": [model]})
    target = RecordingTarget(responses_status=responses_status)
    history = RecordingHistory()
    approval = RecordingApproval()
    observer = RecordingObserver()
    hooks_builder = HookRegistryBuilder()
    if failing_terminal_observer:
        hooks_builder.register_observer(FailingTerminalObserver())
    hooks_builder.register_observer(observer)
    hooks_builder.register_payload(PreSendPayloadHook(thinking=pre_send_thinking))
    anthropic = AnthropicClient(
        target,
        ModelResolver(
            available_ids=catalog.available_ids,
            model_overrides={},
            model_mappings={"requested-model": model_id},
        ),
        settings,
        history=cast(Any, history),
        approval_gate=cast(ApprovalGate, approval),
        hooks=HooksExecutor(hooks_builder.build(), user_timeout_ms=1_000),
        model_catalog=catalog,
    )
    app = create_app(settings)
    app.dependency_overrides[get_anthropic_client] = lambda: anthropic
    return Harness(TestClient(app), target, history, approval, observer)


def _request_body(*, stream: bool = False) -> dict[str, Any]:
    return {
        "model": "requested-model",
        "max_tokens": 64,
        "stream": stream,
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [
            {
                "name": "weather",
                "description": "Get weather",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }
        ],
    }


@pytest.mark.parametrize(
    ("endpoints", "route_override", "expected_reason"),
    [
        (["/responses"], "auto", "single_capability"),
        (["/v1/messages", "/responses"], "responses", "explicit_override"),
    ],
)
def test_anthropic_nonstream_responses_leg_is_a_real_single_owner_asgi_flow(
    endpoints: list[str],
    route_override: str,
    expected_reason: str,
) -> None:
    harness = _harness(endpoints=endpoints, route_override=route_override)
    with harness.client as client:
        response = client.post(
            "/v1/messages",
            headers={
                "x-claude-code-session-id": "session-route-smoke",
                "x-claude-code-agent-id": "agent-route-smoke",
            },
            json=_request_body(),
        )

    assert response.status_code == 200
    assert response.headers["request-id"] == "req_responses"
    assert response.headers["x-ratelimit-remaining-requests"] == "8"
    assert "x-internal-openai" not in response.headers
    assert response.headers["content-length"] != "99999"
    assert harness.target.anthropic_payloads == []
    assert len(harness.target.responses_payloads) == 1
    wire = harness.target.responses_payloads[0]
    assert wire["model"] == "resolved-model"
    assert wire["stream"] is False
    assert wire["max_output_tokens"] == 32
    assert wire["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hello"}],
        }
    ]
    assert wire["tools"][0]["name"] == "weather"

    body = response.json()
    assert body["type"] == "message"
    assert body["model"] == "resolved-model"
    assert body["stop_reason"] == "tool_use"
    assert [block["type"] for block in body["content"]] == [
        "thinking",
        "text",
        "tool_use",
    ]
    assert body["content"][0]["thinking"] == "checked"
    assert body["content"][0]["signature"].startswith(
        "ghc-api-proxy:synthetic-reasoning:v1:"
    )
    assert body["content"][1] == {"type": "text", "text": "hello bridge"}
    assert body["content"][2] == {
        "type": "tool_use",
        "id": "call_weather",
        "name": "weather",
        "input": {"city": "Paris"},
    }
    assert body["usage"] == {
        "input_tokens": 12,
        "output_tokens": 7,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }

    assert len(harness.history.started_contexts) == 1
    assert len(harness.history.finalized_contexts) == 1
    context = harness.history.started_contexts[0]
    assert harness.history.finalized_contexts[0] is context
    assert harness.approval.contexts == [context]
    assert context.state is RequestState.COMPLETED
    assert context.original_model == "requested-model"
    assert context.resolved_model == "resolved-model"
    assert context.protocol_leg == "responses"
    assert context.route_reason == expected_reason
    assert context.session_id == "session-route-smoke"
    assert context.agent_id == "agent-route-smoke"
    assert len(context.attempts) == 1
    assert context.attempts[0].status_code == 200
    assert [event for event, _, _ in harness.observer.seen] == [
        ObserverEvent.REQUEST_RECEIVED,
        ObserverEvent.RESPONSE,
        ObserverEvent.FINALIZE,
    ]
    assert {hook_context.request_id for _, hook_context, _ in harness.observer.seen} == {
        context.id
    }
    response_observation = harness.observer.seen[1][2]
    assert b"hello bridge" in response_observation["response_body"]


SINGLETON_REASONING_SUPPORTS = {
    "adaptive_thinking": True,
    "min_thinking_budget": 1_024,
    "max_thinking_budget": 32_768,
    "reasoning_effort": ["medium"],
}


@pytest.mark.parametrize(
    ("thinking", "expected_reasoning"),
    [
        (
            {"type": "enabled", "budget_tokens": 8_192},
            {"effort": "medium", "summary": "auto"},
        ),
        ({"type": "adaptive"}, {"effort": "medium", "summary": "auto"}),
    ],
)
def test_responses_only_reasoning_uses_resolved_model_capability_facts(
    thinking: dict[str, Any],
    expected_reasoning: dict[str, str],
) -> None:
    harness = _harness(
        endpoints=["/responses"],
        supports=SINGLETON_REASONING_SUPPORTS,
    )
    request = {**_request_body(), "thinking": thinking}

    with harness.client as client:
        response = client.post("/v1/messages", json=request)

    assert response.status_code == 200
    assert harness.target.anthropic_payloads == []
    assert len(harness.target.responses_payloads) == 1
    assert harness.target.responses_payloads[0]["reasoning"] == expected_reasoning


@pytest.mark.parametrize(
    "supports",
    [None, {"reasoning_effort": ["low", "medium", "high"]}],
)
def test_unknown_reasoning_capabilities_fail_closed_without_model_name_guessing(
    supports: Mapping[str, Any] | None,
) -> None:
    harness = _harness(
        endpoints=["/responses"],
        model_id="o3-reasoning-model-name-is-not-a-capability",
        supports=supports,
    )
    request = {
        **_request_body(),
        "thinking": {"type": "enabled", "budget_tokens": 8_192},
    }

    with harness.client as client:
        response = client.post("/v1/messages", json=request)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "reasoning_not_supported"
    assert harness.target.anthropic_payloads == []
    assert harness.target.responses_payloads == []


@pytest.mark.parametrize(
    "efforts",
    [
        ["low", "medium", "high"],
        ["high", "medium", "low"],
    ],
)
@pytest.mark.parametrize(
    ("thinking", "expected_code"),
    [
        (
            {"type": "enabled", "budget_tokens": 8_192},
            "reasoning_budget_not_supported",
        ),
        ({"type": "adaptive"}, "reasoning_not_supported"),
    ],
)
def test_ambiguous_reasoning_effort_set_is_rejected_independent_of_order(
    efforts: list[str],
    thinking: dict[str, Any],
    expected_code: str,
) -> None:
    harness = _harness(
        endpoints=["/responses"],
        supports={
            **SINGLETON_REASONING_SUPPORTS,
            "reasoning_effort": efforts,
        },
    )

    with harness.client as client:
        response = client.post(
            "/v1/messages",
            json={**_request_body(), "thinking": thinking},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == expected_code
    assert harness.target.anthropic_payloads == []
    assert harness.target.responses_payloads == []


@pytest.mark.parametrize(
    ("budget", "expected_status"),
    [(1_023, 400), (1_024, 200), (32_768, 200), (32_769, 400)],
)
def test_responses_reasoning_budget_uses_exact_catalog_boundaries(
    budget: int,
    expected_status: int,
) -> None:
    harness = _harness(
        endpoints=["/responses"],
        supports=SINGLETON_REASONING_SUPPORTS,
    )
    request = {
        **_request_body(),
        "thinking": {"type": "enabled", "budget_tokens": budget},
    }

    with harness.client as client:
        response = client.post("/v1/messages", json=request)

    assert response.status_code == expected_status
    if expected_status == 200:
        assert harness.target.responses_payloads[0]["reasoning"] == {
            "effort": "medium",
            "summary": "auto",
        }
    else:
        assert response.json()["error"]["code"] == "reasoning_budget_not_supported"
        assert harness.target.responses_payloads == []


def test_pre_send_reasoning_modification_is_reconverted_with_capability_facts() -> None:
    harness = _harness(
        endpoints=["/responses"],
        supports=SINGLETON_REASONING_SUPPORTS,
        pre_send_thinking={"type": "adaptive"},
    )
    request = {
        **_request_body(),
        "thinking": {"type": "disabled"},
    }

    with harness.client as client:
        response = client.post("/v1/messages", json=request)

    assert response.status_code == 200
    assert harness.target.responses_payloads[0]["reasoning"] == {
        "effort": "medium",
        "summary": "auto",
    }
    context = harness.history.finalized_contexts[0]
    assert context.attempts[0].payload_modifications == ["max_tokens", "thinking"]


def test_dual_capability_auto_keeps_existing_messages_leg() -> None:
    harness = _harness(endpoints=["/v1/messages", "/responses"])
    with harness.client as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 200
    assert response.headers["x-messages-existing"] == "preserved"
    assert response.json()["content"] == [{"type": "text", "text": "direct Messages"}]
    assert len(harness.target.anthropic_payloads) == 1
    assert harness.target.responses_payloads == []
    context = harness.history.finalized_contexts[0]
    assert context.protocol_leg == "messages"
    assert context.route_reason == "dual_capability_default"
    assert len(context.attempts) == 1


@pytest.mark.parametrize(
    (
        "endpoints",
        "route_override",
        "stream",
        "expected_code",
        "expected_message",
        "expected_approval_count",
        "expected_protocol_leg",
    ),
    [
        (
            [],
            "auto",
            False,
            "capability_missing",
            "supported_endpoints is missing or empty",
            0,
            "",
        ),
        (
            ["/v1/messages"],
            "responses",
            False,
            "override_unsupported",
            "model does not advertise responses capability",
            0,
            "",
        ),
    ],
)
def test_pre_attempt_typed_rejection_uses_single_failure_finalizer(
    endpoints: list[str],
    route_override: str,
    stream: bool,
    expected_code: str,
    expected_message: str,
    expected_approval_count: int,
    expected_protocol_leg: str,
) -> None:
    harness = _harness(endpoints=endpoints, route_override=route_override)
    with harness.client as client:
        response = client.post("/v1/messages", json=_request_body(stream=stream))

    assert response.status_code == 400
    assert response.json() == {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": expected_message,
            "code": expected_code,
        },
    }
    assert harness.target.anthropic_payloads == []
    assert harness.target.responses_payloads == []
    assert len(harness.approval.contexts) == expected_approval_count
    assert len(harness.history.started_contexts) == 1
    assert harness.history.finalized_contexts == harness.history.started_contexts
    context = harness.history.finalized_contexts[0]
    if expected_approval_count:
        assert harness.approval.contexts == [context]
    assert context.state is RequestState.FAILED
    assert context.protocol_leg == expected_protocol_leg
    assert context.attempts == []
    assert context.error is not None
    assert context.error.code == expected_code
    assert [event for event, _, _ in harness.observer.seen] == [
        ObserverEvent.REQUEST_RECEIVED,
        ObserverEvent.ERROR,
        ObserverEvent.FINALIZE,
    ]
    assert {hook_context.request_id for _, hook_context, _ in harness.observer.seen} == {
        context.id
    }
    assert harness.observer.seen[1][2]["error"] is context.error
    assert harness.observer.seen[2][2] == {
        "request": harness.observer.seen[1][2]["request"],
        "state": "failed",
        "error": context.error,
    }


def test_pre_attempt_observer_failure_is_isolated_from_typed_rejection() -> None:
    harness = _harness(endpoints=[], failing_terminal_observer=True)
    with harness.client as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "capability_missing"
    assert harness.target.anthropic_payloads == []
    assert harness.target.responses_payloads == []
    assert harness.history.finalized_contexts == harness.history.started_contexts
    context = harness.history.finalized_contexts[0]
    assert len(harness.history.finalized_contexts) == 1
    assert context.attempts == []
    assert [event for event, _, _ in harness.observer.seen] == [
        ObserverEvent.REQUEST_RECEIVED,
        ObserverEvent.ERROR,
        ObserverEvent.FINALIZE,
    ]
    assert [
        record["phase"]
        for record in context.hook_records
        if record["name"] == "route-smoke-failing-terminal-observer"
    ] == [ObserverEvent.ERROR, ObserverEvent.FINALIZE]


def test_responses_upstream_error_becomes_anthropic_envelope() -> None:
    harness = _harness(endpoints=["/responses"], responses_status=429)
    with harness.client as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 429
    assert response.headers["retry-after"] == "3"
    assert "x-internal-openai" not in response.headers
    assert response.json() == {
        "type": "error",
        "error": {
            "type": "rate_limit_error",
            "message": "Responses quota exhausted",
            "code": "responses_quota",
        },
    }
    assert harness.target.anthropic_payloads == []
    assert len(harness.target.responses_payloads) == 1
    context = harness.history.finalized_contexts[0]
    assert harness.history.started_contexts == [context]
    assert harness.approval.contexts == [context]
    assert context.state is RequestState.FAILED
    assert context.protocol_leg == "responses"
    assert len(context.attempts) == 1
    assert context.attempts[0].status_code == 429