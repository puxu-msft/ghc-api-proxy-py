"""Direct driver for Anthropic Messages. The spec routes count_tokens through this driver too.

Binds the endpoint; the loop is shared, so behaviour cannot drift between the four.
"""

from app.model_provider import ModelEndpoint, ModelProvider
from app.pipeline.direct_driver.base import Budget, DirectDriver
from app.pipeline.events import FrozenSubscribers
from app.pipeline.rate_limiting import RateLimiter
from app.pipeline.request import RequestContext

ENDPOINT = ModelEndpoint.ANTHROPIC_MESSAGES


class AnthropicMessagesDriver(DirectDriver):
    def __init__(
        self,
        provider: ModelProvider,
        subscribers: FrozenSubscribers[RequestContext],
        *,
        budget: Budget,
        attempt_deadline: int = 0,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(
            ENDPOINT,
            provider,
            subscribers,
            budget=budget,
            attempt_deadline=attempt_deadline,
            rate_limiter=rate_limiter,
        )
