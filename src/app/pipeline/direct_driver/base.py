"""The shared direct-driver loop.

A direct driver is the no-translation path: the inbound format already matches the endpoint.
The payload goes out as it arrived, apart from what subscribers change.

The four named drivers differ only in which endpoint they target, so the loop lives here.
Copying it per endpoint is how the four drift apart.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx2

from app.model_provider import ModelEndpoint, ModelProvider
from app.pipeline.events import FrozenSubscribers
from app.pipeline.exceptions import (
    Disposition,
    PipelineAbort,
    UpstreamError,
    UpstreamTimeout,
    classify,
)
from app.pipeline.rate_limiting import RateLimiter
from app.pipeline.request import RequestContext
from app.pipeline.retry import RetryLedger, reason_for

EVENT_ATTEMPT_PREPARE = "attempt.prepare"
EVENT_ATTEMPT_SUCCEEDED = "attempt.succeeded"
EVENT_ATTEMPT_FAILED = "attempt.failed"
EVENT_REQUEST_SUCCEEDED = "request.succeeded"
EVENT_REQUEST_FAILED = "request.failed"

EVENTS = (
    EVENT_ATTEMPT_PREPARE,
    EVENT_ATTEMPT_SUCCEEDED,
    EVENT_ATTEMPT_FAILED,
    EVENT_REQUEST_SUCCEEDED,
    EVENT_REQUEST_FAILED,
)


@dataclass(slots=True)
class RetryBudget:
    """A simple shared counter, kept for callers that have no named strategies configured."""

    max_total: int
    spent: int = 0

    def take(self) -> bool:
        if self.spent >= self.max_total:
            return False
        self.spent += 1
        return True

    def take_for(self, error: BaseException) -> tuple[bool, str]:
        return (self.take(), "retry budget exhausted")


@dataclass(slots=True)
class LedgerBudget:
    """Spends the named per-reason strategies alongside the shared total."""

    ledger: RetryLedger

    def take_for(self, error: BaseException) -> tuple[bool, str]:
        reason = reason_for(error)
        if reason is None:
            return (False, "failure is not retryable")
        verdict = self.ledger.take(reason)
        return (verdict.allowed, verdict.detail or f"{reason.value} retry refused")


class Budget(Protocol):
    def take_for(self, error: BaseException) -> tuple[bool, str]: ...


@dataclass(slots=True)
class DriverOutcome:
    context: RequestContext
    response: httpx2.Response | None = None
    error: BaseException | None = None
    attempts: int = 0
    events: list[str] = field(default_factory=lambda: list[str]())

    @property
    def succeeded(self) -> bool:
        return self.response is not None and self.error is None


class DirectDriver:
    def __init__(
        self,
        endpoint: ModelEndpoint,
        provider: ModelProvider,
        subscribers: FrozenSubscribers[RequestContext],
        *,
        budget: Budget,
        attempt_deadline: int = 0,
        response_header_timeout: int = 0,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._provider = provider
        self._subscribers = subscribers
        self._budget = budget
        self._attempt_deadline = attempt_deadline
        self._response_header_timeout = response_header_timeout
        self._rate_limiter = rate_limiter

    @property
    def endpoint(self) -> ModelEndpoint:
        return self._endpoint

    async def _publish(self, event: str, context: RequestContext, outcome: DriverOutcome) -> None:
        """Run one event's subscribers in the frozen order.

        A subscriber raising is how it steers the flow.
        The exception propagates to be classified by the caller rather than swallowed here.
        """
        outcome.events.append(event)
        for subscription in self._subscribers.for_event(event):
            await subscription.handler(context)

    async def run(self, context: RequestContext) -> DriverOutcome:
        outcome = DriverOutcome(context=context)
        while True:
            attempt = context.begin_attempt()
            if self._attempt_deadline > 0:
                # Fixed here rather than at the send, so that everything this attempt does — preparing, waiting on the rate limiter, sending, and then streaming a body long after this function has returned — is measured against one instant.
                attempt.deadline_at = asyncio.get_running_loop().time() + self._attempt_deadline
            outcome.attempts = context.attempt_count
            try:
                await self._publish(EVENT_ATTEMPT_PREPARE, context, outcome)
                # Subscribers edit the context payload.
                # Re-read it rather than trusting the copy taken when the attempt opened.
                attempt.payload = dict(context.payload)
                if self._rate_limiter is not None:
                    context.extras["rate_limit_wait_s"] = await self._rate_limiter.acquire()
                response = await self._send(context, attempt.payload)
            except asyncio.CancelledError:
                # Not a failure this loop gets to have an opinion about. A cancellation is the runtime saying this task stops now, and it is how the layers above express their own deadlines: `handle_bounded` wraps the whole request in `asyncio.timeout`, which fires by cancelling and then reads the cancellation back out to turn it into a `TimeoutError`. Catching it here consumed it, so that conversion never happened and the line meant to answer it — `raise UpstreamTimeout(f"client request exceeded {deadline}s")` — was dead code. The client was told 502 `CancelledError` with an empty message instead of 504. Measured 2026-08-22; see `.dev/docs/upstream/retry-and-continuation/deferred.md` 8a.
                raise
            except BaseException as error:
                attempt.error = str(error)
                if not await self._handle_failure(error, context, outcome):
                    return outcome
                continue

            attempt.status_code = response.status_code
            outcome.response = response
            if self._rate_limiter is not None:
                headers = dict(response.headers)
                if self._rate_limiter.observe_failure(response.status_code, headers):
                    # A limited status is not a delivered response; let the retry path see it.
                    outcome.response = None
                    attempt.error = f"upstream returned {response.status_code}"
                    if not await self._handle_failure(
                        UpstreamError(
                            f"upstream returned {response.status_code}",
                            status_code=response.status_code,
                        ),
                        context,
                        outcome,
                    ):
                        return outcome
                    continue
                self._rate_limiter.observe_success(headers)
            try:
                await self._publish(EVENT_ATTEMPT_SUCCEEDED, context, outcome)
                await self._publish(EVENT_REQUEST_SUCCEEDED, context, outcome)
            except asyncio.CancelledError:
                # Same reason as above, and the same consequence if it were caught: a subscriber's own await can be the one that observes the cancellation.
                outcome.response = None
                raise
            except BaseException as error:
                outcome.response = None
                attempt.error = str(error)
                if not await self._handle_failure(error, context, outcome):
                    return outcome
                continue
            return outcome

    @staticmethod
    def _upstream_status(error: BaseException) -> tuple[int | None, dict[str, str]]:
        """Read the status and headers off a failure.

        The SDKs raise on 4xx and 5xx rather than returning a response, so a limited status
        arrives here as an exception. Reading it only from a returned response would leave the
        limiter blind to every 429.
        """
        status = getattr(error, "status_code", None)
        headers: dict[str, str] = {}
        response = getattr(error, "response", None)
        if response is not None:
            raw = getattr(response, "headers", None)
            if raw is not None:
                headers = {str(k): str(v) for k, v in dict(raw).items()}
            if status is None:
                status = getattr(response, "status_code", None)
        return (status if isinstance(status, int) else None), headers

    async def _handle_failure(
        self,
        error: BaseException,
        context: RequestContext,
        outcome: DriverOutcome,
    ) -> bool:
        """Return whether to attempt again. Records the terminal error when not."""
        if self._rate_limiter is not None:
            status, headers = self._upstream_status(error)
            if status is not None:
                self._rate_limiter.observe_failure(status, headers)
        await self._publish(EVENT_ATTEMPT_FAILED, context, outcome)
        disposition = classify(error)
        if disposition is Disposition.RETRY:
            funded, detail = self._budget.take_for(error)
            if funded:
                return True
            outcome.error = PipelineAbort(f"{detail}: {error}", cause=error)
            await self._publish(EVENT_REQUEST_FAILED, context, outcome)
            return False
        outcome.error = error
        await self._publish(EVENT_REQUEST_FAILED, context, outcome)
        return False

    async def _send(
        self,
        context: RequestContext,
        payload: dict[str, Any],
    ) -> httpx2.Response:
        """Send one attempt under both upstream guards that can act from here.

        This await ends when the response headers arrive, not when the body has been read — measured 2026-08-20 on a server that held the body back two seconds after its headers. So `response_header` is bounded here in full, while the attempt deadline is one bound enforced from two places: a streaming body outlives this function, and the delivery chain holds it to the same instant.

        Both raise `UpstreamTimeout`: both fire while the driver still owns the attempt, so either one leaves through the same path as any other attempt that ran out of time. What is then done about it — another attempt, a continuation, nothing — belongs to the retry configuration, not here.
        """
        send = self._provider.send(
            self._endpoint,
            payload,
            model_id=context.resolved_model,
            stream=context.stream,
            extra_headers=context.client_headers or None,
        )
        attempt = context.current_attempt
        deadline_at = attempt.deadline_at if attempt is not None else None

        async def under_header_guard() -> httpx2.Response:
            if self._response_header_timeout <= 0:
                return await send
            try:
                async with asyncio.timeout(self._response_header_timeout):
                    return await send
            except TimeoutError as error:
                raise UpstreamTimeout(
                    f"no response headers within {self._response_header_timeout}s"
                ) from error

        if deadline_at is None:
            return await under_header_guard()
        try:
            async with asyncio.timeout_at(deadline_at):
                return await under_header_guard()
        except TimeoutError as error:
            # Reached only when the outer guard fired: an `UpstreamTimeout` from the inner one is not a `TimeoutError`, so it passes through with its own account of what ran out.
            raise UpstreamTimeout(f"attempt exceeded {self._attempt_deadline}s") from error
