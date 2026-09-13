"""Immutable HistoryEntry projection from finalized request facts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from app.observability.request_completion import (
    DeliveryState,
    FailureCategory,
    RequestFacts,
)
from app.pipeline.response_observation import (
    FrozenJson,
    FrozenJsonObject,
    freeze_json,
    thaw_json,
)
from app.wire_json import JsonValue


class HistoryOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    INTERRUPTED = "interrupted"


class HistoryDelivery(StrEnum):
    NONE = "none"
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class CaptureCapabilities:
    status: str = "none"
    client_request_available: bool = False
    client_response_available: bool = False
    wire_diagnostic_eligible: bool = False
    semantic_replay_eligible: bool = False
    live_replay_eligible: bool = False


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """The stable, query-oriented projection of one client request.

    The projection deliberately carries no raw transport body. Capture
    evidence is linked later through ``capture_ref`` and its capability state.
    """

    request_id: str
    started_at: str
    finished_at: str
    outcome: HistoryOutcome
    delivery: HistoryDelivery
    status_code: int | None
    inbound_format: str
    requested_model: str
    resolved_model: str
    provider_name: str
    attempts: int
    retry_count: int
    replaced_failures: tuple[str, ...]
    usage: FrozenJsonObject
    losses: FrozenJson
    facts: FrozenJson
    capture: CaptureCapabilities
    capture_ref: str | None = None
    semantic_request: FrozenJson | None = None
    semantic_response: FrozenJson | None = None
    session_id: str | None = None
    agent_id: str | None = None

    @classmethod
    def from_request_facts(cls, facts: RequestFacts) -> HistoryEntry:
        line = facts.request_line()
        outcome = _outcome_for(facts)
        return cls(
            request_id=line.request_id,
            session_id=facts.session_id,
            agent_id=facts.agent_id,
            started_at=line.started_at,
            finished_at=facts.at,
            outcome=outcome,
            delivery=_delivery_for(facts, outcome),
            status_code=line.status_code,
            inbound_format=line.inbound_format,
            requested_model=line.requested_model,
            resolved_model=line.model,
            provider_name=line.provider_name,
            attempts=max(1, line.attempts),
            retry_count=max(0, line.attempts - 1),
            replaced_failures=tuple(line.replaced_failures),
            usage=_freeze_object(line.usage),
            losses=freeze_json(list(line.losses)),
            facts=freeze_json(list(line.facts)),
            capture=CaptureCapabilities(),
        )

    def as_dict(self) -> dict[str, JsonValue]:
        """Return the safe projection without exposing raw transport evidence."""
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outcome": self.outcome.value,
            "delivery": self.delivery.value,
            "status_code": self.status_code,
            "inbound_format": self.inbound_format,
            "requested_model": self.requested_model,
            "resolved_model": self.resolved_model,
            "provider_name": self.provider_name,
            "attempts": self.attempts,
            "retry_count": self.retry_count,
            "replaced_failures": list(self.replaced_failures),
            "usage": cast(dict[str, JsonValue], thaw_json(self.usage)),
            "losses": thaw_json(self.losses),
            "facts": thaw_json(self.facts),
            "capture": {
                "status": self.capture.status,
                "client_request_available": self.capture.client_request_available,
                "client_response_available": self.capture.client_response_available,
                "wire_diagnostic_eligible": self.capture.wire_diagnostic_eligible,
                "semantic_replay_eligible": self.capture.semantic_replay_eligible,
                "live_replay_eligible": self.capture.live_replay_eligible,
                "capture_ref": self.capture_ref,
            },
        }


def _freeze_object(value: object) -> FrozenJsonObject:
    frozen = freeze_json(value)
    if not isinstance(frozen, FrozenJsonObject):
        raise TypeError("History object projection did not produce a JSON object")
    return frozen


def _outcome_for(facts: RequestFacts) -> HistoryOutcome:
    if facts.status == "gone":
        return HistoryOutcome.ABORTED
    if facts.status == "fail":
        return HistoryOutcome.FAILED
    if (
        facts.status in {"ok", "retry"}
        and facts.delivery.state is DeliveryState.ACCEPTED
    ):
        return HistoryOutcome.COMPLETED
    if (
        facts.delivery.failure is not None
        and facts.delivery.failure.category
        in {FailureCategory.DISCONNECT, FailureCategory.CANCELLED}
    ):
        return HistoryOutcome.ABORTED
    return HistoryOutcome.FAILED


def _delivery_for(
    facts: RequestFacts,
    outcome: HistoryOutcome,
) -> HistoryDelivery:
    body_bytes = facts.delivery.downstream_body_bytes
    if outcome is HistoryOutcome.COMPLETED:
        return HistoryDelivery.COMPLETE
    if body_bytes is not None and body_bytes > 0:
        return HistoryDelivery.PARTIAL
    if facts.delivery.state is DeliveryState.STARTED or facts.delivery.http_start_accepted:
        return HistoryDelivery.UNCERTAIN
    return HistoryDelivery.NONE


__all__ = [
    "CaptureCapabilities",
    "HistoryDelivery",
    "HistoryEntry",
    "HistoryOutcome",
]
