"""Direct drivers: the paths where no format translation is needed.

One module per upstream endpoint, as MAIN.md's driver table names them.
`ws:/responses` has no driver, matching the spec's unsupported row.
"""

from app.model_provider import ModelEndpoint
from app.pipeline.direct_driver.anthropic_messages import AnthropicMessagesDriver
from app.pipeline.direct_driver.base import (
    EVENT_ATTEMPT_FAILED,
    EVENT_ATTEMPT_PREPARE,
    EVENT_ATTEMPT_SUCCEEDED,
    EVENT_REQUEST_FAILED,
    EVENT_REQUEST_SUCCEEDED,
    EVENTS,
    DirectDriver,
    DriverOutcome,
    RetryBudget,
)
from app.pipeline.direct_driver.openai_chat_completions import OpenAIChatCompletionsDriver
from app.pipeline.direct_driver.openai_embeddings import OpenAIEmbeddingsDriver
from app.pipeline.direct_driver.openai_responses import OpenAIResponsesDriver

DRIVERS: dict[ModelEndpoint, type[DirectDriver]] = {
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
    "AnthropicMessagesDriver",
    "DirectDriver",
    "DriverOutcome",
    "OpenAIChatCompletionsDriver",
    "OpenAIEmbeddingsDriver",
    "OpenAIResponsesDriver",
    "RetryBudget",
]
