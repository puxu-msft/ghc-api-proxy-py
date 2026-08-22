import pytest

from app.pipeline.rate_limiter import AdaptiveRateLimiter, RateLimitMode
from app.repetition_detector import RepetitionDetector
from app.shutdown import ShutdownManager, ShutdownPhase


@pytest.mark.asyncio
async def test_rate_limiter_transitions_rate_limited_recovering_normal() -> None:
    limiter = AdaptiveRateLimiter(consecutive_successes=2, default_retry_interval=0)
    limiter.report_rate_limit(0)
    assert limiter.mode is RateLimitMode.RATE_LIMITED
    await limiter.acquire()
    assert limiter.mode is RateLimitMode.RECOVERING
    limiter.report_success()
    limiter.report_success()
    assert limiter.mode is RateLimitMode.NORMAL


def test_repetition_detector_finds_repeated_pattern_incrementally() -> None:
    detector = RepetitionDetector(min_pattern_length=3, min_repetitions=3)
    assert detector.feed("abcabc") is None
    result = detector.feed("abc")
    assert result is not None
    assert result.pattern == "abc"
    assert result.repetitions >= 3


@pytest.mark.asyncio
async def test_shutdown_manager_runs_four_phases() -> None:
    phases: list[ShutdownPhase] = []
    manager = ShutdownManager(on_phase=phases.append)
    await manager.run()
    assert phases == [
        ShutdownPhase.SETUP,
        ShutdownPhase.GRACEFUL_WAIT,
        ShutdownPhase.ABORT,
        ShutdownPhase.FORCE_CLOSE,
    ]
