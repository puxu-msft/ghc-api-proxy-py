from collections.abc import AsyncGenerator, AsyncIterator
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
from app.errors import ApiError, ErrorCategory
from app.models.anthropic import MessagesRequest
from app.pipeline.approval import ApprovalRejectedError
from app.pipeline.context import RequestContext, RequestState
from app.pipeline.executor import UpstreamResponseError
from app.streaming.anthropic_usage import AnthropicSSEUsageTap
from app.streaming.idle_timeout import resolve_stream_idle, with_idle_timeout
from app.streaming.sse import create_sse_response, passthrough_bytes
from app.wire_json import dumps

router = APIRouter(tags=["anthropic"])


async def _history_stream(
    stream: AsyncIterator[bytes],
    *,
    context: RequestContext,
    client: AnthropicClientDependency,
    request: MessagesRequest,
) -> AsyncGenerator[bytes]:
    completed = False
    usage_tap = AnthropicSSEUsageTap()
    try:
        async for chunk in stream:
            usage_tap.feed(chunk)
            yield chunk
        completed = True
    finally:
        history = getattr(client, "history", None)
        if completed:
            context.transition(RequestState.COMPLETED)
        else:
            context.fail(
                ApiError(
                    "stream interrupted",
                    category=ErrorCategory.NETWORK,
                    status_code=499,
                )
            )
        await client.observe_stream_finalized(
            request,
            context,
            usage=usage_tap.usage,
            completed=completed,
        )
        if history is not None:
            await history.finalized(context)


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
    except ApprovalRejectedError as error:
        return Response(
            content=dumps({"type": "error", "error": {"message": str(error)}}),
            status_code=403,
            media_type="application/json",
        )
    except ApiError as error:
        error_detail: dict[str, Any] = {
            "type": error.wire_type,
            "message": error.message,
        }
        if error.code is not None:
            error_detail["code"] = error.code
        if error.request_id is not None:
            error_detail["request_id"] = error.request_id
        return Response(
            content=dumps({"type": "error", "error": error_detail}),
            status_code=error.status_code,
            media_type="application/json",
        )
    except UpstreamResponseError as error:
        body = await error.response.aread()
        content_type = error.response.headers.get("content-type", "application/json")
        error_headers = forward_response_headers(
            error.response.headers,
            strict=settings.anthropic.strict_response_headers,
            blacklist=settings.anthropic.response_header_blacklist,
            whitelist=settings.anthropic.response_header_whitelist,
        )
        await error.response.aclose()
        return Response(
            content=body,
            status_code=error.response.status_code,
            media_type=content_type,
            headers=error_headers,
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
            _history_stream(
                with_idle_timeout(upstream.aiter_raw(), timeout_seconds=idle_timeout),
                context=result.context,
                client=client,
                request=request,
            ),
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
