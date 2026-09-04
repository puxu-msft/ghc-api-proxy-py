"""Direct drivers: the paths where no format translation is needed.

One module per upstream endpoint, as the driver table in `docs/.human-controlled/ghc-api.md` names them.
`ws:/responses` has no driver, matching that table's unsupported row.
"""

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from app.model_provider import ModelDescriptor, ModelEndpoint, ModelProvider
from app.pipeline.direct_driver.anthropic_messages import AnthropicMessagesDriver
from app.pipeline.direct_driver.base import (
    EVENT_ATTEMPT_FAILED,
    EVENT_ATTEMPT_PREPARE,
    EVENT_ATTEMPT_SUCCEEDED,
    EVENT_REQUEST_FAILED,
    EVENT_REQUEST_SUCCEEDED,
    EVENTS,
    AdmissionPolicy,
    Budget,
    DirectDriver,
    DriverOutcome,
    LedgerBudget,
    RetryBudget,
)
from app.pipeline.direct_driver.openai_chat_completions import OpenAIChatCompletionsDriver
from app.pipeline.direct_driver.openai_embeddings import OpenAIEmbeddingsDriver
from app.pipeline.direct_driver.openai_responses import OpenAIResponsesDriver
from app.pipeline.events import FrozenSubscribers
from app.pipeline.rate_limiting import RateLimiter
from app.pipeline.request import RequestContext
from app.tokenization.admission import TokenAdmissionObservation


class DriverFactory(Protocol):
    """How a named driver is constructed; the endpoint is already bound."""

    def __call__(
        self,
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
    ) -> DirectDriver: ...


DRIVERS: dict[ModelEndpoint, DriverFactory] = {
    ModelEndpoint.ANTHROPIC_MESSAGES: AnthropicMessagesDriver,
    ModelEndpoint.OPENAI_CHAT_COMPLETIONS: OpenAIChatCompletionsDriver,
    ModelEndpoint.OPENAI_RESPONSES: OpenAIResponsesDriver,
    ModelEndpoint.OPENAI_EMBEDDINGS: OpenAIEmbeddingsDriver,
}

__all__ = [
    "DRIVERS",
    "EVENTS",
    "EVENT_ATTEMPT_FAILED",
    "EVENT_ATTEMPT_PREPARE",
    "EVENT_ATTEMPT_SUCCEEDED",
    "EVENT_REQUEST_FAILED",
    "EVENT_REQUEST_SUCCEEDED",
    "AdmissionPolicy",
    "AnthropicMessagesDriver",
    "Budget",
    "DirectDriver",
    "DriverFactory",
    "DriverOutcome",
    "LedgerBudget",
    "OpenAIChatCompletionsDriver",
    "OpenAIEmbeddingsDriver",
    "OpenAIResponsesDriver",
    "RetryBudget",
]
