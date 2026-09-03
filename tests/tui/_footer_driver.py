"""Run the real footer inside a pty so a screen test can score what it draws.

Not a re-implementation: this builds the production `ActiveRequestRegistry` and `FooterTui` and logs through the standard `logging` root, which is the same path a served request takes. A driver that mimicked the rendering instead would prove only that the mimicry is self-consistent.

Named with a leading underscore so pytest does not collect it — it is a subprocess entry point, not a test.
"""

import logging
import os
import sys
import time

from app.observability.active_requests import ActiveRequestRegistry
from app.observability.request_log import RequestLine, format_completion_line
from app.observability.terminal import TerminalCapabilities
from app.observability.tui import FooterTui
from app.pipeline.delivery.assembling import ReplyDialect
from app.pipeline.response_observation import ResponsesObserver

LINES = int(sys.argv[1]) if len(sys.argv) > 1 else 30
TICKS_PER_LOG = int(sys.argv[2]) if len(sys.argv) > 2 else 1


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    registry = ActiveRequestRegistry()
    logger = logging.getLogger("driver")

    # Forced on rather than probed: the pty makes stderr a real terminal, but the probe also reads `CI`, which is set in exactly the environment this test most needs to run in.
    capabilities = TerminalCapabilities(live=True, color=True, unicode=True)
    tui = FooterTui(registry=registry, capabilities=capabilities, refresh_per_second=20)

    observer = ResponsesObserver()
    observer.observe_response({
        "status": "completed",
        "model": "gpt-5.6-codex-super-long-provider-revision",
        "output": [
            {
                "type": "custom_tool_call",
                "name": "provider)\x1b[31m,\n\\" + "x" * 160,
                "status": "completed",
            }
        ],
        "usage": {
            "input_tokens": 71_900,
            "input_tokens_details": {
                "cached_tokens": 0,
                "cache_write_tokens": 71_897,
            },
            "output_tokens": 765,
        },
    })
    response_observation = observer.snapshot()

    with tui.activate():
        for index in range(1, LINES + 1):
            request_id = f"req-{index}"
            registry.add(request_id, model="FOOTER-MODEL")
            completion = format_completion_line(
                RequestLine(
                    method="POST",
                    path="/v1/responses",
                    inbound_format="openai-responses",
                    client_protocol="H1",
                    upstream_protocol="H2",
                    model="gpt-5.6-codex-super-long-provider-revision",
                    status_code=200,
                    duration_s=14.5,
                    bytes_in=300_100,
                    bytes_out=107_300,
                    dialect=ReplyDialect.RESPONSES,
                ),
                status="ok",
                color=True,
                response_observation=response_observation,
            )
            logger.info("[ OK ] 12:00:00 LOG-%04d %s", index, completion)
            for _ in range(TICKS_PER_LOG):
                registry.add_upstream_response_bytes(request_id, 1024)
                time.sleep(0.01)
            registry.remove(request_id)
        if os.environ.get("HOLD_LIVE") == "1":
            registry.add("held-request", model="FOOTER-MODEL")
            logger.info("DRIVER-READY")
            sys.stdin.read(1)
            registry.remove("held-request")


if __name__ == "__main__":
    main()
