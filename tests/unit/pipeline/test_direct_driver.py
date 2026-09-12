import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import anyio
import httpx2
import pytest

from app.config.schema import ProxyConfig
from app.model_provider import (
    EndpointNotSupported,
    ModelDescriptor,
    ModelEndpoint,
    ProviderRegistry,
)
from app.pipeline.direct_driver import (
    EVENT_ATTEMPT_FAILED,
    EVENT_ATTEMPT_PREPARE,
    EVENT_REQUEST_FAILED,
    EVENT_REQUEST_SUCCEEDED,
    PROVIDER_BOUND_OBSERVER,
    AnthropicMessagesDriver,
    DirectDriver,
    RetryBudget,
)
from app.pipeline.driver import (
    _reencode_target_payload,  # pyright: ignore[reportPrivateUsage]
    handle,
)
from app.pipeline.events import SubscriberRegistry
from app.pipeline.exceptions import PipelineAbort, PipelineRetry, UpstreamError
from app.pipeline.rate_limiting import RateLimiter, RateLimitMode
from app.pipeline.request import FORMAT_ENDPOINTS, RequestContext, WireFormat
from app.pipeline.routing import RoutingError, decide_route, split_format_suffix
from app.pipeline.translation_driver.options import TranslationOptions
from app.pipeline.translation_driver.registry import default_registry
from app.pipeline.translation_driver.semantic import TranslationTarget
from app.server.composition import build_chain

CATALOG: dict[str, ModelDescriptor] = {
    "claude-model": ModelDescriptor(
        id="claude-model",
        endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
    ),
    "gpt-model": ModelDescriptor(
        id="gpt-model",
        endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES}),
    ),
    "dual-model": ModelDescriptor(
        id="dual-model",
        endpoints=frozenset(
            {ModelEndpoint.ANTHROPIC_MESSAGES, ModelEndpoint.OPENAI_RESPONSES}
        ),
    ),
    "ws-only-model": ModelDescriptor(
        id="ws-only-model",
        endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES_WS}),
    ),
    "mute-model": ModelDescriptor(id="mute-model", endpoints=frozenset()),
}


class FakeProvider:
    def __init__(self, *, responses: list[Any] | None = None) -> None:
        self.name = "ghc"
        self.sent: list[tuple[ModelEndpoint, dict[str, Any]]] = []
        # Recorded rather than discarded: the header path existed as a parameter on every layer for a long time with nothing ever filling it, and a fake that drops the value cannot tell that state apart from a working one.
        self.sent_headers: list[Any] = []
        self.sent_interaction_ids: list[str | None] = []
        self._responses = responses or []

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset(CATALOG)

    @property
    def raw_catalog(self) -> Mapping[str, Any]:
        return {}

    @property
    def disabled_ids(self) -> frozenset[str]:
        return frozenset()

    @property
    def base_url(self) -> str:
        return "https://fake.invalid"

    @property
    def catalog_refreshed_at(self) -> str:
        return "2026-08-27T00:00:00+00:00"

    def describe(self, model_id: str) -> ModelDescriptor | None:
        return CATALOG.get(model_id)

    async def refresh_catalog(self) -> bool:
        return False

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Any,
        *,
        descriptor: ModelDescriptor,
        stream: bool = False,
        extra_headers: Any = None,
        interaction_id: str | None = None,
    ) -> httpx2.Response:
        self.sent.append((endpoint, dict(payload)))
        self.sent_headers.append(extra_headers)
        self.sent_interaction_ids.append(interaction_id)
        outcome = self._responses.pop(0) if self._responses else httpx2.Response(200)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def count_tokens(self, payload: Any, *, descriptor: ModelDescriptor) -> httpx2.Response:
        # Present so the fake really satisfies the protocol. Nothing here counts tokens, and a silent stub would let a test think it had.
        raise NotImplementedError("this fake does not count tokens")


def context(model: str = "claude-model") -> RequestContext:
    ctx = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model=model,
        payload={"model": model, "messages": []},
    )
    ctx.resolved_model = model
    return ctx


def driver(
    provider: FakeProvider,
    registry: SubscriberRegistry[RequestContext] | None = None,
    *,
    max_total: int = 3,
) -> DirectDriver:
    frozen = (registry or SubscriberRegistry[RequestContext]()).freeze()
    return AnthropicMessagesDriver(provider, frozen, budget=RetryBudget(max_total=max_total))


class UnreadStream(httpx2.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"unread"


class CheckpointCloseStream(httpx2.AsyncByteStream):
    def __init__(self) -> None:
        self.close_started = asyncio.Event()
        self.close_finished = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"unread"

    async def aclose(self) -> None:
        self.close_started.set()
        # AnyIO level cancellation is delivered again at this checkpoint unless response cleanup runs in its own task.
        await asyncio.sleep(0)
        self.close_finished.set()


class FailingCloseStream(CheckpointCloseStream):
    async def aclose(self) -> None:
        self.close_started.set()
        await asyncio.sleep(0)
        raise RuntimeError("response close failed")


class SlowCloseStream(CheckpointCloseStream):
    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()

    async def aclose(self) -> None:
        self.close_started.set()
        await self.release.wait()
        self.close_finished.set()


class RejectingRateLimiter:
    async def acquire(self) -> float:
        return 0.0

    def observe_failure(self, _status: int, _headers: dict[str, str]) -> bool:
        return True

    def observe_success(self, _headers: dict[str, str]) -> None:
        pass

    def note_failure(self) -> None:
        pass


def routing_registry(provider: FakeProvider | None = None) -> ProviderRegistry:
    """A one-provider registry, which is what these routing tests are about.

    `decide_route` takes the registry rather than a provider since routing began choosing between providers: the choice is part of the routing decision, so handing it a single provider would test a function that no longer exists.
    """
    return ProviderRegistry({"ghc": provider or FakeProvider()}, default="ghc")


@pytest.mark.asyncio
async def test_unconsumed_stream_status_body_stays_unobserved() -> None:
    owned = CheckpointCloseStream()
    provider = FakeProvider(
        responses=[
            httpx2.Response(
                429,
                stream=owned,
                headers={"content-type": "application/json"},
            )
        ]
    )
    direct = DirectDriver(
        ModelEndpoint.ANTHROPIC_MESSAGES,
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=RetryBudget(max_total=0),
        rate_limiter=cast(Any, RejectingRateLimiter()),
    )
    request = context()
    request.stream = True

    outcome = await direct.run(request)

    assert isinstance(outcome.error, PipelineAbort)
    assert isinstance(outcome.error.cause, UpstreamError)
    assert outcome.error.cause.status_code == 429
    assert outcome.error.cause.body_bytes == b""
    assert outcome.error.cause.body_observed is False
    assert owned.close_started.is_set()
    assert owned.close_finished.is_set()


@pytest.mark.asyncio
async def test_cancellation_during_retry_cleanup_stays_cancellation() -> None:
    owned = SlowCloseStream()
    provider = FakeProvider(
        responses=[httpx2.Response(429, stream=owned)]
    )
    direct = DirectDriver(
        ModelEndpoint.ANTHROPIC_MESSAGES,
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=RetryBudget(max_total=1),
        rate_limiter=cast(Any, RejectingRateLimiter()),
    )
    request = context()
    request.stream = True
    running = asyncio.create_task(direct.run(request))
    await asyncio.wait_for(owned.close_started.wait(), timeout=1)

    running.cancel()
    owned.release.set()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert owned.close_finished.is_set()
    assert len(provider.sent) == 1


@pytest.mark.asyncio
async def test_deadline_during_retry_cleanup_stays_a_timeout() -> None:
    owned = SlowCloseStream()
    provider = FakeProvider(
        responses=[httpx2.Response(429, stream=owned)]
    )
    direct = DirectDriver(
        ModelEndpoint.ANTHROPIC_MESSAGES,
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=RetryBudget(max_total=1),
        rate_limiter=cast(Any, RejectingRateLimiter()),
    )
    request = context()
    request.stream = True

    async def run() -> None:
        async with asyncio.timeout(0.05):
            await direct.run(request)

    running = asyncio.create_task(run())
    await asyncio.wait_for(owned.close_started.wait(), timeout=1)
    await asyncio.sleep(0.06)
    owned.release.set()

    with pytest.raises(TimeoutError):
        await running

    assert owned.close_finished.is_set()
    assert len(provider.sent) == 1


def test_an_unknown_mapping_provider_uses_the_default_provider() -> None:
    route = decide_route(
        requested_model="claude-opus-4.8",
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        providers=routing_registry(),
        mappings={"claude-opus-4.8": "typo/claude-model"},
    )

    assert route.provider_name == "ghc"
    assert route.model_id == "claude-model"


def test_an_unknown_request_provider_uses_the_default_provider() -> None:
    route = decide_route(
        requested_model="typo/claude-model",
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        providers=routing_registry(),
        mappings={},
    )

    assert route.provider_name == "ghc"
    assert route.model_id == "claude-model"


def test_unavailable_model_on_a_configured_provider_is_not_reported_as_unknown_provider() -> None:
    with pytest.raises(RoutingError) as raised:
        decide_route(
            requested_model="alias",
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            providers=routing_registry(),
            mappings={"alias": "ghc/missing-model"},
        )

    assert "provider 'ghc' is not configured" not in str(raised.value)


def test_route_needs_no_translation_when_the_model_speaks_the_inbound_format() -> None:
    route = decide_route(
        requested_model="claude-model",
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        providers=routing_registry(),
        mappings={},
    )
    assert route.endpoint is ModelEndpoint.ANTHROPIC_MESSAGES
    assert route.translation_required is False
    assert route.reason == "inbound_format_supported"


def test_route_requires_translation_when_the_model_speaks_another_format() -> None:
    route = decide_route(
        requested_model="gpt-model",
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        providers=routing_registry(),
        mappings={},
    )
    assert route.endpoint is ModelEndpoint.OPENAI_RESPONSES
    assert route.target_format is WireFormat.OPENAI_RESPONSES
    assert route.translation_required is True


def test_explicit_format_suffix_selects_the_endpoint() -> None:
    route = decide_route(
        requested_model="dual-model@openai-responses",
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        providers=routing_registry(),
        mappings={},
    )
    assert route.endpoint is ModelEndpoint.OPENAI_RESPONSES
    assert route.reason == "explicit_format"
    assert route.translation_required is True


def test_explicit_format_the_model_lacks_is_refused() -> None:
    with pytest.raises(EndpointNotSupported):
        decide_route(
            requested_model="claude-model@openai-responses",
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            providers=routing_registry(),
            mappings={},
        )


def test_unknown_format_suffix_is_an_error_not_part_of_the_name() -> None:
    with pytest.raises(RoutingError, match="unknown target format"):
        split_format_suffix("some-model@no-such-format")


@pytest.mark.parametrize(
    "unroutable", sorted(set(WireFormat) - set(FORMAT_ENDPOINTS), key=str) or [None]
)
def test_a_named_format_with_no_endpoint_is_refused_rather_than_crashing(
    unroutable: WireFormat | None,
) -> None:
    """The gap a route table opens when it has to name a format nothing can route to.

    `WireFormat` carries a member per wire shape the routes know about, and `FORMAT_ENDPOINTS` maps only the ones an upstream endpoint answers to. Judged on the enum alone, `split_format_suffix` accepted the difference between those two sets and `decide_route` then died on a `KeyError` — which reached the client on `/v1/messages` as a 502 whose body was the `repr` of an enum member. Measured 2026-08-23, the day `GEMINI_GENERATE_CONTENT` was added.

    Parametrized over the set difference rather than over `gemini-generate-content` by name, because that name will move into `FORMAT_ENDPOINTS` the day Gemini is implemented and a test naming it would then be asserting something else while still passing. `[None]` keeps this collectable when the difference is empty — there is nothing to refuse then, which is a legitimate state and not a reason to fail.
    """
    if unroutable is None:
        pytest.skip("every WireFormat currently maps to an endpoint")
    with pytest.raises(RoutingError, match="has no endpoint"):
        split_format_suffix(f"some-model@{unroutable.value}")


def test_model_with_only_an_undriveable_endpoint_is_refused() -> None:
    # ws:/responses is advertised but has no driver, so routing must not select it.
    with pytest.raises(EndpointNotSupported):
        decide_route(
            requested_model="ws-only-model",
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            providers=routing_registry(),
            mappings={},
        )


def test_route_applies_model_mappings() -> None:
    route = decide_route(
        requested_model="opus",
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        providers=routing_registry(),
        mappings={"opus": "claude-model"},
    )
    assert route.model_id == "claude-model"


def test_route_rejects_an_unmapped_unknown_model() -> None:
    with pytest.raises(RoutingError, match="no configured provider offers"):
        decide_route(
            requested_model="mystery",
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            providers=routing_registry(),
            mappings={},
        )


def test_mapping_follows_an_unavailable_alias_to_the_next_mapping() -> None:
    route = decide_route(
        requested_model="alias",
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        providers=routing_registry(),
        mappings={"alias": "missing", "missing": "claude-model"},
    )

    assert route.model_id == "claude-model"


def test_mapping_value_can_select_the_outbound_format() -> None:
    route = decide_route(
        requested_model="alias",
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        providers=routing_registry(),
        mappings={"alias": "gpt-model@openai-responses"},
    )

    assert route.model_id == "gpt-model"
    assert route.endpoint is ModelEndpoint.OPENAI_RESPONSES
    assert route.reason == "mapped_format"


@pytest.mark.asyncio
async def test_successful_attempt_publishes_the_success_events() -> None:
    provider = FakeProvider()
    outcome = await driver(provider).run(context())
    assert outcome.succeeded is True
    assert outcome.attempts == 1
    assert EVENT_REQUEST_SUCCEEDED in outcome.events
    assert EVENT_REQUEST_FAILED not in outcome.events


@pytest.mark.asyncio
async def test_subscriber_edit_reaches_the_sent_payload() -> None:
    registry = SubscriberRegistry[RequestContext]()

    async def add_marker(ctx: RequestContext) -> None:
        ctx.payload["marker"] = "set"

    registry.subscribe(EVENT_ATTEMPT_PREPARE, "marker", add_marker)
    provider = FakeProvider()

    await driver(provider, registry).run(context())

    # The attempt copies the payload when it opens.
    # An edit made during prepare must therefore be re-read rather than lost.
    assert provider.sent[0][1]["marker"] == "set"


@pytest.mark.asyncio
async def test_retry_reuses_the_post_prepare_attempt_payload() -> None:
    registry = SubscriberRegistry[RequestContext]()

    async def add_marker(ctx: RequestContext) -> None:
        ctx.payload["marker"] = "set"

    registry.subscribe(EVENT_ATTEMPT_PREPARE, "marker", add_marker)
    provider = FakeProvider(
        responses=[UpstreamError("boom", status_code=502), httpx2.Response(200)]
    )
    direct = driver(provider, registry)
    outcome = await direct.run(context())

    assert outcome.succeeded is True
    assert "reencoded" not in provider.sent[0][1]
    assert provider.sent[1][1]["marker"] == "set"


@pytest.mark.asyncio
async def test_target_format_change_is_the_only_retry_reencode_path() -> None:
    registry = SubscriberRegistry[RequestContext]()

    async def add_marker(ctx: RequestContext) -> None:
        ctx.payload["temperature"] = 0.7

    registry.subscribe(EVENT_ATTEMPT_PREPARE, "marker", add_marker)
    provider = FakeProvider(
        responses=[UpstreamError("boom", status_code=502), httpx2.Response(200)]
    )
    request = context()
    request.payload = {
        "model": "claude-model",
        "messages": [{"role": "user", "content": "hello"}],
    }
    request.target_format = WireFormat.OPENAI_RESPONSES
    request.translation_options = TranslationOptions(
        translated=True,
        target=TranslationTarget(model_id="claude-model"),
    )
    direct = driver(provider, registry)
    chain = cast(Any, SimpleNamespace(translators=default_registry()))
    direct.configure_reencode_payload(
        lambda payload: _reencode_target_payload(
            chain,
            request,
            payload=payload,
            source_format=WireFormat.OPENAI_CHAT_COMPLETIONS,
            target_format=WireFormat.OPENAI_RESPONSES,
            model_id="claude-model",
        )
    )

    outcome = await direct.run(request)

    assert outcome.succeeded is True
    assert provider.sent[1][1]["temperature"] == 0.7
    assert provider.sent[1][1]["input"][0]["content"][0]["text"] == "hello"


@pytest.mark.asyncio
async def test_handle_reencodes_when_a_retry_changes_the_target_format() -> None:
    subscribers = SubscriberRegistry[RequestContext]()

    async def change_target_on_retry(request: RequestContext) -> None:
        request.target_format = WireFormat.ANTHROPIC_MESSAGES

    subscribers.subscribe(
        EVENT_ATTEMPT_FAILED,
        "change-target-on-retry",
        change_target_on_retry,
    )

    class RoutedProvider(FakeProvider):
        def describe(self, model_id: str) -> ModelDescriptor | None:
            descriptor = super().describe(model_id)
            return replace(descriptor, provider_name=self.name) if descriptor else None

    provider = RoutedProvider(
        responses=[UpstreamError("boom", status_code=502), httpx2.Response(200)]
    )
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
        }
    )
    http_client = httpx2.AsyncClient()
    chain = build_chain(
        config,
        http_client=http_client,
        providers={"ghc": provider},
        subscribers=subscribers,
    )
    request = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="dual-model@openai-responses",
        payload={
            "model": "dual-model",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    try:
        outcome = await handle(chain, request)
    finally:
        await http_client.aclose()

    assert outcome.outcome.succeeded is True
    assert provider.sent[0][0] is ModelEndpoint.OPENAI_RESPONSES
    assert "input" in provider.sent[0][1]
    assert provider.sent[1][0] is ModelEndpoint.ANTHROPIC_MESSAGES
    assert "input" not in provider.sent[1][1]
    assert provider.sent[1][1]["messages"][0]["content"][0]["text"] == "hello"
    assert request.endpoint is ModelEndpoint.ANTHROPIC_MESSAGES
    assert request.target_format is WireFormat.ANTHROPIC_MESSAGES
    assert request.attempts[1].token_admission is not None
    assert (
        request.attempts[1].token_admission.target_format
        == WireFormat.ANTHROPIC_MESSAGES.value
    )
    assert request.attempts[0].plan is not None
    assert request.attempts[1].plan is not None
    assert request.attempts[1].plan.target_format is WireFormat.ANTHROPIC_MESSAGES
    assert request.attempts[1].plan.endpoint is ModelEndpoint.ANTHROPIC_MESSAGES
    assert request.attempts[1].plan.descriptor is request.model_descriptor



def test_real_target_format_reencode_reads_the_post_prepare_payload() -> None:
    request = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="m",
        payload={},
        target_format=WireFormat.OPENAI_RESPONSES,
        translation_options=TranslationOptions(
            translated=True,
            target=TranslationTarget(model_id="m"),
        ),
    )
    chain = cast(Any, SimpleNamespace(translators=default_registry()))
    prepared = {
        "model": "m",
        "messages": [{"role": "user", "content": "edited during prepare"}],
        "stream": False,
    }

    encoded = _reencode_target_payload(
        chain,
        request,
        payload=prepared,
        source_format=WireFormat.OPENAI_CHAT_COMPLETIONS,
        target_format=WireFormat.OPENAI_RESPONSES,
        model_id="m",
    )

    assert encoded["input"][0]["content"][0]["text"] == "edited during prepare"
    assert request.semantic_request is not None
    assert request.semantic_request.messages[0].blocks[0].text == "edited during prepare"


@pytest.mark.asyncio
async def test_provider_bound_observer_runs_after_prepare_subscribers() -> None:
    registry = SubscriberRegistry[RequestContext]()

    async def add_effort(ctx: RequestContext) -> None:
        ctx.payload["output_config"] = {"effort": "xhigh"}

    registry.subscribe(EVENT_ATTEMPT_PREPARE, "effort", add_effort)
    observed: list[dict[str, Any]] = []
    request = context()

    def observe(current: RequestContext) -> None:
        observed.append(dict(current.payload))

    request.extras[PROVIDER_BOUND_OBSERVER] = observe

    await driver(FakeProvider(), registry).run(request)

    assert observed == [
        {
            "model": "claude-model",
            "messages": [],
            "output_config": {"effort": "xhigh"},
        }
    ]


@pytest.mark.asyncio
async def test_retryable_upstream_error_is_attempted_again() -> None:
    provider = FakeProvider(responses=[UpstreamError("boom", status_code=502), httpx2.Response(200)])
    outcome = await driver(provider).run(context())
    assert outcome.succeeded is True
    assert outcome.attempts == 2
    assert EVENT_ATTEMPT_FAILED in outcome.events


@pytest.mark.asyncio
async def test_a_failed_attempt_holds_the_next_one_back() -> None:
    # The retry loop has no interval of its own; the spacing comes from the shared rate limiter,
    # which the failure feeds through `note_failure`. A provider raised `UpstreamError` without a
    # status, so the reactive half never engages and the wait is the failure backoff alone.
    class FakeClock:
        def __init__(self) -> None:
            self.now = 0.0
            self.slept: list[float] = []

        def __call__(self) -> float:
            return self.now

        async def sleep(self, seconds: float) -> None:
            self.slept.append(seconds)
            self.now += seconds

    clock = FakeClock()
    from app.config.schema import ReactiveRateLimiterConfig

    rate_limiter = RateLimiter(ReactiveRateLimiterConfig(), clock=clock, sleep=clock.sleep)
    provider = FakeProvider(responses=[UpstreamError("boom"), httpx2.Response(200)])
    direct = AnthropicMessagesDriver(
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=RetryBudget(max_total=3),
        rate_limiter=rate_limiter,
        clock=clock,
    )
    outcome = await direct.run(context())
    assert outcome.succeeded is True
    assert clock.slept == pytest.approx([0.5])
    assert rate_limiter.mode is RateLimitMode.NORMAL


@pytest.mark.asyncio
async def test_abort_stops_without_another_attempt() -> None:
    provider = FakeProvider(responses=[PipelineAbort("no"), httpx2.Response(200)])
    outcome = await driver(provider).run(context())
    assert outcome.succeeded is False
    assert outcome.attempts == 1
    assert isinstance(outcome.error, PipelineAbort)
    assert EVENT_REQUEST_FAILED in outcome.events


@pytest.mark.asyncio
async def test_unknown_exception_aborts_rather_than_retrying() -> None:
    # A subscriber bug must not spend the retry budget on a defect.
    provider = FakeProvider(responses=[KeyError("bug"), httpx2.Response(200)])
    outcome = await driver(provider).run(context())
    assert outcome.succeeded is False
    assert outcome.attempts == 1
    assert isinstance(outcome.error, KeyError)


@pytest.mark.asyncio
async def test_budget_bounds_the_retries() -> None:
    failures: list[Any] = [UpstreamError("boom") for _ in range(10)]
    provider = FakeProvider(responses=failures)
    outcome = await driver(provider, max_total=2).run(context())
    assert outcome.succeeded is False
    # One initial attempt plus two funded retries.
    assert outcome.attempts == 3
    assert isinstance(outcome.error, PipelineAbort)
    assert "budget exhausted" in str(outcome.error)


@pytest.mark.asyncio
async def test_subscriber_raising_retry_reattempts() -> None:
    registry = SubscriberRegistry[RequestContext]()
    calls: list[int] = []

    async def fail_once(ctx: RequestContext) -> None:
        calls.append(ctx.attempt_count)
        if len(calls) == 1:
            raise PipelineRetry("try again")

    registry.subscribe(EVENT_ATTEMPT_PREPARE, "flaky", fail_once)
    provider = FakeProvider()

    outcome = await driver(provider, registry).run(context())

    assert outcome.succeeded is True
    assert outcome.attempts == 2
    # The first attempt never reached the provider.
    assert len(provider.sent) == 1


@pytest.mark.asyncio
async def test_subscribers_run_in_the_frozen_order() -> None:
    registry = SubscriberRegistry[RequestContext]()
    order: list[str] = []

    async def first(_: RequestContext) -> None:
        order.append("first")

    async def second(_: RequestContext) -> None:
        order.append("second")

    registry.subscribe(EVENT_ATTEMPT_PREPARE, "zebra", second, after=["apple"])
    registry.subscribe(EVENT_ATTEMPT_PREPARE, "apple", first)

    await driver(FakeProvider(), registry).run(context())

    assert order == ["first", "second"]


@pytest.mark.asyncio
async def test_late_subscriber_abort_discards_the_response() -> None:
    registry = SubscriberRegistry[RequestContext]()

    async def reject(_: RequestContext) -> None:
        raise PipelineAbort("not acceptable")

    registry.subscribe(EVENT_REQUEST_SUCCEEDED, "reject", reject)

    outcome = await driver(FakeProvider(), registry).run(context())

    assert outcome.succeeded is False
    assert outcome.response is None
    assert isinstance(outcome.error, PipelineAbort)


@pytest.mark.asyncio
async def test_named_strategies_bound_each_reason_separately() -> None:
    # A 401 draws on githubTokenExpired, which the spec caps at 0, so it must not be retried even though the shared total has room.
    from app.config.schema import UpstreamRequestRetryConfig
    from app.pipeline.direct_driver import LedgerBudget
    from app.pipeline.retry import RetryLedger

    provider = FakeProvider(
        responses=[UpstreamError("expired", status_code=401), httpx2.Response(200)]
    )
    ledger = RetryLedger(UpstreamRequestRetryConfig())
    frozen = SubscriberRegistry[RequestContext]().freeze()
    driver_under_test = AnthropicMessagesDriver(
        provider, frozen, budget=LedgerBudget(ledger)
    )

    outcome = await driver_under_test.run(context())

    assert outcome.succeeded is False
    assert outcome.attempts == 1
    assert "githubTokenExpired" in str(outcome.error)


@pytest.mark.asyncio
async def test_a_draining_process_does_not_open_another_upstream_attempt() -> None:
    """A retry opens a new upstream attempt, and a process that has stopped accepting has promised not to take on new work.

    The failure is one the budget would otherwise fund — the sibling test above proves a 503 buys a second attempt — so the refusal here is the drain's doing and nothing else's.

    Budget is left untouched as well as unspent: the same ledger is read by the hand-over path this ending falls through to, and charging it for an attempt that was never made would narrow what that path is allowed to do.
    """
    from app.config.schema import UpstreamRequestRetryConfig
    from app.pipeline.direct_driver import LedgerBudget
    from app.pipeline.retry import RetryLedger

    ledger = RetryLedger(UpstreamRequestRetryConfig())
    provider = FakeProvider(
        responses=[UpstreamError("gateway", status_code=503), httpx2.Response(200)]
    )
    driver_under_test = AnthropicMessagesDriver(
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=LedgerBudget(ledger, draining=lambda: True),
    )

    outcome = await driver_under_test.run(context())

    assert outcome.succeeded is False
    assert outcome.attempts == 1
    assert "shutting down" in str(outcome.error)
    assert ledger.total_spent == 0


@pytest.mark.asyncio
async def test_the_drain_is_read_at_each_refusal_rather_than_at_construction() -> None:
    """A drain that begins while a request is already in flight has to stop that request's *next* attempt.

    Sampled once when the budget was built, the answer would say "running" for the whole request — which is every request that matters here, since a drain waits for exactly the ones already running.
    """
    from app.config.schema import UpstreamRequestRetryConfig
    from app.pipeline.direct_driver import LedgerBudget
    from app.pipeline.retry import RetryLedger

    draining = False
    provider = FakeProvider(
        responses=[
            UpstreamError("gateway", status_code=503),
            UpstreamError("gateway", status_code=503),
            httpx2.Response(200),
        ]
    )
    driver_under_test = AnthropicMessagesDriver(
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=LedgerBudget(RetryLedger(UpstreamRequestRetryConfig()), draining=lambda: draining),
    )

    # The first failure is funded, and the drain begins between it and the second.
    original_send = provider.send

    async def send_then_drain(*args: Any, **kwargs: Any) -> Any:
        nonlocal draining
        try:
            return await original_send(*args, **kwargs)
        finally:
            draining = True

    provider.send = send_then_drain  # pyright: ignore[reportAttributeAccessIssue]

    outcome = await driver_under_test.run(context())

    assert outcome.succeeded is False
    # One attempt made, and the retry it had already earned refused because the world changed underneath it.
    assert outcome.attempts == 1
    assert "shutting down" in str(outcome.error)


@pytest.mark.asyncio
async def test_named_strategies_allow_a_funded_reason() -> None:
    from app.config.schema import UpstreamRequestRetryConfig
    from app.pipeline.direct_driver import LedgerBudget
    from app.pipeline.retry import RetryLedger

    provider = FakeProvider(
        responses=[UpstreamError("gateway", status_code=503), httpx2.Response(200)]
    )
    driver_under_test = AnthropicMessagesDriver(
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=LedgerBudget(RetryLedger(UpstreamRequestRetryConfig())),
    )

    outcome = await driver_under_test.run(context())

    assert outcome.succeeded is True
    assert outcome.attempts == 2


@pytest.mark.asyncio
async def test_the_driver_hands_the_clients_headers_to_the_provider() -> None:
    """Every layer accepted `extra_headers` and nobody ever passed one.

    The signature was there from the start, so the gap was invisible to type checking and to any test that only looked at the payload: production dropped `anthropic-beta`, and upstream then refused body fields that beta enables. Asserting the value rather than the parameter.
    """
    provider = FakeProvider()
    ctx = context()
    ctx.client_headers = {"anthropic-beta": "context-management-2025-06-27"}

    outcome = await driver(provider).run(ctx)

    assert outcome.succeeded is True
    assert provider.sent_headers == [{"anthropic-beta": "context-management-2025-06-27"}]


@pytest.mark.asyncio
async def test_the_driver_hands_the_interaction_id_to_the_provider() -> None:
    provider = FakeProvider()
    ctx = context()
    ctx.interaction_id = "session-a"

    outcome = await driver(provider).run(ctx)

    assert outcome.succeeded is True
    assert provider.sent_interaction_ids == ["session-a"]


@pytest.mark.asyncio
async def test_retry_reuses_a_frozen_provider_interaction_id() -> None:
    provider = FakeProvider(
        responses=[UpstreamError("boom", status_code=502), httpx2.Response(200)]
    )
    registry = SubscriberRegistry[RequestContext]()

    async def mutate_interaction(ctx: RequestContext) -> None:
        ctx.interaction_id = "second"

    registry.subscribe(EVENT_ATTEMPT_FAILED, "mutate-interaction", mutate_interaction)
    ctx = context()
    ctx.interaction_id = "first"

    outcome = await driver(provider, registry).run(ctx)

    assert outcome.succeeded is True
    assert provider.sent_interaction_ids == ["first", "first"]


@pytest.mark.asyncio
async def test_no_client_headers_sends_none_rather_than_an_empty_mapping() -> None:
    """`None` is what the provider signature means by "nothing to add"."""
    provider = FakeProvider()
    ctx = context()

    await driver(provider).run(ctx)

    assert provider.sent_headers == [None]
    assert provider.sent_interaction_ids == [ctx.id]


@pytest.mark.asyncio
async def test_a_cancellation_passes_through_rather_than_being_answered() -> None:
    """A cancellation is not a failure this loop gets an opinion about, and catching it broke the layer above.

    `handle_bounded` expresses the client deadline as `asyncio.timeout`, which fires by cancelling and then reads the cancellation back out to turn it into a `TimeoutError`. While this loop caught it, that conversion never happened: the line meant to answer it raised nothing, and the client was told 502 `CancelledError` with an empty message instead of 504.

    Asserted through `asyncio.timeout` rather than on `CancelledError` directly, because the property that matters is not that the exception escapes — it is that the enclosing scope still recognises its own timeout.
    """
    registry = SubscriberRegistry[RequestContext]()

    async def never_answers(ctx: RequestContext) -> None:
        del ctx
        await asyncio.sleep(60)

    registry.subscribe(EVENT_ATTEMPT_PREPARE, "slow", never_answers)

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await driver(FakeProvider(), registry).run(context())


@pytest.mark.asyncio
async def test_nested_cleanup_wrappers_cannot_turn_cancellation_into_retry_or_a_cycle() -> None:
    class NestedCleanupProvider(FakeProvider):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()

        async def send(
            self,
            endpoint: ModelEndpoint,
            payload: Any,
            *,
            descriptor: ModelDescriptor,
            stream: bool = False,
            extra_headers: Any = None,
            interaction_id: str | None = None,
        ) -> httpx2.Response:
            self.sent.append((endpoint, dict(payload)))
            self.sent_headers.append(extra_headers)
            self.sent_interaction_ids.append(interaction_id)
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError as cancellation:
                inner = RuntimeError("inner cleanup failure")
                inner.__cause__ = cancellation
                outer = PipelineRetry("outer retryable cleanup failure")
                raise outer from inner
            raise AssertionError("unreachable")

    def assert_acyclic(root: BaseException) -> None:
        visited: set[int] = set()
        active: set[int] = set()

        def visit(error: BaseException) -> None:
            error_id = id(error)
            assert error_id not in active, f"exception graph cycles through {error!r}"
            if error_id in visited:
                return
            visited.add(error_id)
            active.add(error_id)
            linked = [
                child
                for child in (error.__cause__, error.__context__)
                if child is not None
            ]
            if isinstance(error, BaseExceptionGroup):
                group = cast(BaseExceptionGroup[BaseException], error)
                linked.extend(group.exceptions)
            for child in linked:
                visit(child)
            active.remove(error_id)

        visit(root)

    provider = NestedCleanupProvider()
    running = asyncio.create_task(driver(provider).run(context()))
    await asyncio.wait_for(provider.started.wait(), timeout=1)
    running.cancel()

    with pytest.raises(asyncio.CancelledError) as raised:
        await running

    cancellation = raised.value
    outer = cancellation.__cause__
    assert isinstance(outer, PipelineRetry)
    assert str(outer) == "outer retryable cleanup failure"
    inner = outer.__cause__
    assert isinstance(inner, RuntimeError)
    assert str(inner) == "inner cleanup failure"
    assert inner.__cause__ is None
    assert len(provider.sent) == 1
    assert_acyclic(cancellation)


@pytest.mark.asyncio
async def test_cancellation_closes_a_response_the_driver_has_not_handed_off() -> None:
    """The driver owns the response until its success subscribers finish.

    A downstream disconnect can cancel this exact interval: provider send has returned, but the route has not received the response yet. Clearing `outcome.response` without closing it loses the only owner and leaves its connection checked out.
    """
    owned = CheckpointCloseStream()
    response = httpx2.Response(200, stream=owned)
    entered_subscriber = asyncio.Event()
    registry = SubscriberRegistry[RequestContext]()

    async def hold_response(ctx: RequestContext) -> None:
        del ctx
        entered_subscriber.set()
        await asyncio.Event().wait()

    registry.subscribe(EVENT_REQUEST_SUCCEEDED, "hold-response", hold_response)

    async def run() -> None:
        with pytest.raises(asyncio.CancelledError):
            await driver(FakeProvider(responses=[response]), registry).run(context())

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(run)
        await asyncio.wait_for(entered_subscriber.wait(), timeout=1)
        assert response.is_closed is False
        # This is how the pre-response listener stops dispatch: AnyIO's cancelled scope, not a one-shot `Task.cancel()` from outside it.
        task_group.cancel_scope.cancel()

    assert response.is_closed is True
    assert owned.close_started.is_set()
    assert owned.close_finished.is_set()


@pytest.mark.asyncio
async def test_cancellation_keeps_a_response_close_failure_as_its_cause() -> None:
    owned = FailingCloseStream()
    response = httpx2.Response(200, stream=owned)
    entered_subscriber = asyncio.Event()
    exits: list[BaseException] = []
    registry = SubscriberRegistry[RequestContext]()

    async def hold_response(ctx: RequestContext) -> None:
        del ctx
        entered_subscriber.set()
        await asyncio.Event().wait()

    registry.subscribe(EVENT_REQUEST_SUCCEEDED, "hold-response", hold_response)

    async def run() -> None:
        try:
            await driver(FakeProvider(responses=[response]), registry).run(context())
        except BaseException as error:
            exits.append(error)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(run)
        await asyncio.wait_for(entered_subscriber.wait(), timeout=1)
        task_group.cancel_scope.cancel()

    assert len(exits) == 1
    cancellation = exits[0]
    assert isinstance(cancellation, asyncio.CancelledError)
    assert isinstance(cancellation.__cause__, RuntimeError)
    assert str(cancellation.__cause__) == "response close failed"
    assert owned.close_started.is_set()


@pytest.mark.asyncio
async def test_subscriber_retry_closes_the_response_it_discarded() -> None:
    owned = CheckpointCloseStream()
    discarded = httpx2.Response(200, stream=owned)
    registry = SubscriberRegistry[RequestContext]()
    calls = 0

    async def retry_once(ctx: RequestContext) -> None:
        nonlocal calls
        del ctx
        calls += 1
        if calls == 1:
            raise PipelineRetry("retry after inspecting the response")

    registry.subscribe(EVENT_REQUEST_SUCCEEDED, "retry-once", retry_once)
    outcome = await driver(
        FakeProvider(responses=[discarded, httpx2.Response(200)]),
        registry,
    ).run(context())

    assert outcome.succeeded is True
    assert outcome.attempts == 2
    assert discarded.is_closed is True
    assert owned.close_started.is_set()
    assert owned.close_finished.is_set()


@pytest.mark.asyncio
async def test_close_failure_does_not_erase_the_subscriber_retry() -> None:
    owned = FailingCloseStream()
    discarded = httpx2.Response(200, stream=owned)
    provider = FakeProvider(responses=[discarded])
    registry = SubscriberRegistry[RequestContext]()

    async def retry(ctx: RequestContext) -> None:
        del ctx
        raise PipelineRetry("subscriber retry")

    registry.subscribe(EVENT_REQUEST_SUCCEEDED, "retry", retry)

    with pytest.raises(PipelineRetry, match="subscriber retry") as raised:
        await driver(provider, registry).run(context())

    assert isinstance(raised.value.__cause__, RuntimeError)
    assert str(raised.value.__cause__) == "response close failed"
    assert len(provider.sent) == 1
    assert owned.close_started.is_set()
