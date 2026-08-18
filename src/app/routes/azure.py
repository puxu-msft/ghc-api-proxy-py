from typing import Any

import httpx
from fastapi import APIRouter, Response

from app.deps import ApprovalGateDependency, OpenAIClientDependency, RuntimeDependency
from app.history.types import HistoryEntry
from app.models.openai import ChatCompletionRequest, EmbeddingsRequest, ResponsesRequest
from app.pipeline.protocol_guard import apply_approval_guard
from app.protocols.azure import adapt_azure_payload
from app.routes.protocol_history import (
    finalize_protocol_history,
    history_stream,
    start_protocol_history,
)
from app.runtime import RuntimeState
from app.streaming.sse import create_sse_response, passthrough_bytes

router = APIRouter(prefix="/openai/deployments", tags=["azure"])


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


@router.post("/{deployment}/chat/completions")
async def azure_chat(
    deployment: str,
    body: dict[str, Any],
    client: OpenAIClientDependency,
    gate: ApprovalGateDependency,
    runtime: RuntimeDependency,
) -> Response:
    adapted = adapt_azure_payload(body, deployment=deployment)
    guarded = await apply_approval_guard(
        adapted.wire_payload,
        model=deployment,
        endpoint="azure-chat-completions",
        gate=gate,
    )
    request = ChatCompletionRequest.model_validate(guarded)
    history_entry = start_protocol_history(
        runtime,
        endpoint="azure-chat-completions",
        model=deployment,
        payload=adapted.original_payload,
    )
    return await _response(
        await client.chat(request),
        stream=request.stream,
        runtime=runtime,
        history_entry=history_entry,
    )


@router.post("/{deployment}/responses")
async def azure_responses(
    deployment: str,
    body: dict[str, Any],
    client: OpenAIClientDependency,
    gate: ApprovalGateDependency,
    runtime: RuntimeDependency,
) -> Response:
    adapted = adapt_azure_payload(body, deployment=deployment)
    guarded = await apply_approval_guard(
        adapted.wire_payload,
        model=deployment,
        endpoint="azure-responses",
        gate=gate,
    )
    request = ResponsesRequest.model_validate(guarded)
    history_entry = start_protocol_history(
        runtime,
        endpoint="azure-responses",
        model=deployment,
        payload=adapted.original_payload,
    )
    return await _response(
        await client.responses(request),
        stream=request.stream,
        runtime=runtime,
        history_entry=history_entry,
    )


@router.post("/{deployment}/embeddings")
async def azure_embeddings(
    deployment: str,
    body: dict[str, Any],
    client: OpenAIClientDependency,
    gate: ApprovalGateDependency,
    runtime: RuntimeDependency,
) -> Response:
    adapted = adapt_azure_payload(body, deployment=deployment)
    guarded = await apply_approval_guard(
        adapted.wire_payload,
        model=deployment,
        endpoint="azure-embeddings",
        gate=gate,
    )
    request = EmbeddingsRequest.model_validate(guarded)
    history_entry = start_protocol_history(
        runtime,
        endpoint="azure-embeddings",
        model=deployment,
        payload=adapted.original_payload,
    )
    return await _response(
        await client.embeddings(request),
        runtime=runtime,
        history_entry=history_entry,
    )
