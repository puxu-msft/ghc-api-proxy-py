"""Direct driver for Anthropic Messages. The spec routes count_tokens through this driver too.

Binds the endpoint; the loop is shared, so behaviour cannot drift between the four.
"""

from app.model_provider import ModelEndpoint, ModelProvider
from app.pipeline.direct_driver.base import DirectDriver, RetryBudget
from app.pipeline.events import FrozenSubscribers
from app.pipeline.request import RequestContext

ENDPOINT = ModelEndpoint.ANTHROPIC_MESSAGES


class AnthropicMessagesDriver(DirectDriver):
    def __init__(
        self,
        provider: ModelProvider,
        subscribers: FrozenSubscribers[RequestContext],
        *,
        budget: RetryBudget,
    ) -> None:
        super().__init__(ENDPOINT, provider, subscribers, budget=budget)
