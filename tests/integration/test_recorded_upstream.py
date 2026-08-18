"""The primary path against a recording of what upstream actually said.

Everything here runs on real bytes captured from Copilot: the token exchange, the model catalog,
and a streamed Responses reply to an Anthropic Messages request. Only the network is absent.

Why this file exists rather than another hand-written stand-in: streaming on this exact path
returned HTTP 200 and zero bytes in production while every test was green, because no fake
reproduced upstream's habit of changing an item's id between `added` and `done`. A recording
cannot make that mistake — it does not know what we expected.
"""

from typing import Any, cast

import orjson
import pytest
from support.recorded_provider import recorded_chain

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
                message_id=context.id,
                model=context.resolved_model,
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


@pytest.mark.asyncio
async def test_the_recorded_upstream_really_does_change_the_item_id() -> None:
    """The recording's own premise, asserted so it cannot quietly stop holding.

    If a future re-recording came from an upstream that kept ids stable, the regression above
    would still pass while no longer testing anything. This says out loud what makes it a test.
    """
    async with recorded_chain(CASSETTE) as chain:
        await refresh_catalogs(chain)
        route = route_for_path("/v1/messages")
        assert route is not None
        handled = await handle_bounded(chain, build_context(route, messages_body(stream=True)))
        response = handled.response
        assert response is not None
        raw = await response.aread()

    ids: dict[str, list[str]] = {"added": [], "done": []}
    for line in raw.splitlines():
        if not line.startswith(b"data: "):
            continue
        try:
            event = cast(dict[str, Any], orjson.loads(line[len(b"data: ") :]))
        except orjson.JSONDecodeError:
            continue
        kind = str(event.get("type", ""))
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        identifier = str(cast(dict[str, Any], item).get("id", ""))
        if kind == "response.output_item.added":
            ids["added"].append(identifier)
        elif kind == "response.output_item.done":
            ids["done"].append(identifier)

    assert ids["added"] and ids["done"], "the capture has no output items to compare"
    assert ids["added"] != ids["done"], (
        "upstream kept the item ids stable in this recording, so the regression above no longer "
        "reproduces the defect it was written for"
    )
