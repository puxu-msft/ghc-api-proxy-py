"""PoC: drive AsyncOpenAI's *low-level* transport to get raw upstream SSE bytes,
bypassing the typed `.chat.completions.create(stream=True)` parser entirely.

Validates three things against the mock server in mock_server.py:
  1. The exact low-level API shape that returns an httpx.Response (not a
     pydantic-parsed object, not the SDK's `Stream`/`AsyncStream` wrapper).
  2. Custom headers (Copilot-Integration-Id, editor-version, X-Initiator,
     Openai-Intent) and extra body fields survive end to end.
  3. Chunks arrive incrementally (no internal buffering) by measuring the
     wall-clock time between `async for chunk in resp.aiter_bytes()` yields.
"""

import asyncio
import json
import time

import httpx
from openai import AsyncOpenAI

BASE_URL = "http://127.0.0.1:8811"


async def main() -> None:
    client = AsyncOpenAI(
        api_key="sk-mock-does-not-matter",
        base_url=BASE_URL,
        timeout=30.0,
        max_retries=0,
    )

    extra_headers = {
        "Copilot-Integration-Id": "vscode-chat",
        "editor-version": "vscode/1.99.0",
        "X-Initiator": "user",
        "Openai-Intent": "conversation-panel",
    }
    body = {
        "model": "gpt-4o-mock",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        # non-standard passthrough field a real client might send
        "x_client_extra_field": {"foo": "bar"},
    }

    t0 = time.monotonic()

    # --- The core low-level call under test -----------------------------
    # cast_to=httpx.Response makes `_process_response` short-circuit and
    # return the raw httpx.Response object untouched (see _base_client.py,
    # `if cast_to == httpx.Response: return cast(ResponseT, response)`).
    # stream=True makes the underlying `self._client.send(request, stream=True)`
    # call defer reading the body, so `resp` here is NOT fully read yet.
    resp: httpx.Response = await client.post(
        "/chat/completions",
        cast_to=httpx.Response,
        body=body,
        options={"headers": extra_headers},
        stream=True,
    )
    # ----------------------------------------------------------------------

    print(f"[t={time.monotonic() - t0:6.3f}s] got httpx.Response object, status={resp.status_code}")
    print(f"[t={time.monotonic() - t0:6.3f}s] response.is_stream_consumed = {resp.is_stream_consumed}")
    assert isinstance(resp, httpx.Response), f"expected raw httpx.Response, got {type(resp)}"
    assert not resp.is_stream_consumed, "response body was already read eagerly -- buffering detected!"

    chunk_times: list[float] = []
    raw_chunks: list[bytes] = []
    async for chunk in resp.aiter_bytes():
        now = time.monotonic() - t0
        chunk_times.append(now)
        raw_chunks.append(chunk)
        print(f"[t={now:6.3f}s] raw chunk ({len(chunk)} bytes): {chunk!r}")

    await resp.aclose()
    await client.close()

    # --- Assertions /判据 --------------------------------------------------
    full_text = b"".join(raw_chunks).decode()
    events = [json.loads(line[len("data: "):]) for line in full_text.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]

    echo_event = events[0]
    assert echo_event["type"] == "echo", f"first event should be the header/body echo, got {echo_event}"
    got_headers = {k.lower(): v for k, v in echo_event["headers"].items()}
    print("\n--- Server-observed headers ---")
    for k, v in got_headers.items():
        print(f"  {k}: {v}")
    got_body = echo_event["body"]
    print("\n--- Server-observed body ---")
    print(json.dumps(got_body, indent=2))

    for k, v in extra_headers.items():
        assert got_headers.get(k.lower()) == v, f"header {k} did not survive: expected {v}, got {got_headers.get(k.lower())}"
    assert got_body.get("x_client_extra_field") == {"foo": "bar"}, "extra body field did not survive"

    # Non-buffering check: consecutive chunk arrival times should be spread out
    # by roughly CHUNK_DELAY_SECONDS (0.4s in mock_server.py), not all clustered
    # at the end.
    deltas = [b - a for a, b in zip(chunk_times, chunk_times[1:])]
    print("\n--- Inter-chunk deltas (s) ---")
    print(deltas)
    assert len(deltas) >= 3, "expected multiple chunks"
    # deltas[0] is echo->chunk0, then chunk_i->chunk_{i+1} are ~CHUNK_DELAY_SECONDS apart.
    # The very last delta (last content chunk -> "[DONE]") is intentionally ~0 in the mock
    # server (no artificial delay before the terminator), so exclude it from the spread check.
    spread_deltas = deltas[:-1]
    assert all(d > 0.2 for d in spread_deltas), (
        "chunks arrived back-to-back instead of spread out -- SDK is buffering the whole body "
        f"before we see anything! deltas={deltas}"
    )

    print("\nALL ASSERTIONS PASSED: raw SSE bytes passthrough via client.post(cast_to=httpx.Response, stream=True) works, "
          "custom headers + extra body fields survive, chunks are delivered incrementally (no buffering).")


if __name__ == "__main__":
    asyncio.run(main())
