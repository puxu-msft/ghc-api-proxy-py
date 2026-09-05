"""Block-level delivery to the client.

The package is split along two axes, and keeping them apart is the point:

- **Generic**, naming no wire format — `blocks` (what a block is and how many are held), `sse_frame` and `sse_source` (the wire envelope, written and read), `assembling` and `framing` (the two contracts), `stream` (the delivery loop).
- **Format-specific**, under `formats`, named for the wire format they speak *and for what they make of it*. Each format's assembler and its framer live together — `anthropic_messages` and `openai_responses` are peers and neither imports from the other. Anything else specific to one format carries that format's name and says what it produces, which is why `anthropic_messages_synthetic_reply` is spelled out in full: the package manufactures several different things at different scales, and a file called `synthetic` would only have said that it manufactures.

The split used to be blurred in both directions — the generic `SseFrame` lived inside the Anthropic module, which made the Responses framer import from it; the generically-named `assembler` held both formats' implementations; and the generically-named `synthetic` wrote Anthropic and nothing else. Restructured 2026-08-22.
"""

from app.pipeline.delivery.assembling import (
    BlockAssembler,
    ReplyDialect,
    Terminal,
)
from app.pipeline.delivery.blocks import (
    SERVER_TOOL_USE,
    TEXT,
    THINKING,
    TOOL_USE,
    WEB_SEARCH_TOOL_RESULT,
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
    "SERVER_TOOL_USE",
    "TEXT",
    "THINKING",
    "TOOL_USE",
    "WEB_SEARCH_TOOL_RESULT",
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
