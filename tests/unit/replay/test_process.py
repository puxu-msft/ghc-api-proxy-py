from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.history import CaptureCapabilities
from app.history.entry import CaptureAttemptCapabilities
from app.observability.raw_capture import RawCaptureStore
from app.replay import (
    ReplayError,
    ReplayMode,
    ReplayProcess,
    ReplayRequest,
    ReplayResult,
    ReplaySourceAuthority,
    ReplaySourceReceipt,
    ReplaySourceSelector,
    ReplayTargetPolicy,
)

_SOURCE_RECEIPTS: dict[tuple[str, str | None], ReplaySourceReceipt] = {}


class _TestSourceAuthority:
    async def __call__(
        self,
        entry_id: str,
        capture_ref: str | None,
    ) -> ReplaySourceReceipt | None:
        return _SOURCE_RECEIPTS.get((entry_id, capture_ref))


@pytest.fixture(autouse=True)
def _install_source_authority(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    _SOURCE_RECEIPTS.clear()
    authority: ReplaySourceAuthority = _TestSourceAuthority()
    monkeypatch.setattr("app.replay.process._DEFAULT_SOURCE_AUTHORITY", authority)
    yield
    _SOURCE_RECEIPTS.clear()


def _capture(
    tmp_path: Path,
    *,
    complete_attempt: bool = True,
    complete_client_request: bool = True,
) -> Path:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="session-replay",
        agent_id=None,
        request_id="source-entry",
        method="POST",
        path="/v1/messages",
        headers={"Authorization": "Bearer source-secret"},
    )
    capture.request_body(b'{"messages":[{"role":"user","content":"hi"}]}')
    capture.request_body_end(complete=complete_client_request)
    capture.upstream_attempt_start(0)
    capture.upstream_request_start(
        "POST",
        "/responses",
        headers={"Authorization": "Bearer source-secret"},
        attempt=0,
    )
    capture.upstream_request_body(b'{"input":"hi"}', attempt=0)
    capture.upstream_response_start(
        200,
        headers={"x-request-id": "upstream"},
        attempt=0,
    )
    capture.upstream_response_body(b'{"output":"hello"}', attempt=0)
    capture.upstream_response_end(complete=complete_attempt, attempt=0)
    capture.upstream_attempt_end(0, complete=complete_attempt)
    capture.client_response_start(200, headers={"content-type": "application/json"})
    capture.client_response_body(b'{"content":"hello"}', more_body=False)
    capture.finish(status_code=200, complete=True)
    store.flush()
    [path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    store.close()
    return path


def _wire_evidence_records(
    *,
    request_headers: object | None,
    response_headers: object | None,
    response_body: bool,
) -> tuple[dict[str, object], ...]:
    request_start: dict[str, object] = {
        "request_id": "source-entry",
        "event": "upstream.request.start",
        "attempt": 0,
    }
    if request_headers is not None:
        request_start["headers"] = request_headers
    response_start: dict[str, object] = {
        "request_id": "source-entry",
        "event": "upstream.response.start",
        "attempt": 0,
        "status_code": 200,
    }
    if response_headers is not None:
        response_start["headers"] = response_headers
    records: list[dict[str, object]] = [
        {
            "request_id": "source-entry",
            "event": "upstream.attempt.start",
            "attempt": 0,
        },
        request_start,
        {
            "request_id": "source-entry",
            "event": "upstream.request.body",
            "attempt": 0,
            "body": b"{}",
        },
        response_start,
    ]
    if response_body:
        records.append(
            {
                "request_id": "source-entry",
                "event": "upstream.response.body",
                "attempt": 0,
                "body": b"{}",
            }
        )
    records.extend(
        [
            {
                "request_id": "source-entry",
                "event": "upstream.response.end",
                "attempt": 0,
                "complete": True,
            },
            {
                "request_id": "source-entry",
                "event": "upstream.attempt.end",
                "attempt": 0,
                "complete": True,
            },
        ]
    )
    return tuple(records)


def _request(
    path: Path | None,
    *,
    mode: ReplayMode,
    selector: ReplaySourceSelector,
    deadline_s: float = 1.0,
    capabilities: CaptureCapabilities | None = None,
) -> ReplayRequest:
    resolved_capabilities = capabilities if capabilities is not None else _capabilities()
    capture_ref = str(path) if path is not None else None
    _SOURCE_RECEIPTS[("source-entry", capture_ref)] = ReplaySourceReceipt(
        entry_id="source-entry",
        capture_path=path,
        capture_ref=capture_ref,
        capabilities=resolved_capabilities,
    )
    return ReplayRequest(
        capture_path=path,
        source_entry_id="source-entry",
        selector=selector,
        mode=mode,
        target_policy=ReplayTargetPolicy.CURRENT_ROUTE,
        deadline_s=deadline_s,
        attempt_id=0 if selector is ReplaySourceSelector.UPSTREAM_ATTEMPT else None,
        original_target="provider/original",
        current_target="provider/current",
        source_capture_ref=capture_ref,
    )


def _capabilities(
    *,
    status: str = "complete",
    client_request_available: bool = True,
    wire_diagnostic_eligible: bool = True,
    semantic_replay_eligible: bool = True,
    live_replay_eligible: bool = True,
    upstream_attempts: tuple[CaptureAttemptCapabilities, ...] | None = None,
) -> CaptureCapabilities:
    return CaptureCapabilities(
        status=status,
        client_request_available=client_request_available,
        client_response_available=True,
        wire_diagnostic_eligible=wire_diagnostic_eligible,
        semantic_replay_eligible=semantic_replay_eligible,
        live_replay_eligible=live_replay_eligible,
        upstream_attempts=upstream_attempts
        if upstream_attempts is not None
        else (
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
    )


@pytest.mark.asyncio
async def test_replay_requires_capture_and_never_falls_back_to_history() -> None:
    process = ReplayProcess(max_deadline_s=5)

    with pytest.raises(ReplayError) as raised:
        await process.run(
            _request(
                None,
                mode=ReplayMode.SEMANTIC,
                selector=ReplaySourceSelector.CLIENT_REQUEST,
            )
        )

    assert raised.value.code == "source_content_unavailable"
    assert raised.value.not_started is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "selector", "capabilities"),
    [
        (
            ReplayMode.WIRE_DIAGNOSTIC,
            ReplaySourceSelector.UPSTREAM_ATTEMPT,
            _capabilities(wire_diagnostic_eligible=False),
        ),
        (
            ReplayMode.SEMANTIC,
            ReplaySourceSelector.CLIENT_REQUEST,
            _capabilities(semantic_replay_eligible=False),
        ),
        (
            ReplayMode.LIVE,
            ReplaySourceSelector.CLIENT_REQUEST,
            _capabilities(live_replay_eligible=False),
        ),
    ],
)
async def test_replay_capability_is_authoritative_over_readable_capture(
    tmp_path: Path,
    mode: ReplayMode,
    selector: ReplaySourceSelector,
    capabilities: CaptureCapabilities,
) -> None:
    path = _capture(tmp_path)
    process = ReplayProcess(max_deadline_s=5)

    async def must_not_run(_: Any) -> dict[str, str]:
        raise AssertionError("capability denial must not execute replay")

    with pytest.raises(ReplayError) as raised:
        await process.run(
            _request(path, mode=mode, selector=selector, capabilities=capabilities),
            executor=must_not_run,
        )

    assert raised.value.code == "source_capability_denied"
    assert '"messages"' not in raised.value.message
    assert "Authorization" not in raised.value.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        ("corrupt", "source_capture_corrupt"),
    ],
)
async def test_replay_rejects_noncomplete_history_capability_stably(
    tmp_path: Path,
    status: str,
    expected_code: str,
) -> None:
    process = ReplayProcess(max_deadline_s=5)

    with pytest.raises(ReplayError) as raised:
        await process.run(
            _request(
                _capture(tmp_path),
                mode=ReplayMode.SEMANTIC,
                selector=ReplaySourceSelector.CLIENT_REQUEST,
                capabilities=_capabilities(
                    status=status,
                    semantic_replay_eligible=True,
                ),
            )
        )

    assert raised.value.code == expected_code
    assert raised.value.not_started is True


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ReplayMode.SEMANTIC, ReplayMode.LIVE])
async def test_incomplete_capture_allows_eligible_semantic_and_live_replay(
    tmp_path: Path,
    mode: ReplayMode,
) -> None:
    path = _capture(tmp_path)

    async def execute(_: Any) -> dict[str, str]:
        return {"outcome": "completed"}

    result = await ReplayProcess(max_deadline_s=5).run(
        _request(
            path,
            mode=mode,
            selector=ReplaySourceSelector.CLIENT_REQUEST,
            capabilities=_capabilities(status="incomplete"),
        ),
        executor=execute,
    )

    assert result.outcome == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ReplayMode.SEMANTIC, ReplayMode.LIVE])
async def test_incomplete_capture_denies_ineligible_semantic_and_live_replay(
    tmp_path: Path,
    mode: ReplayMode,
) -> None:
    capabilities = _capabilities(
        status="incomplete",
        semantic_replay_eligible=mode is not ReplayMode.SEMANTIC,
        live_replay_eligible=mode is not ReplayMode.LIVE,
    )

    with pytest.raises(ReplayError) as raised:
        await ReplayProcess(max_deadline_s=5).run(
            _request(
                _capture(tmp_path),
                mode=mode,
                selector=ReplaySourceSelector.CLIENT_REQUEST,
                capabilities=capabilities,
            )
        )

    assert raised.value.code == "source_capability_denied"


@pytest.mark.asyncio
async def test_replay_requires_configured_source_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.replay.process._DEFAULT_SOURCE_AUTHORITY", None)
    process = ReplayProcess(max_deadline_s=5)
    request = _request(
        _capture(tmp_path),
        mode=ReplayMode.SEMANTIC,
        selector=ReplaySourceSelector.CLIENT_REQUEST,
    )

    with pytest.raises(ReplayError) as raised:
        await process.run(request)

    assert raised.value.code == "source_authority_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ReplayMode.SEMANTIC, ReplayMode.LIVE])
async def test_semantic_and_live_replay_require_complete_source_request(
    tmp_path: Path,
    mode: ReplayMode,
) -> None:
    process = ReplayProcess(max_deadline_s=5)

    with pytest.raises(ReplayError) as raised:
        await process.run(
            _request(
                _capture(tmp_path, complete_client_request=False),
                mode=mode,
                selector=ReplaySourceSelector.CLIENT_REQUEST,
            )
        )

    assert raised.value.code == "source_content_unavailable"


@pytest.mark.asyncio
async def test_wire_diagnostic_reads_selected_attempt_without_executor(
    tmp_path: Path,
) -> None:
    path = _capture(tmp_path)
    process = ReplayProcess(max_deadline_s=5)

    async def must_not_run(_: Any) -> dict[str, str]:
        raise AssertionError("wire diagnostic must remain offline")

    result = await process.run(
        _request(
            path,
            mode=ReplayMode.WIRE_DIAGNOSTIC,
            selector=ReplaySourceSelector.UPSTREAM_ATTEMPT,
        ),
        executor=must_not_run,
    )

    assert result.outcome == "completed"
    assert result.request_id.startswith("replay-")
    assert result.source_entry_id == "source-entry"
    assert {record["event"] for record in result.diagnostic_records} == {
        "upstream.attempt.start",
        "upstream.request.start",
        "upstream.request.body",
        "upstream.response.start",
        "upstream.response.body",
        "upstream.response.end",
        "upstream.attempt.end",
    }
    assert all(
        set(record)
        <= {"event", "attempt", "status_code", "complete", "body_bytes"}
        for record in result.diagnostic_records
    )
    serialized = json.dumps(result.as_dict())
    assert '"body":' not in serialized
    assert '"headers":' not in serialized
    assert "hello" not in serialized
    assert "x-request-id" not in serialized


@pytest.mark.asyncio
async def test_semantic_replay_uses_current_target_and_returns_client_actions(
    tmp_path: Path,
) -> None:
    path = _capture(tmp_path)
    process = ReplayProcess(max_deadline_s=5)
    seen: dict[str, Any] = {}

    async def execute(execution: Any) -> dict[str, Any]:
        seen["execution"] = execution
        return {
            "outcome": "completed",
            "client_actions": [{"type": "function_call", "name": "Bash"}],
        }

    result = await process.run(
        _request(
            path,
            mode=ReplayMode.SEMANTIC,
            selector=ReplaySourceSelector.CLIENT_REQUEST,
        ),
        executor=execute,
    )

    execution = seen["execution"]
    assert execution.target == "provider/current"
    assert execution.client_request["messages"][0]["content"] == "hi"
    assert result.client_actions == ({"type": "function_call", "name": "Bash"},)


@pytest.mark.asyncio
async def test_wire_diagnostic_rejects_incomplete_attempt(tmp_path: Path) -> None:
    path = _capture(tmp_path, complete_attempt=False)
    process = ReplayProcess(max_deadline_s=5)

    with pytest.raises(ReplayError) as raised:
        await process.run(
            _request(
                path,
                mode=ReplayMode.WIRE_DIAGNOSTIC,
                selector=ReplaySourceSelector.UPSTREAM_ATTEMPT,
                capabilities=_capabilities(
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
                            response_complete=False,
                            attempt_complete=False,
                        ),
                    )
                ),
            )
        )

    assert raised.value.code == "source_capability_denied"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_headers", "response_headers", "response_body"),
    [
        (None, {}, True),
        ({}, None, True),
        ({}, {}, False),
        ("invalid", {}, True),
        ({}, ["invalid"], True),
    ],
)
async def test_wire_diagnostic_rejects_incomplete_header_or_body_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request_headers: object | None,
    response_headers: object | None,
    response_body: bool,
) -> None:
    def reader(_: Path) -> Iterator[dict[str, object]]:
        return iter(
            _wire_evidence_records(
                request_headers=request_headers,
                response_headers=response_headers,
                response_body=response_body,
            )
        )

    monkeypatch.setattr("app.replay.process.iter_raw_capture_records", reader)
    request_headers_available = isinstance(request_headers, Mapping)
    response_headers_available = isinstance(response_headers, Mapping)
    with pytest.raises(ReplayError) as raised:
        await ReplayProcess(max_deadline_s=5).run(
            _request(
                tmp_path / "evidence.capture",
                mode=ReplayMode.WIRE_DIAGNOSTIC,
                selector=ReplaySourceSelector.UPSTREAM_ATTEMPT,
                capabilities=_capabilities(
                    upstream_attempts=(
                        CaptureAttemptCapabilities(
                            attempt=0,
                            attempt_started=True,
                            request_started=True,
                            request_headers_available=request_headers_available,
                            request_body_available=True,
                            response_started=True,
                            response_headers_available=response_headers_available,
                            response_body_available=response_body,
                            response_complete=True,
                            attempt_complete=True,
                        ),
                    )
                ),
            )
        )

    assert raised.value.code == "source_capability_denied"


@pytest.mark.asyncio
async def test_wire_diagnostic_rejects_unknown_attempt_after_capability_gate(
    tmp_path: Path,
) -> None:
    process = ReplayProcess(max_deadline_s=5)
    request = _request(
        _capture(tmp_path),
        mode=ReplayMode.WIRE_DIAGNOSTIC,
        selector=ReplaySourceSelector.UPSTREAM_ATTEMPT,
    )
    request = ReplayRequest(
        capture_path=request.capture_path,
        source_entry_id=request.source_entry_id,
        selector=request.selector,
        mode=request.mode,
        target_policy=request.target_policy,
        deadline_s=request.deadline_s,
        attempt_id=99,
        original_target=request.original_target,
        current_target=request.current_target,
        source_capture_ref=request.source_capture_ref,
    )

    with pytest.raises(ReplayError) as raised:
        await process.run(request)

    assert raised.value.code == "source_capability_denied"


@pytest.mark.asyncio
async def test_wire_diagnostic_rejects_attempt_without_granted_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(
        _capture(tmp_path),
        mode=ReplayMode.WIRE_DIAGNOSTIC,
        selector=ReplaySourceSelector.UPSTREAM_ATTEMPT,
        capabilities=_capabilities(
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
                CaptureAttemptCapabilities(
                    attempt=1,
                    attempt_started=True,
                    request_started=True,
                    request_headers_available=False,
                    request_body_available=False,
                    response_started=True,
                    response_headers_available=False,
                    response_body_available=False,
                    response_complete=False,
                    attempt_complete=False,
                    wire_diagnostic_eligible=False,
                ),
            )
        ),
    )
    request = replace(request, attempt_id=1)

    def must_not_read(_: Path) -> None:
        raise AssertionError("ungranted attempt must not read capture")

    monkeypatch.setattr("app.replay.process.iter_raw_capture_records", must_not_read)
    with pytest.raises(ReplayError) as raised:
        await ReplayProcess(max_deadline_s=5).run(request)

    assert raised.value.code == "source_capability_denied"


@pytest.mark.asyncio
async def test_replay_rejects_wrong_mode_selector_before_reading_capture() -> None:
    process = ReplayProcess(max_deadline_s=5)

    with pytest.raises(ReplayError) as raised:
        await process.run(
            _request(
                None,
                mode=ReplayMode.LIVE,
                selector=ReplaySourceSelector.UPSTREAM_ATTEMPT,
            )
        )

    assert raised.value.code == "invalid_source_selector"


@pytest.mark.asyncio
@pytest.mark.parametrize("deadline_s", [float("nan"), float("inf"), float("-inf")])
async def test_replay_rejects_nonfinite_deadline_before_reader_or_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    deadline_s: float,
) -> None:
    process = ReplayProcess(max_deadline_s=5)

    def must_not_read(_: Path) -> None:
        raise AssertionError("invalid deadline must not read capture")

    async def must_not_execute(_: Any) -> dict[str, str]:
        raise AssertionError("invalid deadline must not execute replay")

    monkeypatch.setattr("app.replay.process.iter_raw_capture_records", must_not_read)
    with pytest.raises(ReplayError) as raised:
        await process.run(
            _request(
                _capture(tmp_path),
                mode=ReplayMode.LIVE,
                selector=ReplaySourceSelector.CLIENT_REQUEST,
                deadline_s=deadline_s,
            ),
            executor=must_not_execute,
        )

    assert raised.value.code == "invalid_deadline"
    assert raised.value.not_started is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "selector"),
    [
        (ReplayMode.WIRE_DIAGNOSTIC, ReplaySourceSelector.UPSTREAM_ATTEMPT),
        (ReplayMode.SEMANTIC, ReplaySourceSelector.CLIENT_REQUEST),
    ],
)
async def test_replay_enforces_deadline_during_source_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ReplayMode,
    selector: ReplaySourceSelector,
) -> None:
    def slow_reader(_: Path) -> object:
        time.sleep(0.3)
        return iter(())

    async def must_not_execute(_: Any) -> dict[str, str]:
        raise AssertionError("expired source read must not execute replay")

    monkeypatch.setattr("app.replay.process.iter_raw_capture_records", slow_reader)
    started = time.monotonic()
    with pytest.raises(ReplayError) as raised:
        await ReplayProcess(max_deadline_s=5).run(
            _request(
                tmp_path / "slow.capture",
                mode=mode,
                selector=selector,
                deadline_s=0.02,
            ),
            executor=must_not_execute,
        )

    assert raised.value.code == "deadline_exceeded"
    assert raised.value.not_started is True
    assert time.monotonic() - started < 0.2


@pytest.mark.asyncio
async def test_replay_enforces_deadline_during_post_read_many_attempt_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt_reads = 0

    class CountingAttemptRecord(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            nonlocal attempt_reads
            if key == "attempt":
                attempt_reads += 1
            return super().get(key, default)

    records = tuple(
        CountingAttemptRecord(
            {
                "request_id": "source-entry",
                "event": "upstream.attempt.start",
                "attempt": attempt,
            }
        )
        for attempt in range(3_500)
    )
    reader_returned = False
    deadline_checks: list[float] = []
    checks_before_attempt_grouping = 2 * len(records) + 2

    def returned_reader(
        _: Path,
        __: str,
        *,
        deadline_at: float,
    ) -> tuple[Mapping[str, Any], ...]:
        nonlocal reader_returned
        reader_returned = True
        return records

    def expire_during_attempt_grouping(deadline_at: float) -> float:
        deadline_checks.append(deadline_at)
        if len(deadline_checks) > checks_before_attempt_grouping:
            raise ReplayError("deadline_exceeded", "replay deadline exceeded")
        return 1.0

    monkeypatch.setattr("app.replay.process._read_source_records", returned_reader)
    monkeypatch.setattr(
        "app.replay.process._require_remaining_deadline",
        expire_during_attempt_grouping,
    )
    with pytest.raises(ReplayError) as raised:
        await ReplayProcess(max_deadline_s=5).run(
            _request(
                tmp_path / "many-attempts.capture",
                mode=ReplayMode.WIRE_DIAGNOSTIC,
                selector=ReplaySourceSelector.UPSTREAM_ATTEMPT,
                deadline_s=0.2,
            )
        )

    assert raised.value.code == "deadline_exceeded"
    assert raised.value.not_started is True
    assert reader_returned is True
    assert len(set(deadline_checks)) == 1
    assert attempt_reads == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ReplayMode.SEMANTIC, ReplayMode.LIVE])
async def test_replay_enforces_deadline_during_client_request_decode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ReplayMode,
) -> None:
    original_loads = json.loads

    def slow_loads(value: str | bytes | bytearray) -> Any:
        time.sleep(0.06)
        return original_loads(value)

    async def must_not_execute(_: Any) -> dict[str, str]:
        raise AssertionError("expired decode must not execute replay")

    monkeypatch.setattr("app.replay.process.json.loads", slow_loads)
    with pytest.raises(ReplayError) as raised:
        await ReplayProcess(max_deadline_s=5).run(
            _request(
                _capture(tmp_path),
                mode=mode,
                selector=ReplaySourceSelector.CLIENT_REQUEST,
                deadline_s=0.05,
            ),
            executor=must_not_execute,
        )

    assert raised.value.code == "deadline_exceeded"
    assert raised.value.not_started is True


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ReplayMode.SEMANTIC, ReplayMode.LIVE])
async def test_semantic_and_live_results_exclude_opaque_executor_payloads(
    tmp_path: Path,
    mode: ReplayMode,
) -> None:
    async def execute(_: Any) -> dict[str, Any]:
        return {
            "outcome": "completed",
            "body": "executor-body-marker",
            "headers": {"x-marker": "executor-header-marker"},
            "credentials": "executor-credential-marker",
            "transport": {"payload": "executor-transport-marker"},
            "client_actions": [
                {
                    "type": "function_call",
                    "name": "Bash",
                    "arguments": "executor-action-marker",
                }
            ],
        }

    result = await ReplayProcess(max_deadline_s=5).run(
        _request(
            _capture(tmp_path),
            mode=mode,
            selector=ReplaySourceSelector.CLIENT_REQUEST,
        ),
        executor=execute,
    )

    assert result.output == {"outcome": "completed"}
    assert result.client_actions == ({"type": "function_call", "name": "Bash"},)
    serialized = json.dumps(result.as_dict())
    assert '"body":' not in serialized
    assert '"headers":' not in serialized
    assert '"credentials":' not in serialized
    assert '"transport":' not in serialized
    assert "executor-body-marker" not in serialized
    assert "executor-header-marker" not in serialized
    assert "executor-credential-marker" not in serialized
    assert "executor-transport-marker" not in serialized
    assert "executor-action-marker" not in serialized


def test_replay_result_as_dict_sanitizes_directly_constructed_nested_payloads() -> None:
    result = ReplayResult(
        replay_id="replay-1",
        request_id="request-1",
        mode=ReplayMode.WIRE_DIAGNOSTIC,
        selector=ReplaySourceSelector.UPSTREAM_ATTEMPT,
        source_entry_id="source-entry",
        source_capture_ref="capture-ref",
        target_policy=ReplayTargetPolicy.CURRENT_ROUTE,
        target="provider/current",
        started_at="2026-09-16T00:00:00.000Z",
        finished_at="2026-09-16T00:00:01.000Z",
        outcome="completed",
        error_code=None,
        client_actions=(
            {
                "type": "function_call",
                "name": "Bash",
                "arguments": {"token": "direct-action-marker"},
            },
        ),
        output={
            "outcome": "completed",
            "body": {"nested": "direct-body-marker"},
            "headers": {"authorization": "direct-header-marker"},
            "credentials": "direct-credential-marker",
        },
        diagnostic_records=(
            {
                "event": "upstream.response.body",
                "attempt": 0,
                "body": b"direct-diagnostic-body-marker",
                "headers": {"x-marker": "direct-diagnostic-header-marker"},
            },
        ),
    )

    serialized = json.dumps(result.as_dict())

    assert '"body":' not in serialized
    assert '"headers":' not in serialized
    assert '"credentials":' not in serialized
    assert "direct-body-marker" not in serialized
    assert "direct-header-marker" not in serialized
    assert "direct-credential-marker" not in serialized
    assert "direct-action-marker" not in serialized
    assert "direct-diagnostic-body-marker" not in serialized
    assert "direct-diagnostic-header-marker" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["entry_id", "capture_ref"])
async def test_replay_rejects_mismatched_authority_receipt_before_reader_or_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    path = _capture(tmp_path)
    request = _request(
        path,
        mode=ReplayMode.LIVE,
        selector=ReplaySourceSelector.CLIENT_REQUEST,
    )
    receipt = _SOURCE_RECEIPTS[(request.source_entry_id, request.source_capture_ref)]
    if field == "entry_id":
        receipt = replace(receipt, entry_id="another-entry")
    else:
        receipt = replace(receipt, capture_ref="another.capture")
    _SOURCE_RECEIPTS[(request.source_entry_id, request.source_capture_ref)] = receipt

    def must_not_read(_: Path) -> None:
        raise AssertionError("mismatched authority receipt must not read capture")

    async def must_not_execute(_: Any) -> dict[str, str]:
        raise AssertionError("mismatched grant must not execute replay")

    monkeypatch.setattr("app.replay.process.iter_raw_capture_records", must_not_read)
    with pytest.raises(ReplayError) as raised:
        await ReplayProcess(max_deadline_s=5).run(
            request,
            executor=must_not_execute,
        )

    assert raised.value.code == "source_capability_mismatch"
    assert raised.value.not_started is True


@pytest.mark.asyncio
async def test_replay_rejects_history_source_without_capture_before_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def must_not_read(_: Path) -> None:
        raise AssertionError("missing capture must not read capture")

    monkeypatch.setattr("app.replay.process.iter_raw_capture_records", must_not_read)
    with pytest.raises(ReplayError) as raised:
        await ReplayProcess(max_deadline_s=5).run(
            _request(
                None,
                mode=ReplayMode.SEMANTIC,
                selector=ReplaySourceSelector.CLIENT_REQUEST,
                capabilities=_capabilities(status="none"),
            )
        )

    assert raised.value.code == "source_content_unavailable"
    assert raised.value.not_started is True


@pytest.mark.asyncio
async def test_replay_deadline_is_bounded_and_reported(tmp_path: Path) -> None:
    path = _capture(tmp_path)
    process = ReplayProcess(max_deadline_s=5)

    async def slow(_: Any) -> dict[str, str]:
        await asyncio.sleep(0.2)
        return {"outcome": "completed"}

    result = await process.run(
        _request(
            path,
            mode=ReplayMode.LIVE,
            selector=ReplaySourceSelector.CLIENT_REQUEST,
            deadline_s=0.1,
        ),
        executor=slow,
    )

    assert result.outcome == "deadline_exceeded"
    assert result.error_code == "deadline_exceeded"
