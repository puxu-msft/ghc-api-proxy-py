from app.tokenization.calibration import (
    BUCKET_BOUNDS,
    FACTOR_CLAMP_MAX,
    FACTOR_CLAMP_MIN,
    WEIGHT_CAP,
    CalibrationEngine,
)


def test_bucket_boundaries_and_protocol_model_isolation() -> None:
    assert (0, 15_000, 30_000, 60_000, 120_000, 240_000, float("inf")) == BUCKET_BOUNDS
    engine = CalibrationEngine()
    engine.learn("anthropic", "Claude-Opus-4.8", 20_000, 30_000)

    assert engine.calibrate("anthropic", "claude-opus-4-8", 20_000) == 30_000
    assert engine.calibrate("gemini", "claude-opus-4-8", 20_000) == 20_000
    assert engine.calibrate("anthropic", "other", 20_000) == 20_000


def test_factor_is_clamped_and_log_interpolated() -> None:
    engine = CalibrationEngine()
    engine.learn("anthropic", "model", 10_000, 100)
    engine.learn("anthropic", "model", 100_000, 500_000)

    assert engine.factor_at("anthropic", "model", 1) == FACTOR_CLAMP_MIN
    assert engine.factor_at("anthropic", "model", 1_000_000) == FACTOR_CLAMP_MAX
    middle = engine.factor_at("anthropic", "model", 31_623)
    assert FACTOR_CLAMP_MIN < middle < FACTOR_CLAMP_MAX


def test_bucket_weight_is_bounded() -> None:
    engine = CalibrationEngine()
    for _ in range(WEIGHT_CAP + 10):
        engine.learn("anthropic", "model", 10_000, 20_000)

    snapshot = engine.snapshot()
    bucket = snapshot["anthropic:model"]["buckets"][0]
    assert bucket["sample_count"] == WEIGHT_CAP
    assert engine.calibrate("anthropic", "model", 10_000) == 20_000


def test_snapshot_round_trip_preserves_factors() -> None:
    engine = CalibrationEngine()
    engine.learn("anthropic", "model", 40_000, 50_000)

    restored = CalibrationEngine.from_snapshot(engine.snapshot())

    assert restored.calibrate("anthropic", "model", 40_000) == 50_000
