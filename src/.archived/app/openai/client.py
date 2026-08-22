from collections.abc import Mapping
from typing import Any, Protocol

import httpx2

from app.models.openai import ChatCompletionRequest, EmbeddingsRequest, ResponsesRequest
from app.openai.responses_conversion import normalize_call_ids
from app.openai.sanitize import sanitize_chat_messages
from app.transform.model_resolver import ModelResolver
from app.wire_json import JsonValue, dumps, loads


class OpenAITarget(Protocol):
    async def send_openai(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx2.Response: ...

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx2.Response: ...

    async def send_embeddings(self, payload: Mapping[str, Any]) -> httpx2.Response: ...


class OpenAIClient:
    def __init__(self, target: OpenAITarget, resolver: ModelResolver) -> None:
        self._target = target
        self._resolver = resolver

    def _wire(
        self,
        request: ChatCompletionRequest | ResponsesRequest | EmbeddingsRequest,
    ) -> dict[str, Any]:
        wire = request.model_dump(mode="json", exclude_unset=True)
        wire["model"] = self._resolver.resolve(request.model)
        return wire

    async def chat(self, request: ChatCompletionRequest) -> httpx2.Response:
        wire = self._wire(request)
        wire["messages"] = sanitize_chat_messages(wire["messages"])
        return await self._target.send_openai(wire, stream=request.stream)

    async def responses(self, request: ResponsesRequest) -> httpx2.Response:
        response = await self._target.send_responses(self._wire(request), stream=request.stream)
        if request.stream or not response.is_success:
            return response
        try:
            data: JsonValue = loads(await response.aread())
            normalized = normalize_call_ids(data)
        finally:
            await response.aclose()
        return httpx2.Response(
            response.status_code,
            headers=response.headers,
            content=dumps(normalized),
        )

    async def embeddings(self, request: EmbeddingsRequest) -> httpx2.Response:
        return await self._target.send_embeddings(self._wire(request))
