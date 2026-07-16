import time
from collections.abc import Callable
from enum import StrEnum

import anyio


class RateLimitMode(StrEnum):
    NORMAL = "normal"
    RATE_LIMITED = "rate_limited"
    RECOVERING = "recovering"


class AdaptiveRateLimiter:
    def __init__(
        self,
        *,
        consecutive_successes: int = 5,
        default_retry_interval: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.mode = RateLimitMode.NORMAL
        self._needed = consecutive_successes
        self._successes = 0
        self._default_retry_interval = default_retry_interval
        self._clock = clock
        self._retry_at = 0.0
        self._gate = anyio.Event()
        self._gate.set()

    async def acquire(self) -> float:
        started = self._clock()
        if self.mode is RateLimitMode.RATE_LIMITED:
            await anyio.sleep(max(0.0, self._retry_at - self._clock()))
            await self.release_for_retry()
        if self.mode is RateLimitMode.RECOVERING:
            await self._gate.wait()
        return (self._clock() - started) * 1000

    def report_success(self) -> None:
        if self.mode is RateLimitMode.RECOVERING:
            self._successes += 1
            if self._successes >= self._needed:
                self.mode = RateLimitMode.NORMAL
                self._gate.set()

    def report_rate_limit(self, retry_after: float | None) -> None:
        self.mode = RateLimitMode.RATE_LIMITED
        self._successes = 0
        self._gate = anyio.Event()
        self._retry_at = self._clock() + (
            retry_after if retry_after is not None else self._default_retry_interval
        )

    async def release_for_retry(self) -> None:
        self.mode = RateLimitMode.RECOVERING
        self._gate.set()


PassthroughRateLimiter = AdaptiveRateLimiter