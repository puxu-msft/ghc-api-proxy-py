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

from app.config.schema import ContentBlockStartCompat
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


def signature_frame(block: CompletedBlock) -> SseFrame | None:
    """The `signature_delta` a standard client needs to keep a thinking block's signature.

    Upstream puts the signature inside `content_block_start` and never sends a delta for it, and
    Claude Code reads it from the delta — so without this the signature is present on the wire and
    still lost. `hook_fix_anthropic_sse.thinking.content_block_start_compat` names this shim.
    """
    if block.kind != "thinking":
        return None
    signature = block.payload.get("signature")
    if not isinstance(signature, str) or not signature:
        return None
    return SseFrame(
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": block.index,
            "delta": {"type": "signature_delta", "signature": signature},
        },
    )


def block_frames(
    block: CompletedBlock,
    *,
    signature_compat: ContentBlockStartCompat = "signature_delta",
) -> tuple[SseFrame, ...]:
    """Frame one already-complete block.

    Emitted as a closed group: start, the content, stop.
    A caller cannot obtain a partial group, which keeps a half-formed block off the wire.
    """
    if signature_compat == "redacted_thinking":
        # Schema-valid but undefined: `config.example.yaml` documents only what `signature_delta`
        # does. Refused at the point of use rather than quietly served as one of the other two —
        # an operator who asked for a third behaviour should not be given a different one.
        raise ValueError(
            "content_block_start_compat='redacted_thinking' is not implemented; "
            "use 'signature_delta' (default) or false"
        )
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
    if signature_compat == "signature_delta":
        signature = signature_frame(block)
        if signature is not None:
            frames.append(signature)

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


def error_frame(*, error_type: str, message: str, code: str | None = None) -> SseFrame:
    """The one frame that says a started stream is not going to end successfully.

    Its shape is the legacy chain's, byte for byte (`app/delivery/anthropic_sse.py::render_error`), because the wire contract is the same one and two spellings of it would be two things to keep in step. `code` is omitted rather than sent as null when absent, for the same reason.

    Mutually exclusive with `terminal_frames`: the frozen Spec rules that a terminal error past committed headers uses this event 且不得再发 `message_stop` 冒充成功. Nothing here enforces that — the caller picks one.
    """
    detail: dict[str, Any] = {"type": error_type, "message": message}
    if code is not None:
        detail["code"] = code
    return SseFrame("error", {"type": "error", "error": detail})


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
