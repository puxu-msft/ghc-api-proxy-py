"""Review-only probes. Lives in the /tmp snapshot; never written to the repository."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from fastapi.testclient import TestClient

from app.streaming.deadline import StreamDeadlineError
from tests.http.test_pipeline_app import (  # type: ignore[import-untyped]
    _request_lines,
    _upstream_that_goes_quiet,
    make_client,
    request_log,  # noqa: F401  (fixture)
    sse_upstream,
)


def _trickles(rounds: int, *, header_delay: float = 0.0) -> Callable[[httpx.Request], httpx.Response]:
    whole = sse_upstream("first")
    head, _, tail = whole.partition(b"event: message_delta")

    async def handler(_: httpx.Request) -> httpx.Response:
        if header_delay:
            await asyncio.sleep(header_delay)

        async def body() -> AsyncIterator[bytes]:
            yield head
            for _round in range(rounds):
                await asyncio.sleep(0.05)
                yield b": ping\n\n"
            yield b"event: message_delta" + tail

        return httpx.Response(200, content=body(), headers={"content-type": "text/event-stream"})

    return handler  # type: ignore[return-value]


def _stream(client: TestClient) -> tuple[bytes, BaseException | None]:
    try:
        with client.stream(
            "POST", "/v1/messages", json={"model": "claude-model", "messages": [], "stream": True}
        ) as response:
            assert response.status_code == 200
            return b"".join(response.iter_bytes()), None
    except BaseException as exc:  # noqa: BLE001
        return b"", exc


# ---------------------------------------------------------------------------
# P1  What the client and the log see when the body-phase deadline fires.
# ---------------------------------------------------------------------------
def test_probe_body_deadline_client_and_log(request_log: None, caplog: pytest.LogCaptureFixture) -> None:  # noqa: F811
    client, seen = make_client(
        _trickles(rounds=60),
        overrides={"upstream_request_timeouts": {"upstream_request_deadline": 1}},
    )
    with caplog.at_level(logging.INFO):
        body, exc = _stream(client)
    print("\nP1 upstream requests sent:", len(seen))
    print("P1 client exception:", type(exc).__name__ if exc else None, exc)
    print("P1 log lines:", _request_lines(caplog.records))


# ---------------------------------------------------------------------------
# P2  Is the deadline measured from attempt start, or restarted at the headers?
#     header_delay eats most of the budget; a chain that recomputes gets a fresh one.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("header_delay", [0.0, 1.5])
def test_probe_deadline_origin(header_delay: float) -> None:
    client, _ = make_client(
        _trickles(rounds=200, header_delay=header_delay),
        overrides={"upstream_request_timeouts": {"upstream_request_deadline": 2}},
    )
    started = time.monotonic()
    _body, exc = _stream(client)
    print(
        f"\nP2 header_delay={header_delay}: ended after {time.monotonic() - started:.2f}s"
        f" with {type(exc).__name__ if exc else 'clean finish'}"
    )


# ---------------------------------------------------------------------------
# P3  Does a config that still sets stream_idle_overrides still do anything?
# ---------------------------------------------------------------------------
def test_probe_stream_idle_overrides_still_honoured() -> None:
    client, _ = make_client(
        _upstream_that_goes_quiet(1.5),
        overrides={
            "upstream_request_timeouts": {
                "stream_idle": 0,
                "stream_idle_overrides": {"claude-model": 1},
            }
        },
    )
    _body, exc = _stream(client)
    print("\nP3 config accepted the overrides key; outcome:", type(exc).__name__ if exc else "delivered in full")


# ---------------------------------------------------------------------------
# P4  Non-streaming: is the whole attempt still bounded, and still retried?
# ---------------------------------------------------------------------------
def test_probe_non_streaming_still_bounded(request_log: None, caplog: pytest.LogCaptureFixture) -> None:  # noqa: F811
    async def slow_body(_: httpx.Request) -> httpx.Response:
        async def body() -> AsyncIterator[bytes]:
            await asyncio.sleep(3)
            yield b'{"id":"msg_1","content":[]}'

        return httpx.Response(200, content=body(), headers={"content-type": "application/json"})

    client, seen = make_client(
        slow_body,  # type: ignore[arg-type]
        overrides={"upstream_request_timeouts": {"upstream_request_deadline": 1}},
    )
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/v1/messages", json={"model": "claude-model", "messages": []}
        )
    print("\nP4 status:", response.status_code, "body:", response.text[:200])
    print("P4 upstream requests sent:", len(seen))
    print("P4 log lines:", _request_lines(caplog.records))


# ---------------------------------------------------------------------------
# P5  count_tokens: is anything bounding it?
# ---------------------------------------------------------------------------
def test_probe_count_tokens_is_unbounded() -> None:
    async def slow(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(2.0)
        return httpx.Response(200, json={"input_tokens": 7})

    client, _ = make_client(
        slow,  # type: ignore[arg-type]
        overrides={
            "upstream_request_timeouts": {
                "upstream_request_deadline": 1,
                "response_header": 1,
            }
        },
    )
    started = time.monotonic()
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
    )
    print(
        f"\nP5 count_tokens answered {response.status_code} {response.json()}"
        f" after {time.monotonic() - started:.2f}s with both guards set to 1s"
    )
