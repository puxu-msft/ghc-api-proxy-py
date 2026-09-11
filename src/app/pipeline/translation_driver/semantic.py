"""The intermediate representation translators meet at.

`docs/.human-controlled/message-translation.md` routes translation through "wire format <-> semantic IR <-> wire format".
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
from app.pipeline.translation_driver.reasoning import ThinkingEffortIntent, ThinkingTargetProfile
from app.pipeline.translation_driver.tool_choice import ToolChoiceIntent


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

    Codes rather than prose because the reason is read by other code — a metric, a receipt, a future degradation policy — and matching on English is how those quietly stop matching. The detail string stays for a human reading a log; the code is what anything else keys on.
    """

    UNKNOWN_FIELDS_NOT_CARRIED = "extensions-not-carried"
    EXTENSIONS_NOT_CARRIED = "extensions-not-carried"
    SYSTEM_METADATA_NOT_CARRIED = "system-metadata-not-carried"
    SYSTEM_FIELD_MALFORMED = "system-field-malformed"
    BLOCK_NOT_CARRIED = "block-not-carried"
    ITEM_NOT_CARRIED = "item-not-carried"
    REASONING_STATE_NOT_PORTABLE = "reasoning-state-not-portable"
    INSTRUCTIONS_ROLE_NOT_CARRIED = "instructions-role-not-carried"
    TOOL_RESULT_CONTENT_FLATTENED = "tool-result-content-flattened"
    # Responses has no tool-result error flag; the failure is represented by a text prefix.
    TOOL_RESULT_ERROR_MARKED = "tool-result-error-marked"
    SERVER_TOOL_NOT_CARRIED = "server-tool-not-carried"
    SERVER_TOOL_CALL_ID_NOT_CARRIED = "server-tool-call-id-not-carried"
    SERVER_TOOL_PARTIALLY_REPRESENTABLE = "server-tool-partially-representable"
    SERVER_TOOL_CONSTRAINT_DROPPED = "server-tool-constraint-dropped"
    REASONING_INTENT_APPROXIMATED = "reasoning-intent-approximated"
    REASONING_INTENT_NOT_CARRIED = "reasoning-intent-not-carried"
    TOOL_DESCRIPTION_COERCED = "tool-description-coerced"
    # A `cache_control` key upstream does not accept, removed so the rest of the request can be sent. Its own member rather than `EXTENSIONS_NOT_CARRIED` because what was lost is specific and consequential: `scope` decides how widely a cached prefix is shared, so dropping it changes what the cache does rather than dropping decoration. Spec §7.1.
    CACHE_CONTROL_FIELD_NOT_CARRIED = "cache-control-field-not-carried"
    # This proxy put something in the body that the client did not write. An addition needs a record just as a dropped field does.
    SYNTHETIC_TURN_ADDED = "synthetic-turn-added"
    # Upstream answered with an error this proxy could not read as one. Recorded rather than silently dropped, because it is what decides whether the client is handed upstream's original alongside our envelope — spec §10.1.
    UPSTREAM_ERROR_NOT_INTERPRETED = "upstream-error-not-interpreted"
    OPAQUE_RESPONSE_SKIPPED = "opaque-response-skipped"


class ConversionFactCode(StrEnum):
    THINKING_PROFILE_SELECTED = "thinking-profile-selected"
    THINKING_PROFILE_REJECTED = "thinking-profile-rejected"


@dataclass(frozen=True, slots=True)
class ConversionFact:
    code: ConversionFactCode
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ConversionWarning:
    """A structured, source-scoped diagnostic for best-effort projection."""

    code: str
    source_format: str
    field_path: str
    detail: str = ""


class TranslationRefused(Exception):
    """The request says something this crossing cannot carry without changing what it means.

    Distinct from a `Loss`, and the distinction is the point. A loss is something the client can be told about afterwards because the request still means what it meant — a dropped cache marker, a cost ceiling nobody can enforce. This is for the other kind: a field whose removal would silently reverse an instruction, where carrying on is worse than refusing.

    Carries a `code` and the `field_path` that caused it so the client is told which part of its request is the problem, rather than being handed a generic refusal it cannot act on. `facts` is the immutable snapshot of non-loss conversion observations available at the point of rejection.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        field_path: str,
        facts: tuple[ConversionFact, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field_path = field_path
        self.facts = facts


class ToolChoiceNotSupported(TranslationRefused):
    """A requested tool selection cannot be preserved by this translation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="tool-choice-not-supported", field_path="tool_choice")


@dataclass(frozen=True, slots=True)
class Loss:
    """One thing a translation could not carry."""

    code: LossCode
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.code.value}: {self.detail}" if self.detail else self.code.value


@dataclass(slots=True)
class Conversion:
    """The losses and non-loss facts owned by one translation.

    A named loss is the difference between a degraded response and a silent one. Facts record observations without changing `lossless`, which depends only on whether losses exist.
    """

    losses: list[Loss] = field(default_factory=lambda: list[Loss]())
    facts: list[ConversionFact] = field(default_factory=lambda: list[ConversionFact]())
    warnings: list[ConversionWarning] = field(
        default_factory=lambda: list[ConversionWarning]()
    )

    def record(self, code: LossCode, detail: str = "") -> None:
        self.losses.append(Loss(code, detail))

    def observe(self, code: ConversionFactCode, detail: str = "") -> None:
        self.facts.append(ConversionFact(code, detail))

    def warn(
        self,
        code: str,
        *,
        source_format: str,
        field_path: str,
        detail: str = "",
    ) -> None:
        self.warnings.append(
            ConversionWarning(
                code=code,
                source_format=source_format,
                field_path=field_path,
                detail=detail,
            )
        )

    def has(self, code: LossCode) -> bool:
        return any(loss.code is code for loss in self.losses)

    @property
    def lossless(self) -> bool:
        return not self.losses


@dataclass(frozen=True, slots=True)
class TranslationTarget:
    """What the model this request is about to be sent to can do.

    Deliberately not part of `SemanticRequest`. That record is what the *client* asked for and must read the same whoever ends up serving it; this is a fact about the server that was chosen, and folding the two together would mean a request meant one thing before routing and another after.

    Only what a writer needs to render correctly goes in. `reasoning_efforts` is `None` when the catalog said nothing, mirroring `ModelDescriptor` — a writer has to be able to tell "publishes none" from "we never learned", because the safe thing to send differs.

    The default instance is what a translation with no resolved model gets: same-format round trips in tests, and any caller that has not been given a descriptor. Its `None` efforts mean a writer will decline to invent a reasoning field rather than guess one.
    """

    model_id: str = ""
    reasoning_efforts: tuple[str, ...] | None = None
    thinking_profile: ThinkingTargetProfile | None = None
    thinking_profile_pattern: str = ""


@dataclass(slots=True)
class SemanticRequest:
    """The semantic IR for a model request."""

    model: str
    system: list[SystemBlock] = field(default_factory=lambda: list[SystemBlock]())
    messages: list[SemanticMessage] = field(default_factory=lambda: list[SemanticMessage]())
    tools: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    stream: bool = False
    max_output_tokens: int | None = None
    temperature: float | None = None
    thinking_effort: ThinkingEffortIntent | None = None
    # None means absent or unclaimed; an unclaimed choice remains in extensions for exact replay.
    tool_choice: ToolChoiceIntent | None = None
    # Which wire format the extensions below came off. A writer for a different format must not replay them: an unclaimed key is unclaimed *in its own format*, and in another one it is at best meaningless. Measured — sending Anthropic's `context_management` to the Responses endpoint gets `failed to parse request`, so replaying it is not merely untidy.
    source_format: str = ""
    # The client's own tool-search tool, when one was identified. Written by the outbound writer rather than read off the wire, because identification depends on what that writer decided to do — and the *response* half needs the same answer to turn a `tool_search_call` back into a call on that tool. Empty means no search was translated, which is also the answer when identification declined.
    client_search_tool: str = ""
    # True only when the writer actually mapped an Anthropic dated web-search declaration into the Responses builtin. The response half reads this to distinguish D6's requested call from D3's unsolicited call; the response payload cannot answer who asked for it.
    hosted_web_search_expected: bool = False
    # Request unknown fields no decoder claimed, kept source-scoped so they are
    # projected only by an explicit target codec rule.
    extensions: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    # Unclaimed siblings inside objects a reader otherwise owns. Kept separately so a writer can merge the object before its modelled fields overwrite stale residual values.
    nested_extensions: dict[str, dict[str, Any]] = field(
        default_factory=lambda: dict[str, dict[str, Any]]()
    )
    conversion: Conversion = field(default_factory=Conversion)

    @property
    def unknown_fields(self) -> dict[str, Any]:
        """Request-side fields no decoder claimed, scoped to ``source_format``."""
        return self.extensions

    @unknown_fields.setter
    def unknown_fields(self, value: dict[str, Any]) -> None:
        self.extensions = value

    @property
    def nested_unknown_fields(self) -> dict[str, dict[str, Any]]:
        return self.nested_extensions

    @nested_unknown_fields.setter
    def nested_unknown_fields(self, value: dict[str, dict[str, Any]]) -> None:
        self.nested_extensions = value

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

    def unknown_fields_for(
        self,
        wire_format: str,
        *,
        excluded: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        fields = {key: value for key, value in self.extensions.items() if key not in excluded}
        if not fields or self.source_format == wire_format:
            return fields
        self.conversion.record(
            LossCode.EXTENSIONS_NOT_CARRIED,
            f"from {self.source_format or 'an unnamed format'} into {wire_format}: "
            f"{', '.join(sorted(fields))}",
        )
        return {}

    def nested_extensions_for(self, wire_format: str) -> dict[str, dict[str, Any]]:
        if not self.nested_extensions:
            return {}
        if self.source_format == wire_format:
            return {name: dict(fields) for name, fields in self.nested_extensions.items()}
        for name, fields in self.nested_extensions.items():
            for key in sorted(fields):
                self.conversion.record(
                    LossCode.EXTENSIONS_NOT_CARRIED,
                    f"from {self.source_format} into {wire_format}: {name}.{key}",
                )
        return {}

    def nested_unknown_fields_for(self, wire_format: str) -> dict[str, dict[str, Any]]:
        return self.nested_extensions_for(wire_format)


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


class WebSearchNotExecutable(TranslationRefused):
    """A web search this endpoint cannot run, to be answered rather than refused.

    A subclass of the refusal it replaces, so anything that already classifies a `TranslationRefused` — the 400 mapping among them — keeps working if this is ever raised somewhere that does not know to answer it. What the handler does instead is synthesise the reply Anthropic defines for a failed search, because on the client that sends these an HTTP error demonstrably drew repeat calls from the model and no mechanism repeats a failed tool result. (Repeat calls from the *model*: the transport does not retry a 400 at all. Corrected 2026-08-30.)

    Carries no query: the turn that asked for the search is still on the context, and reading it there keeps this exception about *what happened* rather than about what the reply should say.
    """
