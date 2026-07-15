import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.deps import ModelCatalogDependency, OpenAIClientDependency
from app.models.common import ModelInfo
from app.models.openai import ChatCompletionRequest, EmbeddingsRequest, ResponsesRequest
from app.streaming.sse import create_sse_response, passthrough_bytes

router = APIRouter(tags=["openai"])


async def _response(upstream: httpx.Response, *, stream: bool = False) -> Response:
    if stream:
        return create_sse_response(
            passthrough_bytes(upstream.aiter_raw(), cleanup=upstream.aclose)
        )
    try:
        return Response(
            content=await upstream.aread(),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/json"),
        )
    finally:
        await upstream.aclose()


@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    client: OpenAIClientDependency,
) -> Response:
    return await _response(await client.chat(request), stream=request.stream)


@router.post("/responses")
async def responses(
    request: ResponsesRequest,
    client: OpenAIClientDependency,
) -> Response:
    return await _response(await client.responses(request), stream=request.stream)


@router.post("/embeddings")
async def embeddings(
    request: EmbeddingsRequest,
    client: OpenAIClientDependency,
) -> Response:
    return await _response(await client.embeddings(request))


def _openai_model(model: ModelInfo) -> dict[str, object]:
    return {
        "id": model.id,
        "object": "model",
        "created": 0,
        "owned_by": (model.vendor or "copilot").lower(),
        "capabilities": model.capabilities.model_dump(mode="json"),
    }


@router.get("/models")
async def models(catalog: ModelCatalogDependency) -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            _openai_model(model)
            for model in catalog.models
            if model.id in catalog.available_ids
        ],
    }


@router.get("/models/{model_id}")
async def model(model_id: str, catalog: ModelCatalogDependency) -> dict[str, object]:
    item = catalog.get(model_id)
    if item is None or model_id not in catalog.available_ids:
        raise HTTPException(status_code=404, detail="Model not found")
    return _openai_model(item)