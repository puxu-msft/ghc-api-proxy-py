"""The non-inference surface the new chain serves.

Written against `Chain` rather than adapted from `app.routes`. Those routers resolve their state through `app.deps`, which reaches the existing chain's settings and runtime, so mounting them here would have pulled that chain back in and undone the separation the module boundaries now assert.

Only what this chain can answer truthfully is here. Readiness is the catalog, because that is what decides whether a request can be served at all; the model list is the catalog routing actually consults, so a client reading it learns what routing will accept.

`/api/status` and `/api/config` were added on 2026-08-22, when that stopped being true of them: readiness is the same question `/health/readiness` already answered, and the configuration snapshot is `Chain`'s own. History still needs state this chain does not own, and is absent rather than answered with a plausible stub. The endpoints `api.md` strikes through — approval, the Responses WebSocket, tokenization — are deliberately not wired.
"""


from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import REGISTRY, generate_latest

from app.config.schema import GithubCopilotProviderConfig
from app.core.chain import Chain
from app.model_provider.base import ModelProvider
from app.model_provider.copilot_pricing import pricing_for
from app.pipeline.model_resolution import canonical
from app.pipeline.routing import route_table
from app.server.app_state import chain_of

router = APIRouter()


@router.get("/health/liveness")
async def liveness() -> JSONResponse:
    """The process is up. Deliberately says nothing about whether it can serve."""
    return JSONResponse({"status": "alive"})


def _is_ready(chain: Chain) -> bool:
    """Whether traffic should be sent here at all.

    **The default provider's catalog, not any provider's.** `any(...)` was right while one provider existed and lies as soon as two do: with default=B and B's catalog unloaded, a healthy A makes `any` answer 200 while every request that names no qualifier — which is nearly all of them — dies as `UnknownModel`. `all(...)` errs the other way, retiring the whole instance because a secondary upstream is down, when only requests explicitly qualified to it are affected. Spec §4.3.

    One function, read by both `/health/readiness` and `/api/status`'s `ready` field. Splitting the handlers was safe (see the module docstring); splitting the *judgement* would reintroduce the drift that keeping them as one handler was avoiding.
    """
    return bool(chain.providers.default.available_ids)


@router.get("/health")
@router.get("/health/readiness")
async def readiness(request: Request) -> JSONResponse:
    """Whether a request would be served, judged by the fact routing depends on.

    An empty catalog is not readiness: routing fails closed on capability, so every request would be refused with a message saying the model does not exist. Answering 200 in that state is how a supervisor is told to send traffic to a process that will refuse all of it.

    `/api/status` used to be this same handler. It is not any more — `api.md` files it under "状态与配置" rather than under health checks, and once more than one provider can be configured there is a great deal of status to report that has nothing to do with readiness. Splitting also settles an inconsistency that went unnoticed while they were one: `admission.py`'s `UNGATED_PATHS` exempts `/health/readiness` and not `/api/status`, so the same handler was reachable both inside and outside the admission gate.
    """
    chain = chain_of(request)
    ready = _is_ready(chain)
    return JSONResponse(
        {
            "status": "ready" if ready else "uninitialized",
            "default_model_provider": chain.providers.default_name,
            "models": len(chain.providers.default.available_ids),
        },
        status_code=200 if ready else 503,
    )


@router.get("/api/status")
async def status(request: Request) -> JSONResponse:
    """What this process resolved the configuration to, and what it can serve right now.

    The division of labour with `/api/config` is that the other one reports the configuration's fields as they were resolved — what is written down — while this reports what those fields *mean* once the catalogs are in hand. `claude-opus-4.8: A/claude-opus-5` appears verbatim there and as a resolved route here.

    Always 200. Readiness moved out to `/health/readiness`; a status document that refuses to be read when the news is bad is a status document nobody can use.
    """
    chain = chain_of(request)

    providers: dict[str, Any] = {}
    for name in sorted(chain.providers.names):
        provider = chain.providers.get(name)
        available = provider.available_ids
        disabled = provider.disabled_ids
        providers[name] = {
            # `models` is what is usable; `disabled` is what the catalog carries but this deployment switched off. They sum to the catalog's size. Spec §4.2.3.
            "models": len(available),
            "disabled": len(disabled),
            "base_url": provider.base_url,
            "catalog": "ok" if available or disabled else "empty",
            "catalog_refreshed_at": provider.catalog_refreshed_at or None,
        }

    routes: dict[str, Any] = {}
    for row in route_table(providers=chain.providers, mappings=chain.config.model_mappings):
        entry: dict[str, Any] = {
            "provider": row.provider,
            "model": row.model,
            "origin": row.origin,
            "serviceable": row.serviceable,
        }
        if row.intended:
            # Only when the chain's target and the name that would actually be sent disagree — i.e. the mapping was abandoned and resolution fell back to the client's own name. Present rather than always-on because an always-on field that usually equals its neighbour trains readers to skip it.
            entry["intended"] = row.intended
        routes[row.name] = entry

    return JSONResponse(
        {
            "ready": _is_ready(chain),
            "default_model_provider": chain.providers.default_name,
            "fallback_model_provider": chain.providers.fallback_name or None,
            "providers": providers,
            "routes": routes,
        }
    )


def _requested_model_format(request: Request) -> str | None:
    requested = request.query_params.get("format", "openai").lower()
    if requested in {"openai", "pi"}:
        return requested
    return None


def _invalid_model_format() -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "type": "invalid_request_error",
                "message": "format must be either 'openai' or 'pi'",
                "param": "format",
                "code": None,
            }
        },
        status_code=400,
    )


def _upstream_metadata(provider: ModelProvider, model_id: str) -> dict[str, Any]:
    entries = provider.raw_catalog.get("data")
    if not isinstance(entries, list):
        return {}
    for entry in cast(list[Any], entries):
        if not isinstance(entry, dict):
            continue
        model = cast(dict[str, Any], entry)
        if model.get("id") == model_id:
            return dict(model)
    return {}


def _model_entries(chain: Chain, *, provider_name: str | None = None) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = []
    for row in route_table(
        providers=chain.providers, mappings=chain.config.model_mappings
    ):
        if row.serviceable != "yes":
            continue
        if row.provider is None:
            raise RuntimeError(f"serviceable model {row.name!r} has no provider")
        if provider_name is not None and row.provider != provider_name:
            continue
        provider = chain.providers.get(row.provider)
        entry = _upstream_metadata(provider, row.model)
        entry.update({"id": row.name, "object": "model", "owned_by": row.provider})
        provider_config = chain.config.model_providers.get(row.provider)
        if isinstance(provider_config, GithubCopilotProviderConfig):
            pricing = pricing_for(row.model)
            if pricing is not None:
                entry["copilot_pricing"] = pricing
                entry.setdefault("pricing", pricing)
        data.append(entry)
    return data


def _pi_number(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _string_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, Any], value)
    return {}


def _pi_cost(entry: dict[str, Any]) -> dict[str, int | float] | None:
    pricing = _string_mapping(entry.get("copilot_pricing", entry.get("pricing")))
    if not pricing:
        return None
    names = {
        "input": ("input",),
        "output": ("output",),
        "cacheRead": (
            "cacheRead",
            "cached_input",
            "cache_read",
            "cache_read_input_tokens",
        ),
        "cacheWrite": ("cacheWrite", "cache_write", "cache_creation_input_tokens"),
    }

    def rates(value: Mapping[str, Any]) -> dict[str, int | float] | None:
        result: dict[str, int | float] = {}
        for target, candidates in names.items():
            for candidate in candidates:
                number = _pi_number(value.get(candidate))
                if number is not None:
                    result[target] = number
                    break
        return result if len(result) == len(names) else None

    raw_tiers = pricing.get("tiers")
    if isinstance(raw_tiers, list):
        tiers = [_string_mapping(tier) for tier in cast(list[Any], raw_tiers)]
        tiers = [tier for tier in tiers if tier]
        if not tiers:
            return None
        base = next(
            (tier for tier in tiers if tier.get("name") == "default"),
            tiers[0],
        )
        base_rates = rates(base)
        if base_rates is None:
            return None
        cost: dict[str, Any] = dict(base_rates)
        converted_tiers: list[dict[str, Any]] = []
        for tier in tiers:
            if tier is base:
                continue
            minimum = tier.get("input_min_tokens")
            tier_rates = rates(tier)
            if type(minimum) is not int or minimum <= 0 or tier_rates is None:
                return None
            converted_tiers.append(
                {"inputTokensAbove": minimum - 1, **tier_rates}
            )
        if converted_tiers:
            cost["tiers"] = converted_tiers
        return cost

    direct_cost = rates(pricing)
    return direct_cost


def _pi_api(entry: dict[str, Any]) -> str | None:
    endpoints = entry.get("supported_endpoints")
    if not isinstance(endpoints, list):
        return None
    for endpoint, api in (
        ("/responses", "openai-responses"),
        ("/v1/messages", "anthropic-messages"),
        ("/chat/completions", "openai-completions"),
    ):
        if endpoint in endpoints:
            return api
    return None


def _pi_model(entry: dict[str, Any]) -> dict[str, Any]:
    capabilities_dict = _string_mapping(entry.get("capabilities"))
    supports_dict = _string_mapping(capabilities_dict.get("supports"))
    limits_dict = _string_mapping(capabilities_dict.get("limits"))

    model_id = cast(str, entry["id"])
    reasoning_effort = supports_dict.get("reasoning_effort")
    enabled_efforts = (
        {
            value
            for value in cast(list[Any], reasoning_effort)
            if isinstance(value, str) and value != "none"
        }
        if isinstance(reasoning_effort, list)
        else set[str]()
    )
    reasoning = supports_dict.get("adaptive_thinking") is True or (
        bool(enabled_efforts)
    )
    result: dict[str, Any] = {
        "id": model_id,
        "name": entry.get("name") if isinstance(entry.get("name"), str) else model_id,
        "reasoning": reasoning,
        "input": ["text", "image"] if supports_dict.get("vision") is True else ["text"],
    }
    api = _pi_api(entry)
    if api is not None:
        result["api"] = api
    for source, target in (
        ("max_context_window_tokens", "contextWindow"),
        ("max_output_tokens", "maxTokens"),
    ):
        value = limits_dict.get(source)
        if type(value) is int and value > 0:
            result[target] = value
    cost = _pi_cost(entry)
    if cost is not None:
        result["cost"] = cost
    if supports_dict.get("adaptive_thinking") is True and api == "anthropic-messages":
        result["compat"] = {"forceAdaptiveThinking": True}
    return result


@router.get("/models")
@router.get("/v1/models")
@router.get("/openai/v1/models")
async def list_models(request: Request) -> JSONResponse:
    """The catalog routing consults, in the OpenAI list shape clients expect.

    Every name a client could send and get served — catalog ids **and** mapping keys, each run through the routing rules. Listing only the default provider's ids was right while routing had only one provider to consult; with two, it hides whatever the second one serves. Listing the union without routing them would do the opposite, promising models that resolve to a provider which does not offer them.

    `owned_by` therefore names the provider that would actually answer, which is the first time it has said anything — it used to be the default provider's name on every row, i.e. a constant. Spec §4.1.
    """
    chain = chain_of(request)
    model_format = _requested_model_format(request)
    if model_format is None:
        return _invalid_model_format()
    data = _model_entries(chain, provider_name=request.query_params.get("provider"))
    if model_format == "pi":
        data = [_pi_model(entry) for entry in data]

    return JSONResponse(
        {
            "object": "list",
            "data": data,
        }
    )


@router.get("/models/{model:path}")
@router.get("/v1/models/{model:path}")
@router.get("/openai/v1/models/{model:path}")
async def retrieve_model(model: str, request: Request) -> JSONResponse:
    """Retrieve one routed model in OpenAI or Pi's model shape."""
    if not model:
        return await list_models(request)
    model_format = _requested_model_format(request)
    if model_format is None:
        return _invalid_model_format()
    requested_model = canonical(model)
    entry = next(
        (
            candidate
            for candidate in _model_entries(chain_of(request))
            if canonical(cast(str, candidate["id"])) == requested_model
        ),
        None,
    )
    if entry is None:
        return JSONResponse(
            {
                "error": {
                    "type": "invalid_request_error",
                    "message": f"The model '{model}' does not exist",
                    "param": "model",
                    "code": "model_not_found",
                }
            },
            status_code=404,
        )
    return JSONResponse(_pi_model(entry) if model_format == "pi" else entry)


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type="text/plain; version=0.0.4")


def _without_credentials(url: str) -> str:
    """The same URL with any userinfo replaced.

    Only the userinfo goes: which proxy is in use is the thing an operator reads this to check, and blanking the whole value would answer a different question.
    """
    if not url:
        return url
    parsed = urlsplit(url)
    if parsed.username is None and parsed.password is None:
        return url
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, f"***@{host}", parsed.path, parsed.query, parsed.fragment))


_CREDENTIAL_REDACTION = "***"
_PROVIDER_CREDENTIAL_FIELDS = {
    "sub2api": frozenset({"api_key"}),
    "xingchen": frozenset({"gateway_api_key", "x_token"}),
}


def _redact_model_provider_credentials(data: dict[str, Any]) -> None:
    raw_providers = data.get("model_providers")
    if not isinstance(raw_providers, dict):
        return
    providers = cast(dict[str, object], raw_providers)
    for raw_provider in providers.values():
        if not isinstance(raw_provider, dict):
            continue
        provider = cast(dict[str, Any], raw_provider)
        provider_type = provider.get("type")
        fields = (
            _PROVIDER_CREDENTIAL_FIELDS.get(provider_type)
            if isinstance(provider_type, str)
            else None
        )
        if fields is None:
            continue
        for field in fields:
            if field in provider:
                provider[field] = _CREDENTIAL_REDACTION


@router.get("/api/config")
async def config(request: Request) -> JSONResponse:
    """The configuration this process is actually running, as it was resolved.

    The snapshot rather than any file: five layers feed it, so the file alone never answers "what is in effect", and a restart-only key may differ from what the file now says — that gap is precisely what an operator opens this to see.

    Proxy userinfo and the two credential values carried by an Xingchen provider are redacted at this presentation boundary. Provider names, base URLs, static models and device/install identity stay visible because they answer the diagnostic question this endpoint exists for.
    """
    data = chain_of(request).config.model_dump(mode="json")
    proxy = data.get("proxy")
    if isinstance(proxy, str):
        data["proxy"] = _without_credentials(proxy)
    _redact_model_provider_credentials(data)
    return JSONResponse(data)
