from enum import StrEnum

import anyio


class RateLimitMode(StrEnum):
    NORMAL = "normal"
    RATE_LIMITED = "rate_limited"
    RECOVERING = "recovering"


class AdaptiveRateLimiter:
    def __init__(self, *, consecutive_successes: int = 5) -> None:
        self.mode = RateLimitMode.NORMAL
        self._needed = consecutive_successes
        self._successes = 0
        self._gate = anyio.Event()
        self._gate.set()

    async def acquire(self) -> float:
        if self.mode is not RateLimitMode.NORMAL:
            await self._gate.wait()
        return 0.0

    def report_success(self) -> None:
        if self.mode is RateLimitMode.RECOVERING:
            self._successes += 1
            if self._successes >= self._needed:
                self.mode = RateLimitMode.NORMAL
                self._gate.set()

    def report_rate_limit(self, retry_after: float | None) -> None:
        del retry_after
        self.mode = RateLimitMode.RATE_LIMITED
        self._successes = 0
        self._gate = anyio.Event()

    async def release_for_retry(self) -> None:
        self.mode = RateLimitMode.RECOVERING
        self._gate.set()


PassthroughRateLimiter = AdaptiveRateLimiter