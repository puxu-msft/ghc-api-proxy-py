"""What a request accumulates on its way through, and the line it becomes.

Split out of `app.server.pipeline_app` on 2026-08-22. It had grown to a third of that module while being neither routing nor dispatch, and the tests had already filed it here — `tests/unit/observability/test_request_log_file.py` was importing three of these names out of the HTTP surface by their private spellings.

`RequestTrace` is mutable and written to from several points in a request's life; `RequestLine` in `request_log` is the finished record a renderer reads. They are deliberately two types, and today the second is built from the first by copying 31 fields one at a time — a mechanical copy that this move puts inside one package but does not remove. Collapsing it is the next step, registered in `.dev/docs/server-layout/`.
"""

import time
from dataclasses import dataclass, field
from typing import Any, cast

from app.core.chain import Chain
from app.observability.logging import get_logger
from app.observability.metrics import TRANSLATION_LOSSES
from app.observability.request_log import (
    LogStatus,
    RequestLine,
    format_completion_line,
    status_for,
)
from app.observability.request_log_file import write_request_record
from app.pipeline.delivery.assembling import ReplyDialect, Terminal
from app.pipeline.request import RequestContext
from app.pipeline.response_action import ClientActionRequirement
from app.pipeline.response_observation import JsonAvailability, ResponseObservation
from app.pipeline.translation_driver.semantic import Loss

# The logger every per-request line goes under. Named so a filter, a test or a log shipper can select this process's own lines out of a stream that also carries `httpx` and `uvicorn` — a substring match on the message cannot, because `httpx` narrates every upstream call with the same path in it.
REQUEST_LOGGER = "app.request"


# What a transport read could not produce, as distinct from what it produced as nothing. Both used to come back `None`, and the snapshot then rendered both as `""` — so a row that failed to read the socket was byte-for-byte a row whose transport never had an address to give.
UNREADABLE = object()


def _extra_info(network_stream: Any, name: str) -> Any:
    """Read one live transport fact without letting observability affect the request.

    Returns `None` when the transport simply has no such fact, and `UNREADABLE` when asking for it raised. The two are different answers to a forensic reader — the first is how a mock or a plain HTTP/1.1 exchange normally looks, the second means this row's identity is missing because something went wrong — and collapsing them is what `snapshot_upstream_connection` is careful not to do.
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

    Callers filter with `_readable` first, so there is no `None` case to render — an earlier version answered `""` for it, which is the exact conflation `snapshot_upstream_connection` exists to avoid, sitting one call deeper.
    """
    if isinstance(value, tuple):
        parts = cast(tuple[object, ...], value)
        if len(parts) >= 2:
            host, port = str(parts[0]), parts[1]
            return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return str(cast(object, value))


def snapshot_upstream_connection(response: Any) -> dict[str, Any]:
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
class RequestTrace:
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
    # What each replayed attempt was replacing, in the order the replays were opened. A transparent replay is invisible to the client by design, and until this existed it was invisible to the record too: a successful replacement neither hands over nor re-raises, so `retries=N` was the whole account and the exceptions that caused it were gone.
    #
    # A list rather than the first one. A review put three attempts on the wire with a different failure in the second position and watched it disappear behind the first — and "the later ones failed the same way" was an assumption nothing checked. Empty means no replacement was ever opened; it does **not** mean no second upstream request was made, because a replacement that fails to produce a stream is appended here and then returns.
    replaced_failures: list[str] = field(default_factory=list[str])
    # Upstream dropped the connection after finishing the turn, already cut to the line's bound. Its own field rather than a case inside `detail`, because it is not an ending — it coexists with whatever the ending turns out to be, and a `max_tokens` hand-over is the case that proved it: a review measured the tear vanishing behind the hand-over's detail on the primary path.
    tore_after_terminal: str = ""
    detail: str = ""
    # What the HTTP status cannot say. A streaming status is fixed the moment the response headers arrive, so everything that happens over the next several minutes — the stream stopping mid-turn, upstream tearing, the client leaving — leaves it at 200. `None` means the status code is the whole story.
    status_override: LogStatus | None = None
    started: float = 0.0
    started_at: str = ""
    first_upstream_byte_s: float | None = None
    upstream_max_gap_s: float | None = None
    upstream_chunks: int = 0
    upstream_request_body_bytes: int | None = None
    received: int = 0
    # Distinguishes an observed empty upstream body from a request that never reached a response body at all.
    received_known: bool = False
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
    response_observation: ResponseObservation | None = None

    @property
    def upstream_response_body_bytes(self) -> int | None:
        """Decoded upstream response-body bytes, preserving observed zero."""
        return self.received if self.received_known else None

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

    def absorb_response(self, observation: ResponseObservation) -> None:
        """Take provider-side facts without making them part of delivery control.

        The legacy flat fields remain a compatibility projection. The observation itself is the richer source used by the Responses renderer now and by the versioned request record in the next slice.
        """
        self.response_observation = observation
        if observation.source_protocol != "openai-responses":
            return
        # A replacement attempt makes every response fact from the attempt it replaced stale, including the legacy projection already absorbed from its assembler. Rebuild that projection from the current observer rather than layering new optional facts over old concrete ones.
        self.usage = {}
        self.terminal_seen = False
        self.stop_reason = ""
        self.blocks = 0
        self.tools = ()
        self.thinking = ()
        self.dialect = ReplyDialect.RESPONSES
        if observation.terminal_seen is not None:
            self.terminal_seen = observation.terminal_seen
        if observation.usage is not None:
            normalized = observation.usage.normalized
            usage = {
                key: value
                for key, value in (
                    ("input_tokens", normalized.input_tokens),
                    ("cache_read_input_tokens", normalized.cache_read_input_tokens),
                    (
                        "cache_creation_input_tokens",
                        normalized.cache_creation_input_tokens,
                    ),
                    ("output_tokens", normalized.output_tokens),
                )
                if value is not None
            }
            if usage:
                self.usage = usage
        items = observation.output_items
        if items is not None:
            self.blocks = len(items)
            self.tools = tuple(
                item.name or ""
                for item in items
                if item.client_action.requirement is ClientActionRequirement.REQUIRED
            )
            self.thinking = tuple(
                "txt"
                if item.reasoning.has_readable_summary
                else "enc"
                for item in items
                if item.type == "reasoning"
                and (
                    item.reasoning.has_readable_summary
                    or item.reasoning.has_encrypted_content
                )
            )
        required = bool(
            items
            and any(
                item.client_action.requirement is ClientActionRequirement.REQUIRED
                for item in items
            )
        )
        failure_status = (
            observation.terminal_event_type.removeprefix("response.")
            if observation.terminal_event_type
            in {"response.failed", "response.cancelled"}
            else observation.status
        )
        if failure_status in {"failed", "cancelled"}:
            self.stop_reason = failure_status
            if not self.detail and observation.error_summary is not None:
                message = observation.error_summary.message
                if message:
                    self.detail = f"provider response failed: {message}"
        elif (
            observation.error_summary is not None
            or observation.error.availability is JsonAvailability.OBSERVED
        ):
            self.stop_reason = "error"
            if not self.detail and observation.error_summary is not None:
                message = observation.error_summary.message
                if message:
                    self.detail = f"provider response failed: {message}"
        elif observation.status == "completed":
            self.stop_reason = "tool_use" if required else "end_turn"
        elif observation.status == "incomplete":
            self.stop_reason = (
                "max_tokens"
                if observation.incomplete_reason == "max_output_tokens"
                else observation.incomplete_reason or "incomplete"
            )

    def absorb_losses(self, context: RequestContext) -> None:
        """Take whatever translation has recorded so far onto the line.

        Recomputes from `context.extras` rather than appending, so calling it again after more translation has happened is correct and calling it twice with nothing in between changes nothing. That is what lets it be called at each point a translation has just finished instead of at one point that would have to be the last.

        Called from every `return` in `_dispatch` that has a `context` to read, because no single site sits after all of them. That is the arrangement's cost and it has already been paid once: the count-tokens failure path was added to this list only after a review found it returning `losses: []` for a request whose translation had recorded some. A `return` added later without a call here reports nothing rather than reporting a lie — an empty tuple is also what a lossless crossing looks like — so the omission is invisible, which is why the rule is stated here rather than a count that drifts.
        """
        self.losses = _translation_losses(context)


def request_line_from_trace(
    trace: RequestTrace,
    status_code: int | None,
    *,
    upstream_response_body_bytes: int | None,
    duration_s: float | None = None,
) -> RequestLine:
    """Detach the legacy display/JSON projection from the mutable request trace."""
    return RequestLine(
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
        duration_s=(time.monotonic() - trace.started if duration_s is None else duration_s),
        first_upstream_byte_s=trace.first_upstream_byte_s,
        upstream_max_gap_s=trace.upstream_max_gap_s,
        upstream_chunks=trace.upstream_chunks,
        bytes_in=trace.upstream_request_body_bytes,
        bytes_out=upstream_response_body_bytes,
        usage=dict(trace.usage),
        terminal_seen=trace.terminal_seen,
        stop_reason=trace.stop_reason,
        blocks=trace.blocks,
        tools=tuple(trace.tools),
        thinking=tuple(trace.thinking),
        count_provider=trace.count_provider,
        count_provider_reason=trace.count_provider_reason,
        dialect=trace.dialect,
        attempts=trace.attempts,
        replaced_failures=tuple(trace.replaced_failures),
        tore_after_terminal=trace.tore_after_terminal,
        detail=trace.detail,
        upstream_conn=dict(trace.upstream_conn),
        losses=tuple(dict(loss) for loss in trace.losses),
    )


def log_completion(
    chain: Chain,
    trace: RequestTrace,
    status_code: int | None,
    *,
    upstream_response_body_bytes: int | None,
) -> None:
    """Write the one line that says this request happened.

    Emitted here rather than inside the handler because every exit path — a rejected body, a routing refusal, an upstream failure, a delivered answer, and an exception on its way out through `_serve` — has to produce exactly one, and the handler has a return for each of them and no say in the last.
    """
    line = request_line_from_trace(
        trace,
        status_code,
        upstream_response_body_bytes=upstream_response_body_bytes,
    )
    status = status_for(status_code, override=trace.status_override)
    # Counted here rather than where the loss is recorded, so the count and the record are produced from the same tuple and cannot disagree about what this request lost.
    # One increment per request per kind, not per loss. A request carrying screenshots records one `block-not-carried` per block -- 30 of them in a measured case -- and counting each would make the rate track how many blocks a conversation had rather than how often a crossing loses something. The record keeps every one; the counter answers "how many requests were affected".
    for direction, code in sorted({(loss["direction"], loss["code"]) for loss in line.losses}):
        TRANSLATION_LOSSES.labels(direction=direction, code=code).inc()
    write_request_record(line, status=status)
    get_logger(REQUEST_LOGGER).info(
        format_completion_line(
            line,
            status=status,
            unicode=chain.capabilities.unicode,
            color=chain.capabilities.color,
            response_observation=trace.response_observation,
        ),
        status=status,
    )
