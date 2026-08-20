"""FastAPI surface driven by the new pipeline.

Separate from `app_factory`, which still serves the existing implementation.
Mounting both would give one path two owners.
"""

import os
import sys
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import ExitStack, aclosing, asynccontextmanager
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any, cast
from uuid import uuid4

import anyio
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.observability.logging import get_logger
from app.observability.request_log import (
    LogStatus,
    RequestLine,
    format_arrival_line,
    format_completion_line,
    http_label,
    status_for,
)
from app.observability.tui import footer_tui_or_none
from app.pipeline.delivery.assembler import BlockAssembler, ReplyDialect, Terminal
from app.pipeline.delivery.stream import stream_delivery
from app.pipeline.request import RequestContext
from app.server.admission import InFlightLimit
from app.server.composition import Chain, refresh_catalogs
from app.server.handler import (
    assembler_for,
    delivery_buffer,
    error_body,
    error_headers,
    error_status,
    handle_bounded,
    handle_count_tokens,
    reply_summary,
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
    request_id: str = ""
    inbound_format: str = ""
    client_protocol: str = ""
    upstream_protocol: str = ""
    requested_model: str = ""
    model: str = ""
    attempts: int = 1
    detail: str = ""
    # What the HTTP status cannot say. A streaming status is fixed the moment the response headers arrive, so everything that happens over the next several minutes — the stream stopping mid-turn, upstream tearing, the client leaving — leaves it at 200. `None` means the status code is the whole story.
    status_override: LogStatus | None = None
    started: float = 0.0
    bytes_in: int | None = None
    received: int = 0
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    stop_reason: str = ""
    tools: tuple[str, ...] = ()
    thinking: tuple[str, ...] = ()
    dialect: ReplyDialect = ReplyDialect.ANTHROPIC

    def absorb(self, reply: Terminal) -> None:
        """Take the aggregated reply record onto the line.

        One call rather than four assignments at each of the two delivery paths, so a field added to the record reaches the line without either path being edited — and, more to the point, so neither path can decide for itself what "the tools this turn asked for" means.
        """
        self.usage = dict(reply.usage)
        self.stop_reason = reply.stop_reason
        self.tools = tuple(reply.tools)
        self.thinking = tuple(reply.thinking)
        self.dialect = reply.dialect


def _log_completion(chain: Chain, trace: _Trace, status_code: int | None, *, bytes_out: int | None) -> None:
    """Write the one line that says this request happened.

    Emitted here rather than inside the handler because every exit path — a rejected body, a routing refusal, an upstream failure, a delivered answer — has to produce exactly one, and the handler has a return for each of them.
    """
    line = RequestLine(
        method=trace.method,
        path=trace.path,
        inbound_format=trace.inbound_format,
        client_protocol=trace.client_protocol,
        upstream_protocol=trace.upstream_protocol,
        requested_model=trace.requested_model,
        model=trace.model,
        status_code=status_code,
        duration_s=time.monotonic() - trace.started,
        bytes_in=trace.bytes_in,
        bytes_out=bytes_out,
        usage=trace.usage,
        stop_reason=trace.stop_reason,
        tools=trace.tools,
        thinking=trace.thinking,
        dialect=trace.dialect,
        attempts=trace.attempts,
        detail=trace.detail,
    )
    get_logger(REQUEST_LOGGER).info(
        format_completion_line(line, unicode=chain.capabilities.unicode, color=chain.capabilities.color),
        status=status_for(status_code, override=trace.status_override),
    )


async def _serve(request: Request) -> Response:
    """Register the request, hand it to the dispatcher, and account for it on the way out.

    Registration happens **here**, before a single byte of the body has been read, and that placement is the point. It used to happen after the body was in hand, which meant a request still arriving did not exist as far as the display was concerned. A client that announced a body and stopped sending was then invisible: the footer was blank while the shutdown waited on it, and waiting on it is correct — a half-sent request is a real request — so the fault was never the waiting, only that nothing said what was being waited for.

    A streaming response is left alone on the way out: it has produced no bytes at this point and its own generator is what knows when it finished, so it owns both the release and the completion line.
    """
    chain = _chain(request)
    trace = _Trace(
        method=request.method,
        path=request.url.path,
        started=time.monotonic(),
        # Its own identifier rather than the context's, which does not exist yet and may never: a body that fails to parse never produces one, and the footer still has to be able to show and then drop the request.
        request_id=str(uuid4()),
    )
    # Off the ASGI scope, which is where the server records what it negotiated with the client. `websocket` covers the upgrade case, whose transport is HTTP/1.1 underneath but whose behaviour is nothing like it.
    trace.client_protocol = http_label(
        str(request.scope.get("http_version", "")), websocket=request.scope.get("type") == "websocket"
    )
    # Off by default, the way `copilot-api-js` treats its arrival line: on a busy proxy it doubles the log for information the completion line repeats.
    get_logger(REQUEST_LOGGER).debug(format_arrival_line(RequestLine(method=trace.method, path=trace.path)), status="pending")

    chain.active_requests.add(trace.request_id)
    try:
        response = await _dispatch(request, chain, trace)
    except BaseException:
        chain.active_requests.remove(trace.request_id)
        raise
    if isinstance(response, StreamingResponse):
        return response
    chain.active_requests.remove(trace.request_id)
    # `received` rather than the size of what goes to the client: the line describes the proxy's exchange with upstream, and the two differ once anything is rewritten on the way out.
    _log_completion(chain, trace, response.status_code, bytes_out=trace.received or None)
    return response


async def _dispatch(request: Request, chain: Chain, trace: _Trace) -> Response:
    # Consumed here so the request is fully read before anything can return, which is what lets a rejected body be reported at all. Its size is deliberately **not** what `↑` reports — see `_log_completion`. The request is already registered, so a client that never finishes sending is visible for however long it takes.
    await request.body()

    route = route_for_path(request.url.path)
    if route is None:
        # Defensive rather than reachable: `build_router` registers only paths `route_for_path` knows, so a request that got here has one. An unregistered URL is answered by FastAPI's own router and never reaches this function, which is why no completion line is written for it — that is a deliberate boundary, not an oversight: a 404 for a path this proxy does not serve is not a proxied request.
        return JSONResponse({"error": {"message": "unknown endpoint"}}, status_code=404)
    trace.inbound_format = route.wire_format.value

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

    # Recorded here rather than beside the resolved model, so every path below — the count endpoint, the failures, the ones that never route at all — reports what the client asked for even when nothing answered it.
    trace.requested_model = context.requested_model

    active = chain.active_requests

    def _routed(routed: RequestContext) -> None:
        """Tell the footer which model answered, the moment routing decides it."""
        active.set_model(trace.request_id, routed.resolved_model)
        trace.model = routed.resolved_model

    if route.count_tokens:
        # Answered here rather than driven: the reply is a count, not an upstream response to
        # deliver, so none of the block buffering below applies to it.
        try:
            counted = await handle_count_tokens(chain, context)
        except Exception as error:
            # Routing runs inside the handler, so a failure after it has a resolved model worth naming; before it, this is still empty and the field drops out.
            trace.model = context.resolved_model
            trace.detail = str(error)
            return JSONResponse(
                error_body(error),
                status_code=error_status(error),
                headers=error_headers(error),
            )
        # A count is a model request like any other: it resolves a model and it produces a token number, and a line that reported neither made the busiest endpoint on the proxy the least legible one.
        trace.model = context.resolved_model
        active.set_model(trace.request_id, context.resolved_model)
        tokens = counted.get("input_tokens")
        if isinstance(tokens, int):
            trace.usage = {"input_tokens": tokens}
        return JSONResponse(counted)

    try:
        handled = await handle_bounded(chain, context, _routed)
    except Exception as error:
        trace.model = context.resolved_model
        trace.attempts = context.attempt_count
        trace.detail = str(error)
        return JSONResponse(
            error_body(error),
            status_code=error_status(error),
            headers=error_headers(error),
        )
    active.set_model(trace.request_id, context.resolved_model)
    active.set_attempts(trace.request_id, context.attempt_count)
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
    # Exactly what went out to upstream, taken off the request httpx actually sent rather than re-serialized from the payload. It is not the client's body size: translation rewrites the payload, and the version upstream is billed and tokenized for is the one worth reporting.
    trace.bytes_in = len(response.request.content)
    trace.upstream_protocol = http_label(response.http_version)

    if context.stream:
        # Block-level delivery over the live upstream.
        # The body is never read whole here, so a block goes out while the rest still arrives.
        #
        # The registration deliberately outlives this function. A streaming request has produced nothing at the moment the handler returns — the body is consumed after — so releasing here would drop it off the footer at exactly the point it becomes worth watching.
        # Held rather than passed straight through: the assembler is what reads the upstream's terminal event, so after the stream finishes it is the only thing that knows the token usage and the stop reason.
        assembler = assembler_for(handled)
        accounting = _StreamAccounting(
            chain=chain,
            request_id=trace.request_id,
            trace=trace,
            status_code=response.status_code,
            context=context,
            assembler=assembler,
        )
        return _AccountedStreamingResponse(
            _tracked_delivery(
                stream_delivery(
                    _counted_upstream(response.aiter_bytes(), chain, trace.request_id, trace),
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
    # What upstream sent us, not what we hand onward. A buffered reply is one read, so this is the whole of it.
    trace.received = len(response.content)
    payload = response_payload(chain, handled, body)
    # Read off what goes downstream rather than the upstream body, so the numbers on the line are the ones the client was actually told. Summarised once, into the same record the streaming path publishes, so this function never has to know what a `tool_use` block looks like.
    # Summarised by the route's own reader, which knows both what shape this payload is in and which upstream's words describe it. `None` means this route has no reader yet, and the line then reports nothing about the reply's contents rather than reporting emptiness as fact.
    context.reply = reply_summary(handled, payload)
    if context.reply is not None:
        trace.absorb(context.reply)
    return JSONResponse(payload, status_code=response.status_code)


@dataclass(slots=True)
class _StreamAccounting:
    """One streaming request's slot in the footer and its eventual log line.

    Shared by the delivery generator and the response that carries it, because either one may be the last to run. `finish` is idempotent so whichever gets there first records, and the other is a no-op.
    """

    chain: Chain
    request_id: str
    trace: _Trace
    status_code: int
    context: RequestContext | None = None
    assembler: BlockAssembler | None = None
    done: bool = False
    # How the delivery generator ended. Three endings arrive here indistinguishable — upstream's stream ran out, upstream tore, or delivery was cut short from this side — because none of them saw a terminal event and that is all the assembler records. Naming the wrong one sends whoever reads the line to the wrong half of the system, so each is recorded where it happens instead of guessed here.
    drained: bool = False
    failure: BaseException | None = None

    def finish(self) -> None:
        if self.done:
            return
        self.done = True
        self.chain.active_requests.remove(self.request_id)
        # Read at the end because that is when the upstream's terminal event has either been seen or failed to arrive.
        if self.assembler is not None:
            terminal = self.assembler.terminal
            # Absorbed either way. Every field on the record was put there by an event that actually arrived, so a stream cut off mid-turn still has a true account of the blocks it did produce — which tools were asked for, how much reasoning came back — and withholding those said nothing about the truncation while losing everything else. What upstream never said is now simply absent from the record rather than standing at a default that reads like an answer.
            self.trace.absorb(terminal)
            # Deliberately still gated on `seen` while the line above is not, and conservatively rather than undecidedly: `reply is not None` currently means the reply finished, hooks and History are written against that, and widening it is a contract change that belongs with the STR-04 slice which needs a failed History anyway. Registered in `implementation.md`'s 结构怪味登记 so it is reconsidered there rather than rediscovered.
            if terminal.seen and self.context is not None:
                self.context.reply = terminal
            # Two conditions, because either one alone lets a real incident through. Upstream's reason is not enough: `stream_delivery` writes its terminal frames after its event loop, so a tear or a disconnect unwinds straight past them and the client gets neither `message_delta` nor `message_stop` even when the assembler recorded upstream's. And a clean drain is not enough either: that is exactly the truncation this whole path exists to report.
            # Gating on the reason rather than on `seen` is what separates the one benign case from all of these — an Anthropic leg splits its ending, `message_delta` carrying the reason and usage and `message_stop` merely closing, and a stream that drained after the first has told us everything the client was owed. Reporting that as truncated produced a line arguing with itself: `end_turn` followed by a note saying nothing ended.
            # `failure is None` is there to keep this gate and `_ending()` asking the same question in the same order, not to cover a case anyone has produced: a review measured that `drained` and `failure` cannot both be set today, because an exception from the delivery chain surfaces inside the loop below and so never reaches the assignment that marks a drain. Do not go looking for the state — it needs an early `break` in that loop to exist. Without this term, adding one would silently reopen a gap `_ending()` still believes it is closing.
            delivered_whole = self.drained and self.failure is None
            if not (delivered_whole and terminal.stop_reason):
                # Said outright, because absence is not readable. The status was fixed when the response headers arrived and stays 200 however the stream ends; the fields upstream never sent are simply gone; and a reader cannot tell a field this endpoint does not report from one this request never got.
                self.trace.status_override, self.trace.detail = self._ending()
        _log_completion(self.chain, self.trace, self.status_code, bytes_out=self.trace.received)

    def _ending(self) -> tuple[LogStatus, str]:
        """Which of the three ways this stream stopped short, and how much of a problem each is.

        The failure is quoted rather than summarised. It is the only account of what went wrong that exists anywhere — an upstream reset unwinds through the delivery generator and out through the framework, and nothing else on this path writes it down — so a line reporting only that the stream stopped would discard the one fact worth having.

        A client that left is `gone` rather than `fail`, ruled 2026-08-20. Two of these are the proxy's problem and one is not: on a proxy fronting an interactive client, cancelling a turn is routine, and painting every Esc the same red as an upstream reset would bury the resets. `[ OK ]`, which is what those lines used to get, is the other direction of the same mistake — it made a cancelled turn indistinguishable from an answer that arrived.

        The last branch also catches a shutdown cancelling its own in-flight streams, where the client had not gone anywhere and we are the ones leaving. `gone` and the wording both still hold — nobody received the answer, and delivery stopped before upstream finished — but nothing here can tell the two apart, and the line should not claim to.
        """
        if self.failure is not None:
            return "fail", f"stream failed before a terminal event: {self.failure}"
        if self.drained:
            return "fail", "upstream stream ended without a terminal event"
        return "gone", "delivery stopped before upstream finished"


class _AccountedStreamingResponse(StreamingResponse):
    """A streaming response that is accounted for even if its body never runs.

    The generator's own `finally` covers every case where delivery started, including a mid-stream disconnect. It does **not** cover a client that disappears before the first chunk is pulled: an async generator that was never iterated has no suspended frame, so closing it runs nothing, and the request would sit in the footer for the life of the process with its clock climbing and no log line ever written. A review reproduced exactly that by failing the `http.response.start` send.

    Overriding `__call__` puts a `finally` outside everything the framework does, which is the only place that survives a failure before the first iteration.
    """

    def __init__(self, content: AsyncGenerator[bytes], accounting: _StreamAccounting, **kwargs: Any) -> None:
        super().__init__(content, **kwargs)
        self._content = content
        self._accounting = accounting

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Closing the body is this response's job and nobody else's: the framework iterates the generator but never closes it, so a client that stops reading leaves the whole delivery chain suspended for the collector to find. Every layer below already knows how to release the upstream when it is closed — until this line, nothing asked them to. `DelayedStartStreamingResponse` on the legacy path settles its own body for the same reason.
            # Before accounting, so the completion line is written after the upstream is actually released rather than while it is still open. The generator's own `finally` reaches `finish()` first; it is idempotent, and the call below stays for the case where the body was never iterated at all.
            # `finally` rather than the next statement, because accounting is the thing this class exists to guarantee: a close that raises would otherwise leave the request in the footer with its clock running and no line ever written, which is the exact failure the docstring above says this override was added to prevent.
            # The exit that got us here stays the exit that propagates, with the close failure chained onto it. Raising from a `finally` otherwise replaces it, and the replacement is the less useful of the two: a body that fails to close is a consequence of whatever ended the request, and the operator needs the cause. `finish_stream_cleanup` orders the same pair the same way.
            primary = sys.exception()
            try:
                await self._content.aclose()
            except BaseException as close_error:
                if primary is None:
                    raise
                raise primary from close_error
            finally:
                self._accounting.finish()


async def _counted_upstream(chunks: AsyncIterator[bytes], chain: Chain, request_id: str, trace: _Trace) -> AsyncGenerator[bytes]:
    """Count what upstream sends, as it arrives, and forward it untouched.

    This is the number both the footer and the completion line report, because what an operator is watching is the proxy's conversation with upstream. Bytes delivered onward to the client are a different quantity and a much worse indicator: block-level delivery holds a block until it is whole, so a downstream count sits at zero for most of a request and then jumps — which reads as a broken display rather than as the buffering it is.
    """
    async for chunk in chunks:
        trace.received += len(chunk)
        chain.active_requests.add_bytes(request_id, len(chunk))
        yield chunk


async def _tracked_delivery(chunks: AsyncGenerator[bytes], accounting: _StreamAccounting) -> AsyncGenerator[bytes]:
    """Forward the delivery stream untouched and account for the request when it ends.

    `finally` rather than a trailing statement, because a client that disconnects mid-stream cancels this generator — and a request that vanishes from the footer, or never gets its log line, only when something has gone wrong is exactly backwards.

    `aclosing` for the same reason `stream_delivery` wraps its own inner generator: a bare `async for` closes nothing, so a client that goes away throws GeneratorExit at the `yield` below and unwinds straight past the loop, leaving the delivery chain — and the upstream response under it — suspended until the collector happens to reach it. The layer above already closes *this* generator; this is the link that carried that no further.

    It also puts the upstream's release ahead of `finish()`, so the completion line is written after the response is actually gone rather than while it is still open. That is the order this file wants, and it now depends on the cleanup chain below being prompt — which the layers below have their own tests for. Reordering to decouple them would buy nothing and would put the line back in front of the release.
    """
    try:
        async with aclosing(chunks):
            async for chunk in chunks:
                yield chunk
            # Reached only when upstream's stream ran out on its own. A client that goes away closes this generator at a `yield`, and GeneratorExit unwinds straight past this line to the `finally` — which is exactly what tells "upstream stopped mid-turn" apart from "there was nobody left to deliver to". Neither has seen a terminal event, so nothing else can.
            accounting.drained = True
    except Exception as error:
        # The third ending, and the one that used to be filed under the second: upstream tearing the connection — `httpx.ReadError`, a reset, a converter blowing up — leaves this generator by raising rather than by being closed, so it skips the line above and would otherwise be reported as a client that walked away.
        # `Exception` rather than `BaseException` on purpose. GeneratorExit and CancelledError are the two ways this side stops the delivery, and they are already the case the `finally` alone describes correctly; widening the catch would fold all three back into one.
        accounting.failure = error
        raise
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
    # Outermost, so the bound counts a request from the moment it arrives rather than from the
    # moment routing finishes. Over the limit a request waits; it is never refused and its
    # connection is never closed — see `app.server.admission`.
    app.add_middleware(
        InFlightLimit,
        max_inflight=chain.config.proactive_rate_limiter.max_inflight,
    )
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
