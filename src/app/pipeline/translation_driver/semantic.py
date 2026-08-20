"""The intermediate representation translators meet at.

MAIN.md routes translation through "inbound format <-> intermediate <-> upstream format".
No translator pair needs to know about any other.
Adding a format means writing its two translators, not touching the ones already there.

The representation is deliberately lossy-aware rather than lossless.
The spec does not require capability parity, so what a translator cannot express is recorded.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.pipeline.translation_driver.content import SemanticMessage


@dataclass(frozen=True, slots=True)
class SystemBlock:
    """One system-prompt segment.

    Kept as a list of blocks because both sides carry per-block metadata such as cache_control.
    Flattening to a string here would throw that away before either translator sees it.
    """

    text: str
    metadata: Mapping[str, Any] = field(default_factory=lambda: dict[str, Any]())


class LossCode(StrEnum):
    """Why something did not cross, as a value rather than a sentence.

    Codes rather than prose because the reason is read by other code — a metric, a receipt, a
    future degradation policy — and matching on English is how those quietly stop matching. The
    detail string stays for a human reading a log; the code is what anything else keys on.
    """

    EXTENSIONS_NOT_CARRIED = "extensions-not-carried"
    SYSTEM_METADATA_NOT_CARRIED = "system-metadata-not-carried"
    SYSTEM_FIELD_MALFORMED = "system-field-malformed"
    BLOCK_NOT_CARRIED = "block-not-carried"
    ITEM_NOT_CARRIED = "item-not-carried"
    REASONING_STATE_NOT_PORTABLE = "reasoning-state-not-portable"
    INSTRUCTIONS_ROLE_NOT_CARRIED = "instructions-role-not-carried"
    TOOL_RESULT_CONTENT_FLATTENED = "tool-result-content-flattened"
    SERVER_TOOL_NOT_CARRIED = "server-tool-not-carried"
    SERVER_TOOL_CONSTRAINT_DROPPED = "server-tool-constraint-dropped"


@dataclass(frozen=True, slots=True)
class Loss:
    """One thing a translation could not carry."""

    code: LossCode
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.code.value}: {self.detail}" if self.detail else self.code.value


@dataclass(slots=True)
class Conversion:
    """What a translation could not carry over.

    A named loss is the difference between a degraded response and a silent one.
    """

    losses: list[Loss] = field(default_factory=lambda: list[Loss]())

    def record(self, code: LossCode, detail: str = "") -> None:
        self.losses.append(Loss(code, detail))

    def has(self, code: LossCode) -> bool:
        return any(loss.code is code for loss in self.losses)

    @property
    def lossless(self) -> bool:
        return not self.losses


@dataclass(slots=True)
class SemanticRequest:
    """The intermediate form of an inbound model request."""

    model: str
    system: list[SystemBlock] = field(default_factory=lambda: list[SystemBlock]())
    messages: list[SemanticMessage] = field(default_factory=lambda: list[SemanticMessage]())
    tools: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    stream: bool = False
    max_output_tokens: int | None = None
    temperature: float | None = None
    # Which wire format the extensions below came off. A writer for a different format must not
    # replay them: an unclaimed key is unclaimed *in its own format*, and in another one it is at
    # best meaningless. Measured — sending Anthropic's `context_management` to the Responses
    # endpoint gets `failed to parse request`, so replaying it is not merely untidy.
    source_format: str = ""
    # Fields no translator claimed, kept so an unknown key is not silently dropped.
    extensions: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    conversion: Conversion = field(default_factory=Conversion)

    def extensions_for(self, wire_format: str) -> dict[str, Any]:
        """The extensions a writer for `wire_format` may replay — all of them or none.

        Records the drop rather than performing it silently, which is what `Conversion` is for.
        """
        if not self.extensions or self.source_format == wire_format:
            return dict(self.extensions)
        self.conversion.record(
            LossCode.EXTENSIONS_NOT_CARRIED,
            f"from {self.source_format or 'an unnamed format'} into {wire_format}: "
            f"{', '.join(sorted(self.extensions))}",
        )
        return {}


def system_blocks_from_value(value: object) -> tuple[list[SystemBlock], LossCode | None]:
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
                return [], LossCode.SYSTEM_FIELD_MALFORMED
            block = dict[str, Any](entry)  # pyright: ignore[reportUnknownArgumentType]
            text = block.pop("text", "")
            block.pop("type", None)
            if not isinstance(text, str):
                return [], LossCode.SYSTEM_FIELD_MALFORMED
            blocks.append(SystemBlock(text=text, metadata=block))
        return blocks, None
    return [], LossCode.SYSTEM_FIELD_MALFORMED
