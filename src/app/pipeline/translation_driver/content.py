"""The typed content model the translators meet at.

`D-ARCH = B`, accepted 2026-08-19: typed facts are the internal truth, and a wire `dict` exists only at the codec boundary. Message content used to be the hole in that — `SemanticRequest.messages` carried Anthropic-shaped dicts verbatim, so a real conversation crossing to Responses arrived with
Anthropic's `{"type": "text"}` and upstream answered `Invalid value: 'text'. Supported values are: 'input_text', ...`.

Three properties are load-bearing, and each is here because dropping it loses something no later stage can recover.

Order and message boundaries survive. A reader emits one `SemanticMessage` per inbound message and one block per content block, in order, because a tool result must still follow the call it answers.

An unrecognised block becomes `UNKNOWN` carrying its original, rather than disappearing. A format gains block types faster than a translator learns them, and a silently dropped block is a conversation with a hole in it.

Opaque reasoning state is labelled with whose it is. A signature the proxy issued can be decoded back to the `encrypted_content` inside it; a signature Anthropic issued cannot, and must never be forged into one. `ReasoningState.portable_to` is where that refusal lives.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class BlockKind(StrEnum):
    """What a content block is, independent of either wire format's spelling."""

    TEXT = "text"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    IMAGE = "image"
    UNKNOWN = "unknown"


class OpaqueFormat(StrEnum):
    """Whose opaque reasoning state this is.

    The distinction is not cosmetic: `CLAUDE_SIGNATURE` is a value only Anthropic can produce, while `RESPONSES_ENCRYPTED` is one only the Responses endpoint can. A proxy-issued carrier holds the latter inside the former's slot, which is why it can cross and a native signature cannot.
    """

    CLAUDE_SIGNATURE = "claude-signature"
    RESPONSES_ENCRYPTED = "responses-encrypted"
    PROXY_CARRIER = "proxy-carrier"


@dataclass(frozen=True, slots=True)
class ReasoningState:
    """One provider-issued continuation value.

    Presence is represented by the object itself, so an empty string stays distinct from an absent field. A value only travels natively to the format that issued it; the bridge codec is what lets a client carry it through another format without presenting it to that format's upstream.
    """

    format: OpaqueFormat
    value: str = ""

    def portable_to(self, target: OpaqueFormat) -> bool:
        """Whether this exact value belongs in `target`'s native opaque slot."""
        return self.format is target


@dataclass(frozen=True, slots=True)
class ReasoningSummaryPart:
    """One Responses `summary_text` part, including fields this reader does not consume."""

    text: str
    extensions: Mapping[str, Any] = field(default_factory=lambda: dict[str, Any]())

    def to_wire(self) -> dict[str, Any]:
        return {"type": "summary_text", "text": self.text, **dict(self.extensions)}


@dataclass(frozen=True, slots=True)
class ReasoningContent:
    """One reasoning item's visible projection, structure, and provider-native state."""

    visible_text: str
    source_format: str
    summary_parts: tuple[ReasoningSummaryPart, ...] | None = None
    state: ReasoningState | None = None
    redacted: bool = False

    def responses_summary(self) -> list[dict[str, Any]]:
        if self.summary_parts is not None:
            return [part.to_wire() for part in self.summary_parts]
        if not self.visible_text:
            return []
        return [{"type": "summary_text", "text": self.visible_text}]


@dataclass(frozen=True, slots=True)
class ContentBlock:
    """One block of message content.

    Fields are per-kind rather than a union because every reader and writer needs to look at the same names; a tagged union of six shapes would move the branching into every call site.
    """

    kind: BlockKind
    text: str = ""

    # Correlates a call with its result. Both formats have this; only the field name differs.
    call_id: str = ""
    name: str = ""
    arguments: Any = None
    output: Any = None
    is_error: bool = False

    reasoning: ReasoningContent | None = None

    # The block exactly as it arrived. The only content an `UNKNOWN` block has, and what lets a same-format crossing return what it was given rather than what the model could express.
    raw: Mapping[str, Any] = field(default_factory=lambda: dict[str, Any]())


@dataclass(frozen=True, slots=True)
class SemanticMessage:
    """One turn, with its blocks in the order they arrived."""

    role: str
    blocks: tuple[ContentBlock, ...] = ()
