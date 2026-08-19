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
from pathlib import Path

import pyte
import pytest

DRIVER = Path(__file__).parent / "_footer_driver.py"
NAIVE_DRIVER = Path(__file__).parent / "_naive_footer_driver.py"
ROWS = 24
COLS = 80
LOG_PATTERN = re.compile(r"LOG-(\d{4})")
FOOTER_MARK = "[<-->]"
# The footer is the only thing that prints an elapsed field, so this pattern anywhere else is footer debris left by a redraw that outran its anchor.
FOOTER_DEBRIS = re.compile(r"\d+\.\d\ds|\d+ms")


def _run(script: Path, lines: int, ticks: int) -> pyte.HistoryScreen:
    """Run `script` attached to a pty and replay everything it wrote onto a screen.

    `openpty` plus `subprocess` rather than `pty.fork`: under pytest the child of a fork inherits a `sys.stdout` that capture has replaced with a non-file object, so asking it for a descriptor raises and the child dies before it can exec — leaving an empty capture that every "nothing was corrupted" assertion passes. Sizing the slave before spawning also removes the race where the child renders its first frame against the default 80x24.
    """
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    environment = {**os.environ, "TERM": "xterm-256color", "COLUMNS": str(COLS), "LINES": str(ROWS)}
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
    os.close(master)
    assert process.wait(timeout=30) == 0, f"{script.name} exited non-zero"

    screen = pyte.HistoryScreen(COLS, ROWS, history=4000)
    pyte.ByteStream(screen).feed(b"".join(chunks))
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
    screen = _run(NAIVE_DRIVER, lines=30, ticks=2)
    assert _debris(screen), "the naive footer must be caught, or the scoring proves nothing"


@pytest.mark.parametrize("ticks", [1, 15])
def test_no_log_line_is_swallowed_or_overwritten(ticks: int) -> None:
    """Both the dense case and the production one: sparse logs under a footer redrawing many times between them."""
    screen = _run(DRIVER, lines=30, ticks=ticks)
    assert _found_ordinals(screen) == set(range(1, 31))
    assert _debris(screen) == []


def test_the_footer_sits_below_every_log_line() -> None:
    screen = _run(DRIVER, lines=30, ticks=3)
    visible = [row.rstrip() for row in screen.display]
    footer_rows = [index for index, row in enumerate(visible) if FOOTER_MARK in row]
    log_rows = [index for index, row in enumerate(visible) if LOG_PATTERN.search(row)]
    # One footer, not several: a redraw that leaves an older copy on screen is the same defect as one that leaves it in scrollback.
    assert len(footer_rows) <= 1
    if footer_rows and log_rows:
        assert footer_rows[0] > max(log_rows)


def test_no_footer_copy_is_left_in_scrollback() -> None:
    # Scrollback is what the operator scrolls back through. A footer corpse per scroll makes it unreadable, and unlike a live-region glitch it never repaints away.
    screen = _run(DRIVER, lines=30, ticks=3)
    assert [row for row in _scrollback(screen) if FOOTER_MARK in row] == []
