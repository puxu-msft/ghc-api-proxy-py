import logging, sys, time
from app.observability.active_requests import ActiveRequestRegistry
from app.observability.logging import setup_logging
from app.observability.terminal import TerminalCapabilities
from app.observability.tui import FooterTui

def boom():
    def inner():
        raise ValueError("upstream exploded")
    inner()

def main() -> None:
    setup_logging(log_format="text", colors=True)
    registry = ActiveRequestRegistry()
    logger = logging.getLogger("driver")
    tui = FooterTui(registry=registry, capabilities=TerminalCapabilities(live=True, color=True, unicode=True), refresh_per_second=20)
    with tui.activate():
        for index in (1, 2, 3):
            rid = f"req-{index}"
            registry.add(rid, model="gpt-5")
            logger.info("LOG-%04d POST /v1/messages", index)
            if index == 2:
                try:
                    boom()
                except ValueError as error:
                    logger.error("accepted connection routing crashed", exc_info=error)
            registry.add_bytes(rid, 1024)
            time.sleep(0.15)
            registry.remove(rid)
        time.sleep(0.2)

main()
