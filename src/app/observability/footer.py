"""The live footer: one line naming every request currently in flight.

Pure. Callers supply the active set, the current time and the column count; nothing here reads a clock or touches I/O, so the whole width algorithm is testable without a terminal.

There is one shape whatever the concurrency: one segment per model, `<model>[ xN] <t1>[ ↓<b1>] <t2>[ ↓<b2>] ...`, joined by ` | `. The model name is the only thing that merges. Every in-flight request keeps its own elapsed and its own byte count, because those are the two fields that differ between two calls to the same model and are the reason to look at the line at all.

How many requests each segment gets is decided by the terminal width rather than a fixed per-model cap: every shown model is guaranteed its longest-running request, and the leftover columns are handed out round-robin. A wide terminal shows every in-flight request; a narrow one degrades to the slowest few per model instead of dropping whole models.
"""

import re
from dataclasses import dataclass

from rich.cells import cell_len, set_cell_size

PREFIX = "[<-->] "
# Same six columns as the running prefix, so the line does not shift sideways at the moment the state changes — a jump would read as the display restarting rather than as the process changing what it is doing.
DRAINING_PREFIX = "[DRIN] "
RESOLVING = "(resolving)"
SEPARATOR = " | "
# Between the requests of one model. A space alone ran them together — `48.6s ↓15.6KB 28.3s` reads as one request with three fields rather than as two requests — and the reader has no way to know where one ends, because any of the fields may be absent.
ITEM_SEPARATOR = ", "
# Any C0 control character would force a second physical line and break the one-line invariant.
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ActiveRequest:
    """One in-flight request, as the footer needs it.

    `model` is empty until routing resolves it. `bytes_out` stays `None` until the request reports streaming progress: its absence means "nothing has streamed back yet", which is a different fact from `0`.
    """

    request_id: str
    model: str
    started_at: float
    bytes_out: int | None = None
    attempts: int = 1


def format_duration(seconds: float) -> str:
    """Sub-second precision under one second, one-decimal seconds above it."""
    if seconds < 1.0:
        return f"{int(seconds * 1000)}ms"
    return f"{seconds:.1f}s"


def format_bytes(count: int) -> str:
    if count >= 1_048_576:
        return f"{count / 1_048_576:.1f}MB"
    if count >= 1024:
        return f"{count / 1024:.1f}KB"
    return f"{count}B"


def _item(request: ActiveRequest, now: float, *, unicode: bool) -> str:
    """`<elapsed>[ ↓<bytes>]` for one request, with the retry count when there is one.

    The arrow degrades to `<` where the stream's encoding cannot carry it, matching the direction idiom the existing `[<-->]` status prefix already uses. Not dropped entirely: without a marker the byte count would read as a second time field.
    """
    elapsed = format_duration(max(0.0, now - request.started_at))
    if request.attempts > 1:
        elapsed = f"{elapsed}({request.attempts - 1})"
    if request.bytes_out is None:
        return elapsed
    return f"{elapsed} {'↓' if unicode else '<'}{format_bytes(request.bytes_out)}"


@dataclass(slots=True)
class _Group:
    """One model and its in-flight requests, longest-running first."""

    model: str
    items: list[str]

    @property
    def head(self) -> str:
        """`<model>[ xN]` — shown whatever the width budget allows.

        `xN` reports how many requests the model actually has, not how many are shown. Under width pressure the two differ, and this count is what tells you the line is hiding something. ASCII rather than the multiplication sign upstream uses, to keep the line free of characters a linter flags as ambiguous and a terminal may render double-width.
        """
        name = self.model or RESOLVING
        return f"{name} x{len(self.items)}" if len(self.items) > 1 else name

    def render(self, count: int) -> str:
        return f"{self.head} {ITEM_SEPARATOR.join(self.items[:count])}"


def _group(active: list[ActiveRequest], now: float, *, unicode: bool) -> list[_Group]:
    """Group by resolved model, oldest request first, both within and across groups.

    The key is the raw model string, empty included — **not** the `(resolving)` placeholder, which is only a rendering of "not known yet". A model genuinely named `(resolving)` would otherwise merge with the unresolved requests, which is a different thing entirely.
    """
    groups: dict[str, _Group] = {}
    for request in sorted(active, key=lambda item: item.started_at):
        group = groups.get(request.model)
        if group is None:
            group = _Group(model=request.model, items=[])
            groups[request.model] = group
        group.items.append(_item(request, now, unicode=unicode))
    return list(groups.values())


def build_footer(
    active: list[ActiveRequest],
    now: float,
    columns: int,
    *,
    unicode: bool = True,
    draining: bool = False,
    connections: int = 0,
) -> str:
    """The footer line, or an empty string when there is nothing to report.

    `draining` swaps the prefix for `[DRIN]`. Once the listener has stopped accepting, the same list of requests means something different — it can only shrink, and nothing new will join it — and a display that looked identical either way would leave the operator unable to tell a busy server from one that is on its way out.

    `connections` is drawn even with no requests in flight, and that combination is the reason the field exists. A pooled client holds its connection between requests, so a drain waits on something the request list cannot show; without this the footer goes blank and a stall is indistinguishable from a finished shutdown.
    """
    if not active and connections <= 0:
        return ""

    prefix = DRAINING_PREFIX if draining else PREFIX
    segments: list[str] = []
    if connections > 0:
        segments.append(f"{connections} clients")
    if not active:
        return _finalize(prefix + SEPARATOR.join(segments), columns)

    groups = _group(active, now, unicode=unicode)
    budget = columns - 1

    # Pass one decides which models appear at all. Each is measured in its minimum form (head plus its longest-running request); models that do not fit collapse into a ` | +K more` tail.
    shown: list[_Group] = []
    used = cell_len(prefix) + sum(cell_len(segment) + cell_len(SEPARATOR) for segment in segments)
    for index, group in enumerate(groups):
        separator = cell_len(SEPARATOR) if shown else 0
        remaining = len(groups) - index
        # Reserve the overflow tail exactly rather than approximately: if this model is taken, `remaining - 1` are left over; if it is rejected the loop breaks immediately, so the real overflow equals what was reserved on the previously accepted model.
        tail = cell_len(f"{SEPARATOR}+{remaining - 1} more") if remaining > 1 else 0
        width = cell_len(group.head) + 1 + cell_len(group.items[0])
        if used + separator + width + tail > budget and shown:
            break
        used += separator + width
        shown.append(group)
    overflow = len(groups) - len(shown)

    # Pass two spends the leftover columns widening the shown models one request at a time, round-robin, so one busy model cannot starve the others.
    counts = [1] * len(shown)
    total = used + (cell_len(SEPARATOR) + cell_len(f"+{overflow} more") if overflow else 0)
    grew = True
    while grew:
        grew = False
        for index, group in enumerate(shown):
            if counts[index] >= len(group.items):
                continue
            cost = cell_len(ITEM_SEPARATOR) + cell_len(group.items[counts[index]])
            if total + cost > budget:
                continue
            total += cost
            counts[index] += 1
            grew = True

    segments.extend(group.render(counts[index]) for index, group in enumerate(shown))
    if overflow:
        segments.append(f"+{overflow} more")
    return _finalize(prefix + SEPARATOR.join(segments), columns)


def _finalize(line: str, columns: int) -> str:
    """The single exit for every branch, and the only place the one-line invariant is enforced.

    Strips control characters first, since a model name or path carrying one would force a second physical line whatever the width, then cuts to `columns - 1`. The -1 avoids the last-column auto-wrap some terminals do. Measured: without the cut an 80-column footer wraps at 40 columns on every run, and under a reserved-region renderer the overflow lands outside the region and corrupts the log area.

    Measured in **terminal cells**, not code points. A CJK or emoji model name occupies two columns per character, so slicing by `len()` lets a 36-character name claim 72 columns and wrap — the same defect the cut exists to prevent, arriving through the one input the proxy does not control. `rich.cells` is already in the dependency tree and answers this properly, including a cut that lands mid-character.

    Cut only when it is too wide. `set_cell_size` also *pads*, and padding every frame to the full width would make an idle footer a line of spaces rather than nothing, and would repaint the whole width on every tick for no gain.
    """
    stripped = CONTROL_CHARS.sub("", line)
    limit = max(0, columns - 1)
    return stripped if cell_len(stripped) <= limit else set_cell_size(stripped, limit)
