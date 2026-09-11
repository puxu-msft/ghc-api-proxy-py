"""The exception contract between subscribers and the driver.

`docs/.human-controlled/request-pipeline.md`: known exceptions are handled by built-in logic, unknown ones always abort.
The closed set is the point.
A subscriber's KeyError must not read as a control instruction.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.tokenization.admission import TokenAdmissionObservation


class Disposition(StrEnum):
    """What the driver does after a subscriber raised."""

    CONTINUE = "continue"
    RETRY = "retry"
    ABORT = "abort"


class PipelineError(Exception):
    """Base of the closed set. Raising a subclass is how a subscriber steers the flow."""


class PromptTokenLimitExceeded(PipelineError):
    """The final Responses payload failed the proxy's local prompt admission policy."""

    def __init__(self, observation: TokenAdmissionObservation) -> None:
        super().__init__(
            f"proxy prompt admission rejected {observation.model} "
            f"at {observation.field_path or 'unknown field'}: "
            f"standalone {observation.tokenizer or 'unknown tokenizer'} count "
            f"{observation.field_token_count} exceeds context window "
            f"{observation.max_context_window_tokens} "
            f"(catalog prompt limit {observation.max_prompt_tokens}, "
            f"provider {observation.provider} generation {observation.catalog_generation})"
        )
        self.observation = observation


class UpstreamError(PipelineError):
    """Upstream refused or failed. Retryable by default; the budget decides."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        headers: Mapping[str, str] | None = None,
        body: str = "",
        body_bytes: bytes = b"",
        content_type: str = "",
        sent: bytes = b"",
        sent_observed: bool = False,
        body_observed: bool = False,
        body_complete: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        # Carried because the rate limiter reads `Retry-After` and the client deserves upstream's own words. Both are lost the moment an SDK exception is flattened to a string.
        self.headers: Mapping[str, str] = dict(headers or {})
        self.body = body
        # The same content one fidelity up, and the pair is deliberate. `body` is `response.text`, which has already made a charset decision; on a direct path the client is owed upstream's own bytes, and a decode that replaced a byte cannot be undone. Empty when the failure arrived without a response to read them off.
        self.body_bytes = body_bytes
        # Empty bytes are ambiguous without this bit: they may be a measured empty response or a streaming body nobody consumed. Non-empty bytes prove observation on their own; empty requires the response boundary to say so explicitly.
        self.body_observed = body_observed or bool(body_bytes)
        self.body_complete = (
            self.body_observed if body_complete is None else body_complete
        )
        self.content_type = content_type
        self.sent = sent
        # An empty request body is legal wire evidence, while the default `b""` also represents no evidence. Keep the observation bit separate so a fallback never invents an empty send.
        self.sent_observed = sent_observed or bool(sent)


class UpstreamTimeout(UpstreamError):
    pass


class UpstreamRateLimit(UpstreamError):
    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        headers: Mapping[str, str] | None = None,
        body: str = "",
        body_bytes: bytes = b"",
        content_type: str = "",
        sent: bytes = b"",
        sent_observed: bool = False,
        body_observed: bool = False,
        body_complete: bool | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=429,
            headers=headers,
            body=body,
            body_bytes=body_bytes,
            content_type=content_type,
            sent=sent,
            sent_observed=sent_observed,
            body_observed=body_observed,
            body_complete=body_complete,
        )
        self.retry_after = retry_after


class UpstreamRejected(PipelineError):
    """Upstream refused the request itself; sending the same body again cannot help.

    Deliberately *not* an `UpstreamError`, so `classify` aborts rather than retries. A malformed body, an unsupported field, an unknown tool — these are deterministic. Spending the server-error budget on nine identical rejections wastes the budget, delays the client's answer by the backoff, and asks upstream the same question nine times.

    The status and body travel so the client is told what upstream actually said, rather than a bare 502 that reads like the proxy failed.

    `sent` travels for the same reason one level further back: upstream's verdict is a verdict on a particular string of bytes, and that string exists nowhere else. The payload dict survives on the context, but it is the body *before* serialization and so cannot answer a refusal about key order, separators, or anything an SDK did on the way out. The bytes are read off the response the SDK attached to its own exception, which is discarded the moment the error is handled, so they are carried on the error rather than fetched later. `sent_observed` distinguishes a measured empty request from missing request evidence.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        headers: Mapping[str, str] | None = None,
        body: str = "",
        body_bytes: bytes = b"",
        content_type: str = "",
        sent: bytes = b"",
        sent_observed: bool = False,
        body_observed: bool = False,
        body_complete: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.headers: Mapping[str, str] = dict(headers or {})
        self.body = body
        # See `UpstreamError`. Not the same thing as `sent` below, which is the *request*.
        self.body_bytes = body_bytes
        self.body_observed = body_observed or bool(body_bytes)
        self.body_complete = (
            self.body_observed if body_complete is None else body_complete
        )
        self.content_type = content_type
        self.sent = sent
        self.sent_observed = sent_observed or bool(sent)


class PipelineRetry(PipelineError):
    """Explicit request to attempt again, independent of any upstream failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


CONNECTION_BOUND_INPUT_ITEM_ID = "input item ID does not belong to this connection"


class ConnectionBoundInputIdRetry(PipelineRetry):
    """Retry a Copilot Responses request with account-bound reasoning state removed."""

    def __init__(self, error: UpstreamError, payload: dict[str, Any]) -> None:
        super().__init__(CONNECTION_BOUND_INPUT_ITEM_ID)
        self.error = error
        self.payload = payload


class PipelineAbort(PipelineError):
    """Explicit request to stop this request without retrying."""

    def __init__(self, reason: str, *, cause: BaseException | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        # The failure that ran out of retries, when the abort is the end of a retry sequence rather than a refusal in its own right.
        #
        # Two facts, and they belong to different readers. The abort explains why this side stopped trying, which is what an operator reading a log line needs. Upstream's own answer — a 429 with a `Retry-After`, a 400 naming the field — is what the *client* can act on, and it used to be flattened into the abort's message on its way out: every retryable failure that exhausted its budget reached the client as a 502 with no headers, which says the proxy broke and offers nothing to do about it. Carried rather than merged, so each reader gets the one it needs.
        self.cause = cause


_RETRYABLE: tuple[type[PipelineError], ...] = (UpstreamError, PipelineRetry)


def classify(error: BaseException) -> Disposition:
    """Map a raised exception to what the driver should do.

    Anything outside the closed set aborts.
    Widening this to "unknown means retry" would turn a subscriber bug into an upstream storm.
    """
    if isinstance(error, PipelineAbort):
        return Disposition.ABORT
    if isinstance(error, _RETRYABLE):
        return Disposition.RETRY
    return Disposition.ABORT


def is_known(error: BaseException) -> bool:
    return isinstance(error, PipelineError)


def is_connection_bound_input_id_error(error: BaseException) -> bool:
    return (
        isinstance(error, UpstreamError)
        and error.status_code == 401
        and CONNECTION_BOUND_INPUT_ITEM_ID in error.body
    )
