from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx2
import orjson

ROOT = Path(__file__).resolve().parent
assert (ROOT / ".review-commit").read_text().strip() == "a7a0e058fc1940c188626e8d3f4aa38e0393ea9c"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "int"))

from app.model_provider.ghc_client.errors import normalize_upstream_error
from app.pipeline.delivery.blocks import DeliveryError
from app.pipeline.delivery.stream import UpstreamStreamUnterminated
from app.pipeline.hand_over import replay_reason
from test_pipeline_app import TOOL_NAME, _delivered, _handed_back, make_client, truncated_sse_upstream


def frame(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n".encode()


def anthropic_severed_after_one_whole_block() -> bytes:
    return b"".join(
        [
            frame("content_block_start", {"index": 0, "content_block": {"type": "text"}}),
            frame("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "kept"}}),
            frame("content_block_stop", {"index": 0}),
            frame("content_block_start", {"index": 1, "content_block": {"type": "text"}}),
            frame("content_block_delta", {"index": 1, "delta": {"type": "text_delta", "text": "cut"}}),
        ]
    )


def anthropic_severed_before_any_whole_block() -> bytes:
    return b"".join(
        [
            frame("content_block_start", {"index": 0, "content_block": {"type": "text"}}),
            frame("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "cut"}}),
        ]
    )


def responses_severed_after_one_whole_item() -> bytes:
    first_open = {
        "output_index": 0,
        "item": {"type": "message", "id": "msg_0", "role": "assistant", "status": "in_progress", "content": []},
    }
    first_done = {
        "output_index": 0,
        "item": {"type": "message", "id": "msg_0_done", "role": "assistant", "status": "completed", "content": []},
    }
    second_open = {
        "output_index": 1,
        "item": {"type": "message", "id": "msg_1", "role": "assistant", "status": "in_progress", "content": []},
    }
    return b"".join(
        [
            frame("response.output_item.added", first_open),
            frame("response.output_text.delta", {"output_index": 0, "item_id": "msg_0", "delta": "kept"}),
            frame("response.output_item.done", first_done),
            frame("response.output_item.added", second_open),
            frame("response.output_text.delta", {"output_index": 1, "item_id": "msg_1", "delta": "cut"}),
        ]
    )


def client_for(body: bytes, *, overrides: dict[str, Any] | None = None):
    return make_client(
        lambda _: httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"}),
        overrides=overrides,
    )[0]


error = UpstreamStreamUnterminated("upstream stream ended without a terminal event")
assert normalize_upstream_error(error) is None
assert replay_reason(error) is None
assert not isinstance(error, DeliveryError)
print("classification: normalize=None replay_reason=None delivery_error=False")

client = client_for(anthropic_severed_after_one_whole_block())
try:
    delivered = _delivered(client)
finally:
    client.close()
handed = _handed_back(delivered)
assert handed["name"] == TOOL_NAME
assert handed["input"]["category"] == "upstream"
assert "UpstreamStreamUnterminated" in handed["input"]["message"]
assert b"incomplete_responses_stream" not in delivered
assert b'"text":"kept"' in delivered and b'"text":"cut"' not in delivered
print("anthropic-upstream severed: handed category=upstream; kept whole block; dropped draft")

client = client_for(truncated_sse_upstream("kept"))
try:
    boundary_default = _delivered(client)
finally:
    client.close()
assert b"turn_interrupted" not in boundary_default
assert b'"stop_reason":"incomplete"' in boundary_default
assert b"incomplete_responses_stream" not in boundary_default
print("boundary/default: synthesized stop_reason=incomplete; no handover")

client = client_for(
    truncated_sse_upstream("kept"),
    overrides={"client_delivery": {"unterminated_stream_stop_reason": ""}},
)
try:
    boundary_empty = _delivered(client)
finally:
    client.close()
handed = _handed_back(boundary_empty)
assert handed["input"]["category"] == "upstream"
assert "UpstreamStreamUnterminated" in handed["input"]["message"]
assert b"incomplete_responses_stream" not in boundary_empty
print("boundary/empty stop reason: handover replaces would-be SSE error")

client = client_for(anthropic_severed_before_any_whole_block())
try:
    no_committed = _delivered(client)
finally:
    client.close()
assert no_committed == b""
print("zero committed blocks: empty downstream body; no handover and no SSE error")

responses_body = responses_severed_after_one_whole_item()
client = client_for(responses_body)
try:
    translated = client.post(
        "/v1/messages",
        json={"model": "gpt-model", "messages": [], "stream": True},
    ).content
finally:
    client.close()
handed = _handed_back(translated)
assert handed["input"]["category"] == "upstream"
assert b'"text":"kept"' in translated and b'"text":"cut"' not in translated
print("Responses upstream -> Anthropic client: handed category=upstream; kept whole item; dropped draft")

client = client_for(responses_body)
try:
    direct = client.post(
        "/responses",
        json={"model": "gpt-model", "input": [], "stream": True},
    ).content
finally:
    client.close()
assert b"turn_interrupted" not in direct
assert b"incomplete_responses_stream" in direct
assert b"response.completed" not in direct
print("Responses client: continuation declined by wire format; Responses error remains")
