"""The primary path against a recording of what upstream actually said.

Everything here runs on real bytes captured from Copilot: the token exchange, the model catalog,
and a streamed Responses reply to an Anthropic Messages request. Only the network is absent.

Why this file exists rather than another hand-written stand-in: streaming on this exact path
returned HTTP 200 and zero bytes in production while every test was green, because no fake
reproduced upstream's habit of changing an item's id between `added` and `done`. A recording
cannot make that mistake — it does not know what we expected.
"""

import re
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx2
import orjson
import pytest
from recorded.cassettes import (
    KEPT_RESPONSE_HEADERS,
    Cassette,
    RecordingTransport,
    ReplayTransport,
    UnauthenticatedRequest,
)
from recorded.recorded_provider import cassette_path, recorded_chain

from app.pipeline.delivery.formats.anthropic_messages import AnthropicFramer
from app.pipeline.delivery.stream import stream_delivery
from app.server.composition import refresh_catalogs
from app.server.handler import assembler_for, delivery_buffer, handle_bounded, stream_settings
from app.server.inbound import build_context, route_for_path

CASSETTE = "anthropic_to_responses_stream"


def messages_body(**extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": "gpt-5.5",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
    }
    body.update(extra)
    return body


@pytest.mark.asyncio
async def test_the_recorded_catalog_loads_and_offers_a_responses_model() -> None:
    """The catalog request in the cassette is the real one, authentication and all.

    A recording that could be read without authenticating would not have caught the catalog fetch
    going out with no Authorization header at all, which stopped the service from starting.
    """
    async with recorded_chain(CASSETTE) as chain:
        await refresh_catalogs(chain)
        provider = chain.providers.get("ghc")

        assert "gpt-5.5" in provider.available_ids
        descriptor = provider.describe("gpt-5.5")
        assert descriptor is not None
        assert any(endpoint.value == "/responses" for endpoint in descriptor.endpoints)


@pytest.mark.asyncio
async def test_a_recorded_stream_assembles_into_anthropic_blocks() -> None:
    """The regression the recording exists for.

    The captured stream carries a different `item.id` on `output_item.added` and
    `output_item.done`. Paired by id, nothing closes and the client receives nothing at all.
    """
    async with recorded_chain(CASSETTE) as chain:
        await refresh_catalogs(chain)
        route = route_for_path("/v1/messages")
        assert route is not None
        context = build_context(route, messages_body(stream=True))
        handled = await handle_bounded(chain, context)
        response = handled.response
        assert response is not None

        chunks = [
            chunk
            async for chunk in stream_delivery(
                response.aiter_bytes(),
                assembler_for(handled),
                buffer=delivery_buffer(chain),
                settings=stream_settings(chain),
                framer=AnthropicFramer(message_id=context.id, model=context.resolved_model),
            )
        ]

    body = b"".join(chunks)
    assert body, "the recorded response assembled into nothing"
    events = [
        line.removeprefix(b"event: ").decode()
        for line in body.splitlines()
        if line.startswith(b"event: ")
    ]
    assert events[0] == "message_start"
    assert events[-1] == "message_stop"
    assert "content_block_stop" in events, "no block was ever closed"
    assert b"PONG" in body


def test_the_cassette_carries_nothing_that_identifies_the_account() -> None:
    """A cassette is committed, so what it keeps is published.

    Asserted here rather than left to whoever records the next one: the scrub list is a list, and a
    list is exactly the kind of thing that gets one entry short. Two rounds of reading this file by
    hand each found a field the round before had missed.
    """
    raw = cassette_path(CASSETTE).read_text(encoding="utf-8")

    for secret in ("Bearer ", "ghu_", "gho_", "ghp_", "github_pat"):
        assert secret not in raw, f"{secret!r} reached the cassette"

    cassette = Cassette.read(cassette_path(CASSETTE))

    # Checked against the allowlist rather than against a list of things to avoid: a denylist is
    # what let three separate identifying headers through, one per round of reading this by hand.
    for interaction in cassette.interactions:
        unexpected = set(interaction.headers) - KEPT_RESPONSE_HEADERS
        assert not unexpected, f"{sorted(unexpected)} were kept without being allowed"

    # A 64-hex value is what an account hash looks like. The request digests we write ourselves
    # are the same shape, so they are excluded by name rather than by loosening the pattern —
    # the point is that nothing hash-shaped arrived from upstream.
    ours = {interaction.request_shape.get("digest") for interaction in cassette.interactions}
    found = set(re.findall(r"\b[0-9a-f]{64}\b", raw)) - ours
    assert not found, f"something hash-shaped reached the cassette: {sorted(found)[:1]}"


@pytest.mark.asyncio
async def test_replay_hands_back_the_recorded_chunk_boundaries() -> None:
    """The property this whole harness was built for, asserted rather than assumed.

    vcrpy was rejected because it merges a streamed response into one chunk. Nothing was stopping
    this replayer from drifting the same way: collapsing every chunk into one left the other tests
    green, because they only read the assembled result.
    """
    cassette = Cassette.read(cassette_path(CASSETTE))
    recorded = next(
        interaction for interaction in cassette.interactions if interaction.path == "/responses"
    )
    assert len(recorded.chunks) > 1, "this cassette has nothing to say about chunking"

    async with recorded_chain(CASSETTE) as chain:
        await refresh_catalogs(chain)
        route = route_for_path("/v1/messages")
        assert route is not None
        handled = await handle_bounded(chain, build_context(route, messages_body(stream=True)))
        response = handled.response
        assert response is not None
        # `aiter_raw` rather than `aiter_bytes`: the question is what the transport handed over,
        # before any decoding had a chance to re-chunk it.
        replayed = [chunk async for chunk in response.aiter_raw()]

    assert replayed == recorded.chunks


@pytest.mark.asyncio
async def test_the_recorded_upstream_changes_the_id_of_the_same_item() -> None:
    """The recording's own premise, paired the way the assembler pairs.

    Comparing the two id *lists* was not enough: a recording whose ids were stable but whose
    `done` events arrived out of order also made those lists differ, so the assertion passed
    while the defect it stands for was absent.
    """
    async with recorded_chain(CASSETTE) as chain:
        await refresh_catalogs(chain)
        route = route_for_path("/v1/messages")
        assert route is not None
        handled = await handle_bounded(chain, build_context(route, messages_body(stream=True)))
        response = handled.response
        assert response is not None
        raw = await response.aread()

    added: dict[str, str] = {}
    done: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.startswith(b"data: "):
            continue
        try:
            event = cast(dict[str, Any], orjson.loads(line[len(b"data: ") :]))
        except orjson.JSONDecodeError:
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        index = str(event.get("output_index", ""))
        identifier = str(cast(dict[str, Any], item).get("id", ""))
        kind = str(event.get("type", ""))
        if kind == "response.output_item.added":
            added[index] = identifier
        elif kind == "response.output_item.done":
            done[index] = identifier

    paired = [(added[index], done[index]) for index in added.keys() & done.keys()]
    assert paired, "the capture has no item that was both opened and closed"
    assert all(opened != closed for opened, closed in paired), (
        "upstream kept each item's id stable in this recording, so the regression above no longer "
        "reproduces the defect it was written for"
    )


@pytest.mark.asyncio
async def test_a_request_for_something_else_is_not_served_this_recording() -> None:
    """Method and path alone are not enough to say a recorded answer still applies.

    A recording made for a streaming `gpt-5.5` request was being served to any POST of the same
    path, so a regression that changed the model, or stopped asking for a stream, was answered
    with the old recording and nothing noticed.
    """
    async with recorded_chain(CASSETTE) as chain:
        await refresh_catalogs(chain)
        route = route_for_path("/v1/messages")
        assert route is not None
        # Non-streaming: the recording answers a streamed request, so it must not be served.
        handled = await handle_bounded(chain, build_context(route, messages_body()))

    # Asserted on the outcome rather than on the exception type: the SDK wraps a transport error
    # as APIConnectionError and the driver records it, so the observable fact is that no answer
    # came back — which is exactly what should happen when the recording does not apply.
    assert handled.response is None
    assert handled.outcome.error is not None


@pytest.mark.asyncio
async def test_replay_reports_the_recorded_http_version() -> None:
    """Product code propagates `response.extensions`, so a replay that dropped them would lie.

    `pipeline/executor.py` and `anthropic/client.py` both pass the upstream extensions through, so
    a recording of an HTTP/2 exchange replayed without them would look like HTTP/1.1 to everything
    downstream, and any path that depends on the version would be tested against the wrong answer.
    """
    cassette = Cassette.read(cassette_path(CASSETTE))
    recorded = next(
        interaction for interaction in cassette.interactions if interaction.path == "/responses"
    )
    assert recorded.extensions.get("http_version"), "the cassette recorded no protocol version"

    async with recorded_chain(CASSETTE) as chain:
        await refresh_catalogs(chain)
        route = route_for_path("/v1/messages")
        assert route is not None
        handled = await handle_bounded(chain, build_context(route, messages_body(stream=True)))
        response = handled.response
        assert response is not None
        # `response.http_version` decodes it; `extensions` holds the raw bytes httpx expects.
        replayed = response.http_version
        await response.aclose()

    assert replayed == recorded.extensions["http_version"]


@pytest.mark.asyncio
async def test_a_replay_refuses_a_request_that_stopped_authenticating() -> None:
    """The guard that caught the bare catalog fetch, exercised directly.

    Every other test here authenticates, so nothing reached this branch: removing the check left
    them all green. A stand-in that cannot tell an authenticated request from a bare one is how
    the catalog went out with no Authorization and the service could not start.
    """
    cassette = Cassette.read(cassette_path(CASSETTE))
    assert any(interaction.authenticated for interaction in cassette.interactions)

    transport = ReplayTransport(cassette)
    async with httpx2.AsyncClient(transport=transport) as client:
        with pytest.raises(UnauthenticatedRequest):
            await client.get("https://api.githubcopilot.com/copilot_internal/v2/token")


@pytest.mark.asyncio
async def test_the_replayed_protocol_version_comes_from_the_cassette() -> None:
    """Asserted against a version httpx would not invent.

    The captured exchange is HTTP/1.1, which is also what httpx reports when a response carries no
    version at all — so a cassette-versus-replay comparison passes whether the extension was
    replayed or dropped. Recording HTTP/2 makes the two answers differ.
    """
    cassette = Cassette.read(cassette_path(CASSETTE))
    for interaction in cassette.interactions:
        interaction.extensions["http_version"] = "HTTP/2"

    async with httpx2.AsyncClient(transport=ReplayTransport(cassette)) as client:
        response = await client.get(
            "https://api.githubcopilot.com/copilot_internal/v2/token",
            headers={"authorization": "Bearer test"},
        )

    assert response.http_version == "HTTP/2"


class _FakeUpstream(httpx2.AsyncBaseTransport):
    """Answers with a fixed set of chunks, so the recorder can be driven without a network."""

    def __init__(self, chunks: list[bytes], headers: dict[str, str]) -> None:
        self._chunks = chunks
        self._headers = headers

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        del request

        class _Stream(httpx2.AsyncByteStream):
            def __init__(self, chunks: list[bytes]) -> None:
                self._chunks = chunks

            async def __aiter__(self) -> AsyncIterator[bytes]:
                for chunk in self._chunks:
                    yield chunk

        return httpx2.Response(200, headers=self._headers, stream=_Stream(list(self._chunks)))


@pytest.mark.asyncio
async def test_the_recorder_scrubs_an_sse_frame_that_spans_two_chunks() -> None:
    """Drives the scrubber rather than inspecting its past output.

    The other guard reads the cassette that is already committed, so making the scrubber a no-op
    left it green — and the next re-record would have published identity data again. This one
    records, and it splits a frame across chunks because that is what a real capture does: only 9
    of 26 chunks ended on a frame boundary, and a scrubber that worked chunk by chunk parsed
    truncated JSON, failed silently and left the identifiers in place.
    """
    frame = (
        b'event: response.created\n'
        b'data: {"response":{"safety_identifier":"' + b"a" * 64 + b'","id":"resp_1"}}\n\n'
    )
    split = len(frame) // 2
    chunks = [frame[:split], frame[split:]]

    recorder = RecordingTransport(
        _FakeUpstream(chunks, {"content-type": "text/event-stream", "x-request-id": "trace-me"})
    )
    async with (
        httpx2.AsyncClient(transport=recorder) as client,
        client.stream("POST", "https://upstream.test/responses") as response,
    ):
        [chunk async for chunk in response.aiter_raw()]

    recorded = recorder.cassette.interactions[0]
    body = b"".join(recorded.chunks)

    assert b"a" * 64 not in body, "the account hash survived recording"
    assert b'"safety_identifier":"REDACTED"' in body
    assert len(recorded.chunks) == len(chunks), "chunk boundaries were lost while scrubbing"
    assert set(recorded.headers) <= KEPT_RESPONSE_HEADERS, "a header outside the allowlist was kept"


@pytest.mark.asyncio
async def test_the_recorder_hands_downstream_what_upstream_sent() -> None:
    """The recorder is transparent, not just faithful to disk.

    The first fix preserved extensions from cassette to replay but not from upstream to the live
    code during recording, so a recording session saw HTTP/1.1 for an HTTP/2 exchange — and any
    behaviour that depends on the version would have been recorded from the wrong branch.
    """
    upstream = _FakeUpstream([b'{"ok":true}'], {"content-type": "application/json"})

    class _Http2(httpx2.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
            response = await upstream.handle_async_request(request)
            response.extensions["http_version"] = b"HTTP/2"
            return response

    recorder = RecordingTransport(_Http2())
    async with httpx2.AsyncClient(transport=recorder) as client:
        live = await client.get("https://upstream.test/probe")

    assert live.http_version == "HTTP/2", "the live response lost what upstream reported"
    assert recorder.cassette.interactions[0].extensions["http_version"] == "HTTP/2"
