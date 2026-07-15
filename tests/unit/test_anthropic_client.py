from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx
import pytest

from app.anthropic.client import AnthropicClient
from app.models.anthropic import MessagesRequest
from app.transform.model_resolver import ModelResolver


class RawStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n"


class StubTarget:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        self.payload = dict(payload)
        return httpx.Response(200, stream=RawStream())


@pytest.mark.asyncio
async def test_anthropic_client_resolves_sanitizes_and_preserves_stream() -> None:
    target = StubTarget()
    resolver = ModelResolver(
        available_ids={"claude-opus-4.6"},
        model_overrides={"opus": "claude-opus-4.6"},
    )
    client = AnthropicClient(target, resolver)
    request = MessagesRequest.model_validate(
        {
            "model": "opus",
            "max_tokens": 100,
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": ""}, {"type": "text", "text": "hi"}],
                }
            ],
            "future_request_field": {"keep": True},
        }
    )

    response, context = await client.send_messages(request)

    assert response.is_stream_consumed is False
    assert context.resolved_model == "claude-opus-4.6"
    assert context.sanitization.empty_text_blocks_removed == 1
    assert target.payload is not None
    assert target.payload["model"] == "claude-opus-4.6"
    assert target.payload["future_request_field"] == {"keep": True}
    messages = target.payload["messages"]
    assert isinstance(messages, list)
    assert messages[0]["content"] == [{"type": "text", "text": "hi"}]