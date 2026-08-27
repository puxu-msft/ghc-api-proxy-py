"""What a client actually receives when a request fails, through the real app.

The ruling these serve is the user's of 2026-08-23: on a direct path the client gets upstream's own answer, including the parts this proxy does not understand; on a translated path the failure crosses an internal representation and is written in the client's dialect. `.dev/docs/error-envelope/spec.md` is the current normative form of it, and it is a living document.

Two things about how these are written, both from a plan review:

**The direct-path sample is not ordinary JSON.** An implementation that parses upstream's body and serialises it again produces the same bytes for `{"error":{...}}`, so a test using one cannot tell passthrough from a round trip. `b"\\xffraw-body"` can: it is not valid UTF-8 and not valid JSON, so anything that decodes or re-encodes it changes it.

**Headers are asserted in both directions.** Today's behaviour — dropping every one of upstream's headers except a reformatted `Retry-After` on a 429 — passes any test that only checks the ones that should survive.
"""

from typing import Any

import httpx2
import orjson
import pytest
from fastapi.testclient import TestClient

# Same directory, so pytest's default `prepend` import mode puts it on the path. There is no `tests` package to import through — `tests/__init__.py` does not exist, deliberately.
from test_pipeline_app import make_client, sse_upstream

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


# ---------------------------------------------------------------------------
# Streaming: what the client actually receives when a turn fails mid-flight.
#
# A mapping can be correct and unused. `tests/unit/pipeline/delivery/test_error_frames.py`
# pins the table and the frame's shape; these drive real failures through the real app and
# read the bytes, which is the only thing that says the two are connected.
# ---------------------------------------------------------------------------


def _streamed(client: Any, body: dict[str, Any]) -> bytes:
    """Everything that reached the client, recorded by a tee around the app.

    **Not read off the response object**, and that is the whole reason this exists. Starlette's test client only rewinds its buffer when it sees `more_body=False`; a stream that ends by raising never reaches that line, so the response reads from the tail and reports `b""`. Every ending examined here frames the error and *then* re-raises — deliberately: the frame tells the client, the exception tells this side's own accounting — so reading the response would report zero bytes for exactly the cases in question. Measured; `.dev/docs/server-layout/reports/260823-error-surface-inventory.md` §6 records the same trap costing a whole round of readings.

    A tee rather than driving the ASGI app by hand: constructing a scope by hand skips whatever the test client sets up around it, and a first attempt at that hung instead of failing.
    """
    chunks: list[bytes] = []
    app = client.app

    async def tee(scope: Any, receive: Any, send: Any) -> None:
        async def recording(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
            await send(message)

        await app(scope, receive, recording)

    teed = TestClient(tee, base_url="http://t")
    try:
        with teed.stream("POST", "/v1/messages", json={**body, "stream": True}) as response:
            for _ in response.iter_bytes():
                pass
    except Exception:
        pass
    return b"".join(chunks)


def _error_frames(delivered: bytes) -> list[dict[str, Any]]:
    return [
        orjson.loads(chunk.split(b"data: ", 1)[1])
        for chunk in delivered.split(b"\n\n")
        if chunk.startswith(b"event: error")
    ]


def _upstream_that_stops_after_a_block() -> Any:
    """A whole block, then EOF with no terminal event. Upstream's stream simply ends."""
    whole = sse_upstream("first")
    cut = whole.split(b"event: message_delta", 1)[0]

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=cut, headers={"content-type": "text/event-stream"})

    return handler


def test_an_upstream_that_ends_without_a_terminal_says_so_in_anthropics_words() -> None:
    """The wiring, driven through the app so the mapping, the framer and the call site have to agree.

    The unit test one directory over would still pass if `stream_delivery` had stopped calling any of them; this is what says they are connected.

    **What it cannot check is the category.** A mutation swapping `UPSTREAM` for `INTERNAL` at that call site left this green, and correctly so: Anthropic spells both `api_error` and OpenAI spells both `server_error`, so the choice is unobservable on every leg this proxy serves. `code` is the discriminator and it is set independently — which is the same loss §6.4 records, met here rather than in the abstract. Asserting the type anyway would be asserting something no implementation could get wrong.
    """
    # Both switches, and the second one is the trap. Emptying `unterminated_stream_stop_reason` alone does **not** produce an error frame any more: since 2026-08-24 a reported failure with a block already delivered is offered to the hand-over first, so on the production shape it comes out as a `turn_interrupted` tool call. The SSE error is what remains when the hand-over does not apply — measured, not assumed.
    client, _ = make_client(
        _upstream_that_stops_after_a_block(),
        overrides={
            "client_delivery": {"unterminated_stream_stop_reason": ""},
            "upstream_request_retry": {"auto_retry_tool_call_full_name": ""},
        },
    )

    delivered = _streamed(client, {"model": "claude-model", "messages": []})
    frames = _error_frames(delivered)

    assert frames, f"no error frame in {delivered!r}"
    payload = frames[-1]
    assert payload["type"] == "error"
    assert "message" not in payload, "the nested shape has to survive the whole delivery chain"
    assert payload["error"]["type"] == "api_error"
    assert payload["error"]["code"] == "incomplete_responses_stream"


def test_a_buffer_cap_this_side_blew_is_named_as_this_sides() -> None:
    """`INTERNAL`, and the only thing that says so is `code` — the type is `api_error` either way.

    The cap is this proxy's own limit, so a client transcript showing `upstream_stream_failed` here would send a reader to the wrong system entirely.
    """
    client, _ = make_client(
        _upstream_that_stops_after_a_block(),
        overrides={
            "client_delivery": {"buffering_policy": "full", "buffer_cap_bytes": 8},
            "upstream_request_retry": {"auto_retry_tool_call_full_name": ""},
        },
    )

    delivered = _streamed(client, {"model": "claude-model", "messages": []})
    frames = _error_frames(delivered)

    assert frames, f"no error frame in {delivered!r}"
    payload = frames[-1]
    assert payload["error"]["type"] == "api_error"
    assert payload["error"]["code"] == "proxy_delivery_aborted"


# ---------------------------------------------------------------------------
# Upstream saying, mid-stream, that the turn failed.
#
# Until 2026-08-24 both assemblers logged such an event and returned nothing, so the loop
# ran on to a terminal-less ending — which, since the clean-EOF change of 2026-08-22, looks
# like success. Upstream said it failed and the client could not tell it from a completed turn.
# ---------------------------------------------------------------------------


def _upstream_that_reports_failure(event: str, payload: str) -> Any:
    """One whole block, then upstream's own failure event, then EOF."""
    whole = sse_upstream("first")
    prefix = whole.split(b"event: message_delta", 1)[0]
    body = prefix + f"event: {event}\ndata: {payload}\n\n".encode()

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    return handler


def _events(delivered: bytes) -> list[str]:
    return [
        chunk.split(b"event: ", 1)[1].split(b"\n", 1)[0].decode()
        for chunk in delivered.split(b"\n\n")
        if chunk.startswith(b"event: ")
    ]


ANTHROPIC_FAILURE = (
    '{"type":"error","error":{"type":"overloaded_error","message":"upstream is overloaded",'
    '"vendor_hint":"a field nothing here knows"}}'
)


def test_a_direct_leg_replays_upstreams_failure_event_untouched() -> None:
    """The client speaks upstream's dialect, so it gets upstream's own words — unknown fields included.

    `vendor_hint` is the assertion that matters. Anything that read this into a record and wrote it back out would drop it, and dropping it is exactly what "even if we do not know it, it can still be passed on" forbids.
    """
    client, _ = make_client(_upstream_that_reports_failure("error", ANTHROPIC_FAILURE))

    delivered = _streamed(client, {"model": "claude-model", "messages": []})
    frames = _error_frames(delivered)

    assert frames, f"the failure event never reached the client: {delivered!r}"
    assert frames[-1]["error"]["type"] == "overloaded_error"
    assert frames[-1]["error"]["vendor_hint"] == "a field nothing here knows"


def test_a_reported_failure_does_not_end_with_a_terminal_that_reads_as_success() -> None:
    """The defect this slice exists for, stated as what must **not** be on the wire.

    Before this, the client received `message_delta` with a stop reason and then `message_stop` — a syntactically complete turn. Not merely indistinguishable from a torn connection, which is what the code comments claimed: indistinguishable from a turn that finished.
    """
    client, _ = make_client(_upstream_that_reports_failure("error", ANTHROPIC_FAILURE))

    delivered = _streamed(client, {"model": "claude-model", "messages": []})
    events = _events(delivered)

    assert "error" in events
    assert "message_stop" not in events, f"a failed turn ended as a completed one: {events}"
    assert "message_delta" not in events
    # What had already been delivered still is. The failure ends the turn; it does not retract what arrived.
    assert b'"text":"first"' in delivered


RESPONSES_FAILED = '{"type":"response.failed","response":{"error":{"code":"server_error","message":"boom"}}}'
RESPONSES_CANCELLED = '{"type":"response.cancelled","response":{"error":{"code":"cancelled","message":"stopped"}}}'


@pytest.mark.parametrize(
    "event, payload", [("response.failed", RESPONSES_FAILED), ("response.cancelled", RESPONSES_CANCELLED)]
)
def test_a_direct_responses_leg_keeps_upstreams_own_event_name(event: str, payload: str) -> None:
    """`response.failed` and `response.cancelled` are different things to a client of that API.

    Normalising both to `error` would be this proxy deciding they are the same, which it is not entitled to do on a leg it is only carrying.
    """
    from test_pipeline_app import responses_sse_upstream

    whole = responses_sse_upstream()
    prefix = whole.split(b"event: response.completed", 1)[0]
    body = prefix + f"event: {event}\ndata: {payload}\n\n".encode()

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client, _ = make_client(handler)
    with client.stream("POST", "/v1/responses", json={"model": "gpt-model", "input": [], "stream": True}) as response:
        delivered = b"".join(response.iter_bytes())

    assert event in _events(delivered), f"upstream's own event name was lost: {_events(delivered)}"


def test_a_translated_leg_spells_upstreams_failure_in_the_clients_dialect() -> None:
    """Anthropic client, Responses upstream: the client cannot read `response.failed`.

    So the failure crosses the record and comes out as this client's own error frame. The other direction of the same ruling — the direct test above asserts upstream's words survive; this one asserts they are translated when they must be.
    """
    from test_pipeline_app import responses_sse_upstream

    whole = responses_sse_upstream()
    prefix = whole.split(b"event: response.completed", 1)[0]
    body = prefix + f"event: response.failed\ndata: {RESPONSES_FAILED}\n\n".encode()

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client, _ = make_client(handler)
    delivered = _streamed(client, {"model": "gpt-model", "messages": []})
    events = _events(delivered)

    assert "response.failed" not in events, "a dialect the client does not speak reached it"
    assert "error" in events
    assert "message_stop" not in events
    frames = _error_frames(delivered)
    assert frames[-1]["error"]["code"] == "server_error"


# ---------------------------------------------------------------------------
# The two remaining exits from the inventory.
# ---------------------------------------------------------------------------

ONLY_UPSTREAM_COUNTER = {"inbound": {"anthropic_count_tokens": {"providers": ["upstream"], "max_retries": 0}}}


@pytest.mark.parametrize("status", [400, 500])
def test_a_failed_count_reports_what_upstream_said_rather_than_one_flat_503(status: int) -> None:
    """Upstream's 400 and its 500 are different things, and both used to arrive as 503 with none of its body.

    Parametrised over both rather than asserting one, because the defect was that they were *the same*: `CountTokensUnavailable` flattened every reason into one status and kept no cause to read back.

    The local estimator is configured out. With it in the list this endpoint answers 200 with an estimate and never reaches the failure at all — which is the right default and also means a test using it would prove nothing about this path.
    """
    client, _ = make_client(
        failing_upstream(status, content=b'{"error":{"message":"upstream says"}}',
                         headers={"content-type": "application/json"}),
        overrides=ONLY_UPSTREAM_COUNTER,
    )

    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == status
    # Upstream's own body: this is a direct path, and a count is not exempt from that.
    assert response.json() == {"error": {"message": "upstream says"}}


def test_the_local_estimator_still_answers_when_it_is_configured() -> None:
    """The control for the test above. Without it, `providers: ["upstream"]` could be doing the work rather than the read-through."""
    client, _ = make_client(failing_upstream(500))

    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert response.json()["estimated"] is True


def test_upstream_calling_a_non_json_body_json_is_not_this_proxys_fault() -> None:
    """The only non-JSON error response the whole proxy used to produce.

    `response.json()` was not inside a `try`, so the decode error left `_dispatch` and Starlette answered `500 text/plain` with the five words `Internal Server Error` — nothing a client can parse and nothing an operator can act on.

    502 rather than 500: nothing here is broken. Upstream answered 200 and called something JSON that is not.
    """
    client, _ = make_client(
        failing_upstream(200, content=b"<html>not json</html>", headers={"content-type": "text/html"})
    )

    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/json")
    body = orjson.loads(response.content)
    assert body["type"] == "error"
    assert body["error"]["type"] == "api_error"


def test_upstream_sending_json_that_is_not_an_object_is_caught_too() -> None:
    """The neighbouring case, which the first branch does not cover: valid JSON, wrong shape.

    A bare list decodes without raising, so a `try` around the decode alone would let it through to whatever reads `body["..."]` next — one `KeyError` further along, with a worse answer.
    """
    client, _ = make_client(failing_upstream(200, content=b"[1,2,3]", headers={"content-type": "application/json"}))

    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert response.status_code == 502
    assert orjson.loads(response.content)["error"]["type"] == "api_error"


# Upstream's own bytes, verbatim from `.dev/docs/upstream/retry-and-continuation/reports/260821-context-limit-400-examples.md` §1.2, trailing newline and all. This leg declares `text/plain` over a JSON body, which is itself part of what a reader here has to survive.
RESPONSES_LEG_OVERFLOW = b'{"error":{"message":"Your input exceeds the context window of this model. Please adjust your input and try again.","code":"invalid_request_body"}}\n'
# Same failure as it reached a user on 2026-08-24. One word of upstream's sentence drifted.
RESPONSES_LEG_OVERFLOW_DRIFTED = b'{"error":{"message":"Your input exceeds the context window of this model. Please adjust your input and try again again.","code":"invalid_request_body"}}\n'
# Same leg, same `error.code`, unrelated failure. `invalid_request_body` carries no discriminating power here, which is why this control is the one that decides whether the predicate is real.
RESPONSES_LEG_UNRELATED = b'{"error":{"message":"Invalid \'max_output_tokens\': integer below minimum value. Expected a value >= 16, but got 8 instead.","code":"invalid_request_body"}}\n'

PLAIN_JSON = {"content-type": "text/plain; charset=utf-8"}


@pytest.mark.parametrize(
    "body", [RESPONSES_LEG_OVERFLOW, RESPONSES_LEG_OVERFLOW_DRIFTED], ids=["recorded", "drifted"]
)
def test_a_translated_context_overflow_reaches_the_client_in_the_idiom_it_acts_on(
    body: bytes,
) -> None:
    """Spec §5.5.3, asserted as the client's own predicate rather than as the sentence this proxy happens to write.

    Claude Code lowercases the whole serialised error object and asks whether it contains this substring — measured across 2.1.207 / 2.1.226 / 2.1.241, `reports/260824-claude-code-context-limit-detection.md`. So the assertion is made against the serialised bytes, the way the client makes it. Pinning the exact sentence instead would go green for a rewrite that moved the phrase somewhere the client never looks.

    Recognising it is what makes the client compact and resend. Not recognising it leaves an `API Error: 400 {…}` in the transcript and the turn stops there.
    """
    client, _ = make_client(failing_upstream(400, content=body, headers=PLAIN_JSON))

    response = client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    assert response.status_code == 400
    assert "prompt is too long" in response.content.decode().lower()


def test_the_overflow_envelope_keeps_anthropics_own_shape() -> None:
    """Anthropic's error body is a tagged union at the top level, and this is that shape.

    **Not** a context-matcher test, although the first version of this file said it was: the claim was that a flattened envelope would carry the right words and go unrecognised, and the probe beside the client report disproves it — with a top-level `message`, the client searches that field, and the phrase is in it either way. The nesting is required by §6.3 for its own two reasons (the carrier's legal shape, and the `overloaded_error` predicate whose keyword sits in a field a flat envelope would discard), and borrowing a disproved cause to support a correct rule is how a spec starts being wrong in the places nobody re-reads.
    """
    client, _ = make_client(
        failing_upstream(400, content=RESPONSES_LEG_OVERFLOW, headers=PLAIN_JSON)
    )

    response = client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    body = orjson.loads(response.content)
    assert "message" not in body
    assert "prompt is too long" in body["error"]["message"]
    assert body["error"]["type"] == "invalid_request_error"
    assert body["error"]["code"] == "model_max_prompt_tokens_exceeded"


def test_an_unrelated_400_on_the_same_leg_is_not_dressed_as_an_overflow() -> None:
    """Without this, `code == "invalid_request_body"` would pass every assertion above while telling a client to throw away a conversation over a malformed field."""
    client, _ = make_client(
        failing_upstream(400, content=RESPONSES_LEG_UNRELATED, headers=PLAIN_JSON)
    )

    response = client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    body = orjson.loads(response.content)
    assert "prompt is too long" not in response.content.decode().lower()
    assert body["error"]["code"] == "invalid_request"
    assert "max_output_tokens" in body["error"]["message"]


def test_a_direct_leg_still_hands_on_upstreams_own_overflow_untouched() -> None:
    """The ruling's first clause outranks the restatement: on a direct leg the client and upstream share a dialect, so this proxy has no business rewording either one.

    It costs nothing here — Copilot's Anthropic leg already says `prompt is too long`, with the counts — which is exactly why only the translated leg was ever broken.
    """
    native = (
        b'{"error":{"code":"model_max_prompt_tokens_exceeded","message":"prompt is too long: '
        b'1051542 tokens > 1000000 maximum","type":"invalid_request_error"},'
        b'"request_id":"req_011CdqwDkJy9YDgyzVF2fixv","type":"error"}'
    )
    client, _ = make_client(
        failing_upstream(400, content=native, headers={"content-type": "application/json"})
    )

    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert response.content == native
