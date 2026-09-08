"""Rate limiting, in three parts.

Reactive: the spec triggers it only on upstream 429 or 502, and explicitly not on 503 or 504.
Once limited, requests are spaced by `request_interval`.
A recovery attempt happens after `recovery_interval`, and enough successes in a row return it.

Proactive: upstream advertises its remaining budget on successful responses.
The wall can therefore be seen before it is hit.
Spacing costs nothing when the budget is healthy and avoids the 429 when it is not.
It needs no configuration of its own, because the numbers come from upstream.

Backoff: consecutive retryable upstream failures of any kind — a torn connection, a timeout, a
5xx — hold the next attempt back, doubling per failure. Retrying each one instantly adds load
exactly when an upstream is least able to take it. Failures are reported through `note_failure`
by whichever layer saw them, so the wait is shared across requests and covers the replay path
alongside the driver's own retry loop.
"""

import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

import anyio

from app.config.schema import ReactiveRateLimiterConfig

# Only these two put the limiter into limited mode.
REACTIVE_STATUSES = frozenset({429, 502})

_REMAINING_HEADERS = (
    "anthropic-ratelimit-requests-remaining",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining",
)
_RESET_HEADERS = (
    "anthropic-ratelimit-requests-reset",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset",
)


class RateLimitMode(StrEnum):
    NORMAL = "normal"
    LIMITED = "limited"
    RECOVERING = "recovering"


@dataclass(frozen=True, slots=True)
class RateLimitSignal:
    """What one upstream response said about the budget."""

    remaining: int | None = None
    reset_after: float | None = None
    retry_after: float | None = None

    @property
    def informative(self) -> bool:
        return self.remaining is not None or self.retry_after is not None


def _first_number(headers: Mapping[str, str], names: tuple[str, ...]) -> float | None:
    for name in names:
        raw = headers.get(name) or headers.get(name.title())
        if raw is None:
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return None


def read_signal(headers: Mapping[str, str]) -> RateLimitSignal:
    """Read the advertised budget off a response.

    Header names differ between upstreams, so several spellings are tried.
    An unparsable value is ignored instead of guessed at.
    """
    lowered = {key.lower(): value for key, value in headers.items()}
    remaining = _first_number(lowered, _REMAINING_HEADERS)
    retry_after = _first_number(lowered, ("retry-after",))
    return RateLimitSignal(
        remaining=int(remaining) if remaining is not None else None,
        reset_after=_first_number(lowered, _RESET_HEADERS),
        retry_after=retry_after,
    )


def proactive_interval(signal: RateLimitSignal) -> float:
    """Spacing that keeps the remaining budget alive until it resets.

    With a healthy budget this is near zero, so the common case pays nothing.
    """
    if signal.remaining is None or signal.reset_after is None:
        return 0.0
    if signal.reset_after <= 0:
        return 0.0
    if signal.remaining <= 0:
        return signal.reset_after
    return signal.reset_after / signal.remaining


class RateLimiter:
    """Gates outbound attempts. One instance per provider."""

    def __init__(
        self,
        config: ReactiveRateLimiterConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
    ) -> None:
        self._config = config
        self._clock = clock
        self._sleep = sleep
        self._mode = RateLimitMode.NORMAL
        self._next_allowed = 0.0
        self._limited_since = 0.0
        self._successes = 0
        self._proactive_interval = 0.0
        self._failures = 0

    @property
    def mode(self) -> RateLimitMode:
        return self._mode

    @property
    def proactive_spacing(self) -> float:
        return self._proactive_interval

    def _failure_backoff(self) -> float:
        """Wait owed before the next attempt, from consecutive retryable upstream failures.

        Each failure in a row doubles the wait — `base`, then `2·base`, then `4·base`, capped — so
        a flapping upstream is asked again at widening intervals instead of being hammered. A
        success clears the streak — see `observe_success`.
        """
        if self._failures <= 0:
            return 0.0
        # The exponent is bounded before the power is taken: a streak that has run for days would
        # otherwise raise a float out of `2 ** (failures - 1)`, and the retry loop must be told the
        # upstream failed, not die on an OverflowError instead of the error it was reporting.
        exponent = min(self._failures - 1, 64)
        return min(
            self._config.failure_backoff_base_sec * 2.0**exponent,
            self._config.failure_backoff_max_sec,
        )

    def _spacing(self) -> float:
        if self._mode is RateLimitMode.NORMAL:
            return self._proactive_interval
        return max(float(self._config.request_interval), self._proactive_interval)

    async def acquire(self) -> float:
        """Wait until an attempt may go out. Returns how long it waited, in seconds."""
        self._maybe_start_recovering()
        now = self._clock()
        wait = max(0.0, self._next_allowed - now)
        if wait > 0:
            await self._sleep(wait)
        # `max` rather than assignment, for the same reason `note_failure` uses it: this limiter is
        # shared, and a failure noted by another request while this one slept must not be erased
        # by the wake-up.
        self._next_allowed = max(self._next_allowed, self._clock() + self._spacing())
        return wait

    def _maybe_start_recovering(self) -> None:
        if self._mode is not RateLimitMode.LIMITED:
            return
        if self._clock() - self._limited_since >= self._config.recovery_interval:
            self._mode = RateLimitMode.RECOVERING
            self._successes = 0

    def note_failure(self) -> None:
        """Record an upstream attempt failure and hold the next attempt back accordingly.

        Deliberately separate from `observe_failure`: the 429/502 path reports the same failure
        twice (once from the response, once through `_handle_failure`), and counting it there
        would double the streak. Callers report one failed attempt exactly once.

        The wait is pushed onto `next_allowed` here rather than folded into `_spacing`, because
        `acquire` reads the *previous* acquire's spacing — a wait set only there would land one
        attempt later than the failure it answers, and a replay path that opens a fresh driver per
        reopen would never be delayed at all. `max` keeps an existing limited-mode wait intact: a
        backoff never shortens what `retry-after` already asked for.
        """
        self._failures += 1
        self._next_allowed = max(self._next_allowed, self._clock() + self._failure_backoff())

    def observe_success(self, headers: Mapping[str, str] | None = None) -> None:
        """Record a success and whatever budget it advertised."""
        if headers is not None:
            self._proactive_interval = proactive_interval(read_signal(headers))
        self._failures = 0
        if self._mode is RateLimitMode.RECOVERING:
            self._successes += 1
            if self._successes >= self._config.consecutive_successes:
                self._mode = RateLimitMode.NORMAL
                self._successes = 0

    def observe_failure(
        self,
        status_code: int,
        headers: Mapping[str, str] | None = None,
    ) -> bool:
        """Record a failure. Returns whether it put the limiter into limited mode.

        503 and 504 are deliberately not among the triggers.
        The spec keeps their retry behaviour untouched.
        """
        if status_code not in REACTIVE_STATUSES:
            return False
        signal = read_signal(headers or {})
        wait = signal.retry_after if signal.retry_after is not None else self._config.retry_interval
        self._mode = RateLimitMode.LIMITED
        self._limited_since = self._clock()
        self._successes = 0
        self._next_allowed = self._clock() + float(wait)
        return True
