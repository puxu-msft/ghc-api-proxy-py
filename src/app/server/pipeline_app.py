"""FastAPI surface driven by the new pipeline.

Separate from `app_factory`, which still serves the existing implementation.
Mounting both would give one path two owners.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

import anyio
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.pipeline.delivery.stream import stream_delivery
from app.server.composition import Chain, refresh_catalogs
from app.server.handler import (
    assembler_for,
    delivery_buffer,
    error_body,
    error_headers,
    error_status,
    handle_bounded,
    handle_count_tokens,
    response_payload,
    stream_settings,
)
from app.server.inbound import ROUTES, InboundRequestError, build_context, route_for_path

CHAIN_STATE_KEY = "pipeline_chain"

# What the calibrator has learnt is only worth keeping if it survives the process.
# Not configurable: `config.example.yaml` has no `tokenization` section to put it in.
TOKENIZATION_FLUSH_SECONDS = 5.0


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
        context = build_context(route, body, request.headers)
    except InboundRequestError as error:
        return JSONResponse(error_body(error), status_code=400)

    if route.count_tokens:
        # Answered here rather than driven: the reply is a count, not an upstream response to
        # deliver, so none of the block buffering below applies to it.
        try:
            counted = await handle_count_tokens(_chain(request), context)
        except Exception as error:
            return JSONResponse(
            error_body(error),
            status_code=error_status(error),
            headers=error_headers(error),
        )
        return JSONResponse(counted)

    try:
        handled = await handle_bounded(_chain(request), context)
    except Exception as error:
        return JSONResponse(
            error_body(error),
            status_code=error_status(error),
            headers=error_headers(error),
        )

    response = handled.response
    if response is None:
        error = handled.outcome.error or RuntimeError("request produced no response")
        return JSONResponse(
            error_body(error),
            status_code=error_status(error),
            headers=error_headers(error),
        )

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
    app = FastAPI(title="ghc-api-proxy", lifespan=_lifespan)
    setattr(app.state, CHAIN_STATE_KEY, chain)
    app.include_router(build_router())
    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Carry the calibrator's state across restarts.

    Without this the `local` token counter starts from nothing every time and throws away
    everything it learns, which makes its estimates worse the more the process is restarted —
    and says nothing about it, because an estimate is still returned.
    """
    chain = cast(Chain, getattr(app.state, CHAIN_STATE_KEY))
    # Routing fails closed on capability, so until this runs the catalog is empty and every request
    # is refused. Done before accepting rather than lazily: a request that arrives first would
    # otherwise get a refusal that says the model does not exist.
    await refresh_catalogs(chain)
    await chain.tokenization.load()
    async with anyio.create_task_group() as flushing:
        flushing.start_soon(chain.tokenization.run_periodic_flush, TOKENIZATION_FLUSH_SECONDS)
        try:
            yield
        finally:
            # The periodic flush cannot be relied on to have caught the last change.
            await chain.tokenization.flush()
            flushing.cancel_scope.cancel()
