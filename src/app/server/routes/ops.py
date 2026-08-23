"""The non-inference surface the new chain serves.

Written against `Chain` rather than adapted from `app.routes`. Those routers resolve their state through `app.deps`, which reaches the existing chain's settings and runtime, so mounting them here would have pulled that chain back in and undone the separation the module boundaries now assert.

Only what this chain can answer truthfully is here. Readiness is the catalog, because that is what decides whether a request can be served at all; the model list is the catalog routing actually consults, so a client reading it learns what routing will accept.

`/api/status` and `/api/config` were added on 2026-08-22, when that stopped being true of them: readiness is the same question `/health/readiness` already answered, and the configuration snapshot is `Chain`'s own. History still needs state this chain does not own, and is absent rather than answered with a plausible stub. The endpoints `api.md` strikes through — approval, the Responses WebSocket, tokenization — are deliberately not wired.
"""


from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import REGISTRY, generate_latest

from app.server.app_state import chain_of

router = APIRouter()


@router.get("/health/liveness")
async def liveness() -> JSONResponse:
    """The process is up. Deliberately says nothing about whether it can serve."""
    return JSONResponse({"status": "alive"})


@router.get("/health")
@router.get("/health/readiness")
@router.get("/api/status")
async def readiness(request: Request) -> JSONResponse:
    """Whether a request would be served, judged by the same fact routing uses.

    An empty catalog is not readiness: routing fails closed on capability, so every request would be refused with a message saying the model does not exist. Answering 200 in that state is how a supervisor is told to send traffic to a process that will refuse all of it.

    `/api/status` is the same handler rather than a second one. `api.md` ratifies both paths and says nothing about their bodies, and they ask the same question — the old chain answered `/api/status` from a readiness flag of its own, which is exactly the arrangement where two answers to one question drift apart. The shape follows readiness rather than the old `{ready, checks}` because this chain's answer is the catalog, and a boolean would drop the per-provider detail a supervisor needs to act on.
    """
    chain = chain_of(request)
    providers = {
        name: {"models": len(chain.providers.get(name).available_ids)}
        for name in sorted(chain.providers.names)
    }
    ready = any(entry["models"] for entry in providers.values())
    return JSONResponse(
        {"status": "ready" if ready else "uninitialized", "providers": providers},
        status_code=200 if ready else 503,
    )


@router.get("/models")
@router.get("/v1/models")
@router.get("/openai/v1/models")
async def list_models(request: Request) -> JSONResponse:
    """The catalog routing consults, in the OpenAI list shape clients expect."""
    provider = chain_of(request).providers.default
    return JSONResponse(
        {
            "object": "list",
            "data": [
                {"id": model_id, "object": "model", "owned_by": provider.name}
                for model_id in sorted(provider.available_ids)
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


@router.get("/api/config")
async def config(request: Request) -> JSONResponse:
    """The configuration this process is actually running, as it was resolved.

    The snapshot rather than any file: five layers feed it, so the file alone never answers "what is in effect", and a restart-only key may differ from what the file now says — that gap is precisely what an operator opens this to see.

    `proxy` is the one field redacted, and only its userinfo. The chain this replaces blanked `auth.github_token` and `upstream.api_key`; neither field exists in this schema, and the credential a `ProxyConfig` can still carry is the one embedded in a proxy URL. `github_token_file` names a path, not a token, and is left alone. Base URLs are not treated as credential carriers here — userinfo in them is legal but is not how anyone configures them, and if that turns out to be wrong this is the place that has to grow, not a wider blanket applied on suspicion.
    """
    data = chain_of(request).config.model_dump(mode="json")
    proxy = data.get("proxy")
    if isinstance(proxy, str):
        data["proxy"] = _without_credentials(proxy)
    return JSONResponse(data)
