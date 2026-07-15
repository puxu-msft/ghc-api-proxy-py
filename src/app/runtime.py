from dataclasses import dataclass
from typing import TYPE_CHECKING

from anyio.abc import TaskGroup

from app.config.settings import AppSettings

if TYPE_CHECKING:
    from app.anthropic.client import AnthropicClient
    from app.anthropic.token_counting import TokenCounter
    from app.openai.client import OpenAIClient
    from app.openai.responses_ws import ResponsesWebSocketClient
    from app.upstream.bootstrap import UpstreamServices


@dataclass(slots=True)
class RuntimeState:
    settings: AppSettings
    background_task_group: TaskGroup | None = None
    otel_enabled: bool = False
    github_token_ready: bool = False
    copilot_token_ready: bool = False
    models_ready: bool = False
    upstream_services: UpstreamServices | None = None
    anthropic_client: AnthropicClient | None = None
    token_counter: TokenCounter | None = None
    openai_client: OpenAIClient | None = None
    responses_ws_client: ResponsesWebSocketClient | None = None

    def readiness_checks(self) -> dict[str, bool]:
        return {
            "github_token": self.github_token_ready,
            "copilot_token": self.copilot_token_ready,
            "models": self.models_ready,
        }

    @property
    def is_ready(self) -> bool:
        return all(self.readiness_checks().values())