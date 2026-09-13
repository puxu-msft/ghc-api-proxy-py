from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.observability.raw_capture import RawCaptureStore
from app.replay import (
    ReplayError,
    ReplayMode,
    ReplayProcess,
    ReplayRequest,
    ReplaySourceSelector,
    ReplayTargetPolicy,
)


def _capture(tmp_path: Path, *, complete_attempt: bool = True) -> Path:
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
    capture.request_body_end(complete=True)
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
    capture.client_response_start(200, headers={"content-type": "application/json"})
    capture.client_response_body(b'{"content":"hello"}', more_body=False)
    capture.finish(status_code=200, complete=True)
    store.flush()
    [path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    store.close()
    return path


def _request(
    path: Path | None,
    *,
    mode: ReplayMode,
    selector: ReplaySourceSelector,
    deadline_s: float = 1.0,
) -> ReplayRequest:
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
        "upstream.request.start",
        "upstream.request.body",
        "upstream.response.start",
        "upstream.response.body",
        "upstream.response.end",
    }


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
            )
        )

    assert raised.value.code == "source_evidence_unavailable"


@pytest.mark.asyncio
async def test_replay_deadline_is_bounded_and_reported(tmp_path: Path) -> None:
    path = _capture(tmp_path)
    process = ReplayProcess(max_deadline_s=5)

    async def slow(_: Any) -> dict[str, str]:
        await asyncio.sleep(0.05)
        return {"outcome": "completed"}

    result = await process.run(
        _request(
            path,
            mode=ReplayMode.LIVE,
            selector=ReplaySourceSelector.CLIENT_REQUEST,
            deadline_s=0.001,
        ),
        executor=slow,
    )

    assert result.outcome == "deadline_exceeded"
    assert result.error_code == "deadline_exceeded"
