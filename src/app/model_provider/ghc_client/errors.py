"""Turn the SDKs' exceptions into the pipeline's closed set.

`docs/.human-controlled/request-pipeline.md` has the driver abort on anything outside that set, and that is the right default — a
subscriber's `KeyError` must not read as "retry". But the production send path calls
`AsyncOpenAI.post` and `AsyncAnthropic.post` directly, and both raise their *own* status and
connection exceptions on 4xx, 5xx and transport failure. Those are outside the set, so every real
upstream failure aborted and surfaced as a bare 502, and the configured 429, 5xx and network retry
budgets were never once consulted on the path that serves requests.

The fix belongs here rather than in `classify`: widening the closed set would let genuine bugs read
as retryable. This is the one boundary where the SDKs' vocabulary becomes ours, so it is where the
translation goes — every caller of `GhcApiClient` gets it, not just the driver that noticed.

Which statuses come back retryable is a judgement about determinism, not about severity. A 400
naming a field upstream will not accept answers the same way nine times over; a 503 does not.
"""

from collections.abc import Mapping
from typing import Any

import httpx2
from anthropic import APIConnectionError as AnthropicConnectionError
from anthropic import APIStatusError as AnthropicStatusError
from anthropic import APITimeoutError as AnthropicTimeoutError
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
# 401 is here because the token can be re-minted; whether it *is* retried is the budget's call,
# and `githubTokenExpired.max_retries` defaults to 0.
RETRYABLE_STATUSES = frozenset({401, 408, 409, 425, 429, 500, 502, 503, 504})

_STATUS_ERRORS = (OpenAIStatusError, AnthropicStatusError)
_TIMEOUT_ERRORS = (OpenAITimeoutError, AnthropicTimeoutError)
_CONNECTION_ERRORS = (OpenAIConnectionError, AnthropicConnectionError, httpx2.TransportError)


def retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """Read `Retry-After` as seconds, ignoring the HTTP-date form.

    The date form is legal and upstream does not use it; parsing it here would be code with no
    way to tell whether it works.
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

    None rather than a catch-all: an exception this does not recognise is not an upstream failure,
    and dressing it as one would hide a bug in our own code behind a retry.
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
