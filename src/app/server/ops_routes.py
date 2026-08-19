"""The non-inference surface the new chain serves.

Written against `Chain` rather than adapted from `app.routes`. Those routers resolve their state
through `app.deps`, which reaches the existing chain's settings and runtime, so mounting them here
would have pulled that chain back in and undone the separation the module boundaries now assert.

Only what this chain can answer truthfully is here. Readiness is the catalog, because that is what
decides whether a request can be served at all; the model list is the catalog routing actually
consults, so a client reading it learns what routing will accept. History and the management API
need state this chain does not own yet, and are absent rather than answered with a plausible stub.
"""

from typing import cast

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import REGISTRY, generate_latest

from app.server.composition import Chain

CHAIN_STATE_KEY = "pipeline_chain"

router = APIRouter()


def _chain(request: Request) -> Chain:
    return cast(Chain, getattr(request.app.state, CHAIN_STATE_KEY))


@router.get("/health/liveness")
async def liveness() -> JSONResponse:
    """The process is up. Deliberately says nothing about whether it can serve."""
    return JSONResponse({"status": "alive"})


@router.get("/health")
@router.get("/health/readiness")
async def readiness(request: Request) -> JSONResponse:
    """Whether a request would be served, judged by the same fact routing uses.

    An empty catalog is not readiness: routing fails closed on capability, so every request would
    be refused with a message saying the model does not exist. Answering 200 in that state is how
    a supervisor is told to send traffic to a process that will refuse all of it.
    """
    chain = _chain(request)
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
    provider = _chain(request).providers.default
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
