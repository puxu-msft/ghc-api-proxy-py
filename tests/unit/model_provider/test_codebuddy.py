"""The CodeBuddy provider against the `ModelProvider` protocol: static catalog,
endpoint gating, and the send/count paths.
"""

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest

from app.config.schema import CodebuddyProviderConfig
from app.model_provider import (
    EndpointNotSupported,
    ModelEndpoint,
    UnknownModel,
)
from app.model_provider.codebuddy import DRIVEN_ENDPOINTS, CodebuddyProvider
from app.model_provider.codebuddy_client import (
    CodebuddyClient,
    CodebuddyClientConfig,
    CodebuddyCredentials,
    DesktopAuthState,
)
from app.model_provider.codebuddy_client.models import DEFAULT_MODEL_IDS


def _refusing_handler(request: httpx2.Request) -> httpx2.Response:
    """Every test here asserts on behaviour *before* the network, so any handler will do — but a 500 makes an accidental network call loud."""
    return httpx2.Response(500)


def build_provider(
    tmp_path: Path,
    handler: Callable[[httpx2.Request], httpx2.Response] = _refusing_handler,
    *,
    disabled: list[str] | None = None,
) -> CodebuddyProvider:
    state_file = tmp_path / "state.info"
    state_file.write_text(
        json.dumps(
            {
                "auth": {
                    "accessToken": "t",
                    "refreshToken": "r",
                    "expiresAt": int(time.time() * 1000) + 3_600_000,
                },
                "account": {"uid": "u"},
            }
        ),
        encoding="utf-8",
    )
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    credentials = CodebuddyCredentials(
        DesktopAuthState(str(state_file)), http_client, CodebuddyClientConfig()
    )
    client = CodebuddyClient(
        CodebuddyClientConfig(api_base_url_override="https://cb.example"),
        credentials,
        http_client=http_client,
    )
    config = CodebuddyProviderConfig(type="codebuddy", disabled_models=disabled or [])
    return CodebuddyProvider("cb", client, config, base_url="https://cb.example")


def test_the_static_catalog_is_served_and_stamped(tmp_path: Path) -> None:
    provider = build_provider(tmp_path)

    assert provider.available_ids == frozenset(DEFAULT_MODEL_IDS)
    assert provider.catalog_refreshed_at != ""
    assert provider.base_url == "https://cb.example"
    # The raw catalog keeps the Copilot wire shape, so one reader serves both providers.
    assert provider.raw_catalog["object"] == "list"
    assert {entry["id"] for entry in provider.raw_catalog["data"]} == set(DEFAULT_MODEL_IDS)


def test_every_model_advertises_exactly_chat_completions(tmp_path: Path) -> None:
    provider = build_provider(tmp_path)

    descriptor = provider.describe(DEFAULT_MODEL_IDS[0])
    assert descriptor is not None
    assert descriptor.endpoints == frozenset({ModelEndpoint.OPENAI_CHAT_COMPLETIONS})


def test_refresh_catalog_reports_unchanged(tmp_path: Path) -> None:
    provider = build_provider(tmp_path)

    assert asyncio.run(provider.refresh_catalog()) is False


def test_disabled_models_are_not_on_offer(tmp_path: Path) -> None:
    provider = build_provider(tmp_path, disabled=[DEFAULT_MODEL_IDS[0]])

    assert provider.describe(DEFAULT_MODEL_IDS[0]) is None
    assert provider.disabled_ids == frozenset({DEFAULT_MODEL_IDS[0]})


def test_an_unknown_model_is_refused_before_the_network(tmp_path: Path) -> None:
    provider = build_provider(tmp_path)

    with pytest.raises(UnknownModel):
        asyncio.run(
            provider.send(
                ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
                {"model": "nope"},
                model_id="nope",
            )
        )


def test_the_messages_endpoint_is_refused_by_the_gate(tmp_path: Path) -> None:
    """Anthropic clients reach this provider translated; the gate is what enforces it."""
    provider = build_provider(tmp_path)
    model_id = DEFAULT_MODEL_IDS[0]

    with pytest.raises(EndpointNotSupported):
        asyncio.run(
            provider.send(
                ModelEndpoint.ANTHROPIC_MESSAGES,
                {"model": model_id},
                model_id=model_id,
            )
        )


def test_count_tokens_is_gated_the_same_way(tmp_path: Path) -> None:
    """Refused at the gate, so the counting chain falls through to its next leg."""
    provider = build_provider(tmp_path)
    model_id = DEFAULT_MODEL_IDS[0]

    with pytest.raises(EndpointNotSupported):
        asyncio.run(provider.count_tokens({"model": model_id}, model_id=model_id))


def test_the_driven_table_matches_the_send_path() -> None:
    assert frozenset({ModelEndpoint.OPENAI_CHAT_COMPLETIONS}) == DRIVEN_ENDPOINTS
