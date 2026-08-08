from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import Response

from app.anthropic.header_policy import (
    forward_response_headers,
    normalize_responses_response_headers,
)
from app.anthropic.warmup import apply_warmup_policy
from app.delivery.reservation import RequestResidentAccount
from app.delivery.responses_anthropic_stream import (
    ResponsesAnthropicStreamState,
    render_responses_as_anthropic_sse,
)
from app.deps import (
    AnthropicClientDependency,
    RuntimeDependency,
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
from app.streaming.sse import create_delayed_sse_response, create_sse_response, passthrough_bytes
from app.wire_json import dumps

router = APIRouter(tags=["anthropic"])


async def _history_stream(
    stream: AsyncIterator[bytes],
    *,
    context: RequestContext,
    client: AnthropicClientDependency,
    request: MessagesRequest,
    responses_state: ResponsesAnthropicStreamState | None = None,
) -> AsyncGenerator[bytes]:
    completed = False
    stream_error: ApiError | None = None
    usage_tap = AnthropicSSEUsageTap()
    try:
        async for chunk in stream:
            usage_tap.feed(chunk)
            yield chunk
        completed = (
            responses_state is None
            or (
                responses_state.error is None
                and responses_state.frontier is not None
                and responses_state.frontier.terminal_accepted
            )
        )
        if responses_state is not None and responses_state.error is not None:
            stream_error = responses_state.error
    except ApiError as error:
        stream_error = error
        raise
    finally:
        history = getattr(client, "history", None)
        normalized_usage = (
            responses_state.usage.as_wire()
            if responses_state is not None and responses_state.usage is not None
            else usage_tap.usage
        )
        if completed:
            context.transition(RequestState.COMPLETED)
        else:
            if stream_error is None:
                delivery_uncertain = (
                    responses_state is not None
                    and responses_state.frontier is not None
                    and responses_state.frontier.delivery_uncertain
                )
                stream_error = ApiError(
                    (
                        "downstream delivery outcome is uncertain"
                        if delivery_uncertain
                        else "stream interrupted"
                    ),
                    category=ErrorCategory.NETWORK,
                    status_code=499,
                    code="delivery_uncertain" if delivery_uncertain else None,
                )
            context.fail(stream_error)
        await client.observe_stream_finalized(
            request,
            context,
            usage=normalized_usage,
            completed=completed,
            usage_estimated=(
                responses_state.usage_estimated
                if responses_state is not None
                else False
            ),
        )
        if history is not None:
            response = (
                responses_state.committed_response
                if responses_state is not None
                else None
            )
            if response is not None:
                response["usage"] = dict(normalized_usage)
                if responses_state is not None and responses_state.usage_estimated:
                    response["usage_facts"] = {"estimated": True}
                if stream_error is not None:
                    response["error"] = {
                        "type": stream_error.wire_type,
                        "message": stream_error.message,
                        "code": stream_error.code,
                    }
            await history.finalized(
                context,
                response=response,
                usage=normalized_usage if response is not None else None,
                usage_estimated=(
                    responses_state.usage_estimated
                    if responses_state is not None
                    else False
                ),
            )


def _api_error_response(error: ApiError) -> Response:
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


def _response_headers(
    headers: Mapping[str, str],
    *,
    responses_leg: bool,
    settings: SettingsDependency,
) -> dict[str, str]:
    selected = (
        normalize_responses_response_headers(headers)
        if responses_leg
        else dict(headers)
    )
    return forward_response_headers(
        selected,
        strict=settings.anthropic.strict_response_headers,
        blacklist=settings.anthropic.response_header_blacklist,
        whitelist=settings.anthropic.response_header_whitelist,
    )


@router.post("/v1/messages")
async def messages(
    request: MessagesRequest,
    client: AnthropicClientDependency,
    runtime: RuntimeDependency,
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
        return _api_error_response(error)
    except UpstreamResponseError as error:
        body = await error.response.aread()
        content_type = error.response.headers.get("content-type", "application/json")
        error_headers = _response_headers(
            error.response.headers,
            responses_leg=error.context.protocol_leg == "responses",
            settings=settings,
        )
        await error.response.aclose()
        return Response(
            content=body,
            status_code=error.response.status_code,
            media_type=content_type,
            headers=error_headers,
        )
    upstream = result.response
    responses_leg = result.context.protocol_leg == "responses"
    forwarded_headers = _response_headers(
        upstream.headers,
        responses_leg=responses_leg,
        settings=settings,
    )
    if request.stream:
        idle_timeout = resolve_stream_idle(
            result.context.resolved_model,
            settings.timeouts,
        )
        upstream_stream: AsyncIterator[bytes] = with_idle_timeout(
            upstream.aiter_raw(),
            timeout_seconds=idle_timeout,
        )
        responses_state: ResponsesAnthropicStreamState | None = None
        if responses_leg:
            responses_state = ResponsesAnthropicStreamState()
            resident_account = (
                RequestResidentAccount(
                    request_id=result.context.id,
                    attempt=result.context.attempts[-1].number,
                    capacity_bytes=settings.openai_responses.request_resident_bytes,
                    budget=runtime.resident_byte_budget,
                )
                if runtime.resident_byte_budget is not None
                else None
            )
            upstream_stream = render_responses_as_anthropic_sse(
                upstream_stream,
                model=result.context.resolved_model,
                state=responses_state,
                resident_account=resident_account,
            )
        stream = passthrough_bytes(
            _history_stream(
                upstream_stream,
                context=result.context,
                client=client,
                request=request,
                responses_state=responses_state,
            ),
            cleanup=upstream.aclose,
        )
        if responses_leg:
            return create_delayed_sse_response(
                stream,
                headers=forwarded_headers,
                on_start_accepted=(
                    responses_state.accept_headers
                    if responses_state is not None
                    else None
                ),
                on_start_uncertain=(
                    responses_state.mark_headers_uncertain
                    if responses_state is not None
                    else None
                ),
                on_body_uncertain=(
                    responses_state.mark_body_uncertain
                    if responses_state is not None
                    else None
                ),
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
