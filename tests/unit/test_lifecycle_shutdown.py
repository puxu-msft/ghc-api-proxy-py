"""The shutdown ladder and the listener a directly-run process binds.

The ladder distinguishes "stop accepting" from "interrupt what is running" from "stop waiting".
It also keeps a smooth restart from being mistaken for the second of those.
"""

import signal
import socket

import pytest

from app.lifecycle.listener import LISTENER_NAME, ListenerBindError, bind_listener
from app.lifecycle.shutdown import ShutdownLadder, ShutdownStage


def ladder_after(*signals: signal.Signals) -> ShutdownStage:
    ladder = ShutdownLadder()
    for sig in signals:
        ladder.receive(sig)
    return ladder.stage


def test_a_fresh_ladder_is_not_stopping() -> None:
    ladder = ShutdownLadder()
    assert ladder.stage is ShutdownStage.RUNNING
    assert ladder.stopping is False


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGUSR2])
def test_any_of_the_three_signals_starts_the_drain(sig: signal.Signals) -> None:
    # The spec gives all three the same first rung: stop accepting, wait normally.
    assert ladder_after(sig) is ShutdownStage.DRAINING


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_a_second_stop_signal_interrupts_requests(sig: signal.Signals) -> None:
    assert ladder_after(sig, sig) is ShutdownStage.INTERRUPTING


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_a_third_stop_signal_stops_waiting(sig: signal.Signals) -> None:
    assert ladder_after(sig, sig, sig) is ShutdownStage.FINALIZING


def test_the_two_stop_signals_escalate_the_same_ladder() -> None:
    # Mixing them must not restart the count.
    # Ctrl-C followed by a TERM is one escalation, not two fresh descents.
    assert ladder_after(signal.SIGINT, signal.SIGTERM) is ShutdownStage.INTERRUPTING


def test_a_restart_signal_does_not_interrupt_a_drain() -> None:
    # The spec: SIGUSR2 信号不会中断优雅关闭.
    assert ladder_after(signal.SIGTERM, signal.SIGUSR2) is ShutdownStage.DRAINING


def test_repeated_restart_signals_never_escalate() -> None:
    assert ladder_after(signal.SIGUSR2, signal.SIGUSR2, signal.SIGUSR2) is ShutdownStage.DRAINING


def test_a_restart_signal_after_interruption_does_not_walk_back() -> None:
    # It neither deepens the shutdown nor undoes it.
    assert ladder_after(signal.SIGTERM, signal.SIGTERM, signal.SIGUSR2) is (
        ShutdownStage.INTERRUPTING
    )


def test_the_ladder_stops_at_the_last_rung() -> None:
    # A fourth signal must not run off the end; the operator's escape hatch is SIGKILL.
    stage = ladder_after(*([signal.SIGINT] * 6))
    assert stage is ShutdownStage.FINALIZING


def test_an_unrelated_signal_is_not_a_shutdown() -> None:
    assert ladder_after(signal.SIGHUP) is ShutdownStage.RUNNING


def test_receive_reports_the_rung_it_moved_to() -> None:
    ladder = ShutdownLadder()
    assert ladder.receive(signal.SIGTERM) is ShutdownStage.DRAINING
    assert ladder.receive(signal.SIGTERM) is ShutdownStage.INTERRUPTING


def test_a_bound_listener_is_listening_and_reuses_the_port() -> None:
    listeners = bind_listener("127.0.0.1", 0)
    try:
        (identity,) = listeners.identities()
        assert identity.name == LISTENER_NAME
        assert identity.address[0] == "127.0.0.1"
        assert identity.address[1] > 0
        duplicate = listeners.duplicate_for_accept()[LISTENER_NAME]
        try:
            assert duplicate.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
            assert duplicate.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT) == 1
        finally:
            duplicate.close()
    finally:
        listeners.close()


def test_a_second_process_can_bind_the_same_port() -> None:
    """The point of SO_REUSEPORT: the replacement binds while the old one still listens."""
    first = bind_listener("127.0.0.1", 0)
    try:
        port = first.identities()[0].address[1]
        second = bind_listener("127.0.0.1", port)
        second.close()
    finally:
        first.close()


def test_binding_without_reuse_port_blocks_a_smooth_restart() -> None:
    # The negative control for the test above: without the option the second bind is refused.
    first = bind_listener("127.0.0.1", 0, reuse_port=False)
    try:
        port = first.identities()[0].address[1]
        with pytest.raises(ListenerBindError):
            bind_listener("127.0.0.1", port, reuse_port=False)
    finally:
        first.close()


def test_an_unresolvable_host_is_reported_as_a_bind_error() -> None:
    with pytest.raises(ListenerBindError):
        bind_listener("no-such-host.invalid", 0)
