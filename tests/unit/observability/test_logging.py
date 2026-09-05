import json
import logging

import pytest
import structlog

from app.model_provider.ghc_client.auth.providers import NoGitHubToken
from app.observability.logging import LogFormat, get_logger, setup_logging


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


@pytest.mark.parametrize("log_format", ["text", "json"])
def test_catalog_failure_formats_its_positional_arguments(
    capsys: pytest.CaptureFixture[str], log_format: LogFormat,
) -> None:
    setup_logging(log_format=log_format, colors=False)
    reason = "No GitHub token provider produced a usable token"

    with structlog.contextvars.bound_contextvars(request_id="catalog-refresh"):
        get_logger().warning(
            "model provider %r: background catalog refresh failed: %s",
            "ghc",
            NoGitHubToken(reason),
            status="fail",
        )
    _flush_handlers()

    output = capsys.readouterr().err
    expected = f"model provider 'ghc': background catalog refresh failed: {reason}"
    if log_format == "json":
        event = json.loads(output)
        assert event["event"] == expected
        assert event["status"] == "fail"
        assert event["level"] == "warning"
        assert event["request_id"] == "catalog-refresh"
        assert "positional_args" not in event
    else:
        assert output.startswith("[FAIL] ")
        assert f" {expected} request_id=catalog-refresh\n" in output
        assert "positional_args=" not in output


@pytest.mark.parametrize("log_format", ["text", "json"])
def test_native_and_stdlib_logs_preserve_literal_percent_signs(
    capsys: pytest.CaptureFixture[str], log_format: LogFormat,
) -> None:
    setup_logging(log_format=log_format, colors=False)
    for logger in (get_logger("app.probe"), logging.getLogger("app.probe")):
        logger.warning("progress %(value)s", {"value": "100%; literal %s"})
        logger.warning("no arguments: 100%; literal %s")
    _flush_handlers()

    lines = capsys.readouterr().err.splitlines()
    if log_format == "json":
        events = [json.loads(line) for line in lines]
        messages = [event["event"] for event in events]
        assert all("positional_args" not in event for event in events)
    else:
        assert all(line.startswith("[WARN] ") for line in lines)
        messages = [line.split(" ", 2)[2] for line in lines]
    assert messages == ["progress 100%; literal %s", "no arguments: 100%; literal %s"] * 2


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


def test_a_library_record_shows_its_severity(capsys: pytest.CaptureFixture[str]) -> None:
    # A library has no way to set `status`, and text mode drops `level`, so every line httpx, httpcore, uvicorn or asyncio produced arrived as `[....]` — the prefix and the dimmed styling of a request that has just started. Not merely hard to spot: in text mode the word `error` never reached the output, so there was nothing to grep for either.
    setup_logging(log_format="text", colors=False)

    logging.getLogger("httpx").warning("connection pool exhausted")
    logging.getLogger("httpcore").error("upstream TLS handshake failed")
    logging.getLogger("app.own").info("a request has started")
    _flush_handlers()

    lines = capsys.readouterr().err.splitlines()
    assert [line.split(" ")[0] for line in lines] == ["[WARN]", "[FAIL]", "[....]"]


def test_our_own_status_outranks_the_level_it_logged_at(capsys: pytest.CaptureFixture[str]) -> None:
    # A retry is reported at error level and is still a retry. The outcome this project named itself is the more specific answer, so the severity fallback must not overwrite it.
    setup_logging(log_format="text", colors=False)

    get_logger("app.own").error("upstream_retried", status="retry")
    _flush_handlers()

    assert capsys.readouterr().err.startswith("[RETY] ")
