"""The exception contract between subscribers and the driver.

MAIN.md: known exceptions are handled by built-in logic, unknown ones always abort.
The closed set is the point.
A subscriber's KeyError must not read as a control instruction.
"""

from enum import StrEnum


class Disposition(StrEnum):
    """What the driver does after a subscriber raised."""

    CONTINUE = "continue"
    RETRY = "retry"
    ABORT = "abort"


class PipelineError(Exception):
    """Base of the closed set. Raising a subclass is how a subscriber steers the flow."""


class UpstreamError(PipelineError):
    """Upstream refused or failed. Retryable by default; the budget decides."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class UpstreamTimeout(UpstreamError):
    pass


class UpstreamRateLimit(UpstreamError):
    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class PipelineRetry(PipelineError):
    """Explicit request to attempt again, independent of any upstream failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PipelineAbort(PipelineError):
    """Explicit request to stop this request without retrying."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


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
