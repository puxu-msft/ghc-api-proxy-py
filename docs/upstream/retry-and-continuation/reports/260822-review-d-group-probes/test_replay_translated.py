"""Independent review probe: does the replay wiring survive the translated (primary) path?

Mirrors `test_a_torn_stream_the_client_never_saw_is_replayed_end_to_end`, but routes to
`gpt-model`, which the catalog only serves on `/responses` — so `translation_required` is True
and `handle` rewrites `context.payload` in place before the first attempt.
"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx2

sys.path.insert(0, str(Path("/home/xp/src/ghc-api-proxy-py/tests/int")))

from test_pipeline_app import make_client  # noqa: E402


def _responses_sse(text: str) -> bytes:
    return (
        b'event: response.created\ndata: {"type":"response.created","response":{"id":"resp_1"}}\n\n'
        b'event: response.output_item.added\ndata: {"type":"response.output_item.added","output_index":0,"item":{"id":"m1","type":"message","role":"assistant","content":[]}}\n\n'
        b'event: response.output_item.done\ndata: {"type":"response.output_item.done","output_index":0,"item":{"id":"m1","type":"message","role":"assistant","content":[{"type":"output_text","text":"'
        + text.encode()
        + b'"}]}}\n\n'
        b'event: response.completed\ndata: {"type":"response.completed","response":{"id":"resp_1","status":"completed","usage":{"input_tokens":1,"output_tokens":1}}}\n\n'
    )


def test_replay_on_the_translated_path() -> None:
    calls: list[bytes] = []

    async def torn_body() -> AsyncIterator[bytes]:
        yield b'event: response.created\ndata: {"type":"response.created","response":{"id":"resp_1"}}\n\n'
        raise httpx2.RemoteProtocolError("peer closed the connection")

    def upstream(request: httpx2.Request) -> httpx2.Response:
        calls.append(request.content)
        if len(calls) == 1:
            return httpx2.Response(
                200, content=torn_body(), headers={"content-type": "text/event-stream"}
            )
        return httpx2.Response(
            200, content=_responses_sse("kept"), headers={"content-type": "text/event-stream"}
        )

    client, _ = make_client(upstream)
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )

    print("STATUS", response.status_code)
    print("BODY", response.text[:2000])
    for index, sent in enumerate(calls):
        print(f"--- upstream call {index + 1} body ---")
        print(sent.decode()[:2000])
    assert len(calls) == 2, "upstream should have been asked twice"
    assert calls[0] == calls[1], "the replayed attempt must send the same body as the first"
