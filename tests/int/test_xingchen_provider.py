import asyncio
from collections.abc import Callable
from typing import Any

import httpx2
from fastapi.testclient import TestClient

from app.config.schema import ProxyConfig, XingchenProviderConfig
from app.model_provider import ModelProvider, XingchenProvider
from app.model_provider.xingchen import XingchenClient
from app.server.composition import build_chain
from app.server.pipeline_app import create_pipeline_app
from app.wire_json import loads

CHAT_SSE = (
    b'data: {"id":"cc-1","object":"chat.completion.chunk","choices":'
    b'[{"index":0,"delta":{"content":"pong"},"finish_reason":null}]}\n\n'
    b'data: {"id":"cc-1","object":"chat.completion.chunk","choices":'
    b'[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
    b"data: [DONE]\n\n"
)


def make_client(
    handler: Callable[[httpx2.Request], httpx2.Response],
) -> tuple[TestClient, list[httpx2.Request], httpx2.AsyncClient]:
    seen: list[httpx2.Request] = []

    def recording(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(recording))
    config = ProxyConfig.model_validate(
        {
            "model_providers": {
                "xingchen": {
                    "type": "xingchen",
                    "models": ["chat-pro"],
                    "gateway_api_key": "gateway-key",
                    "x_token": "complete.x.token",
                    "device_id": "device-id",
                    "install_id": "install-id",
                }
            },
            "default_model_provider": "xingchen",
        }
    )
    provider_config = config.model_providers["xingchen"]
    assert isinstance(provider_config, XingchenProviderConfig)
    provider = XingchenProvider(
        "xingchen",
        XingchenClient(http_client, provider_config),
        provider_config,
    )
    providers: dict[str, ModelProvider] = {"xingchen": provider}
    chain = build_chain(
        config,
        http_client=http_client,
        providers=providers,
    )
    return TestClient(create_pipeline_app(chain)), seen, http_client


def close(client: TestClient, http_client: httpx2.AsyncClient) -> None:
    client.close()
    asyncio.run(http_client.aclose())


def test_native_chat_request_reaches_signed_xingchen_endpoint() -> None:
    client, seen, http_client = make_client(
        lambda _: httpx2.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "pong"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )
    )

    try:
        response = client.post(
            "/chat/completions",
            json={"model": "chat-pro", "messages": [{"role": "user", "content": "ping"}]},
        )
    finally:
        close(client, http_client)

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "pong"
    assert len(seen) == 1
    request = seen[0]
    assert request.url.path == "/superCowork/sapi/api/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer gateway-key"
    assert request.headers["x-token"] == "complete.x.token"
    assert request.headers["x-superagent-sign-version"] == "v1"
    assert loads(request.content) == {
        "model": "chat-pro",
        "messages": [{"role": "user", "content": "ping"}],
    }


def test_native_chat_stream_is_delivered_verbatim() -> None:
    client, seen, http_client = make_client(
        lambda _: httpx2.Response(
            200,
            content=CHAT_SSE,
            headers={"content-type": "text/event-stream"},
        )
    )

    try:
        response = client.post(
            "/chat/completions",
            json={"model": "chat-pro", "messages": [], "stream": True},
        )
    finally:
        close(client, http_client)

    assert response.status_code == 200
    assert response.content == CHAT_SSE
    assert len(seen) == 1
    body = loads(seen[0].content)
    assert isinstance(body, dict)
    assert body["stream_options"] == {"include_usage": True}
    assert body["tool_stream"] is True


def test_the_legs_without_a_translation_still_refuse_before_the_network() -> None:
    """Embeddings and token counting have no way to reach a chat-only upstream.

    Written when **no** non-chat leg could reach this provider (there was no
    outbound chat translator at all); the chat-completions translation leg now
    carries Anthropic and Responses ingress onto this wire, so the refusal this
    test pins is down to the two legs that still have no crossing — and both must
    refuse before the network, not after.
    """
    client, seen, http_client = make_client(
        lambda _: httpx2.Response(500, text="must not be called")
    )
    requests: list[tuple[str, dict[str, Any]]] = [
        ("/embeddings", {"model": "chat-pro", "input": "hi"}),
        (
            "/v1/messages/count_tokens",
            {"model": "chat-pro", "messages": [{"role": "user", "content": "hi"}]},
        ),
    ]

    try:
        responses = [client.post(path, json=body) for path, body in requests]
    finally:
        close(client, http_client)

    assert all(response.status_code >= 400 for response in responses)
    assert seen == []


def test_anthropic_ingress_is_translated_onto_the_chat_upstream() -> None:
    """Anthropic Messages ingress reaches this chat-only provider translated.

    The outbound chat-completions translator serves this provider exactly as it
    serves CodeBuddy: a Claude Code client and a chat-only upstream meet in the
    middle. The mock answers 500, so the assertion is that the request *arrives*
    (translated, in the upstream's own shape) rather than that it is refused.
    """
    client, seen, http_client = make_client(
        lambda _: httpx2.Response(500, text="must not be called")
    )

    try:
        response = client.post(
            "/v1/messages",
            json={"model": "chat-pro", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]},
        )
    finally:
        close(client, http_client)

    assert response.status_code == 500
    # The mock's 500 is retryable, so the budget fired; the assertion is about the
    # request shape, not the attempt count.
    assert len(seen) >= 1
    body = loads(seen[0].content)
    assert isinstance(body, dict)
    assert body["model"] == "chat-pro"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["max_tokens"] == 16
