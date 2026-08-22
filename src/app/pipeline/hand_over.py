"""What happens when a turn cannot be finished: whose budget pays, and what the client is handed.

Split out of `app.server.pipeline_app` on 2026-08-22. Both decisions here are domain ones — which failures another attempt could answer, and what an unfinishable turn looks like to a client that can carry it on — and they were being made inside the HTTP surface. `D-ARCH = B` puts retry and continuation with the driver, not with the edge, and a policy that only the edge can reach is a policy the driver cannot honour.

`replay_reason` closed over nothing at all, which is the clearest sign it never belonged to a request handler. `hand_back_block` closed over five locals; they are parameters now, which is also what makes it testable without an ASGI request.
"""

from typing import Any, cast
from uuid import uuid4

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
    detail = stop_reason if error is None else str(error)
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
