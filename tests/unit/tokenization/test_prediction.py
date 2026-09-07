from __future__ import annotations

import ast
import hashlib
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

import pytest

from app.tokenization.prediction import (
    build_prediction_record,
    evaluate,
    predict_exact_or_prefix,
)
from app.tokenization.scaling import finalize_local_prediction
from app.tokenization.types import (
    AnchorKind,
    EstimateFeatures,
    ExactAnchor,
    FeatureName,
    FeatureVector,
    FixedContextContribution,
    InputItemContribution,
    LearningIdentity,
    LearningSnapshot,
    LearningUpdate,
    NoPrefixCheckpointChange,
    PredictionCandidateKey,
    PredictionCandidateVariant,
    PredictionMethod,
    PrefixAnchor,
    PrefixFingerprint,
    ProfileKey,
    StoredSample,
    TokenComponent,
)


def _digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


IDENTITY = LearningIdentity(
    actual_provider="provider",
    resolved_model="model",
    endpoint="responses",
    wire_format="responses",
    tokenizer="o200k",
    descriptor_fingerprint=_digest("descriptor"),
    estimator_generation=1,
    profile_schema_revision=1,
    learning_epoch=0,
)
PROFILE = ProfileKey(
    item_kinds=("message",),
    reasoning_origins=(),
    media_kinds=(),
    unknown_type_digests=(),
    unknown_type_count=0,
    unknown_type_overflow=False,
    has_previous_response_id=False,
    context_management_mode="none",
    truncation_mode="none",
)
COLD = PredictionCandidateKey(PredictionMethod.COLD_START, PredictionCandidateVariant.DETERMINISTIC)
EXACT = PredictionCandidateKey(PredictionMethod.HISTORY_EXACT, PredictionCandidateVariant.MEDIAN)
PREFIX = PredictionCandidateKey(
    PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.DETERMINISTIC
)


def _item(known_visible: int, visual: int | None, prior: float = 0.0) -> InputItemContribution:
    return InputItemContribution(known_visible, 4, 0, visual, prior)


def _features(
    *,
    name: str = "query",
    fixed: FixedContextContribution | None = None,
    items: tuple[InputItemContribution, ...] = (),
    prefixes: tuple[str, ...] | None = None,
    reasons: tuple[str, ...] = (),
    context: str = "context",
) -> EstimateFeatures:
    fixed = fixed or FixedContextContribution(0, 0, 0.0)
    known = fixed.known_tokens + sum(item.known_tokens for item in items)
    visual = (
        None
        if any(item.capability_visual_tokens is None for item in items)
        else sum(item.capability_visual_tokens or 0 for item in items)
    )
    prefix_digests = prefixes if prefixes is not None else tuple(
        _digest(f"{name}-prefix-{index}") for index in range(1, len(items) + 1)
    )
    observations = {
        feature_name: (known if feature_name is FeatureName.KNOWN_TOTAL else 0)
        for feature_name in FeatureName
    }
    return EstimateFeatures(
        known_tokens=known,
        capability_visual_tokens=visual,
        components=(TokenComponent("known", known, 1),),
        profile_key=PROFILE,
        feature_vector=FeatureVector.from_observations(observations),
        full_fingerprint=_digest(f"{name}-full"),
        context_fingerprint=_digest(context),
        prefix_fingerprints=tuple(
            PrefixFingerprint(index, digest) for index, digest in enumerate(prefix_digests, start=1)
        ),
        low_confidence_reasons=reasons,
        estimator_generation=1,
        profile_schema_revision=1,
        fixed_context_contribution=fixed,
        input_item_contributions=items,
    )


def _sample(key: tuple[str, str, int], features: EstimateFeatures, actual: int = 100) -> StoredSample:
    return StoredSample(
        sample_key=key,
        identity=IDENTITY,
        features=features,
        actual_input_tokens=actual,
        raw_body_sha256=_digest(f"body-{key}"),
        observed_at_us=1,
        committed_order=1,
    )


def _snapshot(
    *, samples: tuple[StoredSample, ...] = (), exact: tuple[ExactAnchor, ...] = (),
    prefix: tuple[PrefixAnchor, ...] = (), revision: int = 7,
) -> LearningSnapshot:
    return LearningSnapshot(
        identity=IDENTITY,
        revision=revision,
        active_epoch=0,
        samples=samples,
        exact_anchors=exact,
        prefix_anchors=prefix,
    )


def _prefix_anchor(
    source: StoredSample, fingerprint: PrefixFingerprint, *, actual: int = 100, observed: int = 1,
    context: str = "context",
) -> PrefixAnchor:
    return PrefixAnchor(
        identity=IDENTITY,
        context_fingerprint=_digest(context),
        prefix_fingerprint=fingerprint,
        actual_tokens=actual,
        sample_key=source.sample_key,
        observed_at_us=observed,
    )


def test_t4a_c01_cold_exact_aggregate_and_visual_presence() -> None:
    fixed = FixedContextContribution(3, 4, 0.5)
    cases = (
        ((_item(2, None, 0.25), _item(5, 6, 0.75)), 23.5),
        ((_item(2, 0, 0.25), _item(5, 6, 0.75)), 29.5),
        ((_item(2, 3, 0.25), _item(5, 6, 0.75)), 32.5),
    )
    for items, expected in cases:
        decision = predict_exact_or_prefix(_features(fixed=fixed, items=items), _snapshot())
        assert decision.prediction.unscaled_tokens == expected
        assert decision.prediction.low_confidence_reasons == ()


def test_t4a_c02_exact_median_and_all_source_intent() -> None:
    features = _features(name="exact")
    source_keys = tuple(("boot", f"request-{index}", index) for index in range(4))
    samples = tuple(_sample(key, features) for key in source_keys)
    anchor = ExactAnchor(IDENTITY, features.full_fingerprint, (99, 100, 101, 102), source_keys)
    decision = predict_exact_or_prefix(features, _snapshot(samples=samples, exact=(anchor,)))
    assert decision.prediction.unscaled_tokens == 100.5
    assert decision.prediction.sample_count == 4
    assert decision.anchor_use_intent is not None
    assert decision.anchor_use_intent.kind is AnchorKind.EXACT
    assert decision.anchor_use_intent.source_sample_keys == source_keys


def test_t4a_c03_candidate_order_champions_and_cardinality() -> None:
    query = _features(name="query", items=(_item(1, 0), _item(2, 0)))
    source_features = _features(name="source", items=(_item(1, 0),), prefixes=(query.prefix_fingerprints[0].digest,))
    source = _sample(("boot", "source", 0), source_features)
    exact_source = _sample(("boot", "exact", 1), query)
    snapshot = _snapshot(
        samples=(source, exact_source),
        exact=(ExactAnchor(IDENTITY, query.full_fingerprint, (90,), (exact_source.sample_key,)),),
        prefix=(_prefix_anchor(source, query.prefix_fingerprints[0]),),
    )
    record = build_prediction_record(("boot", "current", 2), query, snapshot)
    assert tuple(candidate.candidate_key for candidate in record.candidates) == (EXACT, PREFIX, COLD)
    assert tuple(champion.method for champion in record.method_champions) == (
        PredictionMethod.HISTORY_EXACT, PredictionMethod.HISTORY_PREFIX, PredictionMethod.COLD_START
    )
    assert tuple(candidate.sample_count for candidate in record.candidates) == (1, 1, 0)
    assert record.selected_key == EXACT


def test_t4a_c04_exact_selection_keeps_prefix_challenger() -> None:
    query = _features(name="both", items=(_item(1, 0), _item(2, 0)))
    source = _sample(
        ("boot", "prefix", 0),
        _features(name="short", items=(_item(1, 0),), prefixes=(query.prefix_fingerprints[0].digest,)),
    )
    exact_source = _sample(("boot", "exact", 1), query)
    snapshot = _snapshot(
        samples=(source, exact_source),
        exact=(ExactAnchor(IDENTITY, query.full_fingerprint, (80,), (exact_source.sample_key,)),),
        prefix=(_prefix_anchor(source, query.prefix_fingerprints[0]),),
    )
    record = build_prediction_record(("boot", "new", 2), query, snapshot)
    decision = predict_exact_or_prefix(query, snapshot)
    assert tuple(candidate.candidate_key for candidate in record.candidates) == (EXACT, PREFIX, COLD)
    assert record.selected_key == EXACT
    assert decision.anchor_use_intent is not None
    assert decision.anchor_use_intent.kind is AnchorKind.EXACT


def test_t4a_c05_prefix_anchor_total_order_is_stable_across_snapshot_order() -> None:
    query = _features(name="tie", items=(_item(1, 0), _item(2, 0), _item(3, 0)))
    source_features = _features(
        name="source", items=(_item(1, 0), _item(2, 0)), prefixes=tuple(
            prefix.digest for prefix in query.prefix_fingerprints[:2]
        )
    )
    first = _sample(("z-boot", "z-request", 10), source_features)
    second = _sample(("a-boot", "a-request", 2), source_features)
    third = _sample(("a-boot", "a-request", 10), source_features)
    anchors = (
        _prefix_anchor(first, query.prefix_fingerprints[0], actual=10, observed=999),
        _prefix_anchor(first, query.prefix_fingerprints[1], actual=100, observed=1),
        _prefix_anchor(second, query.prefix_fingerprints[1], actual=120, observed=2),
        _prefix_anchor(third, query.prefix_fingerprints[1], actual=130, observed=2),
    )
    forward = predict_exact_or_prefix(query, _snapshot(samples=(first, second, third), prefix=anchors))
    reverse = predict_exact_or_prefix(
        query, _snapshot(samples=(first, second, third), prefix=tuple(reversed(anchors)))
    )
    assert forward.prediction.unscaled_tokens == 127
    assert forward.anchor_use_intent is not None
    assert forward.anchor_use_intent.source_sample_keys == (second.sample_key,)
    assert reverse.prediction == forward.prediction
    assert reverse.anchor_use_intent == forward.anchor_use_intent


def test_t4a_c06_strict_prefix_only_allows_a_real_append() -> None:
    query = _features(name="strict", items=(_item(1, 0), _item(2, 0)))
    source = _sample(("boot", "source", 0), query)
    equal = _prefix_anchor(source, query.prefix_fingerprints[1])
    wrong_context = _prefix_anchor(source, query.prefix_fingerprints[0], context="other")
    wrong_digest = _prefix_anchor(
        source, PrefixFingerprint(1, _digest("wrong-prefix"))
    )
    decision = predict_exact_or_prefix(query, _snapshot(samples=(source,), prefix=(equal, wrong_context, wrong_digest)))
    assert decision.prediction.candidate_key == COLD
    proper = _prefix_anchor(source, query.prefix_fingerprints[0])
    assert predict_exact_or_prefix(query, _snapshot(samples=(source,), prefix=(proper,))).prediction.candidate_key == PREFIX


def test_t4a_c07_suffix_uses_only_appended_item_slice() -> None:
    query = _features(
        name="slice",
        fixed=FixedContextContribution(100, 4, 50),
        items=(_item(1, None, 8), _item(3, 6, 2)),
    )
    source = _sample(
        ("boot", "source", 0),
        _features(name="unrelated", fixed=FixedContextContribution(1, 0, 0), items=(_item(1, None),),
                  prefixes=(query.prefix_fingerprints[0].digest,)),
    )
    result = predict_exact_or_prefix(
        query, _snapshot(samples=(source,), prefix=(_prefix_anchor(source, query.prefix_fingerprints[0], actual=200),))
    )
    assert result.prediction.unscaled_tokens == 215


@pytest.mark.parametrize(
    ("old_visual", "new_visual", "expected_delta"),
    [(None, None, 6), (None, 7, 13), (0, 7, 13), (7, None, 6)],
)
def test_t4a_c08_each_appended_item_visual_transition(
    old_visual: int | None, new_visual: int | None, expected_delta: int
) -> None:
    query = _features(name=f"visual-{old_visual}-{new_visual}", items=(_item(1, old_visual), _item(1, new_visual, 1)))
    source = _sample(
        ("boot", f"source-{old_visual}-{new_visual}", 0),
        _features(name="source", items=(_item(1, old_visual),), prefixes=(query.prefix_fingerprints[0].digest,)),
    )
    decision = predict_exact_or_prefix(
        query, _snapshot(samples=(source,), prefix=(_prefix_anchor(source, query.prefix_fingerprints[0], actual=100),))
    )
    assert decision.prediction.unscaled_tokens == 100 + expected_delta


def test_t4a_c09_prequential_record_rejects_current_sample_already_in_snapshot() -> None:
    features = _features(name="prequential")
    key = ("boot", "current", 0)
    sample = _sample(key, features)
    with pytest.raises(ValueError, match="current sample key"):
        build_prediction_record(key, features, _snapshot(samples=(sample,)))
    record = build_prediction_record(key, features, _snapshot())
    assert evaluate(record, 0)[0].actual_tokens == 0


def test_t4a_c10_actual_zero_produces_absolute_error_only_in_candidate_order() -> None:
    features = _features(name="zero")
    record = build_prediction_record(("boot", "zero", 0), features, _snapshot())
    evaluations = evaluate(record, 0)
    assert tuple(evaluation.candidate_key for evaluation in evaluations) == (COLD,)
    assert evaluations[0].absolute_error == abs(record.candidates[0].unscaled_tokens)
    assert evaluations[0].signed_relative_error is None
    assert evaluations[0].absolute_percentage_error is None
    with pytest.raises(ValueError):
        evaluate(record, True)


@pytest.mark.parametrize(
    ("value", "multiplier"),
    [(100.5, 1.0), (100.5, 1.1), (100.1, 1.1), (-5, 1.1), (0, 1.5), (10**30 + 1, 1.1)],
)
def test_t4a_c11_finalization_decimal_multiply_then_ceiling(value: int | float, multiplier: float) -> None:
    expected = max(
        1,
        int((Decimal(str(value)) * Decimal(str(multiplier))).to_integral_value(rounding=ROUND_CEILING)),
    )
    assert finalize_local_prediction(value, multiplier) == expected


def test_t4a_c12_wrapper_delegates_once_and_zero_is_now_one(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.tokenization.scaling as scaling

    calls: list[tuple[int | float, float]] = []

    def fake_finalizer(value: int | float, multiplier: float) -> int:
        calls.append((value, multiplier))
        return 17

    monkeypatch.setattr(scaling, "finalize_local_prediction", fake_finalizer)
    assert scaling.scale_local_estimate(0, 1.5) == 17
    assert calls == [(0, 1.5)]


def test_t4a_c13_producer_invariants_are_actual_output_facts() -> None:
    features = _features(name="producer", items=(_item(1, 0), _item(2, 0)))
    source = _sample(
        ("boot", "producer-prefix", 0),
        _features(
            name="producer-source",
            items=(_item(1, 0),),
            prefixes=(features.prefix_fingerprints[0].digest,),
        ),
    )
    exact_source = _sample(("boot", "producer-exact", 1), features)
    record = build_prediction_record(
        ("boot", "producer", 2),
        features,
        _snapshot(
            samples=(source, exact_source),
            exact=(ExactAnchor(IDENTITY, features.full_fingerprint, (90,), (exact_source.sample_key,)),),
            prefix=(_prefix_anchor(source, features.prefix_fingerprints[0]),),
        ),
    )
    assert tuple(candidate.candidate_key for candidate in record.candidates) == (EXACT, PREFIX, COLD)
    assert tuple((champion.method, champion.eligible_for_selection) for champion in record.method_champions) == (
        (PredictionMethod.HISTORY_EXACT, True),
        (PredictionMethod.HISTORY_PREFIX, True),
        (PredictionMethod.COLD_START, True),
    )
    assert record.selected_key == EXACT


def test_t4a_c14_no_checkpoint_transition_or_forbidden_predictor_import() -> None:
    features = _features(name="seam")
    key = ("boot", "seam", 0)
    record = build_prediction_record(key, features, _snapshot())
    sample = _sample(key, features, actual=10)
    update = LearningUpdate(sample, record, evaluate(record, 10), NoPrefixCheckpointChange())
    assert type(update.prefix_checkpoint_command) is NoPrefixCheckpointChange
    source = Path(__file__).parents[3] / "src/app/tokenization/prediction.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    forbidden = {"ReplacePrefixCheckpoint", "DeleteRecoveredPrefixCheckpoint"}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert forbidden.isdisjoint(names | imported)
