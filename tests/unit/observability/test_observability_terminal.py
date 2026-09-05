"""What the capability probe concludes from a stream and an environment.

Both inputs are injected, so every combination is reachable without a terminal and without touching the real `os.environ`.
"""

import io

from app.observability.terminal import DIM, RESET, detect_terminal, paint


class _Stream(io.TextIOWrapper):
    """A stream with a real encoding that answers `isatty` however the test needs.

    Wrapping a `BytesIO` rather than faking an `encoding` attribute: the probe asks whether the glyph survives this stream's encoding, and a made-up attribute would test the probe against a fiction. Here the encode either works or raises for the same reason it would in production.
    """

    def __init__(self, *, tty: bool, encoding: str = "utf-8") -> None:
        super().__init__(io.BytesIO(), encoding=encoding)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_an_interactive_terminal_gets_everything() -> None:
    caps = detect_terminal(_Stream(tty=True), {"TERM": "xterm-256color"})
    assert (caps.live, caps.color, caps.unicode) == (True, True, True)


def test_a_pipe_gets_no_live_region() -> None:
    # The decisive case. A live region rewrites lines already emitted, so anything consuming the output as a byte stream would receive cursor movements instead of a log.
    caps = detect_terminal(_Stream(tty=False), {"TERM": "xterm-256color"})
    assert caps.live is False
    assert caps.color is False


def test_a_pipe_still_carries_unicode() -> None:
    # Deliberately independent of `live`: a file renders UTF-8 correctly, and degrading the byte-count glyph there would be a loss for no reason.
    assert detect_terminal(_Stream(tty=False), {"TERM": "xterm"}).unicode is True


def test_a_dumb_terminal_is_a_terminal_that_takes_plain_lines_only() -> None:
    caps = detect_terminal(_Stream(tty=True), {"TERM": "dumb"})
    assert caps.live is False
    assert caps.color is False


def test_a_terminal_with_no_term_at_all_is_treated_as_dumb() -> None:
    assert detect_terminal(_Stream(tty=True), {}).live is False


def test_ci_is_a_terminal_nobody_is_watching() -> None:
    caps = detect_terminal(_Stream(tty=True), {"TERM": "xterm", "CI": "true"})
    assert caps.live is False


def test_no_color_withholds_colour_without_taking_the_footer_down() -> None:
    # `NO_COLOR` is a statement about colour, not about whether a live region is appropriate. Collapsing the two would make the convention silently disable a feature it says nothing about.
    caps = detect_terminal(_Stream(tty=True), {"TERM": "xterm", "NO_COLOR": "1"})
    assert caps.color is False
    assert caps.live is True


def test_an_encoding_that_cannot_carry_the_glyph_withholds_unicode() -> None:
    caps = detect_terminal(_Stream(tty=True, encoding="ascii"), {"TERM": "xterm"})
    assert caps.unicode is False
    # The footer itself is still fine — only its decoration degrades.
    assert caps.live is True


def test_a_stream_that_refuses_to_answer_is_treated_as_not_a_terminal() -> None:
    class _Closed(io.StringIO):
        def isatty(self) -> bool:
            raise ValueError("I/O operation on closed file")

    # Erring towards plain output: the cost of being wrong this way is a missing footer, and the cost of the other way is escape sequences in somebody's log file.
    assert detect_terminal(_Closed(), {"TERM": "xterm"}).live is False


def test_an_empty_colour_leaves_the_text_alone() -> None:
    # How "no colour" is expressed by a ramp whose middle rung is the terminal's own foreground. A naive format string would emit a bare reset here, which would end whatever span came before it.
    assert paint("50.0KiB", "", color=True) == "50.0KiB"
    assert paint("50.0KiB", DIM, color=True) == f"{DIM}50.0KiB{RESET}"
