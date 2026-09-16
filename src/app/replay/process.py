"""Independent replay orchestration over captured transport evidence."""

from __future__ import annotations

import asyncio
import json
import math
import multiprocessing
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

import cbor2
import zstandard

from app.history import CaptureCapabilities
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
    source_capture_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ReplaySourceReceipt:
    """A History-authorized replay source, resolved outside caller input."""

    entry_id: str
    capture_path: Path | None
    capture_ref: str | None
    capabilities: CaptureCapabilities


class ReplaySourceAuthority(Protocol):
    """Resolve an immutable source receipt from the controlled History boundary."""

    async def __call__(
        self,
        entry_id: str,
        capture_ref: str | None,
    ) -> ReplaySourceReceipt | None: ...


_DEFAULT_SOURCE_AUTHORITY: ReplaySourceAuthority | None = None


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
    """A credential-free replay result.

    Wire diagnostic records are summaries only; raw capture evidence remains
    process-local and is never included in this default result projection.
    """

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
            "client_actions": list(_client_actions(self.client_actions)),
            "output": _safe_result_output(self.output),
            "diagnostic_records": list(
                _diagnostic_summaries(
                    self.diagnostic_records,
                    deadline_at=math.inf,
                )
            ),
        }


@dataclass(frozen=True, slots=True)
class _CaptureSource:
    records: tuple[Mapping[str, Any], ...]
    client_request_body: bytes | None
    client_request_complete: bool
    upstream_attempts: Mapping[int, tuple[Mapping[str, Any], ...]]


class ReplayProcess:
    """Run replay outside the main server lifecycle."""

    def __init__(
        self,
        *,
        max_deadline_s: float,
        source_authority: ReplaySourceAuthority | None = None,
    ) -> None:
        if not math.isfinite(max_deadline_s) or max_deadline_s <= 0:
            raise ValueError("max_deadline_s must be positive")
        self.max_deadline_s = max_deadline_s
        self._source_authority = source_authority or _DEFAULT_SOURCE_AUTHORITY

    async def run(
        self,
        request: ReplayRequest,
        *,
        executor: ReplayExecutor | None = None,
    ) -> ReplayResult:
        started_at = _timestamp()
        replay_id = str(uuid4())
        request_id = f"replay-{replay_id}"
        _validate_request(request, max_deadline_s=self.max_deadline_s)
        target = _target_for(request)
        deadline_at = time.monotonic() + request.deadline_s
        receipt = await _resolve_source_receipt(
            self._source_authority,
            request,
            deadline_at=deadline_at,
        )
        source = _read_source(receipt, deadline_at=deadline_at)
        _validate_source(request, source)

        if request.mode is ReplayMode.WIRE_DIAGNOSTIC:
            diagnostic_records = _diagnostic_summaries(
                _selected_attempt_records(source, request.attempt_id),
                deadline_at=deadline_at,
            )
            return ReplayResult(
                replay_id=replay_id,
                request_id=request_id,
                mode=request.mode,
                selector=request.selector,
                source_entry_id=request.source_entry_id,
                source_capture_ref=receipt.capture_ref,
                target_policy=request.target_policy,
                target=target,
                started_at=started_at,
                finished_at=_timestamp(),
                outcome="completed",
                error_code=None,
                client_actions=(),
                output={"record_count": len(diagnostic_records)},
                diagnostic_records=diagnostic_records,
            )

        if source.client_request_body is None or not source.client_request_complete:
            raise ReplayError(
                "source_content_unavailable",
                "captured client request body is incomplete",
            )
        try:
            _require_remaining_deadline(deadline_at)
            client_request = json.loads(source.client_request_body)
            _require_remaining_deadline(deadline_at)
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
                timeout=_require_remaining_deadline(deadline_at),
            )
        except TimeoutError:
            return ReplayResult(
                replay_id=replay_id,
                request_id=request_id,
                mode=request.mode,
                selector=request.selector,
                source_entry_id=request.source_entry_id,
                source_capture_ref=receipt.capture_ref,
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
        safe_output = _safe_executor_output(output)
        client_actions = _client_actions(output.get("client_actions", ()))
        return ReplayResult(
            replay_id=replay_id,
            request_id=request_id,
            mode=request.mode,
            selector=request.selector,
            source_entry_id=request.source_entry_id,
            source_capture_ref=receipt.capture_ref,
            target_policy=request.target_policy,
            target=target,
            started_at=started_at,
            finished_at=_timestamp(),
            outcome=safe_output["outcome"],
            error_code=None,
            client_actions=client_actions,
            output=safe_output,
            diagnostic_records=(),
        )


def _validate_request(
    request: ReplayRequest,
    *,
    max_deadline_s: float,
) -> None:
    if (
        not math.isfinite(request.deadline_s)
        or request.deadline_s <= 0
        or request.deadline_s > 86_400
        or request.deadline_s > max_deadline_s
    ):
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

async def _resolve_source_receipt(
    authority: ReplaySourceAuthority | None,
    request: ReplayRequest,
    *,
    deadline_at: float,
) -> ReplaySourceReceipt:
    if authority is None:
        raise ReplayError(
            "source_authority_unavailable",
            "replay source authority is not configured",
        )
    try:
        receipt = await asyncio.wait_for(
            authority(request.source_entry_id, request.source_capture_ref),
            timeout=_require_remaining_deadline(deadline_at),
        )
    except TimeoutError as error:
        raise ReplayError("deadline_exceeded", "replay deadline exceeded") from error
    if receipt is None:
        raise ReplayError(
            "source_content_unavailable",
            "source history receipt is unavailable",
        )
    if (
        receipt.entry_id != request.source_entry_id
        or receipt.capture_ref != request.source_capture_ref
    ):
        raise ReplayError(
            "source_capability_mismatch",
            "source history receipt does not match replay source",
        )
    _validate_source_receipt(receipt, request)
    return receipt


def _validate_source_receipt(
    receipt: ReplaySourceReceipt,
    request: ReplayRequest,
) -> None:
    capabilities = receipt.capabilities
    code = capabilities.replay_rejection_code(
        request.mode.value,
        attempt_id=request.attempt_id,
    )
    if code is None:
        if receipt.capture_path is None:
            raise ReplayError(
                "source_content_unavailable",
                "replay requires a capture source",
            )
        if receipt.capture_ref is None:
            raise ReplayError(
                "source_capability_mismatch",
                "source history receipt has no capture reference",
            )
        return
    messages = {
        "source_capture_corrupt": "source capture is corrupt",
        "source_capture_incomplete": "source capture is incomplete",
        "source_content_unavailable": "source capture is unavailable",
        "source_capability_denied": "source history capability does not allow replay",
    }
    raise ReplayError(code, messages[code])


def _read_source(
    receipt: ReplaySourceReceipt,
    *,
    deadline_at: float,
) -> _CaptureSource:
    if receipt.capture_path is None:
        raise ReplayError(
            "source_content_unavailable",
            "replay requires a capture source",
        )
    records = _read_source_records(
        receipt.capture_path,
        receipt.entry_id,
        deadline_at=deadline_at,
    )
    _require_remaining_deadline(deadline_at)
    if not records:
        raise ReplayError(
            "source_evidence_unavailable",
            "capture source has no matching request",
        )
    client_body = _body(records, "request.body", deadline_at=deadline_at)
    client_end = _end_complete(records, "request.body.end", deadline_at=deadline_at)
    attempt_records: dict[int, list[Mapping[str, Any]]] = {}
    attempts_with_events: set[int] = set()
    for record in records:
        _require_remaining_deadline(deadline_at)
        attempt = record.get("attempt")
        event = record.get("event")
        if type(attempt) is int:
            attempt_records.setdefault(attempt, []).append(record)
            if isinstance(event, str):
                attempts_with_events.add(attempt)
    attempts: dict[int, tuple[Mapping[str, Any], ...]] = {}
    for attempt, grouped_records in attempt_records.items():
        _require_remaining_deadline(deadline_at)
        if attempt in attempts_with_events:
            attempts[attempt] = tuple(grouped_records)
    return _CaptureSource(
        records=records,
        client_request_body=client_body,
        client_request_complete=client_end,
        upstream_attempts=attempts,
    )


def _read_source_records(
    capture_path: Path,
    entry_id: str,
    *,
    deadline_at: float,
) -> tuple[Mapping[str, Any], ...]:
    context = multiprocessing.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    worker = context.Process(
        target=_read_source_records_worker,
        args=(sender, capture_path, entry_id),
        daemon=True,
    )
    try:
        worker.start()
        sender.close()
        if not receiver.poll(_require_remaining_deadline(deadline_at)):
            worker.terminate()
            worker.join()
            raise ReplayError("deadline_exceeded", "replay deadline exceeded")
        status, payload = receiver.recv()
        worker.join()
    except (EOFError, OSError, ValueError, TypeError) as error:
        raise ReplayError(
            "source_evidence_unavailable",
            "capture source cannot be read",
        ) from error
    finally:
        sender.close()
        receiver.close()
        if worker.is_alive():
            worker.terminate()
            worker.join()
    if status != "ok" or not isinstance(payload, tuple):
        raise ReplayError(
            "source_evidence_unavailable",
            "capture source cannot be read",
        )
    return cast(tuple[Mapping[str, Any], ...], payload)


def _read_source_records_worker(
    sender: Connection,
    capture_path: Path,
    entry_id: str,
) -> None:
    try:
        records = tuple(
            record
            for record in iter_raw_capture_records(capture_path)
            if record.get("request_id") == entry_id
        )
        sender.send(("ok", records))
    except (
        OSError,
        ValueError,
        TypeError,
        cbor2.CBORDecodeError,
        zstandard.ZstdError,
    ):
        sender.send(("error", None))
    finally:
        sender.close()


def _validate_source(request: ReplayRequest, source: _CaptureSource) -> None:
    if request.mode is ReplayMode.WIRE_DIAGNOSTIC:
        assert request.attempt_id is not None
        attempt = source.upstream_attempts.get(request.attempt_id)
        if attempt is None:
            raise ReplayError(
                "source_evidence_unavailable",
                "capture source has no selected upstream attempt",
            )


def _selected_attempt_records(
    source: _CaptureSource,
    attempt_id: int | None,
) -> tuple[Mapping[str, Any], ...]:
    if attempt_id is None:
        return ()
    return source.upstream_attempts.get(attempt_id, ())


def _diagnostic_summaries(
    records: tuple[Mapping[str, Any], ...],
    *,
    deadline_at: float,
) -> tuple[Mapping[str, Any], ...]:
    """Project selected wire evidence without retaining raw headers or bodies."""
    summaries: list[Mapping[str, Any]] = []
    for record in records:
        _require_remaining_deadline(deadline_at)
        event = record.get("event")
        if not isinstance(event, str):
            continue
        summary: dict[str, Any] = {"event": event}
        attempt = record.get("attempt")
        if type(attempt) is int:
            summary["attempt"] = attempt
        status_code = record.get("status_code")
        if type(status_code) is int:
            summary["status_code"] = status_code
        complete = record.get("complete")
        if type(complete) is bool:
            summary["complete"] = complete
        body = record.get("body")
        if isinstance(body, bytes):
            summary["body_bytes"] = len(body)
        summaries.append(summary)
    return tuple(summaries)


def _require_remaining_deadline(deadline_at: float) -> float:
    remaining = deadline_at - time.monotonic()
    if remaining <= 0:
        raise ReplayError("deadline_exceeded", "replay deadline exceeded")
    return remaining


def _body(
    records: tuple[Mapping[str, Any], ...],
    event_name: str,
    *,
    deadline_at: float,
) -> bytes | None:
    chunks: list[bytes] = []
    for record in records:
        _require_remaining_deadline(deadline_at)
        if record.get("event") != event_name:
            continue
        chunk = record.get("body")
        if not isinstance(chunk, bytes):
            return None
        chunks.append(chunk)
    if not chunks:
        return None
    _require_remaining_deadline(deadline_at)
    body = bytearray()
    for chunk in chunks:
        _require_remaining_deadline(deadline_at)
        body.extend(chunk)
        _require_remaining_deadline(deadline_at)
    result = bytes(body)
    _require_remaining_deadline(deadline_at)
    return result


def _end_complete(
    records: tuple[Mapping[str, Any], ...],
    event_name: str,
    *,
    deadline_at: float,
) -> bool:
    for record in records:
        _require_remaining_deadline(deadline_at)
        if record.get("event") == event_name and record.get("complete") is True:
            return True
    return False


def _client_actions(value: object) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, list):
        items: tuple[object, ...] = tuple(cast(list[object], value))
    elif isinstance(value, tuple):
        items = tuple(cast(tuple[object, ...], value))
    else:
        return ()
    actions: list[Mapping[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        item = cast(Mapping[str, object], item)
        action_type = item.get("type")
        name = item.get("name")
        if not isinstance(action_type, str):
            continue
        action: dict[str, str] = {"type": action_type}
        if isinstance(name, str):
            action["name"] = name
        actions.append(action)
    return tuple(actions)


def _safe_executor_output(output: Mapping[str, Any]) -> Mapping[str, str]:
    outcome = output.get("outcome", "completed")
    if outcome not in {"completed", "failed", "cancelled"}:
        raise ReplayError(
            "executor_invalid_result",
            "replay executor returned an invalid outcome",
        )
    return {"outcome": outcome}


def _safe_result_output(value: Mapping[str, Any] | None) -> Mapping[str, str] | None:
    if value is None:
        return None
    outcome = value.get("outcome")
    if outcome not in {"completed", "failed", "cancelled"}:
        return None
    return {"outcome": outcome}


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
    "ReplaySourceAuthority",
    "ReplaySourceReceipt",
    "ReplaySourceSelector",
    "ReplayTargetPolicy",
]
