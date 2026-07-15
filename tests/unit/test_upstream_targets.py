from collections.abc import AsyncIterator

import httpx
import pytest

from app.auth.copilot import CopilotTokenManager
from app.auth.providers import GitHubTokenManager, GitHubTokenProvider, TokenInfo
from app.config.settings import AppSettings
from app.upstream.client import create_copilot_sdk_clients, create_sdk_clients
from app.upstream.copilot import CopilotUpstream
from app.upstream.generic import GenericUpstream


class RawByteStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"data: raw\n\n"


class StaticProvider(GitHubTokenProvider):
    name = "static"
    priority = 1
    refreshable = False

    async def is_available(self) -> bool:
        return True

    async def get_token(self) -> TokenInfo:
        return TokenInfo(token="ghu", source="env")


@pytest.mark.asyncio
async def test_copilot_upstream_returns_unconsumed_raw_anthropic_response() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        return httpx.Response(200, stream=RawByteStream())

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = AppSettings.model_validate(
        {"upstream": {"ghc_api_base_url": "https://copilot.example"}}
    )
    token_manager = CopilotTokenManager(
        GitHubTokenManager([StaticProvider()]),
        http_client,
        clock=lambda: 1000,
    )
    clients = create_copilot_sdk_clients(settings, http_client=http_client)
    upstream = CopilotUpstream(
        clients,
        token_manager,
        settings,
        interaction_id="interaction",
    )
    try:
        response = await upstream.send_anthropic(
            {"model": "claude-test", "messages": [], "stream": True},
            stream=True,
        )
        assert response.is_stream_consumed is False
        body = await response.aread()
        await response.aclose()
    finally:
        await http_client.aclose()

    assert body == b"data: raw\n\n"
    request = seen[-1]
    assert request.url == "https://copilot.example/v1/messages"
    assert request.headers["authorization"] == "Bearer copilot"
    assert request.headers["x-interaction-id"] == "interaction"


@pytest.mark.asyncio
async def test_generic_upstream_uses_protocol_specific_sdk_base_urls() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = AppSettings.model_validate(
        {
            "upstream": {
                "openai_base_url": "https://openai.example/v1",
                "anthropic_base_url": "https://anthropic.example",
                "api_key": "key",
            }
        }
    )
    clients = create_sdk_clients(settings, http_client=http_client)
    upstream = GenericUpstream(clients)
    try:
        chat = await upstream.send_openai({"model": "gpt", "messages": []})
        messages = await upstream.send_anthropic(
            {"model": "claude", "messages": [], "max_tokens": 10}
        )
        responses = await upstream.send_responses({"model": "gpt", "input": []})
        await chat.aread()
        await messages.aread()
        await responses.aread()
    finally:
        await http_client.aclose()

    assert paths == [
        "https://openai.example/v1/chat/completions",
        "https://anthropic.example/v1/messages",
        "https://openai.example/v1/responses",
    ]