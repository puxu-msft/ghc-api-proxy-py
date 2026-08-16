"""Rendering completed blocks as Anthropic SSE frames.

SSE is the envelope the client expects, not a delivery semantic.
Every frame describes a block that is already whole; nothing is written while one is forming.

The frame sequence per block is start, one delta carrying the finished content, then stop.
The delta exists because the wire format has one, not because content arrives in pieces.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import orjson

from app.pipeline.delivery.blocks import CompletedBlock


@dataclass(frozen=True, slots=True)
class SseFrame:
    event: str
    data: dict[str, Any]

    def encode(self) -> bytes:
        body = orjson.dumps(self.data).decode()
        return f"event: {self.event}\ndata: {body}\n\n".encode()


def message_start(message_id: str, model: str) -> SseFrame:
    return SseFrame(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )


def _delta_for(block: CompletedBlock) -> dict[str, Any] | None:
    """The delta payload carrying a finished block's content.

    Returns None for kinds whose content already rode in content_block_start.
    """
    if block.kind == "text":
        return {"type": "text_delta", "text": str(block.payload.get("text", ""))}
    if block.kind == "thinking":
        return {"type": "thinking_delta", "thinking": str(block.payload.get("thinking", ""))}
    if block.kind == "tool_use":
        raw = block.payload.get("input", {})
        return {"type": "input_json_delta", "partial_json": orjson.dumps(raw).decode()}
    return None


def block_frames(block: CompletedBlock) -> tuple[SseFrame, ...]:
    """Frame one already-complete block.

    Emitted as a closed group: start, the content, stop.
    A caller cannot obtain a partial group, which keeps a half-formed block off the wire.
    """
    start_payload = dict(block.payload)
    if block.kind == "tool_use":
        # The arguments ride in the delta, so the start frame carries an empty input.
        start_payload["input"] = {}
    elif block.kind == "text":
        start_payload["text"] = ""
    elif block.kind == "thinking":
        start_payload["thinking"] = ""

    frames = [
        SseFrame(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": block.index,
                "content_block": start_payload,
            },
        )
    ]
    delta = _delta_for(block)
    if delta is not None:
        frames.append(
            SseFrame(
                "content_block_delta",
                {"type": "content_block_delta", "index": block.index, "delta": delta},
            )
        )
    frames.append(
        SseFrame("content_block_stop", {"type": "content_block_stop", "index": block.index})
    )
    return tuple(frames)


def terminal_frames(
    *,
    stop_reason: str,
    usage: dict[str, Any] | None = None,
) -> tuple[SseFrame, ...]:
    """Close the message. Only valid after every block has been framed."""
    return (
        SseFrame(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": usage or {"output_tokens": 0},
            },
        ),
        SseFrame("message_stop", {"type": "message_stop"}),
    )


def render(
    blocks: Iterable[CompletedBlock],
    *,
    message_id: str,
    model: str,
    stop_reason: str = "end_turn",
    usage: dict[str, Any] | None = None,
) -> Iterator[bytes]:
    """Render a whole message from blocks that are all already complete.

    message_start comes first, but only once there is at least one block.
    An empty or failed response never produces a preamble the client would read as started.
    """
    materialised = list(blocks)
    if not materialised:
        return
    yield message_start(message_id, model).encode()
    for block in materialised:
        for frame in block_frames(block):
            yield frame.encode()
    for frame in terminal_frames(stop_reason=stop_reason, usage=usage):
        yield frame.encode()
