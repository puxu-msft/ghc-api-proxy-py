"""The model-info file as a client sees it, through `/models`.

The unit tests assert the catalog the provider builds. These assert what comes back out
of the HTTP surface, `?format=pi` included, because the failure being fixed is a client
reading an empty description of a model it can already call — and only this path shows
the whole of it.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx2
from fastapi.testclient import TestClient

from app.config.schema import OpenAICompatibleProviderConfig, ProxyConfig
from app.model_provider import ModelProvider, OpenAICompatibleProvider
from app.model_provider.openai_compatible import OpenAICompatibleClient
from app.server.composition import build_chain
from app.server.pipeline_app import create_pipeline_app

# What opencode Zen answers today: ids and nothing else.
UPSTREAM = [
    {"id": "kimi-k3", "object": "model", "created": 1_789_000_000, "owned_by": "opencode"},
    {"id": "upstream-only", "object": "model", "created": 1_789_000_000, "owned_by": "opencode"},
]

DOCUMENT: dict[str, Any] = {
    "schema_version": 1,
    "models": {
        "kimi-k3": {
            "name": "Kimi K3",
            "supported_endpoints": ["/chat/completions", "/v1/messages"],
            "capabilities": {
                "supports": {"vision": True, "reasoning_effort": ["high"]},
                "limits": {
                    "max_context_window_tokens": 1_048_576,
                    "max_output_tokens": 131_072,
                },
            },
            "pricing": {
                "input": 3.0,
                "output": 15.0,
                "cacheRead": 0.3,
                "cacheWrite": 0.0,
            },
        }
    },
}


TIERED: dict[str, Any] = {
    "schema_version": 1,
    "models": {
        "kimi-k3": {
            "name": "Kimi K3",
            "supported_endpoints": ["/v1/messages"],
            "capabilities": {
                "limits": {"max_context_window_tokens": 1_048_576},
            },
            "pricing": {
                "tiers": [
                    {
                        "name": "default",
                        "input": 3.0,
                        "output": 15.0,
                        "cacheRead": 0.3,
                        "cacheWrite": 0.0,
                    },
                    {
                        "name": "above-200000",
                        "input_min_tokens": 200_001,
                        "input": 6.0,
                        "output": 30.0,
                        "cacheRead": 0.6,
                        "cacheWrite": 0.0,
                    },
                ]
            },
        }
    },
}


def bridge_client(
    tmp_path: Path, sampled_days_ago: int = 0, document: dict[str, Any] | None = None
) -> tuple[TestClient, httpx2.AsyncClient]:
    sampled = datetime.now(UTC).date() - timedelta(days=sampled_days_ago)
    contents = {**(document or DOCUMENT), "retrieved_at": sampled.isoformat()}
    path = tmp_path / "model-info.json"
    path.write_text(json.dumps(contents), encoding="utf-8")

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/models"), request.url
        return httpx2.Response(200, json={"object": "list", "data": UPSTREAM})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = OpenAICompatibleProviderConfig.model_validate(
        {
            "type": "bridge",
            "api_base_url": "https://opencode.ai/zen/go/v1",
            "api_key": "test-key",
            "model_info_json": str(path),
            "anthropic_messages_endpoint": True,
            "openai_chat_completions_endpoint": True,
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
    return TestClient(create_pipeline_app(chain)), http_client


def test_the_model_list_is_the_intersection_with_the_local_file(tmp_path: Path) -> None:
    """An id the file is silent about is not served, so it is not listed either.

    Listing it would promise a model whose context window, price and protocol this proxy
    cannot state — which is the state the file exists to leave behind.
    """
    client, http_client = bridge_client(tmp_path)
    try:
        with client:
            response = client.get("/v1/models")
        assert response.status_code == 200
        entries = response.json()["data"]
    finally:
        asyncio.run(http_client.aclose())

    assert [entry["id"] for entry in entries] == ["kimi-k3"]
    entry = entries[0]
    assert entry["owned_by"] == "opencode"
    # Upstream's own row survives the merge.
    assert entry["object"] == "model"
    assert entry["created"] == 1_789_000_000
    # And the file fills in what upstream left out.
    assert entry["name"] == "Kimi K3"
    assert entry["capabilities"]["limits"]["max_context_window_tokens"] == 1_048_576
    assert entry["pricing"]["cacheRead"] == 0.3


def test_the_pi_projection_reports_what_the_file_states(tmp_path: Path) -> None:
    """`?format=pi` reads the merged entry, so the file reaches the client intact.

    Context window, price, protocol and reasoning are exactly the fields a client picks a
    model on, and exactly the ones an id-only upstream cannot answer.
    """
    client, http_client = bridge_client(tmp_path)
    try:
        with client:
            response = client.get("/v1/models?format=pi")
        assert response.status_code == 200
        entries = response.json()["data"]
    finally:
        asyncio.run(http_client.aclose())

    assert [entry["id"] for entry in entries] == ["kimi-k3"]
    entry = entries[0]
    assert entry["name"] == "Kimi K3"
    assert entry["api"] == "anthropic-messages"
    assert entry["contextWindow"] == 1_048_576
    assert entry["maxTokens"] == 131_072
    assert entry["cost"] == {
        "input": 3.0,
        "output": 15.0,
        "cacheRead": 0.3,
        "cacheWrite": 0.0,
    }
    assert entry["reasoning"] is True
    assert entry["input"] == ["text", "image"]


def test_the_status_document_reports_how_old_the_sample_is(tmp_path: Path) -> None:
    """A stale sample and a current one produce the same catalog.

    Nothing else in the deployment can tell them apart, so the age has to reach the one
    reader who can act on it — otherwise an operator serves last quarter's prices with
    no way to notice.
    """
    client, http_client = bridge_client(tmp_path, sampled_days_ago=200)
    try:
        with client:
            response = client.get("/api/status")
        assert response.status_code == 200
        reported = response.json()["providers"]["opencode"]["model_info"]
    finally:
        asyncio.run(http_client.aclose())

    assert reported["age_days"] == 200
    assert reported["stale"] is True
    assert reported["retrieved_at"] == (datetime.now(UTC).date() - timedelta(days=200)).isoformat()
    assert reported["path"].endswith("model-info.json")


def test_a_current_sample_is_reported_as_current(tmp_path: Path) -> None:
    client, http_client = bridge_client(tmp_path)
    try:
        with client:
            response = client.get("/api/status")
        reported = response.json()["providers"]["opencode"]["model_info"]
    finally:
        asyncio.run(http_client.aclose())

    assert reported["age_days"] == 0
    assert reported["stale"] is False


def test_a_tiered_price_reaches_the_pi_projection(tmp_path: Path) -> None:
    """The tier shape has to survive the whole path, file to `?format=pi`.

    `_pi_cost` drops the entire cost block when a tier omits a rate instead of degrading
    to the base rate, so a mistake here reads at the client as a free model.
    """
    client, http_client = bridge_client(tmp_path, document=TIERED)
    try:
        with client:
            response = client.get("/v1/models?format=pi")
        assert response.status_code == 200
        entry = response.json()["data"][0]
    finally:
        asyncio.run(http_client.aclose())

    assert entry["cost"] == {
        "input": 3.0,
        "output": 15.0,
        "cacheRead": 0.3,
        "cacheWrite": 0.0,
        "tiers": [
            {
                "inputTokensAbove": 200_000,
                "input": 6.0,
                "output": 30.0,
                "cacheRead": 0.6,
                "cacheWrite": 0.0,
            }
        ],
    }
