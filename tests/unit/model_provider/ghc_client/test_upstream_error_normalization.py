"""Whether an upstream failure reaches the driver as something it can act on.

The defect these cover is not that a case was handled wrongly — it is that no case reached the
handler at all. `GhcApiClient` posts through the SDKs, the SDKs raise their own exception types on
4xx, 5xx and transport failure, and `classify` aborts on anything outside the pipeline's closed
set. So every configured retry budget was dead code on the path that serves requests, and every
upstream answer became a 502.
"""

import httpx2
import openai
import pytest

from app.model_provider.ghc_client.errors import normalize_upstream_error, retry_after_seconds
from app.pipeline.exceptions import (
    Disposition,
    PipelineAbort,
    UpstreamError,
    UpstreamRateLimit,
    UpstreamRejected,
    UpstreamTimeout,
    classify,
)
from app.pipeline.retry import RetryReason, reason_for
from app.server.handler import error_body, error_headers, error_status


def status_error(
    status: int,
    *,
    headers: dict[str, str] | None = None,
    body: str = "{}",
    sent: bytes = b"",
) -> Exception:
    request = httpx2.Request("POST", "https://upstream.example/responses", content=sent)
    response = httpx2.Response(status, headers=headers or {}, text=body, request=request)
    return openai.APIStatusError("upstream said no", response=response, body=None)


def test_a_deterministic_4xx_is_not_retried() -> None:
    """The measured case: a body field upstream will not accept.

    Retrying it spends the server-error budget on nine identical rejections, delays the client's
    answer, and asks upstream the same question nine times. `UpstreamRejected` is outside
    `_RETRYABLE` so `classify` aborts, which is the whole point of it not being an `UpstreamError`.
    """
    normalized = normalize_upstream_error(
        status_error(400, body='{"error": {"message": "context_management: Extra inputs"}}')
    )

    assert isinstance(normalized, UpstreamRejected)
    assert normalized.status_code == 400
    assert classify(normalized) is Disposition.ABORT
    assert reason_for(normalized) is None


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_a_server_error_is_retryable_and_named_as_one(status: int) -> None:
    normalized = normalize_upstream_error(status_error(status))

    assert isinstance(normalized, UpstreamError)
    assert classify(normalized) is Disposition.RETRY
    assert reason_for(normalized) is RetryReason.SERVER_ERROR


def test_a_429_carries_its_retry_after() -> None:
    """The number that decides how long to wait. Lost entirely when the SDK error was flattened."""
    normalized = normalize_upstream_error(status_error(429, headers={"retry-after": "12"}))

    assert isinstance(normalized, UpstreamRateLimit)
    assert normalized.retry_after == 12.0
    assert classify(normalized) is Disposition.RETRY


def test_a_401_is_named_as_a_token_problem_rather_than_a_server_error() -> None:
    """So it draws on the token budget, which the spec defaults to 0 retries."""
    normalized = normalize_upstream_error(status_error(401))
    assert normalized is not None
    assert reason_for(normalized) is RetryReason.GITHUB_TOKEN_EXPIRED


def test_a_timeout_becomes_a_network_retry() -> None:
    request = httpx2.Request("POST", "https://upstream.example/responses")
    normalized = normalize_upstream_error(openai.APITimeoutError(request=request))

    assert isinstance(normalized, UpstreamTimeout)
    assert reason_for(normalized) is RetryReason.NETWORK


def test_a_transport_failure_becomes_a_network_retry() -> None:
    normalized = normalize_upstream_error(httpx2.ConnectError("refused"))

    assert isinstance(normalized, UpstreamError)
    assert normalized.status_code is None
    assert reason_for(normalized) is RetryReason.NETWORK


def test_an_error_that_is_not_the_upstreams_is_left_alone() -> None:
    """A catch-all here would dress a bug in our own code as a retryable upstream failure.

    Returning None rather than a generic `UpstreamError` is what keeps `classify`'s closed set
    meaningful: an unrecognised exception still aborts, and still reads as a bug.
    """
    assert normalize_upstream_error(KeyError("subscriber bug")) is None
    assert normalize_upstream_error(PipelineAbort("already ours")) is None


def test_retry_after_ignores_the_http_date_form() -> None:
    """Legal but unused here, and parsing it would be code nothing could show works."""
    assert retry_after_seconds({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}) is None
    assert retry_after_seconds({"Retry-After": "3"}) == 3.0
    assert retry_after_seconds({}) is None


def test_the_client_is_told_what_upstream_said() -> None:
    """A 400 answered as 502 says the proxy broke — both wrong and useless to the client."""
    rejected = normalize_upstream_error(
        status_error(400, body='{"error": {"message": "context_management: Extra inputs"}}')
    )
    assert rejected is not None

    assert error_status(rejected) == 400
    assert "context_management" in error_body(rejected)["error"]["upstream"]


def test_a_rate_limit_reaches_the_client_as_429_with_its_retry_after() -> None:
    limited = normalize_upstream_error(status_error(429, headers={"retry-after": "12"}))
    assert limited is not None

    assert error_status(limited) == 429
    assert error_headers(limited) == {"retry-after": "12"}


def test_a_timeout_reaches_the_client_as_504() -> None:
    assert error_status(UpstreamTimeout("upstream took too long")) == 504


def test_an_upstream_server_error_is_still_a_bad_gateway() -> None:
    """502 is right here — the proxy really could not get an answer out of upstream."""
    failed = normalize_upstream_error(status_error(503))
    assert failed is not None
    assert error_status(failed) == 502


def test_a_refusal_carries_the_bytes_it_was_a_refusal_of() -> None:
    """This boundary is the last place the outbound body exists.

    The SDK's exception holds the response, the response holds the request, and both are dropped as soon as the error becomes ours — after which only the payload dict survives, which is the body before it was serialized. The bytes are what upstream read, so they travel with the verdict on them.
    """
    sent = b'{"model":"gpt-5","input":"hi"}'
    rejected = normalize_upstream_error(status_error(400, sent=sent))

    assert isinstance(rejected, UpstreamRejected)
    assert rejected.sent == sent


def test_a_refusal_whose_body_cannot_be_read_back_is_still_a_refusal() -> None:
    """Reading the request off the error must not become a second failure on top of the first.

    `httpx.Request.content` raises for a body that was streamed rather than held, which no send on this path does today — but the client is already being told what upstream said, and a `RequestNotRead` raised while taking a note about it would replace that answer with a traceback.
    """
    assert UpstreamRejected("refused", status_code=400).sent == b"", "the field has to have a value when nothing supplied one"

    unread = httpx2.Request("POST", "https://upstream.example/responses", content=iter([b"chunk"]))
    error = openai.APIStatusError(
        "upstream said no",
        response=httpx2.Response(400, text="{}", request=unread),
        body=None,
    )

    normalized = normalize_upstream_error(error)

    assert isinstance(normalized, UpstreamRejected)
    assert normalized.status_code == 400
    assert normalized.sent == b""
