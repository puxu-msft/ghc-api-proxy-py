from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from json import loads as load_json_exact
from typing import Any, Protocol, cast

from app.pipeline.response_action import (
    ClientActionObservation,
    classify_responses_client_action,
)
from app.protocols.responses_anthropic import (
    ResponseConversionError,
    ResponseUsageFacts,
    convert_responses_usage,
)
from app.wire_json import JsonScalar, JsonValue


class FrozenJsonError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FrozenJsonObject:
    items: tuple[tuple[str, FrozenJson], ...]


@dataclass(frozen=True, slots=True)
class FrozenJsonArray:
    items: tuple[FrozenJson, ...]


type FrozenJson = JsonScalar | FrozenJsonObject | FrozenJsonArray


class ResponseEvent(Protocol):
    @property
    def event(self) -> str: ...

    @property
    def data(self) -> str: ...


def freeze_json(value: object, *, path: str = "$") -> FrozenJson:
    """Detach one JSON value into recursively immutable, container-tagged data."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        # JSON numbers do not have JavaScript's 53-bit limit. This domain is written by Python's JSON encoder and must preserve provider accounting exactly; the stricter client-wire encoder is a separate boundary in `app.wire_json`.
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FrozenJsonError(f"non-finite float at {path} is not valid JSON")
        return value
    if isinstance(value, Mapping):
        frozen: list[tuple[str, FrozenJson]] = []
        for key, nested in cast(Mapping[object, object], value).items():
            if not isinstance(key, str):
                raise FrozenJsonError(f"object key at {path} must be a string")
            frozen.append((key, freeze_json(nested, path=f"{path}.{key}")))
        return FrozenJsonObject(items=tuple(frozen))
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        return FrozenJsonArray(
            items=tuple(
                freeze_json(nested, path=f"{path}[{index}]")
                for index, nested in enumerate(cast(Sequence[object], value))
            )
        )
    raise FrozenJsonError(f"unsupported JSON value at {path}")


def thaw_json(value: FrozenJson) -> JsonValue:
    """Restore a frozen value at the one boundary that writes ordinary JSON."""
    if isinstance(value, FrozenJsonObject):
        return {key: thaw_json(nested) for key, nested in value.items}
    if isinstance(value, FrozenJsonArray):
        return [thaw_json(nested) for nested in value.items]
    return value


class JsonAvailability(StrEnum):
    OBSERVED = "observed"
    ABSENT = "absent"
    EXPLICIT_NULL = "explicit_null"
    UNREADABLE = "unreadable"
    NOT_APPLICABLE = "not_applicable"


class ResponseAvailability(StrEnum):
    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class ObservationIssue:
    code: str
    field_path: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class JsonObservation:
    availability: JsonAvailability
    value: FrozenJson | None = None


@dataclass(frozen=True, slots=True)
class ProviderErrorSummary:
    type: str | None
    code: str | None
    message: str | None


@dataclass(frozen=True, slots=True)
class NormalizedUsage:
    input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ExactUsage:
    upstream_input_tokens: int | None
    input_tokens: int | None
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    computed_total_tokens: int | None
    upstream_total_tokens: int | None
    input_tokens_details: FrozenJsonObject
    output_tokens_details: FrozenJsonObject
    inconsistent: bool


@dataclass(frozen=True, slots=True)
class UsageObservation:
    normalized: NormalizedUsage
    raw: JsonObservation
    exact: ExactUsage | None
    issues: tuple[ObservationIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class ReasoningObservation:
    summary_items: int = 0
    has_readable_summary: bool = False
    has_encrypted_content: bool = False


@dataclass(frozen=True, slots=True)
class OutputItemSummary:
    output_index: int
    type: str | None
    name: str | None
    status: str | None
    execution: str | None
    call_id: str | None
    reasoning: ReasoningObservation
    client_action: ClientActionObservation


@dataclass(frozen=True, slots=True)
class ResponseObservation:
    availability: ResponseAvailability
    source_protocol: str
    terminal_event_type: str | None
    terminal_seen: bool | None
    status: str | None
    incomplete_reason: str | None
    error: JsonObservation
    error_summary: ProviderErrorSummary | None
    model: str | None
    service_tier: str | None
    output_items: tuple[OutputItemSummary, ...] | None
    usage: UsageObservation | None
    provider_usage: JsonObservation
    tool_usage: JsonObservation
    issues: tuple[ObservationIssue, ...] = ()

    @property
    def provider_failed(self) -> bool:
        return (
            self.terminal_event_type in _FAILURE_TERMINALS
            or self.status in {"failed", "cancelled"}
            or self.error.availability is JsonAvailability.OBSERVED
            or self.error_summary is not None
        )


_NORMAL_TERMINALS = frozenset({"response.completed", "response.incomplete"})
_FAILURE_TERMINALS = frozenset({"response.failed", "response.cancelled", "error"})
_ITEM_EVENTS = frozenset({"response.output_item.added", "response.output_item.done"})


class _ItemSource(IntEnum):
    ADDED = 1
    DONE = 2
    COMPLETE_RESPONSE = 3


@dataclass(frozen=True, slots=True)
class _StringField:
    present: bool
    value: str | None = None


@dataclass(frozen=True, slots=True)
class _EnvironmentField:
    present: bool
    is_mapping: bool = False
    type_present: bool = False
    type_text: str | None = None


@dataclass(frozen=True, slots=True)
class _ItemDraft:
    type: _StringField
    name: _StringField
    status: _StringField
    execution: _StringField
    call_id: _StringField
    environment: _EnvironmentField
    summary_present: bool
    summary_items: int
    has_readable_summary: bool
    encrypted_present: bool
    has_encrypted_content: bool


@dataclass(frozen=True, slots=True)
class _ObservedItem:
    source: _ItemSource
    draft: _ItemDraft


@dataclass(slots=True)
class ResponsesObserver:
    """A side-only view of one Responses upstream attempt.

    Every public mutator contains its own errors. Observation is allowed to become unavailable; it is never allowed to steer delivery or turn a raw passthrough into a protocol implementation ceiling.
    """

    _availability: ResponseAvailability = ResponseAvailability.UNAVAILABLE
    _terminal_event_type: str | None = None
    _terminal_seen: bool | None = None
    _status: str | None = None
    _incomplete_reason: str | None = None
    _error: JsonObservation | None = None
    _error_summary: ProviderErrorSummary | None = None
    _model: str | None = None
    _service_tier: str | None = None
    _items: dict[int, _ObservedItem] | None = None
    _usage: UsageObservation | None = None
    _provider_usage: JsonObservation | None = None
    _tool_usage: JsonObservation | None = None
    _issues: list[ObservationIssue] = field(default_factory=lambda: list[ObservationIssue]())

    def observe_event(self, event: ResponseEvent) -> None:
        try:
            # Provider accounting is an observation boundary, not the client-wire codec. The stdlib decoder preserves JSON integer tokens as arbitrary-precision Python ints; `orjson.loads` converts values beyond 64-bit to float before `freeze_json` can retain them exactly.
            decoded = load_json_exact(event.data)
            if not isinstance(decoded, dict):
                self._issue("event_payload_not_object", "event.data")
                return
            data = cast(dict[str, Any], decoded)
            self._availability = ResponseAvailability.OBSERVED
            if self._terminal_seen is None:
                self._terminal_seen = False
            if event.event in _ITEM_EVENTS:
                self._observe_event_item(event.event, data)
            response = data.get("response")
            if isinstance(response, Mapping):
                terminal = event.event if event.event in _NORMAL_TERMINALS | _FAILURE_TERMINALS else None
                self._observe_response_mapping(
                    cast(Mapping[str, Any], response),
                    envelope=data,
                    terminal_event=terminal,
                    complete_body=terminal is not None,
                )
            elif event.event in _NORMAL_TERMINALS | (_FAILURE_TERMINALS - {"error"}):
                self._terminal_event_type = event.event
                self._terminal_seen = event.event in _NORMAL_TERMINALS
                self._issue("terminal_response_not_object", "response")
            if event.event == "error":
                self._terminal_event_type = event.event
                self._terminal_seen = False
                # CAPI nests `{error:{code,message}}`; the public Responses event is flat `{type,code,message}`. Preserve whichever holder upstream actually used, preferring the nested object when present just as the delivery failure parser does.
                error_value = data.get("error") if "error" in data else data
                self._error = (
                    self._field(data, "error", field_path="error")
                    if "error" in data
                    else self._freeze_value(data, field_path="error")
                )
                self._error_summary = _provider_error_summary(error_value)
        except Exception as error:
            self._issue("event_observation_failed", "event.data", error)

    def observe_response(self, body: Mapping[str, Any]) -> None:
        try:
            self._availability = ResponseAvailability.OBSERVED
            status = _optional_string(body.get("status"))
            terminal_event = (
                {
                    "completed": "response.completed",
                    "incomplete": "response.incomplete",
                    "failed": "response.failed",
                    "cancelled": "response.cancelled",
                }.get(status)
                if status is not None
                else None
            )
            self._terminal_seen = terminal_event in _NORMAL_TERMINALS
            self._observe_response_mapping(
                body,
                envelope=body,
                terminal_event=terminal_event,
                complete_body=True,
            )
        except Exception as error:
            self._availability = ResponseAvailability.UNAVAILABLE
            self._terminal_seen = None
            self._issue("response_observation_failed", "response", error)

    def observe_body_bytes(self, body: bytes) -> None:
        """Observe a buffered provider body carried by an HTTP status error."""
        try:
            decoded = load_json_exact(body)
        except Exception as error:
            self._availability = ResponseAvailability.UNAVAILABLE
            self._terminal_seen = None
            self._issue("response_body_not_json", "response", error)
            return
        if not isinstance(decoded, Mapping):
            self._availability = ResponseAvailability.UNAVAILABLE
            self._terminal_seen = None
            self._issue("response_body_not_object", "response")
            return
        self.observe_response(cast(Mapping[str, Any], decoded))

    def snapshot(self) -> ResponseObservation:
        observed = self._availability is ResponseAvailability.OBSERVED
        issues = tuple(self._issues)
        if self._availability is ResponseAvailability.UNAVAILABLE and not issues:
            issues = (
                ObservationIssue(
                    code="provider_body_not_observed",
                    field_path="response",
                ),
            )
        return ResponseObservation(
            availability=self._availability,
            source_protocol="openai-responses",
            terminal_event_type=self._terminal_event_type,
            terminal_seen=self._terminal_seen if observed else None,
            status=self._status,
            incomplete_reason=self._incomplete_reason,
            error=self._error or _missing_json(observed),
            error_summary=self._error_summary,
            model=self._model,
            service_tier=self._service_tier,
            output_items=(
                tuple(
                    _summarize_item(output_index, observed.draft)
                    for output_index, observed in sorted(self._items.items())
                )
                if self._items is not None
                else None
            ),
            usage=(
                self._usage
                if self._usage is not None
                else (_absent_usage() if observed else None)
            ),
            provider_usage=self._provider_usage or _missing_json(observed),
            tool_usage=self._tool_usage or _missing_json(observed),
            issues=issues,
        )

    def _observe_event_item(self, event_type: str, data: Mapping[str, Any]) -> None:
        output_index = data.get("output_index")
        item = data.get("item")
        if (
            not isinstance(output_index, int)
            or isinstance(output_index, bool)
            or output_index < 0
        ):
            self._issue("invalid_output_index", "output_index")
            return
        if not isinstance(item, Mapping):
            self._issue("output_item_not_object", "item")
            return
        source = (
            _ItemSource.DONE
            if event_type == "response.output_item.done"
            else _ItemSource.ADDED
        )
        self._observe_item(
            output_index,
            cast(Mapping[str, Any], item),
            source=source,
        )

    def _observe_response_mapping(
        self,
        response: Mapping[str, Any],
        *,
        envelope: Mapping[str, Any],
        terminal_event: str | None,
        complete_body: bool,
    ) -> None:
        self._availability = ResponseAvailability.OBSERVED
        if self._terminal_seen is None:
            self._terminal_seen = False
        if terminal_event is not None:
            self._terminal_event_type = terminal_event
            self._terminal_seen = terminal_event in _NORMAL_TERMINALS
        if terminal_event is not None:
            # A terminal without a status does not inherit the earlier `in_progress` snapshot. The event name remains the authoritative failure/completion fact and the raw terminal status stays absent.
            self._status = (
                _optional_string(response.get("status"))
                if "status" in response
                else None
            )
        else:
            self._status = _optional_string(response.get("status")) or self._status
        self._model = _optional_string(response.get("model")) or self._model
        self._service_tier = _optional_string(response.get("service_tier")) or self._service_tier

        details = response.get("incomplete_details")
        if isinstance(details, Mapping):
            detail_mapping = cast(Mapping[str, Any], details)
            self._incomplete_reason = _optional_string(detail_mapping.get("reason"))
        elif details is None and "incomplete_details" in response:
            self._incomplete_reason = None

        if "error" in response:
            error_value = response.get("error")
            self._error = self._field(response, "error", field_path="response.error")
            self._error_summary = _provider_error_summary(error_value)
        if "copilot_usage" in envelope:
            self._provider_usage = self._field(
                envelope,
                "copilot_usage",
                field_path="copilot_usage",
            )
        if "tool_usage" in response:
            self._tool_usage = self._field(response, "tool_usage", field_path="response.tool_usage")
        if "usage" in response:
            self._usage = self._observe_usage(response.get("usage"))
        elif complete_body:
            self._usage = _absent_usage()

        output = response.get("output")
        if isinstance(output, Sequence) and not isinstance(output, (str, bytes, bytearray)):
            if self._items is None:
                self._items = {}
            for output_index, raw_item in enumerate(cast(Sequence[object], output)):
                if isinstance(raw_item, Mapping):
                    self._observe_item(
                        output_index,
                        cast(Mapping[str, Any], raw_item),
                        source=(
                            _ItemSource.COMPLETE_RESPONSE
                            if complete_body
                            else _ItemSource.ADDED
                        ),
                    )
                else:
                    self._issue("output_item_not_object", f"response.output[{output_index}]")
        elif "output" in response and output is not None:
            self._issue("output_not_array", "response.output")

    def _observe_item(
        self,
        output_index: int,
        item: Mapping[str, Any],
        *,
        source: _ItemSource,
    ) -> None:
        if self._items is None:
            self._items = {}
        existing = self._items.get(output_index)
        if existing is not None and source < existing.source:
            # A late partial event cannot weaken the full item carried by the terminal response.
            return
        draft = _draft_item(item)
        if existing is not None:
            draft = _merge_item_drafts(existing.draft, draft)
        self._items[output_index] = _ObservedItem(source=source, draft=draft)

    def _observe_usage(self, value: object) -> UsageObservation:
        raw = self._freeze_value(value, field_path="response.usage")
        if value is None:
            return UsageObservation(
                normalized=NormalizedUsage(),
                raw=raw,
                exact=None,
            )
        try:
            converted = convert_responses_usage(value)
        except ResponseConversionError as error:
            return UsageObservation(
                normalized=NormalizedUsage(),
                raw=raw,
                exact=None,
                issues=(
                    ObservationIssue(
                        code=error.code,
                        field_path=error.field_path,
                        detail=str(error),
                    ),
                ),
            )
        wire = converted.wire.model_dump()
        exact = _exact_usage(converted.exact)
        return UsageObservation(
            normalized=NormalizedUsage(
                input_tokens=(exact.input_tokens if exact is not None else None),
                cache_read_input_tokens=(
                    exact.cache_read_input_tokens if exact is not None else None
                ),
                cache_creation_input_tokens=(
                    exact.cache_creation_input_tokens if exact is not None else None
                ),
                output_tokens=_integer_or_none(wire.get("output_tokens")),
            ),
            raw=raw,
            exact=exact,
            issues=tuple(
                ObservationIssue(code=fact.code, field_path=fact.field_path)
                for fact in converted.facts
            ),
        )

    def _field(
        self,
        mapping: Mapping[str, Any],
        key: str,
        *,
        field_path: str,
    ) -> JsonObservation:
        if key not in mapping:
            return JsonObservation(availability=JsonAvailability.ABSENT)
        value = mapping[key]
        if value is None:
            return JsonObservation(availability=JsonAvailability.EXPLICIT_NULL)
        return self._freeze_value(value, field_path=field_path)

    def _freeze_value(self, value: object, *, field_path: str) -> JsonObservation:
        if value is None:
            return JsonObservation(availability=JsonAvailability.EXPLICIT_NULL)
        try:
            return JsonObservation(
                availability=JsonAvailability.OBSERVED,
                value=freeze_json(value, path=field_path),
            )
        except FrozenJsonError as error:
            self._issue("json_value_unreadable", field_path, error)
            return JsonObservation(availability=JsonAvailability.UNREADABLE)

    def _issue(
        self,
        code: str,
        field_path: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        self._issues.append(
            ObservationIssue(
                code=code,
                field_path=field_path,
                detail=str(error)[:500] if error is not None else None,
            )
        )


def _absent_usage() -> UsageObservation:
    return UsageObservation(
        normalized=NormalizedUsage(),
        raw=JsonObservation(availability=JsonAvailability.ABSENT),
        exact=None,
    )


def _string_field(item: Mapping[str, Any], key: str) -> _StringField:
    if key not in item:
        return _StringField(present=False)
    return _StringField(present=True, value=_optional_string(item[key]))


def _environment_field(item: Mapping[str, Any]) -> _EnvironmentField:
    if "environment" not in item:
        return _EnvironmentField(present=False)
    environment = item["environment"]
    if not isinstance(environment, Mapping):
        return _EnvironmentField(present=True, is_mapping=False)
    environment_mapping = cast(Mapping[str, Any], environment)
    if "type" not in environment_mapping:
        return _EnvironmentField(present=True, is_mapping=True)
    return _EnvironmentField(
        present=True,
        is_mapping=True,
        type_present=True,
        type_text=str(environment_mapping["type"]),
    )


def _draft_item(item: Mapping[str, Any]) -> _ItemDraft:
    summary = item.get("summary")
    summary_present = "summary" in item
    summary_items = (
        len(cast(Sequence[object], summary))
        if isinstance(summary, Sequence) and not isinstance(summary, (str, bytes, bytearray))
        else 0
    )
    readable = False
    if isinstance(summary, Sequence) and not isinstance(summary, (str, bytes, bytearray)):
        for part in cast(Sequence[object], summary):
            if not isinstance(part, Mapping):
                continue
            part_mapping = cast(Mapping[str, Any], part)
            if _optional_string(part_mapping.get("text")):
                readable = True
                break
    encrypted_present = "encrypted_content" in item
    encrypted = _optional_string(item.get("encrypted_content"))
    return _ItemDraft(
        type=_string_field(item, "type"),
        name=_string_field(item, "name"),
        status=_string_field(item, "status"),
        execution=_string_field(item, "execution"),
        call_id=_string_field(item, "call_id"),
        environment=_environment_field(item),
        summary_present=summary_present,
        summary_items=summary_items,
        has_readable_summary=readable,
        encrypted_present=encrypted_present,
        has_encrypted_content=bool(encrypted),
    )


def _merge_string_field(older: _StringField, newer: _StringField) -> _StringField:
    return newer if newer.present else older


def _merge_environment_field(
    older: _EnvironmentField,
    newer: _EnvironmentField,
) -> _EnvironmentField:
    return newer if newer.present else older


def _merge_item_drafts(older: _ItemDraft, newer: _ItemDraft) -> _ItemDraft:
    return _ItemDraft(
        type=_merge_string_field(older.type, newer.type),
        name=_merge_string_field(older.name, newer.name),
        status=_merge_string_field(older.status, newer.status),
        execution=_merge_string_field(older.execution, newer.execution),
        call_id=_merge_string_field(older.call_id, newer.call_id),
        environment=_merge_environment_field(older.environment, newer.environment),
        summary_present=older.summary_present or newer.summary_present,
        summary_items=(
            newer.summary_items if newer.summary_present else older.summary_items
        ),
        has_readable_summary=(
            newer.has_readable_summary
            if newer.summary_present
            else older.has_readable_summary
        ),
        encrypted_present=older.encrypted_present or newer.encrypted_present,
        has_encrypted_content=(
            newer.has_encrypted_content
            if newer.encrypted_present
            else older.has_encrypted_content
        ),
    )


def _summarize_item(
    output_index: int,
    draft: _ItemDraft,
) -> OutputItemSummary:
    policy_item: dict[str, Any] = {}
    if draft.type.present:
        policy_item["type"] = draft.type.value
    if draft.execution.present:
        policy_item["execution"] = draft.execution.value
    if draft.environment.present:
        if not draft.environment.is_mapping:
            policy_item["environment"] = None
        else:
            environment: dict[str, Any] = {}
            if draft.environment.type_present:
                environment["type"] = draft.environment.type_text
            policy_item["environment"] = environment
    return OutputItemSummary(
        output_index=output_index,
        type=draft.type.value,
        name=draft.name.value,
        status=draft.status.value,
        execution=draft.execution.value,
        call_id=draft.call_id.value,
        reasoning=ReasoningObservation(
            summary_items=draft.summary_items,
            has_readable_summary=draft.has_readable_summary,
            has_encrypted_content=draft.has_encrypted_content,
        ),
        client_action=classify_responses_client_action(policy_item),
    )


def _provider_error_summary(value: object) -> ProviderErrorSummary | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        error = cast(Mapping[str, object], value)
        return ProviderErrorSummary(
            type=_bounded_string(error.get("type")),
            code=_bounded_string(error.get("code")),
            message=_bounded_line(error.get("message")),
        )
    return ProviderErrorSummary(
        type=None,
        code=None,
        message=_bounded_line(value),
    )


def _bounded_string(value: object, *, limit: int = 240) -> str | None:
    if not isinstance(value, str):
        return None
    if len(value) <= limit:
        return value
    return f"{value[:limit]}… (+{len(value) - limit} more chars)"


def _bounded_line(value: object, *, limit: int = 240) -> str | None:
    if not isinstance(value, str):
        return None
    flattened = " ".join(value.split())
    if len(flattened) <= limit:
        return flattened
    return f"{flattened[:limit]}… (+{len(flattened) - limit} more chars)"


def _missing_json(observed: bool) -> JsonObservation:
    return JsonObservation(
        availability=(JsonAvailability.ABSENT if observed else JsonAvailability.NOT_APPLICABLE)
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _integer_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _exact_usage(value: ResponseUsageFacts | None) -> ExactUsage | None:
    if value is None:
        return None
    input_details = freeze_json(dict(value.input_tokens_details), path="usage.input_tokens_details")
    output_details = freeze_json(dict(value.output_tokens_details), path="usage.output_tokens_details")
    if not isinstance(input_details, FrozenJsonObject) or not isinstance(
        output_details, FrozenJsonObject
    ):
        raise FrozenJsonError("usage detail mappings did not freeze as objects")
    return ExactUsage(
        upstream_input_tokens=value.upstream_input_tokens,
        input_tokens=value.input_tokens,
        cache_read_input_tokens=value.cache_read_input_tokens,
        cache_creation_input_tokens=value.cache_creation_input_tokens,
        output_tokens=value.output_tokens,
        reasoning_tokens=value.reasoning_tokens,
        computed_total_tokens=value.total_tokens,
        upstream_total_tokens=value.upstream_total_tokens,
        input_tokens_details=input_details,
        output_tokens_details=output_details,
        inconsistent=value.inconsistent,
    )


__all__ = [
    "ExactUsage",
    "FrozenJson",
    "FrozenJsonArray",
    "FrozenJsonError",
    "FrozenJsonObject",
    "JsonAvailability",
    "JsonObservation",
    "NormalizedUsage",
    "ObservationIssue",
    "OutputItemSummary",
    "ProviderErrorSummary",
    "ReasoningObservation",
    "ResponseAvailability",
    "ResponseEvent",
    "ResponseObservation",
    "ResponsesObserver",
    "UsageObservation",
    "freeze_json",
    "thaw_json",
]
