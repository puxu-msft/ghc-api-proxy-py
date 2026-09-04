import asyncio
from collections.abc import Mapping
from typing import Any

import httpx2
import pytest

import app.pipeline.direct_driver.base as driver_module
from app.model_provider import ModelDescriptor, ModelEndpoint, PromptTokenLimits
from app.pipeline.direct_driver import (
    EVENT_ATTEMPT_FAILED,
    EVENT_ATTEMPT_PREPARE,
    OpenAIResponsesDriver,
    RetryBudget,
)
from app.pipeline.events import SubscriberRegistry
from app.pipeline.exceptions import (
    PipelineAbort,
    PromptTokenLimitExceeded,
    UpstreamError,
    UpstreamTimeout,
)
from app.pipeline.request import RequestContext, WireFormat
from app.tokenization.admission import (
    PromptTokenAdmission,
    TokenAdmissionObservation,
    TokenAdmissionOutcome,
)


def descriptor(model: str = "gpt-model") -> ModelDescriptor:
    return ModelDescriptor(
        id=model,
        endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES}),
        provider_name="ghc",
        catalog_generation=7,
        catalog_refreshed_at="2026-09-04T00:00:00+00:00",
        prompt_token_limits=PromptTokenLimits(
            tokenizer="o200k_base",
            max_prompt_tokens=8,
            max_context_window_tokens=10,
        ),
    )


def context(payload: dict[str, Any] | None = None) -> RequestContext:
    model = descriptor()
    return RequestContext(
        inbound_format=WireFormat.OPENAI_RESPONSES,
        requested_model=model.id,
        resolved_model=model.id,
        provider_name=model.provider_name,
        endpoint=ModelEndpoint.OPENAI_RESPONSES,
        target_format=WireFormat.OPENAI_RESPONSES,
        model_descriptor=model,
        payload=payload or {"model": model.id, "input": "short"},
    )


class RecordingProvider:
    name = "ghc"
    base_url = "https://upstream.invalid"
    catalog_refreshed_at = "2026-09-04T00:00:00+00:00"
    available_ids = frozenset({"gpt-model"})
    disabled_ids: frozenset[str] = frozenset()
    raw_catalog: Mapping[str, Any] = {}

    def __init__(self, responses: list[httpx2.Response | BaseException] | None = None) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self._responses = responses or [httpx2.Response(200)]

    def describe(self, model_id: str) -> ModelDescriptor | None:
        return descriptor(model_id) if model_id == "gpt-model" else None

    async def refresh_catalog(self) -> bool:
        return False

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Mapping[str, Any],
        *,
        descriptor: ModelDescriptor,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        del endpoint, stream, extra_headers
        self.sent.append((descriptor.id, dict(payload)))
        result = self._responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    async def count_tokens(
        self,
        payload: Mapping[str, Any],
        *,
        descriptor: ModelDescriptor,
    ) -> httpx2.Response:
        del payload, descriptor
        raise NotImplementedError


class CountingLimiter:
    def __init__(self) -> None:
        self.calls = 0

    async def acquire(self) -> float:
        self.calls += 1
        return 0.0

    def observe_failure(self, _status: int, _headers: Mapping[str, str]) -> bool:
        return False

    def observe_success(self, _headers: Mapping[str, str]) -> None:
        return None


class AdvancingAdmission:
    def __init__(self, clock: list[float], *, advance_to: float | None = None) -> None:
        self.clock = clock
        self.advance_to = advance_to
        self.calls = 0

    async def evaluate(
        self,
        *,
        attempt: int,
        target_format: str,
        descriptor: ModelDescriptor,
        payload: dict[str, Any],
    ) -> TokenAdmissionObservation:
        del payload
        self.calls += 1
        if self.advance_to is not None:
            self.clock[0] = self.advance_to
        limits = descriptor.prompt_token_limits
        assert limits is not None
        return TokenAdmissionObservation(
            attempt=attempt,
            origin="proxy",
            outcome=TokenAdmissionOutcome.ADMITTED_FAST,
            target_format=target_format,
            model=descriptor.id,
            provider=descriptor.provider_name,
            catalog_generation=descriptor.catalog_generation,
            catalog_refreshed_at=descriptor.catalog_refreshed_at,
            tokenizer=limits.tokenizer,
            max_prompt_tokens=limits.max_prompt_tokens,
            max_context_window_tokens=limits.max_context_window_tokens,
            field_path="input",
            field_kind="input",
            field_utf8_byte_count=5,
        )


def driver(
    provider: RecordingProvider,
    *,
    registry: SubscriberRegistry[RequestContext] | None = None,
    admission: Any = None,
    limiter: Any = None,
    clock: Any = None,
    attempt_deadline: int = 0,
    max_total: int = 0,
) -> OpenAIResponsesDriver:
    return OpenAIResponsesDriver(
        provider,
        (registry or SubscriberRegistry[RequestContext]()).freeze(),
        budget=RetryBudget(max_total=max_total),
        descriptor=descriptor(),
        admission=admission or PromptTokenAdmission(),
        rate_limiter=limiter,
        clock=clock,
        attempt_deadline=attempt_deadline,
    )


@pytest.mark.asyncio
async def test_last_prepare_rewrite_is_admitted_before_limiter_or_network() -> None:
    registry = SubscriberRegistry[RequestContext]()

    async def expand(request: RequestContext) -> None:
        request.payload["input"] = "0123456789" * 100

    registry.subscribe(EVENT_ATTEMPT_PREPARE, "test:expand", expand)
    provider = RecordingProvider()
    limiter = CountingLimiter()

    outcome = await driver(provider, registry=registry, limiter=limiter).run(context())

    assert isinstance(outcome.error, PromptTokenLimitExceeded)
    assert outcome.attempts == 1
    assert limiter.calls == 0
    assert provider.sent == []


@pytest.mark.asyncio
async def test_private_snapshot_does_not_share_nested_payload_during_limiter_wait() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class WaitingLimiter(CountingLimiter):
        async def acquire(self) -> float:
            self.calls += 1
            entered.set()
            await release.wait()
            return 0.0

    payload = {
        "model": "gpt-model",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "original"}],
            }
        ],
    }
    request = context(payload)
    provider = RecordingProvider()
    running = asyncio.create_task(driver(provider, limiter=WaitingLimiter()).run(request))
    await asyncio.wait_for(entered.wait(), timeout=1)
    request.payload["input"][0]["content"][0]["text"] = "mutated after admission"
    release.set()
    outcome = await running

    assert outcome.succeeded is True
    assert provider.sent[0][1]["input"][0]["content"][0]["text"] == "original"


@pytest.mark.asyncio
async def test_prepare_cannot_reroute_the_captured_descriptor() -> None:
    registry = SubscriberRegistry[RequestContext]()

    async def reroute(request: RequestContext) -> None:
        request.payload["model"] = "other-model"
        request.resolved_model = "other-model"
        request.provider_name = "other"
        request.model_descriptor = ModelDescriptor(
            id="other-model",
            endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES}),
            provider_name="other",
        )

    registry.subscribe(EVENT_ATTEMPT_PREPARE, "test:reroute", reroute)
    provider = RecordingProvider()

    outcome = await driver(provider, registry=registry).run(context())

    assert outcome.succeeded is True
    assert provider.sent == [("gpt-model", {"model": "gpt-model", "input": "short"})]


@pytest.mark.asyncio
async def test_deadline_after_deepcopy_stops_before_policy_limiter_and_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    real_deepcopy = driver_module.deepcopy

    def slow_copy(payload: dict[str, Any]) -> dict[str, Any]:
        copied = real_deepcopy(payload)
        clock[0] = 2.0
        return copied

    monkeypatch.setattr(driver_module, "deepcopy", slow_copy)
    policy = AdvancingAdmission(clock)
    limiter = CountingLimiter()
    provider = RecordingProvider()

    outcome = await driver(
        provider,
        admission=policy,
        limiter=limiter,
        clock=lambda: clock[0],
        attempt_deadline=1,
    ).run(context())

    assert isinstance(outcome.error, PipelineAbort)
    assert isinstance(outcome.error.cause, UpstreamTimeout)
    assert policy.calls == 0
    assert limiter.calls == 0
    assert provider.sent == []


@pytest.mark.asyncio
async def test_deadline_after_fast_policy_stops_before_limiter_and_provider() -> None:
    clock = [0.0]
    policy = AdvancingAdmission(clock, advance_to=2.0)
    limiter = CountingLimiter()
    provider = RecordingProvider()

    outcome = await driver(
        provider,
        admission=policy,
        limiter=limiter,
        clock=lambda: clock[0],
        attempt_deadline=1,
    ).run(context())

    assert isinstance(outcome.error, PipelineAbort)
    assert isinstance(outcome.error.cause, UpstreamTimeout)
    assert policy.calls == 1
    assert limiter.calls == 0
    assert provider.sent == []


@pytest.mark.asyncio
async def test_deadline_after_zero_wait_limiter_stops_before_provider() -> None:
    clock = [0.0]

    class AdvancingLimiter(CountingLimiter):
        async def acquire(self) -> float:
            self.calls += 1
            clock[0] = 2.0
            return 0.0

    policy = AdvancingAdmission(clock)
    limiter = AdvancingLimiter()
    provider = RecordingProvider()

    outcome = await driver(
        provider,
        admission=policy,
        limiter=limiter,
        clock=lambda: clock[0],
        attempt_deadline=1,
    ).run(context())

    assert isinstance(outcome.error, PipelineAbort)
    assert isinstance(outcome.error.cause, UpstreamTimeout)
    assert policy.calls == 1
    assert limiter.calls == 1
    assert provider.sent == []


@pytest.mark.asyncio
async def test_retry_rechecks_payload_and_rejects_before_second_limiter_and_send() -> None:
    registry = SubscriberRegistry[RequestContext]()

    async def expand_after_failure(request: RequestContext) -> None:
        request.payload["input"] = "0123456789" * 100

    registry.subscribe(EVENT_ATTEMPT_FAILED, "test:expand", expand_after_failure)
    provider = RecordingProvider(
        [UpstreamError("try again", status_code=503), httpx2.Response(200)]
    )
    limiter = CountingLimiter()

    outcome = await driver(
        provider,
        registry=registry,
        limiter=limiter,
        max_total=1,
    ).run(context())

    assert isinstance(outcome.error, PromptTokenLimitExceeded)
    assert outcome.attempts == 2
    assert limiter.calls == 1
    assert len(provider.sent) == 1
    observations = [attempt.token_admission for attempt in outcome.context.attempts]
    assert all(observation is not None for observation in observations)
    assert [
        observation.outcome
        for observation in observations
        if observation is not None
    ] == [TokenAdmissionOutcome.ADMITTED_FAST, TokenAdmissionOutcome.REJECTED]
