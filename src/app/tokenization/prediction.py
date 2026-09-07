"""Pure deterministic token-prediction primitives.

This module intentionally consumes only the public, immutable prediction
snapshot.  Persistence, queues, and checkpoint policy belong to later slices.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from statistics import median

from app.tokenization.types import (
    AnchorKind,
    AnchorUseIntent,
    EstimateFeatures,
    ExactAnchor,
    LearningIdentity,
    LearningSnapshot,
    MethodChampion,
    PredictionCandidateKey,
    PredictionCandidateVariant,
    PredictionDecision,
    PredictionEvaluation,
    PredictionMethod,
    PredictionRecord,
    PrefixAnchor,
    PrefixFingerprint,
    ProfileKey,
    SampleKey,
    StoredSample,
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
_PREFIX_ADDITIVE_KEY = PredictionCandidateKey(
    PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.ADDITIVE
)
_PREFIX_MULTIPLICATIVE_KEY = PredictionCandidateKey(
    PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.MULTIPLICATIVE
)


@dataclass(frozen=True, slots=True)
class _PrefixPair:
    base: StoredSample
    longer: StoredSample
    suffix_baseline_delta: float


@dataclass(frozen=True, slots=True)
class PrefixPairIndex:
    """Immutable, point-in-time historical prefix pairs for one snapshot."""

    identity: LearningIdentity
    active_epoch: int
    revision: int
    pairs: tuple[_PrefixPair, ...]


@dataclass(frozen=True, slots=True)
class _PredictionBuild:
    candidates: tuple[TokenPrediction, ...]
    champions: tuple[MethodChampion, ...]
    selected: TokenPrediction
    intents: dict[PredictionCandidateKey, AnchorUseIntent]


def predict_exact_or_prefix(
    features: EstimateFeatures,
    snapshot: LearningSnapshot,
    *,
    prefix_pair_index: PrefixPairIndex | None = None,
) -> PredictionDecision:
    """Select the request-side prediction and its optional anchor-use intent."""
    result = _build_predictions(features, snapshot, prefix_pair_index=prefix_pair_index)
    return PredictionDecision(
        prediction=result.selected,
        anchor_use_intent=result.intents.get(result.selected.candidate_key),
    )


def build_prediction_record(
    sample_key: SampleKey,
    features: EstimateFeatures,
    snapshot: LearningSnapshot,
    *,
    prefix_pair_index: PrefixPairIndex | None = None,
) -> PredictionRecord:
    """Freeze all currently available candidates before the current label is learned."""
    if sample_key in {sample.sample_key for sample in snapshot.samples} or sample_key in {
        record.sample_key for record in snapshot.prediction_records
    }:
        raise ValueError("current sample key must not already be present in the prediction snapshot")
    result = _build_predictions(features, snapshot, prefix_pair_index=prefix_pair_index)
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


def _build_predictions(
    features: EstimateFeatures,
    snapshot: LearningSnapshot,
    *,
    prefix_pair_index: PrefixPairIndex | None,
) -> _PredictionBuild:
    _validate_compatibility(features, snapshot)
    index = prefix_pair_index or build_prefix_pair_index(snapshot)
    _validate_prefix_pair_index(index, snapshot)
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
        prefix_intent = AnchorUseIntent(
            kind=AnchorKind.PREFIX,
            identity=snapshot.identity,
            learning_epoch=snapshot.active_epoch,
            fingerprint=anchor.prefix_fingerprint.digest,
            source_sample_keys=(anchor.sample_key,),
        )
        intents[_PREFIX_KEY] = prefix_intent
        additive_evidence, multiplicative_evidence = _learned_prefix_evidence(
            index, features.profile_key
        )
        if len(additive_evidence) >= 3:
            candidates.append(
                _candidate(
                    features,
                    snapshot,
                    _PREFIX_ADDITIVE_KEY,
                    anchor.actual_tokens + suffix_delta + median(additive_evidence),
                    len(additive_evidence),
                )
            )
            intents[_PREFIX_ADDITIVE_KEY] = prefix_intent
        if len(multiplicative_evidence) >= 3:
            candidates.append(
                _candidate(
                    features,
                    snapshot,
                    _PREFIX_MULTIPLICATIVE_KEY,
                    anchor.actual_tokens
                    + suffix_delta * exp(median(multiplicative_evidence)),
                    len(multiplicative_evidence),
                )
            )
            intents[_PREFIX_MULTIPLICATIVE_KEY] = prefix_intent

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
    prefix_champion = _select_prefix_champion(features, snapshot, candidates_tuple)
    champions = tuple(
        MethodChampion(
            _champion_key_for_method(method, candidates_tuple, prefix_champion),
            eligible_for_selection=True,
        )
        for method in PredictionMethod
        if any(candidate.method is method for candidate in candidates_tuple)
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


def build_prefix_pair_index(snapshot: LearningSnapshot) -> PrefixPairIndex:
    """Build canonical, committed-earlier base pairs without inspecting records."""
    seen_orders: set[int] = set()
    for sample in snapshot.samples:
        order = sample.committed_order
        if type(order) is not int or order < 1:
            raise ValueError("snapshot samples require positive committed orders")
        if order in seen_orders:
            raise ValueError("snapshot sample committed orders must be unique")
        seen_orders.add(order)

    ordered_samples = tuple(
        sorted(
            snapshot.samples,
            key=lambda sample: (
                sample.committed_order,
                sample.sample_key[0].encode("utf-8"),
                sample.sample_key[1].encode("utf-8"),
                sample.sample_key[2],
            ),
        )
    )
    lookup: dict[tuple[str, PrefixFingerprint], StoredSample] = {}
    pairs: list[_PrefixPair] = []
    for longer in ordered_samples:
        base = _canonical_base_for(longer, lookup)
        if base is not None:
            pairs.append(
                _PrefixPair(
                    base=base,
                    longer=longer,
                    suffix_baseline_delta=_suffix_baseline(
                        longer.features, len(base.features.input_item_contributions)
                    ),
                )
            )
        if longer.features.prefix_fingerprints:
            final_prefix = longer.features.prefix_fingerprints[-1]
            lookup_key = (longer.features.context_fingerprint, final_prefix)
            existing = lookup.get(lookup_key)
            if existing is None or _is_preferred_base(longer, existing):
                lookup[lookup_key] = longer
    return PrefixPairIndex(snapshot.identity, snapshot.active_epoch, snapshot.revision, tuple(pairs))


def _validate_prefix_pair_index(index: PrefixPairIndex, snapshot: LearningSnapshot) -> None:
    if (
        index.identity != snapshot.identity
        or index.active_epoch != snapshot.active_epoch
        or index.revision != snapshot.revision
    ):
        raise ValueError("prefix pair index must match snapshot identity, epoch, and revision")


def _canonical_base_for(
    longer: StoredSample, lookup: dict[tuple[str, PrefixFingerprint], StoredSample]
) -> StoredSample | None:
    candidates = (
        lookup.get((longer.features.context_fingerprint, prefix))
        for prefix in longer.features.prefix_fingerprints[:-1]
    )
    bases = tuple(base for base in candidates if base is not None)
    if not bases:
        return None
    return min(
        bases,
        key=lambda sample: (
            -len(sample.features.input_item_contributions),
            -sample.observed_at_us,
            sample.sample_key[0].encode("utf-8"),
            sample.sample_key[1].encode("utf-8"),
            sample.sample_key[2],
        ),
    )


def _is_preferred_base(candidate: StoredSample, existing: StoredSample) -> bool:
    return (
        -len(candidate.features.input_item_contributions),
        -candidate.observed_at_us,
        candidate.sample_key[0].encode("utf-8"),
        candidate.sample_key[1].encode("utf-8"),
        candidate.sample_key[2],
    ) < (
        -len(existing.features.input_item_contributions),
        -existing.observed_at_us,
        existing.sample_key[0].encode("utf-8"),
        existing.sample_key[1].encode("utf-8"),
        existing.sample_key[2],
    )


def _suffix_baseline(features: EstimateFeatures, start: int) -> float:
    return sum(
        item.known_tokens
        + (item.capability_visual_tokens if item.capability_visual_tokens is not None else 0)
        + item.prior_residual_tokens
        for item in features.input_item_contributions[start:]
    )


def _learned_prefix_evidence(
    index: PrefixPairIndex, profile_key: ProfileKey
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    additive: list[float] = []
    multiplicative: list[float] = []
    for pair in index.pairs:
        if pair.longer.features.profile_key != profile_key:
            continue
        actual_delta = pair.longer.actual_input_tokens - pair.base.actual_input_tokens
        if actual_delta <= 0:
            continue
        if pair.suffix_baseline_delta >= 0:
            additive.append(actual_delta - pair.suffix_baseline_delta)
        if pair.suffix_baseline_delta > 0:
            multiplicative.append(log(actual_delta / pair.suffix_baseline_delta))
    return tuple(additive), tuple(multiplicative)


def _champion_key_for_method(
    method: PredictionMethod,
    candidates: tuple[TokenPrediction, ...],
    prefix_champion: PredictionCandidateKey | None,
) -> PredictionCandidateKey:
    if method is PredictionMethod.HISTORY_PREFIX:
        if prefix_champion is None:
            raise ValueError("represented prefix candidates require a prefix champion")
        return prefix_champion
    return next(candidate.candidate_key for candidate in candidates if candidate.method is method)


def _select_prefix_champion(
    features: EstimateFeatures,
    snapshot: LearningSnapshot,
    candidates: tuple[TokenPrediction, ...],
) -> PredictionCandidateKey | None:
    current_prefix_keys = tuple(
        candidate.candidate_key
        for candidate in candidates
        if candidate.method is PredictionMethod.HISTORY_PREFIX
    )
    if not current_prefix_keys:
        return None
    records_by_key = {record.sample_key: record for record in snapshot.prediction_records}
    samples_by_key = {sample.sample_key: sample for sample in snapshot.samples}
    if set(records_by_key) - set(samples_by_key):
        raise ValueError("prediction records must link to retained samples")
    eligible: list[tuple[StoredSample, PredictionRecord]] = []
    for sample_key, record in records_by_key.items():
        sample = samples_by_key[sample_key]
        if record.selected.profile_key != sample.features.profile_key:
            raise ValueError("prediction record profile key must match its linked sample")
        if (
            record.selected.identity != sample.identity
            or record.selected.learning_epoch != sample.identity.learning_epoch
        ):
            raise ValueError("prediction record identity and epoch must match its linked sample")
        if sample.actual_input_tokens <= 0 or record.selected.profile_key != features.profile_key:
            continue
        candidate_by_key = {candidate.candidate_key: candidate for candidate in record.candidates}
        if all(key in candidate_by_key for key in current_prefix_keys):
            eligible.append((sample, record))
    eligible.sort(
        key=lambda value: (
            value[0].observed_at_us,
            value[0].sample_key[0].encode("utf-8"),
            value[0].sample_key[1].encode("utf-8"),
            value[0].sample_key[2],
        ),
        reverse=True,
    )
    window = eligible[:31]
    if len(window) < 8:
        return _PREFIX_KEY
    ape_by_key: dict[PredictionCandidateKey, float] = {}
    for key in current_prefix_keys:
        apes = tuple(
            abs(
                next(candidate for candidate in record.candidates if candidate.candidate_key == key)
                .unscaled_tokens
                - sample.actual_input_tokens
            )
            / sample.actual_input_tokens
            for sample, record in window
        )
        ape_by_key[key] = median(apes)
    deterministic_ape = ape_by_key[_PREFIX_KEY]
    contenders = [
        key
        for key in current_prefix_keys
        if key is _PREFIX_KEY or ape_by_key[key] < deterministic_ape
    ]
    preference = {
        _PREFIX_KEY: 0,
        _PREFIX_ADDITIVE_KEY: 1,
        _PREFIX_MULTIPLICATIVE_KEY: 2,
    }
    return min(contenders, key=lambda key: (ape_by_key[key], preference[key]))


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
