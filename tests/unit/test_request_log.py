"""The shape of one request's console line.

Driven directly rather than through a served request, so every branch of the field order is reachable without a logger or a terminal.
"""

from dataclasses import replace

from app.observability.request_log import (
    RequestLine,
    format_arrival_line,
    format_completion_line,
    format_stop_reason,
    format_thinking,
    format_tokens,
    http_label,
    status_for,
)
from app.observability.terminal import BOLD_RED, DIM, RED, WHITE, YELLOW


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


def test_reasoning_blocks_are_counted_by_kind() -> None:
    # `txt` carried readable reasoning, `enc` only a sealed signature. They cost the same tokens and are indistinguishable on every other field of the line.
    assert format_thinking(("enc",)) == "think(enc:1)"
    assert format_thinking(("enc", "txt", "txt")) == "think(enc:1,txt:2)"
    assert format_thinking(("txt",)) == "think(txt:1)"
    # The common case takes no width at all.
    assert format_thinking(()) == ""


def test_reasoning_is_reported_last_and_quietly() -> None:
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/p",
            inbound_format="f",
            model="m",
            status_code=200,
            duration_s=1.0,
            stop_reason="end_turn",
            thinking=("enc", "txt", "txt"),
        )
    )
    # After the fields that describe the exchange, since it describes how the model got to the answer rather than anything about the exchange itself.
    assert line.endswith("end_turn think(enc:1,txt:2)")
    assert DIM in format_completion_line(
        RequestLine(method="POST", path="/p", status_code=200, duration_s=1.0, thinking=("enc",)),
        color=True,
    )


def test_the_protocol_of_each_leg_is_labelled() -> None:
    # Client first, then upstream, in the order the request travels.
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/p",
            inbound_format="f",
            client_protocol="H2",
            upstream_protocol="H1",
            model="m",
            status_code=200,
            duration_s=1.0,
        )
    )
    assert line.startswith("H2/H1 200 ")


def test_a_leg_that_never_happened_is_not_invented() -> None:
    # A request refused before it reached upstream has one leg, and printing a placeholder for the other would describe a connection that was never made.
    line = format_completion_line(
        RequestLine(method="POST", path="/p", client_protocol="H1", status_code=400, duration_s=0.001)
    )
    assert line.startswith("H1 400 POST /p")


def test_http_versions_collapse_to_what_changes_behaviour() -> None:
    # 1 versus 1.1 changes nothing this proxy does; 1 versus 2 changes multiplexing and framing.
    assert http_label("1.0") == "H1"
    assert http_label("1.1") == "H1"
    assert http_label("HTTP/1.1") == "H1"
    assert http_label("2") == "H2"
    assert http_label("HTTP/2") == "H2"
    assert http_label("") == ""


def test_a_websocket_is_not_reported_as_the_http_1_1_it_rides_on() -> None:
    # True underneath and useless to say: the upgrade is the one thing about the leg that matters.
    assert http_label("1.1", websocket=True) == "WS"


def test_a_tool_use_turn_names_the_tools_it_asked_for() -> None:
    # `tool_use` alone says only that the turn ended in tool calls. Three `Bash` and one `Bash` are very different turns, so duplicates are kept and the model's order is preserved.
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/p",
            inbound_format="f",
            model="m",
            status_code=200,
            duration_s=1.0,
            stop_reason="tool_use",
            tools=("Bash", "Bash", "Read"),
        )
    )
    assert line.endswith("tool_use(Bash,Bash,Read)")


def test_a_stop_reason_without_tools_is_left_alone() -> None:
    assert format_stop_reason("end_turn", ()) == "end_turn"
    # An empty name is dropped rather than rendered as a gap, which would read as a tool called "".
    assert format_stop_reason("tool_use", ("", "")) == "tool_use"
    assert format_stop_reason("", ("Bash",)) == ""


def test_colour_is_off_unless_asked_for() -> None:
    # The plain form is the one every other assertion in this file reads, and the one a pipe or a `TERM=dumb` terminal gets. Colour is a rendering choice made from the probe, never a default.
    line = RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=500, duration_s=1.0, detail="boom")
    assert "\x1b" not in format_completion_line(line)
    assert "\x1b" in format_completion_line(line, color=True)


def test_the_duration_escalates_on_its_own() -> None:
    """A slow request should be visible without reading the number.

    Thresholds ported from `copilot-api-js`: white up to 20s, yellow to 60s, red to 180s, bold red beyond.
    """
    def coloured(seconds: float) -> str:
        return format_completion_line(
            RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=seconds),
            color=True,
        )

    assert WHITE in coloured(5.0)
    assert YELLOW in coloured(30.0)
    assert RED in coloured(120.0)
    assert BOLD_RED in coloured(300.0)


def test_a_failing_status_and_its_reason_are_red() -> None:
    line = format_completion_line(
        RequestLine(method="POST", path="/p", status_code=429, duration_s=1.0, detail="rate limited"),
        color=True,
    )
    assert line.count(RED) == 2, "the status and the reason are both what says whether to care"


def test_a_healthy_cache_rate_stays_quiet_and_a_collapsing_one_shouts() -> None:
    # Inverted against duration on purpose: here the number getting smaller is what costs money.
    warm = format_tokens({"input_tokens": 10, "cache_read_input_tokens": 990, "output_tokens": 1}, color=True)
    cold = format_tokens({"input_tokens": 990, "cache_read_input_tokens": 10, "output_tokens": 1}, color=True)
    assert DIM in warm
    assert BOLD_RED in cold


def test_a_mapped_model_shows_what_was_asked_for_and_what_answered() -> None:
    # A line naming only the resolved model hides the mapping, and a mapping doing something unintended is invisible in exactly the request where it matters.
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/v1/messages",
            inbound_format="anthropic-messages",
            requested_model="claude-sonnet-4.5",
            model="claude-sonnet-5",
            status_code=200,
            duration_s=1.5,
        )
    )
    assert line == "200 anthropic-messages/claude-sonnet-4.5 → claude-sonnet-5 1.5s"


def test_an_unmapped_model_is_named_once() -> None:
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/p",
            inbound_format="f",
            requested_model="same-model",
            model="same-model",
            status_code=200,
            duration_s=1.0,
        )
    )
    assert "→" not in line
    assert "f/same-model" in line


def test_both_directions_of_wire_bytes_are_reported() -> None:
    # The reported gap: only the streaming path counted anything, so every other request showed no byte field at all.
    line = format_completion_line(
        RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=1.0, bytes_in=152, bytes_out=2300)
    )
    assert "↑152B ↓2.2KB" in line


def test_token_usage_is_rendered_with_its_cache_breakdown() -> None:
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/p",
            inbound_format="f",
            model="m",
            status_code=200,
            duration_s=1.0,
            usage={"input_tokens": 12, "cache_read_input_tokens": 8000, "cache_creation_input_tokens": 1000, "output_tokens": 456},
            stop_reason="end_turn",
        )
    )
    # Cache reads and writes are additive on the input side because that is what they are: both supply input.
    assert "↑12+8.0k+1.0k" in line
    assert "↓456" in line
    assert line.endswith("end_turn")


def test_the_cache_rate_is_shown_only_when_there_was_cache_activity() -> None:
    plain = format_tokens({"input_tokens": 100, "output_tokens": 5})
    assert plain == "↑100 ↓5"
    cached = format_tokens({"input_tokens": 0, "cache_read_input_tokens": 100, "output_tokens": 5})
    assert "↻100%" in cached


def test_zero_output_tokens_are_reported_rather_than_omitted() -> None:
    # A request that produced no output is a real outcome; omitting the field would make it look like an endpoint that does not count output at all.
    assert "↓0" in format_tokens({"input_tokens": 10, "output_tokens": 0})
    assert "↓" not in format_tokens({"input_tokens": 10})


def test_token_markers_degrade_with_the_rest_of_the_line() -> None:
    ascii_form = format_tokens({"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 2}, unicode=False)
    assert "↑" not in ascii_form
    assert "↻" not in ascii_form
    assert ascii_form.startswith(">10+5")
