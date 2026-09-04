from collections.abc import AsyncIterator, Callable
from copy import deepcopy
from typing import Any
from uuid import UUID

import httpx2
import pytest

from app.config.schema import XingchenProviderConfig
from app.model_provider.xingchen.client import XingchenClient
from app.model_provider.xingchen.signing import SIGN_VERSION, sign_gateway_request
from app.pipeline.exceptions import UpstreamRateLimit, UpstreamRejected, UpstreamTimeout
from app.wire_json import loads

NONCE = UUID("11111111-2222-4333-8444-555555555555")
REQUEST_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")


class OneChunkStream(httpx2.AsyncByteStream):
    def __init__(self, content: bytes) -> None:
        self._content = content

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._content

    async def aclose(self) -> None:
        return None


def config(**overrides: Any) -> XingchenProviderConfig:
    values: dict[str, Any] = {
        "type": "xingchen",
        "models": ["chat-pro", "chat-lite"],
        "gateway_api_key": "gateway-key",
        "x_token": "prefix:header.payload.signature",
        "device_id": "device-id",
        "install_id": "install-id",
    }
    values.update(overrides)
    return XingchenProviderConfig.model_validate(values)


def uuid_sequence(*values: UUID) -> Callable[[], UUID]:
    sequence = iter(values)
    return lambda: next(sequence)


@pytest.mark.asyncio
async def test_stream_request_sends_the_signed_bytes_and_protects_every_owned_header() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            200,
            stream=OneChunkStream(b'data: {"choices":[]}\n\ndata: [DONE]\n\n'),
        )

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    client = XingchenClient(
        http_client,
        config(),
        clock=lambda: 1_700_000_000.9,
        # The first request-id candidate deliberately collides with the nonce.
        uuid_factory=uuid_sequence(NONCE, NONCE, REQUEST_ID),
    )
    payload: dict[str, Any] = {
        "model": "chat-pro",
        "stream": True,
        "messages": [{"role": "user", "content": "ping"}],
    }
    before = deepcopy(payload)
    owned_names = (
        "Authorization",
        "X-Token",
        "X-SuperAgent-Sign-Version",
        "X-SuperAgent-Signature",
        "X-SuperAgent-Timestamp",
        "X-SuperAgent-Nonce",
        "X-SuperAgent-Device-Id",
        "X-SuperAgent-Install-Id",
        "X-App-Version",
        "X-Route-Target",
        "X-TeleAI-Client-Type",
        "X-TeleAI-Upstream-Request-ID",
        "Content-Type",
        "Accept",
        "Cache-Control",
        "User-Agent",
    )
    forged = {name.lower(): "forged" for name in owned_names}
    forged.update(
        {
            "host": "forged.invalid",
            "content-length": "999999",
            "transfer-encoding": "chunked",
            "x-trace-id": "trace-from-client",
        }
    )

    try:
        response = await client.send_chat_completions(
            payload,
            stream=True,
            extra_headers=forged,
        )
        request = seen[0]
        decoded = loads(request.content)

        assert payload == before
        assert isinstance(decoded, dict)
        assert decoded["stream_options"] == {"include_usage": True}
        assert decoded["tool_stream"] is True
        assert request.url.path == "/superCowork/sapi/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer gateway-key"
        assert request.headers["x-token"] == "prefix:header.payload.signature"
        assert request.headers["x-superagent-sign-version"] == SIGN_VERSION == "v1"
        assert request.headers["x-superagent-timestamp"] == "1700000000"
        assert request.headers["x-superagent-nonce"] == str(NONCE)
        assert request.headers["x-superagent-device-id"] == "device-id"
        assert request.headers["x-superagent-install-id"] == "install-id"
        assert request.headers["x-app-version"] == "2.4.1"
        assert request.headers["x-route-target"] == "ops-gateway"
        assert request.headers["x-teleai-client-type"] == "desktop"
        assert request.headers["x-teleai-upstream-request-id"] == str(REQUEST_ID)
        assert request.headers["content-type"] == "application/json"
        assert request.headers["accept"] == "text/event-stream"
        assert request.headers["cache-control"] == "no-cache"
        assert request.headers["user-agent"] == "super-agent/1.0"
        assert request.headers["host"] == "agent.teleai.com.cn"
        assert request.headers["content-length"] == str(len(request.content))
        assert "transfer-encoding" not in request.headers
        assert request.headers["x-trace-id"] == "trace-from-client"

        expected = sign_gateway_request(
            method="POST",
            request_uri=request.url.raw_path.decode("ascii"),
            body=request.content,
            x_token="prefix:header.payload.signature",
            install_id="install-id",
            app_version="2.4.1",
            timestamp="1700000000",
            nonce=str(NONCE),
        )
        assert request.headers["x-superagent-signature"] == expected.value
        for name in owned_names:
            assert request.headers.get_list(name) == [request.headers[name]]
            assert request.headers[name] != "forged"
        assert response.is_stream_consumed is False
        await response.aclose()
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_stream_extensions_preserve_explicit_values_without_mutating_nested_input() -> None:
    seen: list[httpx2.Request] = []
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: seen.append(request) or httpx2.Response(200, content=b"data: [DONE]\n\n")
        )
    )
    client = XingchenClient(
        http_client,
        config(),
        uuid_factory=uuid_sequence(NONCE, REQUEST_ID),
    )
    payload: dict[str, Any] = {
        "model": "chat-pro",
        "stream": True,
        "stream_options": {"include_usage": False, "future": "kept"},
        "tool_stream": False,
    }
    before = deepcopy(payload)

    try:
        response = await client.send_chat_completions(payload, stream=True)
        decoded = loads(seen[0].content)
        assert decoded == payload
        assert payload == before
        await response.aclose()
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_nonstream_request_does_not_inject_stream_extensions() -> None:
    seen: list[httpx2.Request] = []
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: seen.append(request) or httpx2.Response(200, json={"choices": []})
        )
    )
    client = XingchenClient(
        http_client,
        config(),
        uuid_factory=uuid_sequence(NONCE, REQUEST_ID),
    )

    try:
        await client.send_chat_completions({"model": "chat-pro"})
    finally:
        await http_client.aclose()

    decoded = loads(seen[0].content)
    assert isinstance(decoded, dict)
    assert "stream_options" not in decoded
    assert "tool_stream" not in decoded
    assert seen[0].headers["accept"] == "application/json"


@pytest.mark.asyncio
async def test_http_rejection_keeps_response_and_sent_body_bytes() -> None:
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(
                400,
                headers={"content-type": "application/json"},
                content=b'{"error":"bad request"}',
            )
        )
    )
    client = XingchenClient(
        http_client,
        config(),
        uuid_factory=uuid_sequence(NONCE, REQUEST_ID),
    )

    try:
        with pytest.raises(UpstreamRejected) as raised:
            await client.send_chat_completions({"model": "chat-pro"}, stream=True)
    finally:
        await http_client.aclose()

    assert raised.value.status_code == 400
    assert raised.value.body_bytes == b'{"error":"bad request"}'
    assert raised.value.sent == b'{"model":"chat-pro","stream_options":{"include_usage":true},"tool_stream":true}'


@pytest.mark.asyncio
async def test_retry_after_ms_is_normalized_for_rate_limits() -> None:
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(429, headers={"Retry-After-Ms": "1500"}, content=b"later")
        )
    )
    client = XingchenClient(
        http_client,
        config(),
        uuid_factory=uuid_sequence(NONCE, REQUEST_ID),
    )

    try:
        with pytest.raises(UpstreamRateLimit) as raised:
            await client.send_chat_completions({"model": "chat-pro"})
    finally:
        await http_client.aclose()

    assert raised.value.retry_after == 1.5
    assert raised.value.body_bytes == b"later"


@pytest.mark.asyncio
async def test_httpx_timeout_uses_the_pipeline_timeout_carrier() -> None:
    def timeout(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(timeout))
    client = XingchenClient(
        http_client,
        config(),
        uuid_factory=uuid_sequence(NONCE, REQUEST_ID),
    )

    try:
        with pytest.raises(UpstreamTimeout):
            await client.send_chat_completions({"model": "chat-pro"})
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_unknown_local_exception_is_not_disguised_as_upstream_failure() -> None:
    def fail(_: httpx2.Request) -> httpx2.Response:
        raise KeyError("local bug")

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(fail))
    client = XingchenClient(
        http_client,
        config(),
        uuid_factory=uuid_sequence(NONCE, REQUEST_ID),
    )

    try:
        with pytest.raises(KeyError, match="local bug"):
            await client.send_chat_completions({"model": "chat-pro"})
    finally:
        await http_client.aclose()
