from __future__ import annotations

from pathlib import Path

import httpx2

from app.observability.raw_capture import RawCaptureStore, iter_raw_capture_records


def test_selected_capture_preserves_full_header_values(tmp_path: Path) -> None:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="session-headers",
        agent_id=None,
        request_id="request-headers",
        method="POST",
        path="/v1/messages",
        headers={
            "Authorization": "Bearer request-secret",
            "X-Unlisted": "request-marker",
        },
    )
    capture.upstream_request_start(
        "POST",
        "/alpha/generate",
        headers={
            "Authorization": "Bearer upstream-secret",
            "X-Unlisted": "upstream-marker",
        },
        attempt=0,
    )
    capture.client_response_start(
        200,
        headers={"X-Unlisted": "client-marker"},
    )
    capture.finish(status_code=200, complete=True)
    store.flush()

    [path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    records = list(iter_raw_capture_records(path))
    starts = {
        record["event"]: record
        for record in records
        if str(record["event"]).endswith(".start")
    }

    assert starts["request.start"]["headers"] == [
        ["authorization", "Bearer request-secret"],
        ["x-unlisted", "request-marker"],
    ]
    assert starts["upstream.request.start"]["headers"] == [
        ["authorization", "Bearer upstream-secret"],
        ["x-unlisted", "upstream-marker"],
    ]
    assert starts["client.response.start"]["headers"] == [
        ["x-unlisted", "client-marker"],
    ]
    store.close()


def test_selected_capture_preserves_duplicate_header_pairs(tmp_path: Path) -> None:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="session-duplicate-headers",
        agent_id=None,
        request_id="request-duplicate-headers",
        method="POST",
        path="/v1/messages",
    )
    capture.upstream_response_start(
        200,
        headers=httpx2.Headers(
            [
                (b"set-cookie", b"first=1"),
                (b"set-cookie", b"second=2"),
            ]
        ),
        attempt=0,
    )
    capture.finish(status_code=200, complete=True)
    store.flush()

    [path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    response_start = next(
        record
        for record in iter_raw_capture_records(path)
        if record["event"] == "upstream.response.start"
    )
    assert response_start["headers"] == [
        ["set-cookie", "first=1"],
        ["set-cookie", "second=2"],
    ]
    store.close()
