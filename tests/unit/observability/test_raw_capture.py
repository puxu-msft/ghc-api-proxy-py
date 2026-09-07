import base64
import io
import json
from pathlib import Path

import zstandard

from app.observability.raw_capture import RawCaptureStore


def _records(path: Path) -> list[dict[str, object]]:
    with path.open("rb") as stream:
        compressed = stream.read()
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(compressed)) as reader:
        return [json.loads(line) for line in reader.read().splitlines()]


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

    files = list(tmp_path.glob("session-*/agent-*.jsonl.zst"))
    assert len(files) == 1
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
    assert isinstance(request_body, str)
    assert base64.b64decode(request_body) == b'{"prompt":"hello"}'
    assert records[-1]["complete"] is True


def test_capture_path_does_not_use_raw_identity_values(tmp_path: Path) -> None:
    store = RawCaptureStore(tmp_path)
    store.start(
        session_id="../../session with spaces",
        agent_id="agent/with/slashes",
        request_id="request-1",
        method="POST",
        path="/v1/messages",
    )
    store.flush()

    files = list(tmp_path.glob("session-*/agent-*.jsonl.zst"))
    assert len(files) == 1
    assert ".." not in str(files[0].relative_to(tmp_path))
    records = _records(files[0])
    assert records[0]["session_id"] == "../../session with spaces"
    assert records[0]["agent_id"] == "agent/with/slashes"
