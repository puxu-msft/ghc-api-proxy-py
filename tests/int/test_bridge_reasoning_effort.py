import asyncio
from collections.abc import Callable
from typing import cast

import httpx2
import orjson
import pytest
from fastapi.testclient import TestClient

from app.config.schema import OpenAICompatibleProviderConfig, ProxyConfig
from app.core.chain import Chain
from app.model_provider import ModelProvider, OpenAICompatibleProvider
from app.model_provider.openai_compatible import OpenAICompatibleClient
from app.observability.request_log_file import request_logs_dir
from app.pipeline.direct_driver import EVENT_ATTEMPT_PREPARE
from app.pipeline.events import FrozenSubscribers, Subscription
from app.pipeline.request import RequestContext
from app.server.composition import build_chain
from app.server.pipeline_app import create_pipeline_app


def _bridge_app(
    *,
    reasoning_efforts: list[str],
    configure_chain: Callable[[Chain], None] | None = None,
) -> tuple[TestClient, httpx2.AsyncClient, list[httpx2.Request], list[dict[str, object]]]:
    seen: list[httpx2.Request] = []
    prepared: list[dict[str, object]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/v1/models":
            return httpx2.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "bridge-model",
                            "supported_endpoints": ["/responses"],
                        }
                    ],
                },
            )
        seen.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "resp_1",
                "object": "response",
                "model": "bridge-model",
                "output": [],
                "status": "completed",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 0,
                    "total_tokens": 1,
                },
            },
        )

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = OpenAICompatibleProviderConfig.model_validate(
        {
            "type": "bridge",
            "api_base_url": "https://bridge.example/v1",
            "api_key": "test-key",
            "models": ["bridge-model"],
            "openai_responses_endpoint": True,
            "reasoning_efforts": {"bridge-model": reasoning_efforts},
        }
    )
    provider = OpenAICompatibleProvider(
        "bridge",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "bridge",
            "model_providers": {"bridge": provider_config.model_dump(mode="python")},
        }
    )
    chain = build_chain(
        config,
        http_client=http_client,
        providers={"bridge": cast(ModelProvider, provider)},
    )
    if configure_chain is not None:
        configure_chain(chain)
    return TestClient(create_pipeline_app(chain)), http_client, seen, prepared


@pytest.mark.parametrize(
    ("request_fields", "expected_effort"),
    [
        ({}, "high"),
        ({"output_config": {"effort": "xhigh"}}, "xhigh"),
        ({"thinking": {"type": "disabled"}}, "none"),
    ],
)
def test_messages_to_bridge_sends_the_resolved_reasoning_effort(
    request_fields: dict[str, object],
    expected_effort: str,
) -> None:
    client, http_client, seen, _ = _bridge_app(
        reasoning_efforts=["none", "high", "xhigh"]
    )
    try:
        with client:
            response = client.post(
                "/v1/messages",
                json={
                    "model": "bridge-model",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 64,
                    **request_fields,
                },
            )
        assert response.status_code == 200
        assert len(seen) == 1
        payload = cast(dict[str, object], orjson.loads(seen[0].content))
        assert payload["reasoning"] == {"effort": expected_effort}
        records = [
            cast(dict[str, object], orjson.loads(line))
            for path in sorted(request_logs_dir().glob("requests-*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        assert records[-1]["reasoning_effort"] == expected_effort
    finally:
        asyncio.run(http_client.aclose())


def test_missing_bridge_effort_is_not_logged_as_explicit_none() -> None:
    client, http_client, seen, _ = _bridge_app(reasoning_efforts=[])
    try:
        with client:
            response = client.post(
                "/v1/messages",
                json={
                    "model": "bridge-model",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 64,
                },
            )
        assert response.status_code == 200
        assert len(seen) == 1
        payload = cast(dict[str, object], orjson.loads(seen[0].content))
        assert "reasoning" not in payload
        records = [
            cast(dict[str, object], orjson.loads(line))
            for path in sorted(request_logs_dir().glob("requests-*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        assert records[-1]["reasoning_effort"] is None
    finally:
        asyncio.run(http_client.aclose())


def test_models_endpoint_reports_the_effective_bridge_reasoning_capability() -> None:
    client, http_client, _, _ = _bridge_app(reasoning_efforts=["high", "xhigh"])
    try:
        with client:
            response = client.get("/v1/models?format=pi")
        assert response.status_code == 200
        model = response.json()["data"][0]
        assert model["id"] == "bridge-model"
        assert model["reasoning"] is True
    finally:
        asyncio.run(http_client.aclose())


def test_count_tokens_prepares_the_same_reasoning_effort_as_messages() -> None:
    def capture_prepare(chain: Chain) -> None:
        subscribers = chain.subscribers
        events = {
            event: list(subscribers.for_event(event))
            for event in subscribers.events
        }

        async def capture(context: RequestContext) -> None:
            if context.extras.get("counting_only") is True:
                prepared.append(dict(context.payload))

        events.setdefault(EVENT_ATTEMPT_PREPARE, []).append(
            Subscription(id="test:capture-count-reasoning", handler=capture)
        )
        chain.subscribers = FrozenSubscribers(events)

    client, http_client, seen, prepared = _bridge_app(
        reasoning_efforts=["high"],
        configure_chain=capture_prepare,
    )
    try:
        with client:
            response = client.post(
                "/v1/messages/count_tokens",
                json={
                    "model": "bridge-model",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
        assert response.status_code == 200
        assert response.json()["estimated"] is True
        assert seen == []
        assert len(prepared) == 1
        assert prepared[0]["reasoning"] == {"effort": "high"}
    finally:
        asyncio.run(http_client.aclose())
