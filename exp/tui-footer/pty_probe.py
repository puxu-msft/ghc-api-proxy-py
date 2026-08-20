"""Score a footer driver by what actually lands on the screen.

Runs a driver inside a real pty at a fixed window size, interprets its output with pyte, and answers the three questions that decide whether a mechanism can carry a pinned footer above a native-scrolling log.

1. Continuity — every emitted log line is findable in scrollback plus the current screen. A missing ordinal means the mechanism ate a line.
2. Pinning — the footer sits on the bottom row when the run ends.
3. Scrollback hygiene — the footer does not accumulate copies in history. A footer redrawn without a reserved region leaves one corpse per scroll, which is the failure that makes scrollback unreadable.

`--dump` prints the grid with a column ruler instead of scoring, for looking at a layout before deciding what to assert about it.
"""

import argparse
import fcntl
import os
import pty
import re
import select
import struct
import sys
import termios

import pyte

FOOTER_MARK = "[<-->]"
LOG_PATTERN = re.compile(r"LOG-(\d{4})")
# The footer is the only thing that prints an elapsed field, so this pattern appearing anywhere else is footer debris left behind by a redraw that outran its anchor. Chosen over comparing whole lines against the emitted text: rich word-wraps and a raw write breaks at the column, so no single line-reconstruction rule fits both, and the mismatch reads as corruption that is not there. This one targets the failure mechanism instead of the layout.
FOOTER_DEBRIS = re.compile(r"\d+\.\d\ds")


def unwrap(rows: list[str], cols: int) -> list[str]:
    """Rejoin rows the terminal wrapped, so a log ordinal split across two rows is still findable.

    A row whose final column holds a character is a line the terminal broke, not a line the driver ended.
    """
    logical: list[str] = []
    buffer = ""
    for row in rows:
        padded = row.ljust(cols)
        buffer += padded.rstrip() if padded[cols - 1] == " " else padded
        if padded[cols - 1] == " ":
            logical.append(buffer)
            buffer = ""
    if buffer:
        logical.append(buffer)
    return logical


def run_driver(command: list[str], rows: int, cols: int) -> bytes:
    """Run `command` attached to a pty of the given size and return everything it wrote."""
    pid, master = pty.fork()
    if pid == 0:
        # Child: the slave side is already stdin/stdout/stderr.
        packed = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(sys.stdout.fileno(), termios.TIOCSWINSZ, packed)
        os.environ["TERM"] = "xterm-256color"
        os.environ["COLUMNS"] = str(cols)
        os.environ["LINES"] = str(rows)
        os.execvp(command[0], command)

    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    chunks: list[bytes] = []
    while True:
        ready, _, _ = select.select([master], [], [], 20.0)
        if not ready:
            break
        try:
            data = os.read(master, 65536)
        except OSError:
            break
        if not data:
            break
        chunks.append(data)
    os.close(master)
    os.waitpid(pid, 0)
    return b"".join(chunks)


def replay(output: bytes, rows: int, cols: int) -> pyte.HistoryScreen:
    screen = pyte.HistoryScreen(cols, rows, history=4000)
    stream = pyte.ByteStream(screen)
    stream.feed(output)
    return screen


def history_lines(screen: pyte.HistoryScreen) -> list[str]:
    """Scrollback rows as plain strings; history rows are dict-like, not str.

    Trailing spaces are kept: whether the last column is occupied is what tells a wrapped line from an ended one.
    """
    lines: list[str] = []
    for row in screen.history.top:
        lines.append("".join(row[column].data for column in sorted(row)))
    return lines


def score(screen: pyte.HistoryScreen, expected: int, cols: int) -> dict[str, object]:
    scrollback = history_lines(screen)
    visible = list(screen.display)
    logical = unwrap([*scrollback, *visible], cols)

    found = {int(match) for match in LOG_PATTERN.findall("\n".join(logical))}
    missing = sorted(set(range(1, expected + 1)) - found)

    # The discriminating check. A footer that scrolled out of place leaves its tail welded onto whatever content sits there, which keeps the log ordinal intact and the `[<-->]` prefix overwritten — so neither a missing-ordinal count nor a marker search can see it. An elapsed field outside the footer's own row can.
    debris = [line.rstrip() for line in [*scrollback, *[row for index, row in enumerate(visible) if FOOTER_MARK not in row]] if FOOTER_DEBRIS.search(line)]

    stranded = [line for line in scrollback if FOOTER_MARK in line]

    # "Pinned" is not "on the physical bottom row": rich parks the cursor on a blank line under its live region, so the honest invariant is that the footer is the last thing with content and no log line sits below it.
    stripped = [line.rstrip() for line in visible]
    filled = [index for index, line in enumerate(stripped) if line]
    last_filled = filled[-1] if filled else -1
    footer_rows = [index for index, line in enumerate(stripped) if FOOTER_MARK in line]
    log_rows = [index for index, line in enumerate(stripped) if LOG_PATTERN.search(line)]
    footer_row = footer_rows[-1] if footer_rows else -1
    return {
        "missing_log_lines": missing,
        "footer_debris_rows": len(debris),
        "debris_sample": debris[0] if debris else "",
        "footer_below_all_logs": footer_row != -1 and (not log_rows or footer_row > max(log_rows)),
        "footer_is_last_content": footer_row != -1 and footer_row == last_filled,
        "footer_row": footer_row,
        "footer_copies_on_screen": len(footer_rows),
        "footer_copies_in_scrollback": len(stranded),
    }


def dump(screen: pyte.HistoryScreen, cols: int, *, with_history: bool) -> None:
    ruler = "".join(str(index % 10) for index in range(cols))
    if with_history:
        for index, line in enumerate(history_lines(screen)):
            print(f"hist{index:3d} |{line}")
    print(f"     +{ruler}")
    for index, line in enumerate(screen.display):
        print(f"row{index:3d}  |{line.rstrip()}")
    print(f"     +{ruler}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("driver", help="path to the driver script")
    parser.add_argument("--lines", type=int, default=40)
    parser.add_argument("--delay", type=float, default=0.01)
    parser.add_argument("--rows", type=int, default=24)
    parser.add_argument("--cols", type=int, default=80)
    parser.add_argument("--dump", action="store_true", help="print the grid instead of scoring")
    parser.add_argument("--history", action="store_true", help="include scrollback in the dump")
    parser.add_argument("--repeat", type=int, default=1, help="run N times; timing bugs are not single-shot")
    parser.add_argument("--hold", action="store_true", help="tell the driver to leave its last frame standing")
    args = parser.parse_args()

    command = [sys.executable, args.driver, str(args.lines), str(args.delay)]
    if args.hold:
        command.append("hold")
    failures = 0
    for attempt in range(1, args.repeat + 1):
        output = run_driver(command, args.rows, args.cols)
        screen = replay(output, args.rows, args.cols)
        if args.dump:
            dump(screen, args.cols, with_history=args.history)
            return 0
        result = score(screen, args.lines, args.cols)
        ok = (
            not result["missing_log_lines"]
            and result["footer_debris_rows"] == 0
            and result["footer_below_all_logs"]
            and result["footer_copies_on_screen"] == 1
            and result["footer_copies_in_scrollback"] == 0
        )
        failures += 0 if ok else 1
        print(f"run {attempt:2d}  {'PASS' if ok else 'FAIL'}  {result}")
    print(f"\n{args.repeat - failures}/{args.repeat} runs clean")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
