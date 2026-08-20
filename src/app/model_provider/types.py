"""Vocabulary shared by every model provider.

Endpoint identifiers are the upstream paths a catalog advertises in `supported_endpoints`.
They are not a naming of our own, so an answer can be compared with what upstream said.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, cast


class ModelEndpoint(StrEnum):
    ANTHROPIC_MESSAGES = "/v1/messages"
    OPENAI_CHAT_COMPLETIONS = "/chat/completions"
    OPENAI_RESPONSES = "/responses"
    OPENAI_RESPONSES_WS = "ws:/responses"
    OPENAI_EMBEDDINGS = "/embeddings"


class ProviderError(RuntimeError):
    """A provider-level failure raised before any network request is made."""


class UnknownModel(ProviderError):
    def __init__(self, provider: str, model_id: str) -> None:
        super().__init__(f"{provider} does not offer model {model_id!r}")
        self.provider = provider
        self.model_id = model_id


class CapabilityMissing(ProviderError):
    """The catalog told us nothing about which endpoints a model supports.

    Treated as a refusal rather than as permission.
    An empty capability set must never widen into "try it and see".
    """

    def __init__(self, provider: str, model_id: str) -> None:
        super().__init__(f"{provider} advertises no endpoints for model {model_id!r}")
        self.provider = provider
        self.model_id = model_id


class EndpointNotSupported(ProviderError):
    def __init__(self, provider: str, model_id: str, endpoint: str) -> None:
        super().__init__(f"model {model_id!r} does not advertise {endpoint} on {provider}")
        self.provider = provider
        self.model_id = model_id
        self.endpoint = endpoint


class EndpointNotImplemented(ProviderError):
    """The model advertises the endpoint but this proxy does not drive it."""

    def __init__(self, provider: str, endpoint: str) -> None:
        super().__init__(f"{provider} has no driver for {endpoint}")
        self.provider = provider
        self.endpoint = endpoint


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """What a provider knows about one model.

    `unknown_endpoints` keeps advertised paths we have no enum member for.
    They are preserved rather than dropped so a new upstream endpoint stays visible.
    """

    id: str
    endpoints: frozenset[ModelEndpoint]
    unknown_endpoints: tuple[str, ...] = ()
    request_headers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def supports(self, endpoint: ModelEndpoint) -> bool:
        return endpoint in self.endpoints


def parse_endpoints(advertised: object) -> tuple[frozenset[ModelEndpoint], tuple[str, ...]]:
    """Split advertised endpoint strings into known members and unrecognised leftovers."""
    if not isinstance(advertised, list):
        return frozenset(), ()
    known: set[ModelEndpoint] = set()
    unknown: list[str] = []
    for entry in advertised:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(entry, str):
            continue
        try:
            known.add(ModelEndpoint(entry))
        except ValueError:
            unknown.append(entry)
    return frozenset(known), tuple(unknown)


# The endpoint a model of each kind is served on when the catalog names none. Copilot omits `supported_endpoints` outright for part of its catalog rather than listing an empty one — on 2026-08-20 that was 18 of 42 models — and those models are not endpoint-less; they are served on the standard endpoint for their kind. Embeddings models are the one kind that differs, and they are also the one kind that never appears with an advertised list, so the split cannot be learnt from the catalog itself.
_DEFAULT_ENDPOINT_BY_TYPE = {"embeddings": ModelEndpoint.OPENAI_EMBEDDINGS}
# Everything else. The absent set on that date held 14 models of type `chat` and one of type `completion`, and both are chat-completions models.
DEFAULT_ENDPOINT = ModelEndpoint.OPENAI_CHAT_COMPLETIONS


def model_type_of(model: Mapping[str, Any]) -> str:
    """`capabilities.type` — `chat`, `completion` or `embeddings` — or empty when unreadable.

    It is the only thing in an entry that says which endpoint a model of this kind is served on, and it is needed exactly when `supported_endpoints` says nothing. It lives beside `resolve_endpoints` rather than in either caller because routing and the report both have to read it, and reading it twice is how the two would come to disagree.
    """
    capabilities = model.get("capabilities")
    if not isinstance(capabilities, dict):
        return ""
    model_type = cast(dict[str, Any], capabilities).get("type")
    return model_type if isinstance(model_type, str) else ""


@dataclass(frozen=True, slots=True)
class ResolvedEndpoints:
    """Which endpoints a model offers, and whether the catalog is where that came from.

    `advertised` is false when nothing was named and the default for the model's kind was used instead. Routing does not care which it was — the endpoint is the endpoint — but anything reporting on the catalog does, because presenting an assumption as something upstream said is how a report stops being evidence.
    """

    known: frozenset[ModelEndpoint]
    unknown: tuple[str, ...]
    advertised: bool


def resolve_endpoints(advertised: object, *, model_type: str = "") -> ResolvedEndpoints:
    """Read a catalog entry's endpoints, falling back to the standard one for its kind.

    Three inputs, three answers, and the distinction between the last two is the whole point:

    - **Nothing stated** (the key is absent, or present as `null`) — Copilot's actual shape for part of its catalog. Filled in with the default for the model's kind.
    - **A list** — upstream speaking, taken at its word, including the empty list. "None" and "unstated" are different claims and only the second is ours to fill in, so an empty list keeps `CapabilityMissing` meaning what it says. Copilot has never been observed sending that form.
    - **Anything else** — a string, a mapping, a number. Upstream emitted the field and we could not read it, which is not silence. Filling in a default here would invent a capability from an unreadable field, and worse, would ignore a value that may contradict it: `"/responses"` as a bare string would be answered by sending to `/chat/completions`. It fails closed instead, and `_wrong_shape` in the report calls the same entry `malformed`, so routing and the report cannot disagree about it.
    """
    known, unknown = parse_endpoints(advertised)
    if known or unknown:
        return ResolvedEndpoints(known, unknown, True)
    if advertised is not None:
        return ResolvedEndpoints(frozenset(), (), True)
    default = _DEFAULT_ENDPOINT_BY_TYPE.get(model_type, DEFAULT_ENDPOINT)
    return ResolvedEndpoints(frozenset({default}), (), False)


def require_endpoint(descriptor: ModelDescriptor, endpoint: ModelEndpoint, provider: str) -> None:
    """Fail closed before the network.

    A model with no advertised endpoints raises rather than being tried optimistically.
    """
    if not descriptor.endpoints and not descriptor.unknown_endpoints:
        raise CapabilityMissing(provider, descriptor.id)
    if not descriptor.supports(endpoint):
        raise EndpointNotSupported(provider, descriptor.id, endpoint.value)
