"""Drive a hand-rolled DECSTBM sticky footer under a real terminal.

The control arm for the rich.Live probe. Mechanism is the one copilot-api-js settled on (`src/lib/tui/render/region.ts`): reserve the bottom row by setting the scroll region to rows `1..rows-1`, print log lines with the cursor parked inside that region, and draw the footer on the reserved row between a DECSC/DECRC pair so the log cursor never moves.

Same payload as `driver_rich_live.py` so one probe can score both.
"""

import fcntl
import os
import struct
import sys
import termios
import time

LINES = int(sys.argv[1]) if len(sys.argv) > 1 else 40
DELAY_S = float(sys.argv[2]) if len(sys.argv) > 2 else 0.01
HOLD = len(sys.argv) > 3 and sys.argv[3] == "hold"
TICKS_PER_LOG = int(os.environ.get("TICKS_PER_LOG", "1"))
LONG_LINES = os.environ.get("LONG_LINES") == "1"


def terminal_size() -> tuple[int, int]:
    packed = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
    rows, cols, _, _ = struct.unpack("HHHH", packed)
    return rows, cols


def main() -> None:
    rows, _cols = terminal_size()
    out = sys.stdout
    # Reserve the bottom row: logs scroll only within rows 1..rows-1.
    out.write(f"\x1b[1;{rows - 1}r")
    # Park the cursor at the bottom of the scrolling region so the first newline scrolls the region rather than jumping over the footer.
    out.write(f"\x1b[{rows - 1};1H")
    out.flush()

    for index in range(1, LINES + 1):
        tail = "x" * 140 if LONG_LINES else ""
        out.write(f"[ OK ] 12:00:00 LOG-{index:04d} POST /v1/messages{tail}\r\n")
        for tick in range(TICKS_PER_LOG):
            # DECSC -> absolute move to the reserved row -> clear -> draw -> DECRC. The save/restore pair is what keeps the log cursor untouched.
            value = index * 100 + tick
            footer = f"[<-->] gpt-5 x2 {value / 100:5.2f}s ~1.2KB | claude-sonnet-4 {value / 200:5.2f}s"
            out.write(f"\x1b7\x1b[{rows};1H\x1b[2K\x1b[2m{footer}\x1b[0m\x1b8")
            out.flush()
            time.sleep(DELAY_S)

    # `hold` leaves the footer standing so a probe can score the steady state. Without it the driver exits the way a real TUI must: reserved row cleared, scroll region reset, cursor shown.
    if HOLD:
        out.write("\x1b[r")
    else:
        out.write(f"\x1b7\x1b[{rows};1H\x1b[2K\x1b8\x1b[r\x1b[?25h")
    out.flush()


if __name__ == "__main__":
    main()
