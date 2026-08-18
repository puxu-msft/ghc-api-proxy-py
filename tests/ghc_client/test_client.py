from collections.abc import AsyncIterator, Callable

import httpx
import openai
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.ghc_client import GhcApiClient, GhcClientConfig
from app.ghc_client.tokens import CopilotTokenManager
from app.pipeline.exceptions import UpstreamRateLimit

BASE_URL = "https://copilot.example"


class StaticTokenSource:
    async def get_token(self) -> str:
        return "ghu_github"

    async def refresh(self) -> str | None:
        return None


class RawByteStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"data: raw\n\n"


def build_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[GhcApiClient, httpx.AsyncClient]:
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
    return client, http_client


def token_or(response: httpx.Response) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        return response

    return handler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("send_chat_completions", "/chat/completions"),
        ("send_responses", "/responses"),
        ("send_embeddings", "/embeddings"),
        ("send_anthropic_messages", "/v1/messages"),
        ("send_anthropic_count_tokens", "/v1/messages/count_tokens"),
    ],
)
async def test_each_endpoint_is_posted_with_copilot_auth(method: str, path: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client, http_client = build_client(handler)
    try:
        await getattr(client, method)({"model": "any-model"})
    finally:
        await http_client.aclose()

    assert len(seen) == 1
    assert seen[0].url == f"{BASE_URL}{path}"
    assert seen[0].method == "POST"
    assert seen[0].headers["authorization"] == "Bearer copilot"
    assert seen[0].headers["x-interaction-id"] == "interaction"


@pytest.mark.asyncio
async def test_streaming_response_is_returned_unconsumed() -> None:
    client, http_client = build_client(token_or(httpx.Response(200, stream=RawByteStream())))
    try:
        response = await client.send_anthropic_messages({"model": "m"}, stream=True)
        assert response.is_stream_consumed is False
        body = await response.aread()
        await response.aclose()
    finally:
        await http_client.aclose()

    assert body == b"data: raw\n\n"


@pytest.mark.asyncio
async def test_extra_headers_reach_the_anthropic_leg() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client, http_client = build_client(handler)
    try:
        await client.send_anthropic_messages(
            {"model": "m"},
            extra_headers={"anthropic-beta": "probe"},
        )
    finally:
        await http_client.aclose()

    assert seen[0].headers["anthropic-beta"] == "probe"


@pytest.mark.asyncio
async def test_ordinary_send_raises_in_the_pipelines_vocabulary() -> None:
    """The asymmetry this guards is unchanged; the exception it raises is not.

    An ordinary send still raises where `send_responses_headers` returns. It used to raise the
    SDK's own `openai.RateLimitError`, which is outside the driver's closed set, so `classify`
    aborted and the 429 reached the client as a 502 with no retry ever considered.
    """
    client, http_client = build_client(
        token_or(httpx.Response(429, json={"error": "slow down"}, headers={"retry-after": "7"}))
    )
    try:
        with pytest.raises(UpstreamRateLimit) as raised:
            await client.send_responses({"model": "m"})
    finally:
        await http_client.aclose()

    assert raised.value.status_code == 429
    assert raised.value.retry_after == 7.0
    # The SDK error is still reachable, so nothing about the cause is lost in translation.
    assert isinstance(raised.value.__cause__, openai.RateLimitError)


@pytest.mark.asyncio
async def test_responses_headers_returns_the_error_response_instead_of_raising() -> None:
    client, http_client = build_client(token_or(httpx.Response(429, json={"error": "slow down"})))
    try:
        response = await client.send_responses_headers({"model": "m"})
    finally:
        await http_client.aclose()

    assert response.status_code == 429
