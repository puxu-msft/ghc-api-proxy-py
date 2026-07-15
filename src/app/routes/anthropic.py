from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from app.deps import AnthropicClientDependency, TokenCounterDependency
from app.models.anthropic import MessagesRequest
from app.streaming.idle_timeout import with_idle_timeout
from app.streaming.sse import create_sse_response, passthrough_bytes

router = APIRouter(tags=["anthropic"])


@router.post("/v1/messages")
async def messages(
    request: MessagesRequest,
    client: AnthropicClientDependency,
) -> Response:
    result = await client.execute(request)
    upstream = result.response
    if request.stream:
        stream = passthrough_bytes(
            with_idle_timeout(upstream.aiter_raw(), timeout_seconds=300)
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
