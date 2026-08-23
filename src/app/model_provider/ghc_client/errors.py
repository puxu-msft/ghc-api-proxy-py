"""Turn the SDKs' exceptions into the pipeline's closed set.

`docs/.human-controlled/request-pipeline.md` has the driver abort on anything outside that set, and that is the right default — a
subscriber's `KeyError` must not read as "retry". But the production send path calls `AsyncOpenAI.post` and `AsyncAnthropic.post` directly, and both raise their *own* status and connection exceptions on 4xx, 5xx and transport failure. Those are outside the set, so every real upstream failure aborted and surfaced as a bare 502, and the configured 429, 5xx and network retry budgets were never once consulted on the path that serves requests.

The fix belongs here rather than in `classify`: widening the closed set would let genuine bugs read as retryable. This is the one boundary where the SDKs' vocabulary becomes ours, so it is where the translation goes — every caller of `GhcApiClient` gets it, not just the driver that noticed.

Which statuses come back retryable is a judgement about determinism, not about severity. A 400 naming a field upstream will not accept answers the same way nine times over; a 503 does not.
"""

from collections.abc import Mapping
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
RETRYABLE_STATUSES = frozenset({401, 408, 409, 425, 429, 500, 502, 503, 504})

_STATUS_ERRORS = (OpenAIStatusError, AnthropicStatusError)
_TIMEOUT_ERRORS = (OpenAITimeoutError, AnthropicTimeoutError)
# `H2Error` is here because nothing wraps it on the body path, and its absence made one upstream event have two fates. httpcore guards only the socket read — `receive_data` sits outside that `try` (`httpcore2/_async/http2.py:425`) — and httpx re-raises what its map does not know. So a GOAWAY whose following frames land in a *separate* read arrives as `httpx2.RemoteProtocolError` and is retried, while the same GOAWAY batched into *one* read arrives as a bare `h2.exceptions.ProtocolError` and was neither retried nor called an upstream failure. Which one happened was decided by the kernel's read boundary. Measured 2026-08-23, `.dev/docs/upstream/retry-and-continuation/reports/260823-h2-protocolerror-category.md`.
#
# The family rather than one class, and the reason is not that every `H2Error` is upstream's — it is not. h2's hierarchy carries no attribution: `ProtocolError` is raised for a peer's bad preamble and for a local `send_data` over the window alike, `RFC1122Error` only ever for the caller's own misuse, and `StreamIDTooLowError`, `NoSuchStreamError`, `StreamClosedError` and `FlowControlError` are all reachable from both sides. An independent review built ten of them through h2's public API.
#
# What makes the mapping sound is where a *bare* one can come from **in this process**, which is two facts that must both hold:
#
#   1. Nothing here drives h2. The only live imports are types — `h2.events` for the gloss in `app.pipeline.hand_over`, and this one — and `tests/unit/test_module_boundaries.py` pins that, so a future module that starts calling `H2Connection` makes a test say so rather than silently widening this tuple.
#   2. httpcore converts the h2 errors *it* raises during the request phase, into `RemoteProtocolError` or `LocalProtocolError` (`httpcore2/_async/http2.py:151-166`). Nothing converts what the body path raises: `receive_data` sits outside every `try` (`:425`), and the byte stream re-raises unchanged.
#
# So a bare `H2Error` arriving here came out of httpcore's body path. **That is not the same as saying the peer caused it, and this comment said so until a review showed otherwise.** httpcore also calls `acknowledge_received_data` per `DataReceived` on that path (`:286-300`), and the review drove a real `_receive_response_body` into a bare local `NoSuchStreamError` through it. What the residue actually is matters more than its size: a dependency's own bookkeeping invariant, not this proxy's code. Mapping it to a network retry spends the budget and then surfaces, which is a different failure from the one the module docstring guards against — dressing *our* bug as retryable so it never surfaces at all. Registered in `deferred.md` §22之七.
#
# If either fact stops holding, this entry stops being sound — which is why they are named rather than summarised as "h2 means upstream".
_CONNECTION_ERRORS = (
    OpenAIConnectionError,
    AnthropicConnectionError,
    httpx2.TransportError,
    H2Error,
)


def retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """Read `Retry-After` as seconds, ignoring the HTTP-date form.

    The date form is legal and upstream does not use it; parsing it here would be code with no way to tell whether it works.
    """
    raw = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _response_parts(error: Exception) -> tuple[int | None, dict[str, str], str]:
    status: int | None = getattr(error, "status_code", None)
    headers: dict[str, str] = {}
    body = ""
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
    return status, headers, body


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
        status, headers, body = _response_parts(error)
        if status == 429:
            return UpstreamRateLimit(
                f"upstream rate limited: {error}",
                retry_after=retry_after_seconds(headers),
                headers=headers,
                body=body,
            )
        if status is not None and status not in RETRYABLE_STATUSES and 400 <= status < 500:
            return UpstreamRejected(
                f"upstream rejected the request: {error}",
                status_code=status,
                headers=headers,
                body=body,
                sent=_sent_body(error),
            )
        return UpstreamError(
            f"upstream returned {status}: {error}",
            status_code=status,
            headers=headers,
            body=body,
        )
    if isinstance(error, _CONNECTION_ERRORS):
        # No response exists yet, so there is no status to carry and nothing to reject over.
        return UpstreamError(f"upstream connection failed: {error}")
    return None
