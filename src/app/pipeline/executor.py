import time
from dataclasses import dataclass
from typing import Any, cast

import httpx

from app.anthropic.client import AnthropicClient
from app.anthropic.thinking.quarantine import QuarantineKey
from app.anthropic.thinking.strip_all import strip_all_thinking
from app.errors import ApiError, ErrorCategory
from app.models.anthropic import MessagesRequest
from app.pipeline.context import Attempt, RequestContext, RequestState
from app.pipeline.rate_limiter import PassthroughRateLimiter
from app.pipeline.strategies import PoisonedThinkingStrategy, RetryCoordinator


@dataclass(slots=True)
class PipelineResult:
    context: RequestContext
    response: httpx.Response


class UpstreamResponseError(Exception):
    def __init__(self, context: RequestContext, response: httpx.Response) -> None:
        super().__init__(f"upstream returned HTTP {response.status_code}")
        self.context = context
        self.response = response


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
    prepared = client.prepare(request)
    context.resolved_model = prepared.resolved_model
    context.sanitization = prepared.sanitization
    context.transition(RequestState.EXECUTING)
    key = QuarantineKey(session_id, agent_id or "") if session_id else None
    strategy = PoisonedThinkingStrategy(client.quarantine, key)
    coordinator = RetryCoordinator([strategy], max_retries=1)
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
        current = prepared.__class__(
            prepared.original_model,
            prepared.resolved_model,
            prepared.sanitization,
            payload,
            prepared.headers,
        )
        response = await client.send_prepared(current, stream=request.stream)
        attempt.status_code = response.status_code
        attempt.completed_at = time.time()
        if response.is_success:
            limiter.report_success()
            strategy.on_success()
            context.transition(
                RequestState.STREAMING if request.stream else RequestState.COMPLETED
            )
            if client.history is not None and not request.stream:
                await client.history.finalized(context)
            return PipelineResult(context=context, response=response)
        body = await response.aread()
        error = ApiError(
            body.decode(errors="replace") or f"HTTP {response.status_code}",
            status_code=response.status_code,
        )
        attempt.error = error
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
            attempt.payload_modifications = list(decision.modifications)
            payload = decision.payload
            await response.aclose()
            continue
        context.fail(error)
        if client.history is not None:
            await client.history.finalized(context)
        raise UpstreamResponseError(context, response)
    raise RuntimeError("retry loop exhausted without terminal result")