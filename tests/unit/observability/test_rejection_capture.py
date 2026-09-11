from typing import Any

import pytest

from app.observability import rejection_capture
from app.pipeline.exceptions import UpstreamRateLimit, UpstreamRejected, UpstreamTimeout
from app.pipeline.request import RequestContext, WireFormat


def _context(payload: dict[str, Any] | None = None) -> RequestContext:
    return RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="opus",
        payload=payload if payload is not None else {"model": "claude-model", "messages": []},
    )


def test_rejection_capture_does_not_persist_an_unmatched_body() -> None:
    error = UpstreamRejected(
        "upstream rejected the request",
        status_code=400,
        body='{"error":{"message":"must not be persisted here"}}',
        sent=b'{"model":"claude-model"}',
    )

    assert rejection_capture.capture_rejection(_context(), error, request_id="req-1") is None


@pytest.mark.parametrize(
    "error",
    [
        UpstreamRateLimit("slow down", retry_after=1.0),
        UpstreamTimeout("upstream timed out"),
        RuntimeError("something else entirely"),
    ],
)
def test_non_rejection_failures_are_not_captured(error: BaseException) -> None:
    assert rejection_capture.capture_rejection(_context(), error) is None
