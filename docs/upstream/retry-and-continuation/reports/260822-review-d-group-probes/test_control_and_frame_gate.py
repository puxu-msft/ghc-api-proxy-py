"""Positive control for probe 2, plus probe 3 on the frame gate.

Control: the same slow body with *no* tear, so only the first attempt exists and
`with_client_deadline_at` is in the chain. If this one is also unbounded the probe measures
nothing; it has to be cut at the deadline for the replay result to mean anything.

Probe 3: the human-controlled `client-side-block-delivery.md` keys the SSE error frame on
"已发 HTTP 200 响应头", and a2c9b77 established that the 200 is out before delivery pulls a chunk.
`_deliver` keys it on `client_has_bytes` instead, which under `policy: full` stays unset for the
whole turn.
"""

import asyncio
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx2
import pytest

sys.path.insert(0, str(Path("/home/xp/src/ghc-api-proxy-py/tests/int")))

from app.pipeline.delivery.assembler import AnthropicAssembler  # noqa: E402
from app.pipeline.delivery.blocks import BlockBuffer  # noqa: E402
from app.pipeline.delivery.stream import StreamSettings, stream_delivery  # noqa: E402
from app.streaming.deadline import ClientDeadlineError  # noqa: E402
from test_pipeline_app import make_client, sse_upstream  # noqa: E402


async def _slow(text: str, *, seconds: float) -> AsyncIterator[bytes]:
    payload = sse_upstream(text)
    yield payload[: payload.index(b"event: message_delta")]
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        yield b": upstream keepalive\n\n"
        await asyncio.sleep(0.1)
    yield payload[payload.index(b"event: message_delta") :]


def test_control_the_client_deadline_does_bound_a_first_attempt() -> None:
    def upstream(request: httpx2.Request) -> httpx2.Response:
        del request
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
    print("CONTROL STATUS", response.status_code, "ELAPSED", round(elapsed, 2))
    print("CONTROL TAIL", repr(response.text))
    assert elapsed < 4.0, "the guard does not bound even a first attempt; probe 2 proves nothing"


@pytest.mark.asyncio
async def test_probe3_full_policy_client_deadline_gets_no_frame() -> None:
    async def body() -> AsyncIterator[bytes]:
        payload = sse_upstream("held")
        yield payload[: payload.index(b"event: message_delta")]
        raise ClientDeadlineError("client request exceeded its deadline")

    chunks: list[bytes] = []
    with pytest.raises(ClientDeadlineError):
        async for chunk in stream_delivery(
            body(),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="full"),
            settings=StreamSettings(sse_ping_interval=0),
            message_id="msg_1",
            model="claude-model",
        ):
            chunks.append(chunk)
    print("PROBE3 CHUNKS", b"".join(chunks))
    assert b"client_deadline_exceeded" not in b"".join(chunks)
