import asyncio
from typing import cast

import httpx2
from fastapi.testclient import TestClient

from app.config.schema import OpenAICompatibleProviderConfig, ProxyConfig
from app.model_provider import ModelProvider, OpenAICompatibleProvider
from app.model_provider.openai_compatible import OpenAICompatibleClient
from app.server.composition import build_chain
from app.server.pipeline_app import create_pipeline_app


def _bridge_app(
    **overrides: object,
) -> tuple[TestClient, httpx2.AsyncClient, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/zen/go/v1/models":
            return httpx2.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "bridge-model",
                            "supported_endpoints": ["/v1/messages"],
                        }
                    ],
                },
            )
        seen.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "bridge-model",
                "content": [{"type": "text", "text": "hi"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = OpenAICompatibleProviderConfig.model_validate(
        {
            "type": "bridge",
            "api_base_url": "https://opencode.example/zen/go/v1",
            "api_key": "test-key",
            "models": ["bridge-model"],
            "anthropic_messages_endpoint": True,
            **overrides,
        }
    )
    provider = OpenAICompatibleProvider(
        "opencode",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "opencode",
            "model_providers": {"opencode": provider_config.model_dump(mode="python")},
        }
    )
    chain = build_chain(
        config,
        http_client=http_client,
        providers={"opencode": cast(ModelProvider, provider)},
    )
    return TestClient(create_pipeline_app(chain)), http_client, seen


def _send_messages(
    client: TestClient,
    *,
    session_id: str = "session-42",
) -> None:
    response = client.post(
        "/v1/messages",
        json={
            "model": "bridge-model",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 64,
        },
        headers={"x-claude-code-session-id": session_id},
    )
    assert response.status_code == 200


def test_anthropic_leg_sends_x_api_key_and_no_session_header_by_default() -> None:
    client, http_client, seen = _bridge_app()
    try:
        with client:
            _send_messages(client)
    finally:
        asyncio.run(http_client.aclose())

    assert len(seen) == 1
    assert seen[0].url.path == "/zen/go/v1/messages"
    assert seen[0].headers["x-api-key"] == "test-key"
    assert "authorization" not in seen[0].headers
    assert "x-opencode-session" not in seen[0].headers


def test_anthropic_leg_adds_bearer_when_configured() -> None:
    client, http_client, seen = _bridge_app(add_header_authorization=True)
    try:
        with client:
            _send_messages(client)
    finally:
        asyncio.run(http_client.aclose())

    assert len(seen) == 1
    assert seen[0].headers["x-api-key"] == "test-key"
    assert seen[0].headers["authorization"] == "Bearer test-key"


def test_anthropic_leg_reuses_the_client_conversation_as_x_opencode_session() -> None:
    client, http_client, seen = _bridge_app(add_header_x_opencode_session=True)
    try:
        with client:
            _send_messages(client, session_id="client-session-7")
    finally:
        asyncio.run(http_client.aclose())

    assert len(seen) == 1
    assert seen[0].headers["x-opencode-session"] == "client-session-7"
