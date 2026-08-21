import time
from dataclasses import dataclass
from typing import Any, cast

import httpx2
import orjson
from pydantic import ValidationError

from app.anthropic.client import (
    AnthropicClient,
    PreparedAnthropicRequest,
)
from app.anthropic.response_validation import validate_messages_response_wire
from app.anthropic.sanitize import sanitize_messages
from app.anthropic.thinking.quarantine import QuarantineKey
from app.anthropic.thinking.strip_all import strip_all_thinking
from app.errors import ApiError, ErrorCategory
from app.hooks.context import HookContext
from app.hooks.types import ObserverEvent, PayloadPhase
from app.models.anthropic import MessagesRequest, MessagesResponse
from app.pipeline.approval import ApprovalRejectedError
from app.pipeline.context import (
    Attempt,
    RequestContext,
    RequestConversionFactRecord,
    RequestState,
    ResponseConversionFactRecord,
)
from app.pipeline.rate_limiter import PassthroughRateLimiter
from app.pipeline.strategies import (
    PoisonedThinkingStrategy,
    ResponsesNetworkTransportStrategy,
    RetryCoordinator,
    RetryStrategy,
)
from app.upstream.base import ResponsesHeadersPendingTransportError


@dataclass(slots=True)
class PipelineResult:
    context: RequestContext
    response: httpx2.Response


class UpstreamResponseError(Exception):
    def __init__(self, context: RequestContext, response: httpx2.Response) -> None:
        super().__init__(f"upstream returned HTTP {response.status_code}")
        self.context = context
        self.response = response


def _is_retryable_responses_transport_error(
    prepared: PreparedAnthropicRequest,
    error: Exception,
) -> bool:
    return (
        prepared.route is not None
        and prepared.route.protocol_leg.value == "responses"
        and isinstance(error, ResponsesHeadersPendingTransportError)
    )


def _validate_response_body(
    body: bytes,
    *,
    after_response_hooks: bool,
) -> tuple[MessagesResponse, dict[str, Any]]:
    try:
        payload = validate_messages_response_wire(orjson.loads(body))
        return MessagesResponse.model_validate(payload), payload
    except (orjson.JSONDecodeError, ValidationError) as error:
        source = "response hook" if after_response_hooks else "upstream"
        category = ErrorCategory.INTERNAL if after_response_hooks else ErrorCategory.UPSTREAM
        raise ApiError(
            f"{source} produced an invalid Anthropic response body",
            category=category,
            status_code=500 if after_response_hooks else 502,
            code="invalid_anthropic_response_body",
        ) from error


async def _finalize_failure(
    request: MessagesRequest,
    context: RequestContext,
    client: AnthropicClient,
    error: Exception,
) -> None:
    if context.state in (RequestState.COMPLETED, RequestState.FAILED):
        return
    normalized_error = (
        error
        if isinstance(error, ApiError)
        else ApiError(
            f"request hook failed: {error}",
            category=ErrorCategory.INTERNAL,
            status_code=500,
        )
    )
    context.fail(normalized_error)
    if client.hooks is not None:
        hook_context = _hook_context(
            context,
            client,
            attempt_number=max(len(context.attempts) - 1, 0),
        )
        await client.hooks.observe(
            ObserverEvent.ERROR,
            hook_context,
            {
                "request": request,
                "status_code": normalized_error.status_code,
                "error": normalized_error,
            },
            records=context.hook_records,
        )
        await client.hooks.observe(
            ObserverEvent.FINALIZE,
            hook_context,
            {"request": request, "state": "failed", "error": normalized_error},
            records=context.hook_records,
        )
    if client.history is not None:
        await client.history.finalized(context)


def _hook_context(
    context: RequestContext,
    client: AnthropicClient,
    *,
    attempt_number: int,
) -> HookContext:
    return HookContext(
        request_id=context.id,
        endpoint=context.endpoint,
        protocol="anthropic",
        original_model=context.original_model,
        resolved_model=context.resolved_model,
        session_id=context.session_id,
        agent_id=context.agent_id,
        attempt_number=attempt_number,
        settings=client.settings,
    )


async def _prepare_with_hooks(
    client: AnthropicClient,
    request: MessagesRequest,
    context: RequestContext,
) -> tuple[MessagesRequest, PreparedAnthropicRequest]:
    hooks = client.hooks
    if hooks is None:
        return request, client.prepare(request)
    initial_context = _hook_context(context, client, attempt_number=0)
    await hooks.observe(
        ObserverEvent.REQUEST_RECEIVED,
        initial_context,
        {"request": request, "payload": context.original_payload},
        records=context.hook_records,
    )
    raw_payload, _ = await hooks.run_payload(
        PayloadPhase.PRE_SANITIZE,
        request.model_dump(mode="json", exclude_unset=True),
        initial_context,
        records=context.hook_records,
    )
    rewritten_request = MessagesRequest.model_validate(raw_payload)
    resolved_model = client.resolve_model(rewritten_request.model)
    sanitization = sanitize_messages(
        rewritten_request.messages,
        rewritten_request.tools or [],
    )
    wire = rewritten_request.model_dump(mode="json", exclude_unset=True)
    wire["model"] = resolved_model
    wire["messages"] = [
        message.model_dump(mode="json", exclude_unset=True)
        for message in sanitization.messages
    ]
    context.resolved_model = resolved_model
    post_context = _hook_context(context, client, attempt_number=0)
    wire, _ = await hooks.run_payload(
        PayloadPhase.POST_SANITIZE,
        wire,
        post_context,
        records=context.hook_records,
    )
    prepared = client.prepare_payload(
        rewritten_request,
        resolved_model=resolved_model,
        sanitization=sanitization,
        payload=wire,
        apply_thinking_destack=False,
    )
    return rewritten_request, prepared


async def execute_anthropic_pipeline(
    client: AnthropicClient,
    request: MessagesRequest,
    *,
    rate_limiter: PassthroughRateLimiter | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
) -> PipelineResult:
    limiter = rate_limiter or PassthroughRateLimiter()
    context = RequestContext(
        original_model=request.model,
        original_payload=request.model_dump(mode="json", exclude_none=True),
        session_id=session_id,
        agent_id=agent_id,
    )
    context.transition(RequestState.SANITIZING)
    if client.history is not None:
        await client.history.started(context)
    try:
        request, prepared = await _prepare_with_hooks(client, request, context)
    except Exception as error:
        await _finalize_failure(request, context, client, error)
        raise
    if client.approval_gate is not None and client.approval_gate.enabled:
        approval = await client.approval_gate.wait_for_approval(context)
        if approval.status == "rejected":
            error = ApiError(
                f"Rejected: {approval.reason}",
                category=ErrorCategory.CLIENT,
                status_code=403,
            )
            await _finalize_failure(request, context, client, error)
            raise ApprovalRejectedError(error.message)
        if approval.modified_payload:
            try:
                request = MessagesRequest.model_validate(approval.modified_payload)
                request, prepared = await _prepare_with_hooks(client, request, context)
            except Exception as error:
                await _finalize_failure(request, context, client, error)
                raise
    context.resolved_model = prepared.resolved_model
    if prepared.route is not None:
        context.protocol_leg = prepared.route.protocol_leg.value
        context.route_reason = prepared.route.reason.value
    context.sanitization = prepared.sanitization
    context.transition(RequestState.EXECUTING)
    key = QuarantineKey(session_id, agent_id or "") if session_id else None
    try:
        strategies: list[RetryStrategy]
        if client.hooks is not None:
            strategy_context = _hook_context(context, client, attempt_number=0)
            strategies = [
                factory.create(strategy_context)
                for factory in client.hooks.registry.retry_factories
            ]
        else:
            strategies = [PoisonedThinkingStrategy(client.quarantine, key)]
        if prepared.route is not None and prepared.route.protocol_leg.value == "responses":
            strategies.insert(0, ResponsesNetworkTransportStrategy())
    except Exception as error:
        await _finalize_failure(request, context, client, error)
        raise
    coordinator = RetryCoordinator(strategies, max_retries=1)
    payload: dict[str, object] = prepared.wire
    if key is not None and client.quarantine is not None and client.quarantine.is_poisoned(key):
        messages = payload.get("messages")
        if isinstance(messages, list):
            stripped, _ = strip_all_thinking(
                cast(list[dict[str, Any]], messages)
            )
            payload = {**payload, "messages": stripped}
    for attempt_number in range(2):
        context.rate_limiter_wait_ms += await limiter.acquire()
        attempt = Attempt(number=attempt_number)
        context.attempts.append(attempt)
        attempt_payload = cast(dict[str, Any], payload)
        if client.hooks is not None:
            try:
                attempt_payload, hook_modifications = await client.hooks.run_payload(
                    PayloadPhase.PRE_SEND,
                    attempt_payload,
                    _hook_context(context, client, attempt_number=attempt_number),
                    records=context.hook_records,
                )
            except Exception as error:
                await _finalize_failure(request, context, client, error)
                raise
            attempt.payload_modifications.extend(hook_modifications)
        payload = attempt_payload
        current = prepared.__class__(
            prepared.original_model,
            prepared.resolved_model,
            prepared.sanitization,
            attempt_payload,
            prepared.headers,
            prepared.route,
        )
        try:
            attempt_result = await client.send_prepared_attempt(
                current,
                stream=request.stream,
            )
            response = attempt_result.response
        except Exception as error:
            retryable_transport = _is_retryable_responses_transport_error(
                prepared,
                error,
            )
            normalized_error = (
                error
                if isinstance(error, ApiError)
                else ApiError(
                    str(error),
                    category=ErrorCategory.NETWORK,
                    status_code=502,
                    code=(
                        "responses_transport_error"
                        if retryable_transport
                        else None
                    ),
                )
            )
            attempt.error = normalized_error
            attempt.completed_at = time.time()
            if retryable_transport:
                decision = await coordinator.decide(normalized_error, payload)
                if decision is not None:
                    attempt.strategy_applied = decision.owner
                    attempt.payload_modifications.extend(decision.modifications)
                    payload = decision.payload
                    if client.hooks is not None:
                        await client.hooks.observe(
                            ObserverEvent.ERROR,
                            _hook_context(
                                context,
                                client,
                                attempt_number=attempt_number,
                            ),
                            {
                                "request": request,
                                "status_code": normalized_error.status_code,
                                "error": normalized_error,
                            },
                            records=context.hook_records,
                        )
                    continue
            await _finalize_failure(request, context, client, normalized_error)
            if normalized_error is error:
                raise
            raise normalized_error from error
        attempt.status_code = response.status_code
        attempt.completed_at = time.time()
        if response.is_success:
            context.conversion_facts = tuple(
                RequestConversionFactRecord(
                    attempt=attempt_number,
                    field_path=fact.field_path,
                    disposition=fact.disposition,
                    reason=fact.reason,
                )
                for fact in attempt_result.converted_request_facts
            )
            body = b""
            hook_context: HookContext | None = None
            if not request.stream:
                try:
                    body = await response.aread()
                except Exception as error:
                    normalized_error = ApiError(
                        str(error) or "failed to read upstream response body",
                        category=ErrorCategory.NETWORK,
                        status_code=502,
                        code="upstream_response_read_failed",
                    )
                    attempt.error = normalized_error
                    await response.aclose()
                    await _finalize_failure(
                        request,
                        context,
                        client,
                        normalized_error,
                    )
                    raise normalized_error from error
                after_response_hooks = bool(
                    client.hooks is not None
                    and client.hooks.registry.response_hooks
                )
                if client.hooks is not None:
                    hook_context = _hook_context(
                        context,
                        client,
                        attempt_number=attempt_number,
                    )
                    try:
                        transformed = await client.hooks.run_response(
                            body,
                            response.status_code,
                            hook_context,
                            records=context.hook_records,
                        )
                    except Exception as error:
                        await response.aclose()
                        await _finalize_failure(request, context, client, error)
                        raise
                    body = transformed.body
                try:
                    normalized_response, final_response_payload = _validate_response_body(
                        body,
                        after_response_hooks=after_response_hooks,
                    )
                except Exception as error:
                    await response.aclose()
                    await _finalize_failure(request, context, client, error)
                    raise
                if client.hooks is not None:
                    assert hook_context is not None
                    original = response
                    response = httpx2.Response(
                        original.status_code,
                        headers=original.headers,
                        content=body,
                        request=getattr(original, "_request", None),
                        extensions=original.extensions,
                    )
                    await original.aclose()
                context.normalized_response = normalized_response
                context.final_response_payload = final_response_payload
                converted = attempt_result.converted_response
                context.conversion_facts += tuple(
                    ResponseConversionFactRecord(
                        attempt=attempt_number,
                        code=fact.code,
                        field_path=fact.field_path,
                    )
                    for fact in (
                        converted.facts if converted is not None else ()
                    )
                )
                if converted is not None:
                    context.response_usage = converted.usage_facts
            try:
                coordinator.notify_success()
                limiter.report_success()
            except Exception as error:
                await response.aclose()
                await _finalize_failure(request, context, client, error)
                raise
            if not request.stream and client.hooks is not None:
                assert hook_context is not None
                await client.hooks.observe(
                    ObserverEvent.RESPONSE,
                    hook_context,
                    {
                        "request": request,
                        "response_body": body,
                        "status_code": response.status_code,
                    },
                    records=context.hook_records,
                )
            context.transition(
                RequestState.STREAMING if request.stream else RequestState.COMPLETED
            )
            if not request.stream:
                if client.hooks is not None:
                    assert hook_context is not None
                    await client.hooks.observe(
                        ObserverEvent.FINALIZE,
                        hook_context,
                        {"request": request, "state": "completed"},
                        records=context.hook_records,
                    )
                if client.history is not None:
                    await client.history.finalized(context)
            return PipelineResult(context=context, response=response)
        body = await response.aread()
        error = ApiError(
            body.decode(errors="replace") or f"HTTP {response.status_code}",
            status_code=response.status_code,
        )
        attempt.error = error
        if client.hooks is not None:
            await client.hooks.observe(
                ObserverEvent.ERROR,
                _hook_context(context, client, attempt_number=attempt_number),
                {
                    "request": request,
                    "response_body": body,
                    "status_code": response.status_code,
                    "error": error,
                },
                records=context.hook_records,
            )
        if error.category is ErrorCategory.RATE_LIMIT:
            retry_after_value = response.headers.get("retry-after")
            try:
                retry_after = float(retry_after_value) if retry_after_value else None
            except ValueError:
                retry_after = None
            limiter.report_rate_limit(retry_after)
        decision = await coordinator.decide(error, payload)
        if decision is not None:
            attempt.strategy_applied = decision.owner
            attempt.payload_modifications.extend(decision.modifications)
            payload = decision.payload
            await response.aclose()
            continue
        context.fail(error)
        if client.hooks is not None:
            await client.hooks.observe(
                ObserverEvent.FINALIZE,
                _hook_context(context, client, attempt_number=attempt_number),
                {"request": request, "state": "failed", "error": error},
                records=context.hook_records,
            )
        if client.history is not None:
            await client.history.finalized(context)
        raise UpstreamResponseError(context, response)
    raise RuntimeError("retry loop exhausted without terminal result")
