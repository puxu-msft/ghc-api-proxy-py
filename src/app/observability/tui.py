import logging
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Literal

from rich.console import Console
from rich.live import Live
from rich.text import Text
from textual.app import App

from app.observability.active_requests import ActiveRequestRegistry
from app.observability.footer import build_footer
from app.observability.terminal import TerminalCapabilities, detect_terminal

type TuiView = Literal["collapsed", "panel_list", "detail"]


@dataclass(frozen=True, slots=True)
class TuiState:
    view: TuiView = "collapsed"
    requests: tuple[str, ...] = ()
    selected_index: int | None = None


@dataclass(frozen=True, slots=True)
class AddRequest:
    request_id: str


@dataclass(frozen=True, slots=True)
class Expand:
    pass


@dataclass(frozen=True, slots=True)
class EnterDetail:
    index: int


@dataclass(frozen=True, slots=True)
class ExitView:
    pass


type TuiAction = AddRequest | Expand | EnterDetail | ExitView


def reduce_tui(state: TuiState, action: TuiAction) -> TuiState:
    match action:
        case AddRequest(request_id=request_id):
            return replace(state, requests=(*state.requests, request_id))
        case Expand():
            return replace(state, view="panel_list")
        case EnterDetail(index=index):
            return replace(state, view="detail", selected_index=index)
        case ExitView():
            return replace(state, view="collapsed", selected_index=None)


class ProxyTui(App[None]):
    """Textual application shell; runtime subscription remains opt-in.

    Unused by the live footer below, which renders through `rich.Live` instead. A textual App owns the whole screen or an inline block, and neither produces the shape this project wants — a request log scrolling in native scrollback with one line pinned under it. Kept because the panel and detail views the reducer above already models are the plausible future caller; see `.dev/docs/tui/spec.md` for what that would have to re-decide.
    """


class LiveConsoleHandler(logging.Handler):
    """Route log records through the console that owns the footer.

    A second writer to the same terminal is the whole problem: `rich.Live` tracks how many rows its region occupies and erases exactly that many before redrawing, so anything written behind its back lands inside the region and is wiped, or pushes the region without it noticing. Printing through the live console is what keeps the two in one accounting.

    `markup=False` is load-bearing rather than tidiness: the log format opens with `[ OK ]` / `[FAIL]`, and rich reads square brackets as markup. Left on, every status prefix is swallowed as an unknown style tag.

    `soft_wrap=True` for the same class of reason. Without it rich re-flows the record to the console width and inserts its own line break, so a rich request line arrives split across two physical lines with no prefix on the second and the fields it was carrying stranded there. Wrapping a log line is the terminal's job, and it does it without rewriting the text.

    The record is handed over as `Text.from_ansi` rather than as a string. The renderer emits real escape sequences, which is what the plain path needs; passed to rich as a string they would be *characters*, counted toward the width and printed literally. Parsing them turns them back into styles rich understands and keeps its width accounting honest.
    """

    def __init__(self, live: Live) -> None:
        super().__init__()
        self._live = live

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._live.console.print(Text.from_ansi(self.format(record)), soft_wrap=True)
        except Exception:
            self.handleError(record)


@dataclass(slots=True)
class FooterTui:
    """The live footer and the log stream above it.

    Read-only: it subscribes to what requests are in flight and draws them. Controlling a request from here is out of scope by ruling, not by omission — that belongs to the approval system.
    """

    registry: ActiveRequestRegistry
    capabilities: TerminalCapabilities
    refresh_per_second: int = 8
    _live: Live | None = None
    _handler: LiveConsoleHandler | None = None

    def _render(self) -> Text:
        """Recomputed on every refresh, so elapsed fields tick without anyone pushing an update."""
        columns = self._live.console.width if self._live is not None else 80
        snapshot = self.registry.observation_snapshot()
        # The TUI consumes the store's one atomic live/completed frame even though this collapsed view intentionally renders only its live half. A future detail view can use `snapshot.completed` without introducing another read boundary.
        line = build_footer(
            list(snapshot.live),
            time.monotonic(),
            columns,
            unicode=self.capabilities.unicode,
            draining=self.registry.draining,
            connections=self.registry.connections(),
        )
        # `dim` is an ANSI attribute, so it is withheld on the same probe that withholds colour rather than on a separate one.
        return Text(line, style="dim" if self.capabilities.color else "", no_wrap=True, overflow="crop")

    @contextmanager
    def activate(self) -> Generator[FooterTui]:
        console = Console(file=sys.stderr, highlight=False, soft_wrap=False, no_color=not self.capabilities.color, emoji=False)
        live = Live(
            get_renderable=self._render,
            console=console,
            refresh_per_second=self.refresh_per_second,
            transient=True,
            vertical_overflow="crop",
        )
        self._live = live
        handler = LiveConsoleHandler(live)
        self._handler = handler
        root = logging.getLogger()
        # Take over the existing formatting rather than inventing a second one: the structlog processor chain already renders the fixed-width status prefixes, and the footer's job is to sit under those lines, not to restyle them.
        for existing in root.handlers:
            if existing.formatter is not None:
                handler.setFormatter(existing.formatter)
                break
        previous = list(root.handlers)
        root.handlers = [handler]
        with live:
            try:
                yield self
            finally:
                root.handlers = previous
                self._live = None
                self._handler = None


def footer_tui_or_none(registry: ActiveRequestRegistry, capabilities: TerminalCapabilities | None = None) -> FooterTui | None:
    """The TUI when the attached terminal can carry it, `None` otherwise.

    Probed rather than configured: whether a live region is appropriate is a property of where the output is going, and the process can see that directly. A pipe, a file, a CI job and `TERM=dumb` all get plain logs and not one control sequence — which is also what keeps the redirected output diffable.
    """
    caps = capabilities if capabilities is not None else detect_terminal()
    if not caps.live:
        return None
    return FooterTui(registry=registry, capabilities=caps)
