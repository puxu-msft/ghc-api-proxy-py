from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import Response

from app.anthropic.header_policy import forward_response_headers
from app.anthropic.warmup import apply_warmup_policy
from app.deps import (
    AnthropicClientDependency,
    SettingsDependency,
    TokenCounterDependency,
)
from app.models.anthropic import MessagesRequest
from app.pipeline.executor import UpstreamResponseError
from app.streaming.idle_timeout import resolve_stream_idle, with_idle_timeout
from app.streaming.sse import create_sse_response, passthrough_bytes
from app.wire_json import dumps

router = APIRouter(tags=["anthropic"])


@router.post("/v1/messages")
async def messages(
    request: MessagesRequest,
    client: AnthropicClientDependency,
    settings: SettingsDependency,
    session_id: str | None = Header(default=None, alias="x-claude-code-session-id"),
    agent_id: str | None = Header(default=None, alias="x-claude-code-agent-id"),
) -> Response:
    warmup = apply_warmup_policy(
        request.model_dump(mode="json", exclude_unset=True),
        settings.anthropic.warmup,
    )
    if warmup is not None:
        status_code = 429 if "error" in warmup else 200
        return Response(
            content=dumps(warmup),
            status_code=status_code,
            media_type="application/json",
        )
    try:
        result = await client.execute(request, session_id=session_id, agent_id=agent_id)
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
    forwarded_headers = forward_response_headers(
        upstream.headers,
        strict=settings.anthropic.strict_response_headers,
        blacklist=settings.anthropic.response_header_blacklist,
        whitelist=settings.anthropic.response_header_whitelist,
    )
    if request.stream:
        idle_timeout = resolve_stream_idle(
            result.context.resolved_model,
            settings.timeouts,
        )
        stream = passthrough_bytes(
            with_idle_timeout(upstream.aiter_raw(), timeout_seconds=idle_timeout),
            cleanup=upstream.aclose,
        )
        return create_sse_response(stream, headers=forwarded_headers)
    try:
        content = await upstream.aread()
        content_type = upstream.headers.get("content-type", "application/json")
        return Response(
            content=content,
            status_code=upstream.status_code,
            media_type=content_type,
            headers=forwarded_headers,
        )
    finally:
        await upstream.aclose()


@router.post("/v1/messages/count_tokens")
async def count_tokens(
    request: MessagesRequest,
    counter: TokenCounterDependency,
) -> dict[str, Any]:
    return await counter.count(request)
