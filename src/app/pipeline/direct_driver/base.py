"""The shared direct-driver loop.

A direct driver is the no-translation path: the inbound format already matches the endpoint.
The payload goes out as it arrived, apart from what subscribers change.

The four named drivers differ only in which endpoint they target, so the loop lives here.
Copying it per endpoint is how the four drift apart.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.model_provider import ModelEndpoint, ModelProvider
from app.pipeline.events import FrozenSubscribers
from app.pipeline.exceptions import Disposition, PipelineAbort, UpstreamTimeout, classify
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
    response: httpx.Response | None = None
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
    ) -> None:
        self._endpoint = endpoint
        self._provider = provider
        self._subscribers = subscribers
        self._budget = budget
        self._attempt_deadline = attempt_deadline

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
            outcome.attempts = context.attempt_count
            try:
                await self._publish(EVENT_ATTEMPT_PREPARE, context, outcome)
                # Subscribers edit the context payload.
                # Re-read it rather than trusting the copy taken when the attempt opened.
                attempt.payload = dict(context.payload)
                response = await self._send(context, attempt.payload)
            except BaseException as error:
                attempt.error = str(error)
                if not await self._handle_failure(error, context, outcome):
                    return outcome
                continue

            attempt.status_code = response.status_code
            outcome.response = response
            try:
                await self._publish(EVENT_ATTEMPT_SUCCEEDED, context, outcome)
                await self._publish(EVENT_REQUEST_SUCCEEDED, context, outcome)
            except BaseException as error:
                outcome.response = None
                attempt.error = str(error)
                if not await self._handle_failure(error, context, outcome):
                    return outcome
                continue
            return outcome

    async def _handle_failure(
        self,
        error: BaseException,
        context: RequestContext,
        outcome: DriverOutcome,
    ) -> bool:
        """Return whether to attempt again. Records the terminal error when not."""
        await self._publish(EVENT_ATTEMPT_FAILED, context, outcome)
        disposition = classify(error)
        if disposition is Disposition.RETRY:
            funded, detail = self._budget.take_for(error)
            if funded:
                return True
            outcome.error = PipelineAbort(f"{detail}: {error}")
            await self._publish(EVENT_REQUEST_FAILED, context, outcome)
            return False
        outcome.error = error
        await self._publish(EVENT_REQUEST_FAILED, context, outcome)
        return False

    async def _send(
        self,
        context: RequestContext,
        payload: dict[str, Any],
    ) -> httpx.Response:
        """Send one attempt, bounded by the attempt deadline when one is configured.

        The deadline bounds the whole attempt rather than a phase of it, which is what catches an
        upstream that trickles forever without ever finishing.
        """
        send = self._provider.send(
            self._endpoint,
            payload,
            model_id=context.resolved_model,
            stream=context.stream,
        )
        if self._attempt_deadline <= 0:
            return await send
        try:
            async with asyncio.timeout(self._attempt_deadline):
                return await send
        except TimeoutError as error:
            raise UpstreamTimeout(
                f"attempt exceeded {self._attempt_deadline}s"
            ) from error
