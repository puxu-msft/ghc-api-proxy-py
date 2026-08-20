from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx
import pytest

from app.models.openai import ChatCompletionRequest, EmbeddingsRequest, ResponsesRequest
from app.openai.client import OpenAIClient
from app.transform.model_resolver import ModelResolver


class RawStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"data: raw\n\n"


class Target:
    def __init__(self, responses_data: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any], bool]] = []
        self.responses_data = responses_data

    async def send_openai(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        self.calls.append(("chat", dict(payload), stream))
        return httpx.Response(200, stream=RawStream())

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        self.calls.append(("responses", dict(payload), stream))
        if self.responses_data is not None:
            return httpx.Response(200, json=self.responses_data)
        return httpx.Response(200, stream=RawStream())

    async def send_embeddings(self, payload: Mapping[str, Any]) -> httpx.Response:
        self.calls.append(("embeddings", dict(payload), False))
        return httpx.Response(200, json={"object": "list", "data": []})


@pytest.mark.asyncio
async def test_chat_client_resolves_model_and_preserves_null_extra() -> None:
    target = Target()
    client = OpenAIClient(
        target,
        ModelResolver(available_ids={"gpt-test"}, model_overrides={"alias": "gpt-test"}),
    )
    request = ChatCompletionRequest.model_validate(
        {
            "model": "alias",
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
            "future": None,
        }
    )

    response = await client.chat(request)

    assert response.is_stream_consumed is False
    assert target.calls[0][1]["model"] == "gpt-test"
    assert "future" in target.calls[0][1]


@pytest.mark.asyncio
async def test_responses_client_normalizes_call_ids_in_nonstream_response() -> None:
    target = Target(
        {
            "id": "resp_1",
            "object": "response",
            "output": [{"type": "function_call", "call_id": "call_1"}],
        }
    )
    client = OpenAIClient(
        target,
        ModelResolver(available_ids={"gpt-test"}, model_overrides={}),
    )
    response = await client.responses(ResponsesRequest(model="gpt-test", input="hi"))
    data = response.json()

    assert data["output"][0]["call_id"] == "fc_1"


@pytest.mark.asyncio
async def test_embeddings_client_uses_resolved_model() -> None:
    target = Target()
    client = OpenAIClient(
        target,
        ModelResolver(available_ids={"embed-test"}, model_overrides={"embed": "embed-test"}),
    )

    await client.embeddings(EmbeddingsRequest(model="embed", input="hello"))

    assert target.calls[0][1]["model"] == "embed-test"
