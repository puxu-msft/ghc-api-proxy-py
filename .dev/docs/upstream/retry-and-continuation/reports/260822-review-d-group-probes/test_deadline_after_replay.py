"""Probe 2: is `client_request_deadline` still enforced over the body of a *replayed* attempt?

`with_client_deadline_at` wraps the first byte iterator only. `_deliver` rebinds `chunks` to
whatever `reopen()` returns, and `_reopen` builds its chain out of `with_idle_timeout` and
`with_deadline_at` alone. So the guard the commit message calls "the longest-lived" is dropped
at exactly the moment a second attempt begins.
"""

import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx2

sys.path.insert(0, str(Path("/home/xp/src/ghc-api-proxy-py/tests/int")))

from test_pipeline_app import make_client, sse_upstream  # noqa: E402


async def _slow(text: str, *, seconds: float) -> AsyncIterator[bytes]:
    """One complete Anthropic block, then a long silence broken by keep-alive-ish bytes."""
    payload = sse_upstream(text)
    yield payload[: payload.index(b"event: message_delta")]
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        # Comment frames: they defeat the idle guard without ever completing the turn.
        yield b": upstream keepalive\n\n"
        import asyncio

        await asyncio.sleep(0.1)
    yield payload[payload.index(b"event: message_delta") :]


def test_the_client_deadline_survives_a_replay() -> None:
    calls: list[int] = []

    async def torn_body() -> AsyncIterator[bytes]:
        yield b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n'
        raise httpx2.RemoteProtocolError("peer closed the connection")

    def upstream(request: httpx2.Request) -> httpx2.Response:
        del request
        calls.append(1)
        if len(calls) == 1:
            return httpx2.Response(
                200, content=torn_body(), headers={"content-type": "text/event-stream"}
            )
        return httpx2.Response(
            200,
            content=_slow("kept", seconds=6.0),
            headers={"content-type": "text/event-stream"},
        )

    client, _ = make_client(
        upstream,
        overrides={
            "client_delivery": {"client_request_deadline": 2, "sse_ping_interval": 0},
            "upstream_request_timeouts": {"upstream_request_deadline": 60},
        },
    )
    started = time.monotonic()
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [], "stream": True},
    )
    elapsed = time.monotonic() - started
    print("STATUS", response.status_code, "ELAPSED", round(elapsed, 2), "CALLS", len(calls))
    print("TAIL", response.text[-400:])
    assert len(calls) == 2
    assert elapsed < 4.0, (
        f"the client deadline was 2s; the replayed body ran for {elapsed:.1f}s unguarded"
    )
