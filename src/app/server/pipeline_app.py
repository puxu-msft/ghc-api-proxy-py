"""FastAPI surface driven by the new pipeline.

Separate from `app_factory`, which still serves the existing implementation.
Mounting both would give one path two owners.
"""

from typing import Any, cast

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.pipeline.delivery.stream import stream_delivery
from app.server.composition import Chain
from app.server.handler import (
    assembler_for,
    delivery_buffer,
    error_body,
    error_status,
    handle_bounded,
    response_payload,
    stream_settings,
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
        handled = await handle_bounded(_chain(request), context)
    except Exception as error:
        return JSONResponse(error_body(error), status_code=error_status(error))

    response = handled.response
    if response is None:
        error = handled.outcome.error or RuntimeError("request produced no response")
        return JSONResponse(error_body(error), status_code=error_status(error))

    chain = _chain(request)
    if context.stream:
        # Block-level delivery over the live upstream.
        # The body is never read whole here, so a block goes out while the rest still arrives.
        return StreamingResponse(
            stream_delivery(
                response.aiter_bytes(),
                assembler_for(handled),
                buffer=delivery_buffer(chain),
                settings=stream_settings(chain),
                message_id=context.id,
                model=context.resolved_model,
            ),
            status_code=response.status_code,
            media_type="text/event-stream",
        )

    body = cast(dict[str, Any], response.json())
    payload = response_payload(chain, handled, body)
    return JSONResponse(payload, status_code=response.status_code)


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
