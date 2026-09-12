"""The object one request is described by.

`docs/.human-controlled/request-pipeline.md`: one object describes each request, and subscribers may modify it.
Every field is writable by design.
The user ruled that no ownership or permission rule applies, so this is a plain mutable record.

That document now calls the object `ClientRequest` and gives each upstream try its own `UpstreamAttempt`. Here it is still `RequestContext` — the name the earlier single-document version of that spec used — holding its tries as `Attempt` records. Whether to follow the rename is that document's author's call, not this module's.
"""

import time
from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, cast
from uuid import uuid4

from app.model_provider import ModelDescriptor, ModelEndpoint
from app.pipeline.delivery.assembling import Terminal
from app.pipeline.response_observation import ResponseObservation, ResponsesObserver
from app.pipeline.retry import RetryLedger
from app.pipeline.translation_driver.options import TranslationOptions
from app.pipeline.translation_driver.semantic import SemanticRequest, TranslationTarget
from app.tokenization.admission import TokenAdmissionObservation


class WireFormat(StrEnum):
    """A request/response body shape, as used in `model@format` and translator names."""

    ANTHROPIC_MESSAGES = "anthropic-messages"
    OPENAI_CHAT_COMPLETIONS = "openai-chat-completions"
    OPENAI_RESPONSES = "openai-responses"
    OPENAI_EMBEDDINGS = "openai-embeddings"
    # Ratified in `api.md` and routed, but no translator answers to this name yet. `InboundRoute.implemented` is what keeps a request from reaching one; the value exists so the route table can say which format the path carries rather than borrowing a neighbour's.
    GEMINI_GENERATE_CONTENT = "gemini-generate-content"


ENDPOINT_FORMATS: dict[ModelEndpoint, WireFormat] = {
    ModelEndpoint.ANTHROPIC_MESSAGES: WireFormat.ANTHROPIC_MESSAGES,
    ModelEndpoint.OPENAI_CHAT_COMPLETIONS: WireFormat.OPENAI_CHAT_COMPLETIONS,
    ModelEndpoint.OPENAI_RESPONSES: WireFormat.OPENAI_RESPONSES,
    ModelEndpoint.OPENAI_EMBEDDINGS: WireFormat.OPENAI_EMBEDDINGS,
}

FORMAT_ENDPOINTS: dict[WireFormat, ModelEndpoint] = {
    wire: endpoint for endpoint, wire in ENDPOINT_FORMATS.items()
}


def _freeze_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, Any], value)
        frozen: dict[str, Any] = {
            key: _freeze_payload(item) for key, item in mapping.items()
        }
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(_freeze_payload(item) for item in cast(list[Any], value))
    if isinstance(value, tuple):
        return tuple(_freeze_payload(item) for item in cast(tuple[Any, ...], value))
    if isinstance(value, set):
        return frozenset(_freeze_payload(item) for item in cast(set[Any], value))
    return deepcopy(value)


def _thaw_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, Any], value)
        thawed: dict[str, Any] = {
            key: _thaw_payload(item) for key, item in mapping.items()
        }
        return thawed
    if isinstance(value, tuple):
        return [_thaw_payload(item) for item in cast(tuple[Any, ...], value)]
    if isinstance(value, frozenset):
        return {_thaw_payload(item) for item in cast(frozenset[Any], value)}
    return value


@dataclass(frozen=True, slots=True)
class AttemptPlan:
    """The immutable, fully resolved facts for one upstream attempt."""

    provider_name: str
    descriptor: ModelDescriptor
    model_id: str
    client_format: WireFormat
    payload_format: WireFormat
    target_format: WireFormat
    endpoint: ModelEndpoint
    payload: Mapping[str, Any]
    admission: TokenAdmissionObservation

    def __post_init__(self) -> None:
        if self.payload_format is not self.target_format:
            raise ValueError("attempt plan payload and target formats must agree")
        if FORMAT_ENDPOINTS.get(self.target_format) is not self.endpoint:
            raise ValueError("attempt plan endpoint does not match target format")
        if self.descriptor.id != self.model_id:
            raise ValueError("attempt plan descriptor and model do not agree")
        if self.descriptor.provider_name != self.provider_name:
            raise ValueError("attempt plan descriptor and provider do not agree")
        if not self.descriptor.supports(self.endpoint):
            raise ValueError("attempt plan descriptor does not support its endpoint")
        if self.admission.model != self.model_id:
            raise ValueError("attempt plan admission and model do not agree")
        if self.admission.provider != self.provider_name:
            raise ValueError("attempt plan admission and provider do not agree")
        if self.admission.target_format != self.target_format.value:
            raise ValueError("attempt plan admission and target format do not agree")
        if self.admission.catalog_generation != self.descriptor.catalog_generation:
            raise ValueError("attempt plan admission and descriptor generation do not agree")
        if self.admission.catalog_refreshed_at != self.descriptor.catalog_refreshed_at:
            raise ValueError("attempt plan admission and descriptor refresh time do not agree")
        object.__setattr__(self, "payload", _freeze_payload(self.payload))

    @property
    def admission_observation(self) -> TokenAdmissionObservation:
        return self.admission

    @property
    def provider(self) -> str:
        return self.provider_name

    @property
    def admission_result(self) -> TokenAdmissionObservation:
        return self.admission

    def payload_matches(self, payload: Mapping[str, Any]) -> bool:
        return _thaw_payload(self.payload) == payload


@dataclass(slots=True)
class Attempt:
    """One upstream exchange within a request."""

    index: int
    started_at: float = field(default_factory=time.monotonic)
    endpoint: ModelEndpoint | None = None
    payload: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    status_code: int | None = None
    error: str = ""
    # The monotonic instant this attempt must not outlive, or `None` when nothing bounds it. An instant rather than a duration because two places enforce it — the driver, up to the response headers, and the delivery chain, over the body that arrives after the driver has returned — and a duration would be started twice, from two different moments, and would then bound rather more than one attempt's life.
    deadline_at: float | None = None
    # Created when the attempt opens, before subscribers or the send can fail. A replacement attempt therefore becomes the only current source of response facts even when it never obtains response headers.
    response_observer: ResponsesObserver | None = None
    # One result per attempt. Kept on the attempt so a retry cannot overwrite the admission facts of the request it replaced.
    token_admission: TokenAdmissionObservation | None = None
    # The immutable resolved facts are an additional projection for validation and observability.
    plan: AttemptPlan | None = None


@dataclass(slots=True)
class RequestContext:
    inbound_format: WireFormat
    requested_model: str
    payload: dict[str, Any]

    # The body exactly as the client sent it, before anything in this proxy reshaped it. Read-only by contract: `payload` is the working copy and every fixup edits that one.
    # `message-format-reshape.md` requires the original client request kept for the history record to be unaffected by the reshaping, and until this existed there was nowhere for it to live — `build_context` took a shallow copy, so `repair_tool_pairs` editing `messages` in place reached back into the parsed body and the "original" was already not what arrived.
    # An empty mapping means nobody supplied one, which is what a context built directly in a test looks like; it is not a claim that the client sent an empty body.
    original_payload: Mapping[str, Any] = field(default_factory=lambda: dict[str, Any]())

    id: str = field(default_factory=lambda: str(uuid4()))
    # The client's logical conversation identity, consumed by providers that expose an upstream interaction binding.
    interaction_id: str | None = None
    # Resolved once at the first provider send so mutable subscribers cannot split retries or delivery reopens across interactions.
    provider_interaction_id: str | None = None
    stream: bool = False

    # The client's own protocol-negotiation headers, already filtered by `app.pipeline.request_headers`. Held here rather than read at the send site because the driver is where an attempt is built, and it has no access to the ASGI request.
    client_headers: Mapping[str, str] = field(default_factory=lambda: dict[str, str]())
    # The filtered client protocol headers before target-path forwarding policy changes `client_headers`. `None` means the request-lifetime snapshot has not been initialized; an empty mapping is a real initialized value. `build_context` initializes real inbound requests, while `source_headers_for_translation` preserves contexts constructed directly in tests by snapshotting their current headers exactly once.
    source_headers: Mapping[str, str] | None = None

    # Filled in by routing.
    resolved_model: str = ""
    provider_name: str = ""
    endpoint: ModelEndpoint | None = None
    target_format: WireFormat | None = None
    translation_required: bool = False
    route_reason: str = ""
    # What the catalog publishes about the model this attempt is going to, carried straight off the route so a subscriber reads the same descriptor routing decided on. `None` means routing has not run, or ran against a provider that does not describe the model — a subscriber reading a capability off it must treat that as "the catalog said nothing", never as permission.
    model_descriptor: ModelDescriptor | None = None

    # Request-scoped translation facts that the Responses response half cannot
    # recover from upstream output items alone.
    client_search_tool: str = ""
    hosted_web_search_expected: bool = False
    semantic_request: SemanticRequest | None = None
    translation_target: TranslationTarget | None = None
    translation_options: TranslationOptions | None = None

    attempts: list[Attempt] = field(default_factory=lambda: list[Attempt]())

    # What the reply came back with, once one has.
    # Aggregated here rather than re-derived by whoever wants it, so a consumer — the console line, and anything after it — reads a record instead of inspecting the response payload for itself.
    # Both delivery paths fill it: the streaming one from its assembler, a buffered one from the body it read whole. `None` means no reply was reached.
    reply: Terminal | None = None
    # Provider-side facts are separate from `reply`: observation can exist for a failed or partial attempt and never participates in framing, retry or hand-over decisions.
    response_observation: ResponseObservation | None = None

    # Anything a subscriber wants to carry between events.
    extras: MutableMapping[str, Any] = field(default_factory=lambda: dict[str, Any]())
    # One budget for this client request, however many attempts it takes — including the ones delivery opens after a torn body, which happen long after the driver that opened the first has returned. Built lazily by `handle` and kept here rather than by the driver, because a driver built per call would hand each reopened attempt a fresh budget and `max_total` would stop being a bound on anything.
    retry_ledger: RetryLedger | None = None

    def source_headers_for_translation(self) -> Mapping[str, str]:
        if self.source_headers is None:
            self.source_headers = dict(self.client_headers)
        return self.source_headers

    def interaction_id_for_provider(self) -> str:
        if self.provider_interaction_id is None:
            self.provider_interaction_id = self.interaction_id or self.id
        return self.provider_interaction_id

    def begin_attempt(self, *, payload: dict[str, Any] | None = None) -> Attempt:
        # The current response changes when the attempt begins, not when it gets headers. Otherwise an attempt that fails before producing a stream leaves the previous attempt's partial items looking current.
        self.response_observation = None
        observer = (
            ResponsesObserver()
            if self.target_format is WireFormat.OPENAI_RESPONSES
            else None
        )
        attempt = Attempt(
            index=len(self.attempts),
            endpoint=self.endpoint,
            payload=payload if payload is not None else dict(self.payload),
            response_observer=observer,
        )
        self.attempts.append(attempt)
        return attempt

    @property
    def current_attempt(self) -> Attempt | None:
        return self.attempts[-1] if self.attempts else None

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)
