"""A footer implementation that is known to be wrong, used to prove the probe discriminates.

Draws the footer straight onto the physical bottom row with no scroll region reserved. The cursor then returns into the log area and the next newline scrolls the whole screen, dragging the freshly drawn footer up with it. Every scroll therefore strands one footer copy in scrollback.

If `pty_probe.py` reports this arm clean, the probe is measuring nothing and its verdict on the real arms is worthless.
"""

import fcntl
import os
import struct
import sys
import termios
import time

LINES = int(sys.argv[1]) if len(sys.argv) > 1 else 40
DELAY_S = float(sys.argv[2]) if len(sys.argv) > 2 else 0.01
TICKS_PER_LOG = int(os.environ.get("TICKS_PER_LOG", "1"))
LONG_LINES = os.environ.get("LONG_LINES") == "1"


def terminal_size() -> tuple[int, int]:
    packed = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
    rows, cols, _, _ = struct.unpack("HHHH", packed)
    return rows, cols


def main() -> None:
    rows, _cols = terminal_size()
    out = sys.stdout
    for index in range(1, LINES + 1):
        tail = "x" * 140 if LONG_LINES else ""
        out.write(f"[ OK ] 12:00:00 LOG-{index:04d} POST /v1/messages{tail}\r\n")
        for tick in range(TICKS_PER_LOG):
            value = index * 100 + tick
            footer = f"[<-->] gpt-5 x2 {value / 100:5.2f}s ~1.2KB | claude-sonnet-4 {value / 200:5.2f}s"
            out.write(f"\x1b7\x1b[{rows};1H\x1b[2K{footer}\x1b8")
            out.flush()
            time.sleep(DELAY_S)
    out.flush()


if __name__ == "__main__":
    main()
