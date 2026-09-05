"""The counters `/metrics` answers with.

`prometheus_client`'s default `REGISTRY` is what `ops_routes.metrics` serialises, so a counter defined here is exported by being defined — there is nothing to register and nothing to wire. That is also why they live in one module: a metric declared beside the code that increments it is invisible until that code is imported, and a metric nobody can find is a metric nobody reads.

Deliberately not `app.observability.telemetry`. That module builds an OpenTelemetry meter provider and is only ever constructed by the legacy `app_factory`; going through it would pull four `opentelemetry-*` packages into a path that today imports none of them, to reach the same Prometheus endpoint.

Counts rather than the detail: a count says how often, and the per-request record says which fields on which request. Both are needed and neither substitutes — the count is what shows a translation quietly dropping a parameter on every request, and the record is what says which parameter.
"""

import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram

# Labelled by direction and code rather than by model or request, because a metric's label set multiplies its series count and a request id would make one series per request. Which request lost what is the record's question; this answers how often it happens at all.
TRANSLATION_LOSSES = Counter(
    "ghc_proxy_translation_losses_total",
    "Fields a translation could not carry, by crossing direction and loss code.",
    ("direction", "code"),
)

# Unlabelled: there is one reason this fires and one thing it removes. A counter rather than a log line because it fires on every request from the client that sends it — a per-request INFO would be noise, while a number that climbs in step with the request count is exactly the right shape for something that is supposed to be routine.
ATTRIBUTION_LINES_STRIPPED = Counter(
    "ghc_proxy_attribution_lines_stripped_total",
    "Client-injected attribution lines removed from an inbound Anthropic system prompt.",
)

# Labelled, unlike its neighbour above, because there is no single reason this fires: an operator adds a flag to the map after upstream refused a request over it, and the question they come back with is which flag on which model is still being taken away. `flag` carries the **configured** spelling rather than the client's — a label whose value a client controls has no bound on its series count — and `model` is the resolved id, which the catalog bounds.
#
# **What zero does not mean.** This counts what the strip removed, which is a subset of what the client asked for. Two `anthropic-beta` headers on one request are folded into one by the dict comprehension in `forwarded_client_headers`, and the loser is gone before the strip runs — so a flag configured here, sent by the client, and never counted, is indistinguishable from a flag nobody sent. Measured 2026-08-22 against a two-header request: of three flags sent and three configured, one incremented. Closing that is a separate piece of work on the header allowlist, not a branch on this counter.
#
# The name says what it does rather than why: the counter knows the configured table removed these flags, and does not know whether the model would in fact have refused them. Which of the operator's entries are still earning their place is an upstream question nothing here has measured.
BETA_FLAGS_STRIPPED = Counter(
    "ghc_proxy_beta_flags_stripped_total",
    "`anthropic-beta` flags removed from a client request because the configured table names them for the resolved model.",
    ("model", "flag"),
)


RESPONSIVENESS_BUCKETS = (.001, .005, .01, .025, .05, .1, .25, .5, 1, 2, 3, 5, 10, float("inf"))


class DurationMetric:
    """Keep a distribution and an exact high-water mark without retaining samples."""

    def __init__(self, histogram: Histogram, maximum: Gauge, failures: Counter, clock: Callable[[], float]) -> None:
        self.histogram = histogram
        self.maximum = maximum
        self.failures = failures
        self.clock = clock
        self._maximum = 0.0
        self._lock = threading.Lock()

    def observe(self, seconds: float, *, failed: bool = False) -> None:
        seconds = max(0.0, seconds)
        self.histogram.observe(seconds)
        if failed:
            self.failures.inc()
        with self._lock:
            if seconds > self._maximum:
                self._maximum = seconds
                self.maximum.set(seconds)

    @contextmanager
    def measure(self) -> Generator[None]:
        started = self.clock()
        failed = True
        try:
            yield
            failed = False
        finally:
            self.observe(self.clock() - started, failed=failed)


@dataclass(slots=True)
class _RenderProgress:
    previous_start: float | None = None
    last_success: float | None = None


class ResponsivenessMetrics:
    """Fixed-cardinality process metrics, with only active TUI/I/O state retained.

    Progress callbacks take this object's short lock, never a renderer or output lock. Durations survive lifecycle exit; active state does not. Tests may supply a private Prometheus registry without resetting the process's counters.
    """

    def __init__(self, registry: CollectorRegistry = REGISTRY, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._lock = threading.Lock()
        self._tuis: dict[object, _RenderProgress] = {}
        self._io: dict[str, dict[object, tuple[object, float]]] = {"write": {}, "flush": {}}
        self.loop_lag = self._family("event_loop_lag", "Event-loop heartbeat lateness; not CPU time.", registry)[()]
        self.render_interval = self._family("tui_render_interval", "Time between footer callback entries, including work, waits and scheduling.", registry)[()]
        self.render_duration = self._family("tui_render_duration", "Footer callback duration, excluding subsequent Console rendering and I/O.", registry)[()]
        self.terminal_io = {
            key[0]: metric for key, metric in self._family(
                "tui_terminal_io_duration", "Footer Console TextIO call duration, including scheduling pauses.", registry,
                ("operation",), (("write",), ("flush",)),
            ).items()
        }
        self.tokenizer = self._family(
            "local_tokenizer_duration", "Local estimator lookup or post-lookup estimation duration; not pure BPE CPU time.", registry,
            ("format", "phase"), tuple((fmt, phase) for fmt in ("anthropic", "responses") for phase in ("lookup", "estimate")),
        )
        self.loop_active = Gauge("ghc_proxy_event_loop_monitor_active", "Running event-loop heartbeat tasks.", registry=registry)
        self.tui_active = Gauge("ghc_proxy_tui_active", "Active footer lifecycles.", registry=registry)
        self.tui_active.set_function(self._active_tuis)
        self.render_age = Gauge("ghc_proxy_tui_last_render_age_seconds", "Oldest active footer's successful callback age; NaN if any active footer has no success yet, zero if inactive.", registry=registry)
        self.render_age.set_function(self._render_age)
        self.io_active = Gauge("ghc_proxy_tui_terminal_io_in_progress", "Unreturned footer Console TextIO calls.", ("operation",), registry=registry)
        self.io_age = Gauge("ghc_proxy_tui_terminal_io_in_progress_seconds", "Oldest unreturned footer Console TextIO call age, zero if none.", ("operation",), registry=registry)
        for operation in ("write", "flush"):
            self.io_active.labels(operation).set_function(lambda operation=operation: self._io_progress(operation)[0])
            self.io_age.labels(operation).set_function(lambda operation=operation: self._io_progress(operation)[1])

    def _family(
        self,
        name: str,
        description: str,
        registry: CollectorRegistry,
        labels: tuple[str, ...] = (),
        values: tuple[tuple[str, ...], ...] = ((),),
    ) -> dict[tuple[str, ...], DurationMetric]:
        histogram = Histogram(f"ghc_proxy_{name}_seconds", description, labels, buckets=RESPONSIVENESS_BUCKETS, registry=registry)
        maximum = Gauge(f"ghc_proxy_{name}_max_seconds", f"Process lifetime maximum. {description}", labels, registry=registry)
        failures = Counter(f"ghc_proxy_{name}_failures_total", "Failed measured operations; labels never contain exception text.", labels, registry=registry)
        return {
            value: DurationMetric(
                histogram.labels(*value) if labels else histogram,
                maximum.labels(*value) if labels else maximum,
                failures.labels(*value) if labels else failures,
                self.clock,
            ) for value in values
        }

    def activate(self, owner: object) -> None:
        with self._lock:
            self._tuis[owner] = _RenderProgress()

    def deactivate(self, owner: object) -> None:
        with self._lock:
            self._tuis.pop(owner, None)
            for pending in self._io.values():
                for token in [token for token, (writer, _) in pending.items() if writer is owner]:
                    del pending[token]

    def render_started(self, owner: object, now: float) -> bool:
        with self._lock:
            state = self._tuis.get(owner)
            if state is None:
                return False
            previous = state.previous_start
            state.previous_start = now
        if previous is not None:
            self.render_interval.observe(now - previous)
        return True

    def render_succeeded(self, owner: object, now: float) -> None:
        with self._lock:
            state = self._tuis.get(owner)
            if state is not None:
                state.last_success = now

    def io_started(self, owner: object, operation: str, token: object, now: float) -> None:
        with self._lock:
            if owner in self._tuis:
                self._io[operation][token] = (owner, now)

    def io_finished(self, operation: str, token: object) -> None:
        with self._lock:
            self._io[operation].pop(token, None)

    def _active_tuis(self) -> float:
        with self._lock:
            return len(self._tuis)

    def _render_age(self) -> float:
        now = self.clock()
        with self._lock:
            if not self._tuis:
                return 0.0
            successful = [state.last_success for state in self._tuis.values()]
        if any(value is None for value in successful):
            return float("nan")
        return max(max(0.0, now - value) for value in successful if value is not None)

    def _io_progress(self, operation: str) -> tuple[int, float]:
        now = self.clock()
        with self._lock:
            starts = [started for _, started in self._io[operation].values()]
        return len(starts), max(0.0, now - min(starts)) if starts else 0.0


RESPONSIVENESS = ResponsivenessMetrics()
