"""FastAPI surface driven by the new pipeline.

Separate from `app_factory`, which still serves the existing implementation.
Mounting both would give one path two owners.
"""

from typing import Any, cast

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.pipeline.delivery import render
from app.server.composition import Chain
from app.server.handler import (
    blocks_from_anthropic,
    deliver_blocks,
    error_body,
    error_status,
    handle,
    response_payload,
)
from app.server.inbound import ROUTES, InboundRequestError, build_context, route_for_path

CHAIN_STATE_KEY = "pipeline_chain"


def _chain(request: Request) -> Chain:
    return cast(Chain, getattr(request.app.state, CHAIN_STATE_KEY))


async def _serve(request: Request) -> Response:
    route = route_for_path(request.url.path)
    if route is None:
        return JSONResponse({"error": {"message": "unknown endpoint"}}, status_code=404)

    try:
        parsed: object = await request.json()
    except ValueError:
        return JSONResponse({"error": {"message": "body is not valid JSON"}}, status_code=400)
    if not isinstance(parsed, dict):
        return JSONResponse({"error": {"message": "body must be an object"}}, status_code=400)
    body = cast(dict[str, Any], parsed)

    try:
        context = build_context(route, body)
    except InboundRequestError as error:
        return JSONResponse(error_body(error), status_code=400)

    try:
        handled = await handle(_chain(request), context)
    except Exception as error:
        return JSONResponse(error_body(error), status_code=error_status(error))

    response = handled.response
    if response is None:
        error = handled.outcome.error or RuntimeError("request produced no response")
        return JSONResponse(error_body(error), status_code=error_status(error))

    chain = _chain(request)
    body = cast(dict[str, Any], response.json())
    payload = response_payload(chain, handled, body)

    if not context.stream:
        return JSONResponse(payload, status_code=response.status_code)

    # Block-level delivery: every block is already complete before a frame is written.
    committed = deliver_blocks(chain, blocks_from_anthropic(payload))
    frames = render(
        committed,
        message_id=str(payload.get("id", context.id)),
        model=str(payload.get("model", context.resolved_model)),
        stop_reason=str(payload.get("stop_reason", "end_turn")),
        usage=cast(dict[str, Any], payload.get("usage", {})),
    )
    return StreamingResponse(
        iter(list(frames)),
        status_code=response.status_code,
        media_type="text/event-stream",
    )


def build_router() -> APIRouter:
    """Register every inbound path, including the OpenAI-compatible prefixes."""
    router = APIRouter()
    seen: set[str] = set()
    for route in ROUTES:
        paths = [route.path]
        if route.wire_format.value.startswith("openai-"):
            paths = [f"{prefix}{route.path}" for prefix in ("", "/v1", "/openai/v1")]
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            router.add_api_route(path, _serve, methods=["POST"])
    return router


def create_pipeline_app(chain: Chain) -> FastAPI:
    app = FastAPI(title="ghc-api-proxy")
    setattr(app.state, CHAIN_STATE_KEY, chain)
    app.include_router(build_router())
    return app
