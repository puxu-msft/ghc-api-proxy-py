"""Vocabulary shared by every model provider.

Endpoint identifiers are the upstream paths a catalog advertises in `supported_endpoints`.
They are not a naming of our own, so an answer can be compared with what upstream said.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


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


def require_endpoint(descriptor: ModelDescriptor, endpoint: ModelEndpoint, provider: str) -> None:
    """Fail closed before the network.

    A model with no advertised endpoints raises rather than being tried optimistically.
    """
    if not descriptor.endpoints and not descriptor.unknown_endpoints:
        raise CapabilityMissing(provider, descriptor.id)
    if not descriptor.supports(endpoint):
        raise EndpointNotSupported(provider, descriptor.id, endpoint.value)
