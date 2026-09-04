"""The model endpoints: one dispatcher for all of them, and the accounting that follows a stream out.

Split out of `app.server.pipeline_app` on 2026-08-22. That module is the app factory now; this is what it mounts. The route table it dispatches against is `app.server.routes.table`, and everything it decides with belongs to `app.pipeline` — this file reads a request, hands it over, and renders what comes back.
"""

import asyncio
import sys
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Coroutine
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import uuid4

import anyio
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.requests import ClientDisconnect
from starlette.types import Message, Receive, Scope, Send

from app.core.chain import Chain
from app.errors import ErrorCategory
from app.observability.logging import get_logger
from app.observability.metrics import ATTRIBUTION_LINES_STRIPPED
from app.observability.rejection_capture import capture_rejection
from app.observability.request_completion import (
    FailureOrigin as CompletionFailureOrigin,
)
from app.observability.request_completion import (
    InterruptionPhase,
    RequestCompletionCoordinator,
    safe_exception_graph_notes,
    safe_exception_notes,
)
from app.observability.request_log import (
    LogStatus,
    RequestLine,
    format_arrival_line,
    http_label,
)
from app.observability.request_log_file import utc_timestamp
from app.observability.request_trace import (
    REQUEST_LOGGER,
    RequestTrace,
    snapshot_upstream_connection,
)
from app.pipeline.anthropic_request_hook import strip_attribution_lines
from app.pipeline.delivery.assembling import BlockAssembler, FailureOrigin
from app.pipeline.delivery.blocks import TOOL_USE
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.delivery.stream import (
    Attempt,
    ContinuationSupport,
    ReplaySupport,
    UpstreamSource,
    one_shot_delivery,
    stream_delivery,
)
from app.pipeline.delivery_policy import (
    assembler_for,
    carries_upstream_natively,
    delivery_buffer,
    framer_for,
    stream_idle_seconds,
    stream_settings,
)
from app.pipeline.driver import (
    RESPONSE_CONVERSION_LOSSES,
    handle,
    handle_bounded,
    handle_count_tokens,
    ledger_for,
)
from app.pipeline.error_classify import describe
from app.pipeline.hand_over import HandBackOutcome, hand_back_block, one_line, replay_reason
from app.pipeline.reply import reply_summary, response_payload
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.translation_driver.semantic import Loss
from app.server.app_state import chain_of
from app.server.http_errors import error_response, proxy_error
from app.server.inbound import InboundRequestError, build_context
from app.server.routes.table import route_for_path
from app.streaming.deadline import (
    with_client_deadline_at,
    with_deadline_at,
)
from app.streaming.idle_timeout import with_idle_timeout
from app.streaming.keepalive import (
    find_cancellation,
    finish_async_cleanup,
    finish_stream_cleanup,
    raise_with_cleanup_under,
)


class _DisconnectedResponse(Response):
    """Complete FastAPI routing after the peer has left without sending a response."""

    def __init__(self) -> None:
        # Kept as internal state because FastAPI requires an endpoint Response. `__call__` sends no ASGI messages, so this status is never presented or accounted as a response.
        super().__init__(status_code=499)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive, send


async def serve(request: Request) -> Response:
    """Register the request, hand it to the dispatcher, and account for it on the way out.

    Registration happens **here**, before a single byte of the body has been read, and that placement is the point. It used to happen after the body was in hand, which meant a request still arriving did not exist as far as the display was concerned. A client that announced a body and stopped sending was then invisible: the footer was blank while the shutdown waited on it, and waiting on it is correct — a half-sent request is a real request — so the fault was never the waiting, only that nothing said what was being waited for.

    A streaming response is left alone on the way out: it has produced no bytes at this point and its own generator is what knows when it finished, so it owns both the release and the completion line.
    """
    chain = chain_of(request)
    trace = RequestTrace(
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
    completion = RequestCompletionCoordinator(
        chain=chain,
        trace=trace,
        request_id=trace.request_id,
    )
    try:
        response = await _dispatch(request, chain, trace, completion)
    except BaseException as failure:
        # This is the only path with no outer Response object to publish from. Preserve the existing classification, attach the dispatch failure to the delivery observation, and publish once before the exception boundary decides whether anything remains to propagate.
        trace.status_override, trace.detail = _aborted(failure)
        completion.note_wrapped_failure(
            failure,
            origin=CompletionFailureOrigin.DISPATCH,
        )
        if isinstance(failure, ClientDisconnect):
            _note_disconnect_cleanup(completion, failure)
        completion.settle(
            status_code=None,
            upstream_response_bytes=trace.upstream_response_body_bytes,
        )
        completion.publish()
        if isinstance(failure, ClientDisconnect):
            return _DisconnectedResponse()
        raise
    completion.mark_response_ready(response.status_code)
    if isinstance(response, StreamingResponse):
        return response
    return _AccountedResponse(response, completion)


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


def _absorb_response_observation(context: RequestContext, trace: RequestTrace) -> None:
    attempt = context.current_attempt
    observer = attempt.response_observer if attempt is not None else None
    if observer is None:
        return
    observation = observer.snapshot()
    context.response_observation = observation
    trace.absorb_response(observation)


def _observe_failed_upstream_response(
    context: RequestContext,
    trace: RequestTrace,
    chain: Chain,
    error: BaseException,
) -> None:
    attempt = context.current_attempt
    observer = attempt.response_observer if attempt is not None else None
    body = _upstream_error_body(error)
    if body is not None:
        trace.received = len(body)
        trace.received_known = True
        chain.active_requests.set_upstream_response_bytes(trace.request_id, len(body))
        if observer is not None:
            observer.observe_body_bytes(body)
    _absorb_response_observation(context, trace)


def _upstream_error_body(error: BaseException) -> bytes | None:
    seen: set[int] = set()
    pending = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        body = getattr(current, "body_bytes", None)
        body_observed = getattr(current, "body_observed", False)
        if isinstance(body, bytes) and body_observed is True:
            return body
        pending.extend(
            nested
            for nested in (
                current.__cause__,
                current.__context__,
                getattr(current, "cause", None),
            )
            if isinstance(nested, BaseException)
        )
    return None


def _exception_links(error: BaseException) -> list[BaseException]:
    links = [
        nested
        for nested in (error.__cause__, error.__context__)
        if nested is not None
    ]
    if isinstance(error, BaseExceptionGroup):
        group = cast(BaseExceptionGroup[BaseException], error)
        links.extend(group.exceptions)
    return links


def _cancellation_only(error: BaseException | None) -> bool:
    """Whether an exception graph contains only the task group's expected cancellation."""
    if error is None:
        return False
    seen: set[int] = set()
    pending = [error]
    found_cancellation = False
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if safe_exception_notes(current):
            return False
        if isinstance(current, asyncio.CancelledError):
            found_cancellation = True
        elif not isinstance(current, BaseExceptionGroup):
            return False
        pending.extend(_exception_links(cast(BaseException, current)))
    return found_cancellation


def _secondary_failure_key(
    error: BaseException,
) -> tuple[str, str, frozenset[tuple[str, str]]]:
    """Identify equivalent exception-group wrappers without conflating independent errors."""
    if not isinstance(error, BaseExceptionGroup):
        return ("exception", str(id(error)), frozenset())

    normalized_error = cast(BaseException, error)
    seen: set[int] = set()
    facts: set[tuple[str, str]] = {
        ("note", note) for note in safe_exception_graph_notes(normalized_error)
    }
    pending: list[BaseException] = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, asyncio.CancelledError | BaseExceptionGroup):
            pending.extend(_exception_links(cast(BaseException, current)))
        else:
            facts.add(("exception", str(id(current))))
    group = cast(BaseExceptionGroup[BaseException], error)
    return ("group", group.message, frozenset(facts))


def _disconnect_secondary_failures(error: BaseException) -> list[BaseException]:
    """Return each real failure below a disconnect, ignoring cancellation-only links."""
    if not isinstance(error, ClientDisconnect):
        return []
    seen_nodes = {id(error)}
    seen_failures: set[tuple[str, str, frozenset[tuple[str, str]]]] = set()
    pending = list(reversed(_exception_links(error)))
    secondaries: list[BaseException] = []
    while pending:
        current = pending.pop()
        if id(current) in seen_nodes:
            continue
        seen_nodes.add(id(current))
        if _cancellation_only(current):
            continue
        if isinstance(current, asyncio.CancelledError):
            if safe_exception_notes(current):
                key = _secondary_failure_key(current)
                if key not in seen_failures:
                    seen_failures.add(key)
                    secondaries.append(current)
            pending.extend(reversed(_exception_links(current)))
            continue
        key = _secondary_failure_key(current)
        if key not in seen_failures:
            seen_failures.add(key)
            secondaries.append(current)
    return secondaries


def _note_disconnect_cleanup(
    completion: RequestCompletionCoordinator,
    failure: ClientDisconnect,
) -> None:
    completion.note_secondary_cleanup_notes(failure)
    for secondary in _disconnect_secondary_failures(failure):
        completion.note_secondary_cleanup_failure(secondary)


def _raise_with_secondaries(
    primary: BaseException,
    secondaries: list[BaseException],
) -> None:
    distinct = [error for error in secondaries if error is not primary]
    if not distinct:
        raise primary
    secondary: BaseException = (
        distinct[0]
        if len(distinct) == 1
        else BaseExceptionGroup("concurrent request cleanup failed", distinct)
    )
    raise_with_cleanup_under(primary, secondary)


async def _discard_prepared_response(
    response: Response,
    *,
    primary: BaseException | None,
) -> list[BaseException]:
    close = getattr(response, "aclose", None)
    if not callable(close):
        return []
    cleanup_error, cleanup_cancellation = await finish_async_cleanup(
        cast(Callable[[], Coroutine[Any, Any, None]], close),
        primary=primary,
    )
    return [
        error
        for error in (cleanup_error, cleanup_cancellation)
        if error is not None and error is not primary
    ]


async def _run_dispatch_while_connected(
    receive: Receive,
    operation: Callable[[], Awaitable[Response]],
    *,
    on_disconnect: Callable[[], None] | None = None,
) -> Response:
    """Run response preparation alongside the downstream disconnect listener.

    The request-body reader owns `receive` until it has consumed the whole body. This helper starts afterwards and does not hand a Response over until its listener has stopped cleanly; a StreamingResponse then becomes the next owner of the same receive channel.
    """
    winner = [""]
    results: list[Response] = []
    operation_error: BaseException | None = None
    listener_error: BaseException | None = None
    handed_off = False

    try:
        async with anyio.create_task_group() as task_group:

            def stop(label: str) -> None:
                if not winner[0]:
                    winner[0] = label
                task_group.cancel_scope.cancel()

            async def run_operation() -> None:
                nonlocal operation_error
                try:
                    results.append(await operation())
                except BaseException as error:
                    operation_error = error
                finally:
                    stop("operation")

            async def listen_for_disconnect() -> None:
                nonlocal listener_error
                try:
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            if on_disconnect is not None:
                                on_disconnect()
                            stop("disconnect")
                            return
                except BaseException as error:
                    listener_error = error
                    stop("listener")

            task_group.start_soon(run_operation)
            task_group.start_soon(listen_for_disconnect)

        if winner[0] == "operation" and operation_error is None:
            if len(results) != 1:
                raise RuntimeError("dispatch completed without exactly one response")
            if listener_error is None or _cancellation_only(listener_error):
                handed_off = True
                return results[0]
            _raise_with_secondaries(listener_error, [])

        if winner[0] == "operation":
            if operation_error is None:
                raise RuntimeError("dispatch exited without a result or failure")
            operation_secondaries: list[BaseException] = (
                []
                if listener_error is None or _cancellation_only(listener_error)
                else [listener_error]
            )
            _raise_with_secondaries(operation_error, operation_secondaries)

        primary: BaseException
        if winner[0] == "disconnect":
            primary = ClientDisconnect()
        elif winner[0] == "listener" and listener_error is not None:
            primary = listener_error
        else:
            raise RuntimeError("dispatch and disconnect listener ended without a winner")

        secondaries: list[BaseException] = []
        if operation_error is not None and not _cancellation_only(operation_error):
            secondaries.append(operation_error)
        _raise_with_secondaries(primary, secondaries)
        raise AssertionError("unreachable")
    finally:
        if results and not handed_off:
            cleanup_primary = sys.exception()
            cleanup_errors = await _discard_prepared_response(
                results[0],
                primary=cleanup_primary,
            )
            if cleanup_errors:
                if cleanup_primary is None:
                    cleanup_primary = cleanup_errors.pop(0)
                _raise_with_secondaries(cleanup_primary, cleanup_errors)


async def _dispatch(
    request: Request,
    chain: Chain,
    trace: RequestTrace,
    completion: RequestCompletionCoordinator,
) -> Response:
    # Fixed before the body is read, because that read is inside the lifetime this bounds. `handle_bounded` starts its own clock later, when routing hands it the request, so the two do not agree on when the request began — and the one an operator means by "the client request" starts here. Measured 2026-08-22: body read, JSON parse and admission queueing were all outside the only clock there was.
    #
    # An instant rather than a duration, for the same reason the attempt's is: the body outlives the function that admitted it, and a duration restarted downstream would grant a second lifetime.
    client_deadline = chain.config.client_delivery.client_request_deadline
    client_deadline_at = (
        asyncio.get_running_loop().time() + client_deadline if client_deadline > 0 else None
    )
    # Consumed here so the request is fully read before anything can return, which is what lets a rejected body be reported at all. Its size is deliberately **not** what `↑` reports — see `log_completion`. The request is already registered, so a client that never finishes sending is visible for however long it takes.
    try:
        await request.body()
    except ClientDisconnect:
        completion.note_http_disconnect(
            phase=InterruptionPhase.REQUEST_BODY,
        )
        raise
    return await _run_dispatch_while_connected(
        request.receive,
        lambda: _dispatch_after_body(
            request,
            chain,
            trace,
            completion,
            client_deadline_at=client_deadline_at,
        ),
        on_disconnect=lambda: completion.note_http_disconnect(
            phase=InterruptionPhase.DISPATCH_WAIT,
        ),
    )


async def _dispatch_after_body(
    request: Request,
    chain: Chain,
    trace: RequestTrace,
    completion: RequestCompletionCoordinator,
    *,
    client_deadline_at: float | None,
) -> Response:
    # The template rather than the URL: once a path carries parameters the two differ, and only the template identifies the route. The router records which of its own paths answered, so this is that answer rather than a second match of our own. Reading it also survives a mount prefix — measured, `--root-path /api` made `route_for_path(request.url.path)` miss on every route and answer 404 from the branch below.
    matched = request.scope.get("route")
    route = route_for_path(getattr(matched, "path", None) or request.url.path)
    if route is None:
        # Defensive rather than reachable: `build_router` registers only paths `route_for_path` knows, so a request that got here has one. An unregistered URL is answered by FastAPI's own router and never reaches this function, which is why no completion line is written for it — that is a deliberate boundary, not an oversight: a 404 for a path this proxy does not serve is not a proxied request.
        # `INTERNAL` rather than the 404 this used to answer. Reaching here means the router and the lookup table disagree about what is mounted, which is this proxy's own inconsistency; telling the client "not found" would send it to check its URL, and the URL is fine. The dialect is Anthropic's because without a route there is no inbound format to read.
        return error_response(
            proxy_error(ErrorCategory.INTERNAL, "this proxy's route table and router disagree"),
            inbound_format=WireFormat.ANTHROPIC_MESSAGES.value,
        )
    trace.inbound_format = route.wire_format.value
    trace.count_tokens = route.count_tokens
    chain.active_requests.set_route(
        trace.request_id,
        route=route.path,
        inbound_format=trace.inbound_format,
    )

    if not route.implemented:
        # 501, not 404 and not 400. The path is one `api.md` ratifies, and a 404 would make it indistinguishable from an endpoint this proxy does not have; 400 is what a missing translator would otherwise produce, and that blames the client's body for a capability this proxy has not built. Answered before the body is *parsed* — it has already been read, a line above — because nothing here can judge a format it cannot read.
        # The URL rather than `route.path`, which is this repository's own spelling: a client told that `/v1beta/models/{model}:generateContent` is unimplemented has been handed a template it cannot act on. The envelope is this proxy's general one; whether an unimplemented endpoint should answer in its own dialect's error shape is registered in `deferred.md` rather than decided here.
        trace.detail = f"{route.wire_format.value} is routed but not implemented"
        return error_response(
            proxy_error(
                ErrorCategory.NOT_IMPLEMENTED, f"{request.url.path} is not implemented yet"
            ),
            inbound_format=route.wire_format.value,
        )

    try:
        parsed: object = await request.json()
    except ValueError:
        trace.detail = "body is not valid JSON"
        return error_response(
            proxy_error(ErrorCategory.CLIENT, "body is not valid JSON"),
            inbound_format=route.wire_format.value,
        )
    if not isinstance(parsed, dict):
        trace.detail = "body must be an object"
        return error_response(
            proxy_error(ErrorCategory.CLIENT, "body must be an object"),
            inbound_format=route.wire_format.value,
        )
    body = cast(dict[str, Any], parsed)

    try:
        # The path parameters go with the body because for some routes they are part of it: Azure names the deployment in the URL and sends a body with no model, so what the client asked for can only be read from the two together.
        context = build_context(route, body, request.headers, request.path_params)
    except InboundRequestError as error:
        trace.detail = str(error)
        return error_response(
            proxy_error(ErrorCategory.CLIENT, str(error)),
            inbound_format=route.wire_format.value,
        )

    # After parsing and before routing, which is where `docs/.human-controlled/message-format-reshape.md` puts it: the line is addressed to Anthropic's billing rather than to any model, so routing, translation and the token counter should not be reading it. Scope is what that document specifies — the leading lines of `system[0]` — so an attribution line placed anywhere else does still travel.
    # Off unless the operator asks, per the same document. It was resident for one commit, under that document's previous revision.
    if (
        route.wire_format is WireFormat.ANTHROPIC_MESSAGES
        and chain.config.hook_strip_anthropic_request_headers.strip_attribution_header
    ):
        stripped = strip_attribution_lines(context.payload)
        if stripped:
            ATTRIBUTION_LINES_STRIPPED.inc(stripped)

    chain.active_requests.set_stream(trace.request_id, context.stream)

    # Recorded here rather than beside the resolved model, so every path below — the count endpoint, the failures, the ones that never route at all — reports what the client asked for even when nothing answered it.
    trace.message_id = context.id
    trace.requested_model = context.requested_model

    active = chain.active_requests

    def _routed(routed: RequestContext) -> None:
        """Publish routing facts the moment routing decides them."""
        active.set_model(trace.request_id, routed.resolved_model)
        active.set_provider(trace.request_id, routed.provider_name)
        trace.model = routed.resolved_model

    def _count_upstream_response_observed(counted_context: RequestContext) -> None:
        """Project count transport facts as soon as its buffered response exists."""
        upstream_protocol = counted_context.extras.get(
            "count_tokens_upstream_protocol"
        )
        if isinstance(upstream_protocol, str):
            trace.upstream_protocol = http_label(upstream_protocol)
        sent = counted_context.extras.get("count_tokens_upstream_request_bytes")
        if isinstance(sent, int):
            trace.upstream_request_body_bytes = sent
        came_back = counted_context.extras.get(
            "count_tokens_upstream_response_bytes"
        )
        if isinstance(came_back, int):
            trace.received = came_back
            trace.received_known = True
            active.set_upstream_response_bytes(trace.request_id, came_back)

    if route.count_tokens:
        # Answered here rather than driven: the reply is a count, not an upstream response to deliver, so none of the block buffering below applies to it.
        try:
            counted = await handle_count_tokens(
                chain,
                context,
                _routed,
                _count_upstream_response_observed,
            )
        except Exception as error:
            # Idempotent with the early callback and needed when failure happened before that callback could run.
            _count_upstream_response_observed(context)
            # Routing runs inside the handler, so a failure after it has a resolved model worth naming; before it, this is still empty and the field drops out.
            trace.model = context.resolved_model
            trace.detail = str(error)
            # A count that failed still translated, and what the translation could not carry is part of why it may have failed.
            trace.absorb_losses(context)
            # No capture here on purpose. `count_tokens` converts every upstream failure into `CountTokensUnavailable` before it reaches this line, so an `UpstreamRejected` never arrives and a call would be wiring that looks live and is not. That conversion also means a counting request refused over its body answers 503 rather than upstream's own verdict, which is a separate gap and not this one's to close.
            return error_response(
                error,
                inbound_format=route.wire_format.value,
                translated=context.translation_required,
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
        # The upstream leg, present only when upstream responded to the count—which is not the same as answering it, since a reply carrying no usable number is handed to the estimator with the leg already flown. The early callback already projected it before parsing; this idempotent call keeps the final trace aligned on local-only paths too.
        _count_upstream_response_observed(context)
        # A count is translated too, and on the same terms — so a count whose `thinking` never crossed says so, exactly as a turn does.
        trace.absorb_losses(context)
        return JSONResponse(counted)

    # Taken before anything can rewrite it, because a replayed attempt has to send what the client sent. `handle` translates in place — `context.payload = translated`, and `fix_anthropic_request` edits the dict it is given — so a second pass over the same context would translate an already-translated body. Measured 2026-08-22 on the primary path: the second attempt went out as `{"model": "gpt-model", "input": [], "stream": true}` and the client was answered from an empty prompt with a clean 200.
    #
    # Deep, because the rewrites reach into nested structures. Cheap enough at once per request, and once more per replay, which is rare by construction.
    inbound_payload = deepcopy(context.payload)
    try:
        handled = await handle_bounded(chain, context, _routed, deadline_at=client_deadline_at)
    except Exception as error:
        _observe_failed_upstream_response(context, trace, chain, error)
        trace.model = context.resolved_model
        trace.attempts = context.attempt_count
        trace.detail = str(error)
        # A refused crossing is exactly where the losses matter: they name which field the request could not carry, and the error alone rarely does.
        trace.absorb_losses(context)
        # Before the response is written, because `context.payload` is the body upstream refused and nothing downstream keeps it.
        capture_rejection(context, error, request_id=trace.request_id)
        return error_response(
            error,
            inbound_format=route.wire_format.value,
            translated=context.translation_required,
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
        _observe_failed_upstream_response(context, trace, chain, error)
        # Build the record once and give both presentations its message. Classifying again inside `error_response` left the wire on `ErrorInfo.message` while the completion line read the SDK exception's incompatible `__str__`.
        info = describe(error, source_format=route.wire_format.value)
        trace.detail = one_line(info.message)
        # The branch an upstream refusal actually takes: the driver reports it in the outcome rather than raising, so the exception path above never sees one.
        capture_rejection(context, error, request_id=trace.request_id)
        return error_response(
            info,
            inbound_format=route.wire_format.value,
            translated=context.translation_required,
        )
    # Exactly what went out to upstream, taken off the request httpx actually sent rather than re-serialized from the payload. It is not the client's body size: translation rewrites the payload, and the version upstream is billed and tokenized for is the one worth reporting.
    trace.upstream_request_body_bytes = len(response.request.content)
    trace.upstream_protocol = http_label(response.http_version)
    # Snapshot the live socket now. `log_completion` intentionally runs only after the response is released, when httpcore's `client_addr` lookup can already raise `OSError: [Errno 9] Bad file descriptor`.
    trace.upstream_conn = snapshot_upstream_connection(response)

    _hand_over_reasons = frozenset(chain.config.upstream_request_retry.hand_over_stop_reasons)


    def _hand_back(
        error: BaseException | None,
        stop_reason: str,
    ) -> HandBackOutcome | None:
        return hand_back_block(
            chain=chain,
            context=context,
            inbound_payload=inbound_payload,
            wire_format=route.wire_format,
            request_id=trace.request_id,
            error=error,
            stop_reason=stop_reason,
        )

    def _observe_response_event(event: SseEvent) -> None:
        # Resolve on every event rather than closing over the first attempt. `begin_attempt` changes the current observer before a replay prepares or sends, so discarded attempts cannot keep receiving facts.
        attempt = context.current_attempt
        observer = attempt.response_observer if attempt is not None else None
        if observer is not None:
            observer.observe_event(event)

    if context.stream:
        # The instant the driver fixed when it opened this attempt, read rather than recomputed: a second `now + deadline` here would start the clock at the moment the headers came back and quietly grant the attempt a second full lifetime.
        attempt = context.current_attempt
        settings = stream_settings(chain)
        completion_delivery = _CompletionDelivery()
        framer = framer_for(
            handled,
            chain,
            message_id=context.id,
            model=context.resolved_model,
            on_passthrough_terminal_unit=completion_delivery.offer,
        )
        if framer is None:
            # This client leg has no outbound framer, so there is no block to deliver. The upstream stream is read whole and handed over in one write, in the client's own dialect, byte for byte. Ruled 2026-08-22; before this branch existed those bytes went into an assembler that recognised none of them and the client got a 200 with an empty body and no error frame.
            # The same guards in the same order as the block path below, so an idle upstream, an expired attempt and an expired client deadline all still stop this the same way, and the byte counter still sees every byte.
            # What is *not* the same is what the client is told when one fires. The block path writes an error frame; there is no framer for this leg, so the guard's exception ends the response after `one_shot_delivery` sends the upstream bytes that had already arrived — 200, `text/event-stream`, those bytes, and no error frame.
            # This is the same shape as the defect this branch removed, on a narrower path. Deliberate for now: naming an error in a dialect nobody here can write is the same piece of work as finding this dialect's block boundaries, and the ruling deferred that. See `.dev/docs/tmp/260822-ghc-api-conformance-summary.md`.
            one_shot_accounting = _StreamAccounting(
                chain=chain,
                request_id=trace.request_id,
                trace=trace,
                completion=completion,
                status_code=response.status_code,
                context=context,
                completion_delivery=completion_delivery,
            )
            return _AccountedStreamingResponse(
                _tracked_delivery(
                    one_shot_delivery(
                        with_client_deadline_at(
                            _counted_upstream(
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
                                attempt=context.attempt_count,
                            ),
                            deadline_at=client_deadline_at,
                        ),
                        on_complete=completion_delivery.offer,
                    ),
                    one_shot_accounting,
                ),
                one_shot_accounting,
                status_code=response.status_code,
                media_type="text/event-stream",
                close_response=response.aclose,
            )
        # Block-level delivery over the live upstream.
        # The body is never read whole here, so a block goes out while the rest still arrives.
        #
        # The registration deliberately outlives this function. A streaming request has produced nothing at the moment the handler returns — the body is consumed after — so releasing here would drop it off the footer at exactly the point it becomes worth watching.
        # Held rather than passed straight through: the assembler is what reads the upstream's terminal event, so after the stream finishes it is the only thing that knows the token usage and the stop reason.
        # Two guards on the same bytes, and the order decides which one gets to speak: the deadline is outermost so that an idle timeout raised beneath it arrives with its own name rather than being relabelled by whichever guard happens to wrap the other.
        # The second place `upstream_request_deadline` is enforced from — one bound, not two. `await send` returns when the response headers arrive — measured 2026-08-20 — so everything the body does afterwards happens with the driver already off the stack, and until this line nothing was holding the attempt to the life it was given.
        upstream_side = UpstreamSource(
            with_deadline_at(
                with_idle_timeout(
                    response.aiter_bytes(),
                    timeout_seconds=stream_idle_seconds(chain),
                ),
                deadline_at=attempt.deadline_at if attempt is not None else None,
            )
        )
        assembler = assembler_for(handled, hand_over_stop_reasons=_hand_over_reasons)
        accounting = _StreamAccounting(
            chain=chain,
            request_id=trace.request_id,
            trace=trace,
            completion=completion,
            status_code=response.status_code,
            context=context,
            assembler=assembler,
            response_loss_assembler=assembler,
            passthrough=carries_upstream_natively(handled),
            completion_delivery=completion_delivery,
        )

        async def _reopen(replacing: Exception) -> Attempt | None:
            """Another attempt at the same request, wrapped in the same guards as the first.

            `handle` rather than `handle_bounded`: the client deadline is enforced over the body now, and a second `asyncio.timeout` around this would be a second clock for one lifetime — the exact defect the outer guard was added to fix.

            The trace keeps the first attempt's connection identity and byte count. A reader comparing `upstream_conn` across failures is looking for the connection that broke, and overwriting it with the one that recovered erases the thing being looked for.

            `None` while the process is draining. A replay opens a *new* upstream attempt, and a process that has stopped accepting has promised not to take work on: the attempt would extend the drain by its whole length, and if the drain gives up first the client is left with neither answer. `upstream-retry-and-continuation.md` rules it out.

            Scoped to retries and replays, which is narrower than "no new upstream requests": a client request already admitted still opens its *first* attempt during a drain, whether it was queued behind `InFlightLimit` or arrived just before the listener closed. That is what a drain is for — finishing what was accepted — so it is deliberate rather than a gap.

            **What the client gets today is the truncated-stream ending, not a hand-over — and the reason is a gate, not a limitation.** An earlier version of this comment said a hand-over "needs delivered content to hand over"; that is false, and the false reason is what made this look settled. `_hand_over` synthesises its own preamble when the session has not started, so it can perfectly well end a turn nothing was delivered on. What stops it here is its own `committed_count == 0` gate, which a review lifted in an experiment and got a clean hand-over out of exactly this path.

            So whether a drain should be a case that gate lets through is an open product question, not an answered one — and it matters more than it looks: under `full` or `until-tool-use` a whole turn's worth of complete blocks can be sitting in the buffer with `committed_count` still zero, and this ending throws them away where a replay used to recover them. Registered in `deferred.md` §5; do not read the current behaviour here as a decision.
            """
            if chain.active_requests.draining:
                get_logger().info(
                    "upstream_replay_refused_while_draining",
                    request_id=trace.request_id,
                )
                return None
            # What the client sent, not what the last attempt turned it into. See `inbound_payload`.
            context.payload = deepcopy(inbound_payload)
            opened_before = context.attempt_count
            try:
                again = await handle(chain, context, _routed)
            finally:
                # Both written off the same fact — whether `begin_attempt` ran — so an entry here always means an upstream attempt was opened for it, and never the reverse.
                #
                # Not "after `handle` returned", which loses a replacement that opened an attempt and then failed: a review measured two upstream calls recorded as `attempts=1` with nothing replaced. Not "before `handle`" either, which was the fix for that and overshot: `handle` can fail in `shape_request` or translation, before `DirectDriver.run` reaches `begin_attempt`, and the same review measured one upstream call carrying a phantom replacement entry.
                #
                # Every failure, not the first. The same review put a bare `h2.ProtocolError` in the second position of three and watched it vanish behind the first attempt's `RemoteProtocolError`, which is the exact class of failure this whole slice exists to make visible.
                if context.attempt_count > opened_before:
                    trace.attempts = context.attempt_count
                    active.set_attempts(trace.request_id, context.attempt_count)
                    trace.replaced_failures.append(one_line(repr(replacing)))
                    # The replacement attempt now owns response conversion facts even if it fails before obtaining headers and an assembler. The discarded attempt's losses must not become the final request's losses.
                    accounting.response_loss_assembler = None
            reopened = again.outcome.response
            if reopened is None or not again.context.stream:
                return None
            fresh_attempt = again.context.current_attempt
            fresh_assembler = assembler_for(again, hand_over_stop_reasons=_hand_over_reasons)
            # The accounting reads terminal and response-conversion facts off whichever assembler is current, and after this the current one is this.
            accounting.assembler = fresh_assembler
            accounting.response_loss_assembler = fresh_assembler
            # Its own marker, at the same line as the first attempt's: below the counter, above the guards that speak for upstream. A fresh one rather than the first attempt's, so a tear that attempt recorded cannot be read as this one's.
            fresh_upstream = UpstreamSource(
                with_deadline_at(
                    with_idle_timeout(
                        reopened.aiter_bytes(), timeout_seconds=stream_idle_seconds(chain)
                    ),
                    deadline_at=fresh_attempt.deadline_at if fresh_attempt is not None else None,
                )
            )
            return (
                # The client's deadline wraps this one too. It is the same instant, so this is still one clock — but it is a *different iterator*, and the guard the first attempt was wrapped in went out with the stream it was wrapping. Without this a replayed body is bounded only by the attempt's own deadline: measured 2026-08-22, a 2-second client deadline let a replayed body run 6.1 seconds.
                with_client_deadline_at(
                    _counted_upstream(
                        fresh_upstream,
                        chain,
                        trace.request_id,
                        trace,
                        attempt=again.context.attempt_count,
                    ),
                    deadline_at=client_deadline_at,
                ),
                fresh_upstream,
                fresh_assembler,
                delivery_buffer(chain),
            )

        def _hand_back_streaming(
            error: BaseException | None, stop_reason: str
        ) -> dict[str, Any] | None:
            """`_hand_back`, plus the one thing only this path records.

            The recording is here rather than inside it because the two paths mark the same fact in different places: a streaming request's verdict is decided by the accounting object long after this returns, while a buffered one settles its line inline.
            """
            if accounting.handed_over:
                # One per turn. Today the two call sites in `_deliver` each return, so a second call cannot happen — but that is a property of control flow somewhere else, and the guard's whole value is surviving a change to it. This project has already found guards stranded on a path nobody takes.
                return None
            outcome = _hand_back(error, stop_reason)
            if outcome is None:
                return None
            if outcome.trigger is not None:
                accounting.completion.note_upstream_stream_failure(
                    attempt=context.attempt_count,
                    category=outcome.trigger.category,
                    exception_module=outcome.trigger.exception_module,
                    exception_type=outcome.trigger.exception_type,
                    message=outcome.trigger.message,
                )
            # The client is about to get a complete reply it will act on, and the upstream attempt behind it did not finish.
            accounting.handed_over = True
            # Kept because a hand-over is the one ending that swallows its cause: the exception never leaves the delivery generator, so `_StreamAccounting.failure` — which is set from what propagates — stays `None` and the completion line had nothing to say about *why* the turn was handed back. Two reviews found failures reaching the client as a clean `retry` line with no account of them anywhere.
            accounting.handed_over_error = (
                outcome.trigger.legacy_repr or outcome.trigger.exception_type
                if outcome.trigger is not None
                else None
            )
            return outcome.payload

        continuation = ContinuationSupport(
            synthesize=_hand_back_streaming, stop_reasons=_hand_over_reasons
        )

        replay = ReplaySupport(
            # Built by `handle` on the first attempt and kept on the request, so every attempt this reopens draws on the same `max_total` as the ones the driver opened.
            ledger=ledger_for(context, chain),
            eligible=replay_reason,
            reopen=_reopen,
        )
        return _AccountedStreamingResponse(
            _tracked_delivery(
                stream_delivery(
                    # Outermost of the guards, because it is the longest-lived: an attempt's deadline may expire and be replaced by another attempt's, and this one does not move. Its own name on the way out, so the line an operator gets says which setting ended the stream. Until 2026-08-22 there was one clock here and it only reached as far as the response headers.
                    with_client_deadline_at(
                        # The guard measures upstream SSE activity, not the events parsed out of it. Ruled 2026-08-20: a comment frame and a large event still arriving both keep bytes moving while the parser yields nothing, so timing the parser would call a connection that is still transmitting silent — and never false-killing legitimate thinking is what `config.example.yaml` freezes.
                        _counted_upstream(
                            # **The attribution line, and this is why it is here rather than around the whole chain.** Everything below states something about upstream — the raw bytes, and two guards whose entire purpose is to say upstream went quiet or ran out of time. Everything above is this side: `_counted_upstream` is bookkeeping, and a bug in it is ours. Delivery is handed this object alongside the composite and asks it, and only it, what raised. Wrapped around the composite instead, a `KeyError` in the byte counter reached the client as upstream's failure — measured, and the reason this parameter exists.
                            upstream_side,
                            chain,
                            trace.request_id,
                            trace,
                            attempt=context.attempt_count,
                        ),
                        deadline_at=client_deadline_at,
                    ),
                    assembler,
                    upstream=upstream_side,
                    buffer=delivery_buffer(chain),
                    settings=settings,
                    framer=framer,
                    replay=replay,
                    continuation=continuation,
                    on_tear_after_terminal=accounting.note_tear_after_terminal,
                    on_runtime_failure=accounting.note_runtime_failure,
                    observe_event=_observe_response_event,
                    # The client and upstream speak the same dialect exactly when nothing had to be translated. Delivery cannot work this out for itself: one assembler serves both a Responses client directly and a Responses upstream on its way to Anthropic, and the framer is the client's either way.
                    passthrough=not context.translation_required,
                ),
                accounting,
            ),
            accounting,
            status_code=response.status_code,
            media_type="text/event-stream",
            close_response=response.aclose,
        )

    # What upstream sent us, not what we hand onward. A buffered reply is one read, so this is the whole of it.
    trace.received = len(response.content)
    trace.received_known = True
    active.set_upstream_response_bytes(trace.request_id, trace.received)
    attempt = context.current_attempt
    observer = attempt.response_observer if attempt is not None else None
    if observer is not None:
        # Observe the source bytes before the production parser can reject them. Valid objects populate provider facts; malformed/non-object bodies become unavailable with a concrete issue rather than not_applicable.
        observer.observe_body_bytes(response.content)
        _absorb_response_observation(context, trace)
        if context.response_observation is not None and context.response_observation.provider_failed:
            trace.status_override = "fail"
    try:
        parsed_reply: object = response.json()
    except ValueError as error:
        # Upstream answered 200 and called it JSON, and it is not. Until this branch existed the decode error left `_dispatch` entirely: Starlette's error middleware answered `500 text/plain` with the five words `Internal Server Error`, which is the one non-JSON error response the whole proxy produced and carries nothing a client or an operator can act on.
        #
        # `UPSTREAM`, not `INTERNAL`. Nothing here is broken — upstream sent something it should not have — and a 502 sends a reader to the right side of the connection.
        trace.detail = f"upstream answered {response.status_code} with a body that is not JSON"
        return error_response(
            proxy_error(ErrorCategory.UPSTREAM, f"upstream sent a body that is not JSON: {error}"),
            inbound_format=route.wire_format.value,
        )
    if not isinstance(parsed_reply, dict):
        # JSON, but not an object — a bare list or string cannot be a reply on any of these protocols.
        trace.detail = f"upstream answered {response.status_code} with JSON that is not an object"
        return error_response(
            proxy_error(ErrorCategory.UPSTREAM, "upstream sent JSON that is not an object"),
            inbound_format=route.wire_format.value,
        )
    body = cast(dict[str, Any], parsed_reply)
    payload = response_payload(chain, handled, body)
    # Summarised before the hand-over is appended, so the line describes what *upstream* produced.
    # The streaming path reads its summary off the assembler, which never sees the synthesised block;
    # reading this one off the finished payload instead made the same upstream reply report two different things depending on which route carried it — one block and no tools, or two blocks and a tool the model never asked for. That divergence is the thing this whole area exists to remove, and it had been pushed back into the observability surface.
    context.reply = reply_summary(handled, payload)
    # The shape is checked before the block is built, not after. Built first, a body whose `content` was not a list left a warning logged, an id spent and a hand-over silently not happening — the reply going out unchanged with nothing saying so.
    handed = (
        _hand_back(None, str(payload.get("stop_reason", "")))
        if str(payload.get("stop_reason", "")) in _hand_over_reasons
        and isinstance(payload.get("content"), list)
        else None
    )
    if handed is not None:
        # A buffered reply is delivered whole, so there is no position to be in and nothing to replay — but the turn is no more finished than a streamed one upstream cut short, and the client is still the only side that can carry it on. Ruled 2026-08-22, withdrawing the earlier ruling that a non-streaming turn could not be continued.
        #
        # The truncated block was already dropped during translation, where upstream's `status` is still readable. This is the other half of that: dropping content is only defensible because the client is handed a way to get it back.
        content = payload.get("content")
        if isinstance(content, list):
            cast(list[Any], content).append(handed.payload)
            payload["stop_reason"] = TOOL_USE
            # Neither `ok` nor `fail`, for the same reason as the streaming path. Set here rather than by an accounting object, because a buffered request settles its line inline.
            trace.status_override = "retry"
            trace.detail = "turn handed back to the client to continue"
    # Summarised by the route's own reader, which knows both what shape this payload is in and which upstream's words describe it. `None` means this route has no reader yet, and the line then reports nothing about the reply's contents rather than reporting emptiness as fact.
    if context.reply is not None:
        trace.absorb(context.reply)
    # Source observation is the final writer of the compatibility projection. `context.reply` remains available to delivery and hooks, but its client-shaped blocks cannot overwrite the provider's item, usage or vocabulary on the operator record.
    _absorb_response_observation(context, trace)
    if context.response_observation is not None and context.response_observation.provider_failed:
        trace.status_override = "fail"
    # Again, because the reply has only just crossed back: the response half of the translation records its losses during `response_payload` above, after the call that covered the request half.
    trace.absorb_losses(context)
    return JSONResponse(payload, status_code=response.status_code)


@dataclass(slots=True)
class _CompletionDelivery:
    """The one downstream chunk whose accepted send completes this reply.

    `pending` is set while that chunk is being framed. It becomes `accepted` only after `_tracked_delivery` resumes from yielding the same chunk, which `StreamingResponse` does after its ASGI send returns. Keeping the two states separate is what prevents a parsed or merely yielded terminal from being reported as delivered.
    """

    pending: bool = False
    accepted: bool = False

    def offer(self) -> None:
        self.pending = True

    def accept(self, offered: bool) -> None:
        if offered:
            self.pending = False
            self.accepted = True


def _assembler_response_losses(assembler: BlockAssembler[Any] | None) -> list[Loss]:
    if assembler is None:
        return []
    value = getattr(assembler, "response_losses", ())
    if not isinstance(value, tuple):
        return []
    return [loss for loss in cast(tuple[object, ...], value) if isinstance(loss, Loss)]


@dataclass(slots=True)
class _StreamAccounting:
    """One streaming request's slot in the footer and its eventual log line.

    Shared by the delivery generator and the response that carries it, because either one may be the last to run. `finish` is idempotent so whichever gets there first records, and the other is a no-op.
    """

    chain: Chain
    request_id: str
    trace: RequestTrace
    completion: RequestCompletionCoordinator
    status_code: int
    context: RequestContext | None = None
    assembler: BlockAssembler | None = None
    # Attempt-scoped independently of the terminal owner. A replay may open a replacement attempt and fail before it obtains a new assembler; in that gap the discarded attempt's response losses must not become the request's final facts.
    response_loss_assembler: BlockAssembler | None = None
    # Native passthrough can complete early only through its identified terminal batch. A translated leg instead completes by natural drain. Keeping the mode explicit prevents a drained native failure from being mislabelled as a translated completion.
    passthrough: bool = False
    # Set when the turn was handed back to the client as a tool call. Neither `ok` nor `fail` on its own: the client holds a complete reply and will act on it, and the upstream attempt behind it did not finish.
    handed_over: bool = False
    # The once-rendered legacy account of what the hand-over swallowed. `None` on endings that are not failures; settlement must not touch the exception again after payload and typed trigger were built from the same observation.
    handed_over_error: str | None = None
    # Independent of `drained`: a native terminal batch or complete one-shot body may cross the downstream send boundary before the generator gets another turn to observe EOF. Sharing this object with the framer lets the producer identify the right chunk without searching encoded bytes here.
    completion_delivery: _CompletionDelivery = field(default_factory=_CompletionDelivery)
    # Upstream finished the turn and then the connection went. Not a failure — the client holds the whole reply — and recorded anyway, because until this field existed the exception was discarded where it was caught and the request was accounted a plain success. An operator watching a peer that resets every connection after its last frame had nothing at all to look at.
    tore_after_terminal: BaseException | None = None
    done: bool = False
    # How the delivery generator ended. Three endings arrive here indistinguishable — upstream's stream ran out, upstream tore, or delivery was cut short from this side — because none of them saw a terminal event and that is all the assembler records. Naming the wrong one sends whoever reads the line to the wrong half of the system, so each is recorded where it happens instead of guessed here.
    drained: bool = False
    failure: BaseException | None = None
    # Bound to the attempt's positive upstream marker. It rechecks the exception graph after the error-frame send, so a cleanup failure attached to the same root cannot ride through the identity gate unnoticed.
    failure_provenance: Callable[[Exception], bool] | None = None

    def settle(self) -> None:
        """Settle stream-specific facts without publishing the request-wide record."""
        if self.done:
            return
        self.done = True
        # Native and one-shot legs cross only through the completion unit their framer or whole-body adapter explicitly offered. A translated leg has no such marker and instead crosses by natural drain after a normal terminal or hand-over. `drained` alone is not completion: native failure/refusal and unterminated EOF also drain.
        reported = self.assembler.failure if self.assembler is not None else None
        terminal = self.assembler.terminal if self.assembler is not None else None
        translated_drain = bool(
            terminal is not None
            and not self.passthrough
            and self.drained
            and reported is None
            and (self.handed_over or terminal.stop_reason)
        )
        delivered_whole = self.completion_delivery.accepted or (
            self.failure is None and translated_drain
        )
        # A one-shot leg has no assembler and therefore no terminal record. Its whole body is the completion unit; a partial body emitted while propagating a failure never offers that unit and still reaches the ending machinery.
        if self.assembler is None and not delivered_whole:
            self._apply_ending()
        # Read at the end because that is when the upstream's terminal event has either been seen or failed to arrive.
        if self.assembler is not None:
            assert terminal is not None
            # Absorbed either way. Every field on the record was put there by an event that actually arrived, so a stream cut off mid-turn still has a true account of the blocks it did produce — which tools were asked for, how much reasoning came back — and withholding those said nothing about the truncation while losing everything else. What upstream never said is now simply absent from the record rather than standing at a default that reads like an answer.
            self.trace.absorb(terminal)
            # Deliberately still gated on `seen` while the line above is not, and conservatively rather than undecidedly: `reply is not None` currently means the reply finished, hooks and History are written against that, and widening it is a contract change that belongs with the STR-04 slice which needs a failed History anyway. Registered in `.dev/docs/anthropic-responses-bridge/implementation.md`'s 结构怪味登记 so it is reconsidered there rather than rediscovered.
            if terminal.seen and self.context is not None:
                self.context.reply = terminal
            # The reason and a downstream frontier are separate conditions. A translated leg may parse upstream's terminal before it has written the client's `message_delta` and `message_stop`; only its natural drain proves those frames went out. A native passthrough is different: upstream's own terminal rides inside one identified completion unit, and `completion_delivery.accepted` proves that exact chunk's ASGI send returned. Neither `terminal.seen` nor a yield alone is enough.
            # Gating on the reason rather than on `seen` is what separates the one benign Anthropic case from all of these — `message_delta` carries the reason and usage while `message_stop` merely closes, so a stream that drained after the first has told us everything the client was owed. Reporting that as truncated produced a line arguing with itself: `end_turn` followed immediately by a note saying nothing ended.
            # `handed_over` forces the question even on a stream that drained with a reason: a turn upstream ended for want of room drains cleanly and carries `max_tokens`, and would otherwise be reported as an ordinary success — which is the one reading the hand-over exists to prevent.
            if self.handed_over or not (delivered_whole and terminal.stop_reason):
                # Said outright, because absence is not readable. The status was fixed when the response headers arrived and stays 200 however the stream ends; the fields upstream never sent are simply gone; and a reader cannot tell a field this endpoint does not report from one this request never got.
                self._apply_ending()
            if self.tore_after_terminal is not None:
                # `if`, not `elif`. It was an `elif` against the ending above, and the two are not alternatives: a `max_tokens` hand-over sees the terminal event *and* hands the turn back, so both were true and the hand-over's detail took the slot — a review measured the tear reported nowhere on the primary path.
                #
                # No status override either way. This does not decide how the turn came out: an `end_turn` that tears afterwards is still `ok` because the client holds the whole reply, and a `max_tokens` that tears afterwards is still `retry` because the client still has a turn to carry on. What it decides is nothing; it only says what the connection did.
                #
                # Bounded like the other exceptions that reach this line, and for the same reason — upstream chooses the text and `repr` has no limit.
                self.trace.tore_after_terminal = one_line(repr(self.tore_after_terminal))
        if self.context is not None:
            _absorb_response_observation(self.context, self.trace)
            observation = self.context.response_observation
            if observation is not None and observation.provider_failed:
                self.trace.status_override = "fail"
            # Response conversion is attempt-scoped while streaming. A transparent replay replaces the assembler, so publish only the current assembler's facts and overwrite anything the discarded attempt observed before recomputing the request trace.
            self.context.extras[RESPONSE_CONVERSION_LOSSES] = _assembler_response_losses(
                self.response_loss_assembler
            )
            self.trace.absorb_losses(self.context)
        completion_unit = None
        if delivered_whole:
            if self.assembler is None:
                completion_unit = "one_shot_body"
            elif self.completion_delivery.accepted:
                completion_unit = "native_terminal_batch"
            else:
                completion_unit = "translated_drain"
        self.completion.settle(
            status_code=self.status_code,
            upstream_response_bytes=self.trace.upstream_response_body_bytes,
            legacy_duration_s=time.monotonic() - self.trace.started,
            completion_unit=completion_unit,
        )

    def note_runtime_failure(
        self,
        error: Exception,
        upstream: bool,
        provenance: Callable[[Exception], bool] | None = None,
    ) -> None:
        self.failure = error
        self.failure_provenance = provenance if upstream else None
        self.completion.note_wrapped_failure(
            error,
            origin=(
                CompletionFailureOrigin.UPSTREAM
                if upstream
                else CompletionFailureOrigin.WRAPPED
            ),
        )

    def note_tear_after_terminal(self, error: Exception) -> None:
        """Passed to delivery as `on_tear_after_terminal`; see the branch there for when it fires.

        First one wins. An earlier version of this docstring said that only mattered because "a replayed attempt cannot tear after its own terminal", and a review refuted it directly: a replayed attempt reaches this branch and is recorded, with the first attempt's draft discarded as it should be. What actually cannot happen is a *second* one — the branch that calls this breaks the delivery loop, so once a post-terminal tear is recorded no further attempt is opened. The rule is kept anyway, so that a later change to that loop cannot quietly overwrite the earlier account.
        """
        if self.tore_after_terminal is None:
            self.tore_after_terminal = error

    def _apply_ending(self) -> None:
        status, detail = self._ending()
        self.completion.note_stream_ending(
            status,
            detail,
            authoritative=self._ending_is_authoritative(),
        )

    def _ending_is_authoritative(self) -> bool:
        if self.handed_over or self.failure is not None or self.drained:
            return True
        reported = self.assembler.failure if self.assembler is not None else None
        return reported is not None

    def _ending(self) -> tuple[LogStatus, str]:
        """Which of the three ways this stream stopped short, and how much of a problem each is.

        The failure is quoted rather than summarised. It is the durable account of what went wrong: an upstream reset unwinds through delivery into this accounting object, then may be consumed after its error frame's ASGI send returns. A line reporting only that the stream stopped would discard the one fact worth having.

        A client that left is `gone` rather than `fail`, ruled 2026-08-20. Two of these are the proxy's problem and one is not: on a proxy fronting an interactive client, cancelling a turn is routine, and painting every Esc the same red as an upstream reset would bury the resets. `[ OK ]`, which is what those lines used to get, is the other direction of the same mistake — it made a cancelled turn indistinguishable from an answer that arrived.

        The last branch also catches a shutdown cancelling its own in-flight streams, where the client had not gone anywhere and we are the ones leaving. `gone` and the wording both still hold — nobody received the answer, and delivery stopped before upstream finished — but nothing here can tell the two apart, and the line should not claim to.
        """
        if self.handed_over:
            # Both at once, on purpose. Read before the others because they are all true as well — upstream did fail, or drain, or stop — and none of them is what the client got.
            #
            # The cause is quoted when there was one, for the same reason the branch below quotes it: this line is the only account of it that exists anywhere. A hand-over does not re-raise, so nothing downstream ever sees the exception, and `retry` on its own says a turn was handed back without saying what it was handed back from.
            if self.handed_over_error is not None:
                # Bounded for the same reason the replayed failure is, and it was not until a test that asserted the *rendered* line found ten thousand characters of upstream's own text on one of them. `repr` has no limit and upstream chooses the text; both places that put an exception on this line go through the same cut.
                return "retry", f"turn handed back to the client to continue after {self.handed_over_error}"
            return "retry", "turn handed back to the client to continue"
        if self.failure is not None:
            return "fail", f"stream failed before a terminal event: {self.failure}"
        # Before the drain, because **either kind of assembler failure drains**: the delivery loop reports it and returns, so the generator ends normally and `drained` is set. The drain wording is wrong for both of them, in opposite directions. For a refusal it would be false twice over — upstream did send its terminal, and this side is what stopped before reading it. For an upstream failure event it says "no terminal arrived" about a stream that ended with an explicit failure terminal: `response.failed`, `response.cancelled` and Anthropic's `error` are terminals, and the bridge Spec lists them as such. Either way it sends whoever reads the line to the wrong half of the system.
        #
        # Read off the assembler rather than guessed here, which is what the note above asks for; `origin` is the assembler's own record of who decided.
        reported = self.assembler.failure if self.assembler is not None else None
        if reported is not None:
            if reported.origin is FailureOrigin.PROXY_REFUSAL:
                return "fail", f"refused mid-stream: {reported.info.message}"
            return "fail", f"upstream reported a stream failure: {reported.info.message}"
        if self.drained:
            return "fail", "upstream stream ended without a terminal event"
        if self.assembler is not None and self.assembler.terminal.seen:
            return "gone", "delivery stopped before the upstream terminal reached the client"
        if self.completion_delivery.pending:
            return "gone", "delivery stopped after upstream finished"
        return "gone", "delivery stopped before upstream finished"


@dataclass(slots=True)
class _ObservedBackground:
    callback: Callable[[], Awaitable[None]]
    failure: BaseException | None = None

    async def __call__(self) -> None:
        try:
            await self.callback()
        except BaseException as error:
            self.failure = error
            raise


class _AccountedResponse(Response):
    """A transparent ordinary Response whose request record follows its ASGI lifecycle."""

    def __init__(self, wrapped: Response, completion: RequestCompletionCoordinator) -> None:
        # Do not call `Response.__init__`: it would render a second body and rebuild headers/cookies. FastAPI only needs this object to remain a Response subclass; every stateful attribute belongs to the wrapped object.
        self._wrapped = wrapped
        self._completion = completion

    @property
    def status_code(self) -> int:
        return self._wrapped.status_code

    @status_code.setter
    def status_code(self, value: int) -> None:
        self._wrapped.status_code = value

    @property
    def media_type(self) -> str | None:
        return self._wrapped.media_type

    @media_type.setter
    def media_type(self, value: str | None) -> None:
        self._wrapped.media_type = value

    @property
    def charset(self) -> str:
        return self._wrapped.charset

    @charset.setter
    def charset(self, value: str) -> None:
        self._wrapped.charset = value

    @property
    def body(self) -> bytes | memoryview[int]:
        return self._wrapped.body

    @body.setter
    def body(self, value: bytes | memoryview[int]) -> None:
        self._wrapped.body = value

    @property
    def raw_headers(self) -> list[tuple[bytes, bytes]]:
        return self._wrapped.raw_headers

    @raw_headers.setter
    def raw_headers(self, value: list[tuple[bytes, bytes]]) -> None:
        self._wrapped.raw_headers = value

    @property
    def headers(self) -> Any:
        return self._wrapped.headers

    @property
    def background(self) -> Any:
        return self._wrapped.background

    @background.setter
    def background(self, value: Any) -> None:
        self._wrapped.background = value

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self._completion.mark_response_ready(self.status_code)

        async def observed_send(message: Message) -> None:
            self._completion.note_asgi_message_offered(message)
            try:
                await send(message)
            except BaseException as error:
                self._completion.note_send_failure(error)
                raise
            self._completion.note_asgi_message_sent(message)

        original_background = self.background
        observed_background = (
            _ObservedBackground(
                cast(Callable[[], Awaitable[None]], original_background)
            )
            if original_background is not None
            else None
        )
        if observed_background is not None:
            self.background = observed_background

        primary: BaseException | None = None
        try:
            await self._wrapped(scope, receive, observed_send)
        except BaseException as error:
            primary = error
            self._completion.note_wrapped_failure(
                error,
                origin=(
                    CompletionFailureOrigin.BACKGROUND
                    if observed_background is not None
                    and error is observed_background.failure
                    else CompletionFailureOrigin.WRAPPED
                ),
            )
            raise
        finally:
            if observed_background is not None and self.background is observed_background:
                self.background = original_background
            if primary is None and not self._completion.delivery_accepted:
                self._completion.note_missing_terminal()
            self._completion.settle(
                status_code=self.status_code,
                upstream_response_bytes=(
                    self._completion.trace.received
                    if self._completion.trace.received_known
                    else None
                ),
            )
            self._completion.publish()


@dataclass(slots=True)
class _StreamingResponseCleanup:
    content: AsyncGenerator[bytes]
    close_response: Callable[[], Awaitable[None]] | None = None
    done: bool = False

    async def aclose(self) -> None:
        if self.done:
            return
        self.done = True
        content_error: BaseException | None = None
        try:
            await self.content.aclose()
        except BaseException as error:
            content_error = error
        try:
            if self.close_response is not None:
                await self.close_response()
        except BaseException as response_error:
            if content_error is not None:
                raise_with_cleanup_under(content_error, response_error)
            raise
        if content_error is not None:
            raise content_error


class _AccountedStreamingResponse(StreamingResponse):
    """A streaming response that is accounted for even if its body never runs.

    The generator's own `finally` covers every case where delivery started, including a mid-stream disconnect. It does **not** cover a client that disappears before the first chunk is pulled: an async generator that was never iterated has no suspended frame, so closing it runs nothing, and the request would sit in the footer for the life of the process with its clock climbing and no log line ever written. A review reproduced exactly that by failing the `http.response.start` send.

    Overriding `__call__` puts a `finally` outside everything the framework does, which is the only place that survives a failure before the first iteration.
    """

    def __init__(
        self,
        content: AsyncGenerator[bytes],
        accounting: _StreamAccounting,
        *,
        close_response: Callable[[], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(content, **kwargs)
        self._cleanup = _StreamingResponseCleanup(
            content=content,
            close_response=close_response,
        )
        self._accounting = accounting

    async def aclose(self) -> None:
        """Release a prepared response that never crossed into ASGI delivery."""
        await self._cleanup.aclose()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self._accounting.completion.mark_response_ready(self.status_code)

        async def observed_receive() -> Message:
            try:
                message = await receive()
            except Exception as error:
                self._accounting.completion.note_asgi_receive_error(
                    error,
                    phase=InterruptionPhase.RESPONSE_STREAM,
                )
                raise
            if message.get("type") == "http.disconnect":
                self._accounting.completion.note_http_disconnect(
                    phase=InterruptionPhase.RESPONSE_STREAM,
                )
            return message

        async def observed_send(message: Message) -> None:
            self._accounting.completion.note_asgi_message_offered(message)
            try:
                await send(message)
            except BaseException as error:
                self._accounting.completion.note_send_failure(error)
                raise
            self._accounting.completion.note_asgi_message_sent(message)

        original_background = self.background
        observed_background = (
            _ObservedBackground(
                cast(Callable[[], Awaitable[None]], original_background)
            )
            if original_background is not None
            else None
        )
        if observed_background is not None:
            self.background = observed_background

        primary: BaseException | None = None
        try:
            await super().__call__(scope, observed_receive, observed_send)
        except BaseException as error:
            primary = error
            self._accounting.completion.note_wrapped_failure(
                error,
                origin=(
                    CompletionFailureOrigin.BACKGROUND
                    if observed_background is not None
                    and error is observed_background.failure
                    else CompletionFailureOrigin.WRAPPED
                ),
            )
            if isinstance(error, ClientDisconnect):
                _note_disconnect_cleanup(self._accounting.completion, error)
        if observed_background is not None and self.background is observed_background:
            self.background = original_background

        try:
            cleanup_error, cleanup_cancellation = await finish_stream_cleanup(
                None,
                cast(AsyncIterator[bytes], self._cleanup),
                primary=primary,
            )
            if cleanup_error is not None:
                if isinstance(primary, ClientDisconnect):
                    self._accounting.completion.note_secondary_cleanup_failure(
                        cleanup_error
                    )
                else:
                    self._accounting.completion.note_wrapped_failure(
                        cleanup_error,
                        origin=CompletionFailureOrigin.CLEANUP,
                    )
            elif cleanup_cancellation is not None:
                self._accounting.completion.note_wrapped_failure(
                    cleanup_cancellation,
                    origin=CompletionFailureOrigin.CLEANUP,
                )
            if primary is None:
                primary = cleanup_cancellation
            if isinstance(primary, ClientDisconnect):
                return
            if primary is not None:
                if cleanup_error is not None:
                    raise_with_cleanup_under(primary, cleanup_error)
                raise primary
            if isinstance(cleanup_error, ClientDisconnect):
                _note_disconnect_cleanup(self._accounting.completion, cleanup_error)
                return
            if cleanup_error is not None:
                raise cleanup_error
        finally:
            # The inner generator may already have settled. This fallback covers response-start failure where it was never pulled; publication follows both content and response-owner cleanup.
            self._accounting.settle()
            self._accounting.completion.publish()


async def _counted_upstream(
    chunks: AsyncIterator[bytes],
    chain: Chain,
    request_id: str,
    trace: RequestTrace,
    *,
    attempt: int,
) -> AsyncGenerator[bytes]:
    """Count what upstream sends, as it arrives, and forward it untouched.

    This is the number both the footer and the completion line report, because what an operator is watching is the proxy's conversation with upstream. Bytes delivered onward to the client are a different quantity and a much worse indicator: block-level delivery holds a block until it is whole, so a downstream count sits at zero for most of a request and then jumps — which reads as a broken display rather than as the buffering it is.

    Pacing stays bounded rather than retaining every arrival. Request-wide `first_upstream_byte_s`, maximum observed inter-arrival gap and chunk count answer how this side saw the stream progress. The latest body attempt additionally keeps its last chunk, final pull start and body end so a peer EOF after a long final wait can be told from an abrupt one. `upstream_final_pull_s` begins when this iterator actually asks its source again, excluding the assembly and downstream send time between pulls; it still includes scheduling, guards, decoding and transport wait and is not pure socket-idle time.

    The latest-attempt fields reset together when a replayed body opens. End and its derived durations are written only when the final pull reaches EOF or an ordinary upstream error. A cancellation, a close while this generator is suspended at `yield`, or an ordinary cleanup error carrying the active cancellation leaves them absent; otherwise a downstream abort would be recorded as an upstream body ending.

    **Closing this closes the stream under it**, the same way `with_idle_timeout` and `read_events` do. This was the one layer of the production chain that did not, and it was the layer everything else releases through: `read_events` closes the outermost composite and the client deadline closes this one, and the chain stopped here. A client that went away mid-turn therefore left the marker, both guards and the upstream response open until the collector reached them — measured 2026-08-24 against the real five-object composition, where the raw source stayed open across a tick and only an explicit close released it. A cancellation propagates all the way down **when the close succeeds**, which is why the client deadline's own path was never the one that leaked and an ordinary early close was. A source with no `aclose` is left alone, and a close that itself fails is ordered against whatever was already propagating — both by `finish_stream_cleanup`, which is what this delegates the whole of cleanup to.
    """
    trace.received_known = True
    trace.begin_upstream_body_timing(attempt)
    previous: float | None = None
    try:
        while True:
            trace.note_upstream_pull_started(time.monotonic())
            try:
                chunk = await anext(chunks)
            except StopAsyncIteration:
                trace.note_upstream_end(time.monotonic())
                break
            except Exception as error:
                current_task = asyncio.current_task()
                replaced_cancellation = (
                    find_cancellation(error)
                    if current_task is not None and current_task.cancelling() > 0
                    else None
                )
                if replaced_cancellation is None:
                    trace.note_upstream_end(time.monotonic())
                raise
            now = time.monotonic()
            if chunk and trace.first_upstream_byte_s is None:
                trace.first_upstream_byte_s = now - trace.started
            if previous is not None:
                gap = now - previous
                if trace.upstream_max_gap_s is None or gap > trace.upstream_max_gap_s:
                    trace.upstream_max_gap_s = gap
            previous = now
            trace.note_upstream_chunk(now)
            # Every arrival, not only the ones carrying bytes, so a gap here means what a gap means to `with_idle_timeout` underneath — that guard resets on any item, and a count using a different rule would put the two numbers on scales that cannot be compared. httpx's `aiter_bytes` drops empty chunks anyway, so on the production chain the two rules agree.
            trace.upstream_chunks += 1
            trace.received += len(chunk)
            chain.active_requests.add_upstream_response_bytes(request_id, len(chunk))
            yield chunk
    finally:
        # Same order as `_AccountedStreamingResponse.__call__` above, and by the same call rather than by a second copy of the reasoning: the exit that got us here is the one that propagates, with the close failure chained under it. Raising straight from a `finally` replaces it, and a review measured what that costs on the real composition — the byte counter's own bug did not merely lose priority, it left the chain entirely, because the generator below raises its close error with *its* `GeneratorExit` as context rather than with what was propagating. A cancellation is the same story: replaced by a close failure, the task is no longer cancelled.
        #
        # `GeneratorExit` is normalised to no primary at all, exactly as `_events_with_ping` does. It is not an ending anyone needs reported — it *is* the close — and treating it as the primary hands it back to the async-generator machinery, which swallows whatever is chained under it: measured, a close failure under a `GeneratorExit` arrived at the caller as `raised=None`.
        #
        # Delegated rather than hand-rolled so that cleanup is shielded from a *second* cancellation the way `finish_stream_cleanup` shields it. Cancelling a task twice while this close is in flight otherwise interrupts the close itself, and the release this whole `finally` exists for does not happen.
        primary = sys.exception()
        if isinstance(primary, GeneratorExit):
            primary = None
        cleanup_error, cleanup_cancellation = await finish_stream_cleanup(
            None, chunks, primary=primary
        )
        # `is None` rather than `or`, which conflates "is there one" with "which one wins". A `BaseException` subclass may define a falsey `__bool__`, and `or` then hands the exit to the cleanup failure or to a cancellation instead — measured right here: a falsey primary came out of this generator as the `CleanupError`, demoted to its own context. `keepalive.py` states the same priority and had the same bug.
        if primary is None:
            primary = cleanup_cancellation
        if primary is not None:
            if cleanup_error is not None:
                raise_with_cleanup_under(primary, cleanup_error)
            if cleanup_cancellation is not None:
                raise primary
        elif cleanup_error is not None:
            raise cleanup_error


async def _tracked_delivery(chunks: AsyncGenerator[bytes], accounting: _StreamAccounting) -> AsyncGenerator[bytes]:
    """Forward delivery, account for its ending, and contain a reported upstream failure after its error frame is sent.

    `finally` rather than a trailing statement, because a client that disconnects mid-stream cancels this generator — and a request that vanishes from the footer, or never gets its log line, only when something has gone wrong is exactly backwards.

    The explicit `finish_stream_cleanup` closes the inner delivery generator for the same reason that generator closes its own source: a bare `async for` closes nothing. It is explicit rather than an `aclosing` context so a runtime delivery exception and an exception raised only by `aclose()` remain two different facts; merging them let cleanup revoke an already accepted terminal send.

    Cleanup finishes before settle and publication, while settlement itself precedes cleanup-failure classification. That ordering preserves both sides of the contract: resources are released before the completed record is visible, and a completion unit whose send already returned remains monotonically accepted while a late cleanup failure becomes post-delivery evidence.
    """
    cancellation_cleanup_error: BaseException | None = None
    replaced_cancellation: asyncio.CancelledError | None = None
    accepted_upstream_failure: Exception | None = None
    try:
        async for chunk in chunks:
            completion_offered = accounting.completion_delivery.pending
            # `note_runtime_failure` runs immediately before the error frame is formed. Snapshot its exact upstream exception beside that frame, so only this chunk's successful send can make the later re-raise consumable.
            upstream_failure_offered = (
                accounting.failure
                if isinstance(accounting.failure, Exception)
                and accounting.failure_provenance is not None
                and accounting.failure_provenance(accounting.failure)
                else None
            )
            yield chunk
            # `StreamingResponse` resumes this generator only after `await send` returns for the yielded body. If send raises or disconnect cancellation closes us at the yield, these lines are skipped and neither a merely parsed terminal nor a merely framed upstream failure becomes accepted.
            accounting.completion_delivery.accept(completion_offered)
            if upstream_failure_offered is not None:
                accepted_upstream_failure = upstream_failure_offered
        # Reached only when the whole delivery generator ran out on its own. A client that goes away closes this generator at a `yield`, and GeneratorExit unwinds straight past this line to the `finally`; a completion unit whose ASGI send returned can now independently meet the same application-visible completion boundary despite that local abort.
        accounting.drained = True
    except Exception as error:
        # A cancellation can enter a suspended `anext()` and be replaced by the source's failing `finally`. That replacement is still cleanup, identified by the cancellation in its exception chain; treating it as runtime failure revoked terminal units whose send had already returned.
        current_task = asyncio.current_task()
        replaced_cancellation = (
            find_cancellation(error)
            if current_task is not None and current_task.cancelling() > 0
            else None
        )
        if replaced_cancellation is not None:
            cancellation_cleanup_error = error
        else:
            if accounting.failure is not error:
                # One-shot and unexpected local paths have no inner source marker. The normal block path records the exact upstream/local origin through `on_runtime_failure` before the exception reaches here.
                accounting.note_runtime_failure(error, False)
            provenance = accounting.failure_provenance
            if (
                error is not accepted_upstream_failure
                or provenance is None
                or not provenance(error)
            ):
                raise
            # The same, still-unmodified upstream exception already produced an error frame whose ASGI send returned. Its operational facts remain in accounting; propagating it farther would add only Uvicorn's duplicate application traceback.
    finally:
        primary = sys.exception()
        if isinstance(primary, GeneratorExit):
            primary = None
        if primary is None:
            primary = replaced_cancellation
        cleanup_error, cleanup_cancellation = await finish_stream_cleanup(
            None,
            chunks,
            primary=primary,
        )
        if cancellation_cleanup_error is not None:
            if cleanup_error is not None and cleanup_error is not cancellation_cleanup_error:
                cleanup_error = BaseExceptionGroup(
                    "stream cleanup failed",
                    [cancellation_cleanup_error, cleanup_error],
                )
            else:
                cleanup_error = cancellation_cleanup_error
        # Settle the runtime ending and monotonic completion frontier before classifying cleanup. Once a native terminal send returned, the cleanup failure is post-delivery evidence, not a reason to erase that historical fact.
        accounting.settle()
        primary_cancellation = (
            find_cancellation(primary) if primary is not None else None
        )
        if (
            primary_cancellation is not None
            and not accounting.completion.delivery_accepted
        ):
            accounting.completion.note_wrapped_failure(
                primary_cancellation,
                origin=CompletionFailureOrigin.WRAPPED,
            )
        if cleanup_error is not None:
            if (
                primary_cancellation is not None
                and not accounting.completion.delivery_accepted
            ):
                accounting.completion.note_secondary_cleanup(cleanup_error)
            accounting.completion.note_wrapped_failure(
                cleanup_error,
                origin=CompletionFailureOrigin.CLEANUP,
            )
        elif cleanup_cancellation is not None:
            accounting.completion.note_wrapped_failure(
                cleanup_cancellation,
                origin=CompletionFailureOrigin.CLEANUP,
            )
        if primary is None:
            primary = cleanup_cancellation
        if primary is not None:
            if cleanup_error is not None:
                raise_with_cleanup_under(primary, cleanup_error)
            if cleanup_cancellation is not None:
                raise primary
        elif cleanup_error is not None:
            raise cleanup_error
