from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from app.deps import (
    AnthropicClientDependency,
    SettingsDependency,
    TokenCounterDependency,
)
from app.models.anthropic import MessagesRequest
from app.pipeline.executor import UpstreamResponseError
from app.streaming.idle_timeout import resolve_stream_idle, with_idle_timeout
from app.streaming.sse import create_sse_response, passthrough_bytes

router = APIRouter(tags=["anthropic"])


@router.post("/v1/messages")
async def messages(
    request: MessagesRequest,
    client: AnthropicClientDependency,
    settings: SettingsDependency,
) -> Response:
    try:
        result = await client.execute(request)
    except UpstreamResponseError as error:
        body = await error.response.aread()
        content_type = error.response.headers.get("content-type", "application/json")
        await error.response.aclose()
        return Response(
            content=body,
            status_code=error.response.status_code,
            media_type=content_type,
        )
    upstream = result.response
    if request.stream:
        idle_timeout = resolve_stream_idle(
            result.context.resolved_model,
            settings.timeouts,
        )
        stream = passthrough_bytes(
            with_idle_timeout(upstream.aiter_raw(), timeout_seconds=idle_timeout),
            cleanup=upstream.aclose,
        )
        return create_sse_response(stream)
    try:
        content = await upstream.aread()
        content_type = upstream.headers.get("content-type", "application/json")
        return Response(content=content, status_code=upstream.status_code, media_type=content_type)
    finally:
        await upstream.aclose()


@router.post("/v1/messages/count_tokens")
async def count_tokens(
    request: MessagesRequest,
    counter: TokenCounterDependency,
) -> dict[str, Any]:
    return await counter.count(request)
