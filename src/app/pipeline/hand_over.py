"""What happens when a turn cannot be finished: whose budget pays, and what the client is handed.

Split out of `app.server.pipeline_app` on 2026-08-22. Both decisions here are domain ones — which failures another attempt could answer, and what an unfinishable turn looks like to a client that can carry it on — and they were being made inside the HTTP surface. `D-ARCH = B` puts retry and continuation with the driver, not with the edge, and a policy that only the edge can reach is a policy the driver cannot honour.

`replay_reason` closed over nothing at all, which is the clearest sign it never belonged to a request handler. `hand_back_block` closed over five locals; they are parameters now, which is also what makes it testable without an ASGI request.
"""

from typing import Any, cast
from uuid import uuid4

from h2.events import ConnectionTerminated, StreamReset
from h2.exceptions import H2Error

from app.core.chain import Chain
from app.errors import ErrorCategory
from app.model_provider.ghc_client.errors import normalize_upstream_error
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


def _one_line(text: str) -> str:
    """Collapse whitespace, and say so when the text was cut rather than letting it trail off."""
    flat = " ".join(text.split())
    if len(flat) <= _MAX_LINK_CHARS:
        return flat
    return f"{flat[:_MAX_LINK_CHARS]}… (+{len(flat) - _MAX_LINK_CHARS} more chars)"


def _chain(error: BaseException) -> list[BaseException]:
    """The exception and what it was raised from, outermost first.

    `__context__` is followed only where `__cause__` is absent and the context was not suppressed, which is the same reading `app.streaming.sse` already applies. It matters here because the informative link is often not the outermost one: a real connection reset arrives as `httpx2.ReadError('')` and says nothing until the fourth link, an `OSError` reading `[Errno 104] Connection reset by peer`.
    """
    links: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and len(links) < _MAX_LINKS and id(current) not in seen:
        seen.add(id(current))
        links.append(current)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return links


def _h2_gloss(links: list[BaseException]) -> str | None:
    """What an HTTP/2 event in the chain actually says, in words.

    httpcore raises `RemoteProtocolError(event)` for these, and httpx re-raises `mapped(str(exc)) from exc`, so the event object itself survives one link down as `args[0]` while only its `repr` reaches the top. That `repr` prints `error_code` through `IntEnum.__str__`, i.e. as a bare number — so the one word that distinguishes an upstream graceful shutdown from an upstream cancelling this very stream is on the object and invisible in the text. Every record in the MCP server's journal so far has been one of those two reprs.

    Read off the event's own enum rather than a table kept here, so a code this project has never seen still comes out named. Absent or unrecognised, the gloss is simply omitted: it is an explanation of the text beside it, never the only account of what happened.
    """
    for link in links:
        for argument in link.args:
            if isinstance(argument, ConnectionTerminated):
                return f"HTTP/2 GOAWAY from upstream, error_code={_code_name(argument.error_code)}"
            if isinstance(argument, StreamReset):
                # `remote_reset` distinguishes upstream dropping this stream from this process dropping it, which is the difference between an upstream decision and our own — and the `repr` is the only place it appears today.
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
    return _one_line(text)


def describe_error(error: BaseException) -> str:
    """One line naming what broke, why, and — for the transport failures this actually sees — what the protocol event meant.

    Three things `str(error)` alone does not give, all of them measured rather than supposed (`.dev/docs/upstream/retry-and-continuation/reports/260823-handover-error-shapes.md`):

    - **The type.** `<ConnectionTerminated …>` does not say it arrived as an `httpx2.RemoteProtocolError`, and `RemoteProtocolError` alone would not say which of the three libraries' versions of that name it was.
    - **A guarantee of content.** A real connection reset arrives as `httpx2.ReadError` whose `str()` is empty, and a bare `h2.ProtocolError()` is empty too — an empty `message` is the one value that tells a reader nothing at all.
    - **The chain.** The link that carries the reason is routinely not the one that was caught: for that same reset it is the fourth.

    Links whose text repeats an earlier link's, and interior links carrying no text at all, are dropped. Both are the ordinary shape here rather than edge cases: httpx re-raises httpcore's message unchanged, so every transport tear carries the same event `repr` twice, and a real connection reset arrives as four links of which the first three are empty. What survives is the type the code actually caught and the first link that had something to say — measured, those are `httpx2.ReadError` and `ConnectionResetError('[Errno 104] Connection reset by peer')`.
    """
    links = _chain(error)
    rendered: list[str] = []
    seen_text: set[str] = set()
    for position, link in enumerate(links):
        text = _link_text(link)
        name = f"{type(link).__module__}.{type(link).__qualname__}"
        if not text:
            # The outermost link is kept even when it says nothing, because its type is what the code caught and is the only account of the failure when the whole chain is silent.
            if position == 0:
                rendered.append(name)
            continue
        if text in seen_text:
            continue
        seen_text.add(text)
        rendered.append(f"{name}: {text}")
    described = "; caused by ".join(rendered)
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
        category = CATEGORY_FOR_REASON.get(reason, ErrorCategory.INTERNAL).value if reason else ErrorCategory.INTERNAL.value
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
