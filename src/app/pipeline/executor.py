import time
from dataclasses import dataclass

import httpx

from app.anthropic.client import AnthropicClient
from app.errors import ApiError
from app.models.anthropic import MessagesRequest
from app.pipeline.context import Attempt, RequestContext, RequestState
from app.pipeline.rate_limiter import PassthroughRateLimiter


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
    attempt = Attempt(number=0)
    context.attempts.append(attempt)
    response = await client.send_prepared(prepared, stream=request.stream)
    attempt.status_code = response.status_code
    attempt.completed_at = time.time()
    if not response.is_success:
        body = await response.aread()
        await response.aclose()
        error = ApiError(
            body.decode(errors="replace") or f"HTTP {response.status_code}",
            status_code=response.status_code,
        )
        attempt.error = error
        context.fail(error)
        raise UpstreamResponseError(context, response)
    limiter.report_success()
    context.transition(RequestState.STREAMING if request.stream else RequestState.COMPLETED)
    return PipelineResult(context=context, response=response)