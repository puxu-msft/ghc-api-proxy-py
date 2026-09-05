"""The footer's width algorithm and what it chooses to show.

Driven directly rather than through a terminal: `build_footer` takes the active set, the time and the column count and returns a string, so every branch of the two-pass budget is reachable without a pty. The rendered-screen invariants live in `tests/tui/`.
"""

from app.observability.footer import ActiveRequest, build_footer

NOW = 1_000.0


def _request(request_id: str, model: str, age: float, upstream_response_bytes: int | None = None, attempts: int = 1) -> ActiveRequest:
    return ActiveRequest(request_id=request_id, model=model, started_at=NOW - age, upstream_response_bytes=upstream_response_bytes, attempts=attempts)


def test_open_connections_are_shown_as_their_own_block() -> None:
    active = [_request("a", "gpt-5", 1.0)]
    assert build_footer(active, NOW, 200, connections=2) == "[<-->] 2 clients | gpt-5 1.0s"
    assert build_footer(active, NOW, 200, connections=1).startswith("[<-->] 1 clients | ")


def test_connections_are_shown_even_with_nothing_in_flight() -> None:
    """The combination this field exists for.

    A pooled client holds its connection between requests, so a drain can be waiting on something the request list cannot show. Without this the footer goes blank and a stalled shutdown is indistinguishable from a finished one — which is exactly the report that prompted the field.
    """
    assert build_footer([], NOW, 200, connections=1, draining=True) == "[DRIN] 1 clients"
    # Nothing at all to report is still nothing at all.
    assert build_footer([], NOW, 200, connections=0) == ""


def test_requests_of_one_model_are_separated_by_commas() -> None:
    """Where one request ends and the next begins.

    Joined by a space, `48.6s ↓15.6KiB 28.3s` reads as a single request with three fields, and the reader cannot tell otherwise because any field may be absent — the third request here has no byte count at all.
    """
    active = [
        _request("a", "claude-opus-5", 48.6, upstream_response_bytes=15_974),
        _request("b", "claude-opus-5", 28.3, upstream_response_bytes=8_396),
        _request("c", "claude-opus-5", 3.6),
    ]
    assert build_footer(active, NOW, 200) == "[<-->] claude-opus-5 x3 48.6s ↓15.6KiB, 28.3s ↓8.2KiB, 3.6s"


def test_draining_says_so_in_the_prefix() -> None:
    """A stopped listener changes what the same list means.

    From here it can only shrink and nothing new will join it, so a footer that looked identical either way would leave a busy server and one on its way out indistinguishable.
    """
    active = [_request("a", "gpt-5", 1.0)]
    assert build_footer(active, NOW, 80).startswith("[<-->] ")
    assert build_footer(active, NOW, 80, draining=True).startswith("[DRIN] ")


def test_the_draining_prefix_is_the_same_width() -> None:
    # A prefix that changed width would shift the whole line sideways at the moment the state changes, which reads as the display restarting rather than as the process changing what it is doing.
    active = [_request("a", "gpt-5", 1.0)]
    assert len(build_footer(active, NOW, 80)) == len(build_footer(active, NOW, 80, draining=True))


def test_no_active_requests_render_nothing() -> None:
    # Empty rather than a blank line: the caller draws no footer at all, and a line of spaces would still occupy a row.
    assert build_footer([], NOW, 80) == ""


def test_one_segment_per_model_with_a_count_of_what_it_actually_has() -> None:
    line = build_footer([_request("a", "gpt-5", 2.0), _request("b", "gpt-5", 1.0)], NOW, 200)
    assert line.startswith("[<-->] gpt-5 x2 ")
    # Each request keeps its own elapsed; the model name is the only thing that merges.
    assert "2.0s" in line
    assert "1.0s" in line


def test_requests_and_models_are_ordered_oldest_first() -> None:
    line = build_footer(
        [_request("new", "fast-model", 1.0), _request("old", "slow-model", 90.0)],
        NOW,
        200,
    )
    # A model's position is that of its oldest request, so the one worth worrying about survives the width budget and the newest is what gets cut.
    assert line.index("slow-model") < line.index("fast-model")


def test_an_unresolved_model_renders_as_resolving() -> None:
    assert "(resolving)" in build_footer([_request("a", "", 1.0)], NOW, 80)


def test_a_model_actually_named_resolving_does_not_merge_with_unresolved_ones() -> None:
    # The grouping key is the raw model string; `(resolving)` is only a rendering of "not known yet". Merging the two would report one model where there are two.
    line = build_footer([_request("a", "", 1.0), _request("b", "(resolving)", 2.0)], NOW, 200)
    assert "x2" not in line


def test_absent_byte_count_is_not_the_same_as_zero() -> None:
    # No bytes field means nothing has streamed back yet; `0B` means it streamed and produced nothing.
    assert "↓" not in build_footer([_request("a", "gpt-5", 1.0)], NOW, 80)
    assert "↓0B" in build_footer([_request("a", "gpt-5", 1.0, upstream_response_bytes=0)], NOW, 80)


def test_retries_are_reported_next_to_the_elapsed() -> None:
    assert "(2)" in build_footer([_request("a", "gpt-5", 5.0, attempts=3)], NOW, 80)


def test_sub_second_requests_keep_millisecond_precision() -> None:
    assert "250ms" in build_footer([_request("a", "gpt-5", 0.25)], NOW, 80)


def test_the_line_never_exceeds_one_terminal_row() -> None:
    # The hard invariant. Measured failure without it: at 40 columns the footer wraps onto a second row every run.
    active = [_request(str(index), f"model-with-a-long-name-{index}", float(index), upstream_response_bytes=index * 4096) for index in range(12)]
    for columns in (20, 40, 60, 80, 120):
        assert len(build_footer(active, NOW, columns)) <= columns - 1


def test_control_characters_cannot_smuggle_in_a_second_row() -> None:
    # A model name is upstream-supplied. A newline in one would break the invariant at any width, so it is stripped rather than truncated away.
    line = build_footer([_request("a", "evil\nmodel", 1.0)], NOW, 200)
    assert "\n" not in line
    assert "evilmodel" in line


def test_models_that_do_not_fit_collapse_into_a_counted_tail() -> None:
    active = [_request(str(index), f"model-{index}", float(20 - index)) for index in range(6)]
    line = build_footer(active, NOW, 46)
    assert "more" in line
    # The tail counts models that were dropped, so the total is still recoverable from the line.
    shown = sum(1 for index in range(6) if f"model-{index}" in line)
    dropped = int(line.split("+")[-1].split(" ")[0])
    assert shown + dropped == 6


def test_leftover_width_is_shared_round_robin_rather_than_by_first_come() -> None:
    # Two models, two requests each, and room for three items in total. A greedy pass would spend both spare columns on the first model; round-robin gives the second model its own.
    active = [
        _request("a1", "alpha", 9.0),
        _request("a2", "alpha", 8.0),
        _request("b1", "bravo", 7.0),
        _request("b2", "bravo", 6.0),
    ]
    wide = build_footer(active, NOW, 200)
    assert wide.count("x2") == 2
    narrow = build_footer(active, NOW, 44)
    # Both models are still named even though neither can show everything.
    assert "alpha" in narrow
    assert "bravo" in narrow


def test_the_byte_marker_degrades_where_the_glyph_cannot_be_encoded() -> None:
    line = build_footer([_request("a", "gpt-5", 1.0, upstream_response_bytes=2048)], NOW, 80, unicode=False)
    assert "↓" not in line
    # Still marked rather than dropped: a bare number would read as a second time field.
    assert "<2.0KiB" in line
