from dataclasses import dataclass

from app.config.settings import AppSettings


@dataclass(frozen=True, slots=True)
class HookContext:
    request_id: str
    endpoint: str
    protocol: str
    original_model: str
    resolved_model: str
    session_id: str | None
    agent_id: str | None
    attempt_number: int
    settings: AppSettings
