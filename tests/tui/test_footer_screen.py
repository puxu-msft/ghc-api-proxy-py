"""What the footer actually puts on the screen.

The invariants here cannot be reached from the byte stream. "The log line survived" and "the footer did not land on top of it" are statements about a grid of characters plus scrollback, so the output is replayed through a terminal emulator and scored there.

The negative control is not decoration. An earlier version of this scoring reported a deliberately broken footer as clean, because the corruption it produces keeps the log ordinal intact and overwrites the `[<-->]` prefix — so neither a missing-ordinal count nor a marker search could see it. `test_the_scoring_catches_a_footer_that_scrolled_out_of_place` is what makes the passing results below mean anything.
"""

import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
from dataclasses import dataclass
from pathlib import Path

import pyte
import pytest

DRIVER = Path(__file__).parent / "_footer_driver.py"
NAIVE_DRIVER = Path(__file__).parent / "_naive_footer_driver.py"
ROWS = 24
COLS = 80
LOG_PATTERN = re.compile(r"LOG-(\d{4})")
FOOTER_MARK = "[<-->]"
# The production driver reserves this model name for the live footer. Seeing it outside the current footer row proves a redraw left debris; completion lines may legitimately carry durations of their own.
FOOTER_DEBRIS = re.compile(r"FOOTER-MODEL")


@dataclass(frozen=True, slots=True)
class RunCapture:
    final: pyte.HistoryScreen
    live: pyte.HistoryScreen | None
    raw: bytes


def _run(
    script: Path,
    lines: int,
    ticks: int,
    *,
    columns: int = COLS,
    hold_live: bool = False,
) -> RunCapture:
    """Run `script` attached to a pty and replay everything it wrote onto a screen.

    `openpty` plus `subprocess` rather than `pty.fork`: under pytest the child of a fork inherits a `sys.stdout` that capture has replaced with a non-file object, so asking it for a descriptor raises and the child dies before it can exec — leaving an empty capture that every "nothing was corrupted" assertion passes. Sizing the slave before spawning also removes the race where the child renders its first frame against the default 80x24.
    """
    master, slave = pty.openpty()
    fcntl.ioctl(
        slave,
        termios.TIOCSWINSZ,
        struct.pack("HHHH", ROWS, columns, 0, 0),
    )
    environment = {
        **os.environ,
        "TERM": "xterm-256color",
        "COLUMNS": str(columns),
        "LINES": str(ROWS),
        "HOLD_LIVE": "1" if hold_live else "0",
    }
    process = subprocess.Popen(
        [sys.executable, str(script), str(lines), str(ticks)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=environment,
        close_fds=True,
    )
    os.close(slave)

    chunks: list[bytes] = []
    live_raw: bytes | None = None
    released = not hold_live
    while True:
        ready, _, _ = select.select([master], [], [], 30.0)
        if not ready:
            break
        try:
            data = os.read(master, 65536)
        except OSError:
            # The pty reports the far end closing as EIO rather than as end of file.
            break
        if not data:
            break
        chunks.append(data)
        observed = b"".join(chunks)
        if (
            hold_live
            and not released
            and b"DRIVER-READY" in observed
            and FOOTER_MARK.encode() in observed
        ):
            live_raw = observed
            os.write(master, b"\n")
            released = True
    os.close(master)
    assert released, "the child never reached its live-footer handshake"
    assert process.wait(timeout=30) == 0, f"{script.name} exited non-zero"

    raw = b"".join(chunks)
    final = _screen(raw, columns)
    live = _screen(live_raw, columns) if live_raw is not None else None
    return RunCapture(final=final, live=live, raw=raw)


def _screen(data: bytes, columns: int) -> pyte.HistoryScreen:
    screen = pyte.HistoryScreen(columns, ROWS, history=4000)
    pyte.ByteStream(screen).feed(data)
    return screen


def _scrollback(screen: pyte.HistoryScreen) -> list[str]:
    """History rows are dict-like rather than strings, so they are assembled column by column."""
    return ["".join(row[column].data for column in sorted(row)) for row in screen.history.top]


def _found_ordinals(screen: pyte.HistoryScreen) -> set[int]:
    everything = "\n".join([*_scrollback(screen), *screen.display])
    return {int(match) for match in LOG_PATTERN.findall(everything)}


def _debris(screen: pyte.HistoryScreen) -> list[str]:
    """Rows carrying footer text that are not the footer's own row."""
    rows = [*_scrollback(screen), *[row for row in screen.display if FOOTER_MARK not in row]]
    return [row.rstrip() for row in rows if FOOTER_DEBRIS.search(row)]


def test_the_scoring_catches_a_footer_that_scrolled_out_of_place() -> None:
    """The negative control. Without it, a clean report below would be worth nothing.

    `_naive_footer_driver.py` draws the same footer with no reserved region and no accounting for how many rows it occupies, which is the mistake this whole design exists to avoid.
    """
    screen = _run(NAIVE_DRIVER, lines=30, ticks=2).final
    assert _debris(screen), "the naive footer must be caught, or the scoring proves nothing"


@pytest.mark.parametrize("columns", [40, 80])
@pytest.mark.parametrize("ticks", [1, 15])
def test_no_log_line_is_swallowed_or_overwritten(ticks: int, columns: int) -> None:
    """Both dense and sparse logs at narrow and ordinary terminal widths."""
    screen = _run(DRIVER, lines=30, ticks=ticks, columns=columns).final
    assert _found_ordinals(screen) == set(range(1, 31))
    assert _debris(screen) == []


@pytest.mark.parametrize("columns", [40, 80])
def test_production_responses_fields_and_inert_provider_token_cross_the_pty(
    columns: int,
) -> None:
    capture = _run(DRIVER, lines=3, ticks=1, columns=columns)
    raw = capture.raw
    escaped = (
        b"provider\\u0029\\u001b\\u005b31m"
        b"\\u002c\\u000a\\u005c"
    )

    assert b"completed" in raw
    assert b"custom_tool_call" in raw
    assert escaped in raw
    assert "…".encode() in raw
    assert b"provider)\x1b[31m,\n\\" not in raw
    assert b"\x1b[32mcompleted\x1b[0m" in raw, "the formatter-owned completed style never crossed Rich"
    assert _found_ordinals(capture.final) == {1, 2, 3}


@pytest.mark.parametrize("columns", [40, 80])
def test_the_footer_is_visible_below_the_live_log_region(columns: int) -> None:
    capture = _run(
        DRIVER,
        lines=30,
        ticks=3,
        columns=columns,
        hold_live=True,
    )
    assert capture.live is not None
    visible = [row.rstrip() for row in capture.live.display]
    footer_rows = [index for index, row in enumerate(visible) if FOOTER_MARK in row]
    ready_rows = [index for index, row in enumerate(visible) if "DRIVER-READY" in row]
    # Exactly one footer while Live is active, below a log row observed at the same handshake—not an optional assertion after transient cleanup erased it.
    assert len(footer_rows) == 1
    assert len(ready_rows) == 1
    assert footer_rows[0] > ready_rows[0]


@pytest.mark.parametrize("columns", [40, 80])
def test_no_footer_copy_is_left_in_scrollback(columns: int) -> None:
    # Scrollback is what the operator scrolls back through. A footer corpse per scroll makes it unreadable, and unlike a live-region glitch it never repaints away.
    screen = _run(DRIVER, lines=30, ticks=3, columns=columns).final
    assert [row for row in _scrollback(screen) if FOOTER_MARK in row] == []
