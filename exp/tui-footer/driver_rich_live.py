"""Drive a `rich.Live` pinned footer under a real terminal.

Idiomatic usage: a one-line renderable held by `Live`, with the log stream printed through `live.console.print` so rich itself decides how to keep the footer below the scrolling output.

The payload is zero-padded (`LOG-0001`) so a "line 9 is missing" check cannot be satisfied by `LOG-0090`. Every line also carries its own ordinal in the text, so a swallowed line is detectable from the grid alone.
"""

import os
import sys
import time

from rich.console import Console
from rich.live import Live
from rich.text import Text

LINES = int(sys.argv[1]) if len(sys.argv) > 1 else 40
DELAY_S = float(sys.argv[2]) if len(sys.argv) > 2 else 0.01
HOLD = len(sys.argv) > 3 and sys.argv[3] == "hold"
# Stress knobs. Production is sparse logs under a footer ticking at ~10Hz, so the interesting ratio is many redraws per printed line, not one.
TICKS_PER_LOG = int(os.environ.get("TICKS_PER_LOG", "1"))
LONG_LINES = os.environ.get("LONG_LINES") == "1"


def footer(tick: int, width: int) -> Text:
    """One physical line, same shape as the copilot-api-js live footer.

    Truncated to `width - 1` because a footer that wraps stops being a footer: the probe catches the second row as debris, and at 40 columns the untruncated form fails every run. The -1 avoids the last-column auto-wrap some terminals do.
    """
    body = f"[<-->] gpt-5 x2 {tick / 100:5.2f}s ~1.2KB | claude-sonnet-4 {tick / 200:5.2f}s"
    return Text(body[: max(0, width - 1)], style="dim", no_wrap=True, overflow="crop")


def main() -> None:
    console = Console(file=sys.stdout, force_terminal=True, highlight=False, soft_wrap=False)
    # `transient` is rich's own knob for the same choice the DECSTBM arm makes explicitly: hold the last frame for a probe to score, or erase it on the way out the way a real TUI must.
    with Live(footer(0, console.width), console=console, refresh_per_second=20, transient=not HOLD) as live:
        for index in range(1, LINES + 1):
            tail = "x" * 140 if LONG_LINES else ""
            live.console.print(f"[ OK ] 12:00:00 LOG-{index:04d} POST /v1/messages{tail}")
            for tick in range(TICKS_PER_LOG):
                live.update(footer(index * 100 + tick, console.width))
                time.sleep(DELAY_S)
    # Leave the terminal exactly as found: no scroll region, cursor visible.
    sys.stdout.write("\x1b[r\x1b[?25h")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
