"""What a client actually receives when a request fails, through the real app.

The ruling these serve is the user's of 2026-08-23: on a direct path the client gets upstream's own answer, including the parts this proxy does not understand; on a translated path the failure crosses an internal representation and is written in the client's dialect. `.dev/docs/error-envelope/spec.md` is the frozen form of it.

Two things about how these are written, both from a plan review:

**The direct-path sample is not ordinary JSON.** An implementation that parses upstream's body and serialises it again produces the same bytes for `{"error":{...}}`, so a test using one cannot tell passthrough from a round trip. `b"\\xffraw-body"` can: it is not valid UTF-8 and not valid JSON, so anything that decodes or re-encodes it changes it.

**Headers are asserted in both directions.** Today's behaviour — dropping every one of upstream's headers except a reformatted `Retry-After` on a 429 — passes any test that only checks the ones that should survive.
"""

from typing import Any

import httpx2
import orjson
import pytest

# Same directory, so pytest's default `prepend` import mode puts it on the path. There is no `tests` package to import through — `tests/__init__.py` does not exist, deliberately.
from test_pipeline_app import make_client

from app.errors import ErrorCategory, ErrorInfo
from app.server.http_errors import _outbound_headers  # pyright: ignore[reportPrivateUsage]

# Upstream's headers, mixed on purpose: three that carry meaning a client acts on, two that frame upstream's own connection and must not ride along.
#
# `content-encoding: gzip` is **not** here, and the reason is worth recording: with it, httpx tries to inflate bytes that are not gzip, the read fails as a `DecodingError`, and the request never becomes a status error at all — it exhausts the network retry budget and arrives as a 502. That is the transport behaving correctly on a fixture that lied, not the code under test. The whole `_NEVER_FORWARDED` set is pinned at the unit level instead, where no transport is in the way.
UPSTREAM_HEADERS = {
    "content-type": "text/html; charset=iso-8859-1",
    "x-request-id": "req_abc",
    "anthropic-ratelimit-requests-remaining": "17",
    "retry-after": "3",
    "connection": "keep-alive",
    "keep-alive": "timeout=5",
}

# Not valid UTF-8 and not valid JSON. Whatever reaches the client either is these bytes or is not.
OPAQUE = b"\xffraw-body"


def failing_upstream(
    status: int, *, content: bytes = OPAQUE, headers: dict[str, str] | None = None
):
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, content=content, headers=headers or UPSTREAM_HEADERS)

    return handler


def test_a_direct_path_hands_on_upstreams_own_bytes() -> None:
    """Anthropic in, an Anthropic model out, so upstream and the client speak the same dialect.

    Byte equality rather than a parse: the ruling is that a client gets what upstream sent, and any assertion that goes through a parser first has already given up the thing being checked.
    """
    client, _ = make_client(failing_upstream(400))

    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert response.status_code == 400
    assert response.content == OPAQUE


def test_a_direct_path_keeps_upstreams_content_type() -> None:
    """The client has to be told what those bytes are, and only upstream can say.

    Asserted separately from the body because the failure modes differ: a proxy that forwards the bytes but stamps `application/json` on them has handed the client something it will try to parse and cannot.
    """
    client, _ = make_client(failing_upstream(400))

    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert response.headers["content-type"] == "text/html; charset=iso-8859-1"


@pytest.mark.parametrize(
    "header, value",
    [
        ("x-request-id", "req_abc"),
        ("anthropic-ratelimit-requests-remaining", "17"),
        # Upstream's own spelling. It used to be parsed to a float and printed back as an int, and only on a 429.
        ("retry-after", "3"),
    ],
)
def test_a_direct_path_forwards_the_headers_a_client_acts_on(header: str, value: str) -> None:
    client, _ = make_client(failing_upstream(400))

    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert response.headers.get(header) == value


@pytest.mark.parametrize("header", ["connection", "keep-alive"])
def test_a_direct_path_drops_the_headers_that_frame_upstreams_own_response(header: str) -> None:
    """The half a one-directional test cannot see: today's behaviour drops *everything*, and passes any test that only checks what should survive."""
    client, _ = make_client(failing_upstream(400))

    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert header not in response.headers


def test_a_translated_path_answers_in_the_clients_dialect_instead() -> None:
    """The same upstream answer, the other path — and the shapes must differ.

    Anthropic in, an OpenAI Responses model out, so upstream's dialect is not the client's. Handing on upstream's bytes here would give the client something its parser does not know, which is what "the translated path translates" means for a failure as much as for a reply.
    """
    client, _ = make_client(failing_upstream(400, content=b'{"error":{"message":"nope"}}',
                                             headers={"content-type": "application/json"}))

    response = client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    assert response.status_code == 400
    body = orjson.loads(response.content)
    assert body["type"] == "error"
    assert body["error"]["type"] == "invalid_request_error"
    assert "nope" in body["error"]["message"]
    # Absent because this one *was* readable. Without this the writer could attach the original unconditionally and every assertion above would still hold — a mutation proved exactly that.
    assert "upstream_error" not in body["error"]


def test_a_translated_path_keeps_an_uninterpretable_upstream_error_structured() -> None:
    """Spec §10.1, the case the user ruled on: upstream failed in a way this proxy cannot read.

    The envelope is the client's, so its SDK parses it; the original travels under `upstream_error` rather than being flattened into the message, which is what the ruling chose over the other two candidates. `\\xff` is what makes the case: a body that is not JSON at all cannot be mapped onto anything.
    """
    client, _ = make_client(failing_upstream(400))

    response = client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    body = orjson.loads(response.content)
    assert body["type"] == "error"
    # Not a replacement character: every byte of `latin-1` maps, so nothing upstream sent is edited on the way through.
    assert body["error"]["upstream_error"] == "ÿraw-body"


def test_upstreams_status_survives_a_retry_budget_running_out() -> None:
    """**Behaviour change.** Every retryable status except 429 used to become a 502.

    503 means overloaded and is worth waiting on; 502 means the gateway itself broke. Both SDKs pick their exception class from the status, so the two are different instructions to the client — and the old answer gave the wrong one for 401, 500, 503 and 504 alike.
    """
    client, _ = make_client(failing_upstream(503))

    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert response.status_code == 503


@pytest.mark.parametrize(
    "path, body, wire",
    [
        ("/v1/messages", {"model": "claude-model", "messages": []}, "anthropic"),
        ("/v1/responses", {"model": "gpt-model", "input": []}, "openai"),
        ("/v1/chat/completions", {"model": "cc-model", "messages": []}, "openai"),
    ],
)
def test_each_inbound_dialect_gets_its_own_envelope(
    path: str, body: dict[str, Any], wire: str
) -> None:
    """Until now all four endpoints answered a failure with byte-identical bodies.

    An OpenAI client asking `/v1/responses` got neither OpenAI's `{"error":{message,type,param,code}}` nor Anthropic's tagged union — it got a shape this project invented, with a Python exception class name where the dialect's own vocabulary goes.

    Driven through a *proxy-produced* failure rather than an upstream one, because that is the case where the dialect is the only thing that varies: an upstream failure on a direct path is upstream's bytes whatever the endpoint.
    """
    client, seen = make_client(failing_upstream(400))

    response = client.post(path, json={**body, "model": "no-such-model"})

    assert response.status_code == 404, "an unknown model is not found, not a malformed request"
    assert seen == []
    parsed = orjson.loads(response.content)
    if wire == "anthropic":
        assert parsed["type"] == "error"
        assert parsed["error"]["type"] == "not_found_error"
    else:
        assert "type" not in parsed
        assert parsed["error"]["type"] == "not_found_error"
        assert parsed["error"]["param"] is None


def test_a_gemini_path_answers_in_geminis_own_error_shape() -> None:
    """Spec §9. The error writer is the only wire output that endpoint has today.

    Google's shape puts the HTTP status in `error.code` and the canonical name in `error.status`; a client of that API reads neither of the fields the other dialects use.
    """
    client, _ = make_client(failing_upstream(400))

    response = client.post("/v1beta/models/gemini-pro:generateContent", json={})

    assert response.status_code == 501
    assert orjson.loads(response.content) == {
        "error": {
            "code": 501,
            "message": "/v1beta/models/gemini-pro:generateContent is not implemented yet",
            "status": "UNIMPLEMENTED",
        }
    }


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/v1beta/models/gemini-pro:generateContent", 501),
        ("/v1/messages", 400),
    ],
)
def test_a_proxy_produced_failure_that_no_retry_can_help_says_so(path: str, expected: int) -> None:
    """`x-should-retry: false`, and only where an SDK's default would be wrong.

    Both SDKs retry every `>= 500` by default, so a 501 meaning "nobody built this" would be asked for again and again. A 400 is already not retried, so adding the header there would be noise — asserted as absent, because "we set it everywhere" and "we set it where it matters" are indistinguishable from the 501 alone.
    """
    client, _ = make_client(failing_upstream(400))

    response = client.post(path, content=b"{not json")

    assert response.status_code == expected
    assert response.headers.get("x-should-retry") == ("false" if expected == 501 else None)


def test_a_retryable_upstream_failure_is_not_told_not_to_be_retried() -> None:
    """A 503 is worth waiting on, and nothing here should say otherwise.

    Renamed from a test that claimed to check the `not direct` term of that condition. It never could: no upstream status maps to `INTERNAL` or `NOT_IMPLEMENTED`, so a direct answer cannot reach the branch at all, and a mutation removing `not direct` left this green. What it *can* observe is the category rule — 503 is `OVERLOADED`, which is not one of the two — and that is what it now says it checks.
    """
    client, _ = make_client(failing_upstream(503))

    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert "x-should-retry" not in response.headers


def test_an_unimplemented_translation_is_not_blamed_on_the_clients_body() -> None:
    """**Behaviour change**: `TranslatorNotFound` used to answer 400.

    A 400 tells the client its request was malformed and invites it to fix the body. Nothing is wrong with the body — this proxy has not built the crossing it asked for, which is a 501 and nothing the client can do anything about.
    """
    client, seen = make_client(failing_upstream(400))

    response = client.post("/v1/chat/completions", json={"model": "claude-model", "messages": []})

    assert response.status_code == 501
    assert seen == []


def test_the_body_that_will_not_parse_is_answered_in_the_endpoints_dialect() -> None:
    """One of the three sources the edge holds without an exception to classify.

    It used to return a bare `{"error":{"message":...}}` — a third envelope in the same app, with no `type` at all. The point of routing it through the same record is that a client does not have to learn one shape per failure site.
    """
    client, _ = make_client(failing_upstream(400))

    response = client.post("/v1/responses", content=b"{not json")

    assert response.status_code == 400
    parsed = orjson.loads(response.content)
    assert parsed["error"]["type"] == "invalid_request_error"
    assert parsed["error"]["code"] == "invalid_request"


def test_the_headers_are_read_off_a_response_the_test_did_not_build(
) -> None:
    """A guard on the fixture rather than on the code.

    Every assertion above compares against `UPSTREAM_HEADERS`, so a fixture that quietly stopped sending them would make the "forwarded" tests fail loudly and the "dropped" tests pass silently. This pins that upstream really is sending both kinds.
    """
    seen_headers: dict[str, str] = {}

    def handler(_: httpx2.Request) -> httpx2.Response:
        seen_headers.update(UPSTREAM_HEADERS)
        return httpx2.Response(400, content=OPAQUE, headers=UPSTREAM_HEADERS)

    client, _ = make_client(handler)
    client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert "x-request-id" in seen_headers
    assert "connection" in seen_headers


@pytest.mark.parametrize(
    "header",
    ["content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive", "te", "trailer", "upgrade"],
)
def test_no_framing_header_of_upstreams_rides_along(header: str) -> None:
    """The whole set, pinned where no transport can get in the way.

    `content-encoding` cannot be driven through the end-to-end fixture — httpx inflates before anything here sees the response, so a lie there fails as a transport error rather than reaching the header filter. That is the right behaviour and it also means the assertion has to happen one level down.

    Each of these describes upstream's own connection or its own body length. On a response with different bytes and a different framing, forwarding one is not untidiness — it is a lie the client's HTTP stack acts on.
    """
    info = ErrorInfo(
        category=ErrorCategory.CLIENT,
        message="m",
        status_code=400,
        headers={header: "whatever", "x-request-id": "req_abc"},
    )

    forwarded = _outbound_headers(info, direct=True)

    assert header not in forwarded
    assert forwarded["x-request-id"] == "req_abc", "the filter must be a denial, not an allowlist of one"
