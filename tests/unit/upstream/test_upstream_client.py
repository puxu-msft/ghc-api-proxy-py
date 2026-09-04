import httpx2
import pytest

from app.config.settings import AppSettings
from app.upstream.client import SDKClients, create_http_client, create_sdk_clients
from app.upstream.copilot import build_copilot_headers
from app.upstream.urls import resolve_copilot_base_url


def test_copilot_base_url_prefers_explicit_override() -> None:
    settings = AppSettings.model_validate(
        {
            "auth": {"account_type": "enterprise"},
            "upstream": {"ghc_api_base_url": "https://custom.example/"},
        }
    )

    assert resolve_copilot_base_url(settings) == "https://custom.example"


@pytest.mark.parametrize(
    ("account_type", "expected"),
    [
        ("individual", "https://api.githubcopilot.com"),
        ("business", "https://api.business.githubcopilot.com"),
        ("enterprise", "https://api.enterprise.githubcopilot.com"),
    ],
)
def test_copilot_base_url_maps_account_type(account_type: str, expected: str) -> None:
    settings = AppSettings.model_validate({"auth": {"account_type": account_type}})

    assert resolve_copilot_base_url(settings) == expected


def test_copilot_base_url_falls_back_to_individual_when_account_type_is_unset() -> None:
    assert resolve_copilot_base_url(AppSettings()) == "https://api.githubcopilot.com"


def test_legacy_upstream_protocol_reaches_the_actual_pool() -> None:
    default_client = create_http_client(AppSettings())
    enabled_client = create_http_client(
        AppSettings.model_validate({"upstream": {"http2": True}})
    )
    default_transport = default_client._transport  # pyright: ignore[reportPrivateUsage]
    enabled_transport = enabled_client._transport  # pyright: ignore[reportPrivateUsage]
    assert isinstance(default_transport, httpx2.AsyncHTTPTransport)
    assert isinstance(enabled_transport, httpx2.AsyncHTTPTransport)
    assert default_transport._pool._http2 is False  # pyright: ignore[reportPrivateUsage]
    assert enabled_transport._pool._http2 is True  # pyright: ignore[reportPrivateUsage]


def test_copilot_headers_protect_core_values_from_model_headers() -> None:
    settings = AppSettings()

    headers = build_copilot_headers(
        "copilot-token",
        settings,
        interaction_id="interaction",
        request_id="request",
        intent="conversation-agent",
        model_request_headers={
            "Authorization": "attacker",
            "x-model-route": "route-a",
        },
    )

    assert headers["Authorization"] == "Bearer copilot-token"
    assert headers["X-Interaction-Id"] == "interaction"
    assert headers["X-Agent-Task-Id"] == "request"
    assert headers["openai-intent"] == "conversation-agent"
    assert headers["x-model-route"] == "route-a"


@pytest.mark.asyncio
async def test_sdk_clients_share_http_pool_and_disable_retries() -> None:
    settings = AppSettings.model_validate(
        {"upstream": {"openai_base_url": "https://openai.example", "anthropic_base_url": "https://anthropic.example"}}
    )
    http_client = create_http_client(settings)
    clients: SDKClients | None = None
    try:
        clients = create_sdk_clients(settings, http_client=http_client)
        assert clients.openai.max_retries == 0
        assert clients.anthropic.max_retries == 0
    finally:
        if clients is not None:
            await clients.close()

    assert http_client.is_closed is True


def test_http_client_has_no_transport_retry_wrapper() -> None:
    client = create_http_client(AppSettings())

    assert isinstance(client, httpx2.AsyncClient)
