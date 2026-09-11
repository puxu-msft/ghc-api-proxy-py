import hashlib
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Full
from typing import Any, cast

import cbor2
import httpx2
import pytest
import zstandard

from app.config.schema import OpenAICompatibleProviderConfig, XingchenProviderConfig
from app.model_provider.codebuddy_client.client import CodebuddyClient
from app.model_provider.codebuddy_client.config import CodebuddyClientConfig
from app.model_provider.openai_compatible.client import OpenAICompatibleClient
from app.model_provider.types import ModelEndpoint
from app.model_provider.xingchen.client import XingchenClient
from app.observability.raw_capture import (
    RawCaptureStore,
    activate_pending_upstream_capture,
    iter_raw_capture_records,
    observe_active_upstream_request,
    pending_upstream_capture,
)
from app.pipeline.direct_driver.base import capture_returned_upstream_response


def _records(path: Path) -> list[dict[str, object]]:
    return list(iter_raw_capture_records(path))


class _ShortWritingStream:
    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def __enter__(self) -> _ShortWritingStream:
        return self

    def __exit__(self, *args: object) -> None:
        self._stream.close()

    def write(self, value: bytes) -> int:
        return cast(int, self._stream.write(value[: max(1, len(value) // 2)]))


def _install_one_short_capture_write(monkeypatch: pytest.MonkeyPatch) -> None:
    original_open = cast(Any, Path.open)
    short_write_pending = True

    def open_with_one_short_write(path: Path, *args: Any, **kwargs: Any) -> Any:
        nonlocal short_write_pending
        stream: Any = original_open(path, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if (
            short_write_pending
            and mode == "ab"
            and path.name.endswith(".cborseq.zst")
        ):
            short_write_pending = False
            return _ShortWritingStream(stream)
        return stream

    monkeypatch.setattr(Path, "open", open_with_one_short_write)


def test_transport_boundary_observer_requires_active_scope_and_deduplicates_attempts(
    tmp_path: Path,
) -> None:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-transport-boundary",
        method="POST",
        path="/v1/messages",
    )

    observe_active_upstream_request(
        httpx2.Request("POST", "https://provider.example/outside", content=b"outside")
    )
    for attempt, body in ((0, b"transport bytes"), (1, b"")):
        request = httpx2.Request(
            "POST",
            f"https://provider.example/attempt-{attempt}",
            content=body,
        )
        with (
            pending_upstream_capture(capture, attempt),
            activate_pending_upstream_capture(),
        ):
            observe_active_upstream_request(request)
            observe_active_upstream_request(request)
        capture.upstream_request_body(b"response-or-error-fallback", attempt=attempt)

    observe_active_upstream_request(
        httpx2.Request("POST", "https://provider.example/after", content=b"after")
    )
    capture.finish(status_code=200, complete=True)
    store.flush()

    [capture_path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    assert [
        (record["attempt"], record["body"])
        for record in _records(capture_path)
        if record["event"] == "upstream.request.body"
    ] == [(0, b"transport bytes"), (1, b"")]
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("client_kind", ["openai-compatible", "xingchen", "codebuddy"])
async def test_non_ghc_direct_clients_observe_active_capture_at_transport_boundary(
    tmp_path: Path,
    client_kind: str,
) -> None:
    transport_bodies: list[bytes] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        transport_bodies.append(request.content)
        if client_kind == "codebuddy":
            return httpx2.Response(
                200,
                content=b"data: [DONE]\n\n",
                headers={"content-type": "text/event-stream"},
            )
        return httpx2.Response(200, json={"ok": True})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    if client_kind == "openai-compatible":
        client = OpenAICompatibleClient(
            http_client,
            OpenAICompatibleProviderConfig.model_validate(
                {
                    "type": "sub2api",
                    "api_base_url": "https://openai-compatible.example/v1",
                    "models": ["test-model"],
                    "openai_responses_endpoint": True,
                }
            ),
        )

        async def send() -> httpx2.Response:
            return await client.send(
                ModelEndpoint.OPENAI_RESPONSES,
                {"model": "test-model", "input": []},
            )

    elif client_kind == "xingchen":
        client = XingchenClient(
            http_client,
            XingchenProviderConfig.model_validate(
                {
                    "type": "xingchen",
                    "models": ["test-model"],
                    "gateway_api_key": "gateway-key",
                    "x_token": "prefix:header.payload.signature",
                    "device_id": "device-id",
                    "install_id": "install-id",
                }
            ),
        )

        async def send() -> httpx2.Response:
            return await client.send_chat_completions({"model": "test-model"})

    else:
        class Credentials:
            async def request_headers(self) -> dict[str, str]:
                return {"Authorization": "Bearer test"}

        client = CodebuddyClient(
            CodebuddyClientConfig(api_base_url_override="https://codebuddy.example"),
            cast(Any, Credentials()),
            http_client=http_client,
        )

        async def send() -> httpx2.Response:
            return await client.send_chat_completions(
                {"model": "test-model"},
                stream=True,
            )

    store = RawCaptureStore(tmp_path / client_kind)
    capture = store.start(
        session_id=f"{client_kind}-session",
        agent_id=f"{client_kind}-agent",
        request_id=f"{client_kind}-request",
        method="POST",
        path="/test",
    )
    try:
        with pending_upstream_capture(capture, 0):
            response = await send()
        await response.aclose()
        capture.finish(status_code=200, complete=True)
        store.flush()
        [capture_path] = (tmp_path / client_kind).glob("session-*/agent-*.cborseq.zst")
        captured_bodies = [
            (record["attempt"], record["body"])
            for record in _records(capture_path)
            if record["event"] == "upstream.request.body"
        ]
    finally:
        store.close()
        await http_client.aclose()

    assert len(transport_bodies) == 1
    assert transport_bodies[0]
    assert captured_bodies == [(0, transport_bodies[0])]


def test_a_session_agent_capture_appends_request_and_response_events(tmp_path: Path) -> None:
    store = RawCaptureStore(tmp_path, compression_level=3)
    capture = store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-1",
        method="POST",
        path="/v1/messages",
    )

    capture.request_body(b'{"prompt":"hello"}')
    capture.upstream_request_body(b'{"input":[{"type":"message"}]}')
    capture.upstream_response_start(200)
    capture.upstream_response_body(b'event: response.created\n\n')
    capture.upstream_response_end()
    capture.client_response_start(200)
    capture.client_response_body(b'event: message_start\n\n', more_body=True)
    capture.client_response_body(b'event: message_stop\n\n', more_body=False)
    capture.finish(status_code=200, complete=True)
    store.flush()

    files = list(tmp_path.glob("session-*/agent-*.cborseq.zst"))
    assert len(files) == 1
    assert not list(tmp_path.rglob("*.jsonl.zst"))
    records = _records(files[0])
    assert [record["event"] for record in records] == [
        "request.start",
        "request.body",
        "upstream.request.body",
        "upstream.response.start",
        "upstream.response.body",
        "upstream.response.end",
        "client.response.start",
        "client.response.body",
        "client.response.body",
        "request.end",
    ]
    request_body = records[1]["body"]
    assert request_body == b'{"prompt":"hello"}'
    assert all(record["schema_version"] == 2 for record in records)
    assert records[-1]["complete"] is True


def test_capture_is_a_stream_of_native_cbor_maps_not_json(tmp_path: Path) -> None:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-1",
        method="POST",
        path="/v1/messages",
    )
    capture.request_body(b"\x00\xffbinary")
    store.flush()

    [path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    with (
        path.open("rb") as compressed,
        zstandard.ZstdDecompressor().stream_reader(compressed) as reader,
    ):
        binary_sequence = reader.read()

    assert binary_sequence[0] >> 5 == 5
    assert not binary_sequence.startswith(b"{")
    assert [record["body"] for record in _records(path) if "body" in record] == [
        b"\x00\xffbinary"
    ]


def test_capture_appends_complete_frames_and_rejects_a_truncated_tail(tmp_path: Path) -> None:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-1",
        method="POST",
        path="/v1/messages",
    )
    store.flush()
    [path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    first_frame = path.read_bytes()

    capture.request_body(b"second-event")
    store.flush()
    complete_file = path.read_bytes()

    assert complete_file.startswith(first_frame)
    assert [record["event"] for record in _records(path)] == [
        "request.start",
        "request.body",
    ]

    path.write_bytes(complete_file[:-5])
    records = iter_raw_capture_records(path)
    assert next(records)["event"] == "request.start"
    with pytest.raises(ValueError, match="incomplete zstd frame"):
        next(records)


def test_legacy_jsonl_files_do_not_participate_in_any_quota(tmp_path: Path) -> None:
    # A large sparse legacy file exhausts the retired default total quota of
    # the old implementation; per-file quota 0 disables the only remaining
    # quota, so a fresh append must still succeed.
    legacy = tmp_path / "legacy" / "agent-old.jsonl.zst"
    legacy.parent.mkdir()
    with legacy.open("wb") as handle:
        handle.truncate(4 * 1024 * 1024 * 1024)
    store = RawCaptureStore(tmp_path, max_file_bytes=0)

    store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-1",
        method="POST",
        path="/v1/messages",
    )
    store.flush()

    files = list(tmp_path.rglob("*.cborseq.zst"))
    assert len(files) == 1
    assert [record["event"] for record in _records(files[0])] == ["request.start"]
    assert legacy.stat().st_size == 4 * 1024 * 1024 * 1024


def test_capture_path_uses_exact_hash_prefixes_without_raw_identity_values(
    tmp_path: Path,
) -> None:
    session_id = "../../session with spaces"
    agent_id = "agent/with/slashes"
    store = RawCaptureStore(tmp_path)
    store.start(
        session_id=session_id,
        agent_id=agent_id,
        request_id="request-1",
        method="POST",
        path="/v1/messages",
    )
    store.flush()

    [capture_path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    agent_hash = hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:24]
    relative_path = capture_path.relative_to(tmp_path)
    assert relative_path == Path(
        f"session-{session_hash}/agent-{agent_hash}.cborseq.zst"
    )
    assert str(relative_path).endswith(".cborseq.zst")
    assert session_id not in str(relative_path)
    assert agent_id not in str(relative_path)
    records = _records(capture_path)
    assert records[0]["session_id"] == session_id
    assert records[0]["agent_id"] == agent_id


def test_missing_agent_id_has_its_own_exact_hashed_capture_group(
    tmp_path: Path,
) -> None:
    session_id = "session-1"
    real_agent_id = "missing-agent-id"
    store = RawCaptureStore(tmp_path)
    missing = store.start(
        session_id=session_id,
        agent_id=None,
        request_id="request-missing-agent",
        method="POST",
        path="/v1/messages",
    )
    identified = store.start(
        session_id=session_id,
        agent_id=real_agent_id,
        request_id="request-real-agent",
        method="POST",
        path="/v1/messages",
    )
    missing.finish(status_code=200, complete=True)
    identified.finish(status_code=200, complete=True)
    store.flush()

    session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    agent_hash = hashlib.sha256(real_agent_id.encode("utf-8")).hexdigest()[:24]
    missing_agent_hash = hashlib.sha256(b"missing-agent-id").hexdigest()[:24]
    relative_paths = {
        path.relative_to(tmp_path) for path in tmp_path.glob("session-*/agent-*.cborseq.zst")
    }
    assert relative_paths == {
        Path(f"session-{session_hash}/agent-{agent_hash}.cborseq.zst"),
        Path(f"session-{session_hash}/agent-missing-{missing_agent_hash}.cborseq.zst"),
    }
    assert all(path.name.endswith(".cborseq.zst") for path in relative_paths)
    assert all(session_id not in str(path) for path in relative_paths)
    assert all(real_agent_id not in str(path) for path in relative_paths)
    records = [record for path in relative_paths for record in _records(tmp_path / path)]
    assert {record["agent_id"] for record in records} == {None, real_agent_id}


def test_incomplete_request_is_reported_even_when_writer_succeeds(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-incomplete",
        method="POST",
        path="/v1/messages",
    )

    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        capture.finish(status_code=None, complete=False)
        store.flush()

    diagnostic = next(
        record.getMessage()
        for record in caplog.records
        if "raw request capture incomplete at request completion" in record.getMessage()
    )
    assert "reason=request_incomplete" in diagnostic
    assert "first_dropped_event=request.end" in diagnostic
    assert "response_body_capture_complete=false" in diagnostic
    assert [record["event"] for record in _records(next(tmp_path.glob("session-*/agent-*.cborseq.zst")))] == [
        "request.start",
        "request.end",
    ]


def test_discarded_response_capture_prefers_the_real_upstream_body(
    tmp_path: Path,
) -> None:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-discarded-response",
        method="POST",
        path="/responses",
    )
    response = httpx2.Response(
        200,
        content=b'{"synthetic":true}',
        request=httpx2.Request("POST", "https://provider.example/responses", content=b"request"),
        extensions={"upstream_raw_response_body": b"event: response.completed\n\n"},
    )

    capture_returned_upstream_response(capture, response, attempt=0)
    capture.finish(status_code=200, complete=True)
    store.flush()

    [capture_path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    body = next(
        record["body"]
        for record in iter_raw_capture_records(capture_path)
        if record["event"] == "upstream.response.body"
    )
    assert body == b"event: response.completed\n\n"


def test_partial_response_boundary_is_reported_at_request_completion(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-partial-boundary",
        method="POST",
        path="/responses",
    )

    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        capture.upstream_response_body(b"partial", attempt=0)
        capture.upstream_response_end(complete=False, attempt=0)
        capture.upstream_attempt_end(0, complete=False)
        capture.finish(status_code=200, complete=True)
        store.flush()

    diagnostic = next(
        record.getMessage()
        for record in caplog.records
        if "raw request capture incomplete at request completion" in record.getMessage()
    )
    assert "reason=upstream_incomplete" in diagnostic
    assert "first_dropped_event=upstream.response.end" in diagnostic
    assert "response_body_capture_complete=false" in diagnostic


def test_failed_attempt_after_complete_response_does_not_report_request_incomplete(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-failed-attempt-complete-response",
        method="POST",
        path="/responses",
    )

    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        capture.upstream_response_start(200, attempt=0)
        capture.upstream_response_body(b"complete", attempt=0)
        capture.upstream_response_end(attempt=0)
        capture.upstream_attempt_end(0, complete=False)
        capture.finish(status_code=200, complete=True)
        store.flush()

    records = [
        record
        for record in _records(next(tmp_path.glob("session-*/agent-*.cborseq.zst")))
        if record["event"] == "upstream.attempt.end"
    ]
    assert len(records) == 1
    assert records[0]["complete"] is False
    assert not any(
        "raw request capture incomplete at request completion" in record.getMessage()
        for record in caplog.records
    )


def test_store_closed_before_request_start_reports_missing_response_body(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = RawCaptureStore(tmp_path)
    store.close()
    capture = store.start(
        session_id="store-closed-session",
        agent_id="store-closed-agent",
        request_id="request-store-closed-start",
        method="POST",
        path="/v1/messages",
    )

    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        capture.finish(status_code=200, complete=True)

    completion_messages = [
        record.getMessage()
        for record in caplog.records
        if "raw request capture incomplete at request completion" in record.getMessage()
    ]
    assert len(completion_messages) == 1
    diagnostic = completion_messages[0]
    assert "reason=store_closed" in diagnostic
    assert "first_dropped_event=request.start" in diagnostic
    assert "response_body_capture_complete=false" in diagnostic


def test_committed_response_body_survives_late_store_closed_request_end(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = RawCaptureStore(tmp_path)
    capture = store.start(
        session_id="late-store-closed-session",
        agent_id="late-store-closed-agent",
        request_id="request-store-closed-end",
        method="POST",
        path="/v1/messages",
    )

    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        capture.client_response_body(b"committed-response-body", more_body=False)
        store.flush()
        store.close()
        capture.finish(status_code=200, complete=True)

    [capture_path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    assert [record["event"] for record in _records(capture_path)] == [
        "request.start",
        "client.response.body",
    ]
    completion_messages = [
        record.getMessage()
        for record in caplog.records
        if "raw request capture incomplete at request completion" in record.getMessage()
    ]
    assert len(completion_messages) == 1
    diagnostic = completion_messages[0]
    assert "reason=store_closed" in diagnostic
    assert "first_dropped_event=request.end" in diagnostic
    assert "response_body_capture_complete=true" in diagnostic


def test_queue_full_preparation_warning_is_safe(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "queue-full-root-marker"
    store = RawCaptureStore(root)

    def raise_full(_: object) -> None:
        raise Full

    monkeypatch.setattr(cast(Any, store._queue), "put_nowait", raise_full)
    identity_marker = "queue-full-identity-marker"
    body_marker = b"queue-full-body-marker"
    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        capture = store.start(
            session_id=identity_marker,
            agent_id=identity_marker,
            request_id="request-queue-full",
            method="POST",
            path="/queue-full-path-marker",
        )
        capture.request_body(body_marker)
        capture.finish(status_code=200, complete=True)
        store.flush()
        store.close()

    messages = [record.getMessage() for record in caplog.records]
    immediate_messages = [
        message
        for message in messages
        if "could not keep raw request capture frame" in message
    ]
    assert immediate_messages == [
        "could not keep raw request capture frame: "
        "request_id=request-queue-full event=request.start reason=writer_queue_full "
        "exception_type=Full errno=None"
    ]
    completion_messages = [
        message
        for message in messages
        if "raw request capture incomplete at request completion" in message
    ]
    assert len(completion_messages) == 1
    assert "response_body_capture_complete=false" in completion_messages[0]
    assert all(str(root) not in message for message in messages)
    assert all(identity_marker not in message for message in messages)
    assert all(body_marker.decode() not in message for message in messages)


def test_capture_error_preparation_warning_is_safe(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "capture-error-root-marker"
    store = RawCaptureStore(root)
    identity_marker = "capture-error-identity-marker"
    body_marker = b"capture-error-body-marker"
    exception_marker = "capture-error-original-message"

    def raise_type_error(*_: object, **__: object) -> bytes:
        raise TypeError(exception_marker)

    monkeypatch.setattr(cbor2, "dumps", raise_type_error)
    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        capture = store.start(
            session_id=identity_marker,
            agent_id=identity_marker,
            request_id="request-capture-error",
            method="POST",
            path="/capture-error-path-marker",
        )
        capture.request_body(body_marker)
        capture.finish(status_code=200, complete=True)
        store.flush()
        store.close()

    messages = [record.getMessage() for record in caplog.records]
    immediate_messages = [
        message
        for message in messages
        if "could not keep raw request capture frame" in message
    ]
    assert immediate_messages == [
        "could not keep raw request capture frame: "
        "request_id=request-capture-error event=request.start reason=capture_error "
        "exception_type=TypeError errno=None"
    ]
    completion_messages = [
        message
        for message in messages
        if "raw request capture incomplete at request completion" in message
    ]
    assert len(completion_messages) == 1
    assert "response_body_capture_complete=false" in completion_messages[0]
    assert all(str(root) not in message for message in messages)
    assert all(identity_marker not in message for message in messages)
    assert all(body_marker.decode() not in message for message in messages)
    assert all(exception_marker not in message for message in messages)


@pytest.mark.parametrize(
    ("quota_kwargs", "expected_reason"),
    [
        ({"max_file_bytes": 512}, "file_quota_exceeded"),
    ],
)
def test_quota_drop_is_reported_safely_at_request_completion(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    quota_kwargs: dict[str, int],
    expected_reason: str,
) -> None:
    store = RawCaptureStore(tmp_path, **quota_kwargs)
    capture = store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-quota",
        method="POST",
        path="/v1/messages",
    )

    secret_body = b"do-not-log-this-marker:" + random.Random(0).randbytes(4096)
    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        capture.request_body(secret_body)
        capture.upstream_response_start(200)
        capture.upstream_response_body(secret_body)
        capture.client_response_start(200)
        capture.client_response_body(secret_body, more_body=False)
        capture.finish(status_code=200, complete=True)
        store.flush()

    files = list(tmp_path.glob("session-*/agent-*.cborseq.zst"))
    assert len(files) == 1
    assert [record["event"] for record in _records(files[0])] == ["request.start"]

    messages = [record.getMessage() for record in caplog.records]
    completion_messages = [
        message
        for message in messages
        if "raw request capture incomplete at request completion" in message
    ]
    assert len(completion_messages) == 1
    diagnostic = completion_messages[0]
    assert "request_id=request-quota" in diagnostic
    assert f"reason={expected_reason}" in diagnostic
    assert "first_dropped_event=request.body" in diagnostic
    assert "writer_error=false" in diagnostic
    assert "response_body_capture_complete=false" in diagnostic
    assert "do-not-log-this-marker" not in diagnostic
    quota_messages = [
        message
        for message in messages
        if "could not keep raw request capture frame" in message
        and "reason=file_quota_exceeded" in message
    ]
    assert len(quota_messages) == 1
    assert "request_id=request-quota event=request.body" in quota_messages[0]
    assert "exception_type=None errno=None" in quota_messages[0]
    assert all(str(tmp_path) not in message for message in messages)


def test_writer_error_is_acknowledged_and_releases_reservations(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = tmp_path / "capture-root-is-a-file"
    root.write_bytes(b"not a directory")
    body_marker = b"writer-body-must-not-enter-logs"
    credential_marker = "writer-credential-must-not-enter-logs"

    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        store = RawCaptureStore(root)
        capture = store.start(
            session_id=credential_marker,
            agent_id="agent-1",
            request_id="request-writer-error",
            method="POST",
            path="/v1/messages",
        )
        capture.upstream_response_body(body_marker)
        capture.client_response_body(body_marker, more_body=False)
        capture.finish(status_code=200, complete=True)
        store.flush()
        store.close()

    messages = [record.getMessage() for record in caplog.records]
    completion_messages = [
        message
        for message in messages
        if "raw request capture incomplete at request completion" in message
    ]
    assert len(completion_messages) == 1
    diagnostic = completion_messages[0]
    assert "request_id=request-writer-error" in diagnostic
    assert "reason=writer_error" in diagnostic
    assert "writer_error=true" in diagnostic
    assert "response_body_capture_complete=false" in diagnostic
    private_store = cast(Any, store)
    assert private_store._reserved_file_bytes == {}
    assert all(body_marker.decode() not in message for message in messages)
    assert all(credential_marker not in message for message in messages)


def test_writer_failure_rollback_preserves_concurrent_successful_cost(
    tmp_path: Path,
) -> None:
    root = tmp_path / "captures"
    root.mkdir()
    store = RawCaptureStore(root)
    private_store = cast(Any, store)
    bad_sessions = [f"bad-session-{index}" for index in range(4)]
    good_sessions = [f"good-session-{index}" for index in range(4)]
    for session_id in bad_sessions:
        bad_path = private_store._path_for(session_id, "agent-1")
        bad_path.parent.write_bytes(b"not a directory")

    def complete_capture(session_id: str) -> None:
        capture = store.start(
            session_id=session_id,
            agent_id="agent-1",
            request_id=f"request-{session_id}",
            method="POST",
            path="/v1/messages",
        )
        capture.client_response_body(b"kept", more_body=False)
        capture.finish(status_code=200, complete=True)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(complete_capture, [*bad_sessions, *good_sessions]))
    store.flush()

    good_paths = {
        private_store._path_for(session_id, "agent-1") for session_id in good_sessions
    }
    assert all(path.is_file() for path in good_paths)
    assert all(
        not private_store._path_for(session_id, "agent-1").exists()
        for session_id in bad_sessions
    )
    actual_costs = {path: path.stat().st_size for path in good_paths}
    assert private_store._reserved_file_bytes == actual_costs
    store.close()


def test_partial_write_poisons_shared_path_for_the_next_request(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_one_short_capture_write(monkeypatch)
    body_marker = b"partial-write-body-must-not-enter-logs"
    credential_marker = "partial-write-credential-must-not-enter-logs"

    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        store = RawCaptureStore(tmp_path)
        first = store.start(
            session_id=credential_marker,
            agent_id="agent-1",
            request_id="request-partial-a",
            method="POST",
            path="/v1/messages",
        )
        first.client_response_body(body_marker, more_body=False)
        first.finish(status_code=200, complete=True)
        [capture_path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
        partial_size = capture_path.stat().st_size

        second = store.start(
            session_id=credential_marker,
            agent_id="agent-1",
            request_id="request-partial-b",
            method="POST",
            path="/v1/messages",
        )
        second.client_response_body(body_marker, more_body=False)
        second.finish(status_code=200, complete=True)
        store.flush()
        store.close()

    assert capture_path.stat().st_size == partial_size
    with pytest.raises((ValueError, zstandard.ZstdError)):
        list(iter_raw_capture_records(capture_path))

    messages = [record.getMessage() for record in caplog.records]
    first_completion = [
        message
        for message in messages
        if "request_id=request-partial-a" in message
        and "raw request capture incomplete at request completion" in message
    ]
    second_completion = [
        message
        for message in messages
        if "request_id=request-partial-b" in message
        and "raw request capture incomplete at request completion" in message
    ]
    assert len(first_completion) == 1
    assert "reason=writer_error" in first_completion[0]
    assert "writer_error=true" in first_completion[0]
    assert len(second_completion) == 1
    assert "reason=path_poisoned" in second_completion[0]
    assert "writer_error=false" in second_completion[0]
    assert "response_body_capture_complete=false" in second_completion[0]
    private_store = cast(Any, store)
    assert private_store._reserved_file_bytes == {capture_path: partial_size}
    assert all(body_marker.decode() not in message for message in messages)
    assert all(credential_marker not in message for message in messages)


def test_partial_write_poison_is_recovered_by_a_new_store(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_one_short_capture_write(monkeypatch)
    body_marker = b"restart-body-must-not-enter-logs"
    credential_marker = "restart-credential-must-not-enter-logs"

    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        first_store = RawCaptureStore(tmp_path)
        first = first_store.start(
            session_id=credential_marker,
            agent_id="agent-1",
            request_id="request-before-restart",
            method="POST",
            path="/v1/messages",
        )
        first.client_response_body(body_marker, more_body=False)
        first.finish(status_code=200, complete=True)
        first_store.close()
        [capture_path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
        partial_size = capture_path.stat().st_size

        second_store = RawCaptureStore(tmp_path)
        second = second_store.start(
            session_id=credential_marker,
            agent_id="agent-1",
            request_id="request-after-restart",
            method="POST",
            path="/v1/messages",
        )
        second.client_response_body(body_marker, more_body=False)
        second.finish(status_code=200, complete=True)
        second_store.close()

    assert capture_path.stat().st_size == partial_size
    completion_messages = [
        record.getMessage()
        for record in caplog.records
        if "request_id=request-after-restart" in record.getMessage()
        and "raw request capture incomplete at request completion"
        in record.getMessage()
    ]
    assert len(completion_messages) == 1
    diagnostic = completion_messages[0]
    assert "reason=path_poisoned" in diagnostic
    assert "writer_error=false" in diagnostic
    assert "response_body_capture_complete=false" in diagnostic
    private_store = cast(Any, second_store)
    assert private_store._reserved_file_bytes == {}
    messages = [record.getMessage() for record in caplog.records]
    assert all(body_marker.decode() not in message for message in messages)
    assert all(credential_marker not in message for message in messages)


@pytest.mark.parametrize(
    ("fixture_payloads", "encoded"),
    [
        pytest.param(
            ("scalar-payload-must-not-enter-logs",),
            cbor2.dumps("scalar-payload-must-not-enter-logs"),
            id="scalar",
        ),
        pytest.param(
            (
                "first-map-payload-must-not-enter-logs",
                "second-map-payload-must-not-enter-logs",
            ),
            cbor2.dumps({"payload": "first-map-payload-must-not-enter-logs"})
            + cbor2.dumps({"payload": "second-map-payload-must-not-enter-logs"}),
            id="multiple-maps",
        ),
    ],
)
def test_new_store_first_append_rejects_valid_zstd_with_invalid_cbor_items(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    fixture_payloads: tuple[str, ...],
    encoded: bytes,
) -> None:
    session_id = "cross-store-session"
    agent_id = "cross-store-agent"
    first_store = RawCaptureStore(tmp_path)
    first = first_store.start(
        session_id=session_id,
        agent_id=agent_id,
        request_id="request-before-restart",
        method="POST",
        path="/v1/messages",
    )
    first.finish(status_code=200, complete=True)
    first_store.close()
    [capture_path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    capture_path.write_bytes(zstandard.ZstdCompressor().compress(encoded))
    original_bytes = capture_path.read_bytes()

    with caplog.at_level(logging.WARNING, logger="app.observability.raw_capture"):
        second_store = RawCaptureStore(tmp_path)
        second = second_store.start(
            session_id=session_id,
            agent_id=agent_id,
            request_id="request-after-restart",
            method="POST",
            path="/v1/messages",
        )
        second.finish(status_code=200, complete=True)
        second_store.close()

    assert capture_path.read_bytes() == original_bytes
    private_store = cast(Any, second_store)
    assert private_store._reserved_file_bytes == {}
    completion_messages = [
        record.getMessage()
        for record in caplog.records
        if "request_id=request-after-restart" in record.getMessage()
        and "raw request capture incomplete at request completion" in record.getMessage()
    ]
    assert len(completion_messages) == 1
    assert "reason=path_poisoned" in completion_messages[0]
    messages = [record.getMessage() for record in caplog.records]
    assert all(
        payload not in message
        for payload in fixture_payloads
        for message in messages
    )


def test_new_store_validates_and_appends_to_a_complete_existing_stream(
    tmp_path: Path,
) -> None:
    first_store = RawCaptureStore(tmp_path)
    first = first_store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-1",
        method="POST",
        path="/v1/messages",
    )
    first.finish(status_code=200, complete=True)
    first_store.close()
    [capture_path] = tmp_path.glob("session-*/agent-*.cborseq.zst")
    first_size = capture_path.stat().st_size

    second_store = RawCaptureStore(tmp_path)
    second = second_store.start(
        session_id="session-1",
        agent_id="agent-1",
        request_id="request-2",
        method="POST",
        path="/v1/messages",
    )
    second.finish(status_code=200, complete=True)
    second_store.close()

    assert capture_path.stat().st_size > first_size
    assert [record["request_id"] for record in _records(capture_path)] == [
        "request-1",
        "request-1",
        "request-2",
        "request-2",
    ]
