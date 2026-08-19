"""Run the real footer inside a pty so a screen test can score what it draws.

Not a re-implementation: this builds the production `ActiveRequestRegistry` and `FooterTui` and logs through the standard `logging` root, which is the same path a served request takes. A driver that mimicked the rendering instead would prove only that the mimicry is self-consistent.

Named with a leading underscore so pytest does not collect it — it is a subprocess entry point, not a test.
"""

import logging
import sys
import time

from app.observability.active_requests import ActiveRequestRegistry
from app.observability.terminal import TerminalCapabilities
from app.observability.tui import FooterTui

LINES = int(sys.argv[1]) if len(sys.argv) > 1 else 30
TICKS_PER_LOG = int(sys.argv[2]) if len(sys.argv) > 2 else 1


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    registry = ActiveRequestRegistry()
    logger = logging.getLogger("driver")

    # Forced on rather than probed: the pty makes stderr a real terminal, but the probe also reads `CI`, which is set in exactly the environment this test most needs to run in.
    capabilities = TerminalCapabilities(live=True, color=True, unicode=True)
    tui = FooterTui(registry=registry, capabilities=capabilities, refresh_per_second=20)

    with tui.activate():
        for index in range(1, LINES + 1):
            request_id = f"req-{index}"
            registry.add(request_id, model="gpt-5")
            logger.info("[ OK ] 12:00:00 LOG-%04d POST /v1/messages", index)
            for _ in range(TICKS_PER_LOG):
                registry.add_bytes(request_id, 1024)
                time.sleep(0.01)
            registry.remove(request_id)


if __name__ == "__main__":
    main()
