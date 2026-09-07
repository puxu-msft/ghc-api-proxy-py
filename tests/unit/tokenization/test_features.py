import hashlib
import json
import pickle
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

import pytest
import tiktoken

from app.tokenization.estimators import estimate_responses_input
from app.tokenization.features import (
    MEDIA_REASON,
    OPAQUE_BYTES_REASON,
    OPAQUE_ITEMS_REASON,
    PDF_REASON,
    UNKNOWN_BYTES_REASON,
    UNKNOWN_ITEMS_REASON,
    analyze_responses_input,
)
from app.tokenization.types import (
    AnchorKind,
    AnchorUseIntent,
    AnchorUseOutcome,
    EstimateFeatures,
    FeatureName,
    FeatureValue,
    FeatureVector,
    LearningIdentity,
    LearningReasonCode,
    LearningSnapshot,
    LearningUpdate,
    MethodChampion,
    NoPrefixCheckpointChange,
    PredictionCandidateKey,
    PredictionCandidateVariant,
    PredictionDecision,
    PredictionEvaluation,
    PredictionMethod,
    PredictionRecord,
    ProfileKey,
    SampleCommittedMetadata,
    SentRequestSnapshot,
    StoreCancellationPhase,
    StoredSample,
    StructuralProfile,
    SyntheticUnresizedPatchGridFormula,
    TokenizationCapabilities,
    TokenLearningObservation,
    TokenPrediction,
    VisualTokenFormulaKind,
)

ENCODING = "o200k_base"
SPECIAL_SPELLINGS = sorted(tiktoken.get_encoding(ENCODING).special_tokens_set)


def ordinary(text: str) -> int:
    return len(tiktoken.get_encoding(ENCODING).encode(text, disallowed_special=()))


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def component_tokens(payload: Mapping[str, Any]) -> dict[str, int]:
    return {component.kind: component.tokens for component in analyze_responses_input(payload).components}


def feature(payload: Mapping[str, Any], name: FeatureName) -> FeatureValue:
    return analyze_responses_input(payload).feature_vector.get(name)


def test_canonical_identity_ignores_key_order_and_stream_only() -> None:
    first = {
        "model": "gpt-model",
        "stream": True,
        "input": [{"type": "message", "role": "user", "content": "hello"}],
        "metadata": {"z": 1, "a": 2},
    }
    reordered = {
        "metadata": {"a": 2, "z": 1},
        "input": [{"content": "hello", "role": "user", "type": "message"}],
        "stream": False,
        "model": "gpt-model",
    }

    first_features = analyze_responses_input(first)
    reordered_features = analyze_responses_input(reordered)

    assert first_features.full_fingerprint == reordered_features.full_fingerprint
    assert first_features.context_fingerprint == reordered_features.context_fingerprint
    assert first_features.prefix_fingerprints == reordered_features.prefix_fingerprints


def test_unknown_top_level_fields_change_full_and_context_identity() -> None:
    baseline: dict[str, Any] = {
        "model": "gpt-model",
        "input": [],
        "future_option": {"value": 1},
    }
    changed: dict[str, Any] = {
        "model": "gpt-model",
        "input": [],
        "future_option": {"value": 2},
    }

    before = analyze_responses_input(baseline)
    after = analyze_responses_input(changed)

    assert before.full_fingerprint != after.full_fingerprint
    assert before.context_fingerprint != after.context_fingerprint
    assert before.known_tokens == after.known_tokens == 0
    assert before.feature_vector.get(FeatureName.UNKNOWN_JSON_BYTES).present


def test_input_changes_full_identity_but_not_context_identity() -> None:
    baseline = {"model": "gpt-model", "instructions": "same", "input": ["first"]}
    changed = {"model": "gpt-model", "instructions": "same", "input": ["second"]}

    before = analyze_responses_input(baseline)
    after = analyze_responses_input(changed)

    assert before.full_fingerprint != after.full_fingerprint
    assert before.context_fingerprint == after.context_fingerprint


@pytest.mark.parametrize(
    ("before_value", "after_value"),
    [
        ({"instructions": "first"}, {"instructions": "second"}),
        (
            {"tools": [{"type": "function", "name": "first"}]},
            {"tools": [{"type": "function", "name": "second"}]},
        ),
    ],
)
def test_token_context_fields_change_full_and_context_identity(
    before_value: dict[str, Any],
    after_value: dict[str, Any],
) -> None:
    before = analyze_responses_input({"model": "gpt-model", "input": [], **before_value})
    after = analyze_responses_input({"model": "gpt-model", "input": [], **after_value})

    assert before.full_fingerprint != after.full_fingerprint
    assert before.context_fingerprint != after.context_fingerprint


def test_prefix_chain_preserves_order_and_every_previous_item() -> None:
    first = {"type": "message", "role": "user", "content": "first"}
    second = {"type": "message", "role": "assistant", "content": "second"}
    original = analyze_responses_input({"model": "gpt-model", "input": [first, second]})
    appended = analyze_responses_input({"model": "gpt-model", "input": [first, second, "third"]})
    reordered = analyze_responses_input({"model": "gpt-model", "input": [second, first]})
    changed_prefix = analyze_responses_input({"model": "gpt-model", "input": ["different", second]})

    assert tuple(prefix.item_count for prefix in original.prefix_fingerprints) == (1, 2)
    assert appended.prefix_fingerprints[:2] == original.prefix_fingerprints
    assert reordered.prefix_fingerprints != original.prefix_fingerprints
    assert changed_prefix.prefix_fingerprints[1] != original.prefix_fingerprints[1]


def test_item_contributions_exactly_reconstruct_known_and_visual_aggregates() -> None:
    capabilities = TokenizationCapabilities(
        visual_formula=SyntheticUnresizedPatchGridFormula(1, 28, 28)
    )
    features = analyze_responses_input(
        {
            "instructions": "fixed",
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "first"}]},
                {"type": "input_image", "width": 56, "height": 84},
            ],
        },
        capabilities=capabilities,
    )

    assert len(features.input_item_contributions) == len(features.prefix_fingerprints) == 2
    assert features.known_tokens == features.fixed_context_contribution.known_tokens + sum(
        item.known_tokens for item in features.input_item_contributions
    )
    assert features.capability_visual_tokens == sum(
        cast(int, item.capability_visual_tokens)
        for item in features.input_item_contributions
    ) == 6
    with pytest.raises(ValueError, match="known_tokens"):
        replace(features, input_item_contributions=features.input_item_contributions[:-1])


def test_compact_prefix_carriers_cover_788_items_with_pickle_safe_alignment() -> None:
    features = analyze_responses_input(
        {"input": [{"type": "message", "role": "user", "content": "x"}] * 788}
    )

    assert len(features.prefix_fingerprints) == len(features.input_item_contributions) == 788
    assert len(canonical([prefix.digest for prefix in features.prefix_fingerprints]).encode()) < 65_536
    assert len(
        canonical(
            [
                [
                    item.visible_tokens,
                    item.item_framing_tokens,
                    item.nested_framing_tokens,
                    item.capability_visual_tokens,
                    item.prior_residual_tokens,
                ]
                for item in features.input_item_contributions
            ]
        ).encode()
    ) < 65_536
    assert pickle.loads(pickle.dumps(features)) == features


def test_unknown_type_digests_are_sorted_bounded_and_do_not_retain_type_text() -> None:
    unknown_types = [f"future-{index}" for index in range(10)]
    payload = {
        "input": [
            *({"type": item_type, "payload": index} for index, item_type in enumerate(unknown_types)),
            {"type": unknown_types[0], "payload": "repeat"},
        ]
    }

    features = analyze_responses_input(payload)
    profile = features.profile_key
    expected = sorted(
        (hashlib.sha256(item_type.encode("utf-8")).hexdigest() for item_type in unknown_types),
        key=bytes.fromhex,
    )

    assert profile.unknown_type_digests == tuple(expected[:8])
    assert profile.unknown_type_count == 10
    assert profile.unknown_type_overflow is True
    assert features.feature_vector.get(FeatureName.UNKNOWN_ITEM_COUNT).value == 11
    assert all(item_type not in repr(profile) for item_type in unknown_types)


def test_feature_vector_requires_complete_enum_order_and_distinguishes_absence_from_zero() -> None:
    observed: dict[FeatureName, int | None] = {name: None for name in FeatureName}
    observed[FeatureName.KNOWN_TOTAL] = 0
    vector = FeatureVector.from_observations(observed)

    assert vector.get(FeatureName.KNOWN_TOTAL) == FeatureValue(FeatureName.KNOWN_TOTAL, True, 0)
    assert vector.get(FeatureName.MEDIA_DECODED_BYTES) == FeatureValue(
        FeatureName.MEDIA_DECODED_BYTES,
        False,
        0,
    )
    with pytest.raises(ValueError, match="every FeatureName"):
        FeatureVector(vector.values[:-1])
    with pytest.raises(ValueError, match="enum order"):
        FeatureVector(tuple(reversed(vector.values)))
    with pytest.raises(ValueError, match="neutral value zero"):
        FeatureValue(FeatureName.PDF_PAGES, False, 1)


def test_structured_features_are_pickle_safe() -> None:
    features = analyze_responses_input(
        {
            "model": "gpt-model",
            "input": [{"type": "reasoning", "summary": [], "encrypted_content": "opaque"}],
        }
    )

    assert pickle.loads(pickle.dumps(features)) == features
    profile = StructuralProfile(key=features.profile_key, features=features.feature_vector)
    assert pickle.loads(pickle.dumps(profile)) == profile


def _learning_identity(
    features: EstimateFeatures,
    *,
    actual_provider: str = "provider-a",
    estimator_generation: int | None = None,
    profile_schema_revision: int | None = None,
    learning_epoch: int = 3,
) -> LearningIdentity:
    return LearningIdentity(
        actual_provider=actual_provider,
        resolved_model="model-a",
        endpoint="responses",
        wire_format="openai-responses",
        tokenizer=ENCODING,
        descriptor_fingerprint=hashlib.sha256(b"descriptor").hexdigest(),
        estimator_generation=(
            features.estimator_generation
            if estimator_generation is None
            else estimator_generation
        ),
        profile_schema_revision=(
            features.profile_schema_revision
            if profile_schema_revision is None
            else profile_schema_revision
        ),
        learning_epoch=learning_epoch,
    )


def _default_variant(method: PredictionMethod) -> PredictionCandidateVariant:
    if method is PredictionMethod.HISTORY_EXACT:
        return PredictionCandidateVariant.MEDIAN
    if method in {PredictionMethod.HISTORY_PREFIX, PredictionMethod.COLD_START}:
        return PredictionCandidateVariant.DETERMINISTIC
    return PredictionCandidateVariant.ADDITIVE


def _prediction(
    features: EstimateFeatures,
    *,
    identity: LearningIdentity | None = None,
    profile_key: ProfileKey | None = None,
    method: PredictionMethod = PredictionMethod.COLD_START,
    variant: PredictionCandidateVariant | None = None,
    unscaled_tokens: float = 10.0,
    history_revision: int = 7,
    learning_epoch: int | None = None,
) -> TokenPrediction:
    selected_identity = identity or _learning_identity(features)
    candidate_key = PredictionCandidateKey(method, variant or _default_variant(method))
    return TokenPrediction(
        identity=selected_identity,
        profile_key=profile_key or features.profile_key,
        method=method,
        candidate_key=candidate_key,
        unscaled_tokens=unscaled_tokens,
        sample_count=0,
        history_revision=history_revision,
        learning_epoch=(
            selected_identity.learning_epoch if learning_epoch is None else learning_epoch
        ),
    )


def _record(
    sample_key: tuple[str, str, int],
    candidates: tuple[TokenPrediction, ...],
    *,
    selected_key: PredictionCandidateKey | None = None,
    eligibility: Mapping[PredictionMethod, bool] | None = None,
) -> PredictionRecord:
    candidate_by_method: dict[PredictionMethod, TokenPrediction] = {}
    for candidate in candidates:
        candidate_by_method.setdefault(candidate.method, candidate)
    champions = tuple(
        MethodChampion(
            candidate_by_method[method].candidate_key,
            True if eligibility is None else eligibility.get(method, True),
        )
        for method in PredictionMethod
        if method in candidate_by_method
    )
    chosen = selected_key or next(
        champion.candidate_key for champion in champions if champion.eligible_for_selection
    )
    return PredictionRecord(sample_key, chosen, candidates, champions)


def test_prediction_record_requires_selected_candidate_key_membership() -> None:
    features = analyze_responses_input({})
    candidate = _prediction(features)
    missing = PredictionCandidateKey(
        PredictionMethod.HISTORY_EXACT,
        PredictionCandidateVariant.MEDIAN,
    )

    with pytest.raises(ValueError, match="selected key"):
        PredictionRecord(
            sample_key=("boot", "request", 0),
            selected_key=missing,
            candidates=(candidate,),
            method_champions=(MethodChampion(candidate.candidate_key, True),),
        )


def test_prediction_record_rejects_cross_candidate_semantic_conflicts() -> None:
    features = analyze_responses_input({})
    selected = _prediction(features)
    identity = selected.identity
    profile_key = selected.profile_key

    conflicting_identity = _prediction(
        features,
        identity=replace(identity, actual_provider="provider-b"),
        method=PredictionMethod.HISTORY_EXACT,
    )
    with pytest.raises(ValueError, match="learning identity"):
        _record(("boot", "request", 0), (selected, conflicting_identity))

    conflicting_generation = _prediction(
        features,
        identity=replace(identity, estimator_generation=identity.estimator_generation + 1),
        method=PredictionMethod.HISTORY_EXACT,
    )
    with pytest.raises(ValueError, match="estimator generation"):
        _record(("boot", "request", 0), (selected, conflicting_generation))

    conflicting_schema = _prediction(
        features,
        identity=replace(identity, profile_schema_revision=identity.profile_schema_revision + 1),
        method=PredictionMethod.HISTORY_EXACT,
    )
    with pytest.raises(ValueError, match="profile schema revision"):
        _record(("boot", "request", 0), (selected, conflicting_schema))

    next_epoch_identity = replace(identity, learning_epoch=identity.learning_epoch + 1)
    conflicting_epoch = _prediction(
        features,
        identity=next_epoch_identity,
        method=PredictionMethod.HISTORY_EXACT,
    )
    with pytest.raises(ValueError, match="learning epoch"):
        _record(("boot", "request", 0), (selected, conflicting_epoch))

    conflicting_profile = _prediction(
        features,
        profile_key=replace(profile_key, truncation_mode="auto"),
        method=PredictionMethod.HISTORY_EXACT,
    )
    with pytest.raises(ValueError, match="profile key"):
        _record(("boot", "request", 0), (selected, conflicting_profile))

    conflicting_revision = _prediction(
        features,
        method=PredictionMethod.HISTORY_EXACT,
        history_revision=selected.history_revision + 1,
    )
    with pytest.raises(ValueError, match="history revision"):
        _record(("boot", "request", 0), (selected, conflicting_revision))

    with pytest.raises(ValueError, match="prediction epoch"):
        replace(selected, learning_epoch=selected.learning_epoch + 1)


def test_stored_sample_requires_feature_generation_and_schema_identity() -> None:
    features = analyze_responses_input({})
    identity = _learning_identity(features)

    def stored_sample(sample_identity: LearningIdentity) -> StoredSample:
        return StoredSample(
            sample_key=("boot", "request", 0),
            identity=sample_identity,
            features=features,
            actual_input_tokens=10,
            raw_body_sha256=hashlib.sha256(b"body").hexdigest(),
            observed_at_us=1_757_203_200_000_000,
        )

    with pytest.raises(ValueError, match="estimator generation"):
        stored_sample(replace(identity, estimator_generation=identity.estimator_generation + 1))
    with pytest.raises(ValueError, match="profile schema revision"):
        stored_sample(
            replace(
                identity,
                profile_schema_revision=identity.profile_schema_revision + 1,
            )
        )


def test_prediction_evaluation_rejects_impossible_error_metrics() -> None:
    valid = PredictionEvaluation(
        sample_key=("boot", "request", 0),
        method=PredictionMethod.COLD_START,
        candidate_key=PredictionCandidateKey(
            PredictionMethod.COLD_START,
            PredictionCandidateVariant.DETERMINISTIC,
        ),
        predicted_tokens=12.0,
        actual_tokens=10,
        absolute_error=2.0,
        signed_relative_error=0.2,
        absolute_percentage_error=0.2,
    )
    zero_actual = PredictionEvaluation(
        sample_key=("boot", "zero", 0),
        method=PredictionMethod.COLD_START,
        candidate_key=PredictionCandidateKey(
            PredictionMethod.COLD_START,
            PredictionCandidateVariant.DETERMINISTIC,
        ),
        predicted_tokens=5.0,
        actual_tokens=0,
        absolute_error=5.0,
        signed_relative_error=None,
        absolute_percentage_error=None,
    )

    with pytest.raises(ValueError, match="absolute prediction error"):
        replace(valid, absolute_error=1.0)
    with pytest.raises(ValueError, match="nonnegative"):
        replace(valid, absolute_percentage_error=-0.2)
    with pytest.raises(ValueError, match="require both"):
        replace(valid, signed_relative_error=None)
    with pytest.raises(ValueError, match="require both"):
        replace(valid, absolute_percentage_error=None)
    with pytest.raises(ValueError, match="signed_relative_error must match"):
        replace(valid, signed_relative_error=0.3)
    with pytest.raises(ValueError, match="absolute_percentage_error must match"):
        replace(valid, absolute_percentage_error=0.3)
    with pytest.raises(ValueError, match="must be absent"):
        replace(zero_actual, signed_relative_error=0.0, absolute_percentage_error=0.0)


def test_learning_snapshot_carries_bounded_prediction_history_with_identity_invariants() -> None:
    features = analyze_responses_input({})
    identity = _learning_identity(features)
    prediction = _prediction(features, identity=identity)
    record = _record(("boot", "request", 0), (prediction,))
    evaluation = PredictionEvaluation(
        sample_key=record.sample_key,
        method=prediction.method,
        candidate_key=prediction.candidate_key,
        predicted_tokens=prediction.unscaled_tokens,
        actual_tokens=10,
        absolute_error=0.0,
        signed_relative_error=0.0,
        absolute_percentage_error=0.0,
    )
    sample = StoredSample(
        sample_key=record.sample_key,
        identity=identity,
        features=features,
        actual_input_tokens=10,
        raw_body_sha256=hashlib.sha256(b"body").hexdigest(),
        observed_at_us=1_757_203_200_000_000,
    )
    _observation = TokenLearningObservation(
        sample_key=record.sample_key,
        outcome="committed",
        reason_code=LearningReasonCode.SAMPLE_COMMITTED,
        metadata=SampleCommittedMetadata(sample.actual_input_tokens),
        prefix_checkpoint_outcome=NoPrefixCheckpointChange(),
        evaluations=(evaluation,),
        revision=prediction.history_revision + 1,
        learning_epoch=identity.learning_epoch,
    )

    snapshot = LearningSnapshot(
        identity=identity,
        revision=prediction.history_revision,
        active_epoch=identity.learning_epoch,
        samples=(replace(sample, committed_order=1),),
        prediction_records=(record,),
        evaluations=(evaluation,),
    )
    update = LearningUpdate(sample, record, (evaluation,), NoPrefixCheckpointChange())

    assert snapshot.prediction_records == (record,)
    assert snapshot.evaluations == (evaluation,)
    assert update.prefix_checkpoint_command == NoPrefixCheckpointChange()
    with pytest.raises(ValueError, match="identity epoch"):
        replace(snapshot, active_epoch=identity.learning_epoch + 1)
    with pytest.raises(ValueError, match="prefix checkpoint command"):
        replace(update, prefix_checkpoint_command=cast(Any, None))


def test_learning_snapshot_rejects_evaluation_without_record_candidate() -> None:
    features = analyze_responses_input({})
    identity = _learning_identity(features)
    cold = _prediction(features, identity=identity)
    record = _record(("boot", "request", 0), (cold,))
    sample = StoredSample(
        sample_key=record.sample_key,
        identity=identity,
        features=features,
        actual_input_tokens=10,
        raw_body_sha256=hashlib.sha256(b"body").hexdigest(),
        observed_at_us=1_757_203_200_000_000,
    )
    extra_exact = PredictionEvaluation(
        sample_key=record.sample_key,
        method=PredictionMethod.HISTORY_EXACT,
        candidate_key=PredictionCandidateKey(
            PredictionMethod.HISTORY_EXACT,
            PredictionCandidateVariant.MEDIAN,
        ),
        predicted_tokens=10.0,
        actual_tokens=10,
        absolute_error=0.0,
        signed_relative_error=0.0,
        absolute_percentage_error=0.0,
    )

    with pytest.raises(ValueError, match="prediction record candidates"):
        LearningSnapshot(
            identity=identity,
            revision=cold.history_revision,
            active_epoch=identity.learning_epoch,
            samples=(replace(sample, committed_order=1),),
            prediction_records=(record,),
            evaluations=(extra_exact,),
        )


def test_anchor_use_intent_is_closed_immutable_and_epoch_bound() -> None:
    features = analyze_responses_input({})
    identity = _learning_identity(features)
    intent = AnchorUseIntent(
        kind=AnchorKind.EXACT,
        identity=identity,
        learning_epoch=identity.learning_epoch,
        fingerprint=features.full_fingerprint,
        source_sample_keys=(("boot", "request", 0),),
    )

    assert intent.source_sample_keys == (("boot", "request", 0),)
    assert tuple(AnchorUseOutcome) == (
        AnchorUseOutcome.RECORDED,
        AnchorUseOutcome.PRUNED,
    )
    assert StoreCancellationPhase.COMMIT.value == "commit"
    with pytest.raises(ValueError, match="epoch"):
        replace(intent, learning_epoch=identity.learning_epoch + 1)
    with pytest.raises(ValueError, match="exactly one"):
        replace(intent, kind=AnchorKind.PREFIX, source_sample_keys=(
            ("boot", "request", 0),
            ("boot", "request-2", 0),
        ))


def test_sent_request_snapshot_copies_mutable_body_before_hash_validation() -> None:
    source = bytearray(b"request body")
    expected_body = bytes(source)
    expected_hash = hashlib.sha256(expected_body).hexdigest()

    snapshot = SentRequestSnapshot(
        process_boot_id="boot",
        request_id="request",
        attempt_index=0,
        endpoint="responses",
        actual_provider="provider-a",
        resolved_model="model-a",
        wire_format="openai-responses",
        tokenizer=ENCODING,
        descriptor_fingerprint=hashlib.sha256(b"descriptor").hexdigest(),
        raw_body_sha256=expected_hash,
        body=cast(bytes, source),
    )
    source[:] = b"changed"

    assert type(snapshot.body) is bytes
    assert snapshot.body == expected_body
    assert snapshot.raw_body_sha256 == expected_hash
    assert hashlib.sha256(snapshot.body).hexdigest() == snapshot.raw_body_sha256


def test_known_components_and_framing_use_independent_literal_arithmetic() -> None:
    tool = {"type": "function", "name": "lookup", "parameters": {"type": "object"}}
    output = {"answer": 42, "ok": True}
    payload = {
        "instructions": "be brief",
        "tools": [tool],
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            },
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "lookup",
                "arguments": '{"query":"answer"}',
            },
            {"type": "function_call_output", "call_id": "call-1", "output": output},
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "visible summary"}],
            },
        ],
    }
    expected = {
        "framing": 4 + 4 + 4 + 4 * 4 + 4 + 4,
        "function_call": ordinary("call-1") + ordinary("lookup") + ordinary('{"query":"answer"}'),
        "function_output": ordinary("call-1") + ordinary(canonical(output)),
        "instructions": ordinary("be brief"),
        "message": ordinary("user") + ordinary("hello"),
        "reasoning_summary": ordinary("visible summary"),
        "tools": ordinary(canonical([tool])),
    }

    features = analyze_responses_input(payload)
    actual = {component.kind: component.tokens for component in features.components}

    assert actual == expected
    assert features.known_tokens == sum(expected.values())
    assert features.feature_vector.get(FeatureName.KNOWN_TOTAL).value == sum(expected.values())
    assert features.feature_vector.get(FeatureName.MESSAGE_ITEM_COUNT).value == 1
    assert features.feature_vector.get(FeatureName.FUNCTION_CALL_ITEM_COUNT).value == 1
    assert features.feature_vector.get(FeatureName.FUNCTION_OUTPUT_ITEM_COUNT).value == 1
    assert features.feature_vector.get(FeatureName.REASONING_ITEM_COUNT).value == 1


def test_function_output_content_parts_separate_text_media_unknown_and_framing() -> None:
    def payload(
        *,
        image_data: str = "YQ==",
        file_id: str = "file-a",
        unknown_blob: str = "x",
    ) -> dict[str, Any]:
        return {
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": [
                        {"type": "input_text", "text": "visible"},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{image_data}",
                        },
                        {"type": "input_file", "file_id": file_id},
                        {"type": "future_part", "blob": unknown_blob},
                        7,
                    ],
                }
            ]
        }

    baseline = analyze_responses_input(payload())
    longer_media = analyze_responses_input(payload(image_data="YWFhYWFh"))
    longer_file_reference = analyze_responses_input(payload(file_id="file-a-much-longer-reference"))
    longer_unknown = analyze_responses_input(payload(unknown_blob="x" * 1000))
    expected_function_output = ordinary("call-1") + ordinary("visible")
    expected_framing = 4 + 5 * 4

    assert component_tokens(payload()) == {
        "framing": expected_framing,
        "function_call": 0,
        "function_output": expected_function_output,
        "instructions": 0,
        "message": 0,
        "reasoning_summary": 0,
        "tools": 0,
    }
    assert baseline.known_tokens == expected_function_output + expected_framing
    assert baseline.feature_vector.get(FeatureName.MEDIA_COUNT).value == 2
    assert baseline.feature_vector.get(FeatureName.MEDIA_DECODED_BYTES).value == 1
    assert longer_media.feature_vector.get(FeatureName.MEDIA_DECODED_BYTES).value == 6
    assert baseline.feature_vector.get(FeatureName.UNKNOWN_ITEM_COUNT).value == 2
    assert longer_unknown.feature_vector.get(FeatureName.UNKNOWN_JSON_BYTES).value > baseline.feature_vector.get(
        FeatureName.UNKNOWN_JSON_BYTES
    ).value
    assert longer_media.components == baseline.components
    assert longer_file_reference.components == baseline.components
    assert longer_unknown.components == baseline.components
    assert len(
        {
            baseline.full_fingerprint,
            longer_media.full_fingerprint,
            longer_file_reference.full_fingerprint,
            longer_unknown.full_fingerprint,
        }
    ) == 4


@pytest.mark.parametrize(("part_type", "type_kind"), [([], "array"), ({}, "object")])
def test_function_output_unhashable_part_type_is_unknown_without_losing_framing(
    part_type: object,
    type_kind: str,
) -> None:
    part = {"type": part_type, "blob": "opaque"}
    payload = {
        "input": [
            {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": [part],
            }
        ]
    }
    expected_function_output = ordinary("call-1")
    expected_framing = 4 + 4

    features = analyze_responses_input(payload)

    assert {component.kind: component.tokens for component in features.components} == {
        "framing": expected_framing,
        "function_call": 0,
        "function_output": expected_function_output,
        "instructions": 0,
        "message": 0,
        "reasoning_summary": 0,
        "tools": 0,
    }
    assert features.known_tokens == expected_function_output + expected_framing
    assert features.feature_vector.get(FeatureName.UNKNOWN_ITEM_COUNT).value == 1
    assert features.feature_vector.get(FeatureName.UNKNOWN_JSON_BYTES).value == len(
        canonical(part).encode("utf-8")
    )
    assert features.profile_key.unknown_type_digests == (
        hashlib.sha256(f"function-output-part:{type_kind}".encode()).hexdigest(),
    )
    assert features.low_confidence_reasons == (UNKNOWN_ITEMS_REASON, UNKNOWN_BYTES_REASON)
    assert features.full_fingerprint == hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def test_ciphertext_growth_changes_opaque_features_but_not_known_components() -> None:
    def payload(carrier: str) -> dict[str, Any]:
        return {
            "input": [
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "visible"}],
                    "encrypted_content": carrier,
                }
            ]
        }

    short = analyze_responses_input(payload("YQ=="))
    long = analyze_responses_input(payload("YQ==" * 1000))

    assert short.components == long.components
    assert short.known_tokens == long.known_tokens
    assert short.feature_vector.get(FeatureName.OPAQUE_REASONING_BYTES).value == 4
    assert long.feature_vector.get(FeatureName.OPAQUE_REASONING_BYTES).value == 4000
    assert short.full_fingerprint != long.full_fingerprint
    assert OPAQUE_BYTES_REASON in short.low_confidence_reasons
    assert OPAQUE_ITEMS_REASON in short.low_confidence_reasons


def test_visible_reasoning_summary_still_changes_known_tokens() -> None:
    baseline = {
        "input": [
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "short"}],
                "encrypted_content": "same opaque value",
            }
        ]
    }
    changed = {
        "input": [
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "a visible explanation " * 100}],
                "encrypted_content": "same opaque value",
            }
        ]
    }

    before = analyze_responses_input(baseline)
    after = analyze_responses_input(changed)

    assert after.known_tokens > before.known_tokens
    assert after.feature_vector.get(FeatureName.OPAQUE_REASONING_BYTES) == before.feature_vector.get(
        FeatureName.OPAQUE_REASONING_BYTES
    )


def test_base64_growth_changes_media_features_but_not_known_components() -> None:
    def payload(encoded: str) -> dict[str, Any]:
        return {
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "describe"},
                        {"type": "input_image", "image_url": f"data:image/png;base64,{encoded}"},
                    ],
                }
            ]
        }

    short = analyze_responses_input(payload("YQ=="))
    long = analyze_responses_input(payload("YWFhYWFh"))

    assert short.components == long.components
    assert short.feature_vector.get(FeatureName.MEDIA_COUNT).value == 1
    assert short.feature_vector.get(FeatureName.MEDIA_DECODED_BYTES).value == 1
    assert long.feature_vector.get(FeatureName.MEDIA_DECODED_BYTES).value == 6
    assert MEDIA_REASON in short.low_confidence_reasons
    assert short.full_fingerprint != long.full_fingerprint


@pytest.mark.parametrize(
    ("short_part", "long_part"),
    [
        (
            {"type": "input_image", "image_url": "https://example.test/a"},
            {"type": "input_image", "image_url": "https://example.test/a-very-long-reference"},
        ),
        (
            {"type": "input_image", "file_id": "file-a"},
            {"type": "input_image", "file_id": "file-a-very-long-reference"},
        ),
        (
            {"type": "input_file", "file_id": "file-a"},
            {"type": "input_file", "file_id": "file-a-very-long-reference"},
        ),
    ],
)
def test_media_reference_length_does_not_change_known_components(
    short_part: dict[str, Any],
    long_part: dict[str, Any],
) -> None:
    def payload(part: dict[str, Any]) -> dict[str, Any]:
        return {
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [part],
                }
            ]
        }

    short = analyze_responses_input(payload(short_part))
    long = analyze_responses_input(payload(long_part))

    assert short.components == long.components
    assert short.feature_vector.get(FeatureName.MEDIA_COUNT).value == 1
    assert short.feature_vector.get(FeatureName.MEDIA_DECODED_BYTES).present is False
    assert short.full_fingerprint != long.full_fingerprint


def test_unknown_json_growth_changes_features_and_identity_but_not_known_components() -> None:
    def payload(blob: str) -> dict[str, Any]:
        return {"input": [{"type": "future_item", "blob": blob}]}

    short = analyze_responses_input(payload("x"))
    long = analyze_responses_input(payload("x" * 1000))

    assert short.components == long.components
    assert short.feature_vector.get(FeatureName.UNKNOWN_ITEM_COUNT).value == 1
    assert long.feature_vector.get(FeatureName.UNKNOWN_JSON_BYTES).value > short.feature_vector.get(
        FeatureName.UNKNOWN_JSON_BYTES
    ).value
    assert short.full_fingerprint != long.full_fingerprint
    assert UNKNOWN_BYTES_REASON in short.low_confidence_reasons
    assert UNKNOWN_ITEMS_REASON in short.low_confidence_reasons


def test_unknown_nested_part_growth_changes_unknown_features_not_known_components() -> None:
    def payload(blob: str) -> dict[str, Any]:
        return {
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "future_part", "blob": blob}],
                }
            ]
        }

    short = analyze_responses_input(payload("x"))
    long = analyze_responses_input(payload("x" * 1000))

    assert short.components == long.components
    assert short.feature_vector.get(FeatureName.UNKNOWN_ITEM_COUNT).value == 1
    assert long.feature_vector.get(FeatureName.UNKNOWN_JSON_BYTES).value > short.feature_vector.get(
        FeatureName.UNKNOWN_JSON_BYTES
    ).value


def test_low_confidence_reasons_are_sorted_unique() -> None:
    payload = {
        "input": [
            {"type": "reasoning", "encrypted_content": "one"},
            {"type": "reasoning", "encrypted_content": "two"},
            {"type": "input_image", "image_url": "https://example.test/image.png"},
            {"type": "future_item", "blob": 1},
            {"type": "future_item", "blob": 2},
        ]
    }

    reasons = analyze_responses_input(payload).low_confidence_reasons

    assert reasons == tuple(sorted(set(reasons)))
    assert reasons == (
        MEDIA_REASON,
        OPAQUE_BYTES_REASON,
        OPAQUE_ITEMS_REASON,
        UNKNOWN_ITEMS_REASON,
        UNKNOWN_BYTES_REASON,
    )


def test_empty_payload_has_zero_structured_tokens_and_legacy_minimum_one() -> None:
    features = analyze_responses_input({})

    assert features.known_tokens == 0
    assert features.prefix_fingerprints == ()
    assert features.raw_sent_body_sha256 is None
    assert estimate_responses_input({}) == 1


def _special_surface(surface: str, spelling: str) -> tuple[dict[str, Any], int]:
    if surface == "instructions":
        return {"instructions": spelling}, ordinary(spelling) + 4
    if surface == "message":
        return {
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": spelling}],
                }
            ]
        }, ordinary("user") + ordinary(spelling) + 8
    if surface == "tool-schema":
        tool = {
            "type": "function",
            "name": "lookup",
            "parameters": {"type": "object", "description": spelling},
        }
        return {"tools": [tool]}, ordinary(canonical([tool])) + 8
    if surface == "function-call-arguments":
        return {
            "input": [
                {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "lookup",
                    "arguments": spelling,
                }
            ]
        }, ordinary("call-1") + ordinary("lookup") + ordinary(spelling) + 4
    if surface == "function-call-output":
        return {
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": spelling,
                }
            ]
        }, ordinary("call-1") + ordinary(spelling) + 4
    if surface == "function-output-content-part":
        return {
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": [{"type": "input_text", "text": spelling}],
                }
            ]
        }, ordinary("call-1") + ordinary(spelling) + 8
    if surface == "reasoning-summary":
        return {
            "input": [
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": spelling}],
                }
            ]
        }, ordinary(spelling) + 8
    raise AssertionError(f"unknown test surface: {surface}")


@pytest.mark.parametrize("spelling", SPECIAL_SPELLINGS)
@pytest.mark.parametrize(
    "surface",
    [
        "instructions",
        "message",
        "tool-schema",
        "function-call-arguments",
        "function-call-output",
        "function-output-content-part",
        "reasoning-summary",
    ],
)
def test_every_known_text_surface_treats_configured_special_spellings_as_ordinary(
    spelling: str,
    surface: str,
) -> None:
    payload, expected = _special_surface(surface, spelling)

    features = analyze_responses_input(payload)

    assert features.known_tokens == expected
    assert estimate_responses_input(payload) == max(expected, 1)


def test_prediction_candidate_keys_accept_exactly_the_seven_v1_pairs() -> None:
    legal = {
        (PredictionMethod.HISTORY_EXACT, PredictionCandidateVariant.MEDIAN),
        (PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.DETERMINISTIC),
        (PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.ADDITIVE),
        (PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.MULTIPLICATIVE),
        (PredictionMethod.PROFILE_CALIBRATED, PredictionCandidateVariant.ADDITIVE),
        (PredictionMethod.PROFILE_CALIBRATED, PredictionCandidateVariant.MULTIPLICATIVE),
        (PredictionMethod.COLD_START, PredictionCandidateVariant.DETERMINISTIC),
    }

    assert tuple(PredictionMethod) == (
        PredictionMethod.HISTORY_EXACT,
        PredictionMethod.HISTORY_PREFIX,
        PredictionMethod.PROFILE_CALIBRATED,
        PredictionMethod.COLD_START,
    )
    assert {
        (method, variant)
        for method in PredictionMethod
        for variant in PredictionCandidateVariant
        if (method, variant) in legal
        and PredictionCandidateKey(method, variant) == PredictionCandidateKey(method, variant)
    } == legal
    for method in PredictionMethod:
        for variant in PredictionCandidateVariant:
            if (method, variant) not in legal:
                with pytest.raises(ValueError, match="legal pair"):
                    PredictionCandidateKey(method, variant)


def test_prediction_record_preserves_variants_champions_and_selection_cardinality() -> None:
    features = analyze_responses_input({})
    prefix_deterministic = _prediction(features, method=PredictionMethod.HISTORY_PREFIX)
    prefix_additive = _prediction(
        features,
        method=PredictionMethod.HISTORY_PREFIX,
        variant=PredictionCandidateVariant.ADDITIVE,
        unscaled_tokens=11.0,
    )
    cold = _prediction(features, unscaled_tokens=12.0)
    prefix_champion = MethodChampion(prefix_additive.candidate_key, True)
    cold_champion = MethodChampion(cold.candidate_key, True)
    record = PredictionRecord(
        ("boot", "request", 0),
        prefix_additive.candidate_key,
        (prefix_deterministic, prefix_additive, cold),
        (prefix_champion, cold_champion),
    )

    assert record.selected is prefix_additive
    assert record.candidates[:2] == (prefix_deterministic, prefix_additive)
    with pytest.raises(ValueError, match="unique candidate keys"):
        replace(record, candidates=(prefix_deterministic, prefix_deterministic, cold))
    with pytest.raises(ValueError, match="exactly cover"):
        replace(record, method_champions=(cold_champion,))
    with pytest.raises(ValueError, match="unique champions"):
        replace(record, method_champions=(prefix_champion, prefix_champion, cold_champion))
    extra_exact = MethodChampion(
        PredictionCandidateKey(PredictionMethod.HISTORY_EXACT, PredictionCandidateVariant.MEDIAN),
        True,
    )
    with pytest.raises(ValueError, match="exactly cover"):
        replace(record, method_champions=(extra_exact, prefix_champion, cold_champion))
    missing_prefix_candidate = MethodChampion(
        PredictionCandidateKey(PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.MULTIPLICATIVE),
        True,
    )
    with pytest.raises(ValueError, match="existing candidate"):
        replace(record, method_champions=(missing_prefix_candidate, cold_champion))
    with pytest.raises(ValueError, match="first eligible"):
        replace(record, selected_key=cold.candidate_key)

    cold_only = _record(("boot", "cold-only", 0), (cold,))
    assert cold_only.selected_key == cold.candidate_key
    assert cold_only.method_champions == (cold_champion,)
    demoted = PredictionRecord(
        ("boot", "demoted", 0),
        cold.candidate_key,
        (prefix_deterministic, cold),
        (MethodChampion(prefix_deterministic.candidate_key, False), cold_champion),
    )
    assert demoted.selected is cold
    with pytest.raises(ValueError, match="first eligible"):
        replace(demoted, selected_key=prefix_deterministic.candidate_key)
    with pytest.raises(ValueError, match="must be eligible"):
        MethodChampion(cold.candidate_key, False)
    exact = _prediction(features, method=PredictionMethod.HISTORY_EXACT)
    with pytest.raises(ValueError, match="must be eligible"):
        MethodChampion(exact.candidate_key, False)


def test_prediction_decision_requires_method_specific_ephemeral_anchor_intent() -> None:
    features = analyze_responses_input({"input": ["hello"]})
    identity = _learning_identity(features)
    exact = _prediction(features, identity=identity, method=PredictionMethod.HISTORY_EXACT)
    prefix = _prediction(features, identity=identity, method=PredictionMethod.HISTORY_PREFIX)
    cold = _prediction(features, identity=identity)
    exact_intent = AnchorUseIntent(
        AnchorKind.EXACT,
        identity,
        identity.learning_epoch,
        features.full_fingerprint,
        (("boot", "exact", 0),),
    )
    prefix_intent = AnchorUseIntent(
        AnchorKind.PREFIX,
        identity,
        identity.learning_epoch,
        features.prefix_fingerprints[-1].digest,
        (("boot", "prefix", 0),),
    )

    assert PredictionDecision(exact, exact_intent).anchor_use_intent is exact_intent
    assert PredictionDecision(prefix, prefix_intent).anchor_use_intent is prefix_intent
    assert PredictionDecision(cold, None).anchor_use_intent is None
    profile = _prediction(features, identity=identity, method=PredictionMethod.PROFILE_CALIBRATED)
    assert PredictionDecision(profile, None).anchor_use_intent is None
    with pytest.raises(ValueError, match="matching anchor-use intent kind"):
        PredictionDecision(exact, None)
    with pytest.raises(ValueError, match="matching anchor-use intent kind"):
        PredictionDecision(exact, prefix_intent)
    with pytest.raises(ValueError, match="must not carry"):
        PredictionDecision(cold, exact_intent)
    with pytest.raises(ValueError, match="must not carry"):
        PredictionDecision(profile, exact_intent)
    other_identity = replace(identity, actual_provider="provider-b")
    with pytest.raises(ValueError, match="identity"):
        PredictionDecision(
            exact,
            replace(exact_intent, identity=other_identity),
        )
    other_epoch_identity = replace(identity, learning_epoch=identity.learning_epoch + 1)
    with pytest.raises(ValueError, match="identity"):
        PredictionDecision(
            exact,
            replace(
                exact_intent,
                identity=other_epoch_identity,
                learning_epoch=other_epoch_identity.learning_epoch,
            ),
        )


def test_a18_visual_capability_is_presence_aware_per_item_and_pickle_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubEncoding:
        def encode_ordinary(self, text: str) -> list[int]:
            counts = {"instructions": 2, "user": 3, "message": 4}
            return [0] * counts.get(text, 0)

    def stub_encoding(_name: str) -> StubEncoding:
        return StubEncoding()

    monkeypatch.setattr(tiktoken, "get_encoding", stub_encoding)
    formula = SyntheticUnresizedPatchGridFormula(revision=1, patch_width=28, patch_height=28)
    capabilities = TokenizationCapabilities(formula)
    payload = {
        "instructions": "instructions",
        "input": [
            {"type": "message", "role": "user", "content": "message"},
            {"type": "reasoning", "encrypted_content": "opaque"},
            {"type": "input_image", "width": 56, "height": 84},
            {"type": "future-item", "opaque": True},
        ],
    }

    features = analyze_responses_input(payload, capabilities=capabilities)

    assert features.known_tokens == 29
    assert features.capability_visual_tokens == 6
    assert features.known_tokens + features.capability_visual_tokens == 35
    assert MEDIA_REASON not in features.low_confidence_reasons
    assert OPAQUE_BYTES_REASON in features.low_confidence_reasons
    assert UNKNOWN_BYTES_REASON in features.low_confidence_reasons
    assert features.estimator_generation == 2
    assert pickle.loads(pickle.dumps(capabilities)) == capabilities
    assert formula.kind is VisualTokenFormulaKind.SYNTHETIC_UNRESIZED_PATCH_GRID_V1

    same_pixels_six = analyze_responses_input(
        {"input": [{"type": "input_image", "width": 56, "height": 84}]},
        capabilities=capabilities,
    )
    same_pixels_eight = analyze_responses_input(
        {"input": [{"type": "input_image", "width": 42, "height": 112}]},
        capabilities=capabilities,
    )
    assert same_pixels_six.feature_vector.get(FeatureName.MEDIA_PIXEL_COUNT).value == 4_704
    assert same_pixels_eight.feature_vector.get(FeatureName.MEDIA_PIXEL_COUNT).value == 4_704
    assert same_pixels_six.capability_visual_tokens == 6
    assert same_pixels_eight.capability_visual_tokens == 8
    assert analyze_responses_input({}, capabilities=capabilities).capability_visual_tokens == 0
    assert analyze_responses_input(payload).capability_visual_tokens is None
    missing_metadata = analyze_responses_input(
        {"input": [{"type": "input_image", "width": 56}]},
        capabilities=capabilities,
    )
    assert missing_metadata.capability_visual_tokens is None
    assert MEDIA_REASON in missing_metadata.low_confidence_reasons
    for invalid in (True, -1, 1.5):
        with pytest.raises(ValueError, match="capability_visual_tokens"):
            replace(features, capability_visual_tokens=cast(Any, invalid))


def test_mixed_image_and_pdf_preserves_generic_media_reason_after_item_visual_success() -> None:
    capabilities = TokenizationCapabilities(
        SyntheticUnresizedPatchGridFormula(revision=1, patch_width=28, patch_height=28)
    )
    features = analyze_responses_input(
        {
            "input": [
                {"type": "input_image", "width": 56, "height": 84},
                {"type": "input_file", "page_count": 1, "media_type": "application/pdf"},
            ]
        },
        capabilities=capabilities,
    )

    assert features.input_item_contributions[0].capability_visual_tokens == 6
    assert features.input_item_contributions[1].capability_visual_tokens is None
    assert features.capability_visual_tokens is None
    assert MEDIA_REASON in features.low_confidence_reasons
    assert PDF_REASON in features.low_confidence_reasons
