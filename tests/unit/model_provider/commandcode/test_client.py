import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx2
import pytest

from app.config.schema import CommandCodeProviderConfig
from app.model_provider.commandcode.client import (
    FINGERPRINT_PATH,
    LIFECYCLE_PATH,
    CommandCodeClient,
)
from app.pipeline.exceptions import UpstreamRateLimit


class _ChunkedStream(httpx2.AsyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


def test_commandcode_client_uses_provider_headers_and_aggregates_ndjson() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            200,
            content=(
                b'{"type":"text-delta","text":"hello"}\n'
                b'{"type":"text-end"}\n'
                b'{"type":"finish","finishReason":"stop","totalUsage":{"inputTokens":3,"outputTokens":1}}\n'
            ),
            headers={"content-type": "application/x-ndjson"},
        )

    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "initialize_upstream": False,
        }
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> tuple[dict[str, Any], bytes]:
        try:
            response = await CommandCodeClient(http, config).send(
                {
                    "params": {
                        "model": "m",
                        "messages": [{"role": "user", "content": []}],
                    }
                },
                stream=False,
                interaction_id="session-123",
            )
            return response.json(), response.extensions["upstream_raw_response_body"]
        finally:
            await http.aclose()

    body, raw_body = asyncio.run(run())
    assert body["events"][0]["type"] == "text-delta"
    assert raw_body == (
        b'{"type":"text-delta","text":"hello"}\n'
        b'{"type":"text-end"}\n'
        b'{"type":"finish","finishReason":"stop","totalUsage":{"inputTokens":3,"outputTokens":1}}\n'
    )
    assert seen[0].url.path == "/alpha/generate"
    assert seen[0].headers["authorization"] == "Bearer user_test"
    assert seen[0].headers["x-session-id"] == "session-123"
    sent = json.loads(seen[0].content)
    assert sent["params"]["stream"] is not False
    assert sent["params"]["system"] == " "


def test_commandcode_client_aggregates_fragmented_ndjson_without_losing_lines() -> None:
    upstream_body = (
        b'{"type":"text-delta","text":"hello"}\n'
        b'{"type":"text-end"}\n'
        b'{"type":"finish","finishReason":"stop","totalUsage":{"outputTokens":1}}\n'
    )
    chunks = tuple(upstream_body[index : index + 3] for index in range(0, len(upstream_body), 3))

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            stream=_ChunkedStream(chunks),
            headers={"content-type": "application/x-ndjson"},
        )

    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "initialize_upstream": False,
        }
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> tuple[dict[str, Any], bytes]:
        try:
            response = await CommandCodeClient(http, config).send(
                {"params": {"model": "m", "messages": []}},
                stream=False,
            )
            return response.json(), response.extensions["upstream_raw_response_body"]
        finally:
            await http.aclose()

    body, raw_body = asyncio.run(run())
    assert [event["type"] for event in body["events"]] == [
        "text-delta",
        "text-end",
        "finish",
    ]
    assert raw_body == upstream_body


def test_commandcode_client_uses_request_scoped_zdr_without_changing_provider_defaults() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            200,
            content=(
                b'{"type":"text-delta","text":"ok"}\n'
                b'{"type":"text-end"}\n'
                b'{"type":"finish","finishReason":"stop","totalUsage":{"outputTokens":1}}\n'
            ),
            headers={"content-type": "application/x-ndjson"},
        )

    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "zdr": False,
            "command_code_version": "pinned-test-version",
            "initialize_upstream": False,
        }
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> None:
        try:
            await CommandCodeClient(http, config).send(
                {"params": {"model": "m", "messages": []}},
                stream=False,
                extra_headers={"x-cmd-zdr": "1"},
            )
        finally:
            await http.aclose()

    asyncio.run(run())
    assert seen[0].headers["x-cmd-zdr"] == "1"
    assert seen[0].headers["x-command-code-version"] == "pinned-test-version"


def test_commandcode_client_preserves_buffered_transport_metadata_without_stream() -> None:
    upstream_body = (
        b'{"type":"text-delta","text":"hello"}\n'
        b'{"type":"text-end"}\n'
        b'{"type":"finish","finishReason":"stop","totalUsage":{"outputTokens":1}}\n'
    )
    transport_stream = object()

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            content=upstream_body,
            headers={"content-type": "application/x-ndjson"},
            extensions={
                "http_version": b"HTTP/2",
                "network_stream": transport_stream,
                "stream_id": 17,
                "connection_diagnostic": {"route": "h2"},
            },
        )

    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "initialize_upstream": False,
        }
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> tuple[str, dict[str, Any]]:
        try:
            response = await CommandCodeClient(http, config).send(
                {"params": {"model": "m", "messages": []}},
                stream=False,
            )
            return response.http_version, dict(response.extensions)
        finally:
            await http.aclose()

    http_version, extensions = asyncio.run(run())
    assert http_version == "HTTP/2"
    assert extensions["stream_id"] == 17
    assert extensions["connection_diagnostic"] == {"route": "h2"}
    assert extensions["upstream_raw_response_body"] == upstream_body
    assert extensions["upstream_transport_status_code"] == 200
    assert extensions["upstream_transport_headers"]["content-type"] == "application/x-ndjson"
    assert "network_stream" not in extensions


def test_commandcode_client_fetches_the_provider_catalog_without_generation_aggregation() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        assert request.url.path == "/provider/v1/models"
        assert "x-cmd-zdr" not in request.headers
        return httpx2.Response(
            200,
            json={"object": "list", "data": [{"id": "m"}]},
        )

    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "fingerprint_mode": "generated",
            "zdr": True,
        }
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> dict[str, Any]:
        try:
            return await CommandCodeClient(http, config).fetch_models()
        finally:
            await http.aclose()

    assert asyncio.run(run())["data"][0]["id"] == "m"


def test_commandcode_initialization_retries_after_partial_failure() -> None:
    attempts = {FINGERPRINT_PATH: 0, LIFECYCLE_PATH: 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path in attempts:
            assert request.headers["x-cmd-zdr"] == "1"
            attempts[path] += 1
            status = 500 if path == FINGERPRINT_PATH and attempts[path] == 1 else 200
            return httpx2.Response(status)
        assert request.headers["x-cmd-zdr"] == "1"
        return httpx2.Response(
            200,
            content=(
                b'{"type":"text-delta","text":"ok"}\n'
                b'{"type":"text-end"}\n'
                b'{"type":"finish","finishReason":"stop","totalUsage":{"outputTokens":1}}\n'
            ),
            headers={"content-type": "application/x-ndjson"},
        )

    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "fingerprint_mode": "generated",
            "zdr": True,
        }
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> None:
        try:
            client = CommandCodeClient(http, config)
            payload: dict[str, Any] = {"params": {"model": "m", "messages": []}}
            await client.send(payload, stream=False)
            await client.send(payload, stream=False)
        finally:
            await http.aclose()

    asyncio.run(run())
    assert attempts == {FINGERPRINT_PATH: 2, LIFECYCLE_PATH: 2}


def test_commandcode_initialization_refresh_window_requires_both_successes() -> None:
    attempts = {FINGERPRINT_PATH: 0, LIFECYCLE_PATH: 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path in attempts:
            attempts[path] += 1
            return httpx2.Response(204)
        return httpx2.Response(
            200,
            content=(
                b'{"type":"text-delta","text":"ok"}\n'
                b'{"type":"text-end"}\n'
                b'{"type":"finish","finishReason":"stop","totalUsage":{"outputTokens":1}}\n'
            ),
            headers={"content-type": "application/x-ndjson"},
        )

    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "fingerprint_mode": "generated",
        }
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> None:
        try:
            client = CommandCodeClient(http, config)
            payload: dict[str, Any] = {"params": {"model": "m", "messages": []}}
            await client.send(payload, stream=False)
            await client.send(payload, stream=False)
        finally:
            await http.aclose()

    asyncio.run(run())
    assert attempts == {FINGERPRINT_PATH: 1, LIFECYCLE_PATH: 1}


def test_commandcode_initialization_skips_fingerprint_by_default() -> None:
    attempts = {FINGERPRINT_PATH: 0, LIFECYCLE_PATH: 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path in attempts:
            attempts[path] += 1
            return httpx2.Response(204)
        return httpx2.Response(
            200,
            content=(
                b'{"type":"text-delta","text":"ok"}\n'
                b'{"type":"text-end"}\n'
                b'{"type":"finish","finishReason":"stop","totalUsage":{"outputTokens":1}}\n'
            ),
            headers={"content-type": "application/x-ndjson"},
        )

    config = CommandCodeProviderConfig.model_validate(
        {"type": "commandcode", "api_key": "user_test"}
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> None:
        try:
            await CommandCodeClient(http, config).send(
                {"params": {"model": "m", "messages": []}},
                stream=False,
            )
        finally:
            await http.aclose()

    asyncio.run(run())
    assert attempts == {FINGERPRINT_PATH: 0, LIFECYCLE_PATH: 1}


def test_commandcode_client_reuses_fallback_session_without_interaction_header() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["x-session-id"])
        return httpx2.Response(
            200,
            content=(
                b'{"type":"text-delta","text":"ok"}\n'
                b'{"type":"text-end"}\n'
                b'{"type":"finish","finishReason":"stop","totalUsage":{"outputTokens":1}}\n'
            ),
            headers={"content-type": "application/x-ndjson"},
        )

    config = CommandCodeProviderConfig.model_validate(
        {"type": "commandcode", "api_key": "user_test", "initialize_upstream": False}
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> None:
        try:
            client = CommandCodeClient(http, config)
            payload: dict[str, Any] = {"params": {"model": "m", "messages": []}}
            await client.send(payload, stream=False)
            await client.send(payload, stream=False)
        finally:
            await http.aclose()

    asyncio.run(run())
    assert len(seen) == 2
    assert seen[0] == seen[1]


def test_commandcode_client_uses_prompt_cache_key_as_session_fallback() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["x-session-id"])
        return httpx2.Response(
            200,
            content=(
                b'{"type":"text-delta","text":"ok"}\n'
                b'{"type":"text-end"}\n'
                b'{"type":"finish","finishReason":"stop","totalUsage":{"outputTokens":1}}\n'
            ),
            headers={"content-type": "application/x-ndjson"},
        )

    config = CommandCodeProviderConfig.model_validate(
        {"type": "commandcode", "api_key": "user_test", "initialize_upstream": False}
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> None:
        try:
            await CommandCodeClient(http, config).send(
                {
                    "prompt_cache_key": "cache-session",
                    "params": {"model": "m", "messages": []},
                },
                stream=False,
            )
        finally:
            await http.aclose()

    asyncio.run(run())
    assert seen == ["cache-session"]


@pytest.mark.parametrize(
    ("events", "message"),
    [
        (
            b'{"type":"text-delta","text":"ok"}\n'
            b'{"type":"text-end"}\n'
            b'{"type":"finish","finishReason":"stop"}\n',
            "no usage",
        ),
        (
            b'{"type":"text-delta","text":"ok"}\n'
            b'{"type":"text-end"}\n'
            b'{"type":"finish","finishReason":"stop","totalUsage":{"outputTokens":0}}\n',
            "zero output tokens",
        ),
        (
            b'{"type":"text-delta","text":"ok"}\n'
            b'{"type":"text-end"}\n',
            "terminal event",
        ),
    ],
)
def test_commandcode_client_retries_instead_of_returning_incomplete_success(
    events: bytes,
    message: str,
) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            content=events,
            headers={"content-type": "application/x-ndjson"},
        )

    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "initialize_upstream": False,
        }
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> None:
        try:
            with pytest.raises(UpstreamRateLimit, match=message):
                await CommandCodeClient(http, config).send(
                    {"params": {"model": "m", "messages": []}},
                    stream=False,
                )
        finally:
            await http.aclose()

    asyncio.run(run())


def test_commandcode_client_keeps_transport_status_separate_from_ndjson_error_status() -> None:
    upstream_body = b'{"type":"error","message":"<429> overloaded"}\n'

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            content=upstream_body,
            headers={
                "content-type": "application/x-ndjson",
                "x-request-id": "transport-request",
            },
        )

    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "initialize_upstream": False,
        }
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> UpstreamRateLimit:
        try:
            with pytest.raises(UpstreamRateLimit) as raised:
                await CommandCodeClient(http, config).send(
                    {"params": {"model": "m", "messages": []}},
                    stream=False,
                )
            return raised.value
        finally:
            await http.aclose()

    error = asyncio.run(run())
    assert error.status_code == 429
    assert error.body_bytes == upstream_body
    assert error.body_observed is True
    transport_error = cast(Any, error)
    assert transport_error.transport_status_code == 200
    assert transport_error.transport_headers == {
        "content-type": "application/x-ndjson",
        "content-length": str(len(upstream_body)),
        "x-request-id": "transport-request",
    }


def test_commandcode_client_accepts_an_open_block_at_finish() -> None:
    upstream_body = (
        b'{"type":"text-delta","text":"ok"}\n'
        b'{"type":"finish","finishReason":"stop","totalUsage":{"outputTokens":1}}\n'
    )

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            content=upstream_body,
            headers={"content-type": "application/x-ndjson"},
        )

    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "initialize_upstream": False,
        }
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    async def run() -> dict[str, Any]:
        try:
            response = await CommandCodeClient(http, config).send(
                {"params": {"model": "m", "messages": []}},
                stream=False,
            )
            return response.json()
        finally:
            await http.aclose()

    body = asyncio.run(run())
    assert body["events"][0]["text"] == "ok"
