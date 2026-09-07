from __future__ import annotations

import ast
import hashlib
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

import pytest

from app.tokenization.prediction import (
    PrefixPairIndex,
    build_prediction_record,
    build_prefix_pair_index,
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
    MethodChampion,
    NoPrefixCheckpointChange,
    PredictionCandidateKey,
    PredictionCandidateVariant,
    PredictionMethod,
    PredictionRecord,
    PrefixAnchor,
    PrefixFingerprint,
    ProfileKey,
    StoredSample,
    TokenComponent,
    TokenPrediction,
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
PROFILE_B = ProfileKey(
    item_kinds=("function",),
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
    profile: ProfileKey = PROFILE,
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
        profile_key=profile,
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


def _sample(
    key: tuple[str, str, int],
    features: EstimateFeatures,
    actual: int = 100,
    *,
    observed: int = 1,
    committed_order: int | None = None,
) -> StoredSample:
    order = committed_order
    if order is None:
        order = int.from_bytes(hashlib.sha256(repr(key).encode()).digest()[:8], "big") + 1
    return StoredSample(
        sample_key=key,
        identity=IDENTITY,
        features=features,
        actual_input_tokens=actual,
        raw_body_sha256=_digest(f"body-{key}"),
        observed_at_us=observed,
        committed_order=order,
    )


def _snapshot(
    *, samples: tuple[StoredSample, ...] = (), exact: tuple[ExactAnchor, ...] = (),
    prefix: tuple[PrefixAnchor, ...] = (), revision: int = 7,
    records: tuple[PredictionRecord, ...] = (),
) -> LearningSnapshot:
    return LearningSnapshot(
        identity=IDENTITY,
        revision=revision,
        active_epoch=0,
        samples=samples,
        exact_anchors=exact,
        prefix_anchors=prefix,
        prediction_records=records,
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


ADDITIVE = PredictionCandidateKey(
    PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.ADDITIVE
)
MULTIPLICATIVE = PredictionCandidateKey(
    PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.MULTIPLICATIVE
)


def _prediction(
    key: PredictionCandidateKey, value: float, *, profile: ProfileKey = PROFILE
) -> TokenPrediction:
    return TokenPrediction(
        identity=IDENTITY,
        profile_key=profile,
        method=key.method,
        candidate_key=key,
        unscaled_tokens=value,
        sample_count=1,
        history_revision=7,
        learning_epoch=0,
    )


def _prefix_record(
    sample: StoredSample,
    deterministic: float,
    additive: float | None = None,
    multiplicative: float | None = None,
) -> PredictionRecord:
    candidates = [_prediction(PREFIX, deterministic, profile=sample.features.profile_key)]
    if additive is not None:
        candidates.append(_prediction(ADDITIVE, additive, profile=sample.features.profile_key))
    if multiplicative is not None:
        candidates.append(
            _prediction(MULTIPLICATIVE, multiplicative, profile=sample.features.profile_key)
        )
    candidates.append(_prediction(COLD, 1, profile=sample.features.profile_key))
    return PredictionRecord(
        sample.sample_key,
        PREFIX,
        tuple(candidates),
        (
            MethodChampion(PREFIX, True),
            MethodChampion(COLD, True),
        ),
    )


def _history_pair(
    number: int,
    *,
    profile: ProfileKey = PROFILE,
    base_profile: ProfileKey | None = None,
    baseline_item: InputItemContribution | None = None,
    context: str = "pair-context",
    actual_delta: int | None = None,
) -> tuple[StoredSample, StoredSample, PrefixFingerprint]:
    baseline_item = baseline_item or InputItemContribution(1, 4, 0, 2, 3)
    first_digest = _digest(f"{context}-first")
    second_digest = _digest(f"{context}-second-{number}")
    base = _sample(
        ("base", f"{context}-{number}", 0),
        _features(
            name=f"base-{context}-{number}",
            context=context,
            profile=base_profile or profile,
            items=(_item(1, None),),
            prefixes=(first_digest,),
        ),
        actual=100,
        observed=number * 2,
        committed_order=number * 2,
    )
    longer = _sample(
        ("longer", f"{context}-{number}", 0),
        _features(
            name=f"longer-{context}-{number}",
            context=context,
            profile=profile,
            items=(_item(1, None), baseline_item),
            prefixes=(first_digest, second_digest),
        ),
        actual=100
        + (
            actual_delta
            if actual_delta is not None
            else int(
                baseline_item.known_tokens
                + (baseline_item.capability_visual_tokens or 0)
                + baseline_item.prior_residual_tokens
            )
        ),
        observed=number * 2 + 1,
        committed_order=number * 2 + 1,
    )
    return base, longer, PrefixFingerprint(1, first_digest)


def _snapshot_with_pairs(
    pairs: tuple[tuple[StoredSample, StoredSample, PrefixFingerprint], ...],
    *,
    records: tuple[PredictionRecord, ...] = (),
    record_samples: tuple[StoredSample, ...] = (),
    exact: tuple[ExactAnchor, ...] = (),
    revision: int = 7,
) -> LearningSnapshot:
    samples = tuple(sample for pair in pairs for sample in pair[:2]) + record_samples
    return _snapshot(
        samples=samples,
        exact=exact,
        revision=revision,
        records=records,
    )


def test_t4bp_c01_committed_order_is_canonical_and_strict() -> None:
    base, longer, _ = _history_pair(1)
    forward = build_prefix_pair_index(_snapshot(samples=(base, longer)))
    reverse = build_prefix_pair_index(_snapshot(samples=(longer, base)))
    assert tuple((pair.base.sample_key, pair.longer.sample_key) for pair in forward.pairs) == (
        (base.sample_key, longer.sample_key),
    )
    assert reverse == forward

    future_base = _sample(
        ("future", "base", 0),
        base.features,
        actual=100,
        committed_order=3,
    )
    earlier_longer = _sample(
        ("earlier", "longer", 0),
        longer.features,
        actual=110,
        committed_order=2,
    )
    assert build_prefix_pair_index(_snapshot(samples=(future_base, earlier_longer))).pairs == ()
    duplicate = _sample(
        ("duplicate", "base", 0), base.features, actual=100, committed_order=base.committed_order
    )
    with pytest.raises(ValueError, match="committed orders must be unique"):
        build_prefix_pair_index(_snapshot(samples=(base, duplicate)))


def test_t4bp_c02_selects_one_canonical_base() -> None:
    first = _digest("canonical-first")
    second = _digest("canonical-second")
    third = _digest("canonical-third")
    short = _sample(
        ("z", "short", 0),
        _features(items=(_item(1, 0),), prefixes=(first,), context="canonical"),
        actual=100,
        observed=999,
        committed_order=1,
    )
    older_long = _sample(
        ("z", "older", 0),
        _features(
            items=(_item(1, 0), _item(1, 0)),
            prefixes=(first, second),
            context="canonical",
        ),
        actual=110,
        observed=1,
        committed_order=2,
    )
    preferred_long = _sample(
        ("a", "preferred", 10),
        _features(
            items=(_item(1, 0), _item(1, 0)),
            prefixes=(first, second),
            context="canonical",
        ),
        actual=120,
        observed=2,
        committed_order=3,
    )
    binary_loser = _sample(
        ("z", "preferred", 0),
        _features(
            items=(_item(1, 0), _item(1, 0)),
            prefixes=(first, second),
            context="canonical",
        ),
        actual=120,
        observed=2,
        committed_order=4,
    )
    numeric_winner = _sample(
        ("a", "preferred", 2),
        _features(
            items=(_item(1, 0), _item(1, 0)),
            prefixes=(first, second),
            context="canonical",
        ),
        actual=120,
        observed=2,
        committed_order=5,
    )
    longer = _sample(
        ("longer", "target", 0),
        _features(
            items=(_item(1, 0), _item(1, 0), _item(1, 0)),
            prefixes=(first, second, third),
            context="canonical",
        ),
        actual=130,
        committed_order=6,
    )
    index = build_prefix_pair_index(
        _snapshot(samples=(longer, short, older_long, preferred_long, binary_loser, numeric_winner))
    )
    target_pairs = [pair for pair in index.pairs if pair.longer == longer]
    assert len(target_pairs) == 1
    assert target_pairs[0].base.sample_key == numeric_winner.sample_key


def test_t4bp_c03_profile_filter_index_binding_and_record_mismatch() -> None:
    pairs = (
        *(_history_pair(number, base_profile=PROFILE_B) for number in range(1, 4)),
        _history_pair(4, profile=PROFILE_B),
    )
    query_items = (_item(1, None), _item(1, 2, 3))
    query = _features(
        name="profile-query",
        items=query_items,
        prefixes=(pairs[0][2].digest, _digest("profile-query-second")),
        context="pair-context",
    )
    anchor = _prefix_anchor(pairs[0][0], query.prefix_fingerprints[0], actual=100, context="pair-context")
    snapshot = _snapshot_with_pairs(pairs)
    prediction_snapshot = _snapshot(
        samples=snapshot.samples,
        prefix=(anchor,),
    )
    record = build_prediction_record(
        ("current", "profile", 0),
        query,
        prediction_snapshot,
    )
    assert tuple(candidate.candidate_key for candidate in record.candidates) == (
        PREFIX,
        ADDITIVE,
        MULTIPLICATIVE,
        COLD,
    )
    assert tuple(candidate.sample_count for candidate in record.candidates) == (1, 3, 3, 0)

    index = build_prefix_pair_index(snapshot)
    with pytest.raises(ValueError, match="prefix pair index"):
        predict_exact_or_prefix(
            query,
            _snapshot(samples=snapshot.samples, revision=8),
            prefix_pair_index=index,
        )
    with pytest.raises(ValueError, match="prefix pair index"):
        predict_exact_or_prefix(
            query,
            prediction_snapshot,
            prefix_pair_index=PrefixPairIndex(IDENTITY, 1, 7, index.pairs),
        )
    wrong_identity = LearningIdentity(
        actual_provider="other-provider",
        resolved_model=IDENTITY.resolved_model,
        endpoint=IDENTITY.endpoint,
        wire_format=IDENTITY.wire_format,
        tokenizer=IDENTITY.tokenizer,
        descriptor_fingerprint=IDENTITY.descriptor_fingerprint,
        estimator_generation=IDENTITY.estimator_generation,
        profile_schema_revision=IDENTITY.profile_schema_revision,
        learning_epoch=IDENTITY.learning_epoch,
    )
    with pytest.raises(ValueError, match="prefix pair index"):
        predict_exact_or_prefix(
            query,
            prediction_snapshot,
            prefix_pair_index=PrefixPairIndex(wrong_identity, 0, 7, index.pairs),
        )

    mismatched_sample = _sample(
        ("record", "mismatch", 0),
        _features(profile=PROFILE),
        actual=10,
        committed_order=100,
    )
    mismatched_record = _prefix_record(mismatched_sample, 10)
    mismatched_record = PredictionRecord(
        mismatched_record.sample_key,
        mismatched_record.selected_key,
        tuple(
            _prediction(candidate.candidate_key, candidate.unscaled_tokens, profile=PROFILE_B)
            for candidate in mismatched_record.candidates
        ),
        mismatched_record.method_champions,
    )
    mismatch_snapshot = _snapshot(
        samples=(*snapshot.samples, mismatched_sample),
        prefix=(anchor,),
        records=(mismatched_record,),
    )
    with pytest.raises(ValueError, match="profile key"):
        predict_exact_or_prefix(query, mismatch_snapshot)


def test_t4bp_c04_full_historical_baseline_includes_known_visual_and_prior() -> None:
    pairs = tuple(_history_pair(number) for number in range(1, 4))
    first_prefix = pairs[0][2]
    query = _features(
        name="full-baseline-query",
        context="pair-context",
        items=(
            _item(1, None),
            InputItemContribution(1, 4, 0, 2, 3),
        ),
        prefixes=(first_prefix.digest, _digest("full-baseline-query-second")),
    )
    anchor = _prefix_anchor(pairs[0][0], first_prefix, actual=100, context="pair-context")
    record = build_prediction_record(
        ("current", "full-baseline", 0),
        query,
        _snapshot(samples=tuple(sample for pair in pairs for sample in pair[:2]), prefix=(anchor,)),
    )
    values = {candidate.candidate_key: candidate for candidate in record.candidates}
    assert values[PREFIX].unscaled_tokens == 110
    assert values[ADDITIVE].unscaled_tokens == 110
    assert values[MULTIPLICATIVE].unscaled_tokens == 110
    assert values[ADDITIVE].sample_count == 3
    assert values[MULTIPLICATIVE].sample_count == 3


@pytest.mark.parametrize(
    ("old_visual", "new_visual", "expected"),
    [(None, None, 6), (None, 7, 13), (0, 7, 13), (7, None, 6)],
)
def test_t4bp_c05_historical_suffix_uses_each_appended_visual_value(
    old_visual: int | None, new_visual: int | None, expected: int
) -> None:
    first = _digest(f"historical-visual-{old_visual}-{new_visual}-first")
    second = _digest(f"historical-visual-{old_visual}-{new_visual}-second")
    base = _sample(
        ("visual", "base", 0),
        _features(
            context="historical-visual",
            items=(_item(1, old_visual),),
            prefixes=(first,),
        ),
        actual=100,
        committed_order=1,
    )
    longer = _sample(
        ("visual", "longer", 0),
        _features(
            context="historical-visual",
            items=(_item(1, old_visual), _item(1, new_visual, 1)),
            prefixes=(first, second),
        ),
        actual=100 + expected,
        committed_order=2,
    )
    pair = build_prefix_pair_index(_snapshot(samples=(longer, base))).pairs[0]
    assert pair.suffix_baseline_delta == expected


def test_t4bp_c06_thresholds_and_current_zero_multiplicative() -> None:
    two_pairs = tuple(_history_pair(number) for number in range(1, 3))
    first_prefix = two_pairs[0][2]
    query = _features(
        context="pair-context",
        items=(_item(1, None), InputItemContribution(0, 4, 0, 0, -4)),
        prefixes=(first_prefix.digest, _digest("zero-current-second")),
    )
    anchor = _prefix_anchor(two_pairs[0][0], first_prefix, actual=100, context="pair-context")
    two_snapshot = _snapshot(
        samples=tuple(sample for pair in two_pairs for sample in pair[:2]),
        prefix=(anchor,),
    )
    assert tuple(
        candidate.candidate_key
        for candidate in build_prediction_record(("current", "two", 0), query, two_snapshot).candidates
    ) == (PREFIX, COLD)

    three_pairs = (
        *two_pairs,
        _history_pair(3),
        _history_pair(
            4,
            baseline_item=InputItemContribution(0, 4, 0, 0, -4),
            actual_delta=2,
        ),
    )
    three_snapshot = _snapshot(
        samples=tuple(sample for pair in three_pairs for sample in pair[:2]),
        prefix=(anchor,),
    )
    values = {
        candidate.candidate_key: candidate
        for candidate in build_prediction_record(("current", "three", 0), query, three_snapshot).candidates
    }
    assert values[MULTIPLICATIVE].unscaled_tokens == 100
    assert values[MULTIPLICATIVE].sample_count == 3
    assert values[ADDITIVE].sample_count == 4


def _record_samples_and_records(
    count: int,
    *,
    deterministic: float,
    additive: float | None,
    multiplicative: float | None,
    observed_start: int = 1000,
) -> tuple[tuple[StoredSample, ...], tuple[PredictionRecord, ...]]:
    samples = tuple(
        _sample(
            ("record", f"{observed_start}-{number}", 0),
            _features(name=f"record-{observed_start}-{number}"),
            actual=100,
            observed=observed_start + number,
            committed_order=observed_start + number,
        )
        for number in range(count)
    )
    return samples, tuple(
        _prefix_record(sample, deterministic, additive, multiplicative) for sample in samples
    )


def _learned_query_and_history() -> tuple[
    tuple[tuple[StoredSample, StoredSample, PrefixFingerprint], ...],
    EstimateFeatures,
    PrefixAnchor,
]:
    pairs = tuple(_history_pair(number) for number in range(1, 4))
    first_prefix = pairs[0][2]
    query = _features(
        name="learned-query",
        context="pair-context",
        items=(_item(1, None), InputItemContribution(1, 4, 0, 2, 3)),
        prefixes=(first_prefix.digest, _digest("learned-query-second")),
    )
    return (
        pairs,
        query,
        _prefix_anchor(pairs[0][0], first_prefix, actual=100, context="pair-context"),
    )


def test_t4bp_c07_exact_keeps_all_learned_prefix_variants_and_champion() -> None:
    pairs, query, anchor = _learned_query_and_history()
    record_samples, records = _record_samples_and_records(
        8, deterministic=150, additive=100, multiplicative=100
    )
    exact_sample = _sample(
        ("exact", "learned", 0), query, actual=80, committed_order=99
    )
    snapshot = _snapshot(
        samples=tuple(sample for pair in pairs for sample in pair[:2])
        + record_samples
        + (exact_sample,),
        exact=(ExactAnchor(IDENTITY, query.full_fingerprint, (80,), (exact_sample.sample_key,)),),
        prefix=(anchor,),
        records=records,
    )
    record = build_prediction_record(("current", "all-variants", 0), query, snapshot)
    decision = predict_exact_or_prefix(query, snapshot)
    assert tuple(candidate.candidate_key for candidate in record.candidates) == (
        EXACT,
        PREFIX,
        ADDITIVE,
        MULTIPLICATIVE,
        COLD,
    )
    assert tuple(candidate.sample_count for candidate in record.candidates) == (1, 1, 3, 3, 0)
    assert tuple(champion.candidate_key for champion in record.method_champions) == (
        EXACT,
        ADDITIVE,
        COLD,
    )
    assert record.selected_key == EXACT
    assert decision.anchor_use_intent is not None
    assert decision.anchor_use_intent.kind is AnchorKind.EXACT


def test_t4bp_c08_minimum_eight_strict_improvement_and_ties() -> None:
    pairs, query, anchor = _learned_query_and_history()
    seven_samples, seven_records = _record_samples_and_records(
        7, deterministic=150, additive=100, multiplicative=90
    )
    seven_snapshot = _snapshot(
        samples=tuple(sample for pair in pairs for sample in pair[:2]) + seven_samples,
        prefix=(anchor,),
        records=seven_records,
    )
    assert build_prediction_record(("current", "seven", 0), query, seven_snapshot).selected_key == PREFIX

    tie_samples, tie_records = _record_samples_and_records(
        8, deterministic=100, additive=100, multiplicative=100
    )
    tie_snapshot = _snapshot(
        samples=tuple(sample for pair in pairs for sample in pair[:2]) + tie_samples,
        prefix=(anchor,),
        records=tie_records,
    )
    assert build_prediction_record(("current", "tie", 0), query, tie_snapshot).selected_key == PREFIX

    learned_samples, learned_records = _record_samples_and_records(
        8, deterministic=150, additive=100, multiplicative=100
    )
    learned_snapshot = _snapshot(
        samples=tuple(sample for pair in pairs for sample in pair[:2]) + learned_samples,
        prefix=(anchor,),
        records=learned_records,
    )
    assert build_prediction_record(("current", "learned", 0), query, learned_snapshot).selected_key == ADDITIVE


def test_t4bp_c09_newest_thirty_one_and_c10_empty_diagnostics() -> None:
    pairs, query, anchor = _learned_query_and_history()
    older_samples, older_records = _record_samples_and_records(
        32, deterministic=150, additive=100, multiplicative=150, observed_start=1000
    )
    newer_samples, newer_records = _record_samples_and_records(
        31, deterministic=100, additive=150, multiplicative=150, observed_start=2000
    )
    snapshot = _snapshot(
        samples=tuple(sample for pair in pairs for sample in pair[:2])
        + older_samples
        + newer_samples,
        prefix=(anchor,),
        records=older_records + newer_records,
    )
    reversed_snapshot = _snapshot(
        samples=tuple(reversed(snapshot.samples)),
        prefix=(anchor,),
        records=tuple(reversed(snapshot.prediction_records)),
    )
    assert snapshot.evaluations == ()
    assert build_prediction_record(("current", "newest", 0), query, snapshot).selected_key == PREFIX
    assert (
        build_prediction_record(("current", "newest-reversed", 0), query, reversed_snapshot).selected_key
        == PREFIX
    )


def test_t4bp_c10_diagnostics_are_not_variant_selection_evidence() -> None:
    pairs, query, anchor = _learned_query_and_history()
    samples, records = _record_samples_and_records(
        8, deterministic=150, additive=100, multiplicative=100
    )
    snapshot = _snapshot(
        samples=tuple(sample for pair in pairs for sample in pair[:2]) + samples,
        prefix=(anchor,),
        records=records,
    )
    assert snapshot.evaluations == ()
    assert build_prediction_record(("current", "no-diagnostics", 0), query, snapshot).selected_key == ADDITIVE


def test_t4bp_c11_uses_the_all_current_variant_common_window() -> None:
    pairs, query, anchor = _learned_query_and_history()
    partial_samples, partial_records = _record_samples_and_records(
        9, deterministic=150, additive=100, multiplicative=None, observed_start=1000
    )
    common_samples, common_records = _record_samples_and_records(
        8, deterministic=100, additive=150, multiplicative=100, observed_start=2000
    )
    snapshot = _snapshot(
        samples=tuple(sample for pair in pairs for sample in pair[:2])
        + partial_samples
        + common_samples,
        prefix=(anchor,),
        records=partial_records + common_records,
    )
    assert build_prediction_record(("current", "common-window", 0), query, snapshot).selected_key == PREFIX
