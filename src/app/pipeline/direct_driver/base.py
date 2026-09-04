"""The shared direct-driver loop.

A direct driver is the no-translation path: the inbound format already matches the endpoint.
The payload goes out as it arrived, apart from what subscribers change.

The four named drivers differ only in which endpoint they target, so the loop lives here.
Copying it per endpoint is how the four drift apart.
"""

import asyncio
import sys
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import httpx2

from app.model_provider import (
    ModelDescriptor,
    ModelEndpoint,
    ModelProvider,
    require_descriptor_owner,
    require_endpoint,
)
from app.pipeline.events import FrozenSubscribers
from app.pipeline.exceptions import (
    Disposition,
    PipelineAbort,
    PromptTokenLimitExceeded,
    UpstreamError,
    UpstreamTimeout,
    classify,
)
from app.pipeline.rate_limiting import RateLimiter
from app.pipeline.request import ENDPOINT_FORMATS, Attempt, RequestContext
from app.pipeline.retry import RetryLedger, reason_for
from app.streaming.keepalive import (
    find_cancellation,
    finish_async_cleanup,
    raise_with_cleanup_under,
)
from app.tokenization.admission import (
    TokenAdmissionObservation,
    TokenAdmissionOutcome,
    reuse_token_admission,
)

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


def _clear_exception_backedges(
    error: BaseException,
    target: BaseException,
    seen: set[int] | None = None,
) -> None:
    """Remove direct links back to an exit that is becoming the primary."""
    visited: set[int] = seen if seen is not None else set()
    if id(error) in visited:
        return
    visited.add(id(error))

    for attribute in ("__cause__", "__context__"):
        linked = getattr(error, attribute)
        if linked is target:
            setattr(error, attribute, None)
        elif linked is not None:
            _clear_exception_backedges(linked, target, visited)
    if isinstance(error, BaseExceptionGroup):
        group = cast(BaseExceptionGroup[BaseException], error)
        for member in group.exceptions:
            _clear_exception_backedges(member, target, visited)


def _without_exception(
    error: BaseException,
    target: BaseException,
) -> BaseException | None:
    """Remove one selected exit while preserving group metadata and shape."""
    if error is target:
        return None
    residual = error
    if isinstance(error, BaseExceptionGroup):
        group = cast(BaseExceptionGroup[BaseException], error)
        _, remainder = group.split(lambda candidate: candidate is target)
        if remainder is None:
            return None
        residual = remainder
    _clear_exception_backedges(residual, target)
    return residual


def _reraise_if_cancelling(error: BaseException) -> None:
    """Keep cancellation in control when cleanup replaced its top-level type."""
    current = asyncio.current_task()
    cancellation = find_cancellation(error)
    if current is None or current.cancelling() <= 0 or cancellation is None:
        return
    secondary = _without_exception(error, cancellation)
    if secondary is not None:
        raise_with_cleanup_under(cancellation, secondary)
    raise cancellation


async def _finish_response_cleanup(
    response: httpx2.Response,
    *,
    primary: BaseException | None,
    discard_reason: BaseException | None = None,
) -> None:
    cleanup_error, cleanup_cancellation = await finish_async_cleanup(
        response.aclose,
        primary=primary,
    )
    active_primary = primary
    if active_primary is None:
        active_primary = cleanup_cancellation
    if (
        active_primary is None
        and cleanup_error is not None
        and discard_reason is not None
    ):
        # A retry decision already consumed this failure. Bring it back only when closing the discarded response also failed, so both facts survive; a new cancellation during an otherwise successful close still belongs to the outer deadline or shutdown.
        active_primary = discard_reason
    if active_primary is not None:
        if cleanup_error is not None:
            raise_with_cleanup_under(active_primary, cleanup_error)
        if cleanup_cancellation is not None:
            raise active_primary
    elif cleanup_error is not None:
        raise cleanup_error


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
    # Whether the process has stopped accepting. `None` on the paths that have no listener to ask — a test harness, or a caller driving a driver directly — and those simply never refuse for this reason.
    #
    # A retry opens a *new* upstream request, and doing that while shutting down is work the process has already promised to stop taking on: it extends the drain by a whole attempt, and if the drain gives up first the client gets neither the retry's answer nor the one it was owed. `upstream-retry-and-continuation.md` rules it out.
    #
    # This door refuses before upstream's headers are in hand, so what the client gets is an ordinary HTTP error response carrying upstream's own status — the hand-over lives on the SSE delivery path and is not reachable from here at all. The sibling gate in `pipeline_app._reopen` is the one where that question arises.
    draining: Callable[[], bool] | None = None

    def take_for(self, error: BaseException) -> tuple[bool, str]:
        # Before the ledger, so a shutdown does not also show up as budget exhaustion in whatever reads the counters next. Not because anything downstream needs the budget intact — checked: nothing on the hand-over path reads `RetryLedger` — and the delivery-side replay spends its own attempt *before* its drain check, so the two doors differ on this. Refusing first is the honest report of why, not a resource decision.
        if self.draining is not None and self.draining():
            return (False, "server is shutting down")
        reason = reason_for(error)
        if reason is None:
            return (False, "failure is not retryable")
        verdict = self.ledger.take(reason)
        return (verdict.allowed, verdict.detail or f"{reason.value} retry refused")


class Budget(Protocol):
    def take_for(self, error: BaseException) -> tuple[bool, str]: ...


class AdmissionPolicy(Protocol):
    async def evaluate(
        self,
        *,
        attempt: int,
        target_format: str,
        descriptor: ModelDescriptor,
        payload: dict[str, Any],
    ) -> TokenAdmissionObservation: ...


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
        descriptor: ModelDescriptor | None = None,
        admission: AdmissionPolicy | None = None,
        prepared_payload: Mapping[str, Any] | None = None,
        reused_admission: TokenAdmissionObservation | None = None,
        attempt_deadline: int = 0,
        response_header_timeout: int = 0,
        rate_limiter: RateLimiter | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if (descriptor is None) is not (admission is None):
            raise ValueError("descriptor and admission must be configured together")
        if (prepared_payload is None) is not (reused_admission is None):
            raise ValueError("prepared payload and reused admission must be configured together")
        if prepared_payload is not None and descriptor is None:
            raise ValueError("prepared replay requires a routed descriptor and admission policy")
        target_format = ENDPOINT_FORMATS[endpoint].value
        if descriptor is not None:
            require_descriptor_owner(descriptor, provider.name)
            require_endpoint(descriptor, endpoint, provider.name)
        if reused_admission is not None and descriptor is not None:
            if (
                reused_admission.model != descriptor.id
                or reused_admission.provider != descriptor.provider_name
                or reused_admission.catalog_generation != descriptor.catalog_generation
                or reused_admission.target_format != target_format
            ):
                raise ValueError("reused admission does not belong to the captured route")
            reuse_token_admission(reused_admission, attempt=reused_admission.attempt)
        self._endpoint = endpoint
        self._target_format = target_format
        self._provider = provider
        self._subscribers = subscribers
        self._budget = budget
        self._descriptor = descriptor
        self._admission = admission
        self._prepared_payload = (
            deepcopy(dict(prepared_payload)) if prepared_payload is not None else None
        )
        self._reused_admission = reused_admission
        self._attempt_deadline = attempt_deadline
        self._response_header_timeout = response_header_timeout
        self._rate_limiter = rate_limiter
        self._clock = clock

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

    def _now(self) -> float:
        return self._clock() if self._clock is not None else asyncio.get_running_loop().time()

    def _raise_if_deadline_elapsed(self, attempt: Attempt) -> None:
        if attempt.deadline_at is not None and self._now() >= attempt.deadline_at:
            raise UpstreamTimeout(f"attempt exceeded {self._attempt_deadline}s")

    async def _prepare_and_send(
        self,
        context: RequestContext,
        outcome: DriverOutcome,
        attempt: Attempt,
    ) -> httpx2.Response:
        source_payload: Mapping[str, Any] = context.payload
        if self._prepared_payload is None:
            await self._publish(EVENT_ATTEMPT_PREPARE, context, outcome)
        else:
            source_payload = self._prepared_payload
        if self._descriptor is not None and self._admission is not None:
            # A private structural copy closes the nested-alias window between the final mutable subscriber and the rate-limiter wait. The same object is admitted and sent. A delivery replay starts from the source attempt's already-final copy and makes another private copy rather than rerunning mutable shaping.
            attempt.payload = deepcopy(dict(source_payload))
            attempt.payload["model"] = self._descriptor.id
            self._raise_if_deadline_elapsed(attempt)
            if self._reused_admission is not None:
                attempt.token_admission = reuse_token_admission(
                    self._reused_admission,
                    attempt=attempt.index,
                )
            else:
                observation = await self._admission.evaluate(
                    attempt=attempt.index,
                    target_format=self._target_format,
                    descriptor=self._descriptor,
                    payload=attempt.payload,
                )
                attempt.token_admission = observation
                self._raise_if_deadline_elapsed(attempt)
                if observation.outcome is TokenAdmissionOutcome.REJECTED:
                    raise PromptTokenLimitExceeded(observation)
        else:
            # Compatibility path for direct driver tests and callers that have not routed a model. Production configures both descriptor and admission.
            attempt.payload = dict(source_payload)
        if self._rate_limiter is not None:
            context.extras["rate_limit_wait_s"] = await self._rate_limiter.acquire()
            self._raise_if_deadline_elapsed(attempt)
        return await self._send(context, attempt.payload)

    async def _run_attempt(
        self,
        context: RequestContext,
        outcome: DriverOutcome,
        attempt: Attempt,
    ) -> httpx2.Response:
        if attempt.deadline_at is None:
            return await self._prepare_and_send(context, outcome, attempt)
        timeout = asyncio.timeout_at(attempt.deadline_at)
        try:
            async with timeout:
                return await self._prepare_and_send(context, outcome, attempt)
        except TimeoutError as error:
            if timeout.expired():
                raise UpstreamTimeout(f"attempt exceeded {self._attempt_deadline}s") from error
            raise

    async def run(self, context: RequestContext) -> DriverOutcome:
        outcome = DriverOutcome(context=context)
        while True:
            attempt = context.begin_attempt()
            if self._attempt_deadline > 0:
                # One instant covers prepare, admission, limiter wait, response headers and the body that delivery consumes after this function returns.
                attempt.deadline_at = self._now() + self._attempt_deadline
            outcome.attempts = context.attempt_count
            try:
                response = await self._run_attempt(context, outcome, attempt)
            except asyncio.CancelledError:
                # Not a failure this loop gets to have an opinion about. A cancellation is the runtime saying this task stops now, and it is how the layers above express their own deadlines: `handle_bounded` wraps the whole request in `asyncio.timeout`, which fires by cancelling and then reads the cancellation back out to turn it into a `TimeoutError`. Catching it here consumed it, so that conversion never happened and the line meant to answer it — `raise UpstreamTimeout(f"client request exceeded {deadline}s")` — was dead code. The client was told 502 `CancelledError` with an empty message instead of 504. Measured 2026-08-22; see `.dev/docs/upstream/retry-and-continuation/deferred.md` 8a.
                raise
            except BaseException as error:
                _reraise_if_cancelling(error)
                attempt.error = str(error)
                if not await self._handle_failure(error, context, outcome):
                    return outcome
                continue

            attempt.status_code = response.status_code
            outcome.response = response
            handed_off = False
            discard_reason: BaseException | None = None
            try:
                if self._rate_limiter is not None:
                    headers = dict(response.headers)
                    if self._rate_limiter.observe_failure(response.status_code, headers):
                        # A limited status is not a delivered response; let the retry path see it. A buffered body is retained for the error observer, while a streaming response has not been read and must not be forced here.
                        outcome.response = None
                        attempt.error = f"upstream returned {response.status_code}"
                        body_bytes = (
                            response.content if response.is_stream_consumed else b""
                        )
                        discard_reason = UpstreamError(
                            f"upstream returned {response.status_code}",
                            status_code=response.status_code,
                            headers=response.headers,
                            body=(response.text if body_bytes else ""),
                            body_bytes=body_bytes,
                            content_type=response.headers.get("content-type", ""),
                            body_observed=response.is_stream_consumed,
                        )
                        if not await self._handle_failure(
                            discard_reason,
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
                    # The response is still this driver's until both success events return. The owner cleanup in `finally` releases it before cancellation leaves.
                    outcome.response = None
                    raise
                except BaseException as error:
                    _reraise_if_cancelling(error)
                    outcome.response = None
                    attempt.error = str(error)
                    discard_reason = error
                    if not await self._handle_failure(error, context, outcome):
                        return outcome
                    continue
                handed_off = True
                return outcome
            finally:
                if not handed_off:
                    outcome.response = None
                    await _finish_response_cleanup(
                        response,
                        primary=sys.exception(),
                        discard_reason=discard_reason,
                    )

    @staticmethod
    def _upstream_status(error: BaseException) -> tuple[int | None, dict[str, str]]:
        """Read the status and headers off a failure.

        The SDKs raise on 4xx and 5xx rather than returning a response, so a limited status arrives here as an exception. Reading it only from a returned response would leave the limiter blind to every 429.
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
        """Send one attempt until its response headers arrive.

        The whole-attempt deadline surrounds this call in `_run_attempt`; this narrower guard says specifically that upstream produced no headers within `response_header_timeout`.
        """
        descriptor = self._descriptor or self._provider.describe(context.resolved_model)
        if descriptor is None:
            raise RuntimeError("direct driver has no routed model descriptor")
        send = self._provider.send(
            self._endpoint,
            payload,
            descriptor=descriptor,
            stream=context.stream,
            extra_headers=context.client_headers or None,
        )
        if self._response_header_timeout <= 0:
            return await send
        try:
            async with asyncio.timeout(self._response_header_timeout):
                return await send
        except TimeoutError as error:
            raise UpstreamTimeout(
                f"no response headers within {self._response_header_timeout}s"
            ) from error
