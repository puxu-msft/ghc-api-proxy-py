"""Typed parsing of OpenAI Responses SSE/event envelopes.

HTTP SSE and WebSocket adapters may expose different framing, but once an
event reaches the semantic pipeline it has the same name, raw JSON payload,
and decoded object. Consumers remain responsible for their own state and
delivery policy.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast


class ResponsesEventSource(Protocol):
    @property
    def event(self) -> str: ...

    @property
    def data(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ResponsesEvent:
    name: str
    data: Mapping[str, Any]
    raw_data: str


def parse_responses_event(event: ResponsesEventSource) -> ResponsesEvent:
    """Decode one already-framed Responses event without choosing its meaning."""
    decoded = json.loads(event.data)
    if not isinstance(decoded, Mapping):
        raise ValueError("Responses event payload must be an object")
    data = cast(Mapping[str, Any], decoded)
    name = event.event or str(data.get("type", ""))
    return ResponsesEvent(name=name, data=data, raw_data=event.data)


__all__ = ["ResponsesEvent", "ResponsesEventSource", "parse_responses_event"]
