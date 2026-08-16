"""Direct driver for OpenAI Responses.

Binds the endpoint; the loop is shared, so behaviour cannot drift between the four.
"""

from app.model_provider import ModelEndpoint, ModelProvider
from app.pipeline.direct_driver.base import DirectDriver, RetryBudget
from app.pipeline.events import FrozenSubscribers
from app.pipeline.request import RequestContext

ENDPOINT = ModelEndpoint.OPENAI_RESPONSES


class OpenAIResponsesDriver(DirectDriver):
    def __init__(
        self,
        provider: ModelProvider,
        subscribers: FrozenSubscribers[RequestContext],
        *,
        budget: RetryBudget,
    ) -> None:
        super().__init__(ENDPOINT, provider, subscribers, budget=budget)
