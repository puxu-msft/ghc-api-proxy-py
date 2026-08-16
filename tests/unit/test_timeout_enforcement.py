"""Timeouts must actually fire.

The defect being fixed is a configured timeout that never takes effect, which looks identical to
a generous one until an upstream hangs.
"""

import asyncio
from typing import Any

import httpx
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
    ) -> httpx.Response:
        self.calls += 1
        await asyncio.sleep(self._delay)
        return httpx.Response(200, json={})


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
