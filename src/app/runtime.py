from dataclasses import dataclass

from anyio.abc import TaskGroup

from app.config.settings import AppSettings


@dataclass(slots=True)
class RuntimeState:
    settings: AppSettings
    background_task_group: TaskGroup | None = None
    otel_enabled: bool = False
    github_token_ready: bool = False
    copilot_token_ready: bool = False
    models_ready: bool = False

    def readiness_checks(self) -> dict[str, bool]:
        return {
            "github_token": self.github_token_ready,
            "copilot_token": self.copilot_token_ready,
            "models": self.models_ready,
        }

    @property
    def is_ready(self) -> bool:
        return all(self.readiness_checks().values())