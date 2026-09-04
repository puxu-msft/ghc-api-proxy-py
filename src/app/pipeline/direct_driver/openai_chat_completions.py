"""Direct driver for OpenAI Chat Completions.

Binds the endpoint; the loop is shared, so behaviour cannot drift between the four.
"""

from collections.abc import Callable, Mapping
from typing import Any

from app.model_provider import ModelDescriptor, ModelEndpoint, ModelProvider
from app.pipeline.direct_driver.base import AdmissionPolicy, Budget, DirectDriver
from app.pipeline.events import FrozenSubscribers
from app.pipeline.rate_limiting import RateLimiter
from app.pipeline.request import RequestContext
from app.tokenization.admission import TokenAdmissionObservation

ENDPOINT = ModelEndpoint.OPENAI_CHAT_COMPLETIONS


class OpenAIChatCompletionsDriver(DirectDriver):
    def __init__(
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
    ) -> None:
        super().__init__(
            ENDPOINT,
            provider,
            subscribers,
            budget=budget,
            descriptor=descriptor,
            admission=admission,
            prepared_payload=prepared_payload,
            reused_admission=reused_admission,
            attempt_deadline=attempt_deadline,
            response_header_timeout=response_header_timeout,
            rate_limiter=rate_limiter,
            clock=clock,
        )
