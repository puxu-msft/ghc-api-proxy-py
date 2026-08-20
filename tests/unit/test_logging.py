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


def _raise_through_two_frames() -> None:
    def inner() -> None:
        raise ValueError("upstream exploded")

    inner()


def test_a_logged_exception_carries_its_stack(capsys: pytest.CaptureFixture[str]) -> None:
    # What a reader needs from an error line is where it came from.
    # Both spellings are in use — `exc_info=<error>` on a stdlib logger, which is what the listener reports a crashed connection with, and structlog's own `exc_info=True` — and neither used to print a frame: the first rendered the traceback object's address, the second rendered the word `True`.
    setup_logging(log_format="text", colors=False)

    try:
        _raise_through_two_frames()
    except ValueError as error:
        logging.getLogger("app.lifecycle.listener").error("routing crashed", exc_info=error)
    try:
        _raise_through_two_frames()
    except ValueError:
        get_logger("app.probe").error("native failure", exc_info=True)
    _flush_handlers()

    captured = capsys.readouterr().err
    assert captured.count("ValueError: upstream exploded") == 2
    assert captured.count("in _raise_through_two_frames") == 2
    assert captured.count("in inner") == 2
    # The raw tuple leaking into the extras is the shape this replaces.
    assert "exc_info=" not in captured


def test_json_carries_the_stack_as_one_field(capsys: pytest.CaptureFixture[str]) -> None:
    # A shipper can search a string; it can do nothing with a repr of a traceback object.
    setup_logging(log_format="json")

    try:
        _raise_through_two_frames()
    except ValueError as error:
        logging.getLogger("app.lifecycle.listener").error("routing crashed", exc_info=error)
    _flush_handlers()

    event = json.loads(capsys.readouterr().err)
    assert "exc_info" not in event
    assert event["exception"].startswith("Traceback (most recent call last):")
    assert event["exception"].endswith("ValueError: upstream exploded")
