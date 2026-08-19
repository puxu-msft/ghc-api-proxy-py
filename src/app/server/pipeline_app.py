"""FastAPI surface driven by the new pipeline.

Separate from `app_factory`, which still serves the existing implementation.
Mounting both would give one path two owners.
"""

import os
import time
from collections.abc import AsyncGenerator
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any, cast

import anyio
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.observability.logging import get_logger
from app.observability.request_log import (
    RequestLine,
    format_arrival_line,
    format_completion_line,
    status_for,
)
from app.observability.tui import footer_tui_or_none
from app.pipeline.delivery.assembler import BlockAssembler
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
from app.server.ops_routes import router as ops_router

CHAIN_STATE_KEY = "pipeline_chain"

# The logger every per-request line goes under. Named so a filter, a test or a log shipper can select this process's own lines out of a stream that also carries `httpx` and `uvicorn` — a substring match on the message cannot, because `httpx` narrates every upstream call with the same path in it.
REQUEST_LOGGER = "app.request"

# What the calibrator has learnt is only worth keeping if it survives the process.
# Not configurable: `config.example.yaml` has no `tokenization` section to put it in.
TOKENIZATION_FLUSH_SECONDS = 5.0


def _chain(request: Request) -> Chain:
    return cast(Chain, getattr(request.app.state, CHAIN_STATE_KEY))


@dataclass(slots=True)
class _Trace:
    """What is known about a request as it goes, gathered for its log line.

    Mutable and filled in as routing learns things, because the line is written at the end but its fields become known at four different points. A frozen record would mean rebuilding it at each one.
    """

    method: str
    path: str
    inbound_format: str = ""
    requested_model: str = ""
    model: str = ""
    attempts: int = 1
    detail: str = ""
    started: float = 0.0
    bytes_in: int | None = None
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    stop_reason: str = ""


def _log_completion(chain: Chain, trace: _Trace, status_code: int | None, *, bytes_out: int | None) -> None:
    """Write the one line that says this request happened.

    Emitted here rather than inside the handler because every exit path — a rejected body, a routing refusal, an upstream failure, a delivered answer — has to produce exactly one, and the handler has a return for each of them.
    """
    line = RequestLine(
        method=trace.method,
        path=trace.path,
        inbound_format=trace.inbound_format,
        requested_model=trace.requested_model,
        model=trace.model,
        status_code=status_code,
        duration_s=time.monotonic() - trace.started,
        bytes_in=trace.bytes_in,
        bytes_out=bytes_out,
        usage=trace.usage,
        stop_reason=trace.stop_reason,
        attempts=trace.attempts,
        detail=trace.detail,
    )
    get_logger(REQUEST_LOGGER).info(
        format_completion_line(line, unicode=chain.capabilities.unicode),
        status=status_for(status_code, failed=False),
    )


async def _serve(request: Request) -> Response:
    """Time the request, hand it to the dispatcher, and account for it on the way out.

    A streaming response is left alone here: at this point it has produced no bytes and its own generator is what knows when it finished and how much went out, so it writes its own completion line.
    """
    chain = _chain(request)
    trace = _Trace(method=request.method, path=request.url.path, started=time.monotonic())
    # Off by default, the way `copilot-api-js` treats its arrival line: on a busy proxy it doubles the log for information the completion line repeats.
    get_logger(REQUEST_LOGGER).debug(format_arrival_line(RequestLine(method=trace.method, path=trace.path)), status="pending")

    response = await _dispatch(request, chain, trace)
    if not isinstance(response, StreamingResponse):
        # Read off the rendered response rather than recomputed from the payload, so it is the count of what actually goes on the wire and so every non-streaming exit — including the error ones, which have no payload to measure — reports one. Leaving this `None` is why rejected requests used to show no byte field at all.
        body = getattr(response, "body", None)
        _log_completion(chain, trace, response.status_code, bytes_out=len(body) if isinstance(body, bytes) else None)
    return response


async def _dispatch(request: Request, chain: Chain, trace: _Trace) -> Response:
    route = route_for_path(request.url.path)
    if route is None:
        return JSONResponse({"error": {"message": "unknown endpoint"}}, status_code=404)
    trace.inbound_format = route.wire_format.value
    # Starlette caches the body it already read for `json()`, so this is a length, not a second read.
    trace.bytes_in = len(await request.body())

    try:
        parsed: object = await request.json()
    except ValueError:
        trace.detail = "body is not valid JSON"
        return JSONResponse({"error": {"message": "body is not valid JSON"}}, status_code=400)
    if not isinstance(parsed, dict):
        trace.detail = "body must be an object"
        return JSONResponse({"error": {"message": "body must be an object"}}, status_code=400)
    body = cast(dict[str, Any], parsed)

    try:
        context = build_context(route, body, request.headers)
    except InboundRequestError as error:
        trace.detail = str(error)
        return JSONResponse(error_body(error), status_code=400)

    active = chain.active_requests
    # Registered before routing, so the footer shows the request as `(resolving)` from the moment it arrives rather than only once its model is known. Everything below must leave through `_release`, except the streaming branch, which hands the registration to the generator instead.
    active.add(context.id)
    released = False

    def _release() -> None:
        nonlocal released
        if not released:
            released = True
            active.remove(context.id)

    try:
        if route.count_tokens:
            # Answered here rather than driven: the reply is a count, not an upstream response to
            # deliver, so none of the block buffering below applies to it.
            try:
                counted = await handle_count_tokens(chain, context)
            except Exception as error:
                trace.detail = str(error)
                return JSONResponse(
                    error_body(error),
                    status_code=error_status(error),
                    headers=error_headers(error),
                )
            return JSONResponse(counted)

        try:
            handled = await handle_bounded(chain, context)
        except Exception as error:
            trace.model = context.resolved_model
            trace.attempts = context.attempt_count
            trace.detail = str(error)
            return JSONResponse(
                error_body(error),
                status_code=error_status(error),
                headers=error_headers(error),
            )
        active.set_model(context.id, context.resolved_model)
        active.set_attempts(context.id, context.attempt_count)
        trace.model = context.resolved_model
        trace.requested_model = context.requested_model
        trace.attempts = context.attempt_count

        response = handled.response
        if response is None:
            error = handled.outcome.error or RuntimeError("request produced no response")
            trace.detail = str(error)
            return JSONResponse(
                error_body(error),
                status_code=error_status(error),
                headers=error_headers(error),
            )

        if context.stream:
            # Block-level delivery over the live upstream.
            # The body is never read whole here, so a block goes out while the rest still arrives.
            #
            # The registration deliberately outlives this function. A streaming request has produced nothing at the moment the handler returns — the body is consumed after — so releasing here would drop it off the footer at exactly the point it becomes worth watching.
            released = True
            # Held rather than passed straight through: the assembler is what reads the upstream's terminal event, so after the stream finishes it is the only thing that knows the token usage and the stop reason.
            assembler = assembler_for(handled)
            accounting = _StreamAccounting(
                chain=chain,
                request_id=context.id,
                trace=trace,
                status_code=response.status_code,
                assembler=assembler,
            )
            return _AccountedStreamingResponse(
                _tracked_delivery(
                    stream_delivery(
                        response.aiter_bytes(),
                        assembler,
                        buffer=delivery_buffer(chain),
                        settings=stream_settings(chain),
                        message_id=context.id,
                        model=context.resolved_model,
                    ),
                    accounting,
                ),
                accounting,
                status_code=response.status_code,
                media_type="text/event-stream",
            )

        body = cast(dict[str, Any], response.json())
        payload = response_payload(chain, handled, body)
        # Taken from what goes downstream rather than from the upstream body, so the numbers on the line are the ones the client was actually told.
        usage = payload.get("usage")
        if isinstance(usage, dict):
            trace.usage = dict(cast(dict[str, Any], usage))
        stop_reason = payload.get("stop_reason")
        if isinstance(stop_reason, str):
            trace.stop_reason = stop_reason
        return JSONResponse(payload, status_code=response.status_code)
    finally:
        _release()


@dataclass(slots=True)
class _StreamAccounting:
    """One streaming request's slot in the footer and its eventual log line.

    Shared by the delivery generator and the response that carries it, because either one may be the last to run. `finish` is idempotent so whichever gets there first records, and the other is a no-op.
    """

    chain: Chain
    request_id: str
    trace: _Trace
    status_code: int
    assembler: BlockAssembler | None = None
    sent: int = 0
    done: bool = False

    def count(self, size: int) -> None:
        self.sent += size
        self.chain.active_requests.add_bytes(self.request_id, size)

    def finish(self) -> None:
        if self.done:
            return
        self.done = True
        self.chain.active_requests.remove(self.request_id)
        # Read at the end because that is when the upstream's terminal event has been seen. `seen` guards against reporting the assembler's defaults — `end_turn` and no usage — for a stream that was cut off before its final frame, which would claim a clean finish for a request that had none.
        if self.assembler is not None and self.assembler.terminal.seen:
            self.trace.usage = dict(self.assembler.terminal.usage)
            self.trace.stop_reason = self.assembler.terminal.stop_reason
        _log_completion(self.chain, self.trace, self.status_code, bytes_out=self.sent)


class _AccountedStreamingResponse(StreamingResponse):
    """A streaming response that is accounted for even if its body never runs.

    The generator's own `finally` covers every case where delivery started, including a mid-stream disconnect. It does **not** cover a client that disappears before the first chunk is pulled: an async generator that was never iterated has no suspended frame, so closing it runs nothing, and the request would sit in the footer for the life of the process with its clock climbing and no log line ever written. A review reproduced exactly that by failing the `http.response.start` send.

    Overriding `__call__` puts a `finally` outside everything the framework does, which is the only place that survives a failure before the first iteration.
    """

    def __init__(self, content: AsyncGenerator[bytes], accounting: _StreamAccounting, **kwargs: Any) -> None:
        super().__init__(content, **kwargs)
        self._accounting = accounting

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._accounting.finish()


async def _tracked_delivery(chunks: AsyncGenerator[bytes], accounting: _StreamAccounting) -> AsyncGenerator[bytes]:
    """Pass the delivery stream through untouched, counting what goes out and accounting for it at the end.

    Wrapping rather than instrumenting `stream_delivery`: byte accounting is an observability concern, and threading it into the delivery layer would put a display detail on the path that decides what the client receives. The bytes are forwarded object-identical, so block boundaries are preserved.

    `finally` rather than a trailing statement, because a client that disconnects mid-stream cancels this generator — and a request that vanishes from the footer, or never gets its log line, only when something has gone wrong is exactly backwards.
    """
    try:
        async for chunk in chunks:
            accounting.count(len(chunk))
            yield chunk
    finally:
        accounting.finish()


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
    # Health, the model list and metrics. A supervisor that cannot ask whether the process is
    # ready has to guess, and the inference routes alone give it nothing to ask.
    app.include_router(ops_router)
    return app


def _version() -> str:
    """The installed version, or `unknown` when there is no installed distribution to ask.

    Never raises. Running from a source tree that was never installed is an ordinary way to run this, and a banner line is the last thing that should be able to stop the server from starting — which it did, until the lookup was given the wrong distribution name and took the whole lifespan down with it.
    """
    try:
        return version("app")
    except PackageNotFoundError:
        return "unknown"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Carry the calibrator's state across restarts.

    Without this the `local` token counter starts from nothing every time and throws away
    everything it learns, which makes its estimates worse the more the process is restarted —
    and says nothing about it, because an estimate is still returned.
    """
    chain = cast(Chain, getattr(app.state, CHAIN_STATE_KEY))
    logger = get_logger()
    logger.info(f"ghc-api-proxy v{_version()} pid={os.getpid()}", status="ok")
    # Attempted before accepting, because routing fails closed on capability: a request arriving
    # first would otherwise be refused with a message saying the model does not exist.
    #
    # Not fatal, though. A supervised service that cannot reach upstream at boot — no credential
    # yet, network not up — must still start and say it is not ready, which is what
    # `/health/readiness` answers from the same empty catalog. Raising here instead turns a
    # degraded start into a service that never comes up at all, and the socket systemd already
    # opened would hold the client's connection open against a process that is dying.
    try:
        await refresh_catalogs(chain)
    except Exception as error:
        logger.warning(f"model catalog unavailable, serving as not-ready: {error}", status="fail")
    else:
        provider = chain.providers.get(chain.providers.default_name)
        logger.info(f"{len(provider.available_ids)} models available from {chain.providers.default_name}", status="ok")
    await chain.tokenization.load()
    # Said before the listener is announced by whoever owns it, so the operator sees which upstream and which port belong together even when the two lines come from different layers.
    logger.info(f"listening on http://{chain.config.server.host}:{chain.config.server.port}", status="ok")
    # Probed, not configured: whether a live footer belongs on this stream is a fact about where the output goes, and the process can see that for itself. Nothing is logged when it comes back unsupported — a pipe or a CI job is the normal case, not a degradation worth a line in everybody's log.
    tui = footer_tui_or_none(chain.active_requests, chain.capabilities)
    async with anyio.create_task_group() as flushing:
        flushing.start_soon(chain.tokenization.run_periodic_flush, TOKENIZATION_FLUSH_SECONDS)
        try:
            with ExitStack() as terminal:
                if tui is not None:
                    terminal.enter_context(tui.activate())
                yield
        finally:
            # The periodic flush cannot be relied on to have caught the last change.
            await chain.tokenization.flush()
            flushing.cancel_scope.cancel()
