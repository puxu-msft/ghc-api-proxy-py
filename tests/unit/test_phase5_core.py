import pytest

from app.auto_truncate.token_limits import TokenLimitCache
from app.pipeline.rate_limiter import AdaptiveRateLimiter, RateLimitMode
from app.repetition_detector import RepetitionDetector
from app.shutdown import ShutdownManager, ShutdownPhase


@pytest.mark.asyncio
async def test_rate_limiter_transitions_rate_limited_recovering_normal() -> None:
    limiter = AdaptiveRateLimiter(consecutive_successes=2)
    limiter.report_rate_limit(0)
    assert limiter.mode is RateLimitMode.RATE_LIMITED
    await limiter.release_for_retry()
    assert limiter.mode is RateLimitMode.RECOVERING
    limiter.report_success()
    limiter.report_success()
    assert limiter.mode is RateLimitMode.NORMAL


def test_token_limit_cache_uses_normalized_model_and_24h_ttl() -> None:
    now = 100.0
    cache = TokenLimitCache(ttl_seconds=86400, clock=lambda: now)
    cache.record("Claude-Opus-4.6", 200_000)
    assert cache.get("claude-opus-4-6") == 200_000
    now = 86_501
    assert cache.get("claude-opus-4.6") is None


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
