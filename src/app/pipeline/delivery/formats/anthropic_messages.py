"""The Anthropic Messages wire format: reading one, and writing one.

Both directions for this format live together, because they are two halves of the same contract and drifting apart is what they do when they are apart. The generic contracts they satisfy are `BlockAssembler` in `assembling` and `OutboundFramer` in `framing`; `openai_responses` beside this file is the same pair for the other format.

SSE is the envelope the client expects, not a delivery semantic. Every frame describes a block that is already whole; nothing is written while one is forming.
The frame sequence per block is start, one delta carrying the finished content, then stop. The delta exists because the wire format has one, not because content arrives in pieces.
"""

from collections.abc import Iterable, Iterator
from typing import Any, cast

import orjson

from app.config.schema import ContentBlockStartCompat
from app.pipeline.delivery.assembling import (
    Draft,
    ReplyDialect,
    Terminal,
    decode_json,
)
from app.pipeline.delivery.blocks import TEXT, THINKING, TOOL_USE, CompletedBlock
from app.pipeline.delivery.sse_frame import SseFrame
from app.pipeline.delivery.sse_source import SseEvent


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

    Mutually exclusive with `terminal_frames`: `.dev/docs/anthropic-responses-bridge/spec.md`, "Downstream Anthropic SSE" item 5, rules that a terminal error past committed headers uses this event 且不得再发 `message_stop` 冒充成功. Nothing here enforces that — the caller picks one.
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


class AnthropicFramer:
    """The `OutboundFramer` for a client that asked in Anthropic Messages.

    A wrapper over the functions above, which stay exactly as they are: this leg needs no state, and holding what it is given at construction only spares three parameters a trip through four call frames.

    The default leg. Anything that is not a Responses client is framed by this one, which is what keeps a translated route — Anthropic in, Responses upstream — answering in the protocol it was asked in.
    """

    __slots__ = ("_message_id", "_model", "_signature_compat")

    def __init__(
        self,
        *,
        message_id: str,
        model: str,
        signature_compat: ContentBlockStartCompat = "signature_delta",
    ) -> None:
        self._message_id = message_id
        self._model = model
        # Annotated because `__slots__` leaves the attribute's type to be inferred from this assignment, and `Literal[False, …]` widens to `bool | str` on the way in.
        self._signature_compat: ContentBlockStartCompat = signature_compat

    def preamble(self) -> tuple[bytes, ...]:
        return (message_start(self._message_id, self._model).encode(),)

    def block(self, block: CompletedBlock) -> tuple[bytes, ...]:
        return tuple(
            frame.encode() for frame in block_frames(block, signature_compat=self._signature_compat)
        )

    def terminal(self, terminal: Terminal) -> tuple[bytes, ...]:
        """Close the message.

        `or "end_turn"` is a synthesis and stays visible rather than being written into the record: it only ever runs on a stream that did see a terminal event, so it fills in a field upstream left empty rather than inventing an ending upstream never reached.
        An explicit empty `stop_reason` gets it too, because `""` is not a stop reason any Anthropic consumer accepts.
        """
        return tuple(
            frame.encode()
            for frame in terminal_frames(
                stop_reason=terminal.stop_reason or "end_turn",
                usage=terminal.usage or None,
            )
        )

    def error(self, *, error_type: str, message: str, code: str | None = None) -> bytes:
        return error_frame(error_type=error_type, message=message, code=code).encode()

    def keepalive(self) -> bytes:
        return b": ping\n\n"


class AnthropicAssembler:
    """Assembles blocks from an Anthropic SSE stream."""

    def __init__(self) -> None:
        self._drafts: dict[int, Draft] = {}
        self._terminal = Terminal()

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        data = event.json()
        kind = event.event or str(data.get("type", ""))

        if kind == "content_block_start":
            self._open(data)
            return ()
        if kind == "content_block_delta":
            self._accumulate(data)
            return ()
        if kind == "content_block_stop":
            return self._close(data)
        if kind == "message_delta":
            self._read_terminal(data)
            return ()
        if kind == "message_stop":
            self._terminal.seen = True
            return ()
        return ()

    def _open(self, data: dict[str, Any]) -> None:
        index = int(data.get("index", len(self._drafts)))
        raw = data.get("content_block")
        block = dict[str, Any](cast(dict[str, Any], raw)) if isinstance(raw, dict) else {}
        self._drafts[index] = Draft(
            index=index,
            kind=str(block.get("type", "")),
            payload=block,
        )

    def _accumulate(self, data: dict[str, Any]) -> None:
        index = int(data.get("index", -1))
        draft = self._drafts.get(index)
        if draft is None:
            return
        raw = data.get("delta")
        delta = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        delta_type = str(delta.get("type", ""))
        if delta_type == "text_delta":
            draft.text += str(delta.get(TEXT, ""))
        elif delta_type == "thinking_delta":
            draft.text += str(delta.get(THINKING, ""))
        elif delta_type == "input_json_delta":
            draft.partial_json += str(delta.get("partial_json", ""))
        elif delta_type == "signature_delta":
            draft.payload["signature"] = str(delta.get("signature", ""))

    def _close(self, data: dict[str, Any]) -> tuple[CompletedBlock, ...]:
        index = int(data.get("index", -1))
        draft = self._drafts.pop(index, None)
        if draft is None:
            return ()
        payload = dict(draft.payload)
        if draft.kind == TEXT:
            payload[TEXT] = draft.text
        elif draft.kind == THINKING:
            payload[THINKING] = draft.text
        elif draft.kind == TOOL_USE and draft.partial_json:
            payload["input"] = decode_json(draft.partial_json)
        block = CompletedBlock(index=draft.index, kind=draft.kind, payload=payload)
        self._terminal.record(block)
        return (block,)

    def _read_terminal(self, data: dict[str, Any]) -> None:
        raw = data.get("delta")
        delta = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        reason = delta.get("stop_reason")
        if isinstance(reason, str):
            self._terminal.stop_reason = reason
        usage = data.get("usage")
        if isinstance(usage, dict):
            self._terminal.usage = dict[str, Any](cast(dict[str, Any], usage))


def terminal_from_anthropic(
    body: dict[str, Any], blocks: Iterable[CompletedBlock], *, dialect: ReplyDialect = ReplyDialect.ANTHROPIC
) -> Terminal:
    """The same summary, for a reply that arrived whole instead of in events.

    A buffered request never runs an assembler, so without this the facts a finished reply carries — which tools were asked for, how much reasoning came back, what it cost — had to be dug back out of the response payload at whatever place happened to want them. That is how the same reply came to be described by two different pieces of code, and why only one of them was ever fixed when the description was wrong.

    Reads an **Anthropic-shaped** body. It has no way to notice one that is not, so a caller holding some other shape must not reach for this — `handler.reply_summary` is where that decision is made.

    `seen` is true by construction: a body read whole is a reply that finished, which is exactly what the flag means on the streaming side.

    The stop reason starts empty rather than at the class default. A stream that never sent its terminal event still has a reason to be called `end_turn` by the code that synthesises one; a body simply not carrying the field means nobody said, and printing `end_turn` there would claim a clean finish on no evidence at all.
    """
    terminal = Terminal(seen=True, dialect=dialect, stop_reason="")
    stop_reason = body.get("stop_reason")
    if isinstance(stop_reason, str) and stop_reason:
        terminal.stop_reason = stop_reason
    usage = body.get("usage")
    if isinstance(usage, dict):
        terminal.usage = dict[str, Any](cast(dict[str, Any], usage))
    for block in blocks:
        terminal.record(block)
    return terminal
