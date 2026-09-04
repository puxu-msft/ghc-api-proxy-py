"""The non-inference surface the new chain serves.

Written against `Chain` rather than adapted from `app.routes`. Those routers resolve their state through `app.deps`, which reaches the existing chain's settings and runtime, so mounting them here would have pulled that chain back in and undone the separation the module boundaries now assert.

Only what this chain can answer truthfully is here. Readiness is the catalog, because that is what decides whether a request can be served at all; the model list is the catalog routing actually consults, so a client reading it learns what routing will accept.

`/api/status` and `/api/config` were added on 2026-08-22, when that stopped being true of them: readiness is the same question `/health/readiness` already answered, and the configuration snapshot is `Chain`'s own. History still needs state this chain does not own, and is absent rather than answered with a plausible stub. The endpoints `api.md` strikes through — approval, the Responses WebSocket, tokenization — are deliberately not wired.
"""


from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import REGISTRY, generate_latest

from app.core.chain import Chain
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


@router.get("/models")
@router.get("/v1/models")
@router.get("/openai/v1/models")
async def list_models(request: Request) -> JSONResponse:
    """The catalog routing consults, in the OpenAI list shape clients expect.

    Every name a client could send and get served — catalog ids **and** mapping keys, each run through the routing rules. Listing only the default provider's ids was right while routing had only one provider to consult; with two, it hides whatever the second one serves. Listing the union without routing them would do the opposite, promising models that resolve to a provider which does not offer them.

    `owned_by` therefore names the provider that would actually answer, which is the first time it has said anything — it used to be the default provider's name on every row, i.e. a constant. Spec §4.1.
    """
    chain = chain_of(request)
    return JSONResponse(
        {
            "object": "list",
            "data": [
                {"id": row.name, "object": "model", "owned_by": row.provider}
                for row in route_table(
                    providers=chain.providers, mappings=chain.config.model_mappings
                )
                if row.serviceable == "yes"
            ],
        }
    )


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
_XINGCHEN_CREDENTIAL_FIELDS = frozenset({"gateway_api_key", "x_token"})


def _redact_model_provider_credentials(data: dict[str, Any]) -> None:
    raw_providers = data.get("model_providers")
    if not isinstance(raw_providers, dict):
        return
    providers = cast(dict[str, object], raw_providers)
    for raw_provider in providers.values():
        if not isinstance(raw_provider, dict):
            continue
        provider = cast(dict[str, Any], raw_provider)
        if provider.get("type") != "xingchen":
            continue
        for field in _XINGCHEN_CREDENTIAL_FIELDS:
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
