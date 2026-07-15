import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.anthropic.sanitize import SanitizationResult
from app.errors import ApiError


class RequestState(StrEnum):
    PENDING = "pending"
    SANITIZING = "sanitizing"
    EXECUTING = "executing"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"


ALLOWED_TRANSITIONS: dict[RequestState, set[RequestState]] = {
    RequestState.PENDING: {RequestState.SANITIZING},
    RequestState.SANITIZING: {RequestState.EXECUTING, RequestState.FAILED},
    RequestState.EXECUTING: {
        RequestState.STREAMING,
        RequestState.COMPLETED,
        RequestState.FAILED,
    },
    RequestState.STREAMING: {RequestState.COMPLETED, RequestState.FAILED},
    RequestState.COMPLETED: set(),
    RequestState.FAILED: set(),
}


@dataclass(slots=True)
class Attempt:
    number: int
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    status_code: int | None = None
    error: ApiError | None = None
    strategy_applied: str | None = None
    payload_modifications: list[str] = field(default_factory=lambda: list[str]())


@dataclass(slots=True)
class RequestContext:
    original_model: str
    original_payload: dict[str, Any]
    endpoint: str = "anthropic-messages"
    id: str = field(default_factory=lambda: str(uuid4()))
    state: RequestState = RequestState.PENDING
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    resolved_model: str = ""
    sanitization: SanitizationResult | None = None
    rate_limiter_wait_ms: float = 0.0
    attempts: list[Attempt] = field(default_factory=lambda: list[Attempt]())
    error: ApiError | None = None

    def transition(self, state: RequestState) -> None:
        if state not in ALLOWED_TRANSITIONS[self.state]:
            raise RuntimeError(f"invalid request state transition: {self.state} -> {state}")
        self.state = state
        if state in (RequestState.COMPLETED, RequestState.FAILED):
            self.completed_at = time.time()

    def fail(self, error: ApiError) -> None:
        self.error = error
        self.transition(RequestState.FAILED)