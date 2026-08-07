import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from app.anthropic.sanitize import SanitizationResult
from app.errors import ApiError
from app.models.anthropic import MessagesResponse
from app.protocols.responses_anthropic import ResponseUsageFacts


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
    session_id: str | None = None
    agent_id: str | None = None
    strategy_applied: str | None = None
    payload_modifications: list[str] = field(default_factory=lambda: list[str]())


@dataclass(frozen=True, slots=True)
class RequestConversionFactRecord:
    attempt: int
    field_path: str
    disposition: str
    reason: str
    provenance: Literal["request"] = "request"


@dataclass(frozen=True, slots=True)
class ResponseConversionFactRecord:
    attempt: int
    code: str
    field_path: str
    provenance: Literal["response"] = "response"


type ConversionFactRecord = RequestConversionFactRecord | ResponseConversionFactRecord


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
    protocol_leg: str = ""
    route_reason: str = ""
    sanitization: SanitizationResult | None = None
    rate_limiter_wait_ms: float = 0.0
    attempts: list[Attempt] = field(default_factory=lambda: list[Attempt]())
    hook_records: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    normalized_response: MessagesResponse | None = None
    final_response_payload: dict[str, Any] | None = None
    response_usage: ResponseUsageFacts | None = None
    conversion_facts: tuple[ConversionFactRecord, ...] = ()
    error: ApiError | None = None
    session_id: str | None = None
    agent_id: str | None = None

    def transition(self, state: RequestState) -> None:
        if state not in ALLOWED_TRANSITIONS[self.state]:
            raise RuntimeError(f"invalid request state transition: {self.state} -> {state}")
        self.state = state
        if state in (RequestState.COMPLETED, RequestState.FAILED):
            self.completed_at = time.time()

    def fail(self, error: ApiError) -> None:
        self.error = error
        self.transition(RequestState.FAILED)