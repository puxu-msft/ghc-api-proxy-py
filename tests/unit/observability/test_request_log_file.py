"""Durable structured records emitted from the existing per-request aggregate."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.observability import request_log_file, request_trace
from app.observability.request_log import RequestLine
from app.observability.request_trace import (
    RequestTrace,
    log_completion,
    snapshot_upstream_connection,
)
from app.observability.terminal import TerminalCapabilities
from app.pipeline.delivery.assembling import ReplyDialect, Terminal
from app.pipeline.delivery.blocks import CompletedBlock


@pytest.fixture(autouse=True)
def elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_log_file, "user_data_path", lambda: tmp_path)


def _chain() -> Any:
    return SimpleNamespace(capabilities=TerminalCapabilities(live=False, color=False, unicode=True))


def _capture_console(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    emitted: list[tuple[str, str]] = []

    class Logger:
        def info(self, event: str, *, status: str) -> None:
            emitted.append((event, status))

    def logger_for(_name: str) -> Logger:
        return Logger()

    monkeypatch.setattr(request_trace, "get_logger", logger_for)
    return emitted


def _only_record(tmp_path: Path) -> dict[str, Any]:
    paths = list((tmp_path / "requests").glob("requests-*.jsonl"))
    assert len(paths) == 1, f"expected one daily request log, found {paths}"
    lines = paths[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, f"expected one request record, found {len(lines)}"
    return cast(dict[str, Any], json.loads(lines[0]))


def test_a_successful_request_writes_one_complete_structured_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    emitted = _capture_console(monkeypatch)
    terminal = Terminal(
        stop_reason="tool_use",
        usage={"input_tokens": 10, "output_tokens": 4},
        seen=True,
        dialect=ReplyDialect.RESPONSES,
    )
    terminal.record(CompletedBlock(index=0, kind="text", payload={"type": "text", "text": "done"}))
    terminal.record(CompletedBlock(index=1, kind="tool_use", payload={"type": "tool_use", "name": "Bash"}))
    terminal.record(CompletedBlock(index=2, kind="thinking", payload={"type": "thinking", "thinking": ""}))
    trace = RequestTrace(
        method="POST",
        path="/v1/messages",
        request_id="req-1",
        message_id="msg-1",
        inbound_format="anthropic-messages",
        client_protocol="H1",
        upstream_protocol="H2",
        requested_model="claude-opus-5",
        model="gpt-5.1-codex",
        attempts=2,
        started=time.monotonic() - 1.0,
        started_at="2026-08-20T15:01:53.580Z",
        first_upstream_byte_s=0.42,
        upstream_max_gap_s=6.5,
        upstream_chunks=214,
        bytes_in=1783221,
        upstream_conn={"local": "172.19.141.235:56822", "peer": "140.82.116.5:443", "alpn": "h2", "stream_id": 7},
    )
    trace.absorb(terminal)

    log_completion(_chain(), trace, 200, bytes_out=2153)

    record = _only_record(tmp_path)
    assert set(record) == {
        "at",
        "status",
        "method",
        "path",
        "request_id",
        "message_id",
        "inbound_format",
        "count_tokens",
        "client_protocol",
        "upstream_protocol",
        "requested_model",
        "model",
        "status_code",
        "started_at",
        "duration_s",
        "first_upstream_byte_s",
        "upstream_max_gap_s",
        "upstream_chunks",
        "bytes_in",
        "bytes_out",
        "usage",
        "terminal_seen",
        "stop_reason",
        "blocks",
        "tools",
        "thinking",
        "count_provider",
        "count_provider_reason",
        "dialect",
        "attempts",
        "replaced_failure",
        "detail",
        "upstream_conn",
        "losses",
    }
    assert record | {"at": "ignored", "duration_s": "ignored"} == {
        "at": "ignored",
        "status": "ok",
        "method": "POST",
        "path": "/v1/messages",
        "request_id": "req-1",
        "message_id": "msg-1",
        "inbound_format": "anthropic-messages",
        # This one was a turn, not a count. The endpoint is recorded either way, so the line can say which it was without inferring it from what came back.
        "count_tokens": False,
        "client_protocol": "H1",
        "upstream_protocol": "H2",
        "requested_model": "claude-opus-5",
        "model": "gpt-5.1-codex",
        "status_code": 200,
        "started_at": "2026-08-20T15:01:53.580Z",
        "duration_s": "ignored",
        "first_upstream_byte_s": 0.42,
        # How the stream was paced. `None` is fewer than two arrivals from upstream, which is what a buffered reply looks like — and is not the same claim as "there was no silence".
        "upstream_max_gap_s": 6.5,
        "upstream_chunks": 214,
        "bytes_in": 1783221,
        "bytes_out": 2153,
        "usage": {"input_tokens": 10, "output_tokens": 4},
        "terminal_seen": True,
        "stop_reason": "tool_use",
        "blocks": 3,
        "tools": ["Bash"],
        "thinking": ["enc"],
        # Empty on a delivered turn: nothing counted it, it was answered.
        "count_provider": "",
        "count_provider_reason": "",
        "dialect": "responses",
        "attempts": 2,
        # `None` because this record is of a request that was answered on its first attempt after the retry count was set by hand; a replay records what it replaced.
        "replaced_failure": None,
        "detail": "",
        "upstream_conn": {"local": "172.19.141.235:56822", "peer": "140.82.116.5:443", "alpn": "h2", "stream_id": 7},
        # Empty on an untranslated turn, and empty rather than absent: a lossless crossing and a crossing nothing looked at have to be one shape here, because the record is written for requests that never reached a translator at all.
        "losses": [],
    }
    assert record["at"].endswith("Z")
    assert cast(float, record["duration_s"]) >= 1.0
    # The join key lives in the record, not on the console line: there is nothing to join to on a request that worked, and the id is wider than several real fields put together.
    assert "req-1" not in emitted[0][0]
    assert emitted[0][1] == record["status"]


def test_a_failed_request_keeps_detail_and_reports_no_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    emitted = _capture_console(monkeypatch)
    detail = "stream failed before a terminal event: <ConnectionTerminated error_code:0, last_stream_id:2147483647>"
    trace = RequestTrace(
        method="POST",
        path="/v1/messages",
        request_id="req-fail",
        message_id="msg-fail",
        started=time.monotonic(),
        started_at="2026-08-20T15:01:53.580Z",
        status_override="fail",
        received=321,
        detail=detail,
        blocks=3,
        terminal_seen=False,
    )

    log_completion(_chain(), trace, 200, bytes_out=trace.received)

    record = _only_record(tmp_path)
    assert record["status"] == "fail"
    assert record["status_code"] == 200
    assert record["detail"] == detail
    assert record["terminal_seen"] is False
    assert record["blocks"] == 3
    assert emitted[0][1] == "fail"
    # Shown because this line reports a failure, and last because the id is the widest thing on it. The status code is 200 — a stream that tore after upstream's headers arrived — so nothing but the resolved status can tell this line from a delivered answer.
    assert emitted[0][0].endswith(" req=req-fail")


def test_a_write_failure_does_not_interrupt_request_completion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    emitted = _capture_console(monkeypatch)
    monkeypatch.setattr(request_log_file, "user_data_path", lambda: tmp_path / "nope" / "\0bad")
    trace = RequestTrace(method="POST", path="/v1/messages", started=time.monotonic(), started_at="2026-08-20T15:01:53.580Z")

    log_completion(_chain(), trace, 200, bytes_out=0)

    assert len(emitted) == 1
    assert emitted[0][1] == "ok"


def test_connection_identity_is_copied_while_the_transport_is_live() -> None:
    class Tls:
        def selected_alpn_protocol(self) -> str:
            return "h2"

    class NetworkStream:
        closed = False

        def get_extra_info(self, name: str) -> Any:
            if self.closed:
                raise OSError(9, "Bad file descriptor")
            return {"client_addr": ("172.19.141.235", 56822), "server_addr": ("140.82.116.5", 443), "ssl_object": Tls()}[name]

    stream = NetworkStream()
    response = SimpleNamespace(extensions={"network_stream": stream, "stream_id": 7})

    snapshot = snapshot_upstream_connection(response)
    stream.closed = True

    assert snapshot == {"local": "172.19.141.235:56822", "peer": "140.82.116.5:443", "alpn": "h2", "stream_id": 7}
    # Once the socket is closed the addresses raise, and the row must say so rather than carry `""` in their place: a named reader compares `local` across rows and reads equal values as one shared connection, which every blanked-out row would satisfy. `stream_id` survives because it comes off the extensions mapping, not the socket — reporting the half that is known beside the reason the rest is missing beats reporting either alone.
    assert snapshot_upstream_connection(response) == {"stream_id": 7, "unavailable": "socket-unreadable"}


def test_a_transport_with_no_identity_says_that_rather_than_going_blank() -> None:
    """The ordinary case, and the one that must not read as a real observation.

    Every HTTP/1.1 exchange recorded so far, and every request served through a mock transport, lands here — 152 of 2527 rows on 2026-08-20. They used to be written as `{"local": "", "peer": "", "alpn": "", "stream_id": null}`, which is indistinguishable from a failed read and, worse, equal to every other such row.
    """
    assert snapshot_upstream_connection(SimpleNamespace(extensions={})) == {"unavailable": "no-transport-identity"}
    # An extensions mapping shaped unlike httpcore's is a third thing again, and it carries what went wrong.
    broken = snapshot_upstream_connection(SimpleNamespace())
    assert list(broken) == ["unavailable"]
    assert broken["unavailable"].startswith("snapshot-failed: ")
    # And none of the three is the empty dict, which `RequestTrace` uses to mean no snapshot was ever taken.
    assert {} not in (broken, snapshot_upstream_connection(SimpleNamespace(extensions={})))


def test_only_the_newest_utc_day_files_are_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_log_file, "KEEP_DAYS", 2)
    directory = tmp_path / "requests"
    directory.mkdir()
    for day in ("20260801", "20260802", "20260803"):
        (directory / f"requests-{day}.jsonl").write_text("{}\n", encoding="utf-8")

    request_log_file.write_request_record(RequestLine(method="POST", path="/v1/messages"), status="ok")

    kept = sorted(path.name for path in directory.glob("requests-*.jsonl"))
    today = f"requests-{datetime.now(UTC):%Y%m%d}.jsonl"
    assert kept == ["requests-20260803.jsonl", today]
