"""End-to-end over the new chain: HTTP in, upstream out, through a real ASGI app.

The upstream is a MockTransport under the real SDKs.
Upstream protocol behaviour is therefore the real thing rather than a friendlier stand-in.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from anthropic import AsyncAnthropic
from fastapi.testclient import TestClient
from openai import AsyncOpenAI

from app.config.schema import ModelProviderConfig, ProxyConfig
from app.ghc_client import GhcApiClient, GhcClientConfig
from app.ghc_client.tokens import CopilotTokenManager
from app.model_provider import GithubCopilotProvider, ModelProvider
from app.server.composition import build_chain
from app.server.pipeline_app import create_pipeline_app

BASE_URL = "https://copilot.example"

CATALOG: dict[str, Any] = {
    "object": "list",
    "data": [
        {"id": "claude-model", "supported_endpoints": ["/v1/messages"]},
        {"id": "gpt-model", "supported_endpoints": ["/responses"]},
        {"id": "embed-model", "supported_endpoints": ["/embeddings"]},
        {"id": "mute-model", "supported_endpoints": []},
    ],
}


class StaticTokenSource:
    async def get_token(self) -> str:
        return "ghu_github"

    async def refresh(self) -> str | None:
        return None


def make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    disabled: list[str] | None = None,
) -> tuple[GithubCopilotProvider, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tokens = CopilotTokenManager(StaticTokenSource(), http_client, clock=lambda: 1000)
    client = GhcApiClient(
        AsyncOpenAI(
            api_key="proxy-managed",
            base_url=BASE_URL,
            http_client=http_client,
            max_retries=0,
        ),
        AsyncAnthropic(
            api_key="proxy-managed",
            base_url=BASE_URL,
            http_client=http_client,
            max_retries=0,
        ),
        tokens,
        GhcClientConfig(base_url_override=BASE_URL),
        interaction_id="interaction",
    )
    provider = GithubCopilotProvider(
        "ghc",
        client,
        ModelProviderConfig(type="github_copilot", disabled_models=disabled or []),
        http_client=http_client,
        base_url=BASE_URL,
    )
    provider.replace_catalog(CATALOG)
    return provider, http_client


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    mappings: dict[str, str] | None = None,
) -> tuple[TestClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        seen.append(request)
        return handler(request)

    provider, http_client = make_provider(recording)
    config = ProxyConfig.model_validate(
        {
            "model_providers": {"ghc": {"type": "github_copilot", "base_url": BASE_URL}},
            "default_model_provider": "ghc",
            "model_mappings": mappings or {},
        }
    )
    providers: dict[str, ModelProvider] = {"ghc": provider}
    chain = build_chain(config, http_client=http_client, providers=providers)
    return TestClient(create_pipeline_app(chain)), seen


def test_anthropic_request_reaches_the_messages_endpoint_untranslated() -> None:
    client, seen = make_client(
        lambda _: httpx.Response(200, json={"id": "msg_1", "content": []})
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "msg_1"
    assert str(seen[-1].url) == f"{BASE_URL}/v1/messages"


def test_anthropic_request_for_a_responses_model_is_translated() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "system": [{"type": "text", "text": "be brief"}],
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
        },
    )

    assert response.status_code == 200
    assert str(seen[-1].url) == f"{BASE_URL}/responses"

    # The body upstream received must be Responses-shaped, not the Anthropic body we accepted.
    sent = seen[-1].read().decode()
    assert '"instructions"' in sent
    assert '"input"' in sent
    assert '"max_output_tokens"' in sent
    assert '"messages"' not in sent


def test_model_mapping_is_applied_before_the_upstream_call() -> None:
    client, seen = make_client(
        lambda _: httpx.Response(200, json={"id": "msg_1"}),
        mappings={"opus": "claude-model"},
    )
    response = client.post("/v1/messages", json={"model": "opus", "messages": []})

    assert response.status_code == 200
    assert '"claude-model"' in seen[-1].read().decode()


def test_openai_group_is_served_under_every_compatible_prefix() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={"id": "resp_1"}))
    for prefix in ("", "/v1", "/openai/v1"):
        response = client.post(f"{prefix}/responses", json={"model": "gpt-model", "input": []})
        assert response.status_code == 200
    assert len(seen) == 3


def test_model_without_the_capability_is_refused_before_the_network() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={}))
    response = client.post("/v1/messages", json={"model": "mute-model", "messages": []})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "CapabilityMissing"
    # Fail closed means nothing was sent, not that upstream rejected it.
    assert seen == []


def test_unknown_model_is_refused_before_the_network() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={}))
    response = client.post("/v1/messages", json={"model": "mystery", "messages": []})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "UnknownModel"
    assert seen == []


def test_missing_model_is_rejected_by_inbound_parsing() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={}))
    response = client.post("/v1/messages", json={"messages": []})

    assert response.status_code == 400
    assert seen == []


def test_streaming_is_refused_rather_than_passed_through() -> None:
    # Block-level delivery is required and not built yet.
    # A raw pass-through would look like it worked while breaking that invariant.
    client, seen = make_client(lambda _: httpx.Response(200, json={}))
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [], "stream": True},
    )

    assert response.status_code == 501
    assert response.json()["error"]["type"] == "StreamingNotWired"
    assert seen == []


def test_upstream_error_status_reaches_the_client_as_a_gateway_failure() -> None:
    client, _ = make_client(lambda _: httpx.Response(500, json={"error": "upstream boom"}))
    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})
    assert response.status_code == 502


def test_unknown_path_is_not_served() -> None:
    client, _ = make_client(lambda _: httpx.Response(200, json={}))
    assert client.post("/nope", json={"model": "claude-model"}).status_code == 404


@pytest.mark.parametrize("path", ["/embeddings", "/v1/embeddings", "/openai/v1/embeddings"])
def test_embeddings_endpoint_is_served(path: str) -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={"data": []}))
    response = client.post(path, json={"model": "embed-model", "input": "hi"})
    assert response.status_code == 200
    assert str(seen[-1].url) == f"{BASE_URL}/embeddings"
