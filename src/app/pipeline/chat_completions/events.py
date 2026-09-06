from __future__ import annotations

import codecs
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from app.pipeline.delivery.sse_source import RawSseFrame, SseEvent, parse_frame
from app.pipeline.response_observation import (
    FrozenJsonError,
    JsonAvailability,
    JsonObservation,
    ObservationIssue,
    freeze_json,
)
from app.pipeline.retry import RetryReason


class ChatEventKind(StrEnum):
    DONE = "done"
    CHUNK = "chunk"
    ERROR = "error"
    UNKNOWN = "unknown"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class ChatEventFacts:
    kind: ChatEventKind
    frame: RawSseFrame
    value: JsonObservation
    error_values: tuple[str, ...] = ()
    retry_reason: RetryReason | None = None
    issue: ObservationIssue | None = None


_TRANSIENT_ERROR_CLASSES = {
    "server_error": "server_error",
    "rate_limited": "rate_limit",
    "rate_limit_error": "rate_limit",
    "rate_limit_exceeded": "rate_limit",
    "upstream_rate_limited": "rate_limit",
}
_ABSENT = JsonObservation(availability=JsonAvailability.ABSENT)
_NOT_APPLICABLE = JsonObservation(availability=JsonAvailability.NOT_APPLICABLE)
_UNREADABLE = JsonObservation(availability=JsonAvailability.UNREADABLE)


class ChatEventReader:
    """Decode one raw Chat Completions SSE frame into immutable facts."""

    def read(self, frame: RawSseFrame) -> ChatEventFacts:
        try:
            codecs.decode(frame.body, "utf-8", errors="strict")
        except UnicodeDecodeError as error:
            return ChatEventFacts(
                kind=ChatEventKind.UNREADABLE,
                frame=frame,
                value=_UNREADABLE,
                issue=ObservationIssue(
                    code="chat_event_invalid_utf8",
                    field_path=f"frame[{frame.ordinal}]",
                    detail=str(error),
                ),
            )
        event = parse_frame(frame.body)
        if event is None:
            return ChatEventFacts(
                kind=ChatEventKind.UNKNOWN,
                frame=frame,
                value=_ABSENT,
                issue=ObservationIssue(
                    code="chat_event_without_data",
                    field_path=f"frame[{frame.ordinal}]",
                ),
            )
        return self._read_event(event, frame)

    def read_sse_event(self, event: SseEvent, *, ordinal: int = 0) -> ChatEventFacts:
        """Decode an already parsed event for the translated legacy assembler."""
        frame = RawSseFrame(
            raw=b"",
            body_end=0,
            start=0,
            end=0,
            ordinal=ordinal,
            terminated=True,
        )
        return self._read_event(event, frame)

    def _read_event(self, event: SseEvent, frame: RawSseFrame) -> ChatEventFacts:
        if event.data.strip() == "[DONE]" and event.event != "error":
            return ChatEventFacts(
                kind=ChatEventKind.DONE,
                frame=frame,
                value=_NOT_APPLICABLE,
            )

        try:
            loaded: object = json.loads(event.data, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError) as error:
            kind = ChatEventKind.ERROR if event.event == "error" else ChatEventKind.UNREADABLE
            code = "chat_error_malformed_json" if kind is ChatEventKind.ERROR else "chat_event_malformed_json"
            return ChatEventFacts(
                kind=kind,
                frame=frame,
                value=_UNREADABLE,
                issue=ObservationIssue(
                    code=code,
                    field_path=f"frame[{frame.ordinal}].data",
                    detail=str(error),
                ),
            )

        mapping: Mapping[str, Any] | None = (
            cast(Mapping[str, Any], loaded)
            if isinstance(loaded, Mapping)
            else None
        )
        is_nested_error = mapping is not None and "error" in mapping
        is_flat_error = mapping is not None and mapping.get("type") == "error"
        is_error = event.event == "error" or is_nested_error or is_flat_error
        error_values: tuple[str, ...] = ()
        retry_reason: RetryReason | None = None
        classification_issue: ObservationIssue | None = None
        if is_error:
            error_values, retry_reason, classification_issue = _classify_error(
                mapping,
                nested=is_nested_error,
                ordinal=frame.ordinal,
            )

        value, freeze_issue = _freeze_observation(
            cast(object, loaded),
            ordinal=frame.ordinal,
            error=is_error,
        )
        if is_error:
            return ChatEventFacts(
                kind=ChatEventKind.ERROR,
                frame=frame,
                value=value,
                error_values=error_values,
                retry_reason=retry_reason,
                issue=classification_issue or freeze_issue,
            )
        if value.availability is JsonAvailability.UNREADABLE:
            return ChatEventFacts(
                kind=ChatEventKind.UNREADABLE,
                frame=frame,
                value=value,
                issue=freeze_issue,
            )
        if mapping is not None:
            return ChatEventFacts(kind=ChatEventKind.CHUNK, frame=frame, value=value)
        return ChatEventFacts(
            kind=ChatEventKind.UNKNOWN,
            frame=frame,
            value=value,
            issue=ObservationIssue(
                code="chat_event_non_object",
                field_path=f"frame[{frame.ordinal}].data",
            ),
        )


def _classify_error(
    mapping: Mapping[str, Any] | None,
    *,
    nested: bool,
    ordinal: int,
) -> tuple[tuple[str, ...], RetryReason | None, ObservationIssue | None]:
    carrier: Mapping[str, Any] | None = mapping
    malformed = mapping is None
    if nested and mapping is not None:
        raw_error = mapping["error"]
        if isinstance(raw_error, Mapping):
            carrier = cast(Mapping[str, Any], raw_error)
        else:
            carrier = None
            malformed = True

    error_values: list[str] = []
    classes: list[str] = []
    unknown = False
    if carrier is not None:
        for key in ("code", "type"):
            raw = carrier.get(key)
            if key == "type" and not nested and raw == "error":
                continue
            if raw is None or raw == "":
                continue
            if not isinstance(raw, str):
                malformed = True
                continue
            error_values.append(raw)
            classified = _TRANSIENT_ERROR_CLASSES.get(raw)
            if classified is None:
                unknown = True
            else:
                classes.append(classified)

    path = f"frame[{ordinal}].data"
    if malformed:
        issue = ObservationIssue(code="chat_error_malformed", field_path=path)
    elif not error_values:
        issue = ObservationIssue(code="chat_error_code_missing", field_path=path)
    elif unknown:
        issue = ObservationIssue(code="chat_error_code_unknown", field_path=path)
    elif len(set(classes)) != 1:
        issue = ObservationIssue(code="chat_error_code_conflict", field_path=path)
    else:
        return tuple(error_values), RetryReason.SERVER_ERROR, None
    return tuple(error_values), None, issue


def _freeze_observation(
    value: object,
    *,
    ordinal: int,
    error: bool,
) -> tuple[JsonObservation, ObservationIssue | None]:
    if value is None:
        return JsonObservation(availability=JsonAvailability.EXPLICIT_NULL), None
    try:
        _validate_unicode(value)
        frozen = freeze_json(value, path=f"frame[{ordinal}].data")
    except (FrozenJsonError, UnicodeEncodeError) as freeze_error:
        code = "chat_error_value_unreadable" if error else "chat_event_value_unreadable"
        return _UNREADABLE, ObservationIssue(
            code=code,
            field_path=f"frame[{ordinal}].data",
            detail=str(freeze_error),
        )
    return JsonObservation(availability=JsonAvailability.OBSERVED, value=frozen), None


def _validate_unicode(value: object) -> None:
    if isinstance(value, str):
        value.encode("utf-8")
        return
    if isinstance(value, Mapping):
        for key, nested in cast(Mapping[object, object], value).items():
            if isinstance(key, str):
                key.encode("utf-8")
            _validate_unicode(nested)
        return
    if isinstance(value, list):
        for nested in cast(list[object], value):
            _validate_unicode(nested)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r}")


__all__ = [
    "ChatEventFacts",
    "ChatEventKind",
    "ChatEventReader",
]
