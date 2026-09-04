"""Probe 4: is the first attempt's upstream response released before the second one is opened?

Uses the idle guard rather than a tear, because a torn body has already ended httpx's own
iterator — the interesting case is a *healthy* upstream that delivery walks away from.
"""

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx2

sys.path.insert(0, str(Path("/home/xp/src/ghc-api-proxy-py/tests/int")))

from test_pipeline_app import make_client, sse_upstream  # noqa: E402


async def _goes_quiet() -> AsyncIterator[bytes]:
    yield b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n'
    await asyncio.sleep(30)
    yield b"never"


def test_the_abandoned_response_is_closed_before_the_next_is_opened() -> None:
    responses: list[httpx2.Response] = []
    closed_when_second_arrived: list[bool] = []

    def upstream(request: httpx2.Request) -> httpx2.Response:
        del request
        if not responses:
            first = httpx2.Response(
                200, content=_goes_quiet(), headers={"content-type": "text/event-stream"}
            )
            responses.append(first)
            return first
        closed_when_second_arrived.append(responses[0].is_closed)
        return httpx2.Response(
            200, content=sse_upstream("kept"), headers={"content-type": "text/event-stream"}
        )

    client, _ = make_client(
        upstream,
        overrides={
            "client_delivery": {"sse_ping_interval": 0},
            "upstream_request_timeouts": {"stream_idle": 1, "upstream_request_deadline": 60},
        },
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [], "stream": True},
    )
    print("STATUS", response.status_code)
    print("CLOSED WHEN SECOND ARRIVED", closed_when_second_arrived)
    print("CLOSED AT END", [r.is_closed for r in responses])
    print("FULL", repr(response.text))
    assert closed_when_second_arrived == [True], "the abandoned upstream response was still open"
