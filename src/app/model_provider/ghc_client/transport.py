import httpx2
from h2.exceptions import ProtocolError as H2ProtocolError
from openai import APIConnectionError as OpenAIAPIConnectionError

# Everything reaching the classifier is pre-header by construction: the `try` it serves wraps only the call that returns once upstream's response headers arrive, so a failure during the body never gets here. That is what makes the whole category retryable rather than any property of the individual errors.
#
# `RemoteProtocolError` covers the connection being torn out from under a request — including an upstream GOAWAY, which httpcore reports this way for every stream that still needs to read. Added 2026-08-20 after four in-flight streams died on one graceful-shutdown GOAWAY. Cost is not a reason to leave it out: an upstream request that can no longer be used is already spent, and declining to retry does not refund it.
_RESPONSES_PRE_HEADERS_HTTPX_ERRORS = (
    httpx2.ConnectError,
    httpx2.ConnectTimeout,
    httpx2.PoolTimeout,
    httpx2.RemoteProtocolError,
)


class ResponsesHeadersPendingTransportError(Exception):
    """A transport failure that happened before any upstream response header arrived.

    Such a failure is safe to retry: no client-visible response byte has been produced yet.
    Once headers have arrived, the same transport error no longer belongs to this category.
    """

    def __init__(self, original: Exception) -> None:
        super().__init__(str(original))
        self.original = original


def is_responses_headers_pending_transport_error(error: Exception) -> bool:
    if isinstance(error, _RESPONSES_PRE_HEADERS_HTTPX_ERRORS):
        return True
    # Not an httpx error at all, and the reason this is checked separately: httpcore guards only the socket read in `_read_incoming_data`, so when a GOAWAY and the frames after it land in one read, hyper-h2 raises through the gap and nothing wraps it. Measured in `.dev/docs/upstream/h2-goaway/archive-260820/260820-h2-goaway-poc.md`. An `isinstance` against `httpx.TransportError` misses it entirely, which is why the caller's `except` has to name it too.
    if isinstance(error, H2ProtocolError):
        return True
    if not isinstance(error, OpenAIAPIConnectionError):
        return False
    cause = error.__cause__
    if cause is None:
        return False
    while cause is not None:
        if isinstance(cause, httpx2.TransportError | H2ProtocolError):
            return isinstance(cause, (*_RESPONSES_PRE_HEADERS_HTTPX_ERRORS, H2ProtocolError))
        cause = cause.__cause__
    return False
