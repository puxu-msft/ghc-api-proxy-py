"""Whether an upstream failure reaches the driver as something it can act on.

The defect these cover is not that a case was handled wrongly — it is that no case reached the handler at all. `GhcApiClient` posts through the SDKs, the SDKs raise their own exception types on 4xx, 5xx and transport failure, and `classify` aborts on anything outside the pipeline's closed set. So every configured retry budget was dead code on the path that serves requests, and every upstream answer became a 502.
"""

import httpx2
import openai
import pytest
from h2.exceptions import NoSuchStreamError, StreamClosedError
from h2.exceptions import ProtocolError as H2ProtocolError

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
from app.server.http_errors import error_body, error_headers, error_status


def status_error(
    status: int,
    *,
    headers: dict[str, str] | None = None,
    body: str = "{}",
    raw: bytes | None = None,
    sent: bytes = b"",
) -> Exception:
    """One upstream failure, as the SDK would raise it.

    `raw` sends the body as bytes rather than as text, which is the only way to build the case that decoding destroys — `text=` would encode a `str` this side already holds and the round trip could never lose anything.
    """
    request = httpx2.Request("POST", "https://upstream.example/responses", content=sent)
    response = (
        httpx2.Response(status, headers=headers or {}, content=raw, request=request)
        if raw is not None
        else httpx2.Response(status, headers=headers or {}, text=body, request=request)
    )
    return openai.APIStatusError("upstream said no", response=response, body=None)


def test_a_deterministic_4xx_is_not_retried() -> None:
    """The measured case: a body field upstream will not accept.

    Retrying it spends the server-error budget on nine identical rejections, delays the client's answer, and asks upstream the same question nine times. `UpstreamRejected` is outside `_RETRYABLE` so `classify` aborts, which is the whole point of it not being an `UpstreamError`.
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


def test_one_goaway_has_one_fate_whichever_shape_it_arrives_in() -> None:
    """The same upstream event used to be retried or not depending on the kernel's read boundary.

    httpcore guards only the socket read; `receive_data` is outside that `try` (`httpcore2/_async/http2.py:425`), and httpx re-raises what its map does not know. So a GOAWAY whose following frames land in a *separate* read surfaces as `httpx2.RemoteProtocolError`, and the very same GOAWAY batched into *one* read surfaces as a bare `h2.exceptions.ProtocolError`. Measured 4/4 in `.dev/docs/upstream/h2-goaway/archive-260820/260820-h2-goaway-poc.md`.

    Before `H2Error` joined `_CONNECTION_ERRORS` the second shape was neither retried nor called an upstream failure, while the first was both. Asserted as an equality between the two rather than as a value for each, because the defect was the divergence.
    """
    wrapped = normalize_upstream_error(
        httpx2.RemoteProtocolError("<ConnectionTerminated error_code:0, last_stream_id:2147483647>")
    )
    bare = normalize_upstream_error(
        H2ProtocolError("Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED")
    )

    assert isinstance(bare, UpstreamError)
    assert isinstance(wrapped, UpstreamError)
    assert reason_for(bare) is reason_for(wrapped) is RetryReason.NETWORK
    assert classify(bare) is classify(wrapped) is Disposition.RETRY


def test_the_h2_family_is_named_because_of_where_a_bare_one_can_come_from() -> None:
    """Not because the hierarchy means "upstream" — it does not, and asserting that would pin a false claim.

    A review built ten `H2Error` subclasses through h2's own public API, all from caller actions: `RFC1122Error` is raised only for the caller's misuse, and `StreamIDTooLowError`, `NoSuchStreamError`, `StreamClosedError` and `FlowControlError` are each reachable from both sides. The family is mapped here on the two conditions named in `errors.py`, not on the type meaning anything by itself.

    So what is asserted is the shape that actually arrives — a subclass with no message of its own, which is what a bare `receive_data` failure looks like and what used to reach the client as a `message` reading `3`. `test_no_live_module_drives_h2_itself` in `tests/unit/test_module_boundaries.py` is what holds up the first condition.
    """
    for error in (StreamClosedError(3), NoSuchStreamError(7)):
        normalized = normalize_upstream_error(error)
        assert isinstance(normalized, UpstreamError), type(error).__name__
        assert reason_for(normalized) is RetryReason.NETWORK, type(error).__name__


def test_a_body_upstream_compressed_wrongly_is_still_not_ours_to_name() -> None:
    """The counterpart, and the reason the h2 entry is a family rather than a catch-all.

    `httpx2.DecodingError` descends from `RequestError`, not `TransportError`, so it stays unnamed — which is what `tests/unit/pipeline/delivery/test_stream_delivery.py` now uses to carry its premise. If this ever starts returning an `UpstreamError`, that test's premise assertion is the thing that will say so.
    """
    assert normalize_upstream_error(httpx2.DecodingError("Error -3 while decompressing data")) is None


def test_an_error_that_is_not_the_upstreams_is_left_alone() -> None:
    """A catch-all here would dress a bug in our own code as a retryable upstream failure.

    Returning None rather than a generic `UpstreamError` is what keeps `classify`'s closed set meaningful: an unrecognised exception still aborts, and still reads as a bug.
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


@pytest.mark.parametrize(
    "content_type, decoded",
    [
        # No charset, so `text` decodes as UTF-8 and the byte has no representation: it becomes U+FFFD and is gone.
        ("application/json", "\ufffdraw-body"),
        # A charset where the byte *does* decode, which is the more interesting half — the decode looks lossless and still is not the bytes: `"ÿ".encode()` is two bytes, not one.
        ("text/html; charset=iso-8859-1", "ÿraw-body"),
    ],
)
def test_upstreams_own_bytes_survive_the_decode_that_text_performs(
    content_type: str, decoded: str
) -> None:
    """The direct path owes the client upstream's answer, and `response.text` is already a charset decision.

    Two charsets because the first draft only had the U+FFFD one, and that one alone makes the property look like it is about invalid input. It is not: the second case decodes cleanly and the bytes still differ, so what `body` cannot carry is not "malformed data" but "the bytes upstream actually sent". The relationship is asserted directly — `body.encode()` is not `body_bytes` — rather than only through the two literals, because the literals are what a reader checks and the relationship is what the direct path depends on.

    The SDK's response object is dropped the moment the error becomes ours, so if the bytes are not taken here they are unrecoverable.
    """
    rejected = normalize_upstream_error(
        status_error(400, raw=b"\xffraw-body", headers={"content-type": content_type})
    )

    assert isinstance(rejected, UpstreamRejected)
    assert rejected.body_bytes == b"\xffraw-body"
    assert rejected.body == decoded
    assert rejected.body.encode() != rejected.body_bytes, "the pair only earns its keep if the two differ"
    # Carried through rather than invented. A first draft asserted `application/json` only, and a mutation proved it had no discriminating power: hard-coding the field to that string left the test green.
    assert rejected.content_type == content_type


def test_an_upstream_that_declared_no_content_type_gets_no_invented_one() -> None:
    """Absence is not readable unless it survives as absence.

    The direct path decides how to hand upstream's bytes onward partly from what upstream said they are; an invented `application/json` would make a client parse something upstream never claimed was JSON.
    """
    rejected = normalize_upstream_error(status_error(400, raw=b"\xffraw-body"))

    assert isinstance(rejected, UpstreamRejected)
    assert rejected.content_type == ""


@pytest.mark.parametrize(
    "status, kind",
    [(400, UpstreamRejected), (500, UpstreamError), (429, UpstreamRateLimit)],
)
def test_every_upstream_failure_that_has_a_body_carries_its_bytes(
    status: int, kind: type[Exception]
) -> None:
    """All three branches of the normaliser, because each builds its exception separately.

    The 429 and 5xx branches were the ones a first draft forgot: they take the same `parts` record and it is one keyword argument per branch to drop.
    """
    normalized = normalize_upstream_error(status_error(status, raw=b'{"e":1}'))

    assert isinstance(normalized, kind)
    # Narrowed a second time against the union rather than against `kind`, which is a variable and narrows nothing. Both members carry the field, so this reads it without a `getattr` that would also pass on a class that has no such attribute.
    assert isinstance(normalized, UpstreamError | UpstreamRejected)
    assert normalized.body_bytes == b'{"e":1}'


def test_a_failure_with_no_response_has_empty_bytes_rather_than_a_guess() -> None:
    """A connection that never got an answer has no upstream body, and an empty one is the honest record of that.

    Not a detail: the direct path decides whether to pass upstream's answer through by asking whether there is one, so "no response" and "a response with an empty body" have to be distinguishable from each other somewhere — today by `status_code is None`, which this pins alongside.
    """
    normalized = normalize_upstream_error(openai.APIConnectionError(request=httpx2.Request("POST", "https://upstream.example/responses")))

    assert isinstance(normalized, UpstreamError)
    assert normalized.body_bytes == b""
    assert normalized.status_code is None
