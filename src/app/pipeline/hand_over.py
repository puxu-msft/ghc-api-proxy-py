"""What happens when a turn cannot be finished: whose budget pays, and what the client is handed.

Split out of `app.server.pipeline_app` on 2026-08-22. Both decisions here are domain ones — which failures another attempt could answer, and what an unfinishable turn looks like to a client that can carry it on — and they were being made inside the HTTP surface. `D-ARCH = B` puts retry and continuation with the driver, not with the edge, and a policy that only the edge can reach is a policy the driver cannot honour.

`replay_reason` closed over nothing at all, which is the clearest sign it never belonged to a request handler. `hand_back_block` closed over five locals; they are parameters now, which is also what makes it testable without an ASGI request.
"""

from asyncio import CancelledError
from typing import Any, cast
from uuid import uuid4

from h2.events import ConnectionTerminated, StreamReset
from h2.exceptions import H2Error

from app.core.chain import Chain
from app.errors import ErrorCategory
from app.model_provider.upstream_errors import normalize_upstream_error
from app.observability.logging import get_logger
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.retry import RetryReason, reason_for
from app.streaming.deadline import ClientDeadlineError, StreamDeadlineError
from app.streaming.idle_timeout import StreamIdleTimeoutError

# What a continuable failure is called when it is handed to the client. Keyed on the reason that decided it was continuable, rather than classified a second time: `classify_error` does not know the pipeline's own exception types, so a transport tear reached it as a statusless `UpstreamError` and came back `internal` — while the retry path, looking at the same event, called it `network`. Two taxonomies for one failure is two answers.
CATEGORY_FOR_REASON = {
    RetryReason.NETWORK: ErrorCategory.NETWORK,
    RetryReason.SERVER_ERROR: ErrorCategory.UPSTREAM,
    RetryReason.GITHUB_TOKEN_EXPIRED: ErrorCategory.AUTH,
}


def client_message_count(payload: dict[str, Any]) -> int:
    """How many messages the client sent, as the client counted them.

    Read off the inbound body rather than the translated one. On the Responses leg a single Anthropic message becomes several items — reasoning, message, function call, function call output — so the two numbers are not the same and only one of them advances by a fixed amount per turn.
    """
    messages = payload.get("messages")
    return len(cast(list[Any], messages)) if isinstance(messages, list) else 0


def replay_reason(error: Exception) -> RetryReason | None:
    """Which budget a torn body draws on, or `None` when no second attempt could answer it.

    The taxonomy lives here rather than in delivery, which has no business importing it. A transport tear and either of the two guards over the body are all failures another attempt could answer; a conversion error, a refusal and anything this proxy raised about itself are not. `normalize_upstream_error` is the same mapping the driver's own retries are decided by, so a body that tears is judged exactly as a connection that tears before the headers.

    The client deadline is named and refused rather than left out. Delivery does answer it before ever asking — but only once the response has opened, and that condition is not this function's to rely on. It held today because `normalize_upstream_error` happens not to recognise the type, which is a coincidence and not a design.
    """
    if isinstance(error, ClientDeadlineError):
        return None
    if isinstance(error, StreamIdleTimeoutError | StreamDeadlineError):
        return RetryReason.NETWORK
    known = normalize_upstream_error(error)
    return reason_for(known) if known is not None else None


# How much of one exception's own text survives, and how many links of the chain are walked. Both are presentation limits: the string is read by a person in the MCP server's journal and by the model in its own transcript, and an upstream error body can be arbitrarily long. Truncation says so rather than trailing off, because a message that was cut and a message that ended read the same otherwise.
#
# Six links rather than four. A real connection reset arrives as `httpx2.ReadError` and the only informative link is the fourth — `httpx2.ReadError('') -> httpcore2.ReadError('') -> anyio.BrokenResourceError('') -> ConnectionResetError('[Errno 104] Connection reset by peer')`, measured 2026-08-23 against a real socket in `.dev/docs/upstream/retry-and-continuation/reports/260823-handover-error-shapes.md`. A bound that stops exactly at the informative link is a bound that loses it the first time a library adds a wrapper.
_MAX_LINK_CHARS = 240
_MAX_LINKS = 6


def one_line(text: str) -> str:
    """Collapse whitespace, and say so when the text was cut rather than letting it trail off.

    Public because the completion line needs the same bound for the same reason: it renders a replayed failure's `repr` inline, and an upstream error carries whatever text upstream chose to send.
    """
    flat = " ".join(text.split())
    if len(flat) <= _MAX_LINK_CHARS:
        return flat
    return f"{flat[:_MAX_LINK_CHARS]}… (+{len(flat) - _MAX_LINK_CHARS} more chars)"


def _chain(error: BaseException) -> tuple[list[BaseException], bool]:
    """The exception and what it was raised from, outermost first, and whether the walk stopped short.

    `__context__` is followed only where `__cause__` is absent and the context was not suppressed, which is the same reading `app.streaming.sse` already applies. It matters here because the informative link is often not the outermost one: a real connection reset arrives as `httpx2.ReadError('')` and says nothing until the fourth link, an `OSError` reading `[Errno 104] Connection reset by peer`.

    `is not None` rather than truthiness. Python's own rule for an explicit cause is `__cause__ is not None`, and an exception subclass may define `__bool__` — `raise X from falsy_cause` would otherwise skip the cause the author named and follow the incidental context instead, or stop dead where the context was suppressed. Nothing structurally excludes a custom exception type here: the delivery `try` catches whatever a framer raises.
    """
    links: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if len(links) == _MAX_LINKS:
            return links, True
        seen.add(id(current))
        links.append(current)
        if current.__cause__ is not None:
            current = current.__cause__
        else:
            current = None if current.__suppress_context__ else current.__context__
    return links, False


def _h2_gloss(links: list[BaseException]) -> str | None:
    """What an HTTP/2 event in the chain actually says, in words.

    httpcore raises `RemoteProtocolError(event)` for these, and httpx re-raises `mapped(str(exc)) from exc`, so the event object itself survives one link down as `args[0]` while only its `repr` reaches the top. That `repr` prints `error_code` through `IntEnum.__str__`, i.e. as a bare number — so the one word that distinguishes an upstream graceful shutdown from an upstream cancelling this very stream is on the object and invisible in the text. Read on 2026-08-23, all four records the MCP server's journal then held were one of those two reprs; that is a snapshot of one file, not a rate.

    Read off the event's own enum rather than a table kept here, so a code this project has never seen still comes out named. Absent or unrecognised, the gloss is simply omitted: it is an explanation of the text beside it, never the only account of what happened.
    """
    for link in links:
        for argument in link.args:
            if isinstance(argument, ConnectionTerminated):
                return f"HTTP/2 GOAWAY from upstream, error_code={_code_name(argument.error_code)}"
            if isinstance(argument, StreamReset):
                # `remote_reset` says which side put the RST_STREAM frame on the wire, and that is all it is read as here. It is not attribution of the decision: h2 also raises `remote_reset=False` when it terminates a stream itself over a protocol or flow-control error the peer provoked (`h2/stream.py`, the `FLOW_CONTROL_ERROR` path).
                who = "from upstream" if argument.remote_reset else "sent by this proxy"
                return f"HTTP/2 RST_STREAM {who} on stream {argument.stream_id}, error_code={_code_name(argument.error_code)}"
    return None


def _code_name(code: object) -> str:
    """The HTTP/2 error code's name, or the raw value when h2 handed over something that has none."""
    name = getattr(code, "name", None)
    return name if isinstance(name, str) else str(code)


def _link_text(link: BaseException) -> str:
    """One exception's own account of itself, with the one shape that lies about itself repaired.

    `h2.exceptions.StreamClosedError` and `NoSuchStreamError` assign `self.stream_id` without calling `super().__init__`, but `BaseException.__new__` has already put the constructor argument in `args` — so `str()` on them is a bare stream id. A `message` reading `3` is worse than an empty one: an empty field is visibly missing, while `3` looks like something upstream said. Measured 2026-08-23, `.dev/docs/upstream/retry-and-continuation/reports/260823-handover-error-shapes.md` §2.2(g).
    """
    text = str(link)
    stream_id = getattr(link, "stream_id", None)
    if isinstance(link, H2Error) and isinstance(stream_id, int) and text == str(stream_id):
        return f"stream {stream_id}"
    return one_line(text)


def _asyncio_timeout_plumbing(links: list[BaseException]) -> set[int]:
    """Which links are the two `asyncio.timeout` raises around a guard, by position in the chain.

    `asyncio.timeout` ends its scope by cancelling the task and converting that into `TimeoutError`, so a guard built on it arrives as exactly three adjacent links — a `TimeoutError` subclass carrying its own message, then a bare `builtins.TimeoutError()`, then an empty `asyncio.CancelledError()`. Measured for `StreamDeadlineError` and `StreamIdleTimeoutError` in `.dev/docs/upstream/retry-and-continuation/reports/260823-handover-error-shapes.md` §2.2(a)/(b). Only the second and third are suppressed; the guard itself is the account.

    Matched as that adjacency and nothing looser. A review took an earlier version — a flag reading "some `TimeoutError` was rendered earlier" — and showed it wrong in both directions at once: it swallowed a `CancelledError` three links below an unrelated timeout, and it *failed* to suppress the real plumbing when a wrapper repeated the guard's message, because the guard then rendered as a bare type and never set the flag. Reading each link's own text rather than whether that text was fresh is what closes the second half.
    """
    found: set[int] = set()
    for index in range(len(links) - 2):
        guard, converted, cancelled = links[index], links[index + 1], links[index + 2]
        if (
            isinstance(guard, TimeoutError)
            and _link_text(guard)
            and type(converted) is TimeoutError
            and not _link_text(converted)
            and type(cancelled) is CancelledError
            and not _link_text(cancelled)
        ):
            found.update({index + 1, index + 2})
    return found


def describe_error(error: BaseException) -> str:
    """One line naming what broke, why, and — for the transport failures this actually sees — what the protocol event meant.

    Three things `str(error)` alone does not give, all of them measured rather than supposed (`.dev/docs/upstream/retry-and-continuation/reports/260823-handover-error-shapes.md`):

    - **The type.** `<ConnectionTerminated …>` does not say it arrived as an `httpx2.RemoteProtocolError`, and `RemoteProtocolError` alone would not say which of the three libraries' versions of that name it was.
    - **A guarantee of content.** A real connection reset arrives as `httpx2.ReadError` whose `str()` is empty, and a bare `h2.ProtocolError()` is empty too — an empty `message` is the one value that tells a reader nothing at all.
    - **The chain.** The link that carries the reason is routinely not the one that was caught: for that same reset it is the fourth.

    A link earns its place by saying something not already said. Three cases, and each was decided by a failure the other two do not cover:

    - **Fresh text** → shown with its type. The ordinary case.
    - **Text already shown, by a different class** → the type alone. Otherwise `RuntimeError('permission denied') from PermissionError('permission denied')` comes out as the `RuntimeError` and loses the one word saying what kind of failure it was, which an independent review built as a counterexample. An h2 event mapped through httpcore into httpx repeats its text too, and there the class name repeats with it, so that link is dropped entirely. That is the one repetition measured so far; a torn HTTP/1.1 body repeats h11's text instead, and a real reset repeats nothing because the outer links are empty.
    - **No text at all** → the type, unless it is one of the two links `asyncio.timeout` inserts under a guard that already named itself. Both deadline guards arrive as `StreamDeadlineError -> TimeoutError() -> CancelledError()`, and those two inner links are how the guard is implemented rather than anything that happened to the turn; printing them invites reading a timeout that already named itself as a cancellation. Everything else keeps its type, because where the outer links are silent — a real connection reset opens with two — the inner types are all there is until the `OSError` at the bottom.

    That last suppression is deliberately tied to the one mechanism that was measured, matched as an adjacency rather than a mood — see `_asyncio_timeout_plumbing`. Two earlier versions were both answered with counterexamples: dropping every silent link once anything had spoken loses the `PermissionError` in `RuntimeError('wrapper failed') from PermissionError()`, and remembering merely that *a* timeout was rendered swallows a genuine `CancelledError` several links below an unrelated one.

    Freshness of a class is judged on `__qualname__`, not on the full dotted path: `httpx2.ReadError` wrapping `httpcore2.ReadError` is one failure described twice by two libraries, and that is the case worth collapsing. Two same-named exceptions from genuinely unrelated modules would collapse too. That is deliberate, and it has only ever been produced by construction.
    """
    links, truncated = _chain(error)
    plumbing = _asyncio_timeout_plumbing(links)
    rendered: list[str] = []
    seen_text: set[str] = set()
    seen_class: set[str] = set()
    for position, link in enumerate(links):
        text = _link_text(link)
        name = f"{type(link).__module__}.{type(link).__qualname__}"
        fresh_class = type(link).__qualname__ not in seen_class
        fresh_text = bool(text) and text not in seen_text
        if fresh_text:
            rendered.append(f"{name}: {text}")
        elif fresh_class and position not in plumbing:
            rendered.append(name)
        else:
            continue
        seen_class.add(type(link).__qualname__)
        if text:
            seen_text.add(text)
    described = "; caused by ".join(rendered)
    if truncated:
        # Named rather than left to trail off, for the same reason a cut message says how much it lost: a chain that ended and a chain that was cut are otherwise the same string.
        described = f"{described}; caused by … (chain continues past {_MAX_LINKS} links)"
    # Scanned over every link, including the ones dropped just above: the event object rides on httpcore's exception, which is exactly the link whose text was a duplicate.
    gloss = _h2_gloss(links)
    return f"{described} ({gloss})" if gloss else described


def interruption_message(
    *,
    error: BaseException | None,
    stop_reason: str,
    request_id: str,
    attempt_count: int,
) -> str:
    """What the hand-over tells the client this turn ended of.

    The request id is carried rather than the facts it identifies. This proxy's own request trace already records the model, the byte counts and the upstream connection identity under that id — and `.dev/docs/upstream/h2-goaway/` reads `upstream_conn` across rows to decide whether simultaneous failures shared one connection. Copying any of that here would give two places to drift; the join key gives one, and the MCP server's journal has carried nothing that reaches the proxy's log until now.

    The attempt count is the exception, because it changes how the line reads on its own: an interruption on the third attempt is a different event from one on the first, and the client side cannot see it at all — the loop detector there only ever sees `num_messages`.
    """
    # Square brackets rather than a second pair of parentheses: what is in them is this proxy's own identity for the turn, not part of the account of what upstream did, and the account already ends in parentheses of its own.
    where = f"[request {request_id}, attempt {attempt_count}]"
    if error is None:
        # Without this the field repeated `category` verbatim and said nothing twice. The stop reason is still quoted whole, since it is upstream's own word and the configured set it was matched against is not fixed to one value.
        return f"upstream ended the turn before it was finished: stop_reason={stop_reason} {where}"
    return f"{describe_error(error)} {where}"


def hand_back_block(
    *,
    chain: Chain,
    context: RequestContext,
    inbound_payload: dict[str, Any],
    wire_format: WireFormat,
    request_id: str,
    error: BaseException | None,
    stop_reason: str,
) -> dict[str, Any] | None:
    """The `tool_use` block that hands an unfinishable turn to the client, or `None` to leave the ending alone.

    Only for a client that asked in Anthropic Messages. The block is that protocol's shape, and the whole mechanism rests on the client executing a tool and coming back — which is a Claude Code behaviour, and the only harness in use. `upstream-retry-and-continuation.md` accepts that limit rather than guessing at the others.

    The tool's presence in the request is checked and **not** enforced. A client that never declared it answers with a `No such tool available` tool result and carries on, which is a worse turn than the one it asked for but a better one than a truncated stream — and the warning is what makes a missing plugin visible instead of silent. Ruled 2026-08-21.
    """
    if wire_format is not WireFormat.ANTHROPIC_MESSAGES:
        return None
    name = chain.config.upstream_request_retry.auto_retry_tool_call_full_name
    if not name:
        return None
    declared = context.payload.get("tools")
    if not isinstance(declared, list) or not any(
        isinstance(tool, dict) and cast(dict[str, Any], tool).get("name") == name
        for tool in cast(list[Any], declared)
    ):
        get_logger().warning(
            "auto_retry_tool_not_declared",
            request_id=request_id,
            tool=name,
        )
    # Category is what the MCP server keys its reply on, so it is read through the same mapping that decided this failure was continuable in the first place. Classified raw, a transport tear is `internal` — it is not an `OSError` — while the retry path calls the same failure `network`, and the two answers would have disagreed about one event.
    #
    # A turn upstream cut short for want of room is not an error and has no `ErrorCategory`. It travels under the stop reason upstream gave it, which is also what a reader of the MCP server's journal will recognise. **The value is provisional**: the user ruled that this case gets a category of its own but has not named it, and the server that reads it is being changed in another repository. See `.dev/docs/upstream/retry-and-continuation/decisions.md` 4.1.
    if error is None:
        category = stop_reason
    else:
        # `Exception`, because that is what decided the failure was continuable in the first place — the endings that are not exceptions never reach here with one.
        reason = replay_reason(error) if isinstance(error, Exception) else None
        # `.get` rather than a subscript: this runs inside the delivery generator, so a `RetryReason` someone adds later without touching the table would kill the client's turn rather than mislabel one field.
        #
        # `UPSTREAM` when the retry taxonomy has no word for the failure, not `INTERNAL`. The two questions are different — "would another attempt help" is not "whose failure was this" — and only the first one has a taxonomy here. What answers the second is the caller's gate: `stream.py` reaches a hand-over only on `not ours`, having positively identified this side's own protections and anything raised out of its own code, so an error arriving here is one this side did not inflict. Until 2026-08-23 an unnamed failure was called `internal`, which told the client the proxy had broken when what had actually happened was an upstream protocol error nobody had taught the classifier to name. It also disagreed with the error frame the very same failure produced on the other exit, which said `upstream_stream_failed`. `deferred.md` §22, §22之二.
        category = (
            CATEGORY_FOR_REASON.get(reason, ErrorCategory.UPSTREAM).value
            if reason
            else ErrorCategory.UPSTREAM.value
        )
    detail = interruption_message(
        error=error,
        stop_reason=stop_reason,
        request_id=request_id,
        attempt_count=context.attempt_count,
    )
    return {
        "type": "tool_use",
        "id": f"toolu_{uuid4().hex[:24]}",
        "name": name,
        "input": {
            # The client's own count, not the upstream request's: it advances by exactly two per hand-over — one assistant turn, one tool result — which is what makes "the same number twice" an exact answer rather than a heuristic. Ruled 2026-08-21.
            "num_messages": client_message_count(inbound_payload),
            "category": category,
            "message": detail,
        },
    }
