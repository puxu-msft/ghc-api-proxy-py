from __future__ import annotations

from dataclasses import replace

from app.history import HistoryDelivery, HistoryEntry, HistoryOutcome
from app.observability.capture_observation import (
    CaptureStatus,
    RawCaptureObservation,
)
from app.observability.request_completion import (
    BodyBytesObservation,
    DeliveryObservation,
    DeliveryState,
    RequestFacts,
    TimingObservation,
)
from app.pipeline.delivery.assembling import ReplyDialect
from app.pipeline.response_observation import FrozenJsonObject, freeze_json


def _facts(
    *,
    status: str,
    delivery: DeliveryState,
    downstream_body_bytes: int | None = None,
) -> RequestFacts:
    legacy = freeze_json(
        {
            "method": "POST",
            "path": "/v1/messages",
            "request_id": "req_history_1",
            "message_id": "",
            "inbound_format": "anthropic-messages",
            "count_tokens": False,
            "client_protocol": "H1",
            "upstream_protocol": "H1",
            "requested_model": "claude-opus-5",
            "model": "claude-opus-5",
            "provider_name": "ghc",
            "reasoning_effort": None,
            "status_code": 200 if status != "fail" else 502,
            "started_at": "2026-09-13T00:00:00.000Z",
            "duration_s": 1.0,
            "last_retry_duration_s": None,
            "first_upstream_byte_s": 0.1,
            "upstream_max_gap_s": None,
            "upstream_chunks": 1,
            "bytes_in": 10,
            "bytes_out": 20,
            "usage": {"input_tokens": 3, "output_tokens": 2},
            "terminal_seen": True,
            "stop_reason": "end_turn",
            "terminal_status": "",
            "client_actions": [],
            "client_action_classification_complete": True,
            "blocks": 1,
            "tools": [],
            "thinking": [],
            "count_provider": "",
            "count_provider_reason": "",
            "dialect": ReplyDialect.ANTHROPIC.value,
            "attempts": 1,
            "replaced_failures": [],
            "tore_after_terminal": "",
            "detail": "",
            "upstream_conn": {},
            "losses": [],
            "facts": [],
        }
    )
    assert isinstance(legacy, FrozenJsonObject)
    return RequestFacts(
        status=status,  # type: ignore[arg-type]
        at="2026-09-13T00:00:01.000Z",
        legacy=legacy,
        response=None,
        delivery=DeliveryObservation(
            state=delivery,
            unit="body" if delivery is DeliveryState.ACCEPTED else None,
            intended_http_status=200,
            http_start_accepted=delivery is not DeliveryState.NOT_STARTED,
            downstream_body_bytes=downstream_body_bytes,
            failure=None,
            post_delivery_failure=None,
            additional_failures=(),
        ),
        timings=TimingObservation(
            response_ready_s=0.1,
            finalized_s=1.0,
            first_upstream_byte_s=0.1,
            upstream_max_gap_s=None,
            upstream_chunks=1,
        ),
        body_bytes=BodyBytesObservation(10, 20, downstream_body_bytes),
        upstream_body_attempts=(),
        session_id="session-1",
        agent_id="agent-1",
    )


def test_history_entry_projects_completed_request_facts() -> None:
    entry = HistoryEntry.from_request_facts(
        _facts(status="ok", delivery=DeliveryState.ACCEPTED, downstream_body_bytes=20)
    )

    assert entry.outcome is HistoryOutcome.COMPLETED
    assert entry.delivery is HistoryDelivery.COMPLETE
    assert entry.session_id == "session-1"
    assert entry.agent_id == "agent-1"
    assert entry.capture.status == "none"
    assert entry.as_dict()["request_id"] == "req_history_1"


def test_history_entry_distinguishes_aborted_partial_delivery() -> None:
    entry = HistoryEntry.from_request_facts(
        _facts(status="gone", delivery=DeliveryState.STARTED, downstream_body_bytes=4)
    )

    assert entry.outcome is HistoryOutcome.ABORTED
    assert entry.delivery is HistoryDelivery.PARTIAL


def test_history_entry_distinguishes_failed_uncertain_delivery() -> None:
    entry = HistoryEntry.from_request_facts(
        _facts(status="fail", delivery=DeliveryState.STARTED)
    )

    assert entry.outcome is HistoryOutcome.FAILED
    assert entry.delivery is HistoryDelivery.UNCERTAIN


def test_history_entry_projects_capture_capabilities_without_raw_body() -> None:
    facts = replace(
        _facts(status="ok", delivery=DeliveryState.ACCEPTED, downstream_body_bytes=4),
        capture=RawCaptureObservation(
            status=CaptureStatus.COMPLETE,
            client_request_available=True,
            client_response_available=True,
            wire_diagnostic_eligible=True,
            semantic_replay_eligible=True,
            live_replay_eligible=True,
        ),
    )

    entry = HistoryEntry.from_request_facts(facts)

    assert entry.capture.status == "complete"
    assert entry.capture.wire_diagnostic_eligible is True
    assert entry.as_dict()["capture"]["capture_ref"] is None
