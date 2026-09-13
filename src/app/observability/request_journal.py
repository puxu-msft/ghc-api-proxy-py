"""Bounded, request-local lifecycle facts for observability projections."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from app.pipeline.response_observation import FrozenJsonObject, freeze_json, thaw_json
from app.wire_json import JsonValue

logger = logging.getLogger(__name__)


class RequestJournalEventKind(StrEnum):
    RESPONSE_READY = "response_ready"
    DELIVERY_STARTED = "delivery_started"
    DELIVERY_FINISHED = "delivery_finished"
    UPSTREAM_RESPONSE_STARTED = "upstream_response_started"
    UPSTREAM_RESPONSE_FINISHED = "upstream_response_finished"
    INTERRUPTION = "interruption"
    FAILURE = "failure"
    FINALIZED = "finalized"


@dataclass(frozen=True, slots=True)
class RequestJournalEvent:
    sequence: int
    kind: RequestJournalEventKind
    observed_s: float
    payload: FrozenJsonObject

    def as_dict(self) -> dict[str, JsonValue]:
        payload = thaw_json(self.payload)
        if not isinstance(payload, dict):
            raise TypeError("RequestJournal event payload is not an object")
        return {
            "sequence": self.sequence,
            "kind": self.kind.value,
            "observed_s": self.observed_s,
            "payload": cast(dict[str, JsonValue], payload),
        }


class RequestJournal:
    """Own the typed lifecycle event order before projections freeze it."""

    def __init__(self, request_id: str, *, max_events: int = 256) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        self.request_id = request_id
        self.max_events = max_events
        self._events: list[RequestJournalEvent] = []
        self._next_sequence = 0
        self._dropped_events = 0
        self._frozen = False

    @property
    def dropped_events(self) -> int:
        return self._dropped_events

    @property
    def frozen(self) -> bool:
        return self._frozen

    def record(
        self,
        kind: RequestJournalEventKind,
        observed_s: float,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """Record one safe event without allowing journal failure to escape."""
        if self._frozen:
            return False
        try:
            frozen_payload = freeze_json(payload or {})
            if not isinstance(frozen_payload, FrozenJsonObject):
                raise TypeError("RequestJournal payload is not an object")
            if len(self._events) >= self.max_events:
                self._dropped_events += 1
                return False
            self._events.append(
                RequestJournalEvent(
                    sequence=self._next_sequence,
                    kind=kind,
                    observed_s=observed_s,
                    payload=frozen_payload,
                )
            )
            self._next_sequence += 1
            return True
        except Exception as error:
            logger.warning(
                "request journal observation dropped: request_id=%s event=%s "
                "exception_type=%s",
                self.request_id,
                kind.value,
                type(error).__qualname__,
            )
            return False

    def freeze(self) -> tuple[RequestJournalEvent, ...]:
        self._frozen = True
        return tuple(self._events)

    def snapshot(self) -> tuple[RequestJournalEvent, ...]:
        return tuple(self._events)


__all__ = [
    "RequestJournal",
    "RequestJournalEvent",
    "RequestJournalEventKind",
]
