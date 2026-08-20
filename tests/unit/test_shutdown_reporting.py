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
from app.observability.active_requests import ActiveRequestRegistry
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


def _statuses(records: list[logging.LogRecord]) -> list[str]:
    """The `ok`/`fail`/`draining` each line carries, which decides how it is coloured and read.

    Separate from `_lines` because the two answer different questions, and because reading only the message is how the closing line's verdict went unguarded: every assertion in this file compared wording, so the whole ok-versus-fail decision could be inverted without a single test noticing.
    """
    out: list[str] = []
    for record in records:
        if record.name != LIFECYCLE_LOGGER:
            continue
        payload = record.msg
        if isinstance(payload, dict):
            out.append(str(cast(dict[str, Any], payload).get("status", "")))
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


def test_the_drain_hook_fires_once_when_the_descent_begins(captured: object) -> None:
    """What tells the footer to say `[DRIN]`.

    Once, on the first move off `RUNNING`. Later rungs escalate a drain that has already been announced, and a hook that fired again on each of them would make "we started draining" a repeating event rather than a transition.
    """
    fired: list[int] = []
    placeholder: object = object()
    server = StandaloneServer(cast(ListenerLifecycle, placeholder), on_draining=lambda: fired.append(1))

    server.receive_signal(signal.SIGINT)
    server.receive_signal(signal.SIGINT)
    server.receive_signal(signal.SIGINT)

    assert fired == [1]


def test_the_registry_reports_draining_once_told(captured: object) -> None:
    # The other half of the same wire: the CLI hands `begin_draining` to the server, and the renderer reads the flag off the registry from its own thread.
    registry = ActiveRequestRegistry()
    assert registry.draining is False
    registry.begin_draining()
    assert registry.draining is True


def test_a_clean_stop_is_one_short_line(captured: object, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        report_shutdown(ShutdownReport(stage=ShutdownStage.DRAINING))
    assert _lines(caplog.records) == ["stopped"]
    assert _statuses(caplog.records) == ["ok"]


def test_an_ordinary_drain_reports_its_counts_without_calling_itself_a_failure(
    captured: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Telling pooled clients to go, and answering a straggler with a 503, is the shutdown working.

    Both numbers were unguarded until this existed: deleting the refusal count, or folding either number back into the verdict, left every test in the suite green. That mattered most for the verdict, because the argument for keeping these two out of it is the longest one in `report_shutdown`'s docstring and it was the one thing nothing checked.

    The refusal is deliberately the mild outcome. A client that gets a 503 knows to come back; the one whose connection was closed under an in-flight request gets an RST and is not counted anywhere, so marking the 503 as a failure would rank the two exactly the wrong way round.
    """
    with caplog.at_level(logging.INFO):
        report_shutdown(
            ShutdownReport(
                stage=ShutdownStage.DRAINING,
                connections_asked_to_close=2,
                refused_requests=1,
            )
        )
    assert _lines(caplog.records) == ["stopped — 2 connections asked to close, 1 requests refused"]
    assert _statuses(caplog.records) == ["ok"]


def test_a_stop_that_cut_something_off_names_the_count(captured: object, caplog: pytest.LogCaptureFixture) -> None:
    # The difference between a restart that was safe and one that was not, which is the whole reason to read this line.
    with caplog.at_level(logging.INFO):
        report_shutdown(
            ShutdownReport(stage=ShutdownStage.FINALIZING, interrupted_connections=1, cancelled_requests=2)
        )
    assert _lines(caplog.records) == ["stopped — 1 connections interrupted, 2 requests cancelled"]
    assert _statuses(caplog.records) == ["fail"]


def test_the_benign_counts_sit_beside_an_incident_without_softening_the_verdict(
    captured: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The two kinds share one line, so the ordering and the verdict have to survive being mixed.
    with caplog.at_level(logging.INFO):
        report_shutdown(
            ShutdownReport(
                stage=ShutdownStage.FINALIZING,
                connections_asked_to_close=3,
                refused_requests=2,
                cancelled_requests=1,
            )
        )
    assert _lines(caplog.records) == [
        "stopped — 3 connections asked to close, 2 requests refused, 1 requests cancelled"
    ]
    assert _statuses(caplog.records) == ["fail"]


def test_a_severed_connection_is_the_one_drain_cost_that_counts_as_a_failure(
    captured: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The count that names a client who got nothing, sitting beside the two that do not.

    All three come out of the same rung, so the line has to rank them: closing an idle connection cost nobody anything, a 503 told its client to come back, and this one threw away a request that had already been sent and answered it with an RST. Only the last is a failure, and the verdict is the only thing that says so — the wording alone would read the same either way.
    """
    with caplog.at_level(logging.INFO):
        report_shutdown(
            ShutdownReport(
                stage=ShutdownStage.DRAINING,
                connections_asked_to_close=3,
                refused_requests=1,
                severed_connections=1,
            )
        )
    assert _lines(caplog.records) == [
        "stopped — 3 connections asked to close, 1 requests refused, "
        "1 connections severed with a request already sent"
    ]
    assert _statuses(caplog.records) == ["fail"]


def test_a_cleanup_that_overran_is_not_reported_as_clean(captured: object, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        report_shutdown(ShutdownReport(stage=ShutdownStage.FINALIZING, cleanup_timed_out=True))
    assert _lines(caplog.records) == ["stopped — cleanup exceeded its budget"]
    assert _statuses(caplog.records) == ["fail"]
