"""Routing: which provider, which model, which endpoint, and whether to translate.

`docs/.human-controlled/request-pipeline.md` calls this the pipeline's first task.
Decide whether the inbound format and the model's endpoint differ, and so whether to translate.

A model may name its target format explicitly as `model@format`.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.model_provider import (
    CapabilityMissing,
    EndpointNotSupported,
    ModelDescriptor,
    ModelEndpoint,
    ModelProvider,
    UnknownModel,
)
from app.pipeline.model_resolution import ModelResolution, resolve_model
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


def decide_route(
    *,
    requested_model: str,
    inbound_format: WireFormat,
    provider: ModelProvider,
    mappings: Mapping[str, str],
) -> Route:
    bare_model, explicit_format = split_format_suffix(requested_model)
    resolution = resolve_model(
        bare_model,
        mappings=mappings,
        available=provider.available_ids,
    )

    descriptor = provider.describe(resolution.resolved)
    if descriptor is None:
        raise UnknownModel(provider.name, resolution.resolved)
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
