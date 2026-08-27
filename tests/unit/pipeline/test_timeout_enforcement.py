"""Timeouts must actually fire.

The defect being fixed is a configured timeout that never takes effect, which looks identical to a generous one until an upstream hangs.
"""

import asyncio
from typing import Any

import httpx2
import pytest

from app.model_provider import ModelDescriptor, ModelEndpoint
from app.pipeline.direct_driver import AnthropicMessagesDriver, RetryBudget
from app.pipeline.events import SubscriberRegistry
from app.pipeline.request import RequestContext, WireFormat

DESCRIPTOR = ModelDescriptor(
    id="claude-model",
    endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
)


class SlowProvider:
    def __init__(self, delay: float) -> None:
        self.name = "ghc"
        self._delay = delay
        self.calls = 0

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset({"claude-model"})

    # Reporting-only members of the provider protocol, here so this stub satisfies it. Nothing on this test's path reads them; `/api/status` does.
    @property
    def disabled_ids(self) -> frozenset[str]:
        return frozenset()

    @property
    def base_url(self) -> str:
        return "https://stub.invalid"

    @property
    def catalog_refreshed_at(self) -> str:
        return "2026-08-27T00:00:00+00:00"

    def describe(self, model_id: str) -> ModelDescriptor | None:
        return DESCRIPTOR if model_id == "claude-model" else None

    async def refresh_catalog(self) -> bool:
        return False

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Any,
        *,
        model_id: str,
        stream: bool = False,
        extra_headers: Any = None,
    ) -> httpx2.Response:
        self.calls += 1
        await asyncio.sleep(self._delay)
        return httpx2.Response(200, json={})

    async def count_tokens(self, payload: Any, *, model_id: str) -> httpx2.Response:
        # Present so the fake really satisfies the protocol. Nothing here counts tokens, and a silent stub would let a test think it had.
        raise NotImplementedError("this fake does not count tokens")


def context() -> RequestContext:
    ctx = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-model",
        payload={"model": "claude-model"},
    )
    ctx.resolved_model = "claude-model"
    return ctx


def driver(provider: SlowProvider, *, deadline: int) -> AnthropicMessagesDriver:
    return AnthropicMessagesDriver(
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=RetryBudget(max_total=0),
        attempt_deadline=deadline,
    )


@pytest.mark.asyncio
async def test_attempt_deadline_stops_a_hanging_upstream() -> None:
    provider = SlowProvider(delay=5.0)
    outcome = await driver(provider, deadline=1).run(context())
    assert outcome.succeeded is False
    # With no retry budget the timeout is reported as the reason the request ended.
    assert "attempt exceeded 1s" in str(outcome.error)


@pytest.mark.asyncio
async def test_a_timeout_is_retryable_when_the_budget_allows() -> None:
    # It surfaces as UpstreamTimeout, which the named strategies fund under network.
    provider = SlowProvider(delay=5.0)
    driver_under_test = AnthropicMessagesDriver(
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=RetryBudget(max_total=1),
        attempt_deadline=1,
    )
    outcome = await driver_under_test.run(context())
    assert outcome.succeeded is False
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_a_fast_upstream_is_untouched_by_the_deadline() -> None:
    # The other direction: a configured deadline must not kill a normal response.
    provider = SlowProvider(delay=0.0)
    outcome = await driver(provider, deadline=5).run(context())
    assert outcome.succeeded is True


@pytest.mark.asyncio
async def test_zero_deadline_disables_the_guard() -> None:
    provider = SlowProvider(delay=0.05)
    outcome = await driver(provider, deadline=0).run(context())
    assert outcome.succeeded is True


@pytest.mark.asyncio
async def test_the_header_guard_stops_an_upstream_that_never_answers() -> None:
    # `response_header` had a value, a name and documentation, and reached nothing: it was read out of the config file and then never passed to anything. A configured guard that does not exist looks exactly like a generous one.
    provider = SlowProvider(delay=5.0)
    driver_under_test = AnthropicMessagesDriver(
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=RetryBudget(max_total=0),
        response_header_timeout=1,
    )
    outcome = await driver_under_test.run(context())
    assert outcome.succeeded is False
    assert "no response headers within 1s" in str(outcome.error)


@pytest.mark.asyncio
async def test_the_two_guards_each_report_themselves() -> None:
    # They are set by different people for different reasons, and the completion line names the one an operator should reach for. Whichever runs out first has to say so under its own name.
    provider = SlowProvider(delay=5.0)
    header_first = AnthropicMessagesDriver(
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=RetryBudget(max_total=0),
        attempt_deadline=10,
        response_header_timeout=1,
    )
    assert "no response headers within 1s" in str((await header_first.run(context())).error)

    deadline_first = AnthropicMessagesDriver(
        SlowProvider(delay=5.0),
        SubscriberRegistry[RequestContext]().freeze(),
        budget=RetryBudget(max_total=0),
        attempt_deadline=1,
        response_header_timeout=10,
    )
    assert "attempt exceeded 1s" in str((await deadline_first.run(context())).error)


@pytest.mark.asyncio
async def test_zero_header_timeout_disables_the_guard() -> None:
    provider = SlowProvider(delay=0.05)
    driver_under_test = AnthropicMessagesDriver(
        provider,
        SubscriberRegistry[RequestContext]().freeze(),
        budget=RetryBudget(max_total=0),
        response_header_timeout=0,
    )
    assert (await driver_under_test.run(context())).succeeded is True


@pytest.mark.asyncio
async def test_the_attempt_carries_the_one_deadline_both_halves_read() -> None:
    # The body is guarded after the driver has returned, so the instant has to survive the driver rather than be worked out again downstream — recomputing it there would hand the attempt a second full lifetime starting from whenever its headers happened to arrive.
    provider = SlowProvider(delay=0.0)
    ctx = context()
    loop = asyncio.get_running_loop()
    before = loop.time()
    await driver(provider, deadline=30).run(ctx)

    attempt = ctx.current_attempt
    assert attempt is not None
    assert attempt.deadline_at is not None
    assert before + 30 <= attempt.deadline_at <= loop.time() + 30

    unbounded = context()
    await driver(SlowProvider(delay=0.0), deadline=0).run(unbounded)
    assert unbounded.current_attempt is not None
    assert unbounded.current_attempt.deadline_at is None
