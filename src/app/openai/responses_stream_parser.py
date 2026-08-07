from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Never, cast

type JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class BlockIdentity:
    output_index: int
    item_id: str
    content_index: int | None


@dataclass(frozen=True, slots=True)
class TextBlock:
    text: str


@dataclass(frozen=True, slots=True)
class FunctionCallBlock:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class ReasoningBlock:
    summary: str
    encrypted_content: str | None


type SemanticBlock = TextBlock | FunctionCallBlock | ReasoningBlock


@dataclass(frozen=True, slots=True)
class CompletedBlock:
    identity: BlockIdentity
    content: SemanticBlock
    first_observed_order: int
    completion_order: int


@dataclass(frozen=True, slots=True)
class SourceOpened:
    identity: BlockIdentity
    source_order: int


@dataclass(frozen=True, slots=True)
class UnsupportedResponsesEvent:
    event_type: str
    output_index: int | None
    item_id: str | None
    content_index: int | None


type TerminalKind = Literal["completed", "incomplete", "failed", "error"]


@dataclass(frozen=True, slots=True)
class ResponsesTerminal:
    kind: TerminalKind
    response_id: str | None
    status: str | None
    error_code: str | None
    message: str | None
    open_blocks: tuple[BlockIdentity, ...]


type ResponsesSemanticEvent = (
    CompletedBlock | SourceOpened | UnsupportedResponsesEvent | ResponsesTerminal
)


class ResponsesStreamProtocolError(ValueError):
    def __init__(self, message: str, *, code: str, event_type: str) -> None:
        super().__init__(message)
        self.code = code
        self.event_type = event_type


@dataclass(slots=True)
class _TextDraft:
    identity: BlockIdentity
    first_observed_order: int
    deltas: list[str] = field(default_factory=lambda: list[str]())
    done: bool = False


@dataclass(slots=True)
class _FunctionCallDraft:
    identity: BlockIdentity
    first_observed_order: int
    call_id: str
    name: str
    argument_deltas: list[str] = field(default_factory=lambda: list[str]())
    arguments: str | None = None
    arguments_done: bool = False
    item_done: bool = False
    emitted: bool = False


@dataclass(slots=True)
class _ReasoningPartDraft:
    deltas: list[str] = field(default_factory=lambda: list[str]())
    text: str | None = None
    done: bool = False


@dataclass(slots=True)
class _ReasoningDraft:
    identity: BlockIdentity
    first_observed_order: int
    parts: dict[int, _ReasoningPartDraft] = field(
        default_factory=lambda: dict[int, _ReasoningPartDraft]()
    )
    authoritative_summary: str | None = None
    encrypted_content: str | None = None
    item_done: bool = False
    emitted: bool = False


@dataclass(slots=True)
class _ItemDraft:
    output_index: int
    item_id: str
    item_type: str
    source_order: int
    done: bool = False
    unsupported: bool = False


class ResponsesStreamParser:
    """Assemble Responses lifecycle events into immutable semantic facts.

    The parser owns attempt-local drafts only. It does not render Anthropic wire data,
    sequence completed blocks for a sink, advance a delivery frontier, or retry.
    """

    def __init__(self) -> None:
        self._items: dict[int, _ItemDraft] = {}
        self._text: dict[tuple[int, int], _TextDraft] = {}
        self._function_calls: dict[int, _FunctionCallDraft] = {}
        self._reasoning: dict[int, _ReasoningDraft] = {}
        self._next_source_order = 0
        self._next_completion_order = 0
        self._terminal: ResponsesTerminal | None = None

    @property
    def open_blocks(self) -> tuple[BlockIdentity, ...]:
        """Return stable identities that still prevent a contiguous commit prefix."""
        return self._open_blocks()

    def process(self, event: dict[str, Any]) -> tuple[ResponsesSemanticEvent, ...]:
        event_type = event.get("type")
        if not isinstance(event_type, str) or not event_type:
            return (self._unsupported(event, "<missing>"),)
        if self._terminal is not None:
            self._fail(
                "event received after terminal",
                code="event_after_terminal",
                event_type=event_type,
            )

        if event_type == "response.output_item.added":
            opened = self._on_output_item_added(event, event_type)
            return (opened,)
        if event_type == "response.output_item.done":
            completed = self._on_output_item_done(event, event_type)
            return (completed,) if completed is not None else ()
        if event_type == "response.output_text.delta":
            self._on_output_text_delta(event, event_type)
            return ()
        if event_type == "response.output_text.done":
            return (self._on_output_text_done(event, event_type),)
        if event_type == "response.function_call_arguments.delta":
            self._on_function_arguments_delta(event, event_type)
            return ()
        if event_type == "response.function_call_arguments.done":
            completed = self._on_function_arguments_done(event, event_type)
            return (completed,) if completed is not None else ()
        if event_type == "response.reasoning_summary_text.delta":
            self._on_reasoning_delta(event, event_type)
            return ()
        if event_type == "response.reasoning_summary_text.done":
            self._on_reasoning_done(event, event_type)
            return ()
        if event_type in {
            "response.completed",
            "response.incomplete",
            "response.failed",
            "error",
        }:
            terminal = self._on_terminal(event, event_type)
            return (terminal,)
        return (self._unsupported(event, event_type),)

    def _on_output_item_added(
        self, event: dict[str, Any], event_type: str
    ) -> SourceOpened | UnsupportedResponsesEvent:
        output_index = self._require_index(event, "output_index", event_type)
        item = self._require_object(event, "item", event_type)
        item_id = self._require_string(item, "id", event_type)
        item_type = self._require_string(item, "type", event_type)
        if output_index in self._items:
            self._fail(
                f"duplicate output item {output_index}",
                code="duplicate_output_item",
                event_type=event_type,
            )
        source_order = self._take_source_order()
        state = _ItemDraft(output_index, item_id, item_type, source_order)
        self._items[output_index] = state

        identity = BlockIdentity(output_index, item_id, None)
        if item_type == "function_call":
            call_id = self._require_string(item, "call_id", event_type)
            name = self._require_string(item, "name", event_type)
            initial_arguments = item.get("arguments", "")
            if not isinstance(initial_arguments, str):
                self._fail(
                    "function_call arguments must be a string",
                    code="invalid_arguments",
                    event_type=event_type,
                )
            draft = _FunctionCallDraft(
                identity=identity,
                first_observed_order=source_order,
                call_id=call_id,
                name=name,
            )
            if initial_arguments:
                draft.argument_deltas.append(initial_arguments)
            self._function_calls[output_index] = draft
        elif item_type == "reasoning":
            encrypted_content = item.get("encrypted_content")
            if encrypted_content is not None and not isinstance(encrypted_content, str):
                self._fail(
                    "reasoning encrypted_content must be a string or null",
                    code="invalid_reasoning",
                    event_type=event_type,
                )
            self._reasoning[output_index] = _ReasoningDraft(
                identity=identity,
                first_observed_order=source_order,
                encrypted_content=encrypted_content or None,
            )
        elif item_type != "message":
            state.unsupported = True
            return self._unsupported(event, event_type)
        return SourceOpened(identity, source_order)

    def _on_output_item_done(
        self, event: dict[str, Any], event_type: str
    ) -> CompletedBlock | UnsupportedResponsesEvent | None:
        output_index = self._require_index(event, "output_index", event_type)
        item = self._require_object(event, "item", event_type)
        state = self._require_item(event, output_index, event_type)
        self._validate_item_id(item, state, event_type)
        item_type = self._require_string(item, "type", event_type)
        if item_type != state.item_type:
            self._fail(
                "output item type changed before completion",
                code="item_type_mismatch",
                event_type=event_type,
            )
        if state.done:
            self._duplicate_done(event_type, output_index)
        state.done = True

        if state.unsupported:
            return self._unsupported(event, event_type)

        if item_type == "function_call":
            draft = self._function_calls[output_index]
            draft.item_done = True
            self._update_function_call_from_item(draft, item, event_type)
            return self._complete_function_call(draft, event_type)
        if item_type == "reasoning":
            draft = self._reasoning[output_index]
            draft.item_done = True
            draft.authoritative_summary = self._reasoning_summary(item, event_type)
            encrypted_content = item.get("encrypted_content")
            if encrypted_content is not None and not isinstance(encrypted_content, str):
                self._fail(
                    "reasoning encrypted_content must be a string or null",
                    code="invalid_reasoning",
                    event_type=event_type,
                )
            draft.encrypted_content = encrypted_content or None
            return self._complete_reasoning(draft, event_type)
        return None

    def _on_output_text_delta(self, event: dict[str, Any], event_type: str) -> None:
        draft = self._text_draft(event, event_type)
        if draft.done:
            self._fail(
                "text delta received after done",
                code="delta_after_done",
                event_type=event_type,
            )
        draft.deltas.append(self._require_string(event, "delta", event_type, allow_empty=True))

    def _on_output_text_done(
        self, event: dict[str, Any], event_type: str
    ) -> CompletedBlock:
        draft = self._text_draft(event, event_type)
        if draft.done:
            self._duplicate_done(event_type, draft.identity.output_index)
        authoritative = self._require_string(event, "text", event_type, allow_empty=True)
        accumulated = "".join(draft.deltas)
        if draft.deltas and accumulated != authoritative:
            self._fail(
                "text deltas do not match authoritative done text",
                code="authoritative_text_mismatch",
                event_type=event_type,
            )
        draft.done = True
        return self._completed(draft.identity, TextBlock(authoritative), draft.first_observed_order)

    def _on_function_arguments_delta(self, event: dict[str, Any], event_type: str) -> None:
        output_index = self._require_index(event, "output_index", event_type)
        draft = self._function_call_draft(event, output_index, event_type)
        if draft.arguments_done:
            self._fail(
                "function arguments delta received after done",
                code="delta_after_done",
                event_type=event_type,
            )
        draft.argument_deltas.append(
            self._require_string(event, "delta", event_type, allow_empty=True)
        )

    def _on_function_arguments_done(
        self, event: dict[str, Any], event_type: str
    ) -> CompletedBlock | None:
        output_index = self._require_index(event, "output_index", event_type)
        draft = self._function_call_draft(event, output_index, event_type)
        if draft.arguments_done:
            self._duplicate_done(event_type, output_index)
        draft.arguments = self._require_string(
            event, "arguments", event_type, allow_empty=True
        )
        draft.arguments_done = True
        return self._complete_function_call(draft, event_type)

    def _on_reasoning_delta(self, event: dict[str, Any], event_type: str) -> None:
        output_index = self._require_index(event, "output_index", event_type)
        draft = self._reasoning_draft(event, output_index, event_type)
        summary_index = self._require_index(event, "summary_index", event_type)
        part = draft.parts.setdefault(summary_index, _ReasoningPartDraft())
        if part.done:
            self._fail(
                "reasoning summary delta received after done",
                code="delta_after_done",
                event_type=event_type,
            )
        part.deltas.append(self._require_string(event, "delta", event_type, allow_empty=True))

    def _on_reasoning_done(self, event: dict[str, Any], event_type: str) -> None:
        output_index = self._require_index(event, "output_index", event_type)
        draft = self._reasoning_draft(event, output_index, event_type)
        summary_index = self._require_index(event, "summary_index", event_type)
        part = draft.parts.setdefault(summary_index, _ReasoningPartDraft())
        if part.done:
            self._duplicate_done(event_type, output_index)
        authoritative = self._require_string(event, "text", event_type, allow_empty=True)
        accumulated = "".join(part.deltas)
        if part.deltas and accumulated != authoritative:
            self._fail(
                "reasoning deltas do not match authoritative done text",
                code="authoritative_reasoning_mismatch",
                event_type=event_type,
            )
        part.text = authoritative
        part.done = True

    def _on_terminal(self, event: dict[str, Any], event_type: str) -> ResponsesTerminal:
        response = event.get("response")
        response_object = cast(JsonObject, response) if isinstance(response, dict) else {}
        response_id = self._optional_string(response_object.get("id"))
        status = self._optional_string(response_object.get("status"))
        error = response_object.get("error")
        error_object = cast(JsonObject, error) if isinstance(error, dict) else {}
        kind: TerminalKind
        if event_type == "response.completed":
            kind = "completed"
        elif event_type == "response.incomplete":
            kind = "incomplete"
        elif event_type == "response.failed":
            kind = "failed"
        else:
            kind = "error"
        open_blocks = self._open_blocks()
        unsupported_items = any(item.unsupported for item in self._items.values())
        error_code = self._optional_string(event.get("code")) or self._optional_string(
            error_object.get("code")
        )
        message = self._optional_string(event.get("message")) or self._optional_string(
            error_object.get("message")
        )
        if kind == "completed" and unsupported_items:
            kind = "incomplete"
            error_code = "unsupported_output_item"
            message = "response contains unsupported output items"
        elif kind == "completed" and open_blocks:
            kind = "incomplete"
            error_code = "incomplete_lifecycle"
            message = "response completed with open output items"
        terminal = ResponsesTerminal(
            kind=kind,
            response_id=response_id,
            status=status,
            error_code=error_code,
            message=message,
            open_blocks=open_blocks,
        )
        self._terminal = terminal
        return terminal

    def _text_draft(self, event: dict[str, Any], event_type: str) -> _TextDraft:
        output_index = self._require_index(event, "output_index", event_type)
        content_index = self._require_index(event, "content_index", event_type)
        item = self._require_item(event, output_index, event_type)
        if item.item_type != "message":
            self._fail(
                "output text event does not belong to a message item",
                code="item_type_mismatch",
                event_type=event_type,
            )
        self._validate_event_item_id(event, item, event_type)
        key = (output_index, content_index)
        draft = self._text.get(key)
        if draft is None:
            draft = _TextDraft(
                identity=BlockIdentity(output_index, item.item_id, content_index),
                first_observed_order=item.source_order,
            )
            self._text[key] = draft
        return draft

    def _function_call_draft(
        self, event: dict[str, Any], output_index: int, event_type: str
    ) -> _FunctionCallDraft:
        item = self._require_item(event, output_index, event_type)
        if item.item_type != "function_call":
            self._fail(
                "function arguments event does not belong to a function_call item",
                code="item_type_mismatch",
                event_type=event_type,
            )
        self._validate_event_item_id(event, item, event_type)
        return self._function_calls[output_index]

    def _reasoning_draft(
        self, event: dict[str, Any], output_index: int, event_type: str
    ) -> _ReasoningDraft:
        item = self._require_item(event, output_index, event_type)
        if item.item_type != "reasoning":
            self._fail(
                "reasoning event does not belong to a reasoning item",
                code="item_type_mismatch",
                event_type=event_type,
            )
        self._validate_event_item_id(event, item, event_type)
        return self._reasoning[output_index]

    def _complete_function_call(
        self, draft: _FunctionCallDraft, event_type: str
    ) -> CompletedBlock | None:
        if not draft.item_done or not draft.arguments_done or draft.emitted:
            return None
        if draft.arguments is None:
            self._fail(
                "function call completed without authoritative arguments",
                code="incomplete_function_call",
                event_type=event_type,
            )
        draft.emitted = True
        content = FunctionCallBlock(draft.call_id, draft.name, draft.arguments)
        return self._completed(draft.identity, content, draft.first_observed_order)

    def _complete_reasoning(
        self, draft: _ReasoningDraft, event_type: str
    ) -> CompletedBlock | None:
        if not draft.item_done or draft.emitted:
            return None
        if any(not part.done for part in draft.parts.values()):
            self._fail(
                "reasoning item completed with an incomplete summary part",
                code="incomplete_reasoning",
                event_type=event_type,
            )
        summary = draft.authoritative_summary
        if summary is None:
            summary = "".join(
                part.text or "" for _, part in sorted(draft.parts.items())
            )
        if not summary and draft.encrypted_content is None:
            draft.emitted = True
            return None
        draft.emitted = True
        content = ReasoningBlock(summary, draft.encrypted_content)
        return self._completed(draft.identity, content, draft.first_observed_order)

    def _update_function_call_from_item(
        self, draft: _FunctionCallDraft, item: dict[str, Any], event_type: str
    ) -> None:
        call_id = self._require_string(item, "call_id", event_type)
        name = self._require_string(item, "name", event_type)
        if call_id != draft.call_id or name != draft.name:
            self._fail(
                "function call identity changed before completion",
                code="function_call_identity_mismatch",
                event_type=event_type,
            )
        arguments = item.get("arguments")
        if arguments is not None:
            if not isinstance(arguments, str):
                self._fail(
                    "function_call arguments must be a string",
                    code="invalid_arguments",
                    event_type=event_type,
                )
            if draft.arguments is not None and draft.arguments != arguments:
                self._fail(
                    "function argument done values disagree",
                    code="authoritative_arguments_mismatch",
                    event_type=event_type,
                )
            draft.arguments = arguments
            draft.arguments_done = True

    def _reasoning_summary(self, item: dict[str, Any], event_type: str) -> str | None:
        summary = item.get("summary")
        if summary is None:
            return None
        if not isinstance(summary, list):
            self._fail(
                "reasoning summary must be an array",
                code="invalid_reasoning",
                event_type=event_type,
            )
        parts: list[str] = []
        for raw_part in cast(list[Any], summary):
            if not isinstance(raw_part, dict):
                self._fail(
                    "reasoning summary parts require text",
                    code="invalid_reasoning",
                    event_type=event_type,
                )
            part = cast(JsonObject, raw_part)
            text = part.get("text")
            if not isinstance(text, str):
                self._fail(
                    "reasoning summary parts require text",
                    code="invalid_reasoning",
                    event_type=event_type,
                )
            parts.append(text)
        return "".join(parts)

    def _completed(
        self, identity: BlockIdentity, content: SemanticBlock, first_observed_order: int
    ) -> CompletedBlock:
        completion_order = self._next_completion_order
        self._next_completion_order += 1
        return CompletedBlock(identity, content, first_observed_order, completion_order)

    def _open_blocks(self) -> tuple[BlockIdentity, ...]:
        identities: dict[BlockIdentity, int] = {
            BlockIdentity(item.output_index, item.item_id, None): item.source_order
            for item in self._items.values()
            if not item.done or item.unsupported
        }
        for draft in self._text.values():
            item = self._items[draft.identity.output_index]
            if item.done and not draft.done:
                identities[draft.identity] = item.source_order
        for draft in self._function_calls.values():
            if not draft.emitted:
                identities[draft.identity] = draft.first_observed_order
        for draft in self._reasoning.values():
            if not draft.emitted:
                identities[draft.identity] = draft.first_observed_order
        return tuple(
            sorted(
                identities,
                key=lambda identity: (
                    identities[identity],
                    identity.content_index if identity.content_index is not None else -1,
                ),
            )
        )

    def _unsupported(
        self, event: dict[str, Any], event_type: str
    ) -> UnsupportedResponsesEvent:
        nested_item = event.get("item")
        nested_item_id = (
            self._optional_string(cast(JsonObject, nested_item).get("id"))
            if isinstance(nested_item, dict)
            else None
        )
        return UnsupportedResponsesEvent(
            event_type=event_type,
            output_index=self._optional_index(event.get("output_index")),
            item_id=self._optional_string(event.get("item_id")) or nested_item_id,
            content_index=self._optional_index(event.get("content_index")),
        )

    def _require_item(
        self, event: dict[str, Any], output_index: int, event_type: str
    ) -> _ItemDraft:
        item = self._items.get(output_index)
        if item is None:
            self._fail(
                f"event references unknown output item {output_index}",
                code="unknown_output_item",
                event_type=event_type,
            )
        self._validate_event_item_id(event, item, event_type)
        return item

    def _validate_event_item_id(
        self, event: dict[str, Any], item: _ItemDraft, event_type: str
    ) -> None:
        item_id = event.get("item_id")
        if item_id is not None and item_id != item.item_id:
            self._fail(
                "event item_id does not match output_index",
                code="item_id_mismatch",
                event_type=event_type,
            )

    def _validate_item_id(
        self, item: dict[str, Any], state: _ItemDraft, event_type: str
    ) -> None:
        if self._require_string(item, "id", event_type) != state.item_id:
            self._fail(
                "done item id does not match added item id",
                code="item_id_mismatch",
                event_type=event_type,
            )

    def _take_source_order(self) -> int:
        value = self._next_source_order
        self._next_source_order += 1
        return value

    def _duplicate_done(self, event_type: str, output_index: int) -> Never:
        self._fail(
            f"duplicate done event for output item {output_index}",
            code="duplicate_done",
            event_type=event_type,
        )

    @classmethod
    def _require_object(
        cls, value: dict[str, Any], key: str, event_type: str
    ) -> dict[str, Any]:
        candidate = value.get(key)
        if not isinstance(candidate, dict):
            cls._fail(
                f"{key} must be an object",
                code="invalid_event",
                event_type=event_type,
            )
        return cast(JsonObject, candidate)

    @classmethod
    def _require_string(
        cls,
        value: dict[str, Any],
        key: str,
        event_type: str,
        *,
        allow_empty: bool = False,
    ) -> str:
        candidate = value.get(key)
        if not isinstance(candidate, str) or (not allow_empty and not candidate):
            cls._fail(
                f"{key} must be a string",
                code="invalid_event",
                event_type=event_type,
            )
        return candidate

    @classmethod
    def _require_index(cls, value: dict[str, Any], key: str, event_type: str) -> int:
        candidate = value.get(key)
        index = cls._optional_index(candidate)
        if index is None:
            cls._fail(
                f"{key} must be a non-negative integer",
                code="invalid_event",
                event_type=event_type,
            )
        return index

    @staticmethod
    def _optional_index(value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _fail(message: str, *, code: str, event_type: str) -> Never:
        raise ResponsesStreamProtocolError(message, code=code, event_type=event_type)


__all__ = [
    "BlockIdentity",
    "CompletedBlock",
    "FunctionCallBlock",
    "ReasoningBlock",
    "ResponsesSemanticEvent",
    "ResponsesStreamParser",
    "ResponsesStreamProtocolError",
    "ResponsesTerminal",
    "SemanticBlock",
    "SourceOpened",
    "TextBlock",
    "UnsupportedResponsesEvent",
]
