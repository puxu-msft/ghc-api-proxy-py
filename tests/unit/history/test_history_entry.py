from __future__ import annotations

from dataclasses import replace

import pytest

from app.history import (
    CaptureCapabilities,
    HistoryDelivery,
    HistoryEntry,
    HistoryOutcome,
)
from app.history.entry import CaptureAttemptCapabilities
from app.observability.capture_observation import (
    CaptureStatus,
    RawCaptureAttemptObservation,
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
from app.pipeline.response_observation import FrozenJsonObject, freeze_json, thaw_json


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
            capture_ref="session-abc/agent-def.cborseq.zst",
        ),
    )

    entry = HistoryEntry.from_request_facts(facts)

    assert entry.capture.status == "complete"
    assert entry.capture.wire_diagnostic_eligible is True
    assert entry.capture_ref == "session-abc/agent-def.cborseq.zst"
    assert entry.as_dict()["capture"] == {
        "status": "complete",
        "client_request_available": True,
        "client_response_available": True,
        "wire_diagnostic_eligible": True,
        "semantic_replay_eligible": True,
        "live_replay_eligible": True,
        "upstream_attempts": [],
        "capture_ref": "session-abc/agent-def.cborseq.zst",
    }


def test_history_entry_projects_attempt_capability_matrix() -> None:
    facts = replace(
        _facts(
            status="ok",
            delivery=DeliveryState.ACCEPTED,
        ),
        capture=RawCaptureObservation(
            status=CaptureStatus.COMPLETE,
            client_request_available=True,
            client_response_available=True,
            wire_diagnostic_eligible=True,
            semantic_replay_eligible=True,
            live_replay_eligible=True,
            capture_ref="session-abc/agent-def.cborseq.zst",
            upstream_attempts=(
                RawCaptureAttemptObservation(
                    attempt=0,
                    attempt_started=True,
                    request_started=True,
                    request_headers_available=True,
                    request_body_available=True,
                    response_started=True,
                    response_headers_available=True,
                    response_body_available=True,
                    response_complete=True,
                    attempt_complete=True,
                ),
                RawCaptureAttemptObservation(
                    attempt=1,
                    request_headers_available=False,
                    request_body_available=True,
                    response_headers_available=True,
                    response_body_available=False,
                    response_complete=False,
                    attempt_complete=False,
                ),
            ),
        ),
    )

    entry = HistoryEntry.from_request_facts(facts)

    assert entry.capture.upstream_attempts == (
        CaptureAttemptCapabilities(
            attempt=0,
            attempt_started=True,
            request_started=True,
            request_headers_available=True,
            request_body_available=True,
            response_started=True,
            response_headers_available=True,
            response_body_available=True,
            response_complete=True,
            attempt_complete=True,
            wire_diagnostic_eligible=True,
        ),
        CaptureAttemptCapabilities(
            attempt=1,
            request_headers_available=False,
            request_body_available=True,
            response_headers_available=True,
            response_body_available=False,
            response_complete=False,
            attempt_complete=False,
            wire_diagnostic_eligible=False,
        ),
    )
    assert entry.capture.replay_rejection_code(
        "wire_diagnostic",
        attempt_id=0,
    ) is None
    assert (
        entry.capture.replay_rejection_code(
            "wire_diagnostic",
            attempt_id=1,
        )
        == "source_capability_denied"
    )
    capture = entry.as_dict()["capture"]
    assert isinstance(capture, dict)
    assert capture["upstream_attempts"] == [
        {
            "attempt": 0,
            "attempt_started": True,
            "request_started": True,
            "request_headers_available": True,
            "request_body_available": True,
            "response_started": True,
            "response_headers_available": True,
            "response_body_available": True,
            "response_complete": True,
            "attempt_complete": True,
            "wire_diagnostic_eligible": True,
        },
        {
            "attempt": 1,
            "attempt_started": False,
            "request_started": False,
            "request_headers_available": False,
            "request_body_available": True,
            "response_started": False,
            "response_headers_available": True,
            "response_body_available": False,
            "response_complete": False,
            "attempt_complete": False,
            "wire_diagnostic_eligible": False,
        },
    ]


@pytest.mark.parametrize(
    ("capabilities", "mode", "expected_code"),
    [
        (
            CaptureCapabilities(
                status="corrupt",
                semantic_replay_eligible=True,
            ),
            "semantic",
            "source_capture_corrupt",
        ),
        (
            CaptureCapabilities(
                status="incomplete",
                client_request_available=True,
                live_replay_eligible=True,
            ),
            "live",
            None,
        ),
        (
            CaptureCapabilities(status="none"),
            "semantic",
            "source_content_unavailable",
        ),
        (
            CaptureCapabilities(
                status="complete",
                client_request_available=False,
                semantic_replay_eligible=True,
            ),
            "semantic",
            "source_capability_denied",
        ),
        (
            CaptureCapabilities(
                status="complete",
                client_request_available=True,
                wire_diagnostic_eligible=True,
                upstream_attempts=(
                    CaptureAttemptCapabilities(
                        attempt=0,
                        attempt_started=True,
                        request_started=True,
                        request_headers_available=True,
                        request_body_available=True,
                        response_started=True,
                        response_headers_available=True,
                        response_body_available=True,
                        response_complete=True,
                        attempt_complete=True,
                        wire_diagnostic_eligible=True,
                    ),
                ),
            ),
            "wire_diagnostic",
            None,
        ),
    ],
)
def test_capture_capabilities_own_replay_eligibility_decision(
    capabilities: CaptureCapabilities,
    mode: str,
    expected_code: str | None,
) -> None:
    assert (
        capabilities.replay_rejection_code(
            mode,
            attempt_id=0 if mode == "wire_diagnostic" else None,
        )
        == expected_code
    )


def test_history_entry_projects_client_semantic_payloads() -> None:
    facts = replace(
        _facts(status="ok", delivery=DeliveryState.ACCEPTED, downstream_body_bytes=4),
        semantic_request=freeze_json({"messages": [{"role": "user", "content": "hi"}]}),
        semantic_response=freeze_json({"content": [{"type": "text", "text": "hello"}]}),
    )

    entry = HistoryEntry.from_request_facts(facts)

    assert thaw_json(entry.semantic_request) == {
        "messages": [{"role": "user", "content": "hi"}]
    }
    assert thaw_json(entry.semantic_response) == {
        "content": [{"type": "text", "text": "hello"}]
    }
