"""Both halves of rate limiting.

Time is injected, so these assert the decisions rather than waiting for a wall clock.
"""

import pytest

from app.config.schema import ReactiveRateLimiterConfig
from app.pipeline.rate_limiting import (
    RateLimiter,
    RateLimitMode,
    RateLimitSignal,
    proactive_interval,
    read_signal,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


def limiter(clock: FakeClock, **overrides: object) -> RateLimiter:
    return RateLimiter(
        ReactiveRateLimiterConfig.model_validate(overrides),
        clock=clock,
        sleep=clock.sleep,
    )


# --- proactive -------------------------------------------------------------


def test_headers_are_read_across_the_spellings_upstreams_use() -> None:
    assert read_signal({"anthropic-ratelimit-requests-remaining": "5"}).remaining == 5
    assert read_signal({"X-RateLimit-Remaining-Requests": "7"}).remaining == 7
    assert read_signal({"retry-after": "30"}).retry_after == 30.0


def test_unparsable_header_is_ignored_rather_than_guessed() -> None:
    assert read_signal({"retry-after": "soon"}).retry_after is None


def test_healthy_budget_costs_nothing() -> None:
    # A large remaining budget must not slow the common case down.
    assert proactive_interval(RateLimitSignal(remaining=1000, reset_after=60.0)) == pytest.approx(
        0.06
    )


def test_spacing_stretches_the_remaining_budget_to_the_reset() -> None:
    assert proactive_interval(RateLimitSignal(remaining=6, reset_after=60.0)) == 10.0


def test_exhausted_budget_waits_for_the_reset() -> None:
    assert proactive_interval(RateLimitSignal(remaining=0, reset_after=45.0)) == 45.0


def test_absent_budget_information_means_no_spacing() -> None:
    assert proactive_interval(RateLimitSignal()) == 0.0
    assert proactive_interval(RateLimitSignal(remaining=5)) == 0.0


@pytest.mark.asyncio
async def test_proactive_spacing_applies_before_any_failure() -> None:
    # The point of the proactive half: it acts while everything is still succeeding.
    clock = FakeClock()
    rate_limiter = limiter(clock)
    await rate_limiter.acquire()
    rate_limiter.observe_success(
        {"anthropic-ratelimit-requests-remaining": "6", "anthropic-ratelimit-requests-reset": "60"}
    )
    assert rate_limiter.mode is RateLimitMode.NORMAL
    assert rate_limiter.proactive_spacing == 10.0

    await rate_limiter.acquire()
    waited = await rate_limiter.acquire()
    assert waited == pytest.approx(10.0)


# --- reactive --------------------------------------------------------------


@pytest.mark.asyncio
async def test_429_enters_limited_mode() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock)
    assert rate_limiter.observe_failure(429) is True
    assert rate_limiter.mode is RateLimitMode.LIMITED


@pytest.mark.asyncio
async def test_502_enters_limited_mode() -> None:
    rate_limiter = limiter(FakeClock())
    assert rate_limiter.observe_failure(502) is True
    assert rate_limiter.mode is RateLimitMode.LIMITED


@pytest.mark.parametrize("status", [500, 503, 504, 400, 401])
def test_other_statuses_do_not_trigger_the_limiter(status: int) -> None:
    # The spec singles out 429 and 502; 503 and 504 keep their retry behaviour untouched.
    rate_limiter = limiter(FakeClock())
    assert rate_limiter.observe_failure(status) is False
    assert rate_limiter.mode is RateLimitMode.NORMAL


@pytest.mark.asyncio
async def test_retry_interval_is_waited_before_the_next_attempt() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock, retry_interval=30)
    rate_limiter.observe_failure(429)
    assert await rate_limiter.acquire() == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_retry_after_header_overrides_the_configured_interval() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock, retry_interval=10)
    rate_limiter.observe_failure(429, {"retry-after": "45"})
    assert await rate_limiter.acquire() == pytest.approx(45.0)


@pytest.mark.asyncio
async def test_limited_mode_spaces_requests_by_the_request_interval() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock, retry_interval=0, request_interval=7)
    rate_limiter.observe_failure(429)
    await rate_limiter.acquire()
    assert await rate_limiter.acquire() == pytest.approx(7.0)


@pytest.mark.asyncio
async def test_recovery_begins_after_the_recovery_interval() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock, retry_interval=0, recovery_interval=600)
    rate_limiter.observe_failure(429)
    assert rate_limiter.mode is RateLimitMode.LIMITED

    clock.advance(599)
    await rate_limiter.acquire()
    assert rate_limiter.mode is RateLimitMode.LIMITED

    clock.advance(2)
    await rate_limiter.acquire()
    assert rate_limiter.mode is RateLimitMode.RECOVERING


@pytest.mark.asyncio
async def test_consecutive_successes_return_to_normal() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock, retry_interval=0, recovery_interval=0, consecutive_successes=3)
    rate_limiter.observe_failure(429)
    await rate_limiter.acquire()
    assert rate_limiter.mode is RateLimitMode.RECOVERING

    for _ in range(2):
        rate_limiter.observe_success()
    assert rate_limiter.mode is RateLimitMode.RECOVERING
    rate_limiter.observe_success()
    assert rate_limiter.mode is RateLimitMode.NORMAL


@pytest.mark.asyncio
async def test_a_failure_during_recovery_restarts_the_limit() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock, retry_interval=0, recovery_interval=0, consecutive_successes=3)
    rate_limiter.observe_failure(429)
    await rate_limiter.acquire()
    rate_limiter.observe_success()
    rate_limiter.observe_failure(429)
    assert rate_limiter.mode is RateLimitMode.LIMITED

    clock.advance(1)
    await rate_limiter.acquire()
    rate_limiter.observe_success()
    rate_limiter.observe_success()
    # The success count restarted, so two are not yet enough.
    assert rate_limiter.mode is RateLimitMode.RECOVERING


@pytest.mark.asyncio
async def test_limited_spacing_never_undercuts_the_proactive_one() -> None:
    # Whichever half asks for more room wins; the two must not cancel each other.
    clock = FakeClock()
    rate_limiter = limiter(clock, retry_interval=0, request_interval=2)
    rate_limiter.observe_success(
        {"anthropic-ratelimit-requests-remaining": "1", "anthropic-ratelimit-requests-reset": "20"}
    )
    rate_limiter.observe_failure(429)
    await rate_limiter.acquire()
    assert await rate_limiter.acquire() == pytest.approx(20.0)


# --- failure backoff ---------------------------------------------------------


@pytest.mark.asyncio
async def test_first_failure_holds_the_next_attempt_by_the_base() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock)
    await rate_limiter.acquire()
    rate_limiter.note_failure()
    assert rate_limiter.mode is RateLimitMode.NORMAL
    assert await rate_limiter.acquire() == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_consecutive_failures_double_the_wait_up_to_the_cap() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock, failure_backoff_base_sec=1, failure_backoff_max_sec=3)
    await rate_limiter.acquire()
    for expected in (1.0, 2.0, 3.0, 3.0):
        rate_limiter.note_failure()
        assert await rate_limiter.acquire() == pytest.approx(expected)


@pytest.mark.asyncio
async def test_a_success_clears_the_failure_streak() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock)
    await rate_limiter.acquire()
    rate_limiter.note_failure()
    rate_limiter.note_failure()
    rate_limiter.observe_success()
    await rate_limiter.acquire()
    rate_limiter.note_failure()
    assert await rate_limiter.acquire() == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_backoff_never_shortens_a_limited_mode_wait() -> None:
    # `retry-after` and `retry_interval` stay the authority on a 429; the streak only ever asks
    # for more room than they do.
    clock = FakeClock()
    rate_limiter = limiter(clock, retry_interval=10)
    rate_limiter.observe_failure(429)
    rate_limiter.note_failure()
    assert await rate_limiter.acquire() == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_a_sustained_limited_streak_eventually_waits_longer_than_the_interval() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock, retry_interval=10, failure_backoff_base_sec=4)
    waits: list[float] = []
    for _ in range(3):
        rate_limiter.observe_failure(429)
        rate_limiter.note_failure()
        waits.append(await rate_limiter.acquire())
    # The streak asks 4, 8, 16; the first two stay under the configured interval.
    assert waits == pytest.approx([10.0, 10.0, 16.0])


@pytest.mark.asyncio
async def test_zero_base_disables_the_backoff() -> None:
    clock = FakeClock()
    rate_limiter = limiter(clock, failure_backoff_base_sec=0)
    await rate_limiter.acquire()
    rate_limiter.note_failure()
    rate_limiter.note_failure()
    assert await rate_limiter.acquire() == 0.0


@pytest.mark.asyncio
async def test_a_streak_longer_than_the_exponent_can_survive_caps_instead_of_overflowing() -> None:
    # Days of continuous failure accumulate a huge streak; the retry loop must be told the
    # upstream failed, not die on a float overflow raised out of the doubling.
    clock = FakeClock()
    rate_limiter = limiter(clock)
    await rate_limiter.acquire()
    for _ in range(2000):
        rate_limiter.note_failure()
    assert await rate_limiter.acquire() == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_a_wait_pushed_while_another_acquire_slept_is_not_erased() -> None:
    # The limiter is shared: a failure another request notes while this acquire is waking up must
    # survive the wake-up's own schedule write.
    clock = FakeClock()

    async def sleep_and_note(seconds: float) -> None:
        await clock.sleep(seconds)
        rate_limiter.note_failure()

    rate_limiter = RateLimiter(
        ReactiveRateLimiterConfig(), clock=clock, sleep=sleep_and_note
    )
    await rate_limiter.acquire()
    rate_limiter.note_failure()
    await rate_limiter.acquire()
    # The note during the sleep pushed the schedule one second out (failures=2 → 0.5 · 2¹); the
    # wake-up's own schedule write kept it instead of resetting it to "now".
    assert await rate_limiter.acquire() == pytest.approx(1.0)
