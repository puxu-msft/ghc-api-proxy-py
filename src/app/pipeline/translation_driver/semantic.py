"""The intermediate representation translators meet at.

MAIN.md routes translation through "inbound format <-> intermediate <-> upstream format".
No translator pair needs to know about any other.
Adding a format means writing its two translators, not touching the ones already there.

The representation is deliberately lossy-aware rather than lossless.
The spec does not require capability parity, so what a translator cannot express is recorded.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SystemBlock:
    """One system-prompt segment.

    Kept as a list of blocks because both sides carry per-block metadata such as cache_control.
    Flattening to a string here would throw that away before either translator sees it.
    """

    text: str
    metadata: Mapping[str, Any] = field(default_factory=lambda: dict[str, Any]())


@dataclass(slots=True)
class Conversion:
    """What a translation could not carry over.

    A named loss is the difference between a degraded response and a silent one.
    """

    losses: list[str] = field(default_factory=lambda: list[str]())

    def record(self, detail: str) -> None:
        self.losses.append(detail)

    @property
    def lossless(self) -> bool:
        return not self.losses


@dataclass(slots=True)
class SemanticRequest:
    """The intermediate form of an inbound model request."""

    model: str
    system: list[SystemBlock] = field(default_factory=lambda: list[SystemBlock]())
    messages: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    tools: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    stream: bool = False
    max_output_tokens: int | None = None
    temperature: float | None = None
    # Fields no translator claimed, kept so an unknown key is not silently dropped.
    extensions: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    conversion: Conversion = field(default_factory=Conversion)


def system_blocks_from_value(value: object) -> tuple[list[SystemBlock], str | None]:
    """Read a system field that may be a string or a list of blocks.

    Anthropic allows both spellings, so accepting only one would reject valid inbound requests.
    """
    if value is None:
        return [], None
    if isinstance(value, str):
        return ([SystemBlock(text=value)] if value else []), None
    if isinstance(value, Sequence):
        blocks: list[SystemBlock] = []
        for entry in value:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(entry, str):
                blocks.append(SystemBlock(text=entry))
                continue
            if not isinstance(entry, Mapping):
                return [], "system entry is neither text nor a block"
            block = dict[str, Any](entry)  # pyright: ignore[reportUnknownArgumentType]
            text = block.pop("text", "")
            block.pop("type", None)
            if not isinstance(text, str):
                return [], "system block text is not a string"
            blocks.append(SystemBlock(text=text, metadata=block))
        return blocks, None
    return [], "system field is neither a string nor a list"
