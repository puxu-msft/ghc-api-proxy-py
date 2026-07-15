import json
import logging

import pytest
import structlog

from app.observability.logging import get_logger, setup_logging


def _flush_handlers() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_structlog_contextvars(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(log_format="json")

    with structlog.contextvars.bound_contextvars(request_id="test-123"):
        get_logger().info("test_event", model="claude-test")

    _flush_handlers()
    assert "test-123" in capsys.readouterr().err


def test_json_renderer_includes_context_and_event(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(log_format="json")

    with structlog.contextvars.bound_contextvars(request_id="test-123"):
        get_logger().info("request_completed", status="ok")
    _flush_handlers()

    captured = capsys.readouterr()
    event = json.loads(captured.err)
    assert event["event"] == "request_completed"
    assert event["request_id"] == "test-123"
    assert event["level"] == "info"
    assert event["status"] == "ok"
    assert "timestamp" in event


def test_text_renderer_uses_fixed_width_prefix(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(log_format="text", colors=False)

    get_logger().error("upstream_failed", status="fail")
    _flush_handlers()

    captured = capsys.readouterr()
    assert "[FAIL]" in captured.err
    assert "upstream_failed" in captured.err


def test_stdlib_logging_is_rendered_by_structlog(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(log_format="json")

    logging.getLogger("uvicorn.error").warning("server warning")
    _flush_handlers()

    captured = capsys.readouterr()
    event = json.loads(captured.err)
    assert event["event"] == "server warning"
    assert event["level"] == "warning"