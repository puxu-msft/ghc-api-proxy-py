"""Independent replay orchestration over captured transport evidence."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import cbor2
import zstandard

from app.observability.raw_capture import iter_raw_capture_records


class ReplayMode(StrEnum):
    WIRE_DIAGNOSTIC = "wire_diagnostic"
    SEMANTIC = "semantic"
    LIVE = "live"


class ReplaySourceSelector(StrEnum):
    CLIENT_REQUEST = "client_request"
    UPSTREAM_ATTEMPT = "upstream_attempt"


class ReplayTargetPolicy(StrEnum):
    ORIGINAL_RESOLVED_TARGET = "original_resolved_target"
    CURRENT_ROUTE = "current_route"


class ReplayError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.not_started = True


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    capture_path: Path | None
    source_entry_id: str
    selector: ReplaySourceSelector
    mode: ReplayMode
    target_policy: ReplayTargetPolicy
    deadline_s: float
    attempt_id: int | None = None
    original_target: str | None = None
    current_target: str | None = None


@dataclass(frozen=True, slots=True)
class ReplayExecution:
    replay_id: str
    request_id: str
    mode: ReplayMode
    target: str | None
    client_request: Mapping[str, Any]
    deadline_at: float


ReplayExecutor = Callable[[ReplayExecution], Awaitable[object]]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    replay_id: str
    request_id: str
    mode: ReplayMode
    selector: ReplaySourceSelector
    source_entry_id: str
    source_capture_ref: str | None
    target_policy: ReplayTargetPolicy
    target: str | None
    started_at: str
    finished_at: str
    outcome: str
    error_code: str | None
    client_actions: tuple[Mapping[str, Any], ...]
    output: Mapping[str, Any] | None
    diagnostic_records: tuple[Mapping[str, Any], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "replay_id": self.replay_id,
            "request_id": self.request_id,
            "replay_mode": self.mode.value,
            "source_entry_id": self.source_entry_id,
            "source_capture_ref": self.source_capture_ref,
            "source_selector": self.selector.value,
            "target_policy": self.target_policy.value,
            "target": self.target,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "client_actions": list(self.client_actions),
            "output": self.output,
            "diagnostic_records": list(self.diagnostic_records),
        }


@dataclass(frozen=True, slots=True)
class _CaptureSource:
    records: tuple[Mapping[str, Any], ...]
    client_request_body: bytes | None
    client_request_complete: bool
    upstream_attempts: Mapping[int, tuple[Mapping[str, Any], ...]]


class ReplayProcess:
    """Run replay outside the main server lifecycle."""

    def __init__(self, *, max_deadline_s: float) -> None:
        if max_deadline_s <= 0:
            raise ValueError("max_deadline_s must be positive")
        self.max_deadline_s = max_deadline_s

    async def run(
        self,
        request: ReplayRequest,
        *,
        executor: ReplayExecutor | None = None,
    ) -> ReplayResult:
        started_at = _timestamp()
        replay_id = str(uuid4())
        request_id = f"replay-{replay_id}"
        target = _target_for(request)
        if request.deadline_s > self.max_deadline_s:
            raise ReplayError(
                "invalid_deadline",
                "replay deadline exceeds the process maximum",
            )
        _validate_request(request)
        source = _read_source(request)
        _validate_source(request, source)
        deadline_at = time.monotonic() + request.deadline_s

        if request.mode is ReplayMode.WIRE_DIAGNOSTIC:
            return ReplayResult(
                replay_id=replay_id,
                request_id=request_id,
                mode=request.mode,
                selector=request.selector,
                source_entry_id=request.source_entry_id,
                source_capture_ref=str(request.capture_path)
                if request.capture_path is not None
                else None,
                target_policy=request.target_policy,
                target=target,
                started_at=started_at,
                finished_at=_timestamp(),
                outcome="completed",
                error_code=None,
                client_actions=(),
                output={"record_count": len(source.records)},
                diagnostic_records=(
                    _selected_attempt_records(source, request.attempt_id)
                    if request.selector is ReplaySourceSelector.UPSTREAM_ATTEMPT
                    else ()
                ),
            )

        if source.client_request_body is None or not source.client_request_complete:
            raise ReplayError(
                "source_content_unavailable",
                "captured client request body is incomplete",
            )
        try:
            client_request = json.loads(source.client_request_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReplayError(
                "source_content_unavailable",
                "captured client request body is not valid JSON",
            ) from error
        if not isinstance(client_request, dict):
            raise ReplayError(
                "source_content_unavailable",
                "captured client request is not a JSON object",
            )
        if target is None:
            raise ReplayError("target_unavailable", "replay target could not be resolved")
        if executor is None:
            raise ReplayError("executor_unavailable", "replay executor is not configured")

        try:
            output = await asyncio.wait_for(
                executor(
                    ReplayExecution(
                        replay_id=replay_id,
                        request_id=request_id,
                        mode=request.mode,
                        target=target,
                        client_request=cast(Mapping[str, Any], client_request),
                        deadline_at=deadline_at,
                    )
                ),
                timeout=request.deadline_s,
            )
        except TimeoutError:
            return ReplayResult(
                replay_id=replay_id,
                request_id=request_id,
                mode=request.mode,
                selector=request.selector,
                source_entry_id=request.source_entry_id,
                source_capture_ref=str(request.capture_path)
                if request.capture_path is not None
                else None,
                target_policy=request.target_policy,
                target=target,
                started_at=started_at,
                finished_at=_timestamp(),
                outcome="deadline_exceeded",
                error_code="deadline_exceeded",
                client_actions=(),
                output=None,
                diagnostic_records=(),
            )
        if not isinstance(output, Mapping):
            raise ReplayError("executor_invalid_result", "replay executor returned a non-object")
        output = cast(Mapping[str, Any], output)
        raw_actions = output.get("client_actions", ())
        client_actions = _client_actions(raw_actions)
        return ReplayResult(
            replay_id=replay_id,
            request_id=request_id,
            mode=request.mode,
            selector=request.selector,
            source_entry_id=request.source_entry_id,
            source_capture_ref=str(request.capture_path)
            if request.capture_path is not None
            else None,
            target_policy=request.target_policy,
            target=target,
            started_at=started_at,
            finished_at=_timestamp(),
            outcome=str(output.get("outcome", "completed")),
            error_code=None,
            client_actions=client_actions,
            output=dict(output),
            diagnostic_records=(),
        )


def _validate_request(
    request: ReplayRequest,
) -> None:
    if request.deadline_s <= 0 or request.deadline_s > 86_400:
        raise ReplayError("invalid_deadline", "replay deadline is invalid")
    if request.mode is ReplayMode.WIRE_DIAGNOSTIC:
        if request.selector is not ReplaySourceSelector.UPSTREAM_ATTEMPT:
            raise ReplayError(
                "invalid_source_selector",
                "wire diagnostic requires an upstream attempt selector",
            )
        if request.attempt_id is None:
            raise ReplayError(
                "invalid_source_selector",
                "wire diagnostic requires attempt_id",
            )
    elif request.selector is not ReplaySourceSelector.CLIENT_REQUEST:
        raise ReplayError(
            "invalid_source_selector",
            "semantic and live replay require client_request",
        )


def _read_source(request: ReplayRequest) -> _CaptureSource:
    if request.capture_path is None:
        raise ReplayError(
            "source_content_unavailable",
            "replay requires a capture source",
        )
    try:
        records = tuple(
            record
            for record in iter_raw_capture_records(request.capture_path)
            if record.get("request_id") == request.source_entry_id
        )
    except (
        OSError,
        ValueError,
        TypeError,
        cbor2.CBORDecodeError,
        zstandard.ZstdError,
    ) as error:
        raise ReplayError(
            "source_evidence_unavailable",
            "capture source cannot be read",
        ) from error
    if not records:
        raise ReplayError(
            "source_evidence_unavailable",
            "capture source has no matching request",
        )
    client_body = _body(records, "request.body")
    client_end = _end_complete(records, "request.body.end")
    attempts: dict[int, tuple[Mapping[str, Any], ...]] = {}
    for record in records:
        attempt = record.get("attempt")
        event = record.get("event")
        if type(attempt) is int and isinstance(event, str):
            attempts.setdefault(attempt, tuple())
    for attempt in tuple(attempts):
        attempts[attempt] = tuple(
            record
            for record in records
            if record.get("attempt") == attempt
        )
    return _CaptureSource(
        records=records,
        client_request_body=client_body,
        client_request_complete=client_end,
        upstream_attempts=attempts,
    )


def _validate_source(request: ReplayRequest, source: _CaptureSource) -> None:
    if request.mode is ReplayMode.WIRE_DIAGNOSTIC:
        assert request.attempt_id is not None
        attempt = source.upstream_attempts.get(request.attempt_id)
        if attempt is None or not _attempt_complete(attempt):
            raise ReplayError(
                "source_evidence_unavailable",
                "selected upstream attempt is incomplete",
            )


def _attempt_complete(records: tuple[Mapping[str, Any], ...]) -> bool:
    has_request = any(record.get("event") == "upstream.request.body" for record in records)
    has_response = any(record.get("event") == "upstream.response.start" for record in records)
    has_response_end = any(
        record.get("event") == "upstream.response.end"
        and record.get("complete") is True
        for record in records
    )
    has_response_body = any(
        record.get("event") == "upstream.response.body" for record in records
    )
    return has_request and has_response and has_response_body and has_response_end


def _selected_attempt_records(
    source: _CaptureSource,
    attempt_id: int | None,
) -> tuple[Mapping[str, Any], ...]:
    if attempt_id is None:
        return ()
    return source.upstream_attempts.get(attempt_id, ())


def _body(records: tuple[Mapping[str, Any], ...], event_name: str) -> bytes | None:
    chunks = [
        record.get("body")
        for record in records
        if record.get("event") == event_name
    ]
    if not chunks:
        return None
    if not all(isinstance(chunk, bytes) for chunk in chunks):
        return None
    return b"".join(cast(bytes, chunk) for chunk in chunks)


def _end_complete(records: tuple[Mapping[str, Any], ...], event_name: str) -> bool:
    return any(
        record.get("event") == event_name and record.get("complete") is True
        for record in records
    )


def _client_actions(value: object) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, list):
        items: tuple[object, ...] = tuple(cast(list[object], value))
    elif isinstance(value, tuple):
        items = tuple(cast(tuple[object, ...], value))
    else:
        return ()
    return tuple(
        cast(Mapping[str, Any], item)
        for item in items
        if isinstance(item, Mapping)
    )


def _target_for(request: ReplayRequest) -> str | None:
    if request.target_policy is ReplayTargetPolicy.ORIGINAL_RESOLVED_TARGET:
        return request.original_target
    return request.current_target


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "ReplayError",
    "ReplayExecution",
    "ReplayMode",
    "ReplayProcess",
    "ReplayRequest",
    "ReplayResult",
    "ReplaySourceSelector",
    "ReplayTargetPolicy",
]
