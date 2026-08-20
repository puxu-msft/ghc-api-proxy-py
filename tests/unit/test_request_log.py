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
from app.observability.terminal import BOLD_RED, CYAN, DIM, GREEN, RED, RESET, WHITE, YELLOW
from app.pipeline.delivery.assembler import ReplyDialect


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


def test_a_token_count_is_not_a_turn_that_lost_its_reply() -> None:
    """The reported line: `H1 200 anthropic-messages/claude-opus-5 1.2s ↑19.7k` and nothing else.

    Every absence on it was honest — a count has no reply, so no returning bytes, no blocks, no stop reason — but on a successful line the route has already collapsed into `<inbound-format>/<model>`, leaving nothing that says a count is what this was. The same line is what a delivered turn looks like when its whole reply goes missing, which is the one reading a reader must not have to guess at.

    The counter's name is the second half. `ghc` is upstream's measurement and `local` is this proxy's estimate; the reply body distinguishes them with `estimated` and the line has only the same bare number.
    """
    counting = RequestLine(
        method="POST",
        path="/v1/messages/count_tokens",
        inbound_format="anthropic-messages",
        client_protocol="H1",
        model="claude-opus-5",
        status_code=200,
        duration_s=1.2,
        usage={"input_tokens": 19_700},
        counter="local",
    )
    line = format_completion_line(counting)
    assert line == "H1 200 anthropic-messages/claude-opus-5 1.2s ↑19.7k count(local)"
    assert "count(ghc)" in format_completion_line(replace(counting, counter="ghc"))
    # And the field stays off every line that is not a count, rather than printing a placeholder for the counter that did not run.
    assert "count(" not in format_completion_line(replace(counting, counter=""))


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
    assert status_for(200) == "ok"
    assert status_for(500) == "fail"
    assert status_for(None) == "fail"


def test_a_streaming_outcome_outranks_the_status_code_it_was_stuck_with() -> None:
    """A streaming status is fixed when upstream's headers arrive and cannot describe what happened next.

    Three endings, three words. `gone` is neither of the other two on purpose: the request did not produce an answer, and nothing about that is a fault — ruled 2026-08-20 so that a client cancelling a turn does not scroll past in the same red as an upstream reset.
    """
    assert status_for(200, override="fail") == "fail"
    assert status_for(200, override="gone") == "gone"
    # And an override of `ok` still overrides, so a path that knows better than the status code is not silently ignored on the one value that happens to agree with the default.
    assert status_for(500, override="ok") == "ok"


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


def test_tools_without_a_stop_reason_are_still_named() -> None:
    """A truncated turn had already asked for tools, and the line used to drop them with the reason.

    A separate word from `format_stop_reason`'s, and deliberately neither upstream's. `tool_use` and `function_call` both claim the reply *ended* in tool calls; on this line nothing said the reply ended at all. `called` rather than `tools` because the latter is also what a request's tool *declarations* are called, and a log line gives the reader no way to tell the two apart.
    """
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/p",
            inbound_format="f",
            model="m",
            status_code=200,
            duration_s=1.0,
            tools=("Bash", "Bash", "Read"),
            detail="upstream stream ended without a terminal event",
        )
    )
    assert "called(Bash,Bash,Read)" in line
    assert "tool_use" not in line and "function_call" not in line
    # Still last, and still the thing the eye stops on.
    assert line.endswith(": upstream stream ended without a terminal event")


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


def test_the_route_on_a_failed_line_is_left_at_the_terminal_default() -> None:
    # It is reference material — what has to be repeated to reproduce the failure — and the status and the reason are what carry the weight. An explicit white made it brighter than the untouched text around it.
    line = format_completion_line(
        RequestLine(method="POST", path="/v1/messages", status_code=400, detail="body must be an object"),
        color=True,
    )
    assert line == f"{RED}400{RESET} POST /v1/messages: {RED}body must be an object{RESET}"


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


def test_each_upstream_is_reported_in_its_own_words() -> None:
    """Anthropic sends thinking blocks; the Responses API sends reasoning items.

    Close enough to be confused, and the log is where somebody works out which upstream a turn actually went to — so the line says what it saw rather than translating both into one house word.
    """
    assert format_thinking(("enc",), ReplyDialect.ANTHROPIC) == "think(enc:1)"
    assert format_thinking(("enc", "txt"), ReplyDialect.RESPONSES) == "reason(enc:1,txt:1)"


def test_a_responses_turn_names_the_item_upstream_actually_sent() -> None:
    # `tool_use` is the Anthropic stop reason the assembler synthesises for the client. Right for the body, wrong for a line that reports what upstream did: a Responses trace contains `function_call` items and no `tool_use` anywhere.
    assert format_stop_reason("tool_use", ("Bash", "Read"), ReplyDialect.RESPONSES) == "function_call(Bash,Read)"
    # The word is corrected whether or not any tool survived naming.
    assert format_stop_reason("tool_use", (), ReplyDialect.RESPONSES) == "function_call"
    # Reasons that are not the synthesised one are upstream's own already and are left alone.
    assert format_stop_reason("max_tokens", (), ReplyDialect.RESPONSES) == "max_tokens"
    assert format_stop_reason("tool_use", ("Bash",), ReplyDialect.ANTHROPIC) == "tool_use(Bash)"


def test_the_dialect_reaches_the_rendered_line() -> None:
    # The fields are chosen field-by-field elsewhere; this is the one assertion that the record's dialect survives the trip to the line rather than being defaulted away at the last step.
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/p",
            inbound_format="anthropic-messages",
            model="gpt-5",
            status_code=200,
            duration_s=1.0,
            stop_reason="tool_use",
            tools=("Bash",),
            thinking=("enc",),
            dialect=ReplyDialect.RESPONSES,
        )
    )
    assert line.endswith("function_call(Bash) reason(enc:1)")


def _received(byte_count: int) -> str:
    """One line's rendering of `byte_count` coming back. No duration: that field is white too, and a bare `WHITE in line` would then pass with the byte field left grey."""
    return format_completion_line(
        RequestLine(method="POST", path="/p", status_code=200, bytes_out=byte_count),
        color=True,
    )


def test_what_came_back_escalates_with_its_size() -> None:
    """A reply an order of magnitude larger than usual should be visible without reading the number.

    Asserted as whole spans — marker, printed figure and colour together — because that is the thing a reader sees, and because a bare colour check passes on any other coloured field in the line.
    """
    def field(byte_count: int) -> str:
        return _received(byte_count).split()[-1]

    assert field(5 * 1024) == f"{DIM}↓5.0KB{RESET}"
    # The middle rung carries no escape at all: an explicit white was brighter than the untouched text beside it and read as emphasis. Compared for equality so a stray code fails here rather than being invisible to an `in` check.
    assert field(10 * 1024) == "↓10.0KB"
    assert field(50 * 1024) == "↓50.0KB"
    assert field(100 * 1024) == f"{YELLOW}↓100.0KB{RESET}"


def test_the_thresholds_are_the_round_numbers() -> None:
    # Exactly `10 * 1024`, not the point where the printed figure reaches `10.0KB`. Both counts below print `10.0KB`, so the same shown number comes out grey on one line and untouched on the next — accepted, because the threshold being the round number is what was asked for.
    assert _received(10 * 1024 - 1).split()[-1] == f"{DIM}↓10.0KB{RESET}"
    assert _received(10 * 1024).split()[-1] == "↓10.0KB"


def test_what_went_out_stays_quiet_however_large() -> None:
    # Its size follows from the request the client made, so it says nothing about how the reply went. Escalating it would put a warm colour on every long-context turn and mean nothing by it.
    line = format_completion_line(
        RequestLine(method="POST", path="/p", status_code=200, duration_s=1.0, bytes_in=5_000_000),
        color=True,
    )
    assert YELLOW not in line
    assert DIM in line


def test_output_tokens_escalate_on_their_own_scale() -> None:
    # Counted, not measured in bytes, so the thresholds are the round numbers a reader thinks in.
    def produced(count: int) -> str:
        return format_tokens({"input_tokens": 1, "output_tokens": count}, color=True)

    assert produced(999) == f"↑1 {DIM}↓999{RESET}"
    assert produced(1_000) == "↑1 ↓1.0k"
    assert produced(9_000) == "↑1 ↓9.0k"
    assert produced(10_000) == f"↑1 {YELLOW}↓10.0k{RESET}"


def test_how_the_turn_ended_is_a_ladder_not_a_flag() -> None:
    """Every one of these is terminal, so one colour would say only "it stopped" — which the field already says.

    What the reader wants is how much of a problem the ending was: a clean finish is nothing to look at, truncation at the token limit is the single thing worth seeing on that line, and a refusal delivered nothing and cannot simply be resumed.
    """
    assert format_stop_reason("end_turn", (), color=True) == f"{GREEN}end_turn{RESET}"
    assert format_stop_reason("stop_sequence", (), color=True) == f"{GREEN}stop_sequence{RESET}"
    assert format_stop_reason("max_tokens", (), color=True) == f"{YELLOW}max_tokens{RESET}"
    assert format_stop_reason("refusal", (), color=True) == f"{RED}refusal{RESET}"
    # Not an ending at all: the turn is continuing, and colouring it as one would make the most common non-ending look like the end.
    assert format_stop_reason("tool_use", (), color=True) == "tool_use"


def test_the_tool_that_asks_a_person_is_picked_out_of_the_list() -> None:
    """That tool's purpose is to put a question to somebody, so the work is now blocked on a human noticing — worth seeing in a scrolling log.

    No claim about the other names: a tool is any string and plenty of others may wait on approvals too. This one says so on its face, which is all the colour rests on.
    """
    line = format_stop_reason("tool_use", ("Bash", "AskUserQuestion", "Read"), color=True)
    assert f"{CYAN}AskUserQuestion{RESET}" in line
    assert f"{DIM}Bash{RESET}" in line and f"{DIM}Read{RESET}" in line


def test_a_run_of_quiet_tools_is_coloured_with_its_commas() -> None:
    # Painting name by name would leave white commas between grey names, which reads as though the separators belonged to something else.
    assert format_stop_reason("tool_use", ("Bash", "Bash", "Read"), color=True) == f"tool_use({DIM}Bash,Bash,Read{RESET})"


def test_none_of_this_shows_up_without_colour() -> None:
    # The plain form is what a pipe, a log file and a `TERM=dumb` terminal get, and it must stay byte-for-byte what it was.
    assert format_stop_reason("end_turn", ("Bash", "AskUserQuestion")) == "end_turn(Bash,AskUserQuestion)"
    assert "\x1b" not in format_completion_line(
        RequestLine(
            method="POST",
            path="/p",
            status_code=200,
            duration_s=1.0,
            bytes_out=500_000,
            usage={"input_tokens": 1, "output_tokens": 50_000},
            stop_reason="end_turn",
            tools=("AskUserQuestion",),
        )
    )
