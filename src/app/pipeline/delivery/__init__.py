"""Block-level delivery to the client.

The package is split along two axes, and keeping them apart is the point:

- **Generic**, naming no wire format — `blocks` (what a block is and how many are held), `sse_frame` and `sse_source` (the wire envelope, written and read), `assembling` and `framing` (the two contracts), `stream` (the delivery loop).
- **Format-specific**, one module per wire format under `formats`, each holding that format's assembler *and* its framer. `anthropic_messages` and `openai_responses` are peers; neither imports from the other.

The split used to be blurred in both directions — the generic `SseFrame` lived inside the Anthropic module, which made the Responses framer import from it; the generically-named `assembler` held both formats' implementations; and the generically-named `synthetic` wrote Anthropic and nothing else. Restructured 2026-08-22.
"""

from app.pipeline.delivery.assembling import (
    BlockAssembler,
    ReplyDialect,
    Terminal,
)
from app.pipeline.delivery.blocks import (
    TEXT,
    THINKING,
    TOOL_USE,
    BlockBuffer,
    BufferCapExceeded,
    CompletedBlock,
    DeliveryError,
    DeliverySession,
    ResponseAlreadyStarted,
)
from app.pipeline.delivery.formats.anthropic_messages import (
    AnthropicAssembler,
    AnthropicFramer,
    block_frames,
    message_start,
    render,
    terminal_frames,
)
from app.pipeline.delivery.formats.openai_responses import (
    ResponsesAssembler,
    ResponsesFramer,
)
from app.pipeline.delivery.framing import OutboundFramer
from app.pipeline.delivery.sse_frame import SseFrame
from app.pipeline.delivery.sse_source import SseEvent, read_events

__all__ = [
    "TEXT",
    "THINKING",
    "TOOL_USE",
    "AnthropicAssembler",
    "AnthropicFramer",
    "BlockAssembler",
    "BlockBuffer",
    "BufferCapExceeded",
    "CompletedBlock",
    "DeliveryError",
    "DeliverySession",
    "OutboundFramer",
    "ReplyDialect",
    "ResponseAlreadyStarted",
    "ResponsesAssembler",
    "ResponsesFramer",
    "SseEvent",
    "SseFrame",
    "Terminal",
    "block_frames",
    "message_start",
    "read_events",
    "render",
    "terminal_frames",
]
