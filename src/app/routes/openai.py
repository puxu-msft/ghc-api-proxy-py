import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.deps import (
    ApprovalGateDependency,
    ModelCatalogDependency,
    OpenAIClientDependency,
    RuntimeDependency,
)
from app.history.types import HistoryEntry
from app.models.common import ModelInfo
from app.models.openai import ChatCompletionRequest, EmbeddingsRequest, ResponsesRequest
from app.pipeline.protocol_guard import apply_approval_guard
from app.routes.protocol_history import (
    finalize_protocol_history,
    history_stream,
    start_protocol_history,
)
from app.runtime import RuntimeState
from app.streaming.sse import create_sse_response, passthrough_bytes

router = APIRouter(tags=["openai"])


async def _response(
    upstream: httpx.Response,
    *,
    stream: bool = False,
    runtime: RuntimeState,
    history_entry: HistoryEntry | None,
) -> Response:
    if stream and upstream.is_success:
        return create_sse_response(
            passthrough_bytes(
                history_stream(
                    upstream.aiter_raw(),
                    runtime=runtime,
                    entry=history_entry,
                ),
                cleanup=upstream.aclose,
            )
        )
    try:
        await finalize_protocol_history(
            runtime,
            history_entry,
            status="completed" if upstream.is_success else "failed",
        )
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
    gate: ApprovalGateDependency,
    runtime: RuntimeDependency,
) -> Response:
    guarded = await apply_approval_guard(
        request.model_dump(mode="json", exclude_unset=True),
        model=request.model,
        endpoint="openai-chat-completions",
        gate=gate,
    )
    request = ChatCompletionRequest.model_validate(guarded)
    history_entry = start_protocol_history(
        runtime,
        endpoint="openai-chat-completions",
        model=request.model,
        payload=guarded,
    )
    return await _response(
        await client.chat(request),
        stream=request.stream,
        runtime=runtime,
        history_entry=history_entry,
    )


@router.post("/responses")
async def responses(
    request: ResponsesRequest,
    client: OpenAIClientDependency,
    gate: ApprovalGateDependency,
    runtime: RuntimeDependency,
) -> Response:
    guarded = await apply_approval_guard(
        request.model_dump(mode="json", exclude_unset=True),
        model=request.model,
        endpoint="openai-responses",
        gate=gate,
    )
    request = ResponsesRequest.model_validate(guarded)
    history_entry = start_protocol_history(
        runtime,
        endpoint="openai-responses",
        model=request.model,
        payload=guarded,
    )
    return await _response(
        await client.responses(request),
        stream=request.stream,
        runtime=runtime,
        history_entry=history_entry,
    )


@router.post("/embeddings")
async def embeddings(
    request: EmbeddingsRequest,
    client: OpenAIClientDependency,
    gate: ApprovalGateDependency,
    runtime: RuntimeDependency,
) -> Response:
    guarded = await apply_approval_guard(
        request.model_dump(mode="json", exclude_unset=True),
        model=request.model,
        endpoint="openai-embeddings",
        gate=gate,
    )
    request = EmbeddingsRequest.model_validate(guarded)
    history_entry = start_protocol_history(
        runtime,
        endpoint="openai-embeddings",
        model=request.model,
        payload=guarded,
    )
    return await _response(
        await client.embeddings(request),
        runtime=runtime,
        history_entry=history_entry,
    )


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
