"""Reproduce the three defects an independent review found, so the fixes are not taken on trust.

Each check states what the broken behaviour was and asserts the fixed behaviour. They are written against the real production objects, not stand-ins — the first defect only exists because two real threads touch one real dict.
"""

import io
import threading
import time

from app.observability.active_requests import ActiveRequestRegistry
from app.observability.footer import ActiveRequest, build_footer
from app.observability.terminal import detect_terminal


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
            registry.add_bytes(f"req-{index}", 10)
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


def test_a_wide_model_name_cannot_push_the_footer_onto_a_second_line() -> None:
    """The one-line invariant, measured the way a terminal measures.

    A CJK or emoji name takes two columns per character, so a 36-character name occupies 72. Slicing by `len()` let it through and the line wrapped — arriving through the one input the proxy does not control, the upstream model catalogue.
    """
    from rich.cells import cell_len

    for name in ("界" * 36, "模型" * 20, "🚀" * 30):
        active = [ActiveRequest(request_id="a", model=name, started_at=0.0, bytes_out=4096)]
        for columns in (20, 40, 80, 120):
            line = build_footer(active, 1.0, columns)
            assert cell_len(line) <= columns - 1, f"{name!r} at {columns} columns rendered {cell_len(line)} cells"


def test_an_empty_no_color_does_not_disable_colour() -> None:
    """`NO_COLOR` is honoured when present **and non-empty**.

    `NO_COLOR=` is how a caller clears an inherited value in a shell that cannot delete one, so reading it as "disable colour" does the opposite of what was asked.
    """
    assert detect_terminal(_Stream(tty=True), {"TERM": "xterm", "NO_COLOR": ""}).color is True
    assert detect_terminal(_Stream(tty=True), {"TERM": "xterm", "NO_COLOR": "1"}).color is False
