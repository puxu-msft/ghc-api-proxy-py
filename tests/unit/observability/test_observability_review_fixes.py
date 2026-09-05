"""Reproduce the three defects an independent review found, so the fixes are not taken on trust.

Each check states what the broken behaviour was and asserts the fixed behaviour. They are written against the real production objects, not stand-ins — the first defect only exists because two real threads touch one real dict.
"""

import io
import threading
import time
from collections import deque
from typing import Any, cast

from app.observability.active_requests import (
    ActiveRequestRegistry,
    RequestObservationSnapshot,
)
from app.observability.footer import ActiveRequest, build_footer
from app.observability.terminal import TerminalCapabilities, detect_terminal
from app.observability.tui import FooterTui


class _Stream(io.TextIOWrapper):
    """A stream with a real encoding that answers `isatty` however the test needs."""

    def __init__(self, *, tty: bool, encoding: str = "utf-8") -> None:
        super().__init__(io.BytesIO(), encoding=encoding)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_the_registry_survives_being_read_while_it_is_written() -> None:
    """The footer renders on `rich.Live`'s own thread while requests mutate the registry on the event loop.

    Unlocked, building the snapshot iterates a dict another thread is resizing, which raises `RuntimeError: dictionary keys changed during iteration`, kills the refresh thread and freezes the footer at whatever it last drew.
    """
    registry = ActiveRequestRegistry()
    failures: list[BaseException] = []
    stop = threading.Event()

    def churn() -> None:
        index = 0
        while not stop.is_set():
            index += 1
            registry.add(f"req-{index}", model="m")
            registry.add_upstream_response_bytes(f"req-{index}", 10)
            if index > 40:
                registry.remove(f"req-{index - 40}")

    def render() -> None:
        try:
            while not stop.is_set():
                build_footer(registry.snapshot(), time.monotonic(), 120)
        except BaseException as error:
            failures.append(error)

    writers = [threading.Thread(target=churn) for _ in range(3)]
    readers = [threading.Thread(target=render) for _ in range(2)]
    for thread in [*writers, *readers]:
        thread.start()
    time.sleep(1.0)
    stop.set()
    for thread in [*writers, *readers]:
        thread.join(timeout=5)

    assert failures == [], f"the renderer thread died: {failures[0]!r}"


def test_live_to_completed_has_no_snapshot_gap() -> None:
    registry = ActiveRequestRegistry()
    registry.add("req-1", model="gpt-model")
    appending = threading.Event()
    release = threading.Event()
    snapshot_done = threading.Event()
    snapshots: list[object] = []
    record = cast(Any, object())

    class PausingCompleted(deque[Any]):
        def append(self, value: Any) -> None:
            appending.set()
            if not release.wait(2.0):
                raise TimeoutError("test did not release completed append")
            super().append(value)

    registry._completed = cast(Any, PausingCompleted(maxlen=256))  # pyright: ignore[reportPrivateUsage]
    writer = threading.Thread(target=registry.complete, args=("req-1", record))

    def read_snapshot() -> None:
        snapshots.append(registry.observation_snapshot())
        snapshot_done.set()

    writer.start()
    assert appending.wait(2.0), "complete() never reached its completed append"
    reader = threading.Thread(target=read_snapshot)
    reader.start()
    assert not snapshot_done.wait(0.05), "snapshot observed the gap between live pop and completed append"
    release.set()
    writer.join(timeout=2.0)
    reader.join(timeout=2.0)

    assert not writer.is_alive() and not reader.is_alive()
    snapshot = cast(Any, snapshots[0])
    assert snapshot.live == ()
    assert snapshot.completed == (record,)


def test_completed_ring_is_bounded_to_the_newest_256_records() -> None:
    registry = ActiveRequestRegistry()
    records = [object() for _ in range(300)]

    for index, record in enumerate(records):
        request_id = f"req-{index}"
        registry.add(request_id)
        registry.complete(request_id, cast(Any, record))

    snapshot = registry.observation_snapshot()
    assert snapshot.live == ()
    assert snapshot.completed == tuple(records[-256:])


def test_live_snapshot_carries_both_byte_frontiers_and_routing_facts() -> None:
    registry = ActiveRequestRegistry()
    registry.add("req-1", model="gpt-model", started_at=10.0)
    registry.set_route("req-1", route="/v1/responses", inbound_format="openai-responses")
    registry.set_provider("req-1", "ghc")
    registry.set_stream("req-1", True)
    registry.add_upstream_response_bytes("req-1", 7)
    registry.add_downstream_bytes("req-1", 0)

    (live,) = registry.observation_snapshot().live
    assert live.model == "gpt-model"
    assert live.route == "/v1/responses"
    assert live.inbound_format == "openai-responses"
    assert live.provider_name == "ghc"
    assert live.stream is True
    assert live.upstream_response_bytes == 7
    assert live.downstream_bytes == 0


def test_footer_tui_reads_the_atomic_observation_snapshot() -> None:
    class AtomicOnlyRegistry(ActiveRequestRegistry):
        observation_calls = 0

        def snapshot(self) -> list[ActiveRequest]:
            raise AssertionError("the TUI used the legacy live-only read")

        def observation_snapshot(self) -> RequestObservationSnapshot:
            self.observation_calls += 1
            if self.observation_calls > 1:
                raise AssertionError("one render combined multiple observation frames")
            return super().observation_snapshot()

    registry = AtomicOnlyRegistry()
    registry.add("req-1", model="gpt-model", started_at=time.monotonic())
    tui = FooterTui(
        registry=registry,
        capabilities=TerminalCapabilities(live=True, color=False, unicode=True),
    )

    rendered = tui._render()  # pyright: ignore[reportPrivateUsage]

    assert "gpt-model" in rendered.plain
    assert registry.observation_calls == 1


def test_a_wide_model_name_cannot_push_the_footer_onto_a_second_line() -> None:
    """The one-line invariant, measured the way a terminal measures.

    A CJK or emoji name takes two columns per character, so a 36-character name occupies 72. Slicing by `len()` let it through and the line wrapped — arriving through the one input the proxy does not control, the upstream model catalogue.
    """
    from rich.cells import cell_len

    for name in ("界" * 36, "模型" * 20, "🚀" * 30):
        active = [ActiveRequest(request_id="a", model=name, started_at=0.0, upstream_response_bytes=4096)]
        for columns in (20, 40, 80, 120):
            line = build_footer(active, 1.0, columns)
            assert cell_len(line) <= columns - 1, f"{name!r} at {columns} columns rendered {cell_len(line)} cells"


def test_an_empty_no_color_does_not_disable_colour() -> None:
    """`NO_COLOR` is honoured when present **and non-empty**.

    `NO_COLOR=` is how a caller clears an inherited value in a shell that cannot delete one, so reading it as "disable colour" does the opposite of what was asked.
    """
    assert detect_terminal(_Stream(tty=True), {"TERM": "xterm", "NO_COLOR": ""}).color is True
    assert detect_terminal(_Stream(tty=True), {"TERM": "xterm", "NO_COLOR": "1"}).color is False
