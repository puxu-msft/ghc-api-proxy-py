from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from app.pipeline.chat_completions.events import ChatEventFacts, ChatEventKind, ChatEventReader
from app.pipeline.delivery.sse_source import RawSseFrame
from app.pipeline.response_observation import (
    ExactUsage,
    FrozenJson,
    FrozenJsonArray,
    FrozenJsonObject,
    JsonAvailability,
    JsonObservation,
    NormalizedUsage,
    ObservationIssue,
    UsageObservation,
    thaw_json,
)
from app.pipeline.retry import RetryReason


@dataclass(frozen=True, slots=True)
class ChatUnattributedFact:
    frame_ordinal: int
    start: int
    end: int
    field_path: str
    value: JsonObservation


@dataclass(frozen=True, slots=True)
class ChatToolCallSnapshot:
    index: int
    id: JsonObservation
    type: JsonObservation
    name: JsonObservation
    arguments: JsonObservation
    tool_unknown: FrozenJsonObject
    function_unknown: FrozenJsonObject


@dataclass(frozen=True, slots=True)
class ChatChoiceSnapshot:
    index: int
    finish_reason: JsonObservation
    reasoning_content: JsonObservation
    tool_calls: tuple[ChatToolCallSnapshot, ...]
    choice_unknown: FrozenJsonObject
    message_unknown: FrozenJsonObject


@dataclass(frozen=True, slots=True)
class ChatAttemptSnapshot:
    done_seen: bool
    semantic_end_offset: int | None
    identity: FrozenJsonObject
    choices: tuple[ChatChoiceSnapshot, ...]
    usage: UsageObservation | None
    stream_error: JsonObservation
    error_values: tuple[str, ...]
    error_retry_reason: RetryReason | None
    top_level_unknown: FrozenJsonObject
    unattributed: tuple[ChatUnattributedFact, ...]
    issues: tuple[ObservationIssue, ...]


@dataclass(frozen=True, slots=True)
class MaterializationReservation:
    working_copy_bytes: int
    output_bytes: int

    @property
    def total_bytes(self) -> int:
        return self.working_copy_bytes + self.output_bytes


class ChatCompletionUnassemblable(ValueError):
    code = "unassemblable"

    def __init__(
        self,
        message: str,
        *,
        field_path: str | None = None,
        frame_ordinal: int | None = None,
        start: int | None = None,
        end: int | None = None,
    ) -> None:
        super().__init__(message)
        self.field_path = field_path
        self.frame_ordinal = frame_ordinal
        self.start = start
        self.end = end


@dataclass(slots=True)
class _FirstString:
    value: str | None = None
    null_seen: bool = False
    invalid: bool = False


@dataclass(slots=True)
class _ConcatString:
    pieces: list[str] = field(default_factory=lambda: list[str]())
    seen: bool = False
    null_seen: bool = False
    invalid: bool = False


@dataclass(slots=True)
class _JsonArrayDraft:
    seen: bool = False
    null_seen: bool = False
    invalid: bool = False
    values: list[FrozenJson] = field(default_factory=lambda: list[FrozenJson]())
    array_seen: bool = False


@dataclass(slots=True)
class _LogprobsDraft:
    seen: bool = False
    null_seen: bool = False
    object_seen: bool = False
    invalid: bool = False
    content: _JsonArrayDraft = field(default_factory=_JsonArrayDraft)
    refusal: _JsonArrayDraft = field(default_factory=_JsonArrayDraft)
    unknown: dict[str, FrozenJson] = field(default_factory=lambda: dict[str, FrozenJson]())


@dataclass(slots=True)
class _FunctionCallDraft:
    seen: bool = False
    name: _FirstString = field(default_factory=_FirstString)
    arguments: _ConcatString = field(default_factory=_ConcatString)
    unknown: dict[str, FrozenJson] = field(default_factory=lambda: dict[str, FrozenJson]())


@dataclass(slots=True)
class _ToolDraft:
    index: int
    id: _FirstString = field(default_factory=_FirstString)
    type: _FirstString = field(default_factory=_FirstString)
    name: _FirstString = field(default_factory=_FirstString)
    arguments: _ConcatString = field(default_factory=_ConcatString)
    unknown: dict[str, FrozenJson] = field(default_factory=lambda: dict[str, FrozenJson]())
    function_unknown: dict[str, FrozenJson] = field(default_factory=lambda: dict[str, FrozenJson]())


@dataclass(slots=True)
class _ChoiceDraft:
    index: int
    role: _FirstString = field(default_factory=_FirstString)
    content: _ConcatString = field(default_factory=_ConcatString)
    refusal: _ConcatString = field(default_factory=_ConcatString)
    reasoning_content: _ConcatString = field(default_factory=_ConcatString)
    function_call: _FunctionCallDraft = field(default_factory=_FunctionCallDraft)
    tools: dict[int, _ToolDraft] = field(default_factory=lambda: dict[int, _ToolDraft]())
    finish_reason: _FirstString = field(default_factory=_FirstString)
    logprobs: _LogprobsDraft = field(default_factory=_LogprobsDraft)
    unknown: dict[str, FrozenJson] = field(default_factory=lambda: dict[str, FrozenJson]())
    message_unknown: dict[str, FrozenJson] = field(default_factory=lambda: dict[str, FrozenJson]())


_IDENTITY_FIELDS = ("id", "created", "model")
_LAST_EXPLICIT_FIELDS = ("service_tier", "system_fingerprint", "moderation")
_TOP_LEVEL_KNOWN = {
    "id",
    "created",
    "model",
    "object",
    "service_tier",
    "system_fingerprint",
    "moderation",
    "choices",
    "usage",
}
_CHOICE_KNOWN = {"index", "delta", "finish_reason", "logprobs"}
_DELTA_KNOWN = {
    "role",
    "content",
    "refusal",
    "reasoning_content",
    "function_call",
    "tool_calls",
}
_TOOL_KNOWN = {"index", "id", "type", "function"}
_FUNCTION_KNOWN = {"name", "arguments"}


class _Missing:
    pass


_MISSING = _Missing()


class _ProspectiveSizer:
    """Compute one event's retained-byte delta without cloning retained state."""

    def __init__(
        self,
        *,
        identity: Mapping[str, FrozenJson],
        object_seen: bool,
        last_explicit: Mapping[str, FrozenJson],
        top_unknown: Mapping[str, FrozenJson],
        choices: Mapping[int, _ChoiceDraft],
        usage_value: FrozenJsonObject | None,
        usage: UsageObservation | None,
    ) -> None:
        self._identity = identity
        self._object_seen = object_seen
        self._last_explicit = last_explicit
        self._top_unknown = top_unknown
        self._choices = choices
        self._usage_value = usage_value
        self._usage = usage
        self._delta = 0
        self._first: dict[str, tuple[str | None, bool, bool]] = {}
        self._concat_seen: dict[str, bool] = {}
        self._unknown: dict[tuple[str, str], FrozenJson | _Missing] = {}
        self._seen_flags: set[str] = set()
        self._array_seen: dict[str, bool] = {}
        self._new_choices: set[int] = set()
        self._new_tools: set[tuple[int, int]] = set()

    def measure(self, facts: ChatEventFacts) -> int:
        if facts.issue is not None:
            self._delta += _issue_size(facts.issue)
        if facts.kind is ChatEventKind.DONE:
            self._delta += len(str(facts.frame.end))
            for index, choice in self._choices.items():
                if choice.role.value is None:
                    self._add_issue(
                        "role_synthesized",
                        f"choices[{index}].message.role",
                    )
            return self._delta
        if facts.kind is ChatEventKind.ERROR:
            if facts.value.value is not None:
                self._delta += len(b"stream_error") + _frozen_size(facts.value.value)
            self._delta += sum(_utf8_size(value) for value in facts.error_values)
            if facts.retry_reason is not None:
                self._delta += _utf8_size(facts.retry_reason.value)
            self._delta += len(str(facts.frame.end))
            return self._delta
        if facts.kind is ChatEventKind.UNREADABLE:
            self._add_issue("chat_event_unreadable", f"frame[{facts.frame.ordinal}]")
            return self._delta
        if facts.kind is ChatEventKind.UNKNOWN:
            if facts.value.availability in {
                JsonAvailability.OBSERVED,
                JsonAvailability.EXPLICIT_NULL,
            }:
                self._add_issue("chat_event_unassemblable", f"frame[{facts.frame.ordinal}]")
            return self._delta
        if (
            facts.value.availability is not JsonAvailability.OBSERVED
            or not isinstance(facts.value.value, FrozenJsonObject)
        ):
            self._add_issue("chat_chunk_not_object", f"frame[{facts.frame.ordinal}].data")
            return self._delta
        self._measure_chunk(facts.value.value, facts.frame)
        return self._delta

    def _measure_chunk(self, frozen: FrozenJsonObject, frame: RawSseFrame) -> None:
        data = dict(frozen.items)
        for key in _IDENTITY_FIELDS:
            if key not in data:
                continue
            value = data[key]
            valid = (
                isinstance(value, str) and bool(value)
                if key != "created"
                else isinstance(value, int) and not isinstance(value, bool)
            )
            if not valid:
                self._add_issue("chat_identity_invalid", f"frame[{frame.ordinal}].{key}")
                continue
            previous = self._identity.get(key, _MISSING)
            if previous is _MISSING:
                self._delta += _utf8_size(key) + _frozen_size(value)
            elif not _same_frozen_json(cast(FrozenJson, previous), value):
                self._add_issue("chat_identity_conflict", key)
        if "object" in data:
            value = data["object"]
            if value not in (None, ""):
                if value != "chat.completion.chunk":
                    self._add_issue("chat_object_invalid", f"frame[{frame.ordinal}].object")
                elif not self._object_seen:
                    self._delta += len(b"object") + len(b"chat.completion.chunk")
        for key in _LAST_EXPLICIT_FIELDS:
            if key not in data:
                continue
            value = data[key]
            previous = self._last_explicit.get(key, _MISSING)
            if previous is _MISSING:
                self._delta += _utf8_size(key) + _frozen_size(value)
            else:
                self._delta += _frozen_size(value) - _frozen_size(cast(FrozenJson, previous))
        self._measure_usage(data, frame.ordinal)
        self._measure_unknown(self._top_unknown, data, known=_TOP_LEVEL_KNOWN, path="")
        choices = data.get("choices", _MISSING)
        if choices is _MISSING:
            return
        if not isinstance(choices, FrozenJsonArray):
            self._add_issue("chat_choices_invalid", f"frame[{frame.ordinal}].choices")
            return
        seen_indices = set[int]()
        for position, value in enumerate(choices.items):
            path = f"choices[{position}]"
            if not isinstance(value, FrozenJsonObject):
                self._add_unattributed(frame, path, _observation_from_value(value))
                self._add_issue("chat_choice_not_object", f"frame[{frame.ordinal}].{path}")
                continue
            choice = dict(value.items)
            index = choice.get("index", _MISSING)
            if not _valid_index(index):
                self._add_unattributed(
                    frame,
                    path,
                    JsonObservation(availability=JsonAvailability.OBSERVED, value=value),
                )
                self._add_issue("chat_choice_index_invalid", f"frame[{frame.ordinal}].{path}.index")
                continue
            choice_index = cast(int, index)
            if choice_index in seen_indices:
                self._add_issue(
                    "duplicate_choice_index",
                    f"frame[{frame.ordinal}].{path}.index",
                    f"choice index {choice_index}",
                )
            seen_indices.add(choice_index)
            current = self._choices.get(choice_index)
            if current is None and choice_index not in self._new_choices:
                self._new_choices.add(choice_index)
                self._delta += len(b"index") + len(repr(choice_index))
            self._measure_choice(current, choice, frame, position, choice_index)

    def _measure_choice(
        self,
        current: _ChoiceDraft | None,
        choice: Mapping[str, FrozenJson],
        frame: RawSseFrame,
        position: int,
        choice_index: int,
    ) -> None:
        base = f"frame[{frame.ordinal}].choices[{position}]"
        if "finish_reason" in choice:
            self._measure_first_string(
                current.finish_reason if current is not None else None,
                choice["finish_reason"],
                key="finish_reason",
                path=f"choices[{choice_index}].finish_reason",
                allow_empty=True,
            )
        if "logprobs" in choice:
            self._measure_logprobs(
                current.logprobs if current is not None else None,
                choice["logprobs"],
                choice_index=choice_index,
                event_path=f"{base}.logprobs",
            )
        current_unknown = current.unknown if current is not None else {}
        if "message" in choice and self._unknown_value(
            current_unknown,
            f"choices[{choice_index}]",
            "message",
        ) is _MISSING:
            self._add_issue("chat_unknown_reserved_name_collision", f"{base}.message")
        self._measure_unknown(
            current_unknown,
            choice,
            known=_CHOICE_KNOWN,
            path=f"choices[{choice_index}]",
        )
        delta_value = choice.get("delta", _MISSING)
        if delta_value is _MISSING:
            return
        if not isinstance(delta_value, FrozenJsonObject):
            if delta_value is not None:
                self._add_issue("chat_delta_invalid", f"{base}.delta")
            return
        delta = dict(delta_value.items)
        if "role" in delta:
            role = delta["role"]
            role_draft = current.role if current is not None else None
            if role is None:
                self._measure_first_string(
                    role_draft,
                    role,
                    key="role",
                    path=f"choices[{choice_index}].message.role",
                )
            elif not isinstance(role, str) or role != "assistant":
                self._measure_invalid_first(
                    role_draft,
                    key="role",
                    path=f"{base}.delta.role",
                    issue_code="chat_role_invalid",
                )
            else:
                self._measure_first_string(
                    role_draft,
                    role,
                    key="role",
                    path=f"choices[{choice_index}].message.role",
                )
        for key, attribute in (
            ("content", "content"),
            ("refusal", "refusal"),
            ("reasoning_content", "reasoning_content"),
        ):
            if key in delta:
                draft = getattr(current, attribute) if current is not None else None
                self._measure_concat(
                    cast(_ConcatString | None, draft),
                    delta[key],
                    key=key,
                    path=f"{base}.delta.{key}",
                )
        if "function_call" in delta:
            self._measure_function_call(
                current.function_call if current is not None else None,
                delta["function_call"],
                choice_index=choice_index,
                event_path=f"{base}.delta.function_call",
            )
        if "tool_calls" in delta:
            self._measure_tools(
                current,
                delta["tool_calls"],
                frame=frame,
                choice_position=position,
                choice_index=choice_index,
            )
        self._measure_unknown(
            current.message_unknown if current is not None else {},
            delta,
            known=_DELTA_KNOWN,
            path=f"choices[{choice_index}].message",
        )

    def _measure_function_call(
        self,
        current: _FunctionCallDraft | None,
        value: FrozenJson,
        *,
        choice_index: int,
        event_path: str,
    ) -> None:
        path = f"choices[{choice_index}].message.function_call"
        if not self._flag_is_set(path, current.seen if current is not None else False):
            self._seen_flags.add(path)
            self._delta += len(b"function_call")
        if not isinstance(value, FrozenJsonObject):
            self._add_issue("chat_function_call_invalid", event_path)
            return
        function = dict(value.items)
        if "name" in function:
            self._measure_first_string(
                current.name if current is not None else None,
                function["name"],
                key="name",
                path=f"{path}.name",
            )
        if "arguments" in function:
            self._measure_concat(
                current.arguments if current is not None else None,
                function["arguments"],
                key="arguments",
                path=f"{path}.arguments",
            )
        self._measure_unknown(
            current.unknown if current is not None else {},
            function,
            known=_FUNCTION_KNOWN,
            path=path,
        )

    def _measure_tools(
        self,
        current_choice: _ChoiceDraft | None,
        value: FrozenJson,
        *,
        frame: RawSseFrame,
        choice_position: int,
        choice_index: int,
    ) -> None:
        event_base = f"frame[{frame.ordinal}].choices[{choice_position}].delta.tool_calls"
        if not isinstance(value, FrozenJsonArray):
            if value is not None:
                self._add_issue("chat_tool_calls_invalid", event_base)
            return
        seen_indices = set[int]()
        for position, tool_value in enumerate(value.items):
            event_path = f"{event_base}[{position}]"
            if not isinstance(tool_value, FrozenJsonObject):
                self._add_unattributed(
                    frame,
                    event_path.removeprefix(f"frame[{frame.ordinal}]."),
                    _observation_from_value(tool_value),
                )
                self._add_issue("chat_tool_call_not_object", event_path)
                continue
            tool = dict(tool_value.items)
            index = tool.get("index", _MISSING)
            if not _valid_index(index):
                self._add_unattributed(
                    frame,
                    event_path.removeprefix(f"frame[{frame.ordinal}]."),
                    JsonObservation(
                        availability=JsonAvailability.OBSERVED,
                        value=tool_value,
                    ),
                )
                self._add_issue("chat_tool_index_invalid", f"{event_path}.index")
                continue
            tool_index = cast(int, index)
            if tool_index in seen_indices:
                self._add_issue(
                    "duplicate_tool_index",
                    f"{event_path}.index",
                    f"tool index {tool_index}",
                )
            seen_indices.add(tool_index)
            key = (choice_index, tool_index)
            current_tool = (
                current_choice.tools.get(tool_index)
                if current_choice is not None
                else None
            )
            if current_tool is None and key not in self._new_tools:
                self._new_tools.add(key)
                self._delta += len(b"index") + len(repr(tool_index))
            path = f"choices[{choice_index}].tool_calls[{tool_index}]"
            for name, attribute in (("id", "id"), ("type", "type")):
                if name in tool:
                    draft = getattr(current_tool, attribute) if current_tool is not None else None
                    self._measure_first_string(
                        cast(_FirstString | None, draft),
                        tool[name],
                        key=name,
                        path=f"{path}.{name}",
                    )
            function_value = tool.get("function", _MISSING)
            if function_value is not _MISSING:
                if not isinstance(function_value, FrozenJsonObject):
                    self._add_issue("chat_tool_function_invalid", f"{event_path}.function")
                else:
                    function = dict(function_value.items)
                    if "name" in function:
                        self._measure_first_string(
                            current_tool.name if current_tool is not None else None,
                            function["name"],
                            key="name",
                            path=f"{path}.function.name",
                        )
                    if "arguments" in function:
                        self._measure_concat(
                            current_tool.arguments if current_tool is not None else None,
                            function["arguments"],
                            key="arguments",
                            path=f"{path}.function.arguments",
                        )
                    self._measure_unknown(
                        current_tool.function_unknown if current_tool is not None else {},
                        function,
                        known=_FUNCTION_KNOWN,
                        path=f"{path}.function",
                    )
            self._measure_unknown(
                current_tool.unknown if current_tool is not None else {},
                tool,
                known=_TOOL_KNOWN,
                path=path,
            )

    def _measure_logprobs(
        self,
        current: _LogprobsDraft | None,
        value: FrozenJson,
        *,
        choice_index: int,
        event_path: str,
    ) -> None:
        path = f"choices[{choice_index}].logprobs"
        if not self._flag_is_set(path, current.seen if current is not None else False):
            self._seen_flags.add(path)
            self._delta += len(b"logprobs")
        if value is None:
            return
        if not isinstance(value, FrozenJsonObject):
            self._add_issue("chat_logprobs_invalid", event_path)
            return
        logprobs = dict(value.items)
        for key, attribute in (("content", "content"), ("refusal", "refusal")):
            if key not in logprobs:
                continue
            field = getattr(current, attribute) if current is not None else None
            self._measure_array(
                cast(_JsonArrayDraft | None, field),
                logprobs[key],
                key=key,
                path=f"{path}.{key}",
                event_path=f"{event_path}.{key}",
            )
        self._measure_unknown(
            current.unknown if current is not None else {},
            logprobs,
            known={"content", "refusal"},
            path=path,
        )

    def _measure_array(
        self,
        current: _JsonArrayDraft | None,
        value: FrozenJson,
        *,
        key: str,
        path: str,
        event_path: str,
    ) -> None:
        seen = self._array_seen.get(path, current.seen if current is not None else False)
        if not seen:
            self._delta += _utf8_size(key)
        self._array_seen[path] = True
        if value is None:
            return
        if not isinstance(value, FrozenJsonArray):
            self._add_issue("chat_logprobs_array_invalid", event_path)
            return
        self._delta += sum(_frozen_size(nested) for nested in value.items)

    def _measure_first_string(
        self,
        current: _FirstString | None,
        value: FrozenJson,
        *,
        key: str,
        path: str,
        allow_empty: bool = False,
    ) -> None:
        state = self._first.get(path)
        if state is None:
            state = (
                current.value if current is not None else None,
                current.null_seen if current is not None else False,
                current.invalid if current is not None else False,
            )
        retained, null_seen, invalid = state
        present = retained is not None or null_seen or invalid
        if value is None:
            if not present:
                self._delta += _utf8_size(key)
            self._first[path] = (retained, True, invalid)
            return
        if not isinstance(value, str):
            self._measure_invalid_first(
                current,
                key=key,
                path=path,
                issue_code="chat_string_field_invalid",
            )
            return
        if not value and not allow_empty:
            return
        if retained is None:
            if not present:
                self._delta += _utf8_size(key)
            self._delta += _utf8_size(value)
            self._first[path] = (value, null_seen, invalid)
        elif retained != value:
            self._add_issue("chat_string_field_conflict", path)
            self._first[path] = state

    def _measure_invalid_first(
        self,
        current: _FirstString | None,
        *,
        key: str,
        path: str,
        issue_code: str,
    ) -> None:
        state = self._first.get(path)
        if state is None:
            state = (
                current.value if current is not None else None,
                current.null_seen if current is not None else False,
                current.invalid if current is not None else False,
            )
        retained, null_seen, invalid = state
        if retained is None and not null_seen and not invalid:
            self._delta += _utf8_size(key)
        self._first[path] = (retained, null_seen, True)
        self._add_issue(issue_code, path)

    def _measure_concat(
        self,
        current: _ConcatString | None,
        value: FrozenJson,
        *,
        key: str,
        path: str,
    ) -> None:
        seen = self._concat_seen.get(path, current.seen if current is not None else False)
        if not seen:
            self._delta += _utf8_size(key)
        self._concat_seen[path] = True
        if value is None:
            return
        if not isinstance(value, str):
            self._add_issue("chat_string_fragment_invalid", path)
            return
        self._delta += _utf8_size(value)

    def _measure_unknown(
        self,
        current: Mapping[str, FrozenJson],
        incoming: Mapping[str, FrozenJson],
        *,
        known: set[str],
        path: str,
    ) -> None:
        for key, value in incoming.items():
            if key in known:
                continue
            previous = self._unknown_value(current, path, key)
            if previous is _MISSING:
                self._delta += _utf8_size(key) + _frozen_size(value)
                self._unknown[(path, key)] = value
            elif not _same_frozen_json(cast(FrozenJson, previous), value):
                self._add_issue(
                    "chat_unknown_field_conflict",
                    f"{path}.{key}" if path else key,
                )

    def _measure_usage(self, data: Mapping[str, FrozenJson], ordinal: int) -> None:
        if "usage" not in data:
            return
        value = data["usage"]
        path = f"frame[{ordinal}].usage"
        previous_size = _usage_state_size(self._usage_value, self._usage)
        projection = self._usage_value
        if value is None:
            observation = UsageObservation(
                normalized=NormalizedUsage(),
                raw=JsonObservation(availability=JsonAvailability.EXPLICIT_NULL),
                exact=None,
            )
        elif isinstance(value, FrozenJsonObject):
            if projection is not None and not _same_frozen_json(projection, value):
                self._add_issue("chat_usage_replaced", path)
            projection = value
            observation = _usage_observation(dict(value.items), value, ordinal=ordinal)
        else:
            issue = ObservationIssue(code="chat_usage_not_object", field_path=path)
            observation = UsageObservation(
                normalized=NormalizedUsage(),
                raw=_observation_from_value(value),
                exact=None,
                issues=(issue,),
            )
            self._add_issue("chat_usage_invalid", path)
        self._usage_value = projection
        self._usage = observation
        self._delta += _usage_state_size(projection, observation) - previous_size

    def _unknown_value(
        self,
        current: Mapping[str, FrozenJson],
        path: str,
        key: str,
    ) -> FrozenJson | _Missing:
        return self._unknown.get((path, key), current.get(key, _MISSING))

    def _flag_is_set(self, path: str, current: bool) -> bool:
        return current or path in self._seen_flags

    def _add_unattributed(
        self,
        frame: RawSseFrame,
        field_path: str,
        value: JsonObservation,
    ) -> None:
        self._delta += _unattributed_size(
            ChatUnattributedFact(
                frame_ordinal=frame.ordinal,
                start=frame.start,
                end=frame.end,
                field_path=field_path,
                value=value,
            )
        )

    def _add_issue(self, code: str, field_path: str, detail: str | None = None) -> None:
        self._delta += _issue_size(
            ObservationIssue(code=code, field_path=field_path, detail=detail)
        )


class ChatAttemptState:
    """One authoritative semantic state for verdict, projection and observation."""

    def __init__(self, reader: ChatEventReader | None = None) -> None:
        self._reader = reader or ChatEventReader()
        self._done_seen = False
        self._semantic_frozen = False
        self._semantic_end_offset: int | None = None
        self._identity: dict[str, FrozenJson] = {}
        self._object_seen = False
        self._last_explicit: dict[str, FrozenJson] = {}
        self._top_unknown: dict[str, FrozenJson] = {}
        self._choices: dict[int, _ChoiceDraft] = {}
        self._usage_value: FrozenJsonObject | None = None
        self._usage: UsageObservation | None = None
        self._stream_error = JsonObservation(availability=JsonAvailability.ABSENT)
        self._error_values: tuple[str, ...] = ()
        self._error_retry_reason: RetryReason | None = None
        self._unattributed: list[ChatUnattributedFact] = []
        self._issues: list[ObservationIssue] = []
        self._unassemblable: list[ObservationIssue] = []

    @property
    def done_seen(self) -> bool:
        return self._done_seen

    @property
    def held_bytes(self) -> int:
        return self._held_bytes()

    @property
    def semantic_end_offset(self) -> int | None:
        return self._semantic_end_offset

    @property
    def error_values(self) -> tuple[str, ...]:
        return self._error_values

    @property
    def error_retry_reason(self) -> RetryReason | None:
        return self._error_retry_reason

    @property
    def unassemblable(self) -> bool:
        return bool(self._unassemblable)

    def read(self, frame: RawSseFrame) -> ChatEventFacts:
        return self._reader.read(frame)

    def additional_held_bytes(self, facts: ChatEventFacts) -> int:
        if self._semantic_frozen:
            return 0
        return _ProspectiveSizer(
            identity=self._identity,
            object_seen=self._object_seen,
            last_explicit=self._last_explicit,
            top_unknown=self._top_unknown,
            choices=self._choices,
            usage_value=self._usage_value,
            usage=self._usage,
        ).measure(facts)

    def apply(self, facts: ChatEventFacts) -> None:
        self.observe(facts)

    def observe(self, facts: ChatEventFacts) -> None:
        if self._semantic_frozen:
            return
        if facts.issue is not None:
            self._issues.append(facts.issue)
        if facts.kind is ChatEventKind.DONE:
            self._done_seen = True
            self._semantic_end_offset = facts.frame.end
            self._finalize_done()
            self._semantic_frozen = True
            return
        if facts.kind is ChatEventKind.ERROR:
            self._stream_error = facts.value
            self._error_values = facts.error_values
            self._error_retry_reason = facts.retry_reason
            self._semantic_end_offset = facts.frame.end
            self._semantic_frozen = True
            return
        if facts.kind is ChatEventKind.UNREADABLE:
            self._mark_unassemblable(
                "chat_event_unreadable",
                f"frame[{facts.frame.ordinal}]",
            )
            return
        if facts.kind is ChatEventKind.UNKNOWN:
            if facts.value.availability in {
                JsonAvailability.OBSERVED,
                JsonAvailability.EXPLICIT_NULL,
            }:
                self._mark_unassemblable(
                    "chat_event_unassemblable",
                    f"frame[{facts.frame.ordinal}]",
                )
            return
        if (
            facts.value.availability is not JsonAvailability.OBSERVED
            or not isinstance(facts.value.value, FrozenJsonObject)
        ):
            self._mark_unassemblable(
                "chat_chunk_not_object",
                f"frame[{facts.frame.ordinal}].data",
            )
            return
        self._observe_chunk(facts.value.value, facts.frame)

    def freeze(self) -> ChatAttemptSnapshot:
        if not self._semantic_frozen:
            self._semantic_frozen = True
        return self.observation_facts()

    def observation_facts(
        self,
        reservation: MaterializationReservation | None = None,
    ) -> ChatAttemptSnapshot:
        if reservation is not None and reservation != self.observation_reservation():
            raise ValueError("observation reservation does not match current Chat state")
        identity = dict(self._identity)
        if self._object_seen:
            identity["object"] = "chat.completion.chunk"
        identity.update(self._last_explicit)
        choices = tuple(self._choice_snapshot(self._choices[index]) for index in sorted(self._choices))
        return ChatAttemptSnapshot(
            done_seen=self._done_seen,
            semantic_end_offset=self._semantic_end_offset,
            identity=_frozen_object(identity),
            choices=choices,
            usage=self._usage,
            stream_error=self._stream_error,
            error_values=self._error_values,
            error_retry_reason=self._error_retry_reason,
            top_level_unknown=_frozen_object(self._top_unknown),
            unattributed=tuple(self._unattributed),
            issues=tuple(self._issues),
        )

    def to_completion_payload(self) -> dict[str, Any]:
        self._ensure_projection_valid()
        payload: dict[str, Any] = {
            "id": thaw_json(self._identity["id"]),
            "object": "chat.completion",
            "created": thaw_json(self._identity["created"]),
            "model": thaw_json(self._identity["model"]),
        }
        for key in _LAST_EXPLICIT_FIELDS:
            if key in self._last_explicit:
                payload[key] = thaw_json(self._last_explicit[key])
        for key, value in self._top_unknown.items():
            payload[key] = thaw_json(value)
        payload["choices"] = [self._choice_payload(self._choices[index]) for index in sorted(self._choices)]
        if self._usage_value is not None:
            payload["usage"] = thaw_json(self._usage_value)
        return payload

    def projection_reservation(self) -> MaterializationReservation:
        self._ensure_projection_valid()
        output_bytes = self._completion_payload_size()
        return MaterializationReservation(
            working_copy_bytes=output_bytes,
            output_bytes=output_bytes,
        )

    def observation_reservation(self) -> MaterializationReservation:
        output_bytes = self._observation_size()
        return MaterializationReservation(
            working_copy_bytes=output_bytes,
            output_bytes=output_bytes,
        )

    def to_completion_bytes(self, reservation: MaterializationReservation) -> bytes:
        """Materialize compact stdlib JSON after capacity for this reservation is held."""
        expected = self.projection_reservation()
        if reservation != expected:
            raise ValueError("projection reservation does not match current Chat state")
        writer = _ReservedJsonWriter(reservation.output_bytes)
        for chunk in self._iter_completion_bytes():
            writer.write(chunk)
        return writer.finish()

    def projection_size_bytes(self) -> int:
        return self.projection_reservation().output_bytes

    def observation_size_bytes(self) -> int:
        return self.observation_reservation().output_bytes

    def _ensure_projection_valid(self) -> None:
        if not self._done_seen:
            raise ChatCompletionUnassemblable("Chat SSE ended without [DONE]", field_path="done_seen")
        if self._unassemblable:
            first = self._unassemblable[0]
            unattributed = next(
                (
                    fact
                    for fact in self._unattributed
                    if first.field_path is not None
                    and first.field_path.startswith(f"frame[{fact.frame_ordinal}].{fact.field_path}")
                ),
                None,
            )
            raise ChatCompletionUnassemblable(
                first.detail or first.code,
                field_path=first.field_path,
                frame_ordinal=(unattributed.frame_ordinal if unattributed is not None else None),
                start=(unattributed.start if unattributed is not None else None),
                end=(unattributed.end if unattributed is not None else None),
            )
        for field_name in _IDENTITY_FIELDS:
            if field_name not in self._identity:
                raise ChatCompletionUnassemblable(
                    f"required identity field {field_name!r} was not observed",
                    field_path=field_name,
                )
        for index, choice in self._choices.items():
            if choice.finish_reason.value is None:
                raise ChatCompletionUnassemblable(
                    f"choice {index} has no finish_reason",
                    field_path=f"choices[{index}].finish_reason",
                )

    def _completion_payload_size(self) -> int:
        fields = [
            ("id", _frozen_json_wire_size(self._identity["id"])),
            ("object", _json_string_size("chat.completion")),
            ("created", _frozen_json_wire_size(self._identity["created"])),
            ("model", _frozen_json_wire_size(self._identity["model"])),
        ]
        fields.extend(
            (key, _frozen_json_wire_size(self._last_explicit[key]))
            for key in _LAST_EXPLICIT_FIELDS
            if key in self._last_explicit
        )
        fields.extend(
            (key, _frozen_json_wire_size(value))
            for key, value in self._top_unknown.items()
        )
        fields.append(
            (
                "choices",
                _json_array_size(
                    self._choice_payload_size(self._choices[index])
                    for index in sorted(self._choices)
                ),
            )
        )
        if self._usage_value is not None:
            fields.append(("usage", _frozen_json_wire_size(self._usage_value)))
        return _json_object_size(fields)

    def _choice_payload_size(self, draft: _ChoiceDraft) -> int:
        message_fields = [
            ("role", _json_string_size(draft.role.value or "assistant")),
            ("content", _concat_wire_size(draft.content, null_when_empty=True)),
            ("refusal", _concat_wire_size(draft.refusal, null_when_empty=True)),
        ]
        if draft.reasoning_content.pieces:
            message_fields.append(
                ("reasoning_content", _joined_string_wire_size(draft.reasoning_content.pieces))
            )
        if draft.function_call.seen:
            function_fields: list[tuple[str, int]] = []
            if draft.function_call.name.value is not None:
                function_fields.append(("name", _json_string_size(draft.function_call.name.value)))
            function_fields.append(
                ("arguments", _joined_string_wire_size(draft.function_call.arguments.pieces))
            )
            function_fields.extend(
                (key, _frozen_json_wire_size(value))
                for key, value in draft.function_call.unknown.items()
            )
            message_fields.append(("function_call", _json_object_size(function_fields)))
        if draft.tools:
            message_fields.append(
                (
                    "tool_calls",
                    _json_array_size(
                        self._tool_payload_size(draft.tools[index])
                        for index in sorted(draft.tools)
                    ),
                )
            )
        message_fields.extend(
            (key, _frozen_json_wire_size(value))
            for key, value in draft.message_unknown.items()
        )
        fields = [
            ("index", _json_scalar_size(draft.index)),
            ("message", _json_object_size(message_fields)),
            ("finish_reason", _json_string_size(cast(str, draft.finish_reason.value))),
        ]
        if draft.logprobs.seen:
            fields.append(("logprobs", self._logprobs_payload_size(draft.logprobs)))
        fields.extend(
            (key, _frozen_json_wire_size(value))
            for key, value in draft.unknown.items()
        )
        return _json_object_size(fields)

    def _tool_payload_size(self, draft: _ToolDraft) -> int:
        fields: list[tuple[str, int]] = []
        if draft.id.value is not None:
            fields.append(("id", _json_string_size(draft.id.value)))
        if draft.type.value is not None:
            fields.append(("type", _json_string_size(draft.type.value)))
        function_fields: list[tuple[str, int]] = []
        if draft.name.value is not None:
            function_fields.append(("name", _json_string_size(draft.name.value)))
        function_fields.append(("arguments", _joined_string_wire_size(draft.arguments.pieces)))
        function_fields.extend(
            (key, _frozen_json_wire_size(value))
            for key, value in draft.function_unknown.items()
        )
        fields.append(("function", _json_object_size(function_fields)))
        fields.extend(
            (key, _frozen_json_wire_size(value))
            for key, value in draft.unknown.items()
        )
        return _json_object_size(fields)

    def _logprobs_payload_size(self, draft: _LogprobsDraft) -> int:
        if draft.null_seen and not draft.object_seen:
            return 4
        fields: list[tuple[str, int]] = []
        for key, source in (("content", draft.content), ("refusal", draft.refusal)):
            if source.array_seen:
                fields.append(
                    (
                        key,
                        _json_array_size(
                            _frozen_json_wire_size(value)
                            for value in source.values
                        ),
                    )
                )
            elif source.null_seen:
                fields.append((key, 4))
        fields.extend(
            (key, _frozen_json_wire_size(value))
            for key, value in draft.unknown.items()
        )
        return _json_object_size(fields)

    def _iter_completion_bytes(self) -> Iterator[bytes]:
        yield from _iter_json_object(self._completion_fields())

    def _completion_fields(self) -> Iterator[tuple[str, Iterable[bytes]]]:
        yield "id", _iter_frozen_json(self._identity["id"])
        yield "object", _iter_json_string("chat.completion")
        yield "created", _iter_frozen_json(self._identity["created"])
        yield "model", _iter_frozen_json(self._identity["model"])
        for key in _LAST_EXPLICIT_FIELDS:
            if key in self._last_explicit:
                yield key, _iter_frozen_json(self._last_explicit[key])
        for key, value in self._top_unknown.items():
            yield key, _iter_frozen_json(value)
        yield "choices", _iter_json_array(
            self._iter_choice_bytes(self._choices[index])
            for index in sorted(self._choices)
        )
        if self._usage_value is not None:
            yield "usage", _iter_frozen_json(self._usage_value)

    def _iter_choice_bytes(self, draft: _ChoiceDraft) -> Iterator[bytes]:
        yield from _iter_json_object(self._choice_fields(draft))

    def _choice_fields(self, draft: _ChoiceDraft) -> Iterator[tuple[str, Iterable[bytes]]]:
        yield "index", _iter_json_scalar(draft.index)
        yield "message", _iter_json_object(self._message_fields(draft))
        yield "finish_reason", _iter_json_string(cast(str, draft.finish_reason.value))
        if draft.logprobs.seen:
            yield "logprobs", self._iter_logprobs_bytes(draft.logprobs)
        for key, value in draft.unknown.items():
            yield key, _iter_frozen_json(value)

    def _message_fields(self, draft: _ChoiceDraft) -> Iterator[tuple[str, Iterable[bytes]]]:
        yield "role", _iter_json_string(draft.role.value or "assistant")
        yield "content", _iter_concat_json(draft.content, null_when_empty=True)
        yield "refusal", _iter_concat_json(draft.refusal, null_when_empty=True)
        if draft.reasoning_content.pieces:
            yield "reasoning_content", _iter_joined_json_string(draft.reasoning_content.pieces)
        if draft.function_call.seen:
            yield "function_call", _iter_json_object(
                self._function_call_fields(draft.function_call)
            )
        if draft.tools:
            yield "tool_calls", _iter_json_array(
                self._iter_tool_bytes(draft.tools[index])
                for index in sorted(draft.tools)
            )
        for key, value in draft.message_unknown.items():
            yield key, _iter_frozen_json(value)

    def _function_call_fields(
        self,
        draft: _FunctionCallDraft,
    ) -> Iterator[tuple[str, Iterable[bytes]]]:
        if draft.name.value is not None:
            yield "name", _iter_json_string(draft.name.value)
        yield "arguments", _iter_joined_json_string(draft.arguments.pieces)
        for key, value in draft.unknown.items():
            yield key, _iter_frozen_json(value)

    def _iter_tool_bytes(self, draft: _ToolDraft) -> Iterator[bytes]:
        yield from _iter_json_object(self._tool_fields(draft))

    def _tool_fields(self, draft: _ToolDraft) -> Iterator[tuple[str, Iterable[bytes]]]:
        if draft.id.value is not None:
            yield "id", _iter_json_string(draft.id.value)
        if draft.type.value is not None:
            yield "type", _iter_json_string(draft.type.value)
        yield "function", _iter_json_object(self._tool_function_fields(draft))
        for key, value in draft.unknown.items():
            yield key, _iter_frozen_json(value)

    def _tool_function_fields(
        self,
        draft: _ToolDraft,
    ) -> Iterator[tuple[str, Iterable[bytes]]]:
        if draft.name.value is not None:
            yield "name", _iter_json_string(draft.name.value)
        yield "arguments", _iter_joined_json_string(draft.arguments.pieces)
        for key, value in draft.function_unknown.items():
            yield key, _iter_frozen_json(value)

    def _iter_logprobs_bytes(self, draft: _LogprobsDraft) -> Iterator[bytes]:
        if draft.null_seen and not draft.object_seen:
            yield b"null"
            return
        yield from _iter_json_object(self._logprobs_fields(draft))

    def _logprobs_fields(self, draft: _LogprobsDraft) -> Iterator[tuple[str, Iterable[bytes]]]:
        for key, source in (("content", draft.content), ("refusal", draft.refusal)):
            if source.array_seen:
                yield key, _iter_json_array(
                    _iter_frozen_json(value) for value in source.values
                )
            elif source.null_seen:
                yield key, iter((b"null",))
        for key, value in draft.unknown.items():
            yield key, _iter_frozen_json(value)

    def _observation_size(self) -> int:
        total = len(b"done_seen") + (4 if self._done_seen else 5)
        total += len(b"semantic_end_offset")
        total += 4 if self._semantic_end_offset is None else len(str(self._semantic_end_offset))
        total += len(b"identity") + _frozen_mapping_size(self._identity)
        if self._object_seen:
            total += len(b"object") + len(b"chat.completion.chunk")
        total += _frozen_mapping_size(self._last_explicit)
        total += len(b"choices")
        for index, choice in self._choices.items():
            total += len(str(index))
            total += _first_string_observation_size(choice.finish_reason)
            total += _concat_observation_size(choice.reasoning_content)
            total += _frozen_mapping_size(choice.unknown)
            total += _frozen_mapping_size(choice.message_unknown)
            for tool_index, tool in choice.tools.items():
                total += len(str(tool_index))
                total += _first_string_observation_size(tool.id)
                total += _first_string_observation_size(tool.type)
                total += _first_string_observation_size(tool.name)
                total += _concat_observation_size(tool.arguments)
                total += _frozen_mapping_size(tool.unknown)
                total += _frozen_mapping_size(tool.function_unknown)
        total += len(b"usage")
        if self._usage is not None:
            total += _usage_observation_size(self._usage)
        total += len(b"stream_error") + _json_observation_size(self._stream_error)
        total += len(b"error_values") + sum(_utf8_size(value) for value in self._error_values)
        total += len(b"error_retry_reason")
        if self._error_retry_reason is not None:
            total += _utf8_size(self._error_retry_reason.value)
        total += len(b"top_level_unknown") + _frozen_mapping_size(self._top_unknown)
        total += len(b"unattributed")
        for fact in self._unattributed:
            total += len(str(fact.frame_ordinal))
            total += len(str(fact.start)) + len(str(fact.end))
            total += _utf8_size(fact.field_path) + _json_observation_size(fact.value)
        total += len(b"issues") + sum(_issue_size(issue) for issue in self._issues)
        return total

    def _observe_chunk(self, frozen: FrozenJsonObject, frame: RawSseFrame) -> None:
        data = dict(frozen.items)
        self._observe_identity(data, frame.ordinal)
        self._observe_top_level_values(data)
        self._observe_usage(data, frame.ordinal)
        self._merge_unknown(
            self._top_unknown,
            data,
            known=_TOP_LEVEL_KNOWN,
            path="",
        )

        if "choices" not in data:
            return
        raw_choices = data["choices"]
        if not isinstance(raw_choices, FrozenJsonArray):
            self._mark_unassemblable(
                "chat_choices_invalid",
                f"frame[{frame.ordinal}].choices",
            )
            return
        seen_indices: set[int] = set()
        for position, raw_choice in enumerate(raw_choices.items):
            path = f"choices[{position}]"
            if not isinstance(raw_choice, FrozenJsonObject):
                self._retain_unattributed(
                    frame,
                    path,
                    _observation_from_value(raw_choice),
                )
                self._mark_unassemblable(
                    "chat_choice_not_object",
                    f"frame[{frame.ordinal}].{path}",
                )
                continue
            choice = dict(raw_choice.items)
            index = choice.get("index")
            if not _valid_index(index):
                self._retain_unattributed(
                    frame,
                    path,
                    JsonObservation(
                        availability=JsonAvailability.OBSERVED,
                        value=raw_choice,
                    ),
                )
                self._mark_unassemblable(
                    "chat_choice_index_invalid",
                    f"frame[{frame.ordinal}].{path}.index",
                )
                continue
            index = cast(int, index)
            if index in seen_indices:
                self._issue(
                    "duplicate_choice_index",
                    f"frame[{frame.ordinal}].{path}.index",
                    f"choice index {index}",
                )
            seen_indices.add(index)
            draft = self._choices.setdefault(index, _ChoiceDraft(index=index))
            self._observe_choice(draft, choice, frame, position)

    def _observe_identity(self, data: Mapping[str, FrozenJson], ordinal: int) -> None:
        for key in _IDENTITY_FIELDS:
            if key not in data:
                continue
            value = data[key]
            valid = (
                isinstance(value, str) and bool(value)
                if key != "created"
                else isinstance(value, int) and not isinstance(value, bool)
            )
            if not valid:
                self._mark_unassemblable(
                    "chat_identity_invalid",
                    f"frame[{ordinal}].{key}",
                )
                continue
            previous = self._identity.get(key)
            if previous is None:
                self._identity[key] = value
            elif not _same_frozen_json(previous, value):
                self._mark_unassemblable("chat_identity_conflict", key)

        if "object" in data:
            value = data["object"]
            if value in (None, ""):
                return
            if value != "chat.completion.chunk":
                self._mark_unassemblable(
                    "chat_object_invalid",
                    f"frame[{ordinal}].object",
                )
            else:
                self._object_seen = True

    def _observe_top_level_values(self, data: Mapping[str, FrozenJson]) -> None:
        for key in _LAST_EXPLICIT_FIELDS:
            if key in data:
                self._last_explicit[key] = data[key]

    def _observe_usage(self, data: Mapping[str, FrozenJson], ordinal: int) -> None:
        if "usage" not in data:
            return
        raw_usage = data["usage"]
        path = f"frame[{ordinal}].usage"
        if raw_usage is None:
            self._usage = UsageObservation(
                normalized=NormalizedUsage(),
                raw=JsonObservation(availability=JsonAvailability.EXPLICIT_NULL),
                exact=None,
            )
            return
        if not isinstance(raw_usage, FrozenJsonObject):
            issue = ObservationIssue(code="chat_usage_not_object", field_path=path)
            self._usage = UsageObservation(
                normalized=NormalizedUsage(),
                raw=_observation_from_value(raw_usage),
                exact=None,
                issues=(issue,),
            )
            self._mark_unassemblable("chat_usage_invalid", path)
            return
        if self._usage_value is not None and not _same_frozen_json(self._usage_value, raw_usage):
            self._issue("chat_usage_replaced", f"frame[{ordinal}].usage")
        self._usage_value = raw_usage
        self._usage = _usage_observation(
            dict(raw_usage.items),
            raw_usage,
            ordinal=ordinal,
        )

    def _observe_choice(
        self,
        draft: _ChoiceDraft,
        choice: Mapping[str, FrozenJson],
        frame: RawSseFrame,
        position: int,
    ) -> None:
        base = f"frame[{frame.ordinal}].choices[{position}]"
        if "finish_reason" in choice:
            self._observe_first_string(
                draft.finish_reason,
                choice["finish_reason"],
                path=f"choices[{draft.index}].finish_reason",
                allow_empty=True,
            )
        if "logprobs" in choice:
            self._observe_logprobs(draft.logprobs, choice["logprobs"], f"{base}.logprobs")
        if "message" in choice and "message" not in draft.unknown:
            self._mark_unassemblable(
                "chat_unknown_reserved_name_collision",
                f"{base}.message",
            )
        self._merge_unknown(draft.unknown, choice, known=_CHOICE_KNOWN, path=f"choices[{draft.index}]")

        if "delta" not in choice:
            return
        raw_delta = choice["delta"]
        if not isinstance(raw_delta, FrozenJsonObject):
            if raw_delta is not None:
                self._mark_unassemblable("chat_delta_invalid", f"{base}.delta")
            return
        delta = dict(raw_delta.items)
        if "role" in delta:
            role = delta["role"]
            if role is None:
                draft.role.null_seen = True
            elif not isinstance(role, str) or role != "assistant":
                draft.role.invalid = True
                self._mark_unassemblable("chat_role_invalid", f"{base}.delta.role")
            elif draft.role.value is None:
                draft.role.value = role
        for key, target in (
            ("content", draft.content),
            ("refusal", draft.refusal),
            ("reasoning_content", draft.reasoning_content),
        ):
            if key in delta:
                self._observe_concat(target, delta[key], path=f"{base}.delta.{key}")
        if "function_call" in delta:
            self._observe_function_call(
                draft.function_call,
                delta["function_call"],
                f"choices[{draft.index}].message.function_call",
            )
        if "tool_calls" in delta:
            self._observe_tools(
                draft,
                delta["tool_calls"],
                frame=frame,
                choice_position=position,
            )
        self._merge_unknown(
            draft.message_unknown,
            delta,
            known=_DELTA_KNOWN,
            path=f"choices[{draft.index}].message",
        )

    def _observe_function_call(
        self,
        draft: _FunctionCallDraft,
        raw: FrozenJson,
        path: str,
    ) -> None:
        draft.seen = True
        if not isinstance(raw, FrozenJsonObject):
            self._mark_unassemblable("chat_function_call_invalid", path)
            return
        function = dict(raw.items)
        if "name" in function:
            self._observe_first_string(draft.name, function["name"], path=f"{path}.name")
        if "arguments" in function:
            self._observe_concat(draft.arguments, function["arguments"], path=f"{path}.arguments")
        self._merge_unknown(draft.unknown, function, known=_FUNCTION_KNOWN, path=path)

    def _observe_tools(
        self,
        choice: _ChoiceDraft,
        raw: FrozenJson,
        *,
        frame: RawSseFrame,
        choice_position: int,
    ) -> None:
        base = f"frame[{frame.ordinal}].choices[{choice_position}].delta.tool_calls"
        if not isinstance(raw, FrozenJsonArray):
            if raw is not None:
                self._mark_unassemblable("chat_tool_calls_invalid", base)
            return
        seen_indices: set[int] = set()
        for position, raw_tool in enumerate(raw.items):
            path = f"{base}[{position}]"
            if not isinstance(raw_tool, FrozenJsonObject):
                self._retain_unattributed(
                    frame,
                    path.removeprefix(f"frame[{frame.ordinal}]."),
                    _observation_from_value(raw_tool),
                )
                self._mark_unassemblable("chat_tool_call_not_object", path)
                continue
            tool = dict(raw_tool.items)
            index = tool.get("index")
            if not _valid_index(index):
                self._retain_unattributed(
                    frame,
                    path.removeprefix(f"frame[{frame.ordinal}]."),
                    JsonObservation(
                        availability=JsonAvailability.OBSERVED,
                        value=raw_tool,
                    ),
                )
                self._mark_unassemblable("chat_tool_index_invalid", f"{path}.index")
                continue
            index = cast(int, index)
            if index in seen_indices:
                self._issue("duplicate_tool_index", f"{path}.index", f"tool index {index}")
            seen_indices.add(index)
            draft = choice.tools.setdefault(index, _ToolDraft(index=index))
            tool_path = f"choices[{choice.index}].tool_calls[{index}]"
            for key, target in (("id", draft.id), ("type", draft.type)):
                if key in tool:
                    self._observe_first_string(target, tool[key], path=f"{tool_path}.{key}")
            if "function" in tool:
                raw_function = tool["function"]
                if not isinstance(raw_function, FrozenJsonObject):
                    self._mark_unassemblable("chat_tool_function_invalid", f"{path}.function")
                else:
                    function = dict(raw_function.items)
                    if "name" in function:
                        self._observe_first_string(
                            draft.name,
                            function["name"],
                            path=f"{tool_path}.function.name",
                        )
                    if "arguments" in function:
                        self._observe_concat(
                            draft.arguments,
                            function["arguments"],
                            path=f"{tool_path}.function.arguments",
                        )
                    self._merge_unknown(
                        draft.function_unknown,
                        function,
                        known=_FUNCTION_KNOWN,
                        path=f"{tool_path}.function",
                    )
            self._merge_unknown(
                draft.unknown,
                tool,
                known=_TOOL_KNOWN,
                path=tool_path,
            )

    def _observe_logprobs(self, draft: _LogprobsDraft, raw: FrozenJson, path: str) -> None:
        draft.seen = True
        if raw is None:
            draft.null_seen = True
            return
        if not isinstance(raw, FrozenJsonObject):
            draft.invalid = True
            self._mark_unassemblable("chat_logprobs_invalid", path)
            return
        draft.object_seen = True
        logprobs = dict(raw.items)
        for key, target in (("content", draft.content), ("refusal", draft.refusal)):
            if key not in logprobs:
                continue
            target.seen = True
            raw_entries = logprobs[key]
            if raw_entries is None:
                target.null_seen = True
                continue
            if not isinstance(raw_entries, FrozenJsonArray):
                target.invalid = True
                draft.invalid = True
                self._mark_unassemblable("chat_logprobs_array_invalid", f"{path}.{key}")
                continue
            target.array_seen = True
            target.values.extend(raw_entries.items)
        self._merge_unknown(
            draft.unknown,
            logprobs,
            known={"content", "refusal"},
            path=path,
        )

    def _observe_first_string(
        self,
        draft: _FirstString,
        raw: object,
        *,
        path: str,
        allow_empty: bool = False,
    ) -> None:
        if raw is None:
            draft.null_seen = True
            return
        if not isinstance(raw, str):
            draft.invalid = True
            self._mark_unassemblable("chat_string_field_invalid", path)
            return
        if not raw and not allow_empty:
            return
        if draft.value is None:
            draft.value = raw
        elif draft.value != raw:
            self._mark_unassemblable("chat_string_field_conflict", path)

    def _observe_concat(self, draft: _ConcatString, raw: object, *, path: str) -> None:
        draft.seen = True
        if raw is None:
            draft.null_seen = True
            return
        if not isinstance(raw, str):
            draft.invalid = True
            self._mark_unassemblable("chat_string_fragment_invalid", path)
            return
        draft.pieces.append(raw)

    def _merge_unknown(
        self,
        target: dict[str, FrozenJson],
        source: Mapping[str, FrozenJson],
        *,
        known: set[str],
        path: str,
    ) -> None:
        for key, value in source.items():
            if key in known:
                continue
            if key not in target:
                target[key] = value
            elif not _same_frozen_json(target[key], value):
                self._mark_unassemblable(
                    "chat_unknown_field_conflict",
                    f"{path}.{key}" if path else key,
                )

    def _finalize_done(self) -> None:
        for index, choice in self._choices.items():
            if choice.role.value is None:
                self._issue("role_synthesized", f"choices[{index}].message.role")

    def _choice_payload(self, draft: _ChoiceDraft) -> dict[str, Any]:
        message: dict[str, Any] = {"role": draft.role.value or "assistant"}
        message["content"] = _concat_payload(draft.content, null_when_empty=True)
        message["refusal"] = _concat_payload(draft.refusal, null_when_empty=True)
        if draft.reasoning_content.pieces:
            message["reasoning_content"] = "".join(draft.reasoning_content.pieces)
        if draft.function_call.seen:
            function_call: dict[str, Any] = {}
            if draft.function_call.name.value is not None:
                function_call["name"] = draft.function_call.name.value
            function_call["arguments"] = "".join(draft.function_call.arguments.pieces)
            for key, value in draft.function_call.unknown.items():
                function_call[key] = thaw_json(value)
            message["function_call"] = function_call
        if draft.tools:
            message["tool_calls"] = [self._tool_payload(draft.tools[index]) for index in sorted(draft.tools)]
        for key, value in draft.message_unknown.items():
            message[key] = thaw_json(value)

        choice: dict[str, Any] = {
            "index": draft.index,
            "message": message,
            "finish_reason": draft.finish_reason.value,
        }
        if draft.logprobs.seen:
            choice["logprobs"] = self._logprobs_payload(draft.logprobs)
        for key, value in draft.unknown.items():
            if key == "message":
                raise ChatCompletionUnassemblable(
                    "unknown choice message field conflicts with projected message",
                    field_path=f"choices[{draft.index}].message",
                )
            choice[key] = thaw_json(value)
        return choice

    def _tool_payload(self, draft: _ToolDraft) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if draft.id.value is not None:
            payload["id"] = draft.id.value
        if draft.type.value is not None:
            payload["type"] = draft.type.value
        function: dict[str, Any] = {}
        if draft.name.value is not None:
            function["name"] = draft.name.value
        function["arguments"] = "".join(draft.arguments.pieces)
        for key, value in draft.function_unknown.items():
            function[key] = thaw_json(value)
        payload["function"] = function
        for key, value in draft.unknown.items():
            payload[key] = thaw_json(value)
        return payload

    def _logprobs_payload(self, draft: _LogprobsDraft) -> Any:
        if draft.null_seen and not draft.object_seen:
            return None
        payload: dict[str, Any] = {}
        for key, source in (("content", draft.content), ("refusal", draft.refusal)):
            if source.array_seen:
                payload[key] = [thaw_json(value) for value in source.values]
            elif source.null_seen:
                payload[key] = None
        for key, value in draft.unknown.items():
            payload[key] = thaw_json(value)
        return payload

    def _choice_snapshot(self, draft: _ChoiceDraft) -> ChatChoiceSnapshot:
        return ChatChoiceSnapshot(
            index=draft.index,
            finish_reason=_first_string_observation(draft.finish_reason),
            reasoning_content=_concat_observation(draft.reasoning_content),
            tool_calls=tuple(self._tool_snapshot(draft.tools[index]) for index in sorted(draft.tools)),
            choice_unknown=_frozen_object(draft.unknown),
            message_unknown=_frozen_object(draft.message_unknown),
        )

    def _tool_snapshot(self, draft: _ToolDraft) -> ChatToolCallSnapshot:
        return ChatToolCallSnapshot(
            index=draft.index,
            id=_first_string_observation(draft.id),
            type=_first_string_observation(draft.type),
            name=_first_string_observation(draft.name),
            arguments=_concat_observation(draft.arguments),
            tool_unknown=_frozen_object(draft.unknown),
            function_unknown=_frozen_object(draft.function_unknown),
        )

    def _retain_unattributed(
        self,
        frame: RawSseFrame,
        field_path: str,
        value: JsonObservation,
    ) -> None:
        self._unattributed.append(
            ChatUnattributedFact(
                frame_ordinal=frame.ordinal,
                start=frame.start,
                end=frame.end,
                field_path=field_path,
                value=value,
            )
        )

    def _mark_unassemblable(self, code: str, field_path: str, detail: str | None = None) -> None:
        issue = ObservationIssue(code=code, field_path=field_path, detail=detail)
        self._issues.append(issue)
        self._unassemblable.append(issue)

    def _issue(self, code: str, field_path: str, detail: str | None = None) -> None:
        self._issues.append(ObservationIssue(code=code, field_path=field_path, detail=detail))

    def _held_bytes(self) -> int:
        total = _frozen_mapping_size(self._identity)
        if self._object_seen:
            total += len(b"object") + len(b"chat.completion.chunk")
        total += _frozen_mapping_size(self._last_explicit)
        total += _frozen_mapping_size(self._top_unknown)
        total += _usage_state_size(self._usage_value, self._usage)
        if self._stream_error.value is not None:
            total += len(b"stream_error") + _frozen_size(self._stream_error.value)
        total += sum(_utf8_size(value) for value in self._error_values)
        if self._error_retry_reason is not None:
            total += _utf8_size(self._error_retry_reason.value)
        if self._semantic_end_offset is not None:
            total += len(str(self._semantic_end_offset))
        total += sum(_unattributed_size(fact) for fact in self._unattributed)
        total += sum(_choice_held_size(choice) for choice in self._choices.values())
        total += sum(_issue_size(issue) for issue in self._issues)
        return total


def _usage_state_size(
    projection: FrozenJsonObject | None,
    observation: UsageObservation | None,
) -> int:
    total = 0
    if projection is not None:
        total += len(b"usage") + _frozen_size(projection)
    if observation is not None:
        if observation.raw.value is not None and observation.raw.value is not projection:
            total += len(b"usage") + _frozen_size(observation.raw.value)
        total += sum(_issue_size(issue) for issue in observation.issues)
    return total


def _unattributed_size(fact: ChatUnattributedFact) -> int:
    total = _utf8_size(fact.field_path)
    total += len(str(fact.frame_ordinal)) + len(str(fact.start)) + len(str(fact.end))
    if fact.value.value is not None:
        total += _frozen_size(fact.value.value)
    return total


def _choice_held_size(choice: _ChoiceDraft) -> int:
    total = len(b"index") + len(repr(choice.index))
    total += _first_string_field_size("role", choice.role)
    total += _concat_field_size("content", choice.content)
    total += _concat_field_size("refusal", choice.refusal)
    total += _concat_field_size("reasoning_content", choice.reasoning_content)
    total += _first_string_field_size("finish_reason", choice.finish_reason)
    if choice.function_call.seen:
        total += len(b"function_call")
    total += _first_string_field_size("name", choice.function_call.name)
    total += _concat_field_size("arguments", choice.function_call.arguments)
    total += _frozen_mapping_size(choice.function_call.unknown)
    total += _frozen_mapping_size(choice.unknown)
    total += _frozen_mapping_size(choice.message_unknown)
    if choice.logprobs.seen:
        total += len(b"logprobs")
    if choice.logprobs.content.seen:
        total += len(b"content")
    if choice.logprobs.refusal.seen:
        total += len(b"refusal")
    total += sum(_frozen_size(value) for value in choice.logprobs.content.values)
    total += sum(_frozen_size(value) for value in choice.logprobs.refusal.values)
    total += _frozen_mapping_size(choice.logprobs.unknown)
    total += sum(_tool_held_size(tool) for tool in choice.tools.values())
    return total


def _tool_held_size(tool: _ToolDraft) -> int:
    total = len(b"index") + len(repr(tool.index))
    total += _first_string_field_size("id", tool.id)
    total += _first_string_field_size("type", tool.type)
    total += _first_string_field_size("name", tool.name)
    total += _concat_field_size("arguments", tool.arguments)
    total += _frozen_mapping_size(tool.unknown)
    total += _frozen_mapping_size(tool.function_unknown)
    return total


def _valid_index(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _frozen_object(values: Mapping[str, FrozenJson]) -> FrozenJsonObject:
    return FrozenJsonObject(items=tuple(values.items()))


def _same_frozen_json(left: FrozenJson, right: FrozenJson) -> bool:
    if isinstance(left, FrozenJsonObject):
        if not isinstance(right, FrozenJsonObject) or len(left.items) != len(right.items):
            return False
        right_items = dict(right.items)
        return all(
            key in right_items and _same_frozen_json(value, right_items[key])
            for key, value in left.items
        )
    if isinstance(left, FrozenJsonArray):
        return isinstance(right, FrozenJsonArray) and len(left.items) == len(right.items) and all(
            _same_frozen_json(left_value, right_value)
            for left_value, right_value in zip(left.items, right.items, strict=True)
        )
    if isinstance(right, (FrozenJsonObject, FrozenJsonArray)):
        return False
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _first_string_observation(draft: _FirstString) -> JsonObservation:
    if draft.invalid:
        return JsonObservation(availability=JsonAvailability.UNREADABLE)
    if draft.value is not None:
        return JsonObservation(availability=JsonAvailability.OBSERVED, value=draft.value)
    if draft.null_seen:
        return JsonObservation(availability=JsonAvailability.EXPLICIT_NULL)
    return JsonObservation(availability=JsonAvailability.ABSENT)


def _concat_observation(draft: _ConcatString) -> JsonObservation:
    if draft.invalid:
        return JsonObservation(availability=JsonAvailability.UNREADABLE)
    if draft.pieces:
        return JsonObservation(
            availability=JsonAvailability.OBSERVED,
            value="".join(draft.pieces),
        )
    if draft.null_seen:
        return JsonObservation(availability=JsonAvailability.EXPLICIT_NULL)
    if draft.seen:
        return JsonObservation(availability=JsonAvailability.OBSERVED, value="")
    return JsonObservation(availability=JsonAvailability.ABSENT)


def _json_observation_size(observation: JsonObservation) -> int:
    total = _utf8_size(observation.availability.value)
    if observation.value is not None:
        total += _frozen_size(observation.value)
    return total


def _first_string_observation_size(draft: _FirstString) -> int:
    if draft.invalid:
        return _utf8_size(JsonAvailability.UNREADABLE.value)
    if draft.value is not None:
        return _utf8_size(JsonAvailability.OBSERVED.value) + _utf8_size(draft.value)
    if draft.null_seen:
        return _utf8_size(JsonAvailability.EXPLICIT_NULL.value)
    return _utf8_size(JsonAvailability.ABSENT.value)


def _concat_observation_size(draft: _ConcatString) -> int:
    if draft.invalid:
        return _utf8_size(JsonAvailability.UNREADABLE.value)
    if draft.pieces:
        return _utf8_size(JsonAvailability.OBSERVED.value) + _concat_size(draft)
    if draft.null_seen:
        return _utf8_size(JsonAvailability.EXPLICIT_NULL.value)
    if draft.seen:
        return _utf8_size(JsonAvailability.OBSERVED.value)
    return _utf8_size(JsonAvailability.ABSENT.value)


def _usage_observation_size(usage: UsageObservation) -> int:
    total = _json_observation_size(usage.raw)
    total += sum(
        len(str(value))
        for value in (
            usage.normalized.input_tokens,
            usage.normalized.cache_read_input_tokens,
            usage.normalized.cache_creation_input_tokens,
            usage.normalized.output_tokens,
        )
        if value is not None
    )
    if usage.exact is not None:
        total += sum(
            len(str(value))
            for value in (
                usage.exact.upstream_input_tokens,
                usage.exact.input_tokens,
                usage.exact.cache_read_input_tokens,
                usage.exact.cache_creation_input_tokens,
                usage.exact.output_tokens,
                usage.exact.reasoning_tokens,
                usage.exact.computed_total_tokens,
                usage.exact.upstream_total_tokens,
            )
            if value is not None
        )
        total += _frozen_size(usage.exact.input_tokens_details)
        total += _frozen_size(usage.exact.output_tokens_details)
        total += 4 if usage.exact.inconsistent else 5
    total += sum(_issue_size(issue) for issue in usage.issues)
    return total


def _concat_payload(draft: _ConcatString, *, null_when_empty: bool) -> str | None:
    if draft.pieces:
        return "".join(draft.pieces)
    return None if null_when_empty else ""


def _utf8_size(value: str) -> int:
    total = 0
    for character in value:
        codepoint = ord(character)
        if codepoint <= 0x7F:
            total += 1
        elif codepoint <= 0x7FF:
            total += 2
        elif codepoint <= 0xFFFF:
            total += 3
        else:
            total += 4
    return total


def _frozen_size(value: FrozenJson) -> int:
    if isinstance(value, FrozenJsonObject):
        return sum(_utf8_size(key) + _frozen_size(nested) for key, nested in value.items)
    if isinstance(value, FrozenJsonArray):
        return sum(_frozen_size(nested) for nested in value.items)
    if isinstance(value, str):
        return _utf8_size(value)
    if value is None:
        return 4
    if isinstance(value, bool):
        return 4 if value else 5
    return len(str(value))


def _frozen_mapping_size(values: Mapping[str, FrozenJson]) -> int:
    return sum(_utf8_size(key) + _frozen_size(value) for key, value in values.items())


def _issue_size(issue: ObservationIssue) -> int:
    return (
        _utf8_size(issue.code)
        + _utf8_size(issue.field_path or "")
        + _utf8_size(issue.detail or "")
    )


def _first_string_size(draft: _FirstString) -> int:
    return _utf8_size(draft.value) if draft.value is not None else 0


def _first_string_field_size(key: str, draft: _FirstString) -> int:
    retained = draft.value is not None or draft.null_seen or draft.invalid
    return (_utf8_size(key) if retained else 0) + _first_string_size(draft)


def _concat_size(draft: _ConcatString) -> int:
    return sum(_utf8_size(piece) for piece in draft.pieces)


def _concat_field_size(key: str, draft: _ConcatString) -> int:
    return (_utf8_size(key) if draft.seen else 0) + _concat_size(draft)


class _ReservedJsonWriter:
    def __init__(self, size: int) -> None:
        self._buffer = bytearray(size)
        self._position = 0

    def write(self, value: bytes) -> None:
        end = self._position + len(value)
        if end > len(self._buffer):
            raise AssertionError("projection exceeded its reservation")
        self._buffer[self._position : end] = value
        self._position = end

    def finish(self) -> bytes:
        if self._position != len(self._buffer):
            raise AssertionError("projection used less than its reservation")
        return bytes(self._buffer)


def _encode_json(value: object) -> bytes:
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return "".join(encoder.iterencode(value)).encode()


def _iter_json_string(value: str) -> Iterator[bytes]:
    yield b'"'
    escapes = {
        '"': b'\\"',
        "\\": b"\\\\",
        "\b": b"\\b",
        "\f": b"\\f",
        "\n": b"\\n",
        "\r": b"\\r",
        "\t": b"\\t",
    }
    for character in value:
        escaped = escapes.get(character)
        if escaped is not None:
            yield escaped
        elif ord(character) < 0x20:
            yield f"\\u{ord(character):04x}".encode()
        else:
            yield character.encode()
    yield b'"'


def _iter_joined_json_string(pieces: Iterable[str]) -> Iterator[bytes]:
    yield b'"'
    for piece in pieces:
        for chunk in _iter_json_string(piece):
            if chunk != b'"':
                yield chunk
    yield b'"'


def _iter_json_scalar(value: bool | int | float | None) -> Iterator[bytes]:
    yield _encode_json(value)


def _iter_frozen_json(value: FrozenJson) -> Iterator[bytes]:
    if isinstance(value, FrozenJsonObject):
        yield from _iter_json_object(
            (key, _iter_frozen_json(nested)) for key, nested in value.items
        )
        return
    if isinstance(value, FrozenJsonArray):
        yield from _iter_json_array(_iter_frozen_json(nested) for nested in value.items)
        return
    if isinstance(value, str):
        yield from _iter_json_string(value)
        return
    yield from _iter_json_scalar(value)


def _iter_json_object(
    fields: Iterable[tuple[str, Iterable[bytes]]],
) -> Iterator[bytes]:
    yield b"{"
    for index, (key, value_chunks) in enumerate(fields):
        if index:
            yield b","
        yield from _iter_json_string(key)
        yield b":"
        yield from value_chunks
    yield b"}"


def _iter_json_array(values: Iterable[Iterable[bytes]]) -> Iterator[bytes]:
    yield b"["
    for index, value_chunks in enumerate(values):
        if index:
            yield b","
        yield from value_chunks
    yield b"]"


def _iter_concat_json(draft: _ConcatString, *, null_when_empty: bool) -> Iterator[bytes]:
    if draft.pieces:
        yield from _iter_joined_json_string(draft.pieces)
    elif null_when_empty:
        yield b"null"
    else:
        yield b'""'


def _json_string_content_size(value: str) -> int:
    total = 0
    for character in value:
        codepoint = ord(character)
        if character in {'"', "\\", "\b", "\f", "\n", "\r", "\t"}:
            total += 2
        elif codepoint < 0x20:
            total += 6
        else:
            total += _utf8_size(character)
    return total


def _json_string_size(value: str) -> int:
    return 2 + _json_string_content_size(value)


def _joined_string_wire_size(pieces: Iterable[str]) -> int:
    return 2 + sum(_json_string_content_size(piece) for piece in pieces)


def _concat_wire_size(draft: _ConcatString, *, null_when_empty: bool) -> int:
    if draft.pieces:
        return _joined_string_wire_size(draft.pieces)
    return 4 if null_when_empty else 2


def _json_scalar_size(value: bool | int | float | None) -> int:
    if value is None:
        return 4
    if isinstance(value, bool):
        return 4 if value else 5
    if isinstance(value, int):
        return len(str(value))
    return len(_encode_json(value))


def _frozen_json_wire_size(value: FrozenJson) -> int:
    if isinstance(value, FrozenJsonObject):
        return _json_object_size(
            (key, _frozen_json_wire_size(nested)) for key, nested in value.items
        )
    if isinstance(value, FrozenJsonArray):
        return _json_array_size(_frozen_json_wire_size(nested) for nested in value.items)
    if isinstance(value, str):
        return _json_string_size(value)
    return _json_scalar_size(value)


def _json_object_size(fields: Iterable[tuple[str, int]]) -> int:
    total = 2
    for index, (key, value_size) in enumerate(fields):
        if index:
            total += 1
        total += _json_string_size(key) + 1 + value_size
    return total


def _json_array_size(value_sizes: Iterable[int]) -> int:
    total = 2
    for index, value_size in enumerate(value_sizes):
        if index:
            total += 1
        total += value_size
    return total


def _usage_observation(
    raw: Mapping[str, FrozenJson],
    frozen: FrozenJsonObject,
    *,
    ordinal: int,
) -> UsageObservation:
    issues = list[ObservationIssue]()
    prefix = f"frame[{ordinal}].usage"
    prompt_tokens = _usage_integer(raw, "prompt_tokens", issues, prefix=prefix)
    completion_tokens = _usage_integer(raw, "completion_tokens", issues, prefix=prefix)
    total_tokens = _usage_integer(raw, "total_tokens", issues, prefix=prefix)
    prompt_details = _usage_details(raw, "prompt_tokens_details", issues, prefix=prefix)
    completion_details = _usage_details(
        raw,
        "completion_tokens_details",
        issues,
        prefix=prefix,
    )
    cached_tokens = _usage_integer(
        prompt_details,
        "cached_tokens",
        issues,
        prefix=f"{prefix}.prompt_tokens_details",
    )
    reasoning_tokens = _usage_integer(
        completion_details,
        "reasoning_tokens",
        issues,
        prefix=f"{prefix}.completion_tokens_details",
    )
    fresh_tokens = prompt_tokens
    inconsistent = False
    if prompt_tokens is not None and cached_tokens is not None:
        fresh_tokens = prompt_tokens - cached_tokens
        inconsistent = fresh_tokens < 0
    computed_total = None
    if prompt_tokens is not None and completion_tokens is not None:
        computed_total = prompt_tokens + completion_tokens
        inconsistent = inconsistent or (
            total_tokens is not None and total_tokens != computed_total
        )
    if inconsistent:
        issues.append(
            ObservationIssue(
                code="usage_inconsistent",
                field_path=f"{prefix}.total_tokens",
            )
        )
    frozen_usage_fields = dict(frozen.items)
    raw_input_details = frozen_usage_fields.get("prompt_tokens_details")
    raw_output_details = frozen_usage_fields.get("completion_tokens_details")
    frozen_input_details = (
        raw_input_details
        if isinstance(raw_input_details, FrozenJsonObject)
        else FrozenJsonObject(items=())
    )
    frozen_output_details = (
        raw_output_details
        if isinstance(raw_output_details, FrozenJsonObject)
        else FrozenJsonObject(items=())
    )
    exact = ExactUsage(
        upstream_input_tokens=prompt_tokens,
        input_tokens=fresh_tokens,
        cache_read_input_tokens=cached_tokens,
        cache_creation_input_tokens=0 if prompt_tokens is not None else None,
        output_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        computed_total_tokens=computed_total,
        upstream_total_tokens=total_tokens,
        input_tokens_details=frozen_input_details,
        output_tokens_details=frozen_output_details,
        inconsistent=inconsistent,
    )
    return UsageObservation(
        normalized=NormalizedUsage(
            input_tokens=fresh_tokens,
            cache_read_input_tokens=cached_tokens,
            cache_creation_input_tokens=0 if prompt_tokens is not None else None,
            output_tokens=completion_tokens,
        ),
        raw=JsonObservation(availability=JsonAvailability.OBSERVED, value=frozen),
        exact=exact,
        issues=tuple(issues),
    )


def _usage_details(
    raw: Mapping[str, FrozenJson],
    key: str,
    issues: list[ObservationIssue],
    *,
    prefix: str,
) -> Mapping[str, FrozenJson]:
    if key not in raw or raw[key] is None:
        return dict[str, FrozenJson]()
    value = raw[key]
    if isinstance(value, FrozenJsonObject):
        return dict(value.items)
    issues.append(
        ObservationIssue(
            code="chat_usage_detail_invalid",
            field_path=f"{prefix}.{key}",
        )
    )
    return dict[str, FrozenJson]()


def _usage_integer(
    raw: Mapping[str, FrozenJson],
    key: str,
    issues: list[ObservationIssue],
    *,
    prefix: str = "usage",
) -> int | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    issues.append(ObservationIssue(code="chat_usage_value_invalid", field_path=f"{prefix}.{key}"))
    return None


def _observation_from_value(value: FrozenJson) -> JsonObservation:
    if value is None:
        return JsonObservation(availability=JsonAvailability.EXPLICIT_NULL)
    return JsonObservation(
        availability=JsonAvailability.OBSERVED,
        value=value,
    )


__all__ = [
    "ChatAttemptSnapshot",
    "ChatAttemptState",
    "ChatChoiceSnapshot",
    "ChatCompletionUnassemblable",
    "ChatToolCallSnapshot",
    "ChatUnattributedFact",
    "MaterializationReservation",
]
