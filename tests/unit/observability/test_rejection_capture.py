"""The body upstream refused, kept where someone can read it.

Two investigations in one day had to reconstruct an outbound request from the *client's* transcripts, because this proxy keeps no record of what it sent and the payload is gone the moment the error response is written. These pin the note it now leaves instead: that it is written at all, that it holds the body as it actually went out rather than as it arrived, and that it stays quiet for the failures a body cannot explain.

`user_data_path` is patched per test, so nothing here touches the developer's own data directory.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.observability import rejection_capture
from app.pipeline.exceptions import UpstreamRateLimit, UpstreamRejected, UpstreamTimeout
from app.pipeline.request import RequestContext, WireFormat


@pytest.fixture(autouse=True)
def elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rejection_capture, "user_data_path", lambda: tmp_path)


def _context(payload: dict[str, Any] | None = None) -> RequestContext:
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="opus",
        payload=payload if payload is not None else {"model": "claude-model", "messages": []},
    )
    context.resolved_model = "claude-opus-5"
    context.target_format = WireFormat.ANTHROPIC_MESSAGES
    return context


def _only_capture(tmp_path: Path) -> dict[str, Any]:
    written = list((tmp_path / "rejected").glob("*.json"))
    assert len(written) == 1, f"expected exactly one capture, found {written}"
    return json.loads(written[0].read_text())


def test_a_refused_body_is_written_as_it_went_out(tmp_path: Path) -> None:
    """The production case, and the whole reason this exists.

    The payload asserted here is the one the subscribers left behind — the blank text block that upstream refused — not the one the client sent. A capture taken from the inbound body would have shown a request that was never made.
    """
    context = _context(
        {
            "model": "claude-opus-5",
            "messages": [{"role": "user", "content": [{"type": "text", "text": ""}]}],
        }
    )
    error = UpstreamRejected(
        "upstream rejected the request: Error code: 400",
        status_code=400,
        body='{"type":"error","error":{"message":"messages: text content blocks must be non-empty"}}',
    )

    path = rejection_capture.capture_rejection(context, error, request_id="req-1")

    assert path is not None
    record = _only_capture(tmp_path)
    assert record["payload"]["messages"][0]["content"] == [{"type": "text", "text": ""}]
    assert record["status"] == 400
    assert "text content blocks must be non-empty" in record["upstream"]
    assert record["resolved_model"] == "claude-opus-5"
    assert record["request_id"] == "req-1"


def test_the_wire_bytes_are_kept_beside_the_dict_they_cannot_be_derived_from(tmp_path: Path) -> None:
    """Two forms of one body, because re-serializing the dict is a guess at what upstream read.

    The bytes here say the same thing as the payload and are not the same string: key order and spacing are decided by whoever serialized them, which is the SDK and not this pipeline. That is the whole reason both are written — a refusal about how a body was spelled is unanswerable from a dict, and until now only the length of the real bytes was ever recorded.
    """
    payload: dict[str, Any] = {"model": "claude-opus-5", "messages": []}
    sent = b'{"messages": [], "model": "claude-opus-5"}'
    error = UpstreamRejected("refused", status_code=400, body="{}", sent=sent)

    rejection_capture.capture_rejection(_context(payload), error, request_id="req-1")

    record = _only_capture(tmp_path)
    assert record["sent"] == sent.decode()
    assert record["sent_bytes"] == len(sent)
    assert json.loads(record["sent"]) == record["payload"], "the two must describe one request"
    assert record["sent"] != json.dumps(record["payload"]), "if the dict re-serialized to the same string there would be nothing to keep"


@pytest.mark.parametrize(
    "error",
    [
        UpstreamRateLimit("slow down", retry_after=1.0),
        UpstreamTimeout("upstream timed out"),
        RuntimeError("something else entirely"),
    ],
    ids=["rate-limit", "timeout", "not-an-upstream-failure"],
)
def test_nothing_is_kept_for_a_failure_a_body_cannot_explain(tmp_path: Path, error: BaseException) -> None:
    """A 429 is about pace and a timeout never got a verdict, so neither is answered by the body.

    Without this the directory fills with the failures that say nothing, and the one capture worth reading is the hardest to find.
    """
    assert rejection_capture.capture_rejection(_context(), error) is None
    assert not (tmp_path / "rejected").exists()


def test_only_the_newest_captures_are_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused body is as large as the conversation behind it, so a storm must not fill the disk."""
    monkeypatch.setattr(rejection_capture, "KEEP_NEWEST", 3)
    error = UpstreamRejected("refused", status_code=400, body="{}")

    for index in range(6):
        rejection_capture.capture_rejection(_context(), error, request_id=f"req-{index}")

    kept = sorted(entry.name for entry in (tmp_path / "rejected").glob("*.json"))
    assert len(kept) == 3
    # Suffix rather than a split on `-`: the request id carries one of its own.
    assert [name.endswith(f"req-{index}.json") for index, name in zip((3, 4, 5), kept, strict=True)] == [True] * 3


def test_a_directory_that_cannot_be_written_does_not_replace_the_client_s_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The client is already being told what upstream said; a filesystem problem must not become the answer instead."""
    monkeypatch.setattr(rejection_capture, "user_data_path", lambda: tmp_path / "nope" / "\0bad")
    error = UpstreamRejected("refused", status_code=400, body="{}")

    assert rejection_capture.capture_rejection(_context(), error) is None
