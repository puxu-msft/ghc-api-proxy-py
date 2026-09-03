"""A footer drawn the wrong way, so the screen test can prove its scoring works.

The same footer marker and model sentinel as `_footer_driver.py`, but painted straight onto the bottom row with no reserved region and no accounting for the rows it occupies. The model sentinel is repeated at the tail so it survives the following log line overwriting the prefix and gives the scoring oracle a stable piece of the welded-on debris. The cursor returns into the log area and the next line scrolls the whole screen, dragging the drawn footer up with it.

If the screen test reports this as clean, it is measuring nothing and its verdict on the real footer is worthless.
"""

import sys
import time

LINES = int(sys.argv[1]) if len(sys.argv) > 1 else 30
TICKS_PER_LOG = int(sys.argv[2]) if len(sys.argv) > 2 else 2


def main() -> None:
    out = sys.stderr
    rows = int(sys.argv[3]) if len(sys.argv) > 3 else 24
    for index in range(1, LINES + 1):
        out.write(f"[ OK ] 12:00:00 LOG-{index:04d} POST /v1/messages\r\n")
        for tick in range(TICKS_PER_LOG):
            elapsed = (index * 10 + tick) / 10
            footer = f"[<-->] FOOTER-MODEL x2 {elapsed:5.2f}s ↓1.2KiB | claude-sonnet-4 {elapsed / 2:5.2f}s | FOOTER-MODEL"
            out.write(f"\x1b7\x1b[{rows};1H\x1b[2K{footer}\x1b8")
            out.flush()
            time.sleep(0.01)


if __name__ == "__main__":
    main()
