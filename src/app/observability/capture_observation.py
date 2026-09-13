"""Safe capability projection for a selected raw capture."""

from dataclasses import dataclass
from enum import StrEnum


class CaptureStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    CORRUPT = "corrupt"


@dataclass(frozen=True, slots=True)
class RawCaptureObservation:
    status: CaptureStatus
    client_request_available: bool
    client_response_available: bool
    wire_diagnostic_eligible: bool
    semantic_replay_eligible: bool
    live_replay_eligible: bool


__all__ = ["CaptureStatus", "RawCaptureObservation"]
