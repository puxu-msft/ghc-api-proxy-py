"""Direct driver for OpenAI Chat Completions.

Binds the endpoint; the loop is shared, so behaviour cannot drift between the four.
"""

from app.model_provider import ModelEndpoint, ModelProvider
from app.pipeline.direct_driver.base import Budget, DirectDriver
from app.pipeline.events import FrozenSubscribers
from app.pipeline.request import RequestContext

ENDPOINT = ModelEndpoint.OPENAI_CHAT_COMPLETIONS


class OpenAIChatCompletionsDriver(DirectDriver):
    def __init__(
        self,
        provider: ModelProvider,
        subscribers: FrozenSubscribers[RequestContext],
        *,
        budget: Budget,
        attempt_deadline: int = 0,
    ) -> None:
        super().__init__(
            ENDPOINT,
            provider,
            subscribers,
            budget=budget,
            attempt_deadline=attempt_deadline,
        )
