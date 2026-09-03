"""The shape of one request's console line.

Driven directly rather than through a served request, so every branch of the field order is reachable without a logger or a terminal.
"""

from dataclasses import replace

import orjson

from app.observability.request_log import (
    LogStatus,
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
from app.pipeline.delivery.assembling import ReplyDialect
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.hand_over import one_line
from app.pipeline.response_action import (
    ClientActionBasis,
    ClientActionObservation,
    ClientActionRequirement,
)
from app.pipeline.response_observation import ResponseObservation, ResponsesObserver


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
        ),
        status="ok",
    )
    assert line == "200 anthropic-messages/claude-sonnet-4.5 3.0s ↓12.1KiB"
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
        ),
        status="fail",
    )
    assert line == "429 POST /v1/messages gpt-5 1.0s: rate limited"


def test_the_join_key_is_kept_for_the_lines_somebody_will_come_looking_for() -> None:
    """`req=<id>` at the very end of a line that went wrong, and nothing at all on one that worked.

    The id is a UUID — wider than the status, the model and the duration put together — and on a delivered request it points at a record nobody is going to open. The structured record keeps it on every request either way, so dropping it here loses nothing and buys back the width. Where it is kept it goes last, past even the detail, so that neither the fields a reader scans nor the explanation they came for is pushed sideways by it.
    """
    identifier = "3f2a1c88-0d9e-4f77-9a41-2b6c5e0d8a13"
    served = RequestLine(
        method="POST",
        path="/v1/messages",
        request_id=identifier,
        inbound_format="anthropic-messages",
        model="claude-opus-5",
        status_code=200,
        duration_s=1.0,
    )
    assert identifier not in format_completion_line(served, status="ok")
    failed = replace(served, status_code=502, detail="upstream is down")
    assert format_completion_line(failed, status="fail") == f"502 POST /v1/messages claude-opus-5 1.0s: upstream is down req={identifier}"
    # A stream that tore halfway keeps the 200 its headers arrived with, so the status code cannot tell this line from a delivered answer and the resolved status is what has to.
    torn = replace(served, detail="upstream stream ended without a terminal event")
    assert format_completion_line(torn, status="fail").endswith(f"req={identifier}")
    # A client that left is not a success either: nobody received the answer, and that is a line somebody comes looking for.
    assert format_completion_line(served, status="gone").endswith(f"req={identifier}")


def test_the_verdict_rather_than_the_status_code_decides_how_the_line_reads() -> None:
    """The one line that could say `[FAIL]` and read as an answer at the same time.

    A streamed reply's status code is settled the moment upstream's headers arrive, so a stream that tore an hour later still carries a 200. Reading the shape off that code dressed the incident as a delivered turn — green code, route collapsed into `<inbound-format>/<model>` — under a prefix already saying it failed. The verdict decides both, so the two halves of the line can no longer disagree.

    `gone` is amber rather than red, on the ruling `STATUS_PREFIXES` records for `[GONE]`: cancelling a turn is routine on a proxy fronting an interactive client, and painting every Esc the colour of an upstream reset would bury the resets. It still loses the successful shape — nobody received the answer, so nothing about it earned the form that says one arrived.
    """
    torn = RequestLine(
        method="POST",
        path="/v1/messages",
        inbound_format="anthropic-messages",
        model="claude-opus-5",
        status_code=200,
        duration_s=61.0,
        detail="upstream stream ended without a terminal event",
    )
    assert format_completion_line(torn, status="fail").startswith("200 POST /v1/messages claude-opus-5 ")
    assert format_completion_line(torn, status="gone").startswith("200 POST /v1/messages claude-opus-5 ")
    # The same record with the same 200, delivered: this is the shape the two above must not borrow.
    assert format_completion_line(torn, status="ok").startswith("200 anthropic-messages/claude-opus-5 ")
    assert f"{RED}200{RESET}" in format_completion_line(torn, status="fail", color=True)
    assert f"{YELLOW}200{RESET}" in format_completion_line(torn, status="gone", color=True)
    assert f"{GREEN}200{RESET}" in format_completion_line(torn, status="ok", color=True)
    # The account of why wears the verdict's colour too. Left at a fixed red, a cancelled turn read as an incident — amber prefix, amber code, red explanation — which is the reading the amber was chosen to prevent.
    # Twelve seconds rather than the sixty above, so the duration is quiet and any red left in the line can only have come from the detail.
    cancelled = format_completion_line(
        replace(torn, duration_s=12.0, detail="delivery stopped before upstream finished"), status="gone", color=True
    )
    assert RED not in cancelled
    assert f"{YELLOW}delivery stopped before upstream finished{RESET}" in cancelled


def test_a_request_that_never_resolved_a_model_omits_it() -> None:
    # A non-model request shows no model and no tokens. A placeholder would read as a model actually named that.
    line = format_completion_line(
        RequestLine(method="POST", path="/v1/messages", status_code=400, duration_s=0.002, detail="body must be an object"),
        status="fail",
    )
    assert line == "400 POST /v1/messages 2ms: body must be an object"


def test_absent_bytes_are_not_the_same_as_zero() -> None:
    base = RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=1.0)
    assert "↓" not in format_completion_line(base, status="ok")
    assert "↓0B" in format_completion_line(replace(base, bytes_out=0), status="ok")


def test_a_token_count_is_not_a_turn_that_lost_its_reply() -> None:
    """The reported line: `H1 200 anthropic-messages-count-tokens/claude-opus-5 1.2s ↑19.7k provider(local)`.

    Every absence on it was honest — a count has no reply, so no returning bytes, no blocks, no stop reason — but on a successful line the route has already collapsed into `<inbound-format>/<model>`, leaving nothing that says a count is what this was. The same line is what a delivered turn looks like when its whole reply goes missing, which is the one reading a reader must not have to guess at.

    The endpoint says it first, in the slot the route used to occupy: a count and a turn send the same Anthropic body, so the format alone cannot tell them apart. The provider's name is the second half, and the half the endpoint cannot supply — `ghc` is upstream's measurement and `local` is this proxy's estimate; the reply body distinguishes them with `estimated` and the line has only the same bare number.
    """
    counting = RequestLine(
        method="POST",
        path="/v1/messages/count_tokens",
        inbound_format="anthropic-messages",
        count_tokens=True,
        client_protocol="H1",
        model="claude-opus-5",
        status_code=200,
        duration_s=1.2,
        usage={"input_tokens": 19_700},
        count_provider="local",
    )
    line = format_completion_line(counting, status="ok")
    assert line == "H1 200 anthropic-messages-count-tokens/claude-opus-5 1.2s ↑19.7k provider(local)"
    assert "provider(ghc)" in format_completion_line(replace(counting, count_provider="ghc"), status="ok")
    # And the field stays off every line that is not a count, rather than printing a placeholder for the counter that did not run.
    assert "provider(" not in format_completion_line(replace(counting, count_provider=""), status="ok")
    # The endpoint is what the format prefix reports, so it survives a count no provider ever answered — where `count_provider` is empty and could not have said it.
    assert format_completion_line(replace(counting, count_provider=""), status="ok").startswith("H1 200 anthropic-messages-count-tokens/")
    # And it is added only to a count: an ordinary turn keeps the bare format.
    assert format_completion_line(replace(counting, count_tokens=False), status="ok").startswith("H1 200 anthropic-messages/")


def test_an_estimate_says_why_it_is_one() -> None:
    """`local` alone was three outcomes wearing one word, two of them incidents.

    A route with no upstream counter estimates every time and is working as configured; an upstream that was asked and could not answer is something to look at; and an operator who left `ghc` out of `providers` chose the estimate. All three produced the same `provider(local)`, which is the same defect one level up from the one this field was added to fix — the failure was not absent from the line, it was wearing the ordinary case's clothes.

    Ruled 2026-08-20 by the user: the reason goes in the parentheses, and the field stays uncoloured because the ordinary case is the common one and a colour that fires daily stops being read.
    """
    estimating = RequestLine(
        method="POST",
        path="/v1/messages/count_tokens",
        inbound_format="anthropic-messages",
        count_tokens=True,
        client_protocol="H1",
        model="claude-opus-5",
        status_code=200,
        duration_s=1.2,
        usage={"input_tokens": 19_700},
        count_provider="local",
    )
    assert format_completion_line(replace(estimating, count_provider_reason="ghc-failed"), status="ok").endswith("provider(ghc-failed,local)")
    assert format_completion_line(replace(estimating, count_provider_reason="no-counter"), status="ok").endswith("provider(no-counter,local)")
    # Nothing to say is said with nothing: the operator configured this proxy to estimate, and no upstream was involved to have a verdict about.
    assert format_completion_line(estimating, status="ok").endswith("provider(local)")


def test_retries_are_reported_once_the_count_is_final() -> None:
    line = format_completion_line(
        RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=1.0, attempts=3),
        status="ok",
    )
    assert "retries=2" in line


def test_what_each_replay_replaced_is_named_and_the_whole_set_is_bounded() -> None:
    """Three entries, each individually short enough to pass, whose sum is not.

    The bound is applied to the joined string rather than to each entry, and the two are only the same thing when there is one replay. Every entry here is already within `one_line`'s per-entry limit — they arrive that way, cut in `_reopen` — so a per-entry bound would let all three through and put roughly 500 characters on one console line.
    """
    entries = tuple(f"RemoteProtocolError('peer closed connection while receiving attempt {n} of the response body')" for n in (1, 2, 3))
    assert all(one_line(entry) == entry for entry in entries), "the premise: no single entry is over the limit"

    line = format_completion_line(
        RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=1.0, attempts=4, replaced_failures=entries),
        status="ok",
    )
    assert "retries=3" in line
    # The first is what the reader wants most, and it survives the cut.
    assert "attempt 1 of the response body" in line
    assert "more chars)" in line, "the set was cut"
    assert "attempt 3" not in line, "and the cut is what dropped the tail, not a shorter join"


def test_the_byte_marker_degrades_where_the_glyph_cannot_be_encoded() -> None:
    line = format_completion_line(
        RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=1.0, bytes_out=2048),
        unicode=False,
        status="ok",
    )
    assert "↓" not in line
    assert "<2.0KiB" in line


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
        ),
        status="ok",
    )
    # After the fields that describe the exchange, since it describes how the model got to the answer rather than anything about the exchange itself.
    assert line.endswith("end_turn think(enc:1,txt:2)")
    assert DIM in format_completion_line(
        RequestLine(method="POST", path="/p", status_code=200, duration_s=1.0, thinking=("enc",)),
        color=True,
        status="ok",
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
        ),
        status="ok",
    )
    assert line.startswith("H2/H1 200 ")


def test_a_leg_that_never_happened_is_not_invented() -> None:
    # A request refused before it reached upstream has one leg, and printing a placeholder for the other would describe a connection that was never made.
    line = format_completion_line(
        RequestLine(method="POST", path="/p", client_protocol="H1", status_code=400, duration_s=0.001),
        status="fail",
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
        ),
        status="ok",
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
        ),
        status="ok",
    )
    assert "called(Bash,Bash,Read)" in line
    assert "tool_use" not in line and "function_call" not in line
    # Still last, and still the thing the eye stops on.
    assert line.endswith(": upstream stream ended without a terminal event")


def test_colour_is_off_unless_asked_for() -> None:
    # The plain form is the one every other assertion in this file reads, and the one a pipe or a `TERM=dumb` terminal gets. Colour is a rendering choice made from the probe, never a default.
    line = RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=500, duration_s=1.0, detail="boom")
    assert "\x1b" not in format_completion_line(line, status="ok")
    assert "\x1b" in format_completion_line(line, color=True, status="ok")


def test_the_duration_escalates_on_its_own() -> None:
    """A slow request should be visible without reading the number.

    Thresholds ported from `copilot-api-js`: white up to 20s, yellow to 60s, red to 180s, bold red beyond.
    """
    def coloured(seconds: float) -> str:
        return format_completion_line(
            RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=seconds),
            color=True,
            status="ok",
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
        status="fail",
    )
    assert line == f"{RED}400{RESET} POST /v1/messages: {RED}body must be an object{RESET}"


def test_a_failing_status_and_its_reason_are_red() -> None:
    line = format_completion_line(
        RequestLine(method="POST", path="/p", status_code=429, duration_s=1.0, detail="rate limited"),
        color=True,
        status="fail",
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
        ),
        status="ok",
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
        ),
        status="ok",
    )
    assert "→" not in line
    assert "f/same-model" in line


def test_both_upstream_http_body_directions_are_reported() -> None:
    # The reported gap: only the streaming path counted upstream response-body bytes, so every other request showed no byte field at all.
    line = format_completion_line(
        RequestLine(method="POST", path="/p", inbound_format="f", model="m", status_code=200, duration_s=1.0, bytes_in=152, bytes_out=2300),
        status="ok",
    )
    assert "↑152B ↓2.2KiB" in line


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
        ),
        status="ok",
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


def test_unknown_input_is_not_rendered_as_a_measured_zero() -> None:
    assert format_tokens({"output_tokens": 2}) == "↓2"
    partial = format_tokens({"cache_read_input_tokens": 5, "output_tokens": 2})
    assert partial == "↑?+5 ↓2"
    assert "↻" not in partial


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


def _responses_observation_and_line(
    body: dict[str, object],
    *,
    status: LogStatus = "ok",
) -> tuple[ResponseObservation, str]:
    observer = ResponsesObserver()
    observer.observe_response(body)
    observation = observer.snapshot()
    return observation, format_completion_line(
        RequestLine(
            method="POST",
            path="/responses",
            inbound_format="openai-responses",
            model="gpt-model",
            status_code=200,
            stop_reason="tool_use",
            dialect=ReplyDialect.RESPONSES,
        ),
        status=status,
        response_observation=observation,
    )


def _responses_observation_line(
    body: dict[str, object],
    *,
    status: LogStatus = "ok",
) -> str:
    return _responses_observation_and_line(body, status=status)[1]


def _assert_output_item_identity(
    observation: ResponseObservation,
    expected: tuple[tuple[int, str | None, str | None], ...],
) -> None:
    assert observation.output_items is not None
    assert tuple(
        (item.output_index, item.type, item.name) for item in observation.output_items
    ) == expected


def test_responses_observation_renders_actual_function_and_reasoning() -> None:
    line = _responses_observation_line({
        "status": "completed",
        "output": [
            {"type": "function_call", "name": "Bash"},
            {"type": "reasoning", "summary": [], "encrypted_content": "sealed"},
        ],
    })

    assert line.endswith("completed function_call(Bash) reason(enc:1)")
    assert "tool_use" not in line


def test_responses_observation_does_not_call_a_custom_action_a_function() -> None:
    line = _responses_observation_line({
        "status": "completed",
        "output": [{"type": "custom_tool_call", "name": "run_shell"}],
    })

    assert line.endswith("completed custom_tool_call(run_shell)")
    assert "function_call" not in line


def test_responses_observation_groups_adjacent_calls_without_deduplicating() -> None:
    observation, line = _responses_observation_and_line({
        "status": "completed",
        "output": [
            {"type": "function_call", "name": "Read"},
            {"type": "function_call", "name": "Read"},
            {"type": "function_call", "name": "Read"},
            {"type": "function_call", "name": "Read"},
        ],
    })

    assert line.endswith("completed function_call(Read,Read,Read,Read)")
    _assert_output_item_identity(
        observation,
        (
            (0, "function_call", "Read"),
            (1, "function_call", "Read"),
            (2, "function_call", "Read"),
            (3, "function_call", "Read"),
        ),
    )


def test_responses_observation_groups_only_adjacent_actual_type_runs() -> None:
    grouped_observation, grouped = _responses_observation_and_line({
        "status": "completed",
        "output": [
            {"type": "custom_tool_call", "name": "exec"},
            {"type": "function_call", "name": "Read"},
            {"type": "function_call", "name": "Bash"},
            {"type": "function_call", "name": "Read"},
        ],
    })
    interleaved_observation, interleaved = _responses_observation_and_line({
        "status": "completed",
        "output": [
            {"type": "function_call", "name": "Read"},
            {"type": "custom_tool_call", "name": "exec"},
            {"type": "function_call", "name": "Bash"},
        ],
    })

    assert grouped.endswith("completed custom_tool_call(exec) function_call(Read,Bash,Read)")
    _assert_output_item_identity(
        grouped_observation,
        (
            (0, "custom_tool_call", "exec"),
            (1, "function_call", "Read"),
            (2, "function_call", "Bash"),
            (3, "function_call", "Read"),
        ),
    )
    assert interleaved.endswith("completed function_call(Read) custom_tool_call(exec) function_call(Bash)")
    _assert_output_item_identity(
        interleaved_observation,
        (
            (0, "function_call", "Read"),
            (1, "custom_tool_call", "exec"),
            (2, "function_call", "Bash"),
        ),
    )


def test_non_client_items_do_not_break_the_displayed_action_run() -> None:
    observation, line = _responses_observation_and_line({
        "status": "completed",
        "output": [
            {"type": "function_call", "name": "Read"},
            {"type": "reasoning", "summary": [], "encrypted_content": "sealed"},
            {"type": "message"},
            {"type": "web_search_call"},
            {"type": "function_call", "name": "Bash"},
        ],
    })

    assert line.endswith("completed function_call(Read,Bash) reason(enc:1)")
    _assert_output_item_identity(
        observation,
        (
            (0, "function_call", "Read"),
            (1, "reasoning", None),
            (2, "message", None),
            (3, "web_search_call", None),
            (4, "function_call", "Bash"),
        ),
    )


def test_anonymous_and_unknown_actions_break_named_runs_without_disappearing() -> None:
    body: dict[str, object] = {
        "status": "completed",
        "output": [
            {"type": "function_call", "name": "Read"},
            {"type": "function_call", "name": ""},
            {"type": "function_call", "name": ""},
            {"type": "function_call", "name": "Bash"},
            {"type": "some_2027_tool_call", "name": "future"},
            {"type": "function_call", "name": "Read"},
            {"type": "function_call", "name": None},
            {"type": "function_call", "name": "Bash"},
        ],
    }
    observation, line = _responses_observation_and_line(body)

    assert line.endswith(
        "completed function_call(Read) function_call function_call function_call(Bash) "
        "client_action(some_2027_tool_call?) function_call(Read) function_call function_call(Bash)"
    )
    _assert_output_item_identity(
        observation,
        (
            (0, "function_call", "Read"),
            (1, "function_call", ""),
            (2, "function_call", ""),
            (3, "function_call", "Bash"),
            (4, "some_2027_tool_call", "future"),
            (5, "function_call", "Read"),
            (6, "function_call", None),
            (7, "function_call", "Bash"),
        ),
    )


def test_grouping_uses_raw_types_before_bounded_display_encoding() -> None:
    prefix = "x" * 121
    raw_types = (f"{prefix}a", f"{prefix}b")
    observer = ResponsesObserver()
    observer.observe_response({
        "status": "completed",
        "output": [
            {"type": raw_types[0], "name": "Read"},
            {"type": raw_types[1], "name": "Bash"},
        ],
    })
    observation = observer.snapshot()
    assert observation.output_items is not None
    required = ClientActionObservation(
        requirement=ClientActionRequirement.REQUIRED,
        basis=ClientActionBasis.KNOWN_CLIENT_ACTION,
        delivery_required=True,
    )
    rendered_observation = replace(
        observation,
        output_items=tuple(
            replace(item, client_action=required) for item in observation.output_items
        ),
    )
    line = format_completion_line(
        RequestLine(
            method="POST",
            path="/responses",
            inbound_format="openai-responses",
            model="gpt-model",
            status_code=200,
            dialect=ReplyDialect.RESPONSES,
        ),
        status="ok",
        response_observation=rendered_observation,
    )
    display_type = f"{'x' * 119}…"

    _assert_output_item_identity(
        rendered_observation,
        (
            (0, raw_types[0], "Read"),
            (1, raw_types[1], "Bash"),
        ),
    )
    assert line.endswith(f"completed {display_type}(Read) {display_type}(Bash)")
    assert f"{display_type}(Read,Bash)" not in line


def test_grouped_names_are_made_inert_before_renderer_commas_are_added() -> None:
    observation, line = _responses_observation_and_line({
        "status": "completed",
        "output": [
            {"type": "function_call", "name": "Read,now"},
            {"type": "function_call", "name": "Bash)\x1b"},
        ],
    })

    assert line.endswith(
        "completed function_call(Read\\u002cnow,Bash\\u0029\\u001b)"
    )
    assert "Read,now" not in line
    assert "\x1b" not in line
    _assert_output_item_identity(
        observation,
        (
            (0, "function_call", "Read,now"),
            (1, "function_call", "Bash)\x1b"),
        ),
    )


def test_responses_observation_keeps_an_unknown_action_unknown() -> None:
    line = _responses_observation_line({
        "status": "completed",
        "output": [{"type": "some_2027_tool_call"}],
    })

    assert line.endswith("completed client_action(some_2027_tool_call?)")
    assert "function_call" not in line


def test_responses_observation_renders_incomplete_and_failure_statuses() -> None:
    incomplete = _responses_observation_line({
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [],
    })
    failed = _responses_observation_line(
        {
            "status": "failed",
            "error": {"code": "server_error", "message": "provider failed"},
            "output": [],
        },
        status="fail",
    )

    assert incomplete.endswith("incomplete(max_output_tokens)")
    assert failed.endswith("failed")
    assert "completed" not in failed


def test_responses_failure_events_keep_their_actual_terminal_names() -> None:
    for event_type, payload, expected in (
        (
            "response.failed",
            {"response": {"error": {"code": "server_error", "message": "boom"}}},
            "failed",
        ),
        (
            "response.cancelled",
            {"response": {"error": {"code": "cancelled", "message": "boom"}}},
            "cancelled",
        ),
        (
            "error",
            {"type": "error", "code": "stream_error", "message": "boom"},
            "error(stream_error)",
        ),
        ("error", {"error": {"message": "boom"}}, "error"),
        ("error", {"type": "error", "message": "boom"}, "error"),
    ):
        observer = ResponsesObserver()
        observer.observe_event(
            SseEvent(event=event_type, data=orjson.dumps(payload).decode())
        )
        observation = observer.snapshot()
        line = format_completion_line(
            RequestLine(
                method="POST",
                path="/responses",
                inbound_format="openai-responses",
                model="gpt-model",
                status_code=200,
                dialect=ReplyDialect.RESPONSES,
            ),
            status="fail",
            response_observation=observation,
        )

        assert observation.provider_failed is True
        assert observation.error_summary is not None
        assert observation.error_summary.message == "boom"
        assert line.endswith(expected)


def test_provider_tokens_are_inert_inside_the_completion_grammar() -> None:
    line = _responses_observation_line({
        "status": "incomplete",
        "incomplete_details": {
            "reason": "max) failed,\x1b[31m\tline\nnext\\end",
        },
        "output": [
            {
                "type": "custom_tool_call) failed",
                "name": "run, now\x00\x1b[0m",
            }
        ],
    })

    assert "\x1b" not in line and "\x00" not in line
    assert "max\\u0029\\u0020failed\\u002c\\u001b" in line
    assert "\\u0009line\\u000anext\\u005cend" in line
    assert "custom_tool_call\\u0029\\u0020failed" in line

    raw_name = "run, now\x00\x1b[0m\\again"
    named_observer = ResponsesObserver()
    named_observer.observe_response({
        "status": "completed",
        "output": [{"type": "custom_tool_call", "name": raw_name}],
    })
    named_observation = named_observer.snapshot()
    named_line = format_completion_line(
        RequestLine(
            method="POST",
            path="/responses",
            inbound_format="openai-responses",
            model="gpt-model",
            status_code=200,
            dialect=ReplyDialect.RESPONSES,
        ),
        status="ok",
        response_observation=named_observation,
    )
    assert named_observation.output_items is not None
    assert named_observation.output_items[0].name == raw_name
    assert "\x1b" not in named_line and "\x00" not in named_line
    assert "run\\u002c\\u0020now\\u0000\\u001b" in named_line
    assert "\\u005cagain" in named_line

    error_observer = ResponsesObserver()
    error_observer.observe_event(
        SseEvent(
            event="error",
            data=orjson.dumps({
                "type": "error",
                "code": "bad)\\code\t\x1b",
                "message": "boom",
            }).decode(),
        )
    )
    error_line = format_completion_line(
        RequestLine(method="POST", path="/responses", status_code=200),
        status="fail",
        response_observation=error_observer.snapshot(),
    )
    assert "error(bad\\u0029\\u005ccode\\u0009\\u001b)" in error_line
    assert "\x1b" not in error_line

    long_name = "x)" * 200
    long_observer = ResponsesObserver()
    long_observer.observe_response({
        "status": "completed",
        "output": [{"type": "custom_tool_call", "name": long_name}],
    })
    long_observation = long_observer.snapshot()
    long_line = format_completion_line(
        RequestLine(method="POST", path="/responses", status_code=200),
        status="ok",
        response_observation=long_observation,
    )
    assert long_observation.output_items is not None
    assert long_observation.output_items[0].name == long_name
    assert "…" in long_line
    assert len(long_line) < 200


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
        ),
        status="ok",
    )
    assert line.endswith("function_call(Bash) reason(enc:1)")


def _received(byte_count: int) -> str:
    """One line's rendering of `byte_count` coming back. No duration: that field is white too, and a bare `WHITE in line` would then pass with the byte field left grey."""
    return format_completion_line(
        RequestLine(method="POST", path="/p", status_code=200, bytes_out=byte_count),
        color=True,
        status="ok",
    )


def test_what_came_back_escalates_with_its_size() -> None:
    """A reply an order of magnitude larger than usual should be visible without reading the number.

    Asserted as whole spans — marker, printed figure and colour together — because that is the thing a reader sees, and because a bare colour check passes on any other coloured field in the line.
    """
    def field(byte_count: int) -> str:
        return _received(byte_count).split()[-1]

    assert field(5 * 1024) == f"{DIM}↓5.0KiB{RESET}"
    # The middle rung carries no escape at all: an explicit white was brighter than the untouched text beside it and read as emphasis. Compared for equality so a stray code fails here rather than being invisible to an `in` check.
    assert field(10 * 1024) == "↓10.0KiB"
    assert field(50 * 1024) == "↓50.0KiB"
    assert field(100 * 1024) == f"{YELLOW}↓100.0KiB{RESET}"


def test_the_thresholds_are_the_round_numbers() -> None:
    # Exactly `10 * 1024`, not the point where the printed figure reaches `10.0KiB`. Both counts below print `10.0KiB`, so the same shown number comes out grey on one line and untouched on the next — accepted, because the threshold being the round number is what was asked for.
    assert _received(10 * 1024 - 1).split()[-1] == f"{DIM}↓10.0KiB{RESET}"
    assert _received(10 * 1024).split()[-1] == "↓10.0KiB"


def test_how_large_is_large_is_read_off_the_dialect() -> None:
    """The same byte count is ordinary on one path and worth seeing on the other.

    Both figures are counted at the same place and in the same units, and a Responses reply still costs tens of times more per output token on this proxy's traffic. A single pair of thresholds therefore cannot discriminate on both paths: the pair that suits Anthropic traffic leaves nearly every Responses line lit, and a column lit on almost every line has stopped saying anything. Why the wire costs that much is recorded at `RECEIVED_BYTES_THRESHOLDS`; what this test fixes is only that the two paths are judged apart.

    Asserted as the same count rendered under each dialect rather than as two independent thresholds, because that is the property being bought: what the colour means is "unusual for this path", so the interesting failure is the two paths agreeing.
    """

    def field(byte_count: int, dialect: ReplyDialect) -> str:
        return format_completion_line(
            RequestLine(method="POST", path="/p", status_code=200, bytes_out=byte_count, dialect=dialect),
            color=True,
            status="ok",
        ).split()[-1]

    # 100KiB tops out the Anthropic scale and is unremarkable on the Responses one, where the current client's tool declarations alone are observed to put 57-58KiB under a reply of any size.
    assert field(100 * 1024, ReplyDialect.ANTHROPIC) == f"{YELLOW}↓100.0KiB{RESET}"
    assert field(100 * 1024, ReplyDialect.RESPONSES) == f"{DIM}↓100.0KiB{RESET}"

    # Both rungs pinned from below as well as on the mark. Without the just-below counts these assertions pass for any thresholds bracketing them — `(256KiB, 3MiB)` satisfies every on-the-mark line above — so the pair could drift down to where it was lighting every line again without a test noticing.
    assert field(384 * 1024 - 1, ReplyDialect.RESPONSES) == f"{DIM}↓384.0KiB{RESET}"
    assert field(384 * 1024, ReplyDialect.RESPONSES) == "↓384.0KiB"
    assert field(4 * 1024 * 1024 - 1, ReplyDialect.RESPONSES) == "↓4.0MiB"
    assert field(4 * 1024 * 1024, ReplyDialect.RESPONSES) == f"{YELLOW}↓4.0MiB{RESET}"


def test_what_went_out_stays_quiet_however_large() -> None:
    # Its size follows from the request the client made, so it says nothing about how the reply went. Escalating it would put a warm colour on every long-context turn and mean nothing by it.
    line = format_completion_line(
        RequestLine(method="POST", path="/p", status_code=200, duration_s=1.0, bytes_in=5_000_000),
        color=True,
        status="ok",
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
        ),
        status="ok",
    )
