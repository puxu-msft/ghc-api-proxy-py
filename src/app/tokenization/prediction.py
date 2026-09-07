"""Pure deterministic token-prediction primitives.

This module intentionally consumes only the public, immutable prediction
snapshot.  Persistence, queues, and checkpoint policy belong to later slices.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from app.tokenization.types import (
    AnchorKind,
    AnchorUseIntent,
    EstimateFeatures,
    ExactAnchor,
    LearningSnapshot,
    MethodChampion,
    PredictionCandidateKey,
    PredictionCandidateVariant,
    PredictionDecision,
    PredictionEvaluation,
    PredictionMethod,
    PredictionRecord,
    PrefixAnchor,
    SampleKey,
    TokenPrediction,
)

_EXACT_KEY = PredictionCandidateKey(
    PredictionMethod.HISTORY_EXACT, PredictionCandidateVariant.MEDIAN
)
_PREFIX_KEY = PredictionCandidateKey(
    PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.DETERMINISTIC
)
_COLD_KEY = PredictionCandidateKey(
    PredictionMethod.COLD_START, PredictionCandidateVariant.DETERMINISTIC
)


@dataclass(frozen=True, slots=True)
class _PredictionBuild:
    candidates: tuple[TokenPrediction, ...]
    champions: tuple[MethodChampion, ...]
    selected: TokenPrediction
    intents: dict[PredictionCandidateKey, AnchorUseIntent]


def predict_exact_or_prefix(
    features: EstimateFeatures, snapshot: LearningSnapshot
) -> PredictionDecision:
    """Select the request-side prediction and its optional anchor-use intent."""
    result = _build_predictions(features, snapshot)
    return PredictionDecision(
        prediction=result.selected,
        anchor_use_intent=result.intents.get(result.selected.candidate_key),
    )


def build_prediction_record(
    sample_key: SampleKey, features: EstimateFeatures, snapshot: LearningSnapshot
) -> PredictionRecord:
    """Freeze all currently available candidates before the current label is learned."""
    if sample_key in {sample.sample_key for sample in snapshot.samples} or sample_key in {
        record.sample_key for record in snapshot.prediction_records
    }:
        raise ValueError("current sample key must not already be present in the prediction snapshot")
    result = _build_predictions(features, snapshot)
    return PredictionRecord(
        sample_key=sample_key,
        selected_key=result.selected.candidate_key,
        candidates=result.candidates,
        method_champions=result.champions,
    )


def evaluate(record: PredictionRecord, actual: int) -> tuple[PredictionEvaluation, ...]:
    """Evaluate every frozen candidate in record order without quantization."""
    if type(actual) is not int or actual < 0:
        raise ValueError("actual must be a nonnegative integer")
    evaluations: list[PredictionEvaluation] = []
    for candidate in record.candidates:
        signed_relative_error = (
            (candidate.unscaled_tokens - actual) / actual if actual > 0 else None
        )
        evaluations.append(
            PredictionEvaluation(
                sample_key=record.sample_key,
                method=candidate.method,
                candidate_key=candidate.candidate_key,
                predicted_tokens=candidate.unscaled_tokens,
                actual_tokens=actual,
                absolute_error=abs(candidate.unscaled_tokens - actual),
                signed_relative_error=signed_relative_error,
                absolute_percentage_error=(
                    abs(signed_relative_error) if signed_relative_error is not None else None
                ),
            )
        )
    return tuple(evaluations)


def _build_predictions(features: EstimateFeatures, snapshot: LearningSnapshot) -> _PredictionBuild:
    _validate_compatibility(features, snapshot)
    candidates: list[TokenPrediction] = []
    intents: dict[PredictionCandidateKey, AnchorUseIntent] = {}

    exact = _find_exact_anchor(features, snapshot)
    if exact is not None:
        candidates.append(
            _candidate(
                features,
                snapshot,
                _EXACT_KEY,
                median(exact.actual_tokens),
                len(exact.actual_tokens),
            )
        )
        intents[_EXACT_KEY] = AnchorUseIntent(
            kind=AnchorKind.EXACT,
            identity=snapshot.identity,
            learning_epoch=snapshot.active_epoch,
            fingerprint=features.full_fingerprint,
            source_sample_keys=exact.sample_keys,
        )

    prefix = _find_prefix_anchor(features, snapshot)
    if prefix is not None:
        anchor, suffix_delta = prefix
        candidates.append(
            _candidate(
                features,
                snapshot,
                _PREFIX_KEY,
                anchor.actual_tokens + suffix_delta,
                1,
            )
        )
        intents[_PREFIX_KEY] = AnchorUseIntent(
            kind=AnchorKind.PREFIX,
            identity=snapshot.identity,
            learning_epoch=snapshot.active_epoch,
            fingerprint=anchor.prefix_fingerprint.digest,
            source_sample_keys=(anchor.sample_key,),
        )

    candidates.append(
        _candidate(
            features,
            snapshot,
            _COLD_KEY,
            _cold_start_unscaled(features),
            0,
        )
    )

    candidates_tuple = tuple(candidates)
    champions = tuple(
        MethodChampion(candidate.candidate_key, eligible_for_selection=True)
        for method in PredictionMethod
        for candidate in candidates_tuple
        if candidate.method is method
    )
    selected = next(
        candidate
        for champion in champions
        for candidate in candidates_tuple
        if candidate.candidate_key == champion.candidate_key
        and champion.eligible_for_selection
    )
    return _PredictionBuild(candidates_tuple, champions, selected, intents)


def _validate_compatibility(features: EstimateFeatures, snapshot: LearningSnapshot) -> None:
    if (
        features.estimator_generation != snapshot.identity.estimator_generation
        or features.profile_schema_revision != snapshot.identity.profile_schema_revision
        or snapshot.active_epoch != snapshot.identity.learning_epoch
    ):
        raise ValueError("features and learning snapshot are incompatible")


def _candidate(
    features: EstimateFeatures,
    snapshot: LearningSnapshot,
    key: PredictionCandidateKey,
    unscaled_tokens: float,
    sample_count: int,
) -> TokenPrediction:
    reasons = set(features.low_confidence_reasons)
    if unscaled_tokens <= 0:
        reasons.add("minimum-one")
    return TokenPrediction(
        identity=snapshot.identity,
        profile_key=features.profile_key,
        method=key.method,
        candidate_key=key,
        unscaled_tokens=unscaled_tokens,
        sample_count=sample_count,
        history_revision=snapshot.revision,
        learning_epoch=snapshot.active_epoch,
        low_confidence_reasons=tuple(sorted(reasons)),
    )


def _cold_start_unscaled(features: EstimateFeatures) -> float:
    whole_known = features.fixed_context_contribution.known_tokens + sum(
        item.known_tokens for item in features.input_item_contributions
    )
    whole_visual = (
        0
        if any(item.capability_visual_tokens is None for item in features.input_item_contributions)
        else sum(item.capability_visual_tokens or 0 for item in features.input_item_contributions)
    )
    whole_prior = features.fixed_context_contribution.prior_residual_tokens + sum(
        item.prior_residual_tokens for item in features.input_item_contributions
    )
    return whole_known + whole_visual + whole_prior


def _find_exact_anchor(
    features: EstimateFeatures, snapshot: LearningSnapshot
) -> ExactAnchor | None:
    matches = tuple(
        anchor
        for anchor in snapshot.exact_anchors
        if anchor.full_fingerprint == features.full_fingerprint
    )
    if len(matches) > 1:
        raise ValueError("snapshot contains duplicate exact-anchor groups")
    return matches[0] if matches else None


def _find_prefix_anchor(
    features: EstimateFeatures, snapshot: LearningSnapshot
) -> tuple[PrefixAnchor, float] | None:
    matches = [
        anchor
        for anchor in snapshot.prefix_anchors
        if anchor.context_fingerprint == features.context_fingerprint
        and anchor.prefix_fingerprint.item_count < len(features.prefix_fingerprints)
        and features.prefix_fingerprints[anchor.prefix_fingerprint.item_count - 1]
        == anchor.prefix_fingerprint
    ]
    if not matches:
        return None
    anchor = min(
        matches,
        key=lambda value: (
            -value.prefix_fingerprint.item_count,
            -value.observed_at_us,
            value.sample_key[0].encode("utf-8"),
            value.sample_key[1].encode("utf-8"),
            value.sample_key[2],
        ),
    )
    if sum(sample.sample_key == anchor.sample_key for sample in snapshot.samples) != 1:
        raise ValueError("selected prefix anchor must reference exactly one snapshot sample")
    appended_items = features.input_item_contributions[anchor.prefix_fingerprint.item_count :]
    suffix_delta = sum(
        item.known_tokens
        + (item.capability_visual_tokens if item.capability_visual_tokens is not None else 0)
        + item.prior_residual_tokens
        for item in appended_items
    )
    return anchor, suffix_delta
