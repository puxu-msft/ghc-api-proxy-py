"""Safe capability projection for a selected raw capture."""

from dataclasses import dataclass
from enum import StrEnum


class CaptureStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    CORRUPT = "corrupt"


@dataclass(frozen=True, slots=True)
class RawCaptureAttemptObservation:
    attempt: int
    attempt_started: bool = False
    request_started: bool = False
    request_headers_available: bool = False
    request_body_available: bool = False
    response_started: bool = False
    response_headers_available: bool = False
    response_body_available: bool = False
    response_complete: bool = False
    attempt_complete: bool = False

    @property
    def wire_diagnostic_eligible(self) -> bool:
        return (
            self.attempt_started
            and self.request_started
            and self.request_headers_available
            and self.request_body_available
            and self.response_started
            and self.response_headers_available
            and self.response_body_available
            and self.response_complete
            and self.attempt_complete
        )


@dataclass(frozen=True, slots=True)
class RawCaptureObservation:
    status: CaptureStatus
    client_request_available: bool
    client_response_available: bool
    wire_diagnostic_eligible: bool
    semantic_replay_eligible: bool
    live_replay_eligible: bool
    capture_ref: str | None = None
    upstream_attempts: tuple[RawCaptureAttemptObservation, ...] = ()


__all__ = [
    "CaptureStatus",
    "RawCaptureAttemptObservation",
    "RawCaptureObservation",
]
