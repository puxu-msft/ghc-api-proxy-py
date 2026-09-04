"""Vocabulary shared by every model provider.

Endpoint identifiers are the upstream paths a catalog advertises in `supported_endpoints`.
They are not a naming of our own, so an answer can be compared with what upstream said.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal, cast


class ModelEndpoint(StrEnum):
    ANTHROPIC_MESSAGES = "/v1/messages"
    OPENAI_CHAT_COMPLETIONS = "/chat/completions"
    OPENAI_RESPONSES = "/responses"
    OPENAI_RESPONSES_WS = "ws:/responses"
    OPENAI_EMBEDDINGS = "/embeddings"


type CatalogSource = Literal["upstream", "static"]


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    """A provider catalog plus the provenance and driver facts needed to report it."""

    raw: Mapping[str, Any]
    source: CatalogSource
    driven_endpoints: frozenset[ModelEndpoint]


class ProviderError(RuntimeError):
    """A provider-level failure raised before any network request is made."""


class UnknownModel(ProviderError):
    """No such model on this provider.

    `target` is the name the mapping chain ended on, when that differs from `model_id`. It is worth carrying because `model_id` is the **request's** name on a passthrough — resolution hands back the original when it cannot place the chain's end — so an operator who wrote `claude-opus-4.8: A/claude-opus-5` and got the model name wrong would otherwise be told that `claude-opus-4.8` does not exist, and go looking for a typo in the mapping key rather than in its value. Spec §5.2.
    """

    def __init__(self, provider: str, model_id: str, target: str = "") -> None:
        detail = f"{provider} does not offer model {model_id!r}"
        if target and target != model_id:
            detail = f"{detail} (its mapping resolves to {target!r}, which {provider} does not offer either)"
        super().__init__(detail)
        self.provider = provider
        self.model_id = model_id
        self.target = target


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

    `reasoning_efforts` is `None` when the catalog said nothing about them and a tuple when it did, the empty tuple included. The distinction is the same one `resolve_endpoints` makes and it is load-bearing for the same reason: "this model publishes no efforts" and "we never learned" lead to different requests, and a single empty default would merge them.

    `adaptive_thinking` needs no such distinction, and that is a property of the catalog rather than a simplification here: it is a **positive** bit, published as `true` on the models that have it and absent on the ones that do not. A bool therefore says everything the catalog says. See `parse_adaptive_thinking` for why the neighbouring budget fields cannot answer this question.
    """

    id: str
    endpoints: frozenset[ModelEndpoint]
    unknown_endpoints: tuple[str, ...] = ()
    request_headers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    reasoning_efforts: tuple[str, ...] | None = None
    adaptive_thinking: bool = False

    def supports(self, endpoint: ModelEndpoint) -> bool:
        return endpoint in self.endpoints


def _supports(model: Mapping[str, Any]) -> dict[str, Any] | None:
    """The `capabilities.supports` object, or `None` when the entry has none to read."""
    capabilities = model.get("capabilities")
    if not isinstance(capabilities, dict):
        return None
    supports = cast(dict[str, Any], capabilities).get("supports")
    if not isinstance(supports, dict):
        return None
    return cast(dict[str, Any], supports)


def parse_reasoning_efforts(model: Mapping[str, Any]) -> tuple[str, ...] | None:
    """The effort names a catalog entry publishes under `capabilities.supports.reasoning_effort`.

    `None` for every shape that is not a list of strings — the key absent, `null`, or a value of some other type. Only a list is upstream stating the set, and only then is it taken at its word. Order is preserved as given; nothing here treats it as ranked, because the catalog does not say it is.

    Non-string entries are dropped rather than making the whole field unreadable: a list with one malformed member still tells us about its other members, and the alternative — discarding the lot — would take a model that publishes four usable efforts down to none.
    """
    supports = _supports(model)
    if supports is None:
        return None
    efforts = supports.get("reasoning_effort")
    if not isinstance(efforts, list):
        return None
    return tuple(entry for entry in cast(list[Any], efforts) if isinstance(entry, str))


def parse_adaptive_thinking(model: Mapping[str, Any]) -> bool:
    """Whether the catalog says this model takes `thinking: {"type": "adaptive"}`.

    Read strictly: only the literal `True` counts. Anything else — absent, `null`, `"true"`, `1` — is not upstream saying yes, and this bit decides which of two mutually exclusive request shapes goes out.

    **It is the only field that can answer the question.** The obvious neighbours cannot: `min_thinking_budget` and `max_thinking_budget` are published at 1024/32000 on `claude-sonnet-5`, which *rejects* `budget_tokens` outright, and on `claude-sonnet-4.5`, which requires it. Reading a budget limit as evidence that budgets are accepted is how the 400 of 2026-08-24 would have survived a first attempt at fixing it. See `.dev/docs/anthropic-direct-request-shape/spec.md` §2.2.
    """
    supports = _supports(model)
    if supports is None:
        return False
    return supports.get("adaptive_thinking") is True


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


# The endpoint a model of each kind is served on when the catalog names none. Copilot omits `supported_endpoints` outright for part of its catalog rather than listing an empty one — on 2026-08-20 that was 18 of 42 models.
#
# Measured, not inferred, by sending a real request to every one of those 18 on 2026-08-20: all 14 of type `chat` answered 200 on `/chat/completions`, and all 3 of type `embeddings` answered 200 on `/embeddings`. That is the whole evidence base, and the table is an allowlist for exactly that reason — a type nobody has measured gets no endpoint rather than a guess.
_DEFAULT_ENDPOINT_BY_TYPE = {
    "chat": ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
    "embeddings": ModelEndpoint.OPENAI_EMBEDDINGS,
}

# `completion` is deliberately absent, and it is the reason this is an allowlist. The 18th model, `gpt-41-copilot`, is the one of that type, and on the same date it answered `model_not_supported` on `/chat/completions`, on `/responses` and on `/v1/messages`, with `/completions` a 404 — the four paths probed, which is what was measured rather than a claim about every path this host might have. The reference implementation explains the shape: `refs/vscode-copilot-chat/.../openai/model.ts:112` selects models by `capabilities.type === 'completion'`, `openai/fetch.ts:470` names the endpoint `completions`, and `openai/fetch.ts:310` builds that URL against the *completions proxy* host — a separate service this proxy does not talk to. Giving the type a default would report a model as routable that answered 400 on everything tried.


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

    - **Nothing stated** (the key is absent, or present as `null`) — Copilot's actual shape for part of its catalog. Filled in with the measured endpoint for the model's kind, or with nothing when that kind has not been measured; an unknown kind fails closed rather than being guessed at, and `debug models` shows it as `no-endpoints` so the gap is visible instead of silent.
    - **A list** — upstream speaking, taken at its word, including the empty list. "None" and "unstated" are different claims and only the second is ours to fill in, so an empty list keeps `CapabilityMissing` meaning what it says. Copilot has never been observed sending that form.
    - **Anything else** — a string, a mapping, a number. Upstream emitted the field and we could not read it, which is not silence. Filling in a default here would invent a capability from an unreadable field, and worse, would ignore a value that may contradict it: `"/responses"` as a bare string would be answered by sending to `/chat/completions`. It fails closed instead, and `_wrong_shape` in the report calls the same entry `malformed`, so routing and the report cannot disagree about it.
    """
    known, unknown = parse_endpoints(advertised)
    if known or unknown:
        return ResolvedEndpoints(known, unknown, True)
    if advertised is not None:
        return ResolvedEndpoints(frozenset(), (), True)
    default = _DEFAULT_ENDPOINT_BY_TYPE.get(model_type)
    if default is None:
        return ResolvedEndpoints(frozenset(), (), False)
    return ResolvedEndpoints(frozenset({default}), (), False)


def require_endpoint(descriptor: ModelDescriptor, endpoint: ModelEndpoint, provider: str) -> None:
    """Fail closed before the network.

    A model with no advertised endpoints raises rather than being tried optimistically.
    """
    if not descriptor.endpoints and not descriptor.unknown_endpoints:
        raise CapabilityMissing(provider, descriptor.id)
    if not descriptor.supports(endpoint):
        raise EndpointNotSupported(provider, descriptor.id, endpoint.value)
