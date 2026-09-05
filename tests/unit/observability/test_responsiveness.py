import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO, cast

import anyio
import pytest
from prometheus_client import CollectorRegistry, generate_latest

import app.observability.responsiveness as responsiveness_module
from app.observability.metrics import ResponsivenessMetrics
from app.observability.responsiveness import (
    HEARTBEAT_SECONDS,
    ObservedTerminal,
    monitor_event_loop,
    observe_render,
    observe_tui,
)


@dataclass
class _Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


def _sample(
    registry: CollectorRegistry,
    name: str,
    labels: dict[str, str] | None = None,
) -> float:
    value = registry.get_sample_value(name, labels)
    assert value is not None
    return value


def test_measure_accumulates_histogram_maximum_and_failures_from_a_fake_clock() -> None:
    registry = CollectorRegistry()
    clock = _Clock(10.0)
    metrics = ResponsivenessMetrics(registry, clock)

    with metrics.loop_lag.measure():
        clock.now = 10.125

    clock.now = 20.0
    first_error = RuntimeError("first")
    with pytest.raises(RuntimeError) as first_caught, metrics.loop_lag.measure():
        clock.now = 20.75
        raise first_error
    assert first_caught.value is first_error

    clock.now = 30.0
    second_error = ValueError("second")
    with pytest.raises(ValueError) as second_caught, metrics.loop_lag.measure():
        clock.now = 30.25
        raise second_error
    assert second_caught.value is second_error

    assert _sample(registry, "ghc_proxy_event_loop_lag_seconds_count") == 3
    assert _sample(registry, "ghc_proxy_event_loop_lag_seconds_sum") == pytest.approx(1.125)
    assert _sample(registry, "ghc_proxy_event_loop_lag_max_seconds") == pytest.approx(0.75)
    assert _sample(registry, "ghc_proxy_event_loop_lag_failures_total") == 2


def test_tui_lifecycle_resets_success_baseline_without_resetting_histograms() -> None:
    registry = CollectorRegistry()
    clock = _Clock()
    metrics = ResponsivenessMetrics(registry, clock)
    owner = object()

    assert _sample(registry, "ghc_proxy_tui_active") == 0
    assert _sample(registry, "ghc_proxy_tui_last_render_age_seconds") == 0

    with observe_tui(metrics, owner):
        assert _sample(registry, "ghc_proxy_tui_active") == 1
        assert math.isnan(_sample(registry, "ghc_proxy_tui_last_render_age_seconds"))

        clock.now = 1.0
        render_error = RuntimeError("render failed")
        with pytest.raises(RuntimeError) as caught, observe_render(metrics, owner):
            clock.now = 2.0
            raise render_error
        assert caught.value is render_error
        assert math.isnan(_sample(registry, "ghc_proxy_tui_last_render_age_seconds"))

        clock.now = 3.0
        with observe_render(metrics, owner):
            clock.now = 3.25
        clock.now = 4.0
        assert _sample(registry, "ghc_proxy_tui_last_render_age_seconds") == pytest.approx(0.75)

    assert _sample(registry, "ghc_proxy_tui_active") == 0
    assert _sample(registry, "ghc_proxy_tui_last_render_age_seconds") == 0
    assert _sample(registry, "ghc_proxy_tui_render_duration_seconds_count") == 2
    assert _sample(registry, "ghc_proxy_tui_render_duration_failures_total") == 1
    assert _sample(registry, "ghc_proxy_tui_render_interval_seconds_count") == 1

    clock.now = 10.0
    with observe_tui(metrics, owner):
        assert math.isnan(_sample(registry, "ghc_proxy_tui_last_render_age_seconds"))
        assert _sample(registry, "ghc_proxy_tui_render_duration_seconds_count") == 2
        with observe_render(metrics, owner):
            clock.now = 10.1
        assert _sample(registry, "ghc_proxy_tui_render_interval_seconds_count") == 1

    assert _sample(registry, "ghc_proxy_tui_last_render_age_seconds") == 0
    assert _sample(registry, "ghc_proxy_tui_render_duration_seconds_count") == 3


def test_lifecycle_and_io_state_are_isolated_by_owner_without_owner_labels() -> None:
    registry = CollectorRegistry()
    clock = _Clock(10.0)
    metrics = ResponsivenessMetrics(registry, clock)
    first_owner = object()
    second_owner = object()
    first_write = object()
    second_write = object()
    first_flush = object()

    metrics.activate(first_owner)
    metrics.activate(second_owner)
    metrics.io_started(first_owner, "write", first_write, 10.0)
    metrics.io_started(second_owner, "write", second_write, 12.0)
    metrics.io_started(first_owner, "flush", first_flush, 14.0)
    clock.now = 17.0

    assert _sample(registry, "ghc_proxy_tui_active") == 2
    assert _sample(registry, "ghc_proxy_tui_terminal_io_in_progress", {"operation": "write"}) == 2
    assert _sample(registry, "ghc_proxy_tui_terminal_io_in_progress_seconds", {"operation": "write"}) == 7
    assert _sample(registry, "ghc_proxy_tui_terminal_io_in_progress", {"operation": "flush"}) == 1
    assert _sample(registry, "ghc_proxy_tui_terminal_io_in_progress_seconds", {"operation": "flush"}) == 3
    payload = generate_latest(registry)
    assert b"ghc_proxy_tui_active{" not in payload
    assert b"owner=" not in payload
    assert b"instance=" not in payload

    metrics.deactivate(first_owner)

    assert _sample(registry, "ghc_proxy_tui_active") == 1
    assert _sample(registry, "ghc_proxy_tui_terminal_io_in_progress", {"operation": "write"}) == 1
    assert _sample(registry, "ghc_proxy_tui_terminal_io_in_progress_seconds", {"operation": "write"}) == 5
    assert _sample(registry, "ghc_proxy_tui_terminal_io_in_progress", {"operation": "flush"}) == 0
    assert _sample(registry, "ghc_proxy_tui_terminal_io_in_progress_seconds", {"operation": "flush"}) == 0

    metrics.io_finished("write", second_write)
    assert _sample(registry, "ghc_proxy_tui_terminal_io_in_progress", {"operation": "write"}) == 0
    assert _sample(registry, "ghc_proxy_tui_terminal_io_in_progress_seconds", {"operation": "write"}) == 0
    metrics.deactivate(second_owner)


class _BlockingStream:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.closed = False

    def write(self, text: str) -> int:
        self.entered.set()
        if not self.release.wait(2):
            raise TimeoutError("write was not released")
        return len(text)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _OutcomeStream:
    def __init__(self) -> None:
        self.closed = False
        self.write_error: BaseException | None = None
        self.flush_error: BaseException | None = None
        self.flush_result = object()

    def write(self, _text: str) -> int:
        if self.write_error is not None:
            raise self.write_error
        return 17

    def flush(self) -> object:
        if self.flush_error is not None:
            raise self.flush_error
        return self.flush_result

    def close(self) -> None:
        self.closed = True


def test_scrape_completes_while_the_underlying_terminal_write_is_blocked() -> None:
    registry = CollectorRegistry()
    clock = _Clock(10.0)
    metrics = ResponsivenessMetrics(registry, clock)
    owner = object()
    stream = _BlockingStream()
    terminal = ObservedTerminal(cast(TextIO, stream), metrics, owner)
    writer_errors: list[BaseException] = []
    payloads: list[bytes] = []
    scraped = threading.Event()

    def write() -> None:
        try:
            terminal.write("blocked")
        except BaseException as error:
            writer_errors.append(error)

    def scrape() -> None:
        payloads.append(generate_latest(registry))
        scraped.set()

    with observe_tui(metrics, owner):
        writer = threading.Thread(target=write)
        writer.start()
        assert stream.entered.wait(1)
        clock.now = 13.0
        scraper = threading.Thread(target=scrape)
        scraper.start()
        try:
            assert scraped.wait(1), "metrics scrape waited for the terminal output call"
        finally:
            stream.release.set()
        writer.join(1)
        scraper.join(1)

    assert not writer.is_alive()
    assert not scraper.is_alive()
    assert writer_errors == []
    assert len(payloads) == 1
    assert b'ghc_proxy_tui_terminal_io_in_progress{operation="write"} 1.0' in payloads[0]
    assert b'ghc_proxy_tui_terminal_io_in_progress_seconds{operation="write"} 3.0' in payloads[0]
    assert stream.closed is False


def test_observed_terminal_preserves_returns_exceptions_and_stream_ownership() -> None:
    registry = CollectorRegistry()
    clock = _Clock()
    metrics = ResponsivenessMetrics(registry, clock)
    owner = object()
    stream = _OutcomeStream()
    terminal = ObservedTerminal(cast(TextIO, stream), metrics, owner)
    flush = cast(Callable[[], object], terminal.flush)

    with observe_tui(metrics, owner):
        assert terminal.write("ok") == 17
        assert flush() is stream.flush_result

        write_error = RuntimeError("write")
        stream.write_error = write_error
        with pytest.raises(RuntimeError) as write_caught:
            terminal.write("fail")
        assert write_caught.value is write_error

        flush_error = ValueError("flush")
        stream.flush_error = flush_error
        with pytest.raises(ValueError) as flush_caught:
            terminal.flush()
        assert flush_caught.value is flush_error

    assert _sample(registry, "ghc_proxy_tui_terminal_io_duration_seconds_count", {"operation": "write"}) == 2
    assert _sample(registry, "ghc_proxy_tui_terminal_io_duration_failures_total", {"operation": "write"}) == 1
    assert _sample(registry, "ghc_proxy_tui_terminal_io_duration_seconds_count", {"operation": "flush"}) == 2
    assert _sample(registry, "ghc_proxy_tui_terminal_io_duration_failures_total", {"operation": "flush"}) == 1
    assert stream.closed is False


@pytest.mark.asyncio
async def test_heartbeat_records_one_late_tick_without_catching_up_and_clears_active_on_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = CollectorRegistry()
    clock = _Clock(10.0)
    metrics = ResponsivenessMetrics(registry, clock)
    second_sleep_entered = anyio.Event()
    never_release = anyio.Event()
    sleeps: list[float] = []

    async def controlled_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 1:
            clock.now = 12.0
            return
        second_sleep_entered.set()
        await never_release.wait()

    monkeypatch.setattr(responsiveness_module.anyio, "sleep", controlled_sleep)

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(monitor_event_loop, metrics)
        await second_sleep_entered.wait()
        assert _sample(registry, "ghc_proxy_event_loop_monitor_active") == 1
        assert sleeps == [HEARTBEAT_SECONDS, HEARTBEAT_SECONDS]
        assert _sample(registry, "ghc_proxy_event_loop_lag_seconds_count") == 1
        assert _sample(registry, "ghc_proxy_event_loop_lag_seconds_sum") == pytest.approx(1.5)
        tasks.cancel_scope.cancel()

    assert _sample(registry, "ghc_proxy_event_loop_monitor_active") == 0
