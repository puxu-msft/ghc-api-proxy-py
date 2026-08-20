"""What the process says when it is asked to stop.

The gap these guard is the one the request log had: the machinery worked and reported nothing, so a terminal went silent at exactly the moment an operator most needs to know something is happening. `ShutdownReport` even documents itself as existing "so a caller can log it rather than guess" — and every caller discarded it.
"""

import logging
import signal
from typing import Any, cast

import pytest
import structlog

from app.cli import report_shutdown
from app.lifecycle.shutdown import ShutdownStage
from app.lifecycle.standalone import (
    LIFECYCLE_LOGGER,
    ListenerLifecycle,
    ShutdownReport,
    StandaloneServer,
)
from app.observability.logging import setup_logging


@pytest.fixture
def captured() -> object:
    """The real logging configuration, so these assertions run against the wiring the CLI installs."""
    setup_logging(log_format="text", colors=False)
    yield None
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


def signal_receiver() -> StandaloneServer:
    """A real server whose adapter is never reached.

    Built through the constructor rather than around it: `receive_signal` reads only the ladder and the wake event, both of which `__init__` creates, so the adapter can be a placeholder. Poking the attributes in directly would work too and would keep working after they were renamed out from under it.
    """
    placeholder: object = object()
    return StandaloneServer(cast(ListenerLifecycle, placeholder))


def _lines(records: list[logging.LogRecord]) -> list[str]:
    """The lifecycle's own lines, with the message pulled out of the structlog event dict.

    `getMessage()` returns the whole dict stringified under `ProcessorFormatter`, because the record carries the dict and the rendering happens at the handler.
    """
    out: list[str] = []
    for record in records:
        if record.name != LIFECYCLE_LOGGER:
            continue
        payload = record.msg
        if isinstance(payload, dict):
            out.append(str(cast(dict[str, Any], payload)["event"]))
        else:
            out.append(record.getMessage())
    return out


def test_a_signal_is_reported_the_moment_it_arrives(captured: object, caplog: pytest.LogCaptureFixture) -> None:
    """The immediacy is the feature.

    Everything after the keystroke can take as long as the drain takes. A terminal that says nothing until the drain finishes leaves the operator unable to tell a graceful stop from a hung process — which is when they reach for a harder signal and lose the requests the drain was protecting.
    """
    with caplog.at_level(logging.INFO):
        signal_receiver().receive_signal(signal.SIGINT)

    assert _lines(caplog.records) == ["SIGINT received, draining, waiting for in-flight requests"]


def test_escalation_says_what_changed(captured: object, caplog: pytest.LogCaptureFixture) -> None:
    server = signal_receiver()

    with caplog.at_level(logging.INFO):
        server.receive_signal(signal.SIGINT)
        server.receive_signal(signal.SIGINT)
        # A third signal on the last rung changes nothing, so it says nothing rather than repeating itself.
        server.receive_signal(signal.SIGINT)
        server.receive_signal(signal.SIGINT)

    assert _lines(caplog.records) == [
        "SIGINT received, draining, waiting for in-flight requests",
        "SIGINT received, interrupting in-flight requests",
        "SIGINT received, finalizing, no longer waiting",
    ]


def test_a_restart_signal_starts_the_descent_without_deepening_it(captured: object, caplog: pytest.LogCaptureFixture) -> None:
    # `SIGUSR2` is the restart request: it opens a drain and never escalates one, so a second is silent.
    server = signal_receiver()

    with caplog.at_level(logging.INFO):
        server.receive_signal(signal.SIGUSR2)
        server.receive_signal(signal.SIGUSR2)

    assert _lines(caplog.records) == ["SIGUSR2 received, draining, waiting for in-flight requests"]


def test_a_clean_stop_is_one_short_line(captured: object, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        report_shutdown(ShutdownReport(stage=ShutdownStage.DRAINING))
    assert _lines(caplog.records) == ["stopped"]


def test_a_stop_that_cut_something_off_names_the_count(captured: object, caplog: pytest.LogCaptureFixture) -> None:
    # The difference between a restart that was safe and one that was not, which is the whole reason to read this line.
    with caplog.at_level(logging.INFO):
        report_shutdown(
            ShutdownReport(stage=ShutdownStage.FINALIZING, interrupted_connections=1, cancelled_requests=2)
        )
    assert _lines(caplog.records) == ["stopped — 1 connection interrupted, 2 requests cancelled"]


def test_a_cleanup_that_overran_is_not_reported_as_clean(captured: object, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        report_shutdown(ShutdownReport(stage=ShutdownStage.FINALIZING, cleanup_timed_out=True))
    assert _lines(caplog.records) == ["stopped — cleanup exceeded its budget"]
