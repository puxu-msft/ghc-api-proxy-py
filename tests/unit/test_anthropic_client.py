from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx
import pytest

from app.anthropic.client import AnthropicClient
from app.anthropic.thinking.reasoning_carrier import (
    PROJECT_SYNTHETIC_REASONING_SIGNATURE,
    PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    encode_reasoning_carrier,
)
from app.models.anthropic import MessagesRequest
from app.transform.model_resolver import ModelResolver


class RawStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n"


class StubTarget:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None
        self.headers: Mapping[str, str] | None = None

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        self.payload = dict(payload)
        self.headers = extra_headers
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
            "future_nullable": None,
            "inference_geo": "strip-me",
        }
    )

    response, context = await client.send_messages(request)

    assert response.is_stream_consumed is False
    assert context.resolved_model == "claude-opus-4.6"
    assert context.sanitization.empty_text_blocks_removed == 1
    assert target.payload is not None
    assert target.payload["model"] == "claude-opus-4.6"
    assert target.payload["future_request_field"] == {"keep": True}
    assert "future_nullable" in target.payload
    assert target.payload["future_nullable"] is None
    assert "inference_geo" not in target.payload
    assert target.headers is not None
    assert target.headers["anthropic-version"] == "2023-06-01"
    messages = target.payload["messages"]
    assert isinstance(messages, list)
    assert messages[0]["content"] == [{"type": "text", "text": "hi"}]


def test_anthropic_client_prepare_strips_only_synthetic_thinking_from_final_wire() -> None:
    client = AnthropicClient(
        StubTarget(),
        ModelResolver(
            available_ids={"claude-opus-4.6"},
            model_overrides={},
        ),
    )
    synthetic_signatures = [
        PROJECT_SYNTHETIC_REASONING_SIGNATURE,
        encode_reasoning_carrier("project-payload"),
        f"{PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX}!!!",
        "ghc-api-proxy:synthetic-reasoning:v2:future",
        UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
        f"{UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX}RU5E",
        UPSTREAM_SYNTHETIC_REASONING_SIGNATURE,
    ]
    request = MessagesRequest.model_validate(
        {
            "model": "claude-opus-4.6",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "keep-before"},
                        *[
                            {
                                "type": "thinking",
                                "thinking": f"visible synthetic {index}",
                                "signature": signature,
                            }
                            for index, signature in enumerate(synthetic_signatures)
                        ],
                        {
                            "type": "thinking",
                            "thinking": "real Anthropic thinking",
                            "signature": "CAIS-real-anthropic",
                        },
                        {"type": "text", "text": "keep-after"},
                    ],
                }
            ],
        }
    )

    prepared = client.prepare(request)

    messages = prepared.wire["messages"]
    assert isinstance(messages, list)
    assert messages[0]["content"] == [
        {"type": "text", "text": "keep-before"},
        {
            "type": "thinking",
            "thinking": "real Anthropic thinking",
            "signature": "CAIS-real-anthropic",
        },
        {"type": "text", "text": "keep-after"},
    ]