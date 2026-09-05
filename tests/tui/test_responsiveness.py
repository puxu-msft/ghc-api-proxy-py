import io
import logging
import sys
import threading

import pyte
import pytest
from prometheus_client import CollectorRegistry

from app.observability.active_requests import ActiveRequestRegistry
from app.observability.metrics import ResponsivenessMetrics
from app.observability.terminal import TerminalCapabilities
from app.observability.tui import FooterTui


class CaptureTerminal(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.changed = threading.Event()

    def isatty(self) -> bool:
        return True

    def write(self, text: str) -> int:
        result = super().write(text)
        if "MODEL-AFTER" in text:
            self.changed.set()
        return result


def test_footer_refreshes_without_log_and_restores_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = CaptureTerminal()
    monkeypatch.setattr(sys, "stderr", terminal)
    monkeypatch.setenv("TERM", "xterm-256color")
    original_stdout, original_stderr = sys.stdout, sys.stderr
    handlers = list(logging.getLogger().handlers)
    prometheus = CollectorRegistry()
    metrics = ResponsivenessMetrics(prometheus)
    registry = ActiveRequestRegistry()
    registry.add("request", model="MODEL-BEFORE")
    tui = FooterTui(registry, TerminalCapabilities(True, False, False), metrics=metrics)

    with tui.activate():
        assert prometheus.get_sample_value("ghc_proxy_tui_active") == 1
        registry.set_model("request", "MODEL-AFTER")
        # No logging or manual refresh: only Rich's existing refresh thread can emit the change.
        assert terminal.changed.wait(3), "automatic footer refresh never wrote the new model"
        screen = pyte.Screen(80, 24)
        pyte.Stream(screen).feed(terminal.getvalue())
        assert "MODEL-AFTER" in "\n".join(screen.display)
        assert (prometheus.get_sample_value("ghc_proxy_tui_render_interval_seconds_count") or 0) > 0

    assert sys.stdout is original_stdout and sys.stderr is original_stderr
    assert logging.getLogger().handlers == handlers
    assert not terminal.closed
    assert prometheus.get_sample_value("ghc_proxy_tui_active") == 0
    assert prometheus.get_sample_value("ghc_proxy_tui_last_render_age_seconds") == 0
    assert prometheus.get_sample_value("ghc_proxy_tui_terminal_io_duration_seconds_count", {"operation": "write"})
    assert prometheus.get_sample_value("ghc_proxy_tui_terminal_io_duration_seconds_count", {"operation": "flush"})


def test_nested_live_does_not_bypass_inner_terminal_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = CaptureTerminal()
    monkeypatch.setattr(sys, "stderr", terminal)
    monkeypatch.setenv("TERM", "xterm-256color")
    original_stdout, original_stderr = sys.stdout, sys.stderr
    outer_metrics = ResponsivenessMetrics(CollectorRegistry())
    inner_registry = CollectorRegistry()
    inner_metrics = ResponsivenessMetrics(inner_registry)
    outer = FooterTui(ActiveRequestRegistry(), TerminalCapabilities(True, False, False), metrics=outer_metrics)
    inner = FooterTui(ActiveRequestRegistry(), TerminalCapabilities(True, False, False), metrics=inner_metrics)
    with outer.activate():
        outer_stdout, outer_stderr = sys.stdout, sys.stderr
        with inner.activate():
            logging.getLogger("test").warning("nested-terminal-message")
            assert inner_registry.get_sample_value("ghc_proxy_tui_terminal_io_duration_seconds_count", {"operation": "write"})
            assert inner_registry.get_sample_value("ghc_proxy_tui_terminal_io_duration_seconds_count", {"operation": "flush"})
        assert sys.stdout is outer_stdout and sys.stderr is outer_stderr
    assert sys.stdout is original_stdout and sys.stderr is original_stderr
    assert "nested-terminal-message" in terminal.getvalue()
    assert not terminal.closed


def test_failed_initial_render_does_not_leave_active_state(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = CaptureTerminal()
    monkeypatch.setattr(sys, "stderr", terminal)
    original_stdout, original_stderr = sys.stdout, sys.stderr
    prometheus = CollectorRegistry()
    metrics = ResponsivenessMetrics(prometheus)
    error = RuntimeError("render failed")

    def fail(self: FooterTui) -> None:
        raise error

    monkeypatch.setattr(FooterTui, "_render_content", fail)
    tui = FooterTui(ActiveRequestRegistry(), TerminalCapabilities(True, False, False), metrics=metrics)
    with pytest.raises(RuntimeError) as caught, tui.activate():
        pytest.fail("initial render should fail")
    assert caught.value is error
    assert prometheus.get_sample_value("ghc_proxy_tui_active") == 0
    assert prometheus.get_sample_value("ghc_proxy_tui_render_duration_failures_total") == 1
    assert sys.stdout is original_stdout and sys.stderr is original_stderr
    assert not terminal.closed
