from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelRef:
    requested: str
    resolved: str


@dataclass(slots=True)
class HistoryEntry:
    id: str
    session_id: str | None
    agent_id: str | None
    started_at: float
    ended_at: float | None
    endpoint: str
    status: str
    model: ModelRef
    request_payload: dict[str, Any]
    response: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    error_message: str | None = None
    pinned: bool = False
