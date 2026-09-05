"""Turn upstream client exceptions into the pipeline's closed set.

`docs/.human-controlled/request-pipeline.md` has the driver abort on anything outside that set, and that is the right default — a subscriber's `KeyError` must not read as "retry". The production providers use OpenAI and Anthropic SDKs as well as raw httpx2; all three expose their own status, timeout and connection exceptions.

The translation belongs here rather than in `classify`: widening the closed set would let genuine bugs read as retryable. This is the one boundary where upstream client vocabulary becomes ours, shared by every provider that sends through one of those clients.

Which statuses come back retryable is a judgement about determinism, not about severity. A 400 naming a field upstream will not accept answers the same way nine times over; a 503 does not.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx2
from anthropic import APIConnectionError as AnthropicConnectionError
from anthropic import APIStatusError as AnthropicStatusError
from anthropic import APITimeoutError as AnthropicTimeoutError
from h2.exceptions import H2Error
from openai import APIConnectionError as OpenAIConnectionError
from openai import APIStatusError as OpenAIStatusError
from openai import APITimeoutError as OpenAITimeoutError

from app.pipeline.exceptions import (
    PipelineError,
    UpstreamError,
    UpstreamRateLimit,
    UpstreamRejected,
    UpstreamTimeout,
)

# Statuses where the same request, sent again, can plausibly get a different answer.
# 401 is here because the token can be re-minted; whether it *is* retried is the budget's call, and `githubTokenExpired.max_retries` defaults to 0.
RETRYABLE_STATUSES = frozenset({401, 408, 409, 425, 429, 499, 500, 502, 503, 504})

_STATUS_ERRORS = (OpenAIStatusError, AnthropicStatusError, httpx2.HTTPStatusError)
_TIMEOUT_ERRORS = (OpenAITimeoutError, AnthropicTimeoutError, httpx2.TimeoutException)
# `H2Error` is here because nothing wraps it on the body path, and its absence made one upstream event have two fates. httpcore guards only the socket read — `receive_data` sits outside that `try` (`httpcore2/_async/http2.py:425`) — and httpx re-raises what its map does not know. So a GOAWAY whose following frames land in a *separate* read arrives as `httpx2.RemoteProtocolError` and is retried, while the same GOAWAY batched into *one* read arrives as a bare `h2.exceptions.ProtocolError` and was neither retried nor called an upstream failure. Which one happened was decided by the kernel's read boundary. Measured 2026-08-23, `.dev/docs/upstream/retry-and-continuation/reports/260823-h2-protocolerror-category.md`.
#
# The family rather than one class, and the reason is not that every `H2Error` is upstream's — it is not. h2's hierarchy carries no attribution: `ProtocolError` is raised for a peer's bad preamble and for a local `send_data` over the window alike, `RFC1122Error` only ever for the caller's own misuse, and `StreamIDTooLowError`, `NoSuchStreamError`, `StreamClosedError` and `FlowControlError` are all reachable from both sides. An independent review built ten of them through h2's public API.
#
# What makes the mapping sound is where a *bare* one can come from **in this process**, which is two facts that must both hold:
#
#   1. Nothing here drives h2. The only live imports are types — `h2.events` for the gloss in `app.pipeline.hand_over`, and this one. `tests/unit/test_module_boundaries.py::test_h2_is_imported_only_for_its_types` makes a *new static import* argue for itself, and that is all it does: a review showed it passes on `raise H2Error(...)` from this side and on a dynamic import. So this condition is held up by reading the tree, not by a check.
#   2. httpcore converts the h2 errors *it* raises during the request phase, into `RemoteProtocolError` or `LocalProtocolError` (`httpcore2/_async/http2.py:151-166`). Nothing converts what the body path raises: `receive_data` sits outside every `try` (`:425`), and the byte stream re-raises unchanged.
#
# So a bare `H2Error` arriving here came out of httpcore's body path. **That is not the same as saying the peer caused it**, and two versions of this comment claimed it was. httpcore also calls `acknowledge_received_data` per `DataReceived` on that path (`:286-300`), and a review drove a real `_receive_response_body` into a bare local `NoSuchStreamError` through it.
#
# What that residue costs is decided by position, not by what kind of error it is — the second thing this comment got wrong. It said such a failure "spends the budget and then surfaces", which is only the ending it gets before anything has been delivered. Once a block has gone out, `decide_stream_ending` takes nothing from the ledger (`app/pipeline/retry.py:138-143`) and the hand-over returns cleanly with the exception swallowed and the client told `upstream`. That is the same ending a bug in this side's own byte counter gets, and the two converge on one gap: **the hand-over has no way left to say a failure was not upstream's.**
#
# The entry is kept on the case that was measured — a GOAWAY through the gap, which is the peer's — with the residue accepted and its real cost written down rather than argued away. Whether that trade is right is a product question, registered with the other half of it in `deferred.md` §22之七.
#
# If either fact stops holding, this entry stops being sound — which is why they are named rather than summarised as "h2 means upstream".
_CONNECTION_ERRORS = (
    OpenAIConnectionError,
    AnthropicConnectionError,
    httpx2.TransportError,
    H2Error,
)


def retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """Read a numeric retry delay, preferring the standard seconds header over milliseconds."""
    retry_after = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
    if retry_after is not None:
        try:
            return float(retry_after)
        except ValueError:
            pass

    retry_after_ms = next((v for k, v in headers.items() if k.lower() == "retry-after-ms"), None)
    if retry_after_ms is None:
        return None
    try:
        return float(retry_after_ms) / 1000
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class UpstreamResponseParts:
    """What is worth keeping off a failed upstream response, before the SDK's exception discards it.

    A record rather than a wider tuple: `body` and `body_bytes` are the same content at two fidelities and a positional pair invites reading one for the other.

    `body_bytes` exists because `body` cannot answer for the direct path. `docs/.human-controlled/` rules that a direct-path client gets upstream's own answer, and `response.text` is already a charset decision — measured, an upstream body of `b"\\xffraw-body"` reaches the client as `\\ufffdraw-body`, so the bytes are unrecoverable from this point on. For a JSON upstream the two agree; for a non-UTF-8 one, a BOM, or anything malformed they do not, and those are exactly the cases "even if we do not know it, it can still be passed on" is about.
    """

    status: int | None
    headers: dict[str, str]
    body: str
    body_bytes: bytes
    content_type: str


def _response_parts(error: Exception) -> UpstreamResponseParts:
    status: int | None = getattr(error, "status_code", None)
    headers: dict[str, str] = {}
    body = ""
    body_bytes = b""
    response: Any = getattr(error, "response", None)
    if response is not None:
        raw = getattr(response, "headers", None)
        if raw is not None:
            headers = {str(k): str(v) for k, v in dict(raw).items()}  # pyright: ignore[reportUnknownArgumentType]
        if status is None:
            candidate = getattr(response, "status_code", None)
            status = candidate if isinstance(candidate, int) else None
        text = getattr(response, "text", None)
        if isinstance(text, str):
            body = text
        # Read after `text` rather than instead of it: both are properties over the same already-read buffer, so this costs nothing, and `body` has consumers that predate this record.
        content = getattr(response, "content", None)
        if isinstance(content, bytes):
            body_bytes = content
    return UpstreamResponseParts(
        status=status,
        headers=headers,
        body=body,
        body_bytes=body_bytes,
        # Off the headers rather than guessed from the payload: what the client is told this content is has to be what upstream said it is, including when upstream was wrong about it.
        content_type=headers.get("content-type", ""),
    )


def _sent_body(error: Exception) -> bytes:
    """The bytes httpx actually put on the wire, taken off the request the SDK attached to its failed response.

    Read here because this is the last point at which they exist. The response — and the request under it — is dropped with the SDK exception the moment it is translated, and everything downstream has only the payload dict, which is what the body looked like before it was serialized. `len()` of these bytes was already being reported on the completion line; the bytes themselves were never kept anywhere, so a refusal about how a body was encoded had nothing to be read against.

    Taken only for a refusal, not for every SDK failure. A rejected body is as large as the conversation that produced it, and a 5xx or a rate limit is not answered by looking at it.
    """
    response: Any = getattr(error, "response", None)
    request: Any = getattr(response, "request", None)
    if request is None:
        return b""
    try:
        content: Any = request.content
    except Exception:
        # `httpx.Request.content` raises when the body was a stream that was never read, which no send on this path uses. Guarded rather than assumed because this runs while an upstream failure is already on its way to the client: a second failure here would replace upstream's own verdict with a traceback about the note we were trying to take.
        return b""
    return content if isinstance(content, bytes) else b""


def normalize_upstream_error(error: BaseException) -> PipelineError | None:
    """Map one SDK failure onto the closed set, or None when it is not one.

    None rather than a catch-all: an exception this does not recognise is not an upstream failure, and dressing it as one would hide a bug in our own code behind a retry.
    """
    if isinstance(error, PipelineError):
        return None
    if isinstance(error, _TIMEOUT_ERRORS):
        return UpstreamTimeout(f"upstream timed out: {error}")
    if isinstance(error, _STATUS_ERRORS):
        parts = _response_parts(error)
        status = parts.status
        if status == 429:
            return UpstreamRateLimit(
                f"upstream rate limited: {error}",
                retry_after=retry_after_seconds(parts.headers),
                headers=parts.headers,
                body=parts.body,
                body_bytes=parts.body_bytes,
                content_type=parts.content_type,
                body_observed=True,
            )
        if status is not None and status not in RETRYABLE_STATUSES and 400 <= status < 500:
            return UpstreamRejected(
                f"upstream rejected the request: {error}",
                status_code=status,
                headers=parts.headers,
                body=parts.body,
                body_bytes=parts.body_bytes,
                content_type=parts.content_type,
                body_observed=True,
                sent=_sent_body(error),
            )
        return UpstreamError(
            f"upstream returned {status}: {error}",
            status_code=status,
            headers=parts.headers,
            body=parts.body,
            body_bytes=parts.body_bytes,
            content_type=parts.content_type,
            body_observed=True,
        )
    if isinstance(error, _CONNECTION_ERRORS):
        # No response exists yet, so there is no status to carry and nothing to reject over.
        return UpstreamError(f"upstream connection failed: {error}")
    return None
