"""The object one request is described by.

MAIN.md: every request is described by a RequestContext, and subscribers may modify it.
Every field is writable by design.
The user ruled that no ownership or permission rule applies, so this is a plain mutable record.
"""

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.model_provider import ModelEndpoint


class WireFormat(StrEnum):
    """A request/response body shape, as used in `model@format` and translator names."""

    ANTHROPIC_MESSAGES = "anthropic-messages"
    OPENAI_CHAT_COMPLETIONS = "openai-chat-completions"
    OPENAI_RESPONSES = "openai-responses"
    OPENAI_EMBEDDINGS = "openai-embeddings"


ENDPOINT_FORMATS: dict[ModelEndpoint, WireFormat] = {
    ModelEndpoint.ANTHROPIC_MESSAGES: WireFormat.ANTHROPIC_MESSAGES,
    ModelEndpoint.OPENAI_CHAT_COMPLETIONS: WireFormat.OPENAI_CHAT_COMPLETIONS,
    ModelEndpoint.OPENAI_RESPONSES: WireFormat.OPENAI_RESPONSES,
    ModelEndpoint.OPENAI_EMBEDDINGS: WireFormat.OPENAI_EMBEDDINGS,
}

FORMAT_ENDPOINTS: dict[WireFormat, ModelEndpoint] = {
    wire: endpoint for endpoint, wire in ENDPOINT_FORMATS.items()
}


@dataclass(slots=True)
class Attempt:
    """One upstream exchange within a request."""

    index: int
    endpoint: ModelEndpoint | None = None
    payload: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    status_code: int | None = None
    error: str = ""


@dataclass(slots=True)
class RequestContext:
    inbound_format: WireFormat
    requested_model: str
    payload: dict[str, Any]

    id: str = field(default_factory=lambda: str(uuid4()))
    stream: bool = False

    # The client's own protocol-negotiation headers, already filtered by
    # `app.pipeline.request_headers`. Held here rather than read at the send site because the
    # driver is where an attempt is built, and it has no access to the ASGI request.
    client_headers: Mapping[str, str] = field(default_factory=lambda: dict[str, str]())

    # Filled in by routing.
    resolved_model: str = ""
    provider_name: str = ""
    endpoint: ModelEndpoint | None = None
    target_format: WireFormat | None = None
    translation_required: bool = False
    route_reason: str = ""

    attempts: list[Attempt] = field(default_factory=lambda: list[Attempt]())

    # Anything a subscriber wants to carry between events.
    extras: MutableMapping[str, Any] = field(default_factory=lambda: dict[str, Any]())

    def begin_attempt(self, *, payload: dict[str, Any] | None = None) -> Attempt:
        attempt = Attempt(
            index=len(self.attempts),
            endpoint=self.endpoint,
            payload=payload if payload is not None else dict(self.payload),
        )
        self.attempts.append(attempt)
        return attempt

    @property
    def current_attempt(self) -> Attempt | None:
        return self.attempts[-1] if self.attempts else None

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)
