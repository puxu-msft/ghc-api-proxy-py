"""What every assembler is, and what every assembler produces.

The generic half of reading an upstream. A `BlockAssembler` turns one upstream's events into `CompletedBlock`s; which upstream that is lives in `formats`, one module per wire format, and nothing here knows how many there are.

Its mirror on the way out is `framing`. The two are separate questions and a route answers them differently: a request that arrives as Anthropic Messages and is served by a Responses upstream is assembled by the Responses assembler and framed by the Anthropic framer.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

import orjson

from app.pipeline.delivery.blocks import THINKING, TOOL_USE, CompletedBlock
from app.pipeline.delivery.sse_source import SseEvent


class ReplyDialect(StrEnum):
    """Whose vocabulary the reply arrived in.

    Not `WireFormat`. That enum is the whole taxonomy of body shapes a route can take, and it lives with `RequestContext`, which now holds one of these records — importing it here would close a cycle. What a summary of a reply needs is narrower anyway: only which of the two upstreams described it, so the words on the console line can be that upstream's own. A reply is assembled by exactly one of them, so this is a property of the record rather than something a reader has to be told separately.
    """

    ANTHROPIC = "anthropic"
    RESPONSES = "responses"


@dataclass(slots=True)
class Terminal:
    """What the upstream said when it finished."""

    # Empty until an upstream says otherwise, so the field cannot be read as a claim nobody made. It used to default to `end_turn`, which made "upstream said the turn ended cleanly" and "upstream never said anything" the same value — and the console line, which prints this, could not tell them apart either. Whoever has to put a reason on the wire for a stream that ended without one synthesises it there, where the synthesis is visible; see `stream_delivery`.
    stop_reason: str = ""
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    # Whether the upstream's own terminal event arrived — `message_stop` here, `response.completed` / `response.incomplete` on the Responses side. False means the stream stopped mid-turn, and everything this record does *not* carry is unknown rather than absent.
    seen: bool = False
    # Which upstream described this reply, and so which words the console line should use for it. Anthropic by default because that is also the shape a translated reply is read back in.
    dialect: ReplyDialect = ReplyDialect.ANTHROPIC
    # Every complete content block received before the terminal event, or before the upstream stopped. A count here remains truthful for a truncated turn because only `record()` advances it.
    blocks: int = 0
    # Every tool the model asked for, in the order it asked, duplicates kept. `tool_use` on its own says a turn ended in tool calls; which tools, and how many of each, is the part that tells one turn from another when reading a log.
    tools: list[str] = field(default_factory=lambda: list[str]())
    # Thinking blocks by kind: `txt` carried readable reasoning, `enc` carried only an opaque signature. The distinction is the interesting one — a turn that reasoned and a turn that was handed back sealed reasoning cost the same tokens and look identical from the outside.
    thinking: list[str] = field(default_factory=lambda: list[str]())
    # Upstream's own usage object, kept beside the converted one rather than derived back from it. `usage` above has been through `_anthropic_usage`, which subtracts the cached part of the input and drops `reasoning_tokens` outright — a lossy pass that is right for an Anthropic client and has no inverse. A leg that has to report what upstream actually said needs the original, and reconstructing it would compose two lossy passes into a number neither side ever computed.
    #
    # Empty on every leg but the Responses one, including the buffered path. A reader must treat empty as "not observed" and say nothing, rather than filling in zeros: a usage of zero is a measurement, and this is the absence of one.
    upstream_usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())

    def record(self, block: CompletedBlock) -> None:
        """Take one finished block into the running summary of the reply.

        Classification lives here, on the record itself, rather than at each place a block becomes final. There are three such places — the two assemblers and a buffered reply read back whole — and when each did its own classifying, the same question ("was this reasoning readable?") was answered by three separate expressions that were free to drift apart. Reading the block's own payload, rather than whatever local draft produced it, is what lets one implementation serve all three.
        """
        self.blocks += 1
        if block.kind == TOOL_USE:
            self.tools.append(str(block.payload.get("name", "")))
        elif block.kind == THINKING:
            self.thinking.append("txt" if block.payload.get(THINKING) else "enc")


class BlockAssembler(Protocol):
    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        """Take one event; return blocks that just became complete."""
        ...

    @property
    def terminal(self) -> Terminal: ...


@dataclass(slots=True)
class Draft:
    """One block being accumulated, before its closing event arrives.

    Public rather than private because both formats' assemblers build one, and one of them passes it to a helper of its own. A second copy per format would be two places for the same shape to drift.
    """

    index: int
    kind: str
    payload: dict[str, Any]
    text: str = ""
    partial_json: str = ""


def decode_json(raw: str) -> Any:
    """A tool call's accumulated arguments, or a marker holding the text that would not parse.

    Shared by both assemblers, which is why it is not private. `{"__raw": …}` is the marker; whatever reads a block back out has to know about it, and `openai_responses`'s framer does.
    """
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        # Keep the text rather than dropping it; a malformed argument is still evidence.
        return {"__raw": raw}
