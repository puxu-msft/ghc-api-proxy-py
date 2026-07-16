import time
from dataclasses import dataclass

import httpx

from app.anthropic.client import AnthropicClient
from app.errors import ApiError
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
) -> PipelineResult:
    limiter = rate_limiter or PassthroughRateLimiter()
    context = RequestContext(
        original_model=request.model,
        original_payload=request.model_dump(mode="json", exclude_none=True),
    )
    context.transition(RequestState.SANITIZING)
    prepared = client.prepare(request)
    context.resolved_model = prepared.resolved_model
    context.sanitization = prepared.sanitization
    context.transition(RequestState.EXECUTING)
    context.rate_limiter_wait_ms += await limiter.acquire()
    coordinator = RetryCoordinator([PoisonedThinkingStrategy()], max_retries=1)
    payload: dict[str, object] = prepared.wire
    for attempt_number in range(2):
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
            context.transition(
                RequestState.STREAMING if request.stream else RequestState.COMPLETED
            )
            return PipelineResult(context=context, response=response)
        body = await response.aread()
        error = ApiError(
            body.decode(errors="replace") or f"HTTP {response.status_code}",
            status_code=response.status_code,
        )
        attempt.error = error
        decision = await coordinator.decide(error, payload)
        if decision is not None:
            attempt.strategy_applied = decision.owner
            attempt.payload_modifications = list(decision.modifications)
            payload = decision.payload
            await response.aclose()
            continue
        context.fail(error)
        raise UpstreamResponseError(context, response)
    raise RuntimeError("retry loop exhausted without terminal result")