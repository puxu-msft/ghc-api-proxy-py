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
    ModelEndpoint,
    ModelProvider,
    UnknownModel,
)
from app.pipeline.model_resolution import ModelResolution, resolve_model
from app.pipeline.request import ENDPOINT_FORMATS, FORMAT_ENDPOINTS, WireFormat

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


def split_format_suffix(name: str) -> tuple[str, WireFormat | None]:
    """Split `model@format`, returning the bare model and the named format.

    An unrecognised format after `@` is an error rather than part of the model name.
    Treating it as a name would send a request the operator never asked for.
    """
    if FORMAT_SEPARATOR not in name:
        return name, None
    model, _, suffix = name.rpartition(FORMAT_SEPARATOR)
    if not model:
        return name, None
    try:
        return model, WireFormat(suffix)
    except ValueError:
        raise RoutingError(f"unknown target format {suffix!r} in {name!r}") from None


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
