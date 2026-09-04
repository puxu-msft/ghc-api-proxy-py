from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

from starlette.requests import ClientDisconnect

from app.observability.logging import get_logger
from app.observability.metrics import TRANSLATION_LOSSES
from app.observability.request_log import LogStatus, RequestLine, format_completion_line, status_for
from app.observability.request_log_file import utc_timestamp, write_finalized_record
from app.observability.request_trace import REQUEST_LOGGER, RequestTrace, request_line_from_trace
from app.pipeline.delivery.assembling import ReplyDialect
from app.pipeline.hand_over import one_line
from app.pipeline.response_observation import (
    ExactUsage,
    FrozenJsonObject,
    JsonObservation,
    ObservationIssue,
    OutputItemSummary,
    ProviderErrorSummary,
    ResponseAvailability,
    ResponseObservation,
    UsageObservation,
    freeze_json,
    thaw_json,
)
from app.tokenization.admission import TokenAdmissionObservation
from app.wire_json import JsonValue

if TYPE_CHECKING:
    from app.core.chain import Chain

logger = logging.getLogger(__name__)


def _warn_no_raise(message: str, *args: object) -> None:
    """Last-resort reporting that cannot re-enter request control flow."""
    # The logging handler is the failed observability sink here. There is no independent safe channel left to report that second failure through.
    with suppress(BaseException):
        logger.warning(message, *args)


class DeliveryState(StrEnum):
    NOT_STARTED = "not_started"
    STARTED = "started"
    ACCEPTED = "accepted"


class FailureOrigin(StrEnum):
    DISPATCH = "dispatch"
    SEND = "send"
    WRAPPED = "wrapped"
    BACKGROUND = "background"
    CLEANUP = "cleanup"
    UPSTREAM = "upstream"


class FailureCategory(StrEnum):
    DISCONNECT = "disconnect"
    CANCELLED = "cancelled"
    ERROR = "error"
    INCOMPLETE_RESPONSE = "incomplete_response"
    PROVIDER_FAILURE = "provider_failure"


class InterruptionKind(StrEnum):
    HTTP_DISCONNECT = "http_disconnect"
    ASGI_RECEIVE_ERROR = "asgi_receive_error"
    UPSTREAM_STREAM_FAILURE = "upstream_stream_failure"


class InterruptionOrigin(StrEnum):
    DOWNSTREAM = "downstream"
    UPSTREAM = "upstream"


class InterruptionPhase(StrEnum):
    REQUEST_BODY = "request_body"
    DISPATCH_WAIT = "dispatch_wait"
    RESPONSE_STREAM = "response_stream"
    UPSTREAM_BODY = "upstream_body"


@dataclass(frozen=True, slots=True)
class FailureSummary:
    origin: FailureOrigin
    category: FailureCategory
    type: str | None
    message: str | None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InterruptionObservation:
    kind: InterruptionKind
    origin: InterruptionOrigin
    phase: InterruptionPhase
    observed_s: float
    attempt: int | None
    category: str | None
    exception_module: str | None
    exception_type: str | None
    message: str | None
    continuation_synthesized: bool


@dataclass(frozen=True, slots=True)
class DeliveryObservation:
    state: DeliveryState
    unit: str | None
    intended_http_status: int | None
    http_start_accepted: bool
    downstream_body_bytes: int | None
    failure: FailureSummary | None
    post_delivery_failure: FailureSummary | None
    additional_failures: tuple[FailureSummary, ...]


@dataclass(frozen=True, slots=True)
class TimingObservation:
    response_ready_s: float | None
    finalized_s: float
    first_upstream_byte_s: float | None
    upstream_max_gap_s: float | None
    upstream_chunks: int
    upstream_timing_attempt: int | None = None
    last_upstream_chunk_s: float | None = None
    final_upstream_pull_started_s: float | None = None
    upstream_end_s: float | None = None
    upstream_tail_gap_s: float | None = None
    upstream_final_pull_s: float | None = None


@dataclass(frozen=True, slots=True)
class BodyBytesObservation:
    upstream_request: int | None
    upstream_response: int | None
    downstream_response: int | None


@dataclass(frozen=True, slots=True)
class FinalizedRequest:
    status: LogStatus
    at: str
    legacy: FrozenJsonObject
    response: ResponseObservation | None
    delivery: DeliveryObservation
    timings: TimingObservation
    body_bytes: BodyBytesObservation
    token_admissions: tuple[TokenAdmissionObservation, ...] = ()
    interruptions: tuple[InterruptionObservation, ...] = ()

    def request_line(self) -> RequestLine:
        value = thaw_json(self.legacy)
        if not isinstance(value, dict):
            raise TypeError("finalized legacy request line is not an object")
        raw = cast(dict[str, Any], value)
        return RequestLine(
            method=_string(raw, "method"),
            path=_string(raw, "path"),
            request_id=_string(raw, "request_id"),
            message_id=_string(raw, "message_id"),
            inbound_format=_string(raw, "inbound_format"),
            count_tokens=_bool(raw, "count_tokens"),
            client_protocol=_string(raw, "client_protocol"),
            upstream_protocol=_string(raw, "upstream_protocol"),
            requested_model=_string(raw, "requested_model"),
            model=_string(raw, "model"),
            status_code=_optional_int(raw, "status_code"),
            started_at=_string(raw, "started_at"),
            duration_s=_optional_number(raw, "duration_s"),
            first_upstream_byte_s=_optional_number(raw, "first_upstream_byte_s"),
            upstream_max_gap_s=_optional_number(raw, "upstream_max_gap_s"),
            upstream_chunks=_integer(raw, "upstream_chunks"),
            bytes_in=_optional_int(raw, "bytes_in"),
            bytes_out=_optional_int(raw, "bytes_out"),
            usage=_object(raw, "usage"),
            terminal_seen=_bool(raw, "terminal_seen"),
            stop_reason=_string(raw, "stop_reason"),
            blocks=_integer(raw, "blocks"),
            tools=_string_tuple(raw, "tools"),
            thinking=_string_tuple(raw, "thinking"),
            count_provider=_string(raw, "count_provider"),
            count_provider_reason=_string(raw, "count_provider_reason"),
            dialect=ReplyDialect(_string(raw, "dialect")),
            attempts=_integer(raw, "attempts"),
            replaced_failures=_string_tuple(raw, "replaced_failures"),
            tore_after_terminal=_string(raw, "tore_after_terminal"),
            detail=_string(raw, "detail"),
            upstream_conn=_object(raw, "upstream_conn"),
            losses=tuple(
                cast(dict[str, str], item)
                for item in _array(raw, "losses")
                if isinstance(item, dict)
            ),
        )

    def to_record_dict(self) -> dict[str, JsonValue]:
        value = thaw_json(self.legacy)
        if not isinstance(value, dict):
            raise TypeError("finalized legacy request line is not an object")
        record = cast(dict[str, JsonValue], value)
        return {
            "at": self.at,
            "status": self.status,
            **record,
            "schema_version": 2,
            "observation": {
                "response": _response_dict(self.response),
                "token_admission": [
                    _token_admission_dict(observation)
                    for observation in self.token_admissions
                ],
                "interruptions": [
                    _interruption_dict(interruption)
                    for interruption in self.interruptions
                ],
                "delivery": _delivery_dict(self.delivery),
                "timings": _timings_dict(self.timings),
                "body_bytes": _body_bytes_dict(self.body_bytes),
            },
        }


@dataclass(slots=True)
class RequestCompletionCoordinator:
    chain: Chain
    trace: RequestTrace
    request_id: str
    _state: DeliveryState = DeliveryState.NOT_STARTED
    _unit: str | None = None
    _intended_http_status: int | None = None
    _http_start_accepted: bool = False
    _downstream_body_bytes: int | None = None
    _failure: FailureSummary | None = None
    _post_delivery_failure: FailureSummary | None = None
    _additional_failures: list[FailureSummary] = field(
        default_factory=lambda: list[FailureSummary]()
    )
    _seen_failures: list[tuple[BaseException, FailureOrigin]] = field(
        default_factory=lambda: list[tuple[BaseException, FailureOrigin]]()
    )
    _interruptions: list[InterruptionObservation] = field(
        default_factory=lambda: list[InterruptionObservation]()
    )
    _exception_messages: list[tuple[BaseException, str | None]] = field(
        default_factory=lambda: list[tuple[BaseException, str | None]]()
    )
    _exception_notes: list[tuple[BaseException, tuple[str, ...]]] = field(
        default_factory=lambda: list[tuple[BaseException, tuple[str, ...]]]()
    )
    _secondary_detail_suffixes: list[str] = field(
        default_factory=lambda: list[str]()
    )
    _response_ready_s: float | None = None
    _legacy_duration_s: float | None = None
    _status_code: int | None = None
    _upstream_response_bytes: int | None = None
    _authoritative_stream_ending: bool = False
    _settled: bool = False
    _record: FinalizedRequest | None = None

    @property
    def delivery_accepted(self) -> bool:
        return self._state is DeliveryState.ACCEPTED

    @property
    def intended_http_status(self) -> int | None:
        return self._intended_http_status

    @property
    def has_pre_acceptance_failure(self) -> bool:
        return self._failure is not None and self._state is not DeliveryState.ACCEPTED

    def mark_response_ready(self, status_code: int) -> None:
        self._intended_http_status = status_code
        if self._response_ready_s is None:
            self._response_ready_s = time.monotonic() - self.trace.started
        if self._legacy_duration_s is None:
            self._legacy_duration_s = self._response_ready_s

    def note_asgi_message_offered(self, message: Mapping[str, Any]) -> None:
        if message.get("type") != "http.response.start":
            return
        status = message.get("status")
        if isinstance(status, int) and not isinstance(status, bool):
            self._intended_http_status = status

    def note_asgi_message_sent(self, message: Mapping[str, Any]) -> None:
        self.note_asgi_message_offered(message)
        kind = message.get("type")
        if kind == "http.response.start":
            self._http_start_accepted = True
            if self._state is DeliveryState.NOT_STARTED:
                self._state = DeliveryState.STARTED
            return
        if kind == "http.response.pathsend":
            self._state = DeliveryState.ACCEPTED
            if self._unit is None:
                self._unit = "pathsend"
            self._downstream_body_bytes = None
            return
        if kind != "http.response.body":
            return
        body = message.get("body", b"")
        count: int | None = None
        if isinstance(body, bytes | bytearray):
            count = len(body)
        elif isinstance(body, memoryview):
            count = body.nbytes
        if count is not None:
            if self._downstream_body_bytes is None:
                self._downstream_body_bytes = 0
            self._downstream_body_bytes += count
            try:
                self.chain.active_requests.add_downstream_bytes(self.request_id, count)
            except Exception as error:
                _warn_no_raise("could not update live downstream bytes: %r", error)
        if not bool(message.get("more_body", False)):
            self._state = DeliveryState.ACCEPTED
            if self._unit is None:
                self._unit = "body"

    def note_send_failure(self, error: BaseException) -> None:
        self._note_failure(error, origin=FailureOrigin.SEND)

    def note_http_disconnect(self, *, phase: InterruptionPhase) -> None:
        self._note_interruption(
            kind=InterruptionKind.HTTP_DISCONNECT,
            origin=InterruptionOrigin.DOWNSTREAM,
            phase=phase,
            category=FailureCategory.DISCONNECT.value,
        )

    def note_asgi_receive_error(
        self,
        error: Exception,
        *,
        phase: InterruptionPhase,
    ) -> None:
        self._note_interruption(
            kind=InterruptionKind.ASGI_RECEIVE_ERROR,
            origin=InterruptionOrigin.DOWNSTREAM,
            phase=phase,
            category=FailureCategory.ERROR.value,
            error=error,
        )

    def note_upstream_stream_failure(
        self,
        *,
        attempt: int,
        category: str,
        exception_module: str,
        exception_type: str,
        message: str | None,
    ) -> None:
        self._interruptions.append(
            InterruptionObservation(
                kind=InterruptionKind.UPSTREAM_STREAM_FAILURE,
                origin=InterruptionOrigin.UPSTREAM,
                phase=InterruptionPhase.UPSTREAM_BODY,
                observed_s=time.monotonic() - self.trace.started,
                attempt=attempt,
                category=category,
                exception_module=exception_module,
                exception_type=exception_type,
                message=message,
                continuation_synthesized=True,
            )
        )

    def note_wrapped_failure(self, error: BaseException, *, origin: FailureOrigin) -> None:
        self._note_failure(error, origin=origin)

    def note_completion_unit_accepted(self, unit: str) -> None:
        self._state = DeliveryState.ACCEPTED
        if self._unit is None or self._unit == "body":
            self._unit = unit

    def note_missing_terminal(self) -> None:
        if self._state is DeliveryState.ACCEPTED:
            return
        if self._failure is None:
            self._failure = FailureSummary(
                origin=FailureOrigin.WRAPPED,
                category=FailureCategory.INCOMPLETE_RESPONSE,
                type=None,
                message="ASGI response returned without a terminal delivery message",
            )
        self.trace.status_override = "fail"
        if not self.trace.detail:
            self.trace.detail = "ASGI response returned without a terminal delivery message"

    def note_secondary_cleanup(self, error: BaseException) -> None:
        details = [
            self._exception_message(error) or type(error).__qualname__,
            *self._exception_notes_for(error),
        ]
        self._append_secondary_detail(f"cleanup also failed: {'; '.join(details)}")

    def note_secondary_cleanup_failure(self, error: BaseException) -> bool:
        # Console detail and structured-failure identity are separate axes. An inner delivery layer may have recorded this exact cleanup object before the outer response discovers that it is secondary to a disconnect; only that cleanup-origin case needs its suffix filled in here. A send error already serving as the primary may also sit under ClientDisconnect.__cause__, and must not be mislabeled as a second cleanup failure.
        for seen, origin in self._seen_failures:
            if error is seen:
                if origin is FailureOrigin.CLEANUP:
                    self.note_secondary_cleanup(error)
                return False
        self.note_secondary_cleanup(error)
        self._note_failure(error, origin=FailureOrigin.CLEANUP)
        return True

    def note_secondary_cleanup_notes(self, error: BaseException) -> None:
        for note in self._exception_notes_for(error):
            self._append_secondary_detail(
                note if note.startswith("cleanup also failed:") else f"cleanup note: {note}"
            )

    def _append_secondary_detail(self, suffix: str) -> None:
        if suffix in self._secondary_detail_suffixes:
            return
        self._secondary_detail_suffixes.append(suffix)
        self._append_detail(suffix)

    def _append_detail(self, suffix: str) -> None:
        self.trace.detail = (
            f"{self.trace.detail}; {suffix}"
            if self.trace.detail
            else suffix
        )

    def _ending_with_secondaries(self, detail: str) -> str:
        if not self._secondary_detail_suffixes:
            return detail
        return "; ".join((detail, *self._secondary_detail_suffixes))

    def note_stream_ending(
        self,
        status: LogStatus,
        detail: str,
        *,
        authoritative: bool,
    ) -> None:
        """Merge a stream ending through its priority, not its arrival order."""
        if authoritative:
            self._authoritative_stream_ending = True
            self.trace.status_override = status
            self.trace.detail = self._ending_with_secondaries(detail)
            return
        if self._failure is None:
            self.trace.status_override = status
            self.trace.detail = self._ending_with_secondaries(detail)
            return
        if (
            status == "gone"
            and self._failure.category
            in {FailureCategory.DISCONNECT, FailureCategory.CANCELLED}
        ):
            # Keep the structured primary message in DeliveryObservation while retaining the established stream-specific console explanation for routine client aborts. Server-side send failures keep their exact primary detail.
            self.trace.detail = self._ending_with_secondaries(detail)

    def settle(
        self,
        *,
        status_code: int | None,
        upstream_response_bytes: int | None,
        legacy_duration_s: float | None = None,
        completion_unit: str | None = None,
    ) -> None:
        self._settled = True
        self._status_code = (
            self._intended_http_status
            if self._intended_http_status is not None
            else status_code
        )
        self._upstream_response_bytes = upstream_response_bytes
        if legacy_duration_s is not None:
            self._legacy_duration_s = legacy_duration_s
        elif self._legacy_duration_s is None:
            self._legacy_duration_s = time.monotonic() - self.trace.started
        if completion_unit is not None:
            self.note_completion_unit_accepted(completion_unit)

    def publish(self) -> FinalizedRequest:
        if self._record is not None:
            return self._record
        if not self._settled:
            self.settle(
                status_code=self._intended_http_status,
                upstream_response_bytes=self.trace.upstream_response_body_bytes,
            )
        status_code = self._status_code
        provider_failed = bool(
            self.trace.response_observation
            and self.trace.response_observation.provider_failed
        )
        status = status_for(
            status_code,
            override=("fail" if provider_failed else self.trace.status_override),
        )
        finalized_s = time.monotonic() - self.trace.started
        line = request_line_from_trace(
            self.trace,
            status_code,
            upstream_response_body_bytes=self._upstream_response_bytes,
            duration_s=self._legacy_duration_s,
        )
        record = FinalizedRequest(
            status=status,
            at=utc_timestamp(),
            legacy=_freeze_line_or_fallback(line),
            response=self.trace.response_observation,
            delivery=DeliveryObservation(
                state=self._state,
                unit=self._unit,
                intended_http_status=self._intended_http_status,
                http_start_accepted=self._http_start_accepted,
                downstream_body_bytes=self._downstream_body_bytes,
                failure=self._failure,
                post_delivery_failure=self._post_delivery_failure,
                additional_failures=tuple(self._additional_failures),
            ),
            timings=TimingObservation(
                response_ready_s=self._response_ready_s,
                finalized_s=finalized_s,
                first_upstream_byte_s=self.trace.first_upstream_byte_s,
                upstream_max_gap_s=self.trace.upstream_max_gap_s,
                upstream_chunks=self.trace.upstream_chunks,
                upstream_timing_attempt=self.trace.upstream_timing_attempt,
                last_upstream_chunk_s=self.trace.last_upstream_chunk_s,
                final_upstream_pull_started_s=(
                    self.trace.final_upstream_pull_started_s
                ),
                upstream_end_s=self.trace.upstream_end_s,
                upstream_tail_gap_s=self.trace.upstream_tail_gap_s,
                upstream_final_pull_s=self.trace.upstream_final_pull_s,
            ),
            body_bytes=BodyBytesObservation(
                upstream_request=self.trace.upstream_request_body_bytes,
                upstream_response=self._upstream_response_bytes,
                downstream_response=self._downstream_body_bytes,
            ),
            token_admissions=self.trace.token_admissions,
            interruptions=tuple(self._interruptions),
        )
        # Set before every sink. A re-entrant or duplicate publisher sees the same immutable record and cannot repeat a side effect.
        self._record = record
        self._emit(record)
        return record

    def _note_interruption(
        self,
        *,
        kind: InterruptionKind,
        origin: InterruptionOrigin,
        phase: InterruptionPhase,
        category: str,
        attempt: int | None = None,
        error: BaseException | None = None,
        continuation_synthesized: bool = False,
    ) -> None:
        self._interruptions.append(
            InterruptionObservation(
                kind=kind,
                origin=origin,
                phase=phase,
                observed_s=time.monotonic() - self.trace.started,
                attempt=attempt,
                category=category,
                exception_module=(type(error).__module__ if error is not None else None),
                exception_type=(type(error).__qualname__ if error is not None else None),
                message=(
                    self._exception_message(error)
                    if error is not None
                    else None
                ),
                continuation_synthesized=continuation_synthesized,
            )
        )

    def _exception_message(self, error: BaseException) -> str | None:
        for seen, message in self._exception_messages:
            if error is seen:
                return message
        message = _safe_exception_message(error)
        self._exception_messages.append((error, message))
        return message

    def _exception_notes_for(self, error: BaseException) -> tuple[str, ...]:
        normalized_error = error
        for seen, notes in self._exception_notes:
            if normalized_error is seen:
                return notes
        notes = (
            safe_exception_graph_notes(normalized_error)
            if isinstance(error, BaseExceptionGroup)
            else safe_exception_notes(normalized_error)
        )
        self._exception_notes.append((normalized_error, notes))
        return notes

    def _note_failure(self, error: BaseException, *, origin: FailureOrigin) -> None:
        if any(error is seen for seen, _origin in self._seen_failures):
            return
        self._seen_failures.append((error, origin))
        summary = _failure_summary(
            error,
            origin=origin,
            message=self._exception_message(error),
            notes=self._exception_notes_for(error),
        )
        if self._state is DeliveryState.ACCEPTED:
            if self._post_delivery_failure is None:
                self._post_delivery_failure = summary
            else:
                self._additional_failures.append(summary)
            return
        # The propagated primary is observed first. Every later distinct failure remains structured evidence but cannot replace its verdict.
        if self._failure is not None:
            self._additional_failures.append(summary)
            return
        self._failure = summary
        provider_failed = bool(
            self.trace.response_observation
            and self.trace.response_observation.provider_failed
        )
        if provider_failed:
            self.trace.status_override = "fail"
            return
        if self._authoritative_stream_ending:
            return
        if summary.category in {FailureCategory.DISCONNECT, FailureCategory.CANCELLED}:
            self.trace.status_override = "gone"
        else:
            self.trace.status_override = "fail"
        if not self.trace.detail:
            self.trace.detail = summary.message or summary.type or summary.category.value

    def _emit(self, record: FinalizedRequest) -> None:
        sinks = (
            ("request store", lambda: self.chain.active_requests.complete(self.request_id, record)),
            ("translation loss metrics", lambda: _record_translation_losses(record)),
            ("structured request record", lambda: write_finalized_record(record.to_record_dict())),
            ("completion line", lambda: _log_finalized(self.chain, record)),
        )
        for name, sink in sinks:
            try:
                sink()
            except Exception as error:
                _warn_no_raise("could not emit %s: %r", name, error)


def _safe_exception_message(error: BaseException) -> str | None:
    for render in (str, repr):
        try:
            rendered = one_line(render(error))
        except BaseException as rendering_error:
            _warn_no_raise(
                "could not render %s for request observability: %r",
                type(error).__qualname__,
                rendering_error,
            )
            continue
        if rendered:
            return rendered
    return None


def safe_exception_notes(error: BaseException) -> tuple[str, ...]:
    """Read one exception's notes as inert base strings without trusting dynamic methods."""
    try:
        raw_notes = getattr(error, "__notes__", None)
    except BaseException as rendering_error:
        _warn_no_raise(
            "could not read %s notes for request observability: %r",
            type(error).__qualname__,
            rendering_error,
        )
        return ("<exception notes unavailable>",)
    if raw_notes is None:
        return ()
    if type(raw_notes) is not list:
        _warn_no_raise(
            "ignored an invalid %s notes container for request observability",
            type(error).__qualname__,
        )
        return ("<invalid exception notes container>",)

    normalized: list[str] = []
    notes = cast(list[object], raw_notes)
    for note in notes:
        if not isinstance(note, str):
            normalized.append("<invalid exception note>")
            continue
        try:
            # Calling the base C implementation avoids a str subclass's overridden `split`, `encode`, `__hash__`, or related methods from re-entering request control flow.
            base_note = bytes.decode(str.encode(note, "utf-8", "replace"), "utf-8")
            rendered = one_line(base_note)
        except BaseException as rendering_error:
            _warn_no_raise(
                "could not normalize an exception note for request observability: %r",
                rendering_error,
            )
            normalized.append("<unrenderable exception note>")
            continue
        if rendered:
            normalized.append(rendered)
    return tuple(normalized)


def safe_exception_graph_notes(error: BaseException) -> tuple[str, ...]:
    """Collect normalized notes from a whole cause/context/group graph once each."""
    seen_nodes: set[int] = set()
    seen_notes: set[str] = set()
    notes: list[str] = []
    pending = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen_nodes:
            continue
        seen_nodes.add(id(current))
        for note in safe_exception_notes(current):
            if note not in seen_notes:
                seen_notes.add(note)
                notes.append(note)
        pending.extend(
            nested
            for nested in (current.__cause__, current.__context__)
            if nested is not None
        )
        if isinstance(current, BaseExceptionGroup):
            group = cast(BaseExceptionGroup[BaseException], current)
            pending.extend(group.exceptions)
    return tuple(notes)


def _failure_summary(
    error: BaseException,
    *,
    origin: FailureOrigin,
    message: str | None,
    notes: tuple[str, ...],
) -> FailureSummary:
    if isinstance(error, asyncio.CancelledError):
        category = FailureCategory.CANCELLED
    elif isinstance(error, ClientDisconnect) or (
        origin is FailureOrigin.SEND and isinstance(error, OSError)
    ):
        category = FailureCategory.DISCONNECT
    else:
        category = FailureCategory.ERROR
    return FailureSummary(
        origin=origin,
        category=category,
        type=error.__class__.__name__,
        message=message,
        notes=notes,
    )


def _record_translation_losses(record: FinalizedRequest) -> None:
    line = record.request_line()
    for direction, code in sorted({(loss["direction"], loss["code"]) for loss in line.losses}):
        TRANSLATION_LOSSES.labels(direction=direction, code=code).inc()


def _log_finalized(chain: Chain, record: FinalizedRequest) -> None:
    line = record.request_line()
    get_logger(REQUEST_LOGGER).info(
        format_completion_line(
            line,
            status=record.status,
            unicode=chain.capabilities.unicode,
            color=chain.capabilities.color,
            response_observation=record.response,
        ),
        status=record.status,
    )


def _freeze_line_or_fallback(line: RequestLine) -> FrozenJsonObject:
    try:
        return _freeze_line(line)
    except Exception as error:
        # Domain construction is observability too. A malformed legacy projection must not replace the response or a primary exception; retain enough safe identity to keep one finalized record and report why the rich projection was unavailable.
        _warn_no_raise("could not freeze the full legacy request projection: %r", error)
        return _freeze_line(
            RequestLine(
                method=line.method,
                path=line.path,
                request_id=line.request_id,
                inbound_format=line.inbound_format,
                status_code=(
                    line.status_code
                    if isinstance(line.status_code, int)
                    and not isinstance(line.status_code, bool)
                    else None
                ),
                started_at=line.started_at,
                detail=f"request observability degraded: {type(error).__name__}",
            )
        )


def _freeze_line(line: RequestLine) -> FrozenJsonObject:
    frozen = freeze_json(
        {
            "method": line.method,
            "path": line.path,
            "request_id": line.request_id,
            "message_id": line.message_id,
            "inbound_format": line.inbound_format,
            "count_tokens": line.count_tokens,
            "client_protocol": line.client_protocol,
            "upstream_protocol": line.upstream_protocol,
            "requested_model": line.requested_model,
            "model": line.model,
            "status_code": line.status_code,
            "started_at": line.started_at,
            "duration_s": line.duration_s,
            "first_upstream_byte_s": line.first_upstream_byte_s,
            "upstream_max_gap_s": line.upstream_max_gap_s,
            "upstream_chunks": line.upstream_chunks,
            "bytes_in": line.bytes_in,
            "bytes_out": line.bytes_out,
            "usage": line.usage,
            "terminal_seen": line.terminal_seen,
            "stop_reason": line.stop_reason,
            "blocks": line.blocks,
            "tools": list(line.tools),
            "thinking": list(line.thinking),
            "count_provider": line.count_provider,
            "count_provider_reason": line.count_provider_reason,
            "dialect": line.dialect.value,
            "attempts": line.attempts,
            "replaced_failures": list(line.replaced_failures),
            "tore_after_terminal": line.tore_after_terminal,
            "detail": line.detail,
            "upstream_conn": line.upstream_conn,
            "losses": list(line.losses),
        }
    )
    if not isinstance(frozen, FrozenJsonObject):
        raise TypeError("request line did not freeze as an object")
    return frozen


def _response_dict(observation: ResponseObservation | None) -> dict[str, JsonValue]:
    if observation is None:
        return {
            "availability": ResponseAvailability.NOT_APPLICABLE.value,
            "source_protocol": None,
            "terminal_event_type": None,
            "terminal_seen": None,
            "status": None,
            "incomplete_reason": None,
            "error": {"availability": "not_applicable", "value": None},
            "error_summary": None,
            "model": None,
            "service_tier": None,
            "output_items": None,
            "usage": None,
            "provider_usage": {"availability": "not_applicable", "value": None},
            "tool_usage": {"availability": "not_applicable", "value": None},
            "issues": [],
        }
    return {
        "availability": observation.availability.value,
        "source_protocol": observation.source_protocol,
        "terminal_event_type": observation.terminal_event_type,
        "terminal_seen": observation.terminal_seen,
        "status": observation.status,
        "incomplete_reason": observation.incomplete_reason,
        "error": _json_observation_dict(observation.error),
        "error_summary": _provider_error_summary_dict(
            observation.error_summary
        ),
        "model": observation.model,
        "service_tier": observation.service_tier,
        "output_items": (
            [_item_dict(item) for item in observation.output_items]
            if observation.output_items is not None
            else None
        ),
        "usage": _usage_dict(observation.usage),
        "provider_usage": _json_observation_dict(observation.provider_usage),
        "tool_usage": _json_observation_dict(observation.tool_usage),
        "issues": [_issue_dict(issue) for issue in observation.issues],
    }


def _json_observation_dict(observation: JsonObservation) -> dict[str, JsonValue]:
    return {
        "availability": observation.availability.value,
        "value": thaw_json(observation.value) if observation.value is not None else None,
    }


def _provider_error_summary_dict(
    summary: ProviderErrorSummary | None,
) -> dict[str, JsonValue] | None:
    if summary is None:
        return None
    return {
        "type": summary.type,
        "code": summary.code,
        "message": summary.message,
    }


def _issue_dict(issue: ObservationIssue) -> dict[str, JsonValue]:
    return {
        "code": issue.code,
        "field_path": issue.field_path,
        "detail": issue.detail,
    }


def _item_dict(item: OutputItemSummary) -> dict[str, JsonValue]:
    return {
        "output_index": item.output_index,
        "type": item.type,
        "name": item.name,
        "status": item.status,
        "execution": item.execution,
        "call_id": item.call_id,
        "reasoning": {
            "summary_items": item.reasoning.summary_items,
            "has_readable_summary": item.reasoning.has_readable_summary,
            "has_encrypted_content": item.reasoning.has_encrypted_content,
        },
        "client_action": {
            "requirement": item.client_action.requirement.value,
            "basis": item.client_action.basis.value,
            "delivery_required": item.client_action.delivery_required,
        },
    }


def _usage_dict(usage: UsageObservation | None) -> dict[str, JsonValue] | None:
    if usage is None:
        return None
    return {
        "normalized": {
            "input_tokens": usage.normalized.input_tokens,
            "cache_read_input_tokens": usage.normalized.cache_read_input_tokens,
            "cache_creation_input_tokens": usage.normalized.cache_creation_input_tokens,
            "output_tokens": usage.normalized.output_tokens,
        },
        "raw": _json_observation_dict(usage.raw),
        "exact": _exact_usage_dict(usage.exact),
        "issues": [_issue_dict(issue) for issue in usage.issues],
    }


def _exact_usage_dict(exact: ExactUsage | None) -> dict[str, JsonValue] | None:
    if exact is None:
        return None
    input_details = thaw_json(exact.input_tokens_details)
    output_details = thaw_json(exact.output_tokens_details)
    return {
        "upstream_input_tokens": exact.upstream_input_tokens,
        "input_tokens": exact.input_tokens,
        "cache_read_input_tokens": exact.cache_read_input_tokens,
        "cache_creation_input_tokens": exact.cache_creation_input_tokens,
        "output_tokens": exact.output_tokens,
        "reasoning_tokens": exact.reasoning_tokens,
        "computed_total_tokens": exact.computed_total_tokens,
        "upstream_total_tokens": exact.upstream_total_tokens,
        "input_tokens_details": input_details,
        "output_tokens_details": output_details,
        "inconsistent": exact.inconsistent,
    }


def _failure_dict(failure: FailureSummary | None) -> dict[str, JsonValue] | None:
    if failure is None:
        return None
    value: dict[str, JsonValue] = {
        "origin": failure.origin.value,
        "category": failure.category.value,
        "type": failure.type,
        "message": failure.message,
    }
    if failure.notes:
        value["notes"] = list(failure.notes)
    return value


def _token_admission_dict(
    observation: TokenAdmissionObservation,
) -> dict[str, JsonValue]:
    return {
        "attempt": observation.attempt,
        "origin": observation.origin,
        "outcome": observation.outcome.value,
        "target_format": observation.target_format,
        "model": observation.model,
        "provider": observation.provider,
        "catalog_generation": observation.catalog_generation,
        "catalog_refreshed_at": observation.catalog_refreshed_at,
        "tokenizer": observation.tokenizer,
        "max_prompt_tokens": observation.max_prompt_tokens,
        "max_context_window_tokens": observation.max_context_window_tokens,
        "field_path": observation.field_path,
        "field_kind": observation.field_kind,
        "field_utf8_byte_count": observation.field_utf8_byte_count,
        "field_token_count": observation.field_token_count,
    }


def _interruption_dict(
    interruption: InterruptionObservation,
) -> dict[str, JsonValue]:
    return {
        "kind": interruption.kind.value,
        "origin": interruption.origin.value,
        "phase": interruption.phase.value,
        "observed_s": interruption.observed_s,
        "attempt": interruption.attempt,
        "category": interruption.category,
        "exception_module": interruption.exception_module,
        "exception_type": interruption.exception_type,
        "message": interruption.message,
        "continuation_synthesized": interruption.continuation_synthesized,
    }


def _delivery_dict(delivery: DeliveryObservation) -> dict[str, JsonValue]:
    return {
        "state": delivery.state.value,
        "unit": delivery.unit,
        "intended_http_status": delivery.intended_http_status,
        "http_start_accepted": delivery.http_start_accepted,
        "downstream_body_bytes": delivery.downstream_body_bytes,
        "failure": _failure_dict(delivery.failure),
        "post_delivery_failure": _failure_dict(delivery.post_delivery_failure),
        "additional_failures": [
            _failure_dict(failure) for failure in delivery.additional_failures
        ],
    }


def _timings_dict(timings: TimingObservation) -> dict[str, JsonValue]:
    return {
        "response_ready_s": timings.response_ready_s,
        "finalized_s": timings.finalized_s,
        "first_upstream_byte_s": timings.first_upstream_byte_s,
        "upstream_max_gap_s": timings.upstream_max_gap_s,
        "upstream_chunks": timings.upstream_chunks,
        "upstream_timing_attempt": timings.upstream_timing_attempt,
        "last_upstream_chunk_s": timings.last_upstream_chunk_s,
        "final_upstream_pull_started_s": timings.final_upstream_pull_started_s,
        "upstream_end_s": timings.upstream_end_s,
        "upstream_tail_gap_s": timings.upstream_tail_gap_s,
        "upstream_final_pull_s": timings.upstream_final_pull_s,
    }


def _body_bytes_dict(body: BodyBytesObservation) -> dict[str, JsonValue]:
    return {
        "upstream_request": body.upstream_request,
        "upstream_response": body.upstream_response,
        "downstream_response": body.downstream_response,
    }


def _string(mapping: dict[str, Any], key: str) -> str:
    value = mapping[key]
    return value if isinstance(value, str) else ""


def _bool(mapping: dict[str, Any], key: str) -> bool:
    return mapping[key] is True


def _integer(mapping: dict[str, Any], key: str) -> int:
    value = mapping[key]
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _optional_int(mapping: dict[str, Any], key: str) -> int | None:
    value = mapping[key]
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_number(mapping: dict[str, Any], key: str) -> float | None:
    value = mapping[key]
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _object(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    value = mapping[key]
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _array(mapping: dict[str, Any], key: str) -> list[Any]:
    value = mapping[key]
    return cast(list[Any], value) if isinstance(value, list) else []


def _string_tuple(mapping: dict[str, Any], key: str) -> tuple[str, ...]:
    return tuple(value for value in _array(mapping, key) if isinstance(value, str))


__all__ = [
    "BodyBytesObservation",
    "DeliveryObservation",
    "DeliveryState",
    "FailureCategory",
    "FailureOrigin",
    "FailureSummary",
    "FinalizedRequest",
    "InterruptionKind",
    "InterruptionObservation",
    "InterruptionOrigin",
    "InterruptionPhase",
    "RequestCompletionCoordinator",
    "TimingObservation",
    "safe_exception_graph_notes",
    "safe_exception_notes",
]
