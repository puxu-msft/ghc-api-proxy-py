"""The shape of one request's console line.

Driven directly rather than through a served request, so every branch of the field order is reachable without a logger or a terminal.
"""

from dataclasses import replace

from app.observability.request_log import (
    RequestLine,
    format_arrival_line,
    format_completion_line,
    status_for,
)


def test_a_successful_request_names_the_model_rather_than_the_route() -> None:
    # Once it worked, which model answered is the thing worth reading; the route is noise. This is the shape `copilot-api-js` settled on and the reason its success lines are so much shorter than its failures.
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/v1/messages",
            inbound_format="anthropic-messages",
            model="claude-sonnet-4.5",
            status_code=200,
            duration_s=3.0,
            bytes_out=12_400,
        )
    )
    assert line == "200 anthropic-messages/claude-sonnet-4.5 3.0s ↓12.1KB"
    assert "POST" not in line


def test_a_failed_request_keeps_the_method_and_path() -> None:
    # The opposite trade: a failure is something to reproduce, and the route is exactly what has to be repeated.
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/v1/messages",
            inbound_format="anthropic-messages",
            model="gpt-5",
            status_code=429,
            duration_s=1.0,
            detail="rate limited",
        )
    )
    assert line == "429 POST /v1/messages gpt-5 1.0s: rate limited"


def test_a_request_that_never_resolved_a_model_omits_it() -> None:
    # `DESIGN.md`: a non-model request shows no model and no tokens. A placeholder would read as a model actually named that.
    line = format_completion_line(
        RequestLine(method="POST", path="/v1/messages", status_code=400, duration_s=0.002, detail="body must be an object")
    )
    assert line == "400 POST /v1/messages 2ms: body must be an object"


def test_absent_bytes_are_not_the_same_as_zero() -> None:
    base = RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=1.0)
    assert "↓" not in format_completion_line(base)
    assert "↓0B" in format_completion_line(replace(base, bytes_out=0))


def test_retries_are_reported_once_the_count_is_final() -> None:
    line = format_completion_line(
        RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=1.0, attempts=3)
    )
    assert "retries=2" in line


def test_the_byte_marker_degrades_where_the_glyph_cannot_be_encoded() -> None:
    line = format_completion_line(
        RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=1.0, bytes_out=2048),
        unicode=False,
    )
    assert "↓" not in line
    assert "<2.0KB" in line


def test_the_arrival_line_says_only_what_is_known_on_arrival() -> None:
    assert format_arrival_line(RequestLine(method="POST", path="/v1/messages")) == "POST /v1/messages"
    assert format_arrival_line(RequestLine(method="POST", path="/v1/messages", model="m")) == "POST /v1/messages m"


def test_an_upstream_error_status_reads_as_a_failure_even_though_it_arrived() -> None:
    # Judged on whether the caller got a usable answer, not on whether a response object exists. A 500 delivered intact is still a failure to the person watching.
    assert status_for(200, failed=False) == "ok"
    assert status_for(500, failed=False) == "fail"
    assert status_for(None, failed=False) == "fail"
    assert status_for(200, failed=True) == "fail"
