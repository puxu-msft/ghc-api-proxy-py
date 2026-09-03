"""HTTP 499 must reach the existing upstream retry policy."""

from collections.abc import Mapping
from typing import Any, cast

import httpx2
import openai
import pytest

from app.config.schema import UpstreamRequestRetryConfig
from app.model_provider import ModelEndpoint, ModelProvider
from app.model_provider.ghc_client.errors import normalize_upstream_error
from app.pipeline.direct_driver import DirectDriver, LedgerBudget
from app.pipeline.events import SubscriberRegistry
from app.pipeline.exceptions import (
    Disposition,
    PipelineAbort,
    PipelineError,
    UpstreamError,
    UpstreamRejected,
    classify,
)
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.retry import RetryLedger, RetryReason, reason_for
from app.server.http_errors import error_status


class SequenceProvider:
    def __init__(self, outcomes: list[BaseException | httpx2.Response]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Mapping[str, Any],
        *,
        model_id: str,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        del endpoint, payload, model_id, stream, extra_headers
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def status_error(status: int) -> Exception:
    request = httpx2.Request("POST", "https://upstream.example/responses")
    response = httpx2.Response(status, content=b"", request=request)
    return openai.APIStatusError("upstream said no", response=response, body=None)


def normalized_status(status: int) -> PipelineError:
    normalized = normalize_upstream_error(status_error(status))
    assert normalized is not None
    return normalized


def context() -> RequestContext:
    request = RequestContext(
        inbound_format=WireFormat.OPENAI_RESPONSES,
        requested_model="gpt-model",
        payload={"model": "gpt-model", "input": []},
    )
    request.resolved_model = "gpt-model"
    request.stream = True
    return request


def direct_driver(provider: SequenceProvider, *, server_error_retries: int) -> DirectDriver:
    config = UpstreamRequestRetryConfig.model_validate(
        {"strategies": {"serverError": {"max_retries": server_error_retries}}}
    )
    return DirectDriver(
        ModelEndpoint.OPENAI_RESPONSES,
        cast(ModelProvider, provider),
        SubscriberRegistry[RequestContext]().freeze(),
        budget=LedgerBudget(RetryLedger(config)),
    )


def test_http_499_is_retryable_and_draws_on_the_server_error_budget() -> None:
    """This status is upstream's answer, not evidence that our downstream client left.

    Measured 2026-09-03: Copilot returned an empty 499 after 123 seconds while this proxy still held the client request open. Treating every otherwise-unlisted 4xx as a deterministic request refusal made that attempt terminal instead of consulting the configured retry budget.
    """
    normalized = normalized_status(499)

    assert isinstance(normalized, UpstreamError)
    assert normalized.status_code == 499
    assert normalized.body_observed is True
    assert classify(normalized) is Disposition.RETRY
    assert reason_for(normalized) is RetryReason.SERVER_ERROR


@pytest.mark.asyncio
async def test_http_499_is_replayed_before_any_response_reaches_the_client() -> None:
    first = normalized_status(499)
    assert isinstance(first, UpstreamError)
    provider = SequenceProvider([first, httpx2.Response(200)])

    outcome = await direct_driver(provider, server_error_retries=1).run(context())

    assert outcome.succeeded is True
    assert outcome.attempts == 2
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_http_499_stops_when_the_server_error_budget_is_exhausted() -> None:
    first = normalized_status(499)
    last = normalized_status(499)
    assert isinstance(first, UpstreamError)
    assert isinstance(last, UpstreamError)
    provider = SequenceProvider([first, last, httpx2.Response(200)])

    outcome = await direct_driver(provider, server_error_retries=1).run(context())

    assert outcome.succeeded is False
    assert outcome.attempts == 2
    assert provider.calls == 2
    assert isinstance(outcome.error, PipelineAbort)
    assert outcome.error.cause is last
    assert error_status(outcome.error) == 499


def test_an_unlisted_neighboring_4xx_remains_a_deterministic_refusal() -> None:
    normalized = normalized_status(498)

    assert isinstance(normalized, UpstreamRejected)
    assert classify(normalized) is Disposition.ABORT
    assert reason_for(normalized) is None
