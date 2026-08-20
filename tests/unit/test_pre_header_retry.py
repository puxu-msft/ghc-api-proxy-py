"""Which pre-header transport failures may be retried.

Everything this classifier sees is pre-header by construction: the `try` it serves wraps only the call that returns once upstream's response headers arrive. So the question it answers is not "is this error safe in general" but "does this error belong to the category that reached us before the client could see anything".
"""

import httpx
import pytest
from h2.exceptions import ProtocolError as H2ProtocolError
from h2.settings import SettingCodes
from openai import APIConnectionError as OpenAIAPIConnectionError

from app.ghc_client.transport import is_responses_headers_pending_transport_error


def request() -> httpx.Request:
    return httpx.Request("POST", "https://upstream.invalid/responses")


def connection_terminated() -> httpx.RemoteProtocolError:
    """What httpcore raises for every stream still reading when a GOAWAY lands."""
    return httpx.RemoteProtocolError(
        "<ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>",
        request=request(),
    )


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("refused", request=request()),
        httpx.ConnectTimeout("timed out", request=request()),
        httpx.PoolTimeout("no connection", request=request()),
    ],
)
def test_the_failures_that_were_always_retryable_still_are(error: httpx.TransportError) -> None:
    assert is_responses_headers_pending_transport_error(error) is True


def test_a_torn_connection_is_retryable_before_headers() -> None:
    """The 2026-08-20 incident: one graceful-shutdown GOAWAY killed every in-flight stream.

    httpcore reports it as `RemoteProtocolError` for each stream that still needed to read. Before this, the classifier's own docstring said such a failure is safe to retry — "no client-visible response byte has been produced yet" — while its tuple left the whole class out, so a GOAWAY arriving during the upload was turned into a 502 for the client instead.
    """
    assert is_responses_headers_pending_transport_error(connection_terminated()) is True


def test_a_bare_h2_error_is_retryable_too() -> None:
    """The one that is not an httpx error at all, and so escapes an `isinstance` against `httpx.TransportError`.

    httpcore guards only the socket read in `_read_incoming_data`; the `h2_state.receive_data` call after it is outside the `try`. So when a GOAWAY and the frames following it arrive in a single read, hyper-h2 raises through the gap unwrapped. Measured in `docs/tmp/260820-h2-goaway-poc.md`.
    """
    error = H2ProtocolError("Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED")
    assert is_responses_headers_pending_transport_error(error) is True


def test_the_sdk_wrapper_is_unwrapped_to_find_the_cause() -> None:
    """The openai SDK re-raises transport failures as its own type, so the chain has to be walked."""
    cause = connection_terminated()
    wrapper = OpenAIAPIConnectionError(request=request())
    wrapper.__cause__ = cause
    assert is_responses_headers_pending_transport_error(wrapper) is True


def test_a_wrapped_bare_h2_error_is_found_through_the_chain() -> None:
    wrapper = OpenAIAPIConnectionError(request=request())
    wrapper.__cause__ = H2ProtocolError("received frame on closed connection")
    assert is_responses_headers_pending_transport_error(wrapper) is True


def test_an_unrelated_error_is_not_swept_in() -> None:
    """The classifier decides a retry, so widening it by accident is how a subscriber bug becomes an upstream storm."""
    assert is_responses_headers_pending_transport_error(ValueError("not a transport failure")) is False


def test_a_wrapper_with_no_cause_is_not_retryable() -> None:
    assert is_responses_headers_pending_transport_error(OpenAIAPIConnectionError(request=request())) is False


def test_an_h2_settings_error_is_still_an_h2_protocol_error() -> None:
    """`ProtocolError` is the family, and everything in it reached us before headers, so the family is the right granularity."""
    assert issubclass(type(H2ProtocolError()), Exception)
    assert is_responses_headers_pending_transport_error(H2ProtocolError(str(SettingCodes.MAX_FRAME_SIZE))) is True
