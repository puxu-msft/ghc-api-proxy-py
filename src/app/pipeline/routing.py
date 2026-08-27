"""Routing: which provider, which model, which endpoint, and whether to translate.

`docs/.human-controlled/request-pipeline.md` calls this the pipeline's first task.
Decide whether the inbound format and the model's endpoint differ, and so whether to translate.

A model may name its target format explicitly as `model@format`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.model_provider import (
    CapabilityMissing,
    EndpointNotSupported,
    ModelDescriptor,
    ModelEndpoint,
    ModelProvider,
    ProviderRegistry,
    UnknownModel,
)
from app.pipeline.model_resolution import (
    QUALIFIER_SEPARATOR,
    ModelResolution,
    ProviderDiscovery,
    ProviderOrigin,
    canonical,
    discover_provider,
    resolve_against_catalog,
    split_provider_qualifier,
)
from app.pipeline.request import (
    ENDPOINT_FORMATS,
    FORMAT_ENDPOINTS,
    RequestContext,
    WireFormat,
)
from app.pipeline.translation_driver.semantic import TranslationTarget

FORMAT_SEPARATOR = "@"

# Tried in order when the inbound format's own endpoint is unavailable.
_FALLBACK_ORDER: tuple[WireFormat, ...] = (
    WireFormat.ANTHROPIC_MESSAGES,
    WireFormat.OPENAI_RESPONSES,
    WireFormat.OPENAI_CHAT_COMPLETIONS,
    WireFormat.OPENAI_EMBEDDINGS,
)


class RoutingError(RuntimeError):
    """Raised before any network request, so an unroutable request never reaches upstream."""


@dataclass(frozen=True, slots=True)
class Route:
    provider_name: str
    model_id: str
    endpoint: ModelEndpoint
    target_format: WireFormat
    inbound_format: WireFormat
    translation_required: bool
    reason: str
    resolution: ModelResolution
    # What the catalog says the model answering this request can do. Carried rather than looked up again downstream: `decide_route` has already asked the provider for it, and a second lookup is a second answer waiting to disagree with the one routing was decided on — the same argument `translation_target` makes for the translation leg.
    #
    # `None` only where no descriptor was available, which today means a `Route` a test built by hand; every route `decide_route` returns has one, because it raises `UnknownModel` when the provider does not describe the model.
    descriptor: ModelDescriptor | None = None
    # How `provider_name` was arrived at, carried for the same reason `descriptor` is: `choose_provider` has already decided it, and anything re-deriving it later would be a second answer waiting to disagree with this one.
    #
    # **Nothing reads it today.** `/api/status` reports an `origin` too, but that one comes from `RouteReport` — `route_table` answers about names in the abstract, and never builds a `Route`. Kept because carrying a fact the decision already produced costs nothing and dropping it would mean re-deriving it the first time a log line or a history record wants it; but do not change this field expecting `/api/status` to move.
    provider_origin: ProviderOrigin = "default"


def split_format_suffix(name: str) -> tuple[str, WireFormat | None]:
    """Split `model@format`, returning the bare model and the named format.

    An unrecognised format after `@` is an error rather than part of the model name.
    Treating it as a name would send a request the operator never asked for.

    "Unrecognised" is decided against `FORMAT_ENDPOINTS` rather than against the enum, and the difference is not academic: a format may be named — because the route table has to say which shape a path carries — while no endpoint answers to it. `WireFormat.GEMINI_GENERATE_CONTENT` is exactly that today. Judged on the enum alone, `claude-model@gemini-generate-content` passed this function and died on `FORMAT_ENDPOINTS[...]` in `decide_route`, reaching the client as a 502 whose body was the Python `repr` of an enum member — measured on `/v1/messages`, the primary path. Keeping the judgement on the same table the lookup uses means a format added for routing purposes cannot open that hole again.
    """
    if FORMAT_SEPARATOR not in name:
        return name, None
    model, _, suffix = name.rpartition(FORMAT_SEPARATOR)
    if not model:
        return name, None
    try:
        wire = WireFormat(suffix)
    except ValueError:
        raise RoutingError(f"unknown target format {suffix!r} in {name!r}") from None
    if wire not in FORMAT_ENDPOINTS:
        # Named but unroutable. Said in its own words rather than folded into the branch above, because the two send an operator to different places: one is a typo, the other is a capability this proxy has not built.
        raise RoutingError(f"target format {suffix!r} in {name!r} has no endpoint on this proxy")
    return model, wire


@dataclass(frozen=True, slots=True)
class ProviderChoice:
    """Who serves this request, where the alias chain ended, and how that was decided.

    Shared by `decide_route` and the `/api/status` route table so both read one answer. Two derivations of the same rule would drift, and the place they would drift is exactly the one an operator opens `/api/status` to check.
    """

    provider_name: str
    origin: ProviderOrigin
    target: str
    # The inbound name with any request-side `provider/` prefix removed. What passthrough reports, since the prefix was never part of the model's name.
    requested: str
    matched_key: str = ""
    hops: int = 0


def _fallback_name(providers: ProviderRegistry, subject: str) -> str:
    """The configured fallback, or a refusal that names the thing actually at fault.

    Refusing rather than falling back to the default is the user's ruling and the fail-closed direction: an unrecognised qualifier means the operator *did* express an intent and got it wrong, so serving the request from wherever the default happens to point would answer a question nobody asked, on an account nobody chose. Spec §5.3.

    `subject` is a phrase, not a bare name, because the two callers have different culprits. On the request side the client's own model name carries the bad prefix. On the configuration side it is the mapping **value** — and quoting the key there would be false in the same way §5.2 describes: it sends an operator to check whether the alias is misspelled when the misspelling is on the other side of the colon.
    """
    name = providers.fallback_name
    if not name:
        configured = ", ".join(sorted(providers.names)) or "none"
        raise RoutingError(
            f"{subject} names a model provider this deployment does not configure, "
            f"and no `fallback_model_provider` is set to catch it "
            f"(configured providers: {configured})"
        )
    return name


def _unrecognised_in_mapping(discovery: ProviderDiscovery) -> str:
    """How to describe a mapping entry whose value names an unconfigured provider."""
    head = discovery.value.partition(QUALIFIER_SEPARATOR)[0]
    if discovery.matched_key:
        return f"mapping value {discovery.value!r} (for key {discovery.matched_key!r}), whose {head!r}"
    return f"{discovery.value!r}, whose {head!r}"


def choose_provider(
    model_name: str,
    *,
    providers: ProviderRegistry,
    mappings: Mapping[str, str],
) -> ProviderChoice:
    """Decide which provider serves an inbound model name.

    Two sources, in priority order. A `provider/` prefix on the request itself wins outright — it is how an operator checks a provider by hand without editing configuration and restarting. Otherwise the qualifiers written into `model_mappings` decide, via `discover_provider`.

    When the request carries its own prefix, the alias chain is **still** walked, but only for the name: a qualifier further down the chain cannot take the request away from the provider it explicitly asked for. Without that, `A/opus` with `opus: B/claude-opus-5` in the table would be served by B, which reads the priority backwards.
    """
    explicit, bare, request_qualified = split_provider_qualifier(model_name, providers.names)
    discovery = discover_provider(bare, mappings=mappings, provider_names=providers.names)

    if request_qualified:
        recognised = explicit is not None
        return ProviderChoice(
            provider_name=explicit
            if recognised
            else _fallback_name(providers, f"the requested model {model_name!r}"),
            origin="qualified" if recognised else "fallback",
            target=discovery.target,
            requested=bare,
            matched_key=discovery.matched_key,
            hops=discovery.hops,
        )

    if discovery.origin == "qualified":
        provider_name = discovery.provider
    elif discovery.origin == "fallback":
        provider_name = _fallback_name(providers, _unrecognised_in_mapping(discovery))
    else:
        provider_name = providers.default_name
    return ProviderChoice(
        provider_name=provider_name,
        origin=discovery.origin,
        target=discovery.target,
        requested=bare,
        matched_key=discovery.matched_key,
        hops=discovery.hops,
    )


type Serviceability = Literal["yes", "absent", "disabled", "unknown", "unroutable"]


@dataclass(frozen=True, slots=True)
class RouteReport:
    """What this proxy would do with one name a client could send.

    A record, not a view onto live objects: `/v1/models` and `/api/status` both read this and nothing else, so the two cannot answer the same question differently. Spec §4.1 point 6 and §4.2.

    `model` is the name that would actually go upstream. `intended` is the mapping chain's end, filled **only** when it differs — which happens when the chain's target is unavailable and resolution falls back to the client's own name (Spec §2.4). Two fields rather than one because both facts are true at once and an operator needs both: what will be sent, and what the configuration asked for.
    """

    name: str
    provider: str | None
    model: str
    origin: ProviderOrigin
    serviceable: Serviceability
    intended: str = ""


def _candidate_names(providers: ProviderRegistry, mappings: Mapping[str, str]) -> tuple[str, ...]:
    """Every name worth reporting on: catalog ids and mapping keys alike.

    Catalog names first, then mapping keys, each group sorted; de-duplicated by `canonical` with the first spelling kept. So a name that is both an upstream id and a mapping key appears once, spelled the way upstream spells it — the catalog is the authority on its own ids, while a mapping key is whatever an operator typed. Spec §4.1 point 2.
    """
    catalog = sorted({model for name in providers.names for model in providers.get(name).available_ids})
    seen: set[str] = set()
    ordered: list[str] = []
    for name in (*catalog, *sorted(mappings)):
        key = canonical(name)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(name)
    return tuple(ordered)


def _report_for(
    name: str,
    *,
    providers: ProviderRegistry,
    mappings: Mapping[str, str],
) -> RouteReport:
    try:
        # The same first step `decide_route` takes, and for the same reason. A candidate carrying a format suffix is split before anything looks it up, so skipping it here would make the table answer one way and the wire another — and `/v1/models` would advertise an id that cannot be sent.
        bare, _ = split_format_suffix(name)
    except RoutingError:
        # The suffix names a format no endpoint answers to, so no request using this name can ever be routed. Reported rather than dropped: a mapping key nobody can reach is worth seeing.
        return RouteReport(name, None, name, "default", "unroutable")

    try:
        choice = choose_provider(bare, providers=providers, mappings=mappings)
    except RoutingError:
        # The one shape with no provider at all: a qualifier naming an unconfigured provider, with no `fallback_model_provider` to catch it. Reported rather than omitted — a row that cannot be served is exactly what an operator opened this to find. Spec §4.2.2.
        discovery = discover_provider(bare, mappings=mappings, provider_names=providers.names)
        return RouteReport(name, None, discovery.target, "fallback", "unroutable")

    provider = providers.get(choice.provider_name)
    # Read once each. `GithubCopilotProvider` rebuilds both sets on every access, and this function used to touch `available_ids` three times per row.
    available = provider.available_ids
    disabled = provider.disabled_ids
    resolution = resolve_against_catalog(
        choice.requested,
        choice.target,
        available=available,
        matched_key=choice.matched_key,
        hops=choice.hops,
    )
    intended = choice.target if choice.target != resolution.resolved else ""

    if not available and not disabled:
        # Nothing has been loaded, so nothing can be said about this model in particular. Distinguished from `absent` because the operator's next move is different: look at credentials and network, not at the model list.
        serviceable: Serviceability = "unknown"
    elif provider.describe(resolution.resolved) is not None:
        serviceable = "yes"
    elif canonical(choice.target) in {canonical(model) for model in disabled}:
        # Folded, like every other model-name comparison here. An operator copying an id out of a 41-line `disabled_models` block may well write `gpt-5-6-terra` for `gpt-5.6-terra`, and an exact match would then answer "not in A's catalogue" — the precise sentence this value exists to stop being said about a model that is in the catalogue.
        serviceable = "disabled"
    else:
        serviceable = "absent"

    return RouteReport(
        name=name,
        provider=provider.name,
        model=resolution.resolved,
        origin=choice.origin,
        serviceable=serviceable,
        intended=intended,
    )


def route_table(
    *,
    providers: ProviderRegistry,
    mappings: Mapping[str, str],
) -> tuple[RouteReport, ...]:
    """The whole route table, one row per name a client could send.

    Recomputed per call rather than cached, and the honest reason is that there is nothing to invalidate against: catalogues are replaced wholesale by `refresh_catalog`, and a cache would need to notice that. Cost is super-linear in the number of candidates — each row rebuilds the mapping index and a canonicalised view of the provider's catalogue — measured 2026-08-27 at 2.5 ms for two 81-entry catalogues and 12 ms for two of 161. Both callers are low-frequency and sit behind the admission gate, which is what makes that acceptable rather than the shape of the loop.
    """
    return tuple(
        _report_for(name, providers=providers, mappings=mappings)
        for name in _candidate_names(providers, mappings)
    )


def decide_route(
    *,
    requested_model: str,
    inbound_format: WireFormat,
    providers: ProviderRegistry,
    mappings: Mapping[str, str],
) -> Route:
    bare_model, explicit_format = split_format_suffix(requested_model)
    choice = choose_provider(bare_model, providers=providers, mappings=mappings)
    provider = providers.get(choice.provider_name)
    resolution = resolve_against_catalog(
        choice.requested,
        choice.target,
        available=provider.available_ids,
        matched_key=choice.matched_key,
        hops=choice.hops,
    )

    descriptor = provider.describe(resolution.resolved)
    if descriptor is None:
        raise UnknownModel(provider.name, resolution.resolved, choice.target)
    if not descriptor.endpoints and not descriptor.unknown_endpoints:
        raise CapabilityMissing(provider.name, descriptor.id)

    if explicit_format is not None:
        endpoint = FORMAT_ENDPOINTS[explicit_format]
        if not descriptor.supports(endpoint):
            raise EndpointNotSupported(provider.name, descriptor.id, endpoint.value)
        reason = "explicit_format"
    else:
        inbound_endpoint = FORMAT_ENDPOINTS[inbound_format]
        if descriptor.supports(inbound_endpoint):
            endpoint = inbound_endpoint
            reason = "inbound_format_supported"
        else:
            endpoint = _first_supported(descriptor.endpoints, provider.name, descriptor.id)
            reason = "translated_to_available_endpoint"

    target_format = ENDPOINT_FORMATS[endpoint]
    return Route(
        provider_name=provider.name,
        model_id=descriptor.id,
        endpoint=endpoint,
        target_format=target_format,
        inbound_format=inbound_format,
        translation_required=target_format is not inbound_format,
        reason=reason,
        resolution=resolution,
        descriptor=descriptor,
        provider_origin=choice.origin,
    )


def _first_supported(
    endpoints: frozenset[ModelEndpoint],
    provider_name: str,
    model_id: str,
) -> ModelEndpoint:
    """Pick a usable endpoint deterministically.

    A fixed order matters more than which one wins.
    The same request must not route differently between processes.
    """
    for candidate in _FALLBACK_ORDER:
        endpoint = FORMAT_ENDPOINTS[candidate]
        if endpoint in endpoints:
            return endpoint
    # Endpoints exist but none has a driver, e.g. only ws:/responses.
    raise EndpointNotSupported(provider_name, model_id, ",".join(sorted(endpoints)))


def apply_route(context: RequestContext, route: Route) -> None:
    context.resolved_model = route.model_id
    context.provider_name = route.provider_name
    context.endpoint = route.endpoint
    context.target_format = route.target_format
    context.translation_required = route.translation_required
    context.route_reason = route.reason
    context.model_descriptor = route.descriptor


def translation_target(provider: ModelProvider, model_id: str) -> TranslationTarget:
    """What the resolved model can do, in the form a writer reads.

    Built from the same descriptor routing used, so the capabilities a translation renders against are the ones the request will actually be sent to. A model the provider does not describe yields the default — no published efforts — which makes a writer decline to render rather than guess, exactly as an absent catalog field does.
    """
    descriptor = provider.describe(model_id)
    if descriptor is None:
        return TranslationTarget(model_id=model_id)
    return TranslationTarget(model_id=model_id, reasoning_efforts=descriptor.reasoning_efforts)
