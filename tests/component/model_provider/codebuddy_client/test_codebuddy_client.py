"""The send client: streaming forced on the wire, aggregation for non-streaming
callers, and upstream refusals mapped onto the closed error set.
"""

import json
from typing import Any

import httpx2
import pytest

from app.model_provider.codebuddy_client.auth_state import CodebuddyCredentials, DesktopAuthState
from app.model_provider.codebuddy_client.client import CodebuddyClient
from app.model_provider.codebuddy_client.config import CodebuddyClientConfig
from app.pipeline.exceptions import UpstreamRejected, UpstreamTimeout

BACKEND = "https://copilot.tencent.example"


def write_state(path: Any) -> None:
    import time

    path.write_text(
        json.dumps(
            {
                "auth": {
                    "accessToken": "access-1",
                    "refreshToken": "r",
                    "expiresAt": int(time.time() * 1000) + 3_600_000,
                },
                "account": {"uid": "u-1"},
            }
        ),
        encoding="utf-8",
    )


def build_client(
    handler: Any, tmp_path: Any
) -> tuple[CodebuddyClient, httpx2.AsyncClient]:
    write_state(tmp_path / "state.info")
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    credentials = CodebuddyCredentials(
        DesktopAuthState(str(tmp_path / "state.info")), http_client, CodebuddyClientConfig()
    )
    client = CodebuddyClient(
        CodebuddyClientConfig(api_base_url_override=BACKEND),
        credentials,
        http_client=http_client,
    )
    return client, http_client


def sse(*chunks: dict[str, Any]) -> httpx2.Response:
    body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
    return httpx2.Response(
        200, content=body.encode(), headers={"content-type": "text/event-stream"}
    )


async def test_the_wire_always_streams(tmp_path: Any) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.read())
        return sse({"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]})

    client, http_client = build_client(handler, tmp_path)
    await client.send_chat_completions({"model": "glm-5.2"}, stream=False)

    await http_client.aclose()
    assert seen["body"]["stream"] is True
    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert seen["body"]["model"] == "glm-5.2"


async def test_stream_true_returns_the_upstream_response_untouched(tmp_path: Any) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return sse({"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]})

    client, http_client = build_client(handler, tmp_path)
    response = await client.send_chat_completions({"model": "glm-5.2"}, stream=True)

    try:
        assert response.status_code == 200
        first = ""
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                first = line
                break
        assert "hi" in first
    finally:
        await response.aclose()
        await http_client.aclose()


async def test_non_streaming_aggregates_content_usage_and_finish(tmp_path: Any) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return sse(
            {"model": "glm-5.2", "choices": [{"delta": {"content": "he"}, "finish_reason": None}]},
            {"model": "glm-5.2", "choices": [{"delta": {"content": "llo"}, "finish_reason": None}]},
            {"model": "glm-5.2", "choices": [{"delta": {}, "finish_reason": "stop"}]},
            {"model": "glm-5.2", "choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        )

    client, http_client = build_client(handler, tmp_path)
    response = await client.send_chat_completions({"model": "glm-5.2"}, stream=False)

    await http_client.aclose()
    body = json.loads(response.content)
    assert body["choices"][0]["message"]["content"] == "hello"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"] == {"prompt_tokens": 10, "completion_tokens": 2}
    assert body["model"] == "glm-5.2"


async def test_non_streaming_aggregates_indexed_tool_calls(tmp_path: Any) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return sse(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "id": "c1", "function": {"name": "f", "arguments": '{"a":'}}
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": "1}"}},
                                {"index": 1, "id": "c2", "function": {"name": "g", "arguments": "{}"}},
                            ]
                        }
                    }
                ]
            },
            {"choices": [{"delta": {}, "finish_reason": None}]},
        )

    client, http_client = build_client(handler, tmp_path)
    response = await client.send_chat_completions({"model": "glm-5.2"}, stream=False)

    await http_client.aclose()
    body = json.loads(response.content)
    calls = body["choices"][0]["message"]["tool_calls"]
    assert calls[0]["function"] == {"name": "f", "arguments": '{"a":1}'}
    assert calls[1]["function"] == {"name": "g", "arguments": "{}"}
    # A reply of tool calls with no explicit finish reason still finishes as tool_calls.
    assert body["choices"][0]["finish_reason"] == "tool_calls"


async def test_a_400_is_an_upstream_rejection_with_the_sent_body(tmp_path: Any) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(400, json={"error": {"message": "bad"}})

    client, http_client = build_client(handler, tmp_path)
    with pytest.raises(UpstreamRejected):
        await client.send_chat_completions({"model": "glm-5.2"}, stream=False)
    await http_client.aclose()


async def test_a_timeout_is_named(tmp_path: Any) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectTimeout("too slow")

    client, http_client = build_client(handler, tmp_path)
    with pytest.raises(UpstreamTimeout):
        await client.send_chat_completions({"model": "glm-5.2"}, stream=False)
    await http_client.aclose()
