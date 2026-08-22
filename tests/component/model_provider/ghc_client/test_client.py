from collections.abc import AsyncIterator, Callable

import httpx2
import openai
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.model_provider.ghc_client import GhcApiClient, GhcClientConfig
from app.model_provider.ghc_client.tokens import CopilotTokenManager
from app.pipeline.exceptions import UpstreamRateLimit

BASE_URL = "https://copilot.example"


class StaticTokenSource:
    async def get_token(self) -> str:
        return "ghu_github"

    async def refresh(self) -> str | None:
        return None


class RawByteStream(httpx2.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"data: raw\n\n"


def build_client(
    handler: Callable[[httpx2.Request], httpx2.Response],
) -> tuple[GhcApiClient, httpx2.AsyncClient]:
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
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
        GhcClientConfig(api_base_url_override=BASE_URL),
        interaction_id="interaction",
    )
    return client, http_client


def token_or(response: httpx2.Response) -> Callable[[httpx2.Request], httpx2.Response]:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "api.github.com":
            return httpx2.Response(
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
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "api.github.com":
            return httpx2.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

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
    client, http_client = build_client(token_or(httpx2.Response(200, stream=RawByteStream())))
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
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "api.github.com":
            return httpx2.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

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
async def test_a_forwarded_header_never_travels_beside_the_one_it_collides_with() -> None:
    """The proxy's own value wins, and the loser does not come along for the ride.

    `request_headers` merged with `{**extra, **owned}`, which only lets the owned value win when the two spellings are byte-equal — and they are not. This library writes `Authorization` capitalised; a header forwarded from a client arrives lowercased. Two dict keys, both surviving, and on the Responses leg `_build_request` reads `multi_items()` and puts **both** on the wire. This asserts on `get_list`, not on `headers[...]`, because a lookup by name folds the case and reports the winner either way — it cannot see the second line at all.
    """
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "api.github.com":
            return httpx2.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

    client, http_client = build_client(handler)
    try:
        await client.send_anthropic_messages(
            {"model": "m"},
            extra_headers={
                "authorization": "Bearer client-secret",
                "x-interaction-id": "client-chosen",
                "anthropic-beta": "probe",
            },
        )
    finally:
        await http_client.aclose()

    sent = seen[0].headers
    assert sent.get_list("authorization") == ["Bearer copilot"]
    assert "client-secret" not in str(sent)
    assert sent.get_list("x-interaction-id") == [sent["x-interaction-id"]]
    assert sent["x-interaction-id"] != "client-chosen"
    # The one that does not collide still travels; this drops colliding names, not forwarding.
    assert sent["anthropic-beta"] == "probe"


@pytest.mark.asyncio
async def test_ordinary_send_raises_in_the_pipelines_vocabulary() -> None:
    """The asymmetry this guards is unchanged; the exception it raises is not.

    An ordinary send still raises where `send_responses_headers` returns. It used to raise the
    SDK's own `openai.RateLimitError`, which is outside the driver's closed set, so `classify`
    aborted and the 429 reached the client as a 502 with no retry ever considered.
    """
    client, http_client = build_client(
        token_or(httpx2.Response(429, json={"error": "slow down"}, headers={"retry-after": "7"}))
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
    client, http_client = build_client(token_or(httpx2.Response(429, json={"error": "slow down"})))
    try:
        response = await client.send_responses_headers({"model": "m"})
    finally:
        await http_client.aclose()

    assert response.status_code == 429
