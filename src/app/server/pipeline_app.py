"""FastAPI surface driven by the new pipeline.

Separate from `app_factory`, which still serves the existing implementation.
Mounting both would give one path two owners.
"""

import asyncio
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
from starlette.requests import ClientDisconnect

from app.observability.logging import get_logger
from app.observability.metrics import ATTRIBUTION_LINES_STRIPPED, TRANSLATION_LOSSES
from app.observability.rejection_capture import capture_rejection
from app.observability.request_log import (
    LogStatus,
    RequestLine,
    format_arrival_line,
    format_completion_line,
    http_label,
    status_for,
)
from app.observability.request_log_file import utc_timestamp, write_request_record
from app.observability.tui import footer_tui_or_none
from app.pipeline.anthropic_request_hook import strip_attribution_lines
from app.pipeline.delivery.assembler import BlockAssembler, ReplyDialect, Terminal
from app.pipeline.delivery.stream import stream_delivery
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.translation_driver.semantic import Loss
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
    stream_idle_seconds,
    stream_settings,
)
from app.server.inbound import ROUTES, InboundRequestError, build_context, route_for_path
from app.server.ops_routes import router as ops_router
from app.streaming.deadline import with_deadline_at
from app.streaming.idle_timeout import with_idle_timeout

CHAIN_STATE_KEY = "pipeline_chain"

# The logger every per-request line goes under. Named so a filter, a test or a log shipper can select this process's own lines out of a stream that also carries `httpx` and `uvicorn` — a substring match on the message cannot, because `httpx` narrates every upstream call with the same path in it.
REQUEST_LOGGER = "app.request"

# What the calibrator has learnt is only worth keeping if it survives the process.
# Not configurable: `config.example.yaml` has no `tokenization` section to put it in.
TOKENIZATION_FLUSH_SECONDS = 5.0


def _chain(request: Request) -> Chain:
    return cast(Chain, getattr(request.app.state, CHAIN_STATE_KEY))


# What a transport read could not produce, as distinct from what it produced as nothing. Both used to come back `None`, and the snapshot then rendered both as `""` — so a row that failed to read the socket was byte-for-byte a row whose transport never had an address to give.
UNREADABLE = object()


def _extra_info(network_stream: Any, name: str) -> Any:
    """Read one live transport fact without letting observability affect the request.

    Returns `None` when the transport simply has no such fact, and `UNREADABLE` when asking for it raised. The two are different answers to a forensic reader — the first is how a mock or a plain HTTP/1.1 exchange normally looks, the second means this row's identity is missing because something went wrong — and collapsing them is what `_snapshot_upstream_connection` is careful not to do.
    """
    if network_stream is None:
        return None
    try:
        return network_stream.get_extra_info(name)
    except Exception:
        # Not only `OSError`: a transport wrapper may reject an unknown key or expose a closed backing object through another ordinary exception. What they share is that the fact was asked for and did not come back — which is the half worth keeping.
        return UNREADABLE


def _readable(value: Any) -> bool:
    """Whether a transport reading is a fact rather than the absence of one. See `UNREADABLE`."""
    return value is not None and value is not UNREADABLE


def _socket_address(value: object) -> str:
    """Render an httpcore socket address without retaining the live socket.

    Callers filter with `_readable` first, so there is no `None` case to render — an earlier version answered `""` for it, which is the exact conflation `_snapshot_upstream_connection` exists to avoid, sitting one call deeper.
    """
    if isinstance(value, tuple):
        parts = cast(tuple[object, ...], value)
        if len(parts) >= 2:
            host, port = str(parts[0]), parts[1]
            return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return str(cast(object, value))


def _snapshot_upstream_connection(response: Any) -> dict[str, Any]:
    """Copy connection identity from response headers before its network stream closes.

    **Only what was actually observed goes in.** A fact the transport did not supply is left out rather than written as `""`, and when something is missing the record says so under `unavailable`. The reason is a named reader: `.dev/docs/upstream/h2-goaway/` reads `upstream_conn.local` across several rows and concludes that equal values mean one shared connection. Filling the blanks with `""` made every unidentified row equal to every other, so that rule would answer "same connection" for rows that carry no identity at all — a positive conclusion drawn from an absence. Leaving the key out cannot be compared, so the question fails loudly instead.

    Four shapes, each meaning one thing: every key present is a real reading; `unavailable: no-transport-identity` is the ordinary case where the transport had nothing to give (a mock, or an HTTP/1.1 exchange that exposes no stream here); `unavailable: socket-unreadable` means the facts were asked for and the read raised — this is not hypothetical, it is why the snapshot is taken the moment headers arrive rather than at completion, see the call site; `unavailable: snapshot-failed: …` is a transport whose extension mapping is shaped differently altogether. An empty dict is none of those — it is `_Trace`'s default, meaning no snapshot was ever attempted.

    `unavailable` can sit beside real keys. A closed socket still yields `stream_id` from the extensions mapping while the addresses are gone, and reporting the half that is known alongside the reason the other half is missing is more use than either alone.
    """
    try:
        extensions = response.extensions
        network_stream = extensions.get("network_stream")
        addresses = {
            "local": _extra_info(network_stream, "client_addr"),
            "peer": _extra_info(network_stream, "server_addr"),
        }
        alpn = _alpn(_extra_info(network_stream, "ssl_object"))
        # Kept out of the address mapping rather than branching on the key name inside it: `alpn` is a protocol string, not a socket address, and rendering it correctly by asking "is this the alpn key" reads as a special case where there is simply a second kind of fact.
        observed: dict[str, Any] = {name: _socket_address(value) for name, value in addresses.items() if _readable(value)}
        if _readable(alpn):
            observed["alpn"] = alpn
        stream_id = extensions.get("stream_id")
        if isinstance(stream_id, int):
            observed["stream_id"] = stream_id
        if any(value is UNREADABLE for value in (*addresses.values(), alpn)):
            observed["unavailable"] = "socket-unreadable"
        elif not observed:
            observed["unavailable"] = "no-transport-identity"
        return observed
    except Exception as failure:
        # A non-httpcore transport can expose a different extension mapping. Logging must still never change the response path — so the reason travels in the record rather than through a logger, which would also mean a new stream of warnings for a case that has never been observed to fire.
        return {"unavailable": f"snapshot-failed: {failure!r}"}


def _alpn(ssl_object: Any) -> Any:
    """The negotiated protocol, or `None` when there is no TLS to ask, or `UNREADABLE` when asking failed."""
    if ssl_object is None or ssl_object is UNREADABLE:
        return ssl_object
    try:
        selected = ssl_object.selected_alpn_protocol()
    except Exception:
        # As above: optional evidence, and wrappers need not fail specifically with `OSError`.
        return UNREADABLE
    return str(selected) if selected is not None else None


# Where each half of a crossing leaves what it could not carry. Two keys rather than one because they are written at different times by different code; they are joined here, once, into the single list the record carries.
LOSS_EXTRAS = (("request", "conversion_losses"), ("response", "response_conversion_losses"))


def _translation_losses(context: RequestContext) -> tuple[dict[str, str], ...]:
    """The losses translation recorded on this request, request half first.

    Reads the two `extras` keys the handler writes. Those keys were the end of the road until this function existed: `Conversion` collected every loss, the handler copied them onto the context, and nothing anywhere read them — so a request that dropped `thinking`, `top_p` and `stop_sequences` on its way to a Responses upstream produced exactly the same console line, the same record and the same reply as one that lost nothing.

    Entries that are not `Loss` objects are skipped rather than coerced. The key is `Any`-typed and written by one caller today; a future writer putting something else there should show up as a missing entry, not as a record field full of `str(...)` of whatever it was.
    """
    collected: list[dict[str, str]] = []
    for direction, key in LOSS_EXTRAS:
        recorded = context.extras.get(key)
        if not isinstance(recorded, list):
            continue
        for loss in cast(list[Any], recorded):
            if not isinstance(loss, Loss):
                continue
            collected.append({"direction": direction, "code": loss.code.value, "detail": loss.detail})
    return tuple(collected)


@dataclass(slots=True)
class _Trace:
    """What is known about a request as it goes, gathered for its log line.

    Mutable and filled in as routing learns things, because the line is written at the end but its fields become known at four different points. A frozen record would mean rebuilding it at each one.
    """

    method: str
    path: str
    request_id: str = ""
    message_id: str = ""
    inbound_format: str = ""
    # Which endpoint took the request, recorded as soon as the route is known — before anything can fail — so a count that never reached a counter is still reported as a count.
    count_tokens: bool = False
    client_protocol: str = ""
    upstream_protocol: str = ""
    requested_model: str = ""
    model: str = ""
    attempts: int = 1
    detail: str = ""
    # What the HTTP status cannot say. A streaming status is fixed the moment the response headers arrive, so everything that happens over the next several minutes — the stream stopping mid-turn, upstream tearing, the client leaving — leaves it at 200. `None` means the status code is the whole story.
    status_override: LogStatus | None = None
    started: float = 0.0
    started_at: str = ""
    first_upstream_byte_s: float | None = None
    bytes_in: int | None = None
    received: int = 0
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    terminal_seen: bool = False
    stop_reason: str = ""
    blocks: int = 0
    tools: tuple[str, ...] = ()
    thinking: tuple[str, ...] = ()
    # Which counting provider answered a token-counting request, and nothing at all on any other route. See `format_count_provider`.
    count_provider: str = ""
    count_provider_reason: str = ""
    dialect: ReplyDialect = ReplyDialect.ANTHROPIC
    upstream_conn: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    losses: tuple[dict[str, str], ...] = ()

    def absorb(self, reply: Terminal) -> None:
        """Take the aggregated reply record onto the line.

        One call rather than four assignments at each of the two delivery paths, so a field added to the record reaches the line without either path being edited — and, more to the point, so neither path can decide for itself what "the tools this turn asked for" means.
        """
        self.usage = dict(reply.usage)
        self.terminal_seen = reply.seen
        self.stop_reason = reply.stop_reason
        self.blocks = reply.blocks
        self.tools = tuple(reply.tools)
        self.thinking = tuple(reply.thinking)
        self.dialect = reply.dialect

    def absorb_losses(self, context: RequestContext) -> None:
        """Take whatever translation has recorded so far onto the line.

        Recomputes from `context.extras` rather than appending, so calling it again after more translation has happened is correct and calling it twice with nothing in between changes nothing. That is what lets it be called at each point a translation has just finished instead of at one point that would have to be the last.

        Called at four such points because translation happens at two of them and the response half at a third; a single call site would have to sit after every `return` in `_dispatch`, which no single site does. The cost of the arrangement is that a `return` added later without a call here reports no losses — which is why `losses` says nothing rather than says none: an empty tuple is what a lossless crossing looks like too.
        """
        self.losses = _translation_losses(context)


def _log_completion(chain: Chain, trace: _Trace, status_code: int | None, *, bytes_out: int | None) -> None:
    """Write the one line that says this request happened.

    Emitted here rather than inside the handler because every exit path — a rejected body, a routing refusal, an upstream failure, a delivered answer, and an exception on its way out through `_serve` — has to produce exactly one, and the handler has a return for each of them and no say in the last.
    """
    line = RequestLine(
        method=trace.method,
        path=trace.path,
        request_id=trace.request_id,
        message_id=trace.message_id,
        inbound_format=trace.inbound_format,
        count_tokens=trace.count_tokens,
        client_protocol=trace.client_protocol,
        upstream_protocol=trace.upstream_protocol,
        requested_model=trace.requested_model,
        model=trace.model,
        status_code=status_code,
        started_at=trace.started_at,
        duration_s=time.monotonic() - trace.started,
        first_upstream_byte_s=trace.first_upstream_byte_s,
        bytes_in=trace.bytes_in,
        bytes_out=bytes_out,
        usage=trace.usage,
        terminal_seen=trace.terminal_seen,
        stop_reason=trace.stop_reason,
        blocks=trace.blocks,
        tools=trace.tools,
        thinking=trace.thinking,
        count_provider=trace.count_provider,
        count_provider_reason=trace.count_provider_reason,
        dialect=trace.dialect,
        attempts=trace.attempts,
        detail=trace.detail,
        upstream_conn=trace.upstream_conn,
        losses=trace.losses,
    )
    status = status_for(status_code, override=trace.status_override)
    for loss in line.losses:
        # Counted here rather than where the loss is recorded, so the count and the record are produced from the same tuple and cannot disagree about what this request lost.
        TRANSLATION_LOSSES.labels(direction=loss["direction"], code=loss["code"]).inc()
    write_request_record(line, status=status)
    get_logger(REQUEST_LOGGER).info(
        format_completion_line(line, status=status, unicode=chain.capabilities.unicode, color=chain.capabilities.color),
        status=status,
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
        started_at=utc_timestamp(),
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
    except BaseException as failure:
        chain.active_requests.remove(trace.request_id)
        # An exception is an exit path like any other, and until this line it was the one that produced no record at all — `_log_completion`'s docstring claimed every path writes exactly one while a client hanging up mid-body, a reply that would not parse, or anything unexpected in translation left nothing behind but a traceback in the server's own log, under a different logger and carrying none of this request's identity. Measured rather than feared: a probe raising from `Request.body()`, and an upstream answering 200 with a body `response.json()` cannot parse, each produced zero `app.request` records.
        # Exactly-once is structural here rather than guarded by a flag, which is the difference from the streaming path. There, the delivery generator and the response's `__call__` both genuinely arrive and `_StreamAccounting.done` has to decide between them; here the two branches are alternatives — this one runs only when `_dispatch` did not return — so there is no second finisher to be idempotent against, and a flag would only hide it if one ever appeared.
        trace.status_override, trace.detail = _aborted(failure)
        # No status code, because none was ever settled: nothing is being sent to the client, so there is nothing to report as what it was told, and the field drops off the line rather than standing at a number nobody saw. That leaves the verdict entirely to the override — `status_for` reads a missing code as a failure, which is right for one of the three endings below and wrong for the other two.
        _log_completion(chain, trace, None, bytes_out=trace.received or None)
        raise
    if isinstance(response, StreamingResponse):
        return response
    chain.active_requests.remove(trace.request_id)
    # `received` rather than the size of what goes to the client: the line describes the proxy's exchange with upstream, and the two differ once anything is rewritten on the way out.
    _log_completion(chain, trace, response.status_code, bytes_out=trace.received or None)
    return response


def _aborted(failure: BaseException) -> tuple[LogStatus, str]:
    """Which of the three ways a request left without ever being answered, and whose problem each is.

    The same split `_StreamAccounting._ending` makes for a stream that stopped short, made here for the same reason: absence is not readable. A line whose status code, usage and reply fields are all missing looks identical whether the client hung up while still sending, the process was going down, or something inside this proxy raised — and those three send a reader to three different places.

    A client that left is `gone` rather than `fail`, on the ruling `_ending` already records: against an interactive client, abandoning a turn is routine, and painting it the same red as a proxy that broke buries the ones worth reading. The cancellation branch also covers a shutdown cancelling its own in-flight requests, where nobody left at all — so its wording names no side, because nothing here can tell the two apart and the line should not claim to.

    The failure is quoted with `repr` rather than the `str` `_ending` uses, because that one has a known transport error in hand and this one has whatever escaped. `str(KeyError("model"))` is `"'model'"` with no hint of what kind of thing went wrong, and `str(RuntimeError())` is empty outright — which would print the detail as a colon and nothing after it, exactly the unreadable absence this function exists to prevent. An exception that arrived wrapped in a group is quoted as the group, which is honest: nothing between here and the raise unwraps one, so picking a member would be a guess about which one mattered.
    """
    if isinstance(failure, ClientDisconnect):
        return "gone", "client disconnected before the request was answered"
    if isinstance(failure, asyncio.CancelledError):
        return "gone", "request cancelled before it was answered"
    return "fail", f"request failed before a response: {failure!r}"


async def _dispatch(request: Request, chain: Chain, trace: _Trace) -> Response:
    # Consumed here so the request is fully read before anything can return, which is what lets a rejected body be reported at all. Its size is deliberately **not** what `↑` reports — see `_log_completion`. The request is already registered, so a client that never finishes sending is visible for however long it takes.
    await request.body()

    route = route_for_path(request.url.path)
    if route is None:
        # Defensive rather than reachable: `build_router` registers only paths `route_for_path` knows, so a request that got here has one. An unregistered URL is answered by FastAPI's own router and never reaches this function, which is why no completion line is written for it — that is a deliberate boundary, not an oversight: a 404 for a path this proxy does not serve is not a proxied request.
        return JSONResponse({"error": {"message": "unknown endpoint"}}, status_code=404)
    trace.inbound_format = route.wire_format.value
    trace.count_tokens = route.count_tokens

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

    # After parsing and before routing, which is where `docs/.human-controlled/message-format-sanitize.md` puts it: the line is addressed to Anthropic's billing rather than to any model, so nothing downstream — routing, translation, the token counter — should ever see it. Resident rather than configured, per the same document.
    if route.wire_format is WireFormat.ANTHROPIC_MESSAGES:
        stripped = strip_attribution_lines(context.payload)
        if stripped:
            ATTRIBUTION_LINES_STRIPPED.inc(stripped)

    # Recorded here rather than beside the resolved model, so every path below — the count endpoint, the failures, the ones that never route at all — reports what the client asked for even when nothing answered it.
    trace.message_id = context.id
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
            # No capture here on purpose. `count_tokens` converts every upstream failure into `CountTokensUnavailable` before it reaches this line, so an `UpstreamRejected` never arrives and a call would be wiring that looks live and is not. That conversion also means a counting request refused over its body answers 503 rather than upstream's own verdict, which is a separate gap and not this one's to close.
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
        # What kind of request this was, and which counter answered. Everything else on a count line is absent because a count has no reply, and absence is what a delivered turn that lost its reply looks like too — so without this the two are one line.
        provider = context.extras.get("count_tokens_provider")
        if isinstance(provider, str):
            trace.count_provider = provider
        # Why the estimator answered, when that is worth saying. Decided in `handle_count_tokens`, which is where the facts that separate a configured estimate from a failed upstream are; this end only carries it.
        reason = context.extras.get("count_tokens_reason")
        if isinstance(reason, str):
            trace.count_provider_reason = reason
        # The upstream leg, present only when upstream responded to the count — which is not the same as answering it, since a reply carrying no usable number is handed to the estimator with the leg already flown. A refusal never gets this far, the client raises it as a pipeline error, and the local estimator never leaves the process; showing a leg for either would claim a request that was never sent.
        upstream_protocol = context.extras.get("count_tokens_upstream_protocol")
        if isinstance(upstream_protocol, str):
            trace.upstream_protocol = http_label(upstream_protocol)
        sent = context.extras.get("count_tokens_bytes_in")
        if isinstance(sent, int):
            trace.bytes_in = sent
        # `received` rather than the size of what goes back to the client, exactly as the delivery path uses it: both halves of the line describe this proxy's exchange with upstream.
        came_back = context.extras.get("count_tokens_bytes_out")
        if isinstance(came_back, int):
            trace.received = came_back
        # A count is translated too, and on the same terms — so a count whose `thinking` never crossed says so, exactly as a turn does.
        trace.absorb_losses(context)
        return JSONResponse(counted)

    try:
        handled = await handle_bounded(chain, context, _routed)
    except Exception as error:
        trace.model = context.resolved_model
        trace.attempts = context.attempt_count
        trace.detail = str(error)
        # A refused crossing is exactly where the losses matter: they name which field the request could not carry, and the error alone rarely does.
        trace.absorb_losses(context)
        # Before the response is written, because `context.payload` is the body upstream refused and nothing downstream keeps it.
        capture_rejection(context, error, request_id=trace.request_id)
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
    # The request half has crossed by now whatever happens next, so this covers the three returns below. The buffered path calls again once the reply has crossed back.
    trace.absorb_losses(context)

    response = handled.response
    if response is None:
        error = handled.outcome.error or RuntimeError("request produced no response")
        trace.detail = str(error)
        # The branch an upstream refusal actually takes: the driver reports it in the outcome rather than raising, so the exception path above never sees one.
        capture_rejection(context, error, request_id=trace.request_id)
        return JSONResponse(
            error_body(error),
            status_code=error_status(error),
            headers=error_headers(error),
        )
    # Exactly what went out to upstream, taken off the request httpx actually sent rather than re-serialized from the payload. It is not the client's body size: translation rewrites the payload, and the version upstream is billed and tokenized for is the one worth reporting.
    trace.bytes_in = len(response.request.content)
    trace.upstream_protocol = http_label(response.http_version)
    # Snapshot the live socket now. `_log_completion` intentionally runs only after the response is released, when httpcore's `client_addr` lookup can already raise `OSError: [Errno 9] Bad file descriptor`.
    trace.upstream_conn = _snapshot_upstream_connection(response)

    if context.stream:
        # Block-level delivery over the live upstream.
        # The body is never read whole here, so a block goes out while the rest still arrives.
        #
        # The registration deliberately outlives this function. A streaming request has produced nothing at the moment the handler returns — the body is consumed after — so releasing here would drop it off the footer at exactly the point it becomes worth watching.
        # Held rather than passed straight through: the assembler is what reads the upstream's terminal event, so after the stream finishes it is the only thing that knows the token usage and the stop reason.
        assembler = assembler_for(handled)
        # The instant the driver fixed when it opened this attempt, read rather than recomputed: a second `now + deadline` here would start the clock at the moment the headers came back and quietly grant the attempt a second full lifetime.
        attempt = context.current_attempt
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
                    # The guard measures upstream SSE activity, not the events parsed out of it. Ruled 2026-08-20: a comment frame and a large event still arriving both keep bytes moving while the parser yields nothing, so timing the parser would call a connection that is still transmitting silent — and never false-killing legitimate thinking is what `config.example.yaml` freezes.
                    _counted_upstream(
                        # Two guards on the same bytes, and the order decides which one gets to speak: the deadline is outermost so that an idle timeout raised beneath it arrives with its own name rather than being relabelled by whichever guard happens to wrap the other.
                        # The second place `upstream_request_deadline` is enforced from — one bound, not two. `await send` returns when the response headers arrive — measured 2026-08-20 — so everything the body does afterwards happens with the driver already off the stack, and until this line nothing was holding the attempt to the life it was given.
                        with_deadline_at(
                            with_idle_timeout(
                                response.aiter_bytes(),
                                timeout_seconds=stream_idle_seconds(chain),
                            ),
                            deadline_at=attempt.deadline_at if attempt is not None else None,
                        ),
                        chain,
                        trace.request_id,
                        trace,
                    ),
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
    # Again, because the reply has only just crossed back: the response half of the translation records its losses during `response_payload` above, after the call that covered the request half.
    trace.absorb_losses(context)
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
        if chunk and trace.first_upstream_byte_s is None:
            trace.first_upstream_byte_s = time.monotonic() - trace.started
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
