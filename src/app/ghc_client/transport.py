import httpx
from openai import APIConnectionError as OpenAIAPIConnectionError

_RESPONSES_PRE_HEADERS_HTTPX_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
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
    if not isinstance(error, OpenAIAPIConnectionError):
        return False
    cause = error.__cause__
    if cause is None:
        return False
    while cause is not None:
        if isinstance(cause, httpx.TransportError):
            return isinstance(cause, _RESPONSES_PRE_HEADERS_HTTPX_ERRORS)
        cause = cause.__cause__
    return False
