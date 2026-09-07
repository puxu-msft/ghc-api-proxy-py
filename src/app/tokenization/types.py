from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, cast

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

type SampleKey = tuple[str, str, int]
type LearningObservationOutcome = Literal["committed", "duplicate", "rejected", "failed"]
type DriftKind = Literal["exact", "profile"]


@dataclass(frozen=True, slots=True)
class EstimatorTiming:
    format: Literal["anthropic", "responses"]
    phase: Literal["lookup", "estimate"]
    seconds: float
    failed: bool


def _require_nonnegative_int(name: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _require_sha256(name: str, value: str) -> None:
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")


def _require_sorted_unique(name: str, values: tuple[str, ...]) -> None:
    if any(not value for value in values):
        raise ValueError(f"{name} values must be non-empty")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{name} must be sorted and unique")


class FeatureName(StrEnum):
    KNOWN_TOTAL = "known_total"
    INSTRUCTIONS_TOKENS = "instructions_tokens"
    TOOLS_TOKENS = "tools_tokens"
    MESSAGE_TOKENS = "message_tokens"
    FUNCTION_CALL_TOKENS = "function_call_tokens"
    FUNCTION_OUTPUT_TOKENS = "function_output_tokens"
    REASONING_SUMMARY_TOKENS = "reasoning_summary_tokens"
    MESSAGE_ITEM_COUNT = "message_item_count"
    FUNCTION_CALL_ITEM_COUNT = "function_call_item_count"
    FUNCTION_OUTPUT_ITEM_COUNT = "function_output_item_count"
    REASONING_ITEM_COUNT = "reasoning_item_count"
    MEDIA_COUNT = "media_count"
    OPAQUE_REASONING_BYTES = "opaque_reasoning_bytes"
    MEDIA_DECODED_BYTES = "media_decoded_bytes"
    MEDIA_PIXEL_COUNT = "media_pixel_count"
    PDF_PAGES = "pdf_pages"
    UNKNOWN_ITEM_COUNT = "unknown_item_count"
    UNKNOWN_JSON_BYTES = "unknown_json_bytes"


@dataclass(frozen=True, slots=True)
class FeatureValue:
    name: FeatureName
    present: bool
    value: int

    def __post_init__(self) -> None:
        _require_nonnegative_int("feature value", self.value)
        if not self.present and self.value != 0:
            raise ValueError("an absent feature must carry the neutral value zero")


@dataclass(frozen=True, slots=True)
class FeatureVector:
    values: tuple[FeatureValue, ...]

    def __post_init__(self) -> None:
        expected = tuple(FeatureName)
        actual = tuple(value.name for value in self.values)
        if actual != expected:
            raise ValueError("feature values must contain every FeatureName exactly once in enum order")

    @classmethod
    def from_observations(cls, observations: Mapping[FeatureName, int | None]) -> FeatureVector:
        expected = set(FeatureName)
        if set(observations) != expected:
            raise ValueError("feature observations must contain every FeatureName exactly once")
        return cls(
            tuple(
                FeatureValue(name=name, present=observations[name] is not None, value=observations[name] or 0)
                for name in FeatureName
            )
        )

    def get(self, name: FeatureName) -> FeatureValue:
        return self.values[tuple(FeatureName).index(name)]


@dataclass(frozen=True, slots=True)
class ProfileKey:
    item_kinds: tuple[str, ...]
    reasoning_origins: tuple[str, ...]
    media_kinds: tuple[str, ...]
    unknown_type_digests: tuple[str, ...]
    unknown_type_count: int
    unknown_type_overflow: bool
    has_previous_response_id: bool
    context_management_mode: str
    truncation_mode: str

    def __post_init__(self) -> None:
        _require_sorted_unique("item_kinds", self.item_kinds)
        _require_sorted_unique("reasoning_origins", self.reasoning_origins)
        _require_sorted_unique("media_kinds", self.media_kinds)
        _require_sorted_unique("unknown_type_digests", self.unknown_type_digests)
        if len(self.unknown_type_digests) > 8:
            raise ValueError("unknown_type_digests may contain at most eight values")
        for digest in self.unknown_type_digests:
            _require_sha256("unknown type digest", digest)
        _require_nonnegative_int("unknown_type_count", self.unknown_type_count)
        if self.unknown_type_overflow:
            if len(self.unknown_type_digests) != 8 or self.unknown_type_count <= 8:
                raise ValueError("unknown type overflow requires more than eight distinct types")
        elif self.unknown_type_count != len(self.unknown_type_digests):
            raise ValueError("all unknown type digests must be retained when overflow is false")
        if not self.context_management_mode or not self.truncation_mode:
            raise ValueError("profile modes must be non-empty")


@dataclass(frozen=True, slots=True)
class StructuralProfile:
    key: ProfileKey
    features: FeatureVector


@dataclass(frozen=True, slots=True)
class TokenComponent:
    kind: str
    tokens: int
    instances: int

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("token component kind must be non-empty")
        _require_nonnegative_int("component tokens", self.tokens)
        _require_nonnegative_int("component instances", self.instances)
        if self.instances == 0 and self.tokens != 0:
            raise ValueError("a component without instances cannot contain tokens")


@dataclass(frozen=True, slots=True)
class PrefixFingerprint:
    item_count: int
    digest: str

    def __post_init__(self) -> None:
        if type(self.item_count) is not int or self.item_count < 1:
            raise ValueError("prefix item_count must be a positive integer")
        _require_sha256("prefix digest", self.digest)


@dataclass(frozen=True, slots=True)
class EstimateFeatures:
    known_tokens: int
    components: tuple[TokenComponent, ...]
    profile_key: ProfileKey
    feature_vector: FeatureVector
    full_fingerprint: str
    context_fingerprint: str
    prefix_fingerprints: tuple[PrefixFingerprint, ...]
    low_confidence_reasons: tuple[str, ...]
    estimator_generation: int
    profile_schema_revision: int
    raw_sent_body_sha256: str | None = None

    def __post_init__(self) -> None:
        _require_nonnegative_int("known_tokens", self.known_tokens)
        kinds = tuple(component.kind for component in self.components)
        if kinds != tuple(sorted(set(kinds))):
            raise ValueError("token components must be sorted by unique kind")
        if sum(component.tokens for component in self.components) != self.known_tokens:
            raise ValueError("known_tokens must equal the sum of token components")
        known_total = self.feature_vector.get(FeatureName.KNOWN_TOTAL)
        if not known_total.present or known_total.value != self.known_tokens:
            raise ValueError("known_total feature must be present and equal known_tokens")
        _require_sha256("full_fingerprint", self.full_fingerprint)
        _require_sha256("context_fingerprint", self.context_fingerprint)
        if tuple(prefix.item_count for prefix in self.prefix_fingerprints) != tuple(
            range(1, len(self.prefix_fingerprints) + 1)
        ):
            raise ValueError("prefix fingerprints must be contiguous and one-based")
        _require_sorted_unique("low_confidence_reasons", self.low_confidence_reasons)
        if type(self.estimator_generation) is not int or self.estimator_generation < 1:
            raise ValueError("estimator_generation must be a positive integer")
        if type(self.profile_schema_revision) is not int or self.profile_schema_revision < 1:
            raise ValueError("profile_schema_revision must be a positive integer")
        if self.raw_sent_body_sha256 is not None:
            _require_sha256("raw_sent_body_sha256", self.raw_sent_body_sha256)


@dataclass(frozen=True, slots=True)
class LearningIdentity:
    actual_provider: str
    resolved_model: str
    endpoint: str
    wire_format: str
    tokenizer: str
    descriptor_fingerprint: str
    estimator_generation: int
    profile_schema_revision: int
    learning_epoch: int

    def __post_init__(self) -> None:
        if not all(
            (
                self.actual_provider,
                self.resolved_model,
                self.endpoint,
                self.wire_format,
                self.tokenizer,
            )
        ):
            raise ValueError("learning identity strings must be non-empty")
        _require_sha256("descriptor_fingerprint", self.descriptor_fingerprint)
        if type(self.estimator_generation) is not int or self.estimator_generation < 1:
            raise ValueError("estimator_generation must be a positive integer")
        if type(self.profile_schema_revision) is not int or self.profile_schema_revision < 1:
            raise ValueError("profile_schema_revision must be a positive integer")
        _require_nonnegative_int("learning_epoch", self.learning_epoch)


@dataclass(frozen=True, slots=True)
class SentRequestSnapshot:
    process_boot_id: str
    request_id: str
    attempt_index: int
    endpoint: str
    actual_provider: str
    resolved_model: str
    wire_format: str
    tokenizer: str
    descriptor_fingerprint: str
    raw_body_sha256: str
    body: bytes

    def __post_init__(self) -> None:
        if not self.process_boot_id or not self.request_id:
            raise ValueError("sample identity strings must be non-empty")
        _require_nonnegative_int("attempt_index", self.attempt_index)
        if not all(
            (
                self.endpoint,
                self.actual_provider,
                self.resolved_model,
                self.wire_format,
                self.tokenizer,
            )
        ):
            raise ValueError("sent request identity strings must be non-empty")
        _require_sha256("descriptor_fingerprint", self.descriptor_fingerprint)
        _require_sha256("raw_body_sha256", self.raw_body_sha256)
        supplied_body = cast(object, self.body)
        if isinstance(supplied_body, bytes):
            immutable_body = supplied_body
        elif isinstance(supplied_body, bytearray):
            immutable_body = bytes(supplied_body)
        elif isinstance(supplied_body, memoryview):
            immutable_body = supplied_body.tobytes()
        else:
            raise TypeError("body must be bytes-like")
        object.__setattr__(self, "body", immutable_body)
        if hashlib.sha256(immutable_body).hexdigest() != self.raw_body_sha256:
            raise ValueError("raw_body_sha256 must identify body exactly")

    @property
    def sample_key(self) -> SampleKey:
        return (self.process_boot_id, self.request_id, self.attempt_index)


@dataclass(frozen=True, slots=True)
class CompletedTokenSample:
    sent: SentRequestSnapshot
    actual_input_tokens: int
    terminal_event_type: Literal["response.completed", "response.incomplete"]

    def __post_init__(self) -> None:
        _require_nonnegative_int("actual_input_tokens", self.actual_input_tokens)


class PredictionMethod(StrEnum):
    HISTORY_EXACT = "history-exact"
    HISTORY_PREFIX = "history-prefix"
    PROFILE_CALIBRATED = "profile-calibrated"
    COLD_START = "cold-start"


@dataclass(frozen=True, slots=True)
class TokenPrediction:
    identity: LearningIdentity
    profile_key: ProfileKey
    method: PredictionMethod
    unscaled_tokens: float
    sample_count: int
    history_revision: int
    learning_epoch: int
    low_confidence_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.unscaled_tokens):
            raise ValueError("unscaled_tokens must be finite")
        _require_nonnegative_int("sample_count", self.sample_count)
        _require_nonnegative_int("history_revision", self.history_revision)
        _require_nonnegative_int("learning_epoch", self.learning_epoch)
        if self.learning_epoch != self.identity.learning_epoch:
            raise ValueError("prediction epoch must match its learning identity")
        _require_sorted_unique("low_confidence_reasons", self.low_confidence_reasons)


@dataclass(frozen=True, slots=True)
class PredictionRecord:
    sample_key: SampleKey
    selected: TokenPrediction
    candidates: tuple[TokenPrediction, ...]

    def __post_init__(self) -> None:
        _validate_sample_key(self.sample_key)
        methods = tuple(candidate.method for candidate in self.candidates)
        if len(methods) != len(set(methods)):
            raise ValueError("prediction candidates must have unique methods")
        if self.selected not in self.candidates:
            raise ValueError("selected prediction must be one of the candidates")
        for candidate in self.candidates:
            if candidate.identity.estimator_generation != self.selected.identity.estimator_generation:
                raise ValueError("prediction candidates must share one estimator generation")
            if candidate.identity.profile_schema_revision != self.selected.identity.profile_schema_revision:
                raise ValueError("prediction candidates must share one profile schema revision")
            if candidate.learning_epoch != self.selected.learning_epoch:
                raise ValueError("prediction candidates must share one learning epoch")
            if candidate.identity != self.selected.identity:
                raise ValueError("prediction candidates must share one learning identity")
            if candidate.profile_key != self.selected.profile_key:
                raise ValueError("prediction candidates must share one profile key")
            if candidate.history_revision != self.selected.history_revision:
                raise ValueError("prediction candidates must share one history revision")


@dataclass(frozen=True, slots=True)
class PredictionEvaluation:
    sample_key: SampleKey
    method: PredictionMethod
    predicted_tokens: float
    actual_tokens: int
    absolute_error: float
    signed_relative_error: float | None
    absolute_percentage_error: float | None

    def __post_init__(self) -> None:
        _validate_sample_key(self.sample_key)
        if not math.isfinite(self.predicted_tokens):
            raise ValueError("predicted_tokens must be finite")
        _require_nonnegative_int("actual_tokens", self.actual_tokens)
        if not math.isfinite(self.absolute_error) or self.absolute_error < 0:
            raise ValueError("absolute_error must be finite and nonnegative")
        expected_absolute = abs(self.predicted_tokens - self.actual_tokens)
        if not math.isclose(self.absolute_error, expected_absolute, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("absolute_error must equal the absolute prediction error")
        if self.actual_tokens == 0:
            if self.signed_relative_error is not None or self.absolute_percentage_error is not None:
                raise ValueError("relative errors must be absent when actual_tokens is zero")
            return
        if self.signed_relative_error is None or self.absolute_percentage_error is None:
            raise ValueError("positive actual_tokens require both relative error metrics")
        if not math.isfinite(self.signed_relative_error):
            raise ValueError("signed_relative_error must be finite")
        if not math.isfinite(self.absolute_percentage_error) or self.absolute_percentage_error < 0:
            raise ValueError("absolute_percentage_error must be finite and nonnegative")
        expected_signed_relative = (self.predicted_tokens - self.actual_tokens) / self.actual_tokens
        if not math.isclose(
            self.signed_relative_error,
            expected_signed_relative,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("signed_relative_error must match predicted_tokens and actual_tokens")
        if not math.isclose(
            self.absolute_percentage_error,
            abs(expected_signed_relative),
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("absolute_percentage_error must match the signed relative error")


@dataclass(frozen=True, slots=True)
class StoredSample:
    sample_key: SampleKey
    identity: LearningIdentity
    features: EstimateFeatures
    actual_input_tokens: int
    raw_body_sha256: str
    observed_at: str

    def __post_init__(self) -> None:
        _validate_sample_key(self.sample_key)
        _require_nonnegative_int("actual_input_tokens", self.actual_input_tokens)
        _require_sha256("raw_body_sha256", self.raw_body_sha256)
        if self.identity.estimator_generation != self.features.estimator_generation:
            raise ValueError("stored sample estimator generation must match its features")
        if self.identity.profile_schema_revision != self.features.profile_schema_revision:
            raise ValueError("stored sample profile schema revision must match its features")
        if not self.observed_at:
            raise ValueError("observed_at must be non-empty")


@dataclass(frozen=True, slots=True)
class ExactAnchor:
    identity: LearningIdentity
    full_fingerprint: str
    actual_tokens: tuple[int, ...]
    sample_keys: tuple[SampleKey, ...]

    def __post_init__(self) -> None:
        _require_sha256("full_fingerprint", self.full_fingerprint)
        if not self.actual_tokens or len(self.actual_tokens) > 5:
            raise ValueError("exact anchor must retain between one and five actuals")
        for actual in self.actual_tokens:
            _require_nonnegative_int("actual token count", actual)
        if len(self.sample_keys) != len(self.actual_tokens):
            raise ValueError("exact anchor actuals and sample keys must align")
        for sample_key in self.sample_keys:
            _validate_sample_key(sample_key)


@dataclass(frozen=True, slots=True)
class PrefixAnchor:
    identity: LearningIdentity
    context_fingerprint: str
    prefix_fingerprint: PrefixFingerprint
    actual_tokens: int
    sample_key: SampleKey
    observed_at: str

    def __post_init__(self) -> None:
        _require_sha256("context_fingerprint", self.context_fingerprint)
        _require_nonnegative_int("actual_tokens", self.actual_tokens)
        _validate_sample_key(self.sample_key)
        if not self.observed_at:
            raise ValueError("observed_at must be non-empty")


@dataclass(frozen=True, slots=True)
class LearningSnapshot:
    identity: LearningIdentity
    revision: int
    active_epoch: int
    samples: tuple[StoredSample, ...] = ()
    exact_anchors: tuple[ExactAnchor, ...] = ()
    prefix_anchors: tuple[PrefixAnchor, ...] = ()

    def __post_init__(self) -> None:
        _require_nonnegative_int("revision", self.revision)
        _require_nonnegative_int("active_epoch", self.active_epoch)


@dataclass(frozen=True, slots=True)
class DriftObservation:
    identity: LearningIdentity
    kind: DriftKind
    previous_epoch: int
    new_epoch: int
    evidence_count: int
    reason: str

    def __post_init__(self) -> None:
        _require_nonnegative_int("previous_epoch", self.previous_epoch)
        _require_nonnegative_int("new_epoch", self.new_epoch)
        _require_nonnegative_int("evidence_count", self.evidence_count)
        if self.new_epoch <= self.previous_epoch:
            raise ValueError("drift must advance the learning epoch")
        if not self.reason:
            raise ValueError("drift reason must be non-empty")


class LearningOfferOutcome(StrEnum):
    QUEUED = "queued"
    QUEUE_FULL = "queue-full"
    DUPLICATE = "duplicate"
    NOT_ACCEPTING = "not-accepting"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class TokenLearningObservation:
    sample_key: SampleKey
    outcome: LearningObservationOutcome
    evaluations: tuple[PredictionEvaluation, ...] = ()
    revision: int | None = None
    learning_epoch: int | None = None
    drift: DriftObservation | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_sample_key(self.sample_key)
        if self.revision is not None:
            _require_nonnegative_int("revision", self.revision)
        if self.learning_epoch is not None:
            _require_nonnegative_int("learning_epoch", self.learning_epoch)
        if self.outcome == "committed" and (self.revision is None or self.learning_epoch is None):
            raise ValueError("a committed observation requires revision and epoch")
        if self.outcome == "failed" and not self.detail:
            raise ValueError("a failed observation requires detail")


@dataclass(frozen=True, slots=True)
class LearningUpdate:
    sample: StoredSample
    prediction_record: PredictionRecord
    evaluations: tuple[PredictionEvaluation, ...]
    observation: TokenLearningObservation
    drift: DriftObservation | None = None

    def __post_init__(self) -> None:
        if self.sample.sample_key != self.prediction_record.sample_key:
            raise ValueError("learning update sample and prediction record must align")
        if any(evaluation.sample_key != self.sample.sample_key for evaluation in self.evaluations):
            raise ValueError("learning update evaluations must align with the sample")
        if self.observation.sample_key != self.sample.sample_key:
            raise ValueError("learning update observation must align with the sample")


def _validate_sample_key(sample_key: SampleKey) -> None:
    if len(sample_key) != 3:
        raise ValueError("sample key must have three members")
    process_boot_id, request_id, attempt_index = sample_key
    if not process_boot_id or not request_id:
        raise ValueError("sample key strings must be non-empty")
    _require_nonnegative_int("sample key attempt index", attempt_index)
