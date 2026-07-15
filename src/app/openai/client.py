from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from app.models.openai import ChatCompletionRequest, EmbeddingsRequest, ResponsesRequest
from app.openai.responses_conversion import normalize_call_ids
from app.transform.model_resolver import ModelResolver
from app.wire_json import JsonValue, dumps, loads


class OpenAITarget(Protocol):
    async def send_openai(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response: ...

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response: ...

    async def send_embeddings(self, payload: Mapping[str, Any]) -> httpx.Response: ...


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

    async def chat(self, request: ChatCompletionRequest) -> httpx.Response:
        return await self._target.send_openai(self._wire(request), stream=request.stream)

    async def responses(self, request: ResponsesRequest) -> httpx.Response:
        response = await self._target.send_responses(self._wire(request), stream=request.stream)
        if request.stream or not response.is_success:
            return response
        data: JsonValue = loads(await response.aread())
        normalized = normalize_call_ids(data)
        await response.aclose()
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=dumps(normalized),
        )

    async def embeddings(self, request: EmbeddingsRequest) -> httpx.Response:
        return await self._target.send_embeddings(self._wire(request))