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


def _require_positive_int(name: str, value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


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
class FixedContextContribution:
    visible_tokens: int
    framing_tokens: int
    prior_residual_tokens: float

    def __post_init__(self) -> None:
        _require_nonnegative_int("fixed context visible_tokens", self.visible_tokens)
        _require_nonnegative_int("fixed context framing_tokens", self.framing_tokens)
        if self.framing_tokens % 4:
            raise ValueError("fixed context framing_tokens must be a multiple of four")
        if not math.isfinite(self.prior_residual_tokens):
            raise ValueError("fixed context prior_residual_tokens must be finite")

    @property
    def known_tokens(self) -> int:
        return self.visible_tokens + self.framing_tokens


@dataclass(frozen=True, slots=True)
class InputItemContribution:
    visible_tokens: int
    item_framing_tokens: int
    nested_framing_tokens: int
    capability_visual_tokens: int | None
    prior_residual_tokens: float

    def __post_init__(self) -> None:
        _require_nonnegative_int("item visible_tokens", self.visible_tokens)
        if self.item_framing_tokens != 4:
            raise ValueError("item_framing_tokens must equal four")
        _require_nonnegative_int("item nested_framing_tokens", self.nested_framing_tokens)
        if self.nested_framing_tokens % 4:
            raise ValueError("item nested_framing_tokens must be a multiple of four")
        if self.capability_visual_tokens is not None:
            _require_nonnegative_int(
                "item capability_visual_tokens", self.capability_visual_tokens
            )
        if not math.isfinite(self.prior_residual_tokens):
            raise ValueError("item prior_residual_tokens must be finite")

    @property
    def known_tokens(self) -> int:
        return self.visible_tokens + self.item_framing_tokens + self.nested_framing_tokens


@dataclass(frozen=True, slots=True)
class EstimateFeatures:
    known_tokens: int
    capability_visual_tokens: int | None
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
    fixed_context_contribution: FixedContextContribution = FixedContextContribution(0, 0, 0.0)
    input_item_contributions: tuple[InputItemContribution, ...] = ()

    def __post_init__(self) -> None:
        _require_nonnegative_int("known_tokens", self.known_tokens)
        if self.capability_visual_tokens is not None:
            _require_nonnegative_int("capability_visual_tokens", self.capability_visual_tokens)
        kinds = tuple(component.kind for component in self.components)
        if kinds != tuple(sorted(set(kinds))):
            raise ValueError("token components must be sorted by unique kind")
        if sum(component.tokens for component in self.components) != self.known_tokens:
            raise ValueError("known_tokens must equal the sum of token components")
        if self.known_tokens != self.fixed_context_contribution.known_tokens + sum(
            contribution.known_tokens for contribution in self.input_item_contributions
        ):
            raise ValueError("known_tokens must equal fixed and input contribution totals")
        if len(self.input_item_contributions) != len(self.prefix_fingerprints):
            raise ValueError("input contributions must align with prefix fingerprints")
        expected_visual: int | None
        if any(
            contribution.capability_visual_tokens is None
            for contribution in self.input_item_contributions
        ):
            expected_visual = None
        else:
            expected_visual = sum(
                cast(int, contribution.capability_visual_tokens)
                for contribution in self.input_item_contributions
            )
        if self.capability_visual_tokens != expected_visual:
            raise ValueError("capability visual tokens must equal item contribution aggregate")
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


class PredictionCandidateVariant(StrEnum):
    MEDIAN = "median"
    DETERMINISTIC = "deterministic"
    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"


_LEGAL_PREDICTION_CANDIDATE_PAIRS = frozenset(
    {
        (PredictionMethod.HISTORY_EXACT, PredictionCandidateVariant.MEDIAN),
        (PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.DETERMINISTIC),
        (PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.ADDITIVE),
        (PredictionMethod.HISTORY_PREFIX, PredictionCandidateVariant.MULTIPLICATIVE),
        (PredictionMethod.PROFILE_CALIBRATED, PredictionCandidateVariant.ADDITIVE),
        (PredictionMethod.PROFILE_CALIBRATED, PredictionCandidateVariant.MULTIPLICATIVE),
        (PredictionMethod.COLD_START, PredictionCandidateVariant.DETERMINISTIC),
    }
)


@dataclass(frozen=True, slots=True)
class PredictionCandidateKey:
    method: PredictionMethod
    variant: PredictionCandidateVariant

    def __post_init__(self) -> None:
        if type(self.method) is not PredictionMethod or type(self.variant) is not PredictionCandidateVariant:
            raise ValueError("prediction candidate method and variant must be closed enums")
        if (self.method, self.variant) not in _LEGAL_PREDICTION_CANDIDATE_PAIRS:
            raise ValueError("prediction candidate method and variant are not a legal pair")


@dataclass(frozen=True, slots=True)
class MethodChampion:
    candidate_key: PredictionCandidateKey
    eligible_for_selection: bool

    def __post_init__(self) -> None:
        if type(self.candidate_key) is not PredictionCandidateKey:
            raise ValueError("method champion candidate key must be closed")
        if type(self.eligible_for_selection) is not bool:
            raise ValueError("method champion eligibility must be a boolean")
        if (
            self.candidate_key.method in {PredictionMethod.HISTORY_EXACT, PredictionMethod.COLD_START}
            and not self.eligible_for_selection
        ):
            raise ValueError("represented exact and cold-start champions must be eligible")

    @property
    def method(self) -> PredictionMethod:
        return self.candidate_key.method


class VisualTokenFormulaKind(StrEnum):
    SYNTHETIC_UNRESIZED_PATCH_GRID_V1 = "synthetic-unresized-patch-grid-v1"


@dataclass(frozen=True, slots=True)
class SyntheticUnresizedPatchGridFormula:
    revision: int
    patch_width: int
    patch_height: int
    kind: VisualTokenFormulaKind = VisualTokenFormulaKind.SYNTHETIC_UNRESIZED_PATCH_GRID_V1

    def __post_init__(self) -> None:
        if self.kind is not VisualTokenFormulaKind.SYNTHETIC_UNRESIZED_PATCH_GRID_V1:
            raise ValueError("visual formula kind must be the closed synthetic unresized variant")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("visual formula revision must be a positive integer")
        if type(self.patch_width) is not int or self.patch_width < 1:
            raise ValueError("visual patch width must be a positive integer")
        if type(self.patch_height) is not int or self.patch_height < 1:
            raise ValueError("visual patch height must be a positive integer")


type VisualTokenFormula = SyntheticUnresizedPatchGridFormula


@dataclass(frozen=True, slots=True)
class TokenizationCapabilities:
    visual_formula: VisualTokenFormula | None = None

    def __post_init__(self) -> None:
        if self.visual_formula is not None and type(self.visual_formula) is not SyntheticUnresizedPatchGridFormula:
            raise ValueError("visual formula must be a closed tokenization formula variant")


class StoreCancellationPhase(StrEnum):
    OPEN = "open"
    PRAGMA = "pragma"
    BEGIN = "begin"
    READ = "read"
    CURSOR_CLOSE = "cursor-close"
    TRANSITION = "transition"
    INSERT = "insert"
    UPDATE = "update"
    COMMIT = "commit"
    ROLLBACK = "rollback"
    CHECKPOINT = "checkpoint"
    CONNECTION_CLOSE = "connection-close"
    BUSY_RETRY = "busy-retry"
    LOCK_WAIT = "lock-wait"
    CLOSE_LOCK_WAIT = "close-lock-wait"
    CLOSE_WAIT = "close-wait"


class LearningReasonCode(StrEnum):
    SAMPLE_COMMITTED = "sample-committed"
    DUPLICATE_SAMPLE = "duplicate-sample"
    SAMPLE_INELIGIBLE = "sample-ineligible"
    MISSING_USAGE = "missing-usage"
    INCONSISTENT_USAGE = "inconsistent-usage"
    QUEUE_FULL = "queue-full"
    ANALYSIS_FAILED = "analysis-failed"
    OPERATION_CANCELLED = "operation-cancelled"
    STORE_UNAVAILABLE = "store-unavailable"
    MIGRATION_FAILED = "migration-failed"
    COMMIT_FAILED = "commit-failed"
    PRUNED = "pruned"


class DriftReasonCode(StrEnum):
    PROFILE_ERROR_REGRESSION = "profile-error-regression"
    EXACT_COUNT_MISMATCH = "exact-count-mismatch"
    IDENTITY_VERSION_CHANGE = "identity-version-change"


class AnalysisFailureStage(StrEnum):
    FEATURE_EXTRACTION = "feature-extraction"
    PREDICTION = "prediction"
    EVALUATION = "evaluation"
    PERSISTENCE = "persistence"


@dataclass(frozen=True, slots=True)
class SampleCommittedMetadata:
    actual_input_tokens: int

    def __post_init__(self) -> None:
        _require_nonnegative_int("actual_input_tokens", self.actual_input_tokens)


@dataclass(frozen=True, slots=True)
class DuplicateSampleMetadata:
    existing_revision: int

    def __post_init__(self) -> None:
        _require_nonnegative_int("existing_revision", self.existing_revision)


@dataclass(frozen=True, slots=True)
class SampleIneligibleMetadata:
    pass


@dataclass(frozen=True, slots=True)
class MissingUsageMetadata:
    pass


@dataclass(frozen=True, slots=True)
class InconsistentUsageMetadata:
    pass


@dataclass(frozen=True, slots=True)
class QueueFullMetadata:
    pending_items: int
    pending_body_bytes: int

    def __post_init__(self) -> None:
        _require_nonnegative_int("pending_items", self.pending_items)
        _require_nonnegative_int("pending_body_bytes", self.pending_body_bytes)


@dataclass(frozen=True, slots=True)
class AnalysisFailedMetadata:
    stage: AnalysisFailureStage

    def __post_init__(self) -> None:
        if type(self.stage) is not AnalysisFailureStage:
            raise ValueError("analysis failure stage must be a closed enum")


@dataclass(frozen=True, slots=True)
class OperationCancelledMetadata:
    phase: StoreCancellationPhase

    def __post_init__(self) -> None:
        if type(self.phase) is not StoreCancellationPhase:
            raise ValueError("cancellation phase must be a closed enum")


@dataclass(frozen=True, slots=True)
class StoreUnavailableMetadata:
    pass


@dataclass(frozen=True, slots=True)
class MigrationFailedMetadata:
    pass


@dataclass(frozen=True, slots=True)
class CommitFailedMetadata:
    pass


@dataclass(frozen=True, slots=True)
class PrunedMetadata:
    pruned_sample_count: int

    def __post_init__(self) -> None:
        _require_nonnegative_int("pruned_sample_count", self.pruned_sample_count)


type LearningReasonMetadata = (
    SampleCommittedMetadata
    | DuplicateSampleMetadata
    | SampleIneligibleMetadata
    | MissingUsageMetadata
    | InconsistentUsageMetadata
    | QueueFullMetadata
    | AnalysisFailedMetadata
    | OperationCancelledMetadata
    | StoreUnavailableMetadata
    | MigrationFailedMetadata
    | CommitFailedMetadata
    | PrunedMetadata
)


@dataclass(frozen=True, slots=True)
class ProfileErrorRegressionMetadata:
    reference_count: int
    recent_count: int

    def __post_init__(self) -> None:
        _require_nonnegative_int("reference_count", self.reference_count)
        _require_nonnegative_int("recent_count", self.recent_count)


@dataclass(frozen=True, slots=True)
class ExactCountMismatchMetadata:
    consecutive_count: int

    def __post_init__(self) -> None:
        _require_nonnegative_int("consecutive_count", self.consecutive_count)


@dataclass(frozen=True, slots=True)
class IdentityVersionChangeMetadata:
    previous_generation: int
    new_generation: int

    def __post_init__(self) -> None:
        if type(self.previous_generation) is not int or self.previous_generation < 1:
            raise ValueError("previous_generation must be a positive integer")
        if type(self.new_generation) is not int or self.new_generation < 1:
            raise ValueError("new_generation must be a positive integer")
        if self.previous_generation == self.new_generation:
            raise ValueError("identity version change must change the generation")


type DriftReasonMetadata = (
    ProfileErrorRegressionMetadata | ExactCountMismatchMetadata | IdentityVersionChangeMetadata
)


class AnchorKind(StrEnum):
    EXACT = "exact"
    PREFIX = "prefix"


@dataclass(frozen=True, slots=True)
class AnchorUseIntent:
    kind: AnchorKind
    identity: LearningIdentity
    learning_epoch: int
    fingerprint: str
    source_sample_keys: tuple[SampleKey, ...]

    def __post_init__(self) -> None:
        if type(self.kind) is not AnchorKind:
            raise ValueError("anchor kind must be a closed enum")
        _require_nonnegative_int("learning_epoch", self.learning_epoch)
        if self.learning_epoch != self.identity.learning_epoch:
            raise ValueError("anchor-use epoch must match its learning identity")
        _require_sha256("anchor-use fingerprint", self.fingerprint)
        if not self.source_sample_keys:
            raise ValueError("anchor-use intent requires source sample keys")
        if len(self.source_sample_keys) != len(set(self.source_sample_keys)):
            raise ValueError("anchor-use source sample keys must be unique")
        if self.kind is AnchorKind.EXACT and len(self.source_sample_keys) > 5:
            raise ValueError("exact anchor-use intent may contain at most five source samples")
        if self.kind is AnchorKind.PREFIX and len(self.source_sample_keys) != 1:
            raise ValueError("prefix anchor-use intent requires exactly one source sample")
        for sample_key in self.source_sample_keys:
            _validate_sample_key(sample_key)


class AnchorUseOutcome(StrEnum):
    RECORDED = "recorded"
    PRUNED = "pruned"


@dataclass(frozen=True, slots=True)
class TokenPrediction:
    identity: LearningIdentity
    profile_key: ProfileKey
    method: PredictionMethod
    candidate_key: PredictionCandidateKey
    unscaled_tokens: float
    sample_count: int
    history_revision: int
    learning_epoch: int
    low_confidence_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.method) is not PredictionMethod:
            raise ValueError("prediction method must be a closed enum")
        if self.candidate_key.method is not self.method:
            raise ValueError("prediction method must match its candidate key")
        if not math.isfinite(self.unscaled_tokens):
            raise ValueError("unscaled_tokens must be finite")
        _require_nonnegative_int("sample_count", self.sample_count)
        _require_nonnegative_int("history_revision", self.history_revision)
        _require_nonnegative_int("learning_epoch", self.learning_epoch)
        if self.learning_epoch != self.identity.learning_epoch:
            raise ValueError("prediction epoch must match its learning identity")
        _require_sorted_unique("low_confidence_reasons", self.low_confidence_reasons)


@dataclass(frozen=True, slots=True)
class PredictionDecision:
    prediction: TokenPrediction
    anchor_use_intent: AnchorUseIntent | None

    def __post_init__(self) -> None:
        method = self.prediction.method
        intent = self.anchor_use_intent
        if method is PredictionMethod.HISTORY_EXACT:
            expected_kind = AnchorKind.EXACT
        elif method is PredictionMethod.HISTORY_PREFIX:
            expected_kind = AnchorKind.PREFIX
        else:
            expected_kind = None
        if expected_kind is None:
            if intent is not None:
                raise ValueError("profile and cold-start decisions must not carry anchor-use intent")
            return
        if intent is None or intent.kind is not expected_kind:
            raise ValueError("history decisions require the matching anchor-use intent kind")
        if intent.identity != self.prediction.identity:
            raise ValueError("decision intent identity must match its prediction")
        if intent.learning_epoch != self.prediction.learning_epoch:
            raise ValueError("decision intent epoch must match its prediction")


@dataclass(frozen=True, slots=True)
class PredictionRecord:
    sample_key: SampleKey
    selected_key: PredictionCandidateKey
    candidates: tuple[TokenPrediction, ...]
    method_champions: tuple[MethodChampion, ...]

    def __post_init__(self) -> None:
        _validate_sample_key(self.sample_key)
        if not self.candidates:
            raise ValueError("prediction record requires candidates")
        candidate_keys = tuple(candidate.candidate_key for candidate in self.candidates)
        if len(candidate_keys) != len(set(candidate_keys)):
            raise ValueError("prediction candidates must have unique candidate keys")
        candidate_by_key = dict(zip(candidate_keys, self.candidates, strict=True))
        cold_key = PredictionCandidateKey(
            PredictionMethod.COLD_START,
            PredictionCandidateVariant.DETERMINISTIC,
        )
        if cold_key not in candidate_by_key:
            raise ValueError("prediction record must contain the cold-start candidate")
        first = self.candidates[0]
        for candidate in self.candidates:
            if candidate.identity.estimator_generation != first.identity.estimator_generation:
                raise ValueError("prediction candidates must share one estimator generation")
            if candidate.identity.profile_schema_revision != first.identity.profile_schema_revision:
                raise ValueError("prediction candidates must share one profile schema revision")
            if candidate.learning_epoch != first.learning_epoch:
                raise ValueError("prediction candidates must share one learning epoch")
            if candidate.identity != first.identity:
                raise ValueError("prediction candidates must share one learning identity")
            if candidate.profile_key != first.profile_key:
                raise ValueError("prediction candidates must share one profile key")
            if candidate.history_revision != first.history_revision:
                raise ValueError("prediction candidates must share one history revision")
        represented_methods = {candidate.method for candidate in self.candidates}
        champion_methods = tuple(champion.method for champion in self.method_champions)
        if len(champion_methods) != len(set(champion_methods)):
            raise ValueError("represented methods must have unique champions")
        if set(champion_methods) != represented_methods:
            raise ValueError("method champions must exactly cover represented methods")
        champion_by_method = {champion.method: champion for champion in self.method_champions}
        for method, champion in champion_by_method.items():
            if champion.candidate_key not in candidate_by_key:
                raise ValueError("method champion must reference an existing candidate")
            if champion.candidate_key.method is not method:
                raise ValueError("method champion must reference a candidate from its method")
        eligible = [
            champion_by_method[method]
            for method in PredictionMethod
            if method in champion_by_method and champion_by_method[method].eligible_for_selection
        ]
        if not eligible or self.selected_key != eligible[0].candidate_key:
            raise ValueError("selected key must be the first eligible represented method champion")

    @property
    def selected(self) -> TokenPrediction:
        return next(candidate for candidate in self.candidates if candidate.candidate_key == self.selected_key)


@dataclass(frozen=True, slots=True)
class PredictionEvaluation:
    sample_key: SampleKey
    method: PredictionMethod
    candidate_key: PredictionCandidateKey
    predicted_tokens: float
    actual_tokens: int
    absolute_error: float
    signed_relative_error: float | None
    absolute_percentage_error: float | None

    def __post_init__(self) -> None:
        _validate_sample_key(self.sample_key)
        if type(self.method) is not PredictionMethod or self.candidate_key.method is not self.method:
            raise ValueError("evaluation method must match its candidate key")
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
    observed_at_us: int
    committed_order: int | None = None

    def __post_init__(self) -> None:
        _validate_sample_key(self.sample_key)
        _require_nonnegative_int("actual_input_tokens", self.actual_input_tokens)
        _require_sha256("raw_body_sha256", self.raw_body_sha256)
        if self.identity.estimator_generation != self.features.estimator_generation:
            raise ValueError("stored sample estimator generation must match its features")
        if self.identity.profile_schema_revision != self.features.profile_schema_revision:
            raise ValueError("stored sample profile schema revision must match its features")
        if (
            self.features.raw_sent_body_sha256 is not None
            and self.features.raw_sent_body_sha256 != self.raw_body_sha256
        ):
            raise ValueError("stored sample raw body digest must match its features")
        _require_nonnegative_int("observed_at_us", self.observed_at_us)
        if self.committed_order is not None:
            _require_positive_int("committed_order", self.committed_order)


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
    observed_at_us: int

    def __post_init__(self) -> None:
        _require_sha256("context_fingerprint", self.context_fingerprint)
        _require_nonnegative_int("actual_tokens", self.actual_tokens)
        _validate_sample_key(self.sample_key)
        _require_nonnegative_int("observed_at_us", self.observed_at_us)


class PrefixCheckpointMode(StrEnum):
    ELIGIBLE = "eligible"
    DEMOTED = "demoted"


@dataclass(frozen=True, slots=True)
class PendingPrefixChampionErrorTriple:
    prefix_absolute_percentage_error: float
    profile_absolute_percentage_error: float | None
    cold_start_absolute_percentage_error: float

    def __post_init__(self) -> None:
        for name, value in (
            ("prefix absolute percentage error", self.prefix_absolute_percentage_error),
            ("cold-start absolute percentage error", self.cold_start_absolute_percentage_error),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.profile_absolute_percentage_error is not None and (
            not math.isfinite(self.profile_absolute_percentage_error)
            or self.profile_absolute_percentage_error < 0
        ):
            raise ValueError("profile absolute percentage error must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class PrefixChampionErrorTriple:
    prefix_absolute_percentage_error: float
    profile_absolute_percentage_error: float | None
    cold_start_absolute_percentage_error: float
    committed_order: int

    def __post_init__(self) -> None:
        PendingPrefixChampionErrorTriple(
            self.prefix_absolute_percentage_error,
            self.profile_absolute_percentage_error,
            self.cold_start_absolute_percentage_error,
        )
        _require_positive_int("prefix evidence committed_order", self.committed_order)

    @classmethod
    def from_pending(
        cls, pending: PendingPrefixChampionErrorTriple, committed_order: int
    ) -> PrefixChampionErrorTriple:
        return cls(
            pending.prefix_absolute_percentage_error,
            pending.profile_absolute_percentage_error,
            pending.cold_start_absolute_percentage_error,
            committed_order,
        )


@dataclass(frozen=True, slots=True)
class PrefixEligibilityCheckpoint:
    profile_key: ProfileKey
    mode: PrefixCheckpointMode
    evidence: tuple[PrefixChampionErrorTriple, ...]
    state_revision: int
    updated_order: int

    def __post_init__(self) -> None:
        if type(self.mode) is not PrefixCheckpointMode:
            raise ValueError("prefix checkpoint mode must be closed")
        _require_positive_int("prefix checkpoint state_revision", self.state_revision)
        _require_positive_int("prefix checkpoint updated_order", self.updated_order)
        expected_count = 16 if self.mode is PrefixCheckpointMode.ELIGIBLE else 8
        if len(self.evidence) > expected_count:
            raise ValueError("prefix checkpoint evidence exceeds its mode bound")
        if any(type(value) is not PrefixChampionErrorTriple for value in self.evidence):
            raise ValueError("public checkpoint evidence must be persistent")
        orders = tuple(value.committed_order for value in self.evidence)
        if orders != tuple(sorted(orders)) or len(orders) != len(set(orders)):
            raise ValueError("prefix checkpoint evidence order must be strictly increasing")


@dataclass(frozen=True, slots=True)
class NoPrefixCheckpointChange:
    pass


@dataclass(frozen=True, slots=True)
class ReplacePrefixCheckpoint:
    profile_key: ProfileKey
    mode: PrefixCheckpointMode
    evidence: tuple[PrefixChampionErrorTriple | PendingPrefixChampionErrorTriple, ...]
    expected_prior_state_revision: int | None

    def __post_init__(self) -> None:
        if type(self.mode) is not PrefixCheckpointMode:
            raise ValueError("prefix checkpoint mode must be closed")
        if self.expected_prior_state_revision is not None:
            _require_positive_int(
                "prefix checkpoint expected_prior_state_revision",
                self.expected_prior_state_revision,
            )
        limit = 16 if self.mode is PrefixCheckpointMode.ELIGIBLE else 8
        if len(self.evidence) > limit:
            raise ValueError("prefix checkpoint evidence exceeds its mode bound")
        pending_positions = [
            index
            for index, value in enumerate(self.evidence)
            if type(value) is PendingPrefixChampionErrorTriple
        ]
        if len(pending_positions) > 1 or (
            pending_positions and pending_positions != [len(self.evidence) - 1]
        ):
            raise ValueError("pending prefix evidence must be the unique tail")
        historical = self.evidence[: pending_positions[0] if pending_positions else len(self.evidence)]
        if any(type(value) is not PrefixChampionErrorTriple for value in historical):
            raise ValueError("prefix checkpoint history must be persistent evidence")
        orders = tuple(cast(PrefixChampionErrorTriple, value).committed_order for value in historical)
        if orders != tuple(sorted(orders)) or len(orders) != len(set(orders)):
            raise ValueError("prefix checkpoint history must have strictly increasing order")


@dataclass(frozen=True, slots=True)
class DeleteRecoveredPrefixCheckpoint:
    profile_key: ProfileKey
    expected_prior_state_revision: int

    def __post_init__(self) -> None:
        _require_positive_int(
            "prefix checkpoint expected_prior_state_revision",
            self.expected_prior_state_revision,
        )


type PrefixCheckpointCommand = (
    NoPrefixCheckpointChange
    | ReplacePrefixCheckpoint
    | DeleteRecoveredPrefixCheckpoint
)


class PrefixCheckpointNotAttemptedReason(StrEnum):
    DUPLICATE_SAMPLE = "duplicate-sample"
    SAMPLE_REJECTED = "sample-rejected"
    FAILURE_BEFORE_POLICY = "failure-before-policy"


class PrefixCheckpointCapacityReason(StrEnum):
    PREFIX_CHECKPOINT_CAPACITY = "prefix-checkpoint-capacity"


@dataclass(frozen=True, slots=True)
class PrefixCheckpointApplied:
    profile_key: ProfileKey
    state_revision: int
    updated_order: int

    def __post_init__(self) -> None:
        _require_positive_int("prefix checkpoint state_revision", self.state_revision)
        _require_positive_int("prefix checkpoint updated_order", self.updated_order)


@dataclass(frozen=True, slots=True)
class PrefixCheckpointDeleted:
    profile_key: ProfileKey
    state_revision: int
    updated_order: int

    def __post_init__(self) -> None:
        _require_positive_int("prefix checkpoint state_revision", self.state_revision)
        _require_positive_int("prefix checkpoint updated_order", self.updated_order)


@dataclass(frozen=True, slots=True)
class PrefixCheckpointCapacityRejected:
    profile_key: ProfileKey
    reason: PrefixCheckpointCapacityReason

    def __post_init__(self) -> None:
        if self.reason is not PrefixCheckpointCapacityReason.PREFIX_CHECKPOINT_CAPACITY:
            raise ValueError("prefix checkpoint capacity reason must be closed")


@dataclass(frozen=True, slots=True)
class PrefixCheckpointCapacityRolledOver:
    profile_key: ProfileKey
    previous_epoch: int
    new_epoch: int
    reason: PrefixCheckpointCapacityReason

    def __post_init__(self) -> None:
        _require_nonnegative_int("prefix checkpoint previous_epoch", self.previous_epoch)
        _require_nonnegative_int("prefix checkpoint new_epoch", self.new_epoch)
        if self.new_epoch != self.previous_epoch + 1:
            raise ValueError("prefix checkpoint rollover must advance one epoch")
        if self.reason is not PrefixCheckpointCapacityReason.PREFIX_CHECKPOINT_CAPACITY:
            raise ValueError("prefix checkpoint capacity reason must be closed")


@dataclass(frozen=True, slots=True)
class PrefixCheckpointNotAttempted:
    reason: PrefixCheckpointNotAttemptedReason

    def __post_init__(self) -> None:
        if type(self.reason) is not PrefixCheckpointNotAttemptedReason:
            raise ValueError("prefix checkpoint not-attempted reason must be closed")


@dataclass(frozen=True, slots=True)
class PrefixCheckpointNotCommitted:
    pass


type PrefixCheckpointStoreOutcome = (
    NoPrefixCheckpointChange
    | PrefixCheckpointApplied
    | PrefixCheckpointDeleted
    | PrefixCheckpointCapacityRejected
    | PrefixCheckpointCapacityRolledOver
    | PrefixCheckpointNotAttempted
    | PrefixCheckpointNotCommitted
)


@dataclass(frozen=True, slots=True)
class LearningSnapshot:
    identity: LearningIdentity
    revision: int
    active_epoch: int
    samples: tuple[StoredSample, ...] = ()
    exact_anchors: tuple[ExactAnchor, ...] = ()
    prefix_anchors: tuple[PrefixAnchor, ...] = ()
    prefix_checkpoints: tuple[PrefixEligibilityCheckpoint, ...] = ()
    prediction_records: tuple[PredictionRecord, ...] = ()
    evaluations: tuple[PredictionEvaluation, ...] = ()
    is_stale: bool = False

    def __post_init__(self) -> None:
        _require_nonnegative_int("revision", self.revision)
        _require_nonnegative_int("active_epoch", self.active_epoch)
        if self.identity.learning_epoch != self.active_epoch:
            raise ValueError("snapshot identity epoch must equal its active epoch")
        sample_keys = tuple(sample.sample_key for sample in self.samples)
        if len(sample_keys) != len(set(sample_keys)):
            raise ValueError("snapshot samples must have unique sample keys")
        if any(sample.identity != self.identity for sample in self.samples):
            raise ValueError("snapshot samples must share its learning identity")
        if any(sample.committed_order is None for sample in self.samples):
            raise ValueError("public snapshot samples require committed order")
        if any(anchor.identity != self.identity for anchor in self.exact_anchors):
            raise ValueError("snapshot exact anchors must share its learning identity")
        if any(anchor.identity != self.identity for anchor in self.prefix_anchors):
            raise ValueError("snapshot prefix anchors must share its learning identity")
        if len({checkpoint.profile_key for checkpoint in self.prefix_checkpoints}) != len(
            self.prefix_checkpoints
        ):
            raise ValueError("snapshot prefix checkpoints must have unique profile keys")
        sample_key_set = set(sample_keys)
        if any(
            sample_key not in sample_key_set
            for anchor in self.exact_anchors
            for sample_key in anchor.sample_keys
        ):
            raise ValueError("snapshot exact anchors must reference retained samples")
        if any(anchor.sample_key not in sample_key_set for anchor in self.prefix_anchors):
            raise ValueError("snapshot prefix anchors must reference retained samples")
        record_keys = tuple(record.sample_key for record in self.prediction_records)
        if len(record_keys) != len(set(record_keys)):
            raise ValueError("snapshot prediction records must have unique sample keys")
        if any(record_key not in sample_key_set for record_key in record_keys):
            raise ValueError("snapshot prediction records must reference retained samples")
        if any(record.selected.identity != self.identity for record in self.prediction_records):
            raise ValueError("snapshot prediction records must share its learning identity")
        evaluation_keys = tuple(
            (evaluation.sample_key, evaluation.candidate_key) for evaluation in self.evaluations
        )
        if len(evaluation_keys) != len(set(evaluation_keys)):
            raise ValueError("snapshot evaluations must have unique sample and candidate key pairs")
        if any(sample_key not in sample_key_set for sample_key, _candidate_key in evaluation_keys):
            raise ValueError("snapshot evaluations must reference retained samples")
        record_candidate_keys = {
            (record.sample_key, candidate.candidate_key)
            for record in self.prediction_records
            for candidate in record.candidates
        }
        if not set(evaluation_keys).issubset(record_candidate_keys):
            raise ValueError("snapshot evaluations must reference prediction record candidates")
        if type(self.is_stale) is not bool:
            raise ValueError("snapshot is_stale must be a boolean")


@dataclass(frozen=True, slots=True)
class DriftObservation:
    identity: LearningIdentity
    kind: DriftKind
    previous_epoch: int
    new_epoch: int
    evidence_count: int
    reason_code: DriftReasonCode
    metadata: DriftReasonMetadata

    def __post_init__(self) -> None:
        if self.kind not in ("exact", "profile"):
            raise ValueError("drift kind must be closed")
        if type(self.reason_code) is not DriftReasonCode:
            raise ValueError("drift reason code must be a closed enum")
        _require_nonnegative_int("previous_epoch", self.previous_epoch)
        _require_nonnegative_int("new_epoch", self.new_epoch)
        _require_nonnegative_int("evidence_count", self.evidence_count)
        if self.new_epoch <= self.previous_epoch:
            raise ValueError("drift must advance the learning epoch")
        expected_type: type[object]
        if self.reason_code is DriftReasonCode.PROFILE_ERROR_REGRESSION:
            expected_type = ProfileErrorRegressionMetadata
            if self.kind != "profile":
                raise ValueError("profile error regression requires profile drift")
        elif self.reason_code is DriftReasonCode.EXACT_COUNT_MISMATCH:
            expected_type = ExactCountMismatchMetadata
            if self.kind != "exact":
                raise ValueError("exact count mismatch requires exact drift")
        else:
            expected_type = IdentityVersionChangeMetadata
        if type(self.metadata) is not expected_type:
            raise ValueError("drift reason metadata does not match its reason code")


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
    reason_code: LearningReasonCode
    metadata: LearningReasonMetadata
    prefix_checkpoint_outcome: PrefixCheckpointStoreOutcome
    evaluations: tuple[PredictionEvaluation, ...] = ()
    revision: int | None = None
    learning_epoch: int | None = None
    drift: DriftObservation | None = None

    def __post_init__(self) -> None:
        _validate_sample_key(self.sample_key)
        if self.outcome not in ("committed", "duplicate", "rejected", "failed"):
            raise ValueError("learning outcome must be closed")
        if type(self.reason_code) is not LearningReasonCode:
            raise ValueError("learning reason code must be a closed enum")
        if not isinstance(
            self.prefix_checkpoint_outcome,
            (
                NoPrefixCheckpointChange,
                PrefixCheckpointApplied,
                PrefixCheckpointDeleted,
                PrefixCheckpointCapacityRejected,
                PrefixCheckpointCapacityRolledOver,
                PrefixCheckpointNotAttempted,
                PrefixCheckpointNotCommitted,
            ),
        ):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("prefix checkpoint outcome must be closed")
        if self.revision is not None:
            _require_nonnegative_int("revision", self.revision)
        if self.learning_epoch is not None:
            _require_nonnegative_int("learning_epoch", self.learning_epoch)
        expected_metadata: type[object]
        if self.reason_code is LearningReasonCode.SAMPLE_COMMITTED:
            expected_metadata = SampleCommittedMetadata
        elif self.reason_code is LearningReasonCode.DUPLICATE_SAMPLE:
            expected_metadata = DuplicateSampleMetadata
        elif self.reason_code is LearningReasonCode.SAMPLE_INELIGIBLE:
            expected_metadata = SampleIneligibleMetadata
        elif self.reason_code is LearningReasonCode.MISSING_USAGE:
            expected_metadata = MissingUsageMetadata
        elif self.reason_code is LearningReasonCode.INCONSISTENT_USAGE:
            expected_metadata = InconsistentUsageMetadata
        elif self.reason_code is LearningReasonCode.QUEUE_FULL:
            expected_metadata = QueueFullMetadata
        elif self.reason_code is LearningReasonCode.ANALYSIS_FAILED:
            expected_metadata = AnalysisFailedMetadata
        elif self.reason_code is LearningReasonCode.OPERATION_CANCELLED:
            expected_metadata = OperationCancelledMetadata
        elif self.reason_code is LearningReasonCode.STORE_UNAVAILABLE:
            expected_metadata = StoreUnavailableMetadata
        elif self.reason_code is LearningReasonCode.MIGRATION_FAILED:
            expected_metadata = MigrationFailedMetadata
        elif self.reason_code is LearningReasonCode.COMMIT_FAILED:
            expected_metadata = CommitFailedMetadata
        else:
            expected_metadata = PrunedMetadata
        if type(self.metadata) is not expected_metadata:
            raise ValueError("learning reason metadata does not match its reason code")
        allowed_codes: tuple[LearningReasonCode, ...]
        if self.outcome == "committed":
            allowed_codes = (LearningReasonCode.SAMPLE_COMMITTED, LearningReasonCode.PRUNED)
            if self.revision is None or self.learning_epoch is None:
                raise ValueError("a committed observation requires revision and epoch")
        elif self.outcome == "duplicate":
            allowed_codes = (LearningReasonCode.DUPLICATE_SAMPLE,)
        elif self.outcome == "rejected":
            allowed_codes = (
                LearningReasonCode.SAMPLE_INELIGIBLE,
                LearningReasonCode.MISSING_USAGE,
                LearningReasonCode.INCONSISTENT_USAGE,
                LearningReasonCode.QUEUE_FULL,
                LearningReasonCode.PRUNED,
            )
        else:
            allowed_codes = (
                LearningReasonCode.ANALYSIS_FAILED,
                LearningReasonCode.OPERATION_CANCELLED,
                LearningReasonCode.STORE_UNAVAILABLE,
                LearningReasonCode.MIGRATION_FAILED,
                LearningReasonCode.COMMIT_FAILED,
            )
        if self.reason_code not in allowed_codes:
            raise ValueError("learning reason code does not match its outcome")
        checkpoint_outcome = self.prefix_checkpoint_outcome
        if self.outcome == "committed":
            if not isinstance(
                checkpoint_outcome,
                (
                    NoPrefixCheckpointChange,
                    PrefixCheckpointApplied,
                    PrefixCheckpointDeleted,
                    PrefixCheckpointCapacityRejected,
                    PrefixCheckpointCapacityRolledOver,
                ),
            ):
                raise ValueError("committed observations require a committed checkpoint outcome")
        elif self.outcome == "duplicate":
            if checkpoint_outcome != PrefixCheckpointNotAttempted(
                PrefixCheckpointNotAttemptedReason.DUPLICATE_SAMPLE
            ):
                raise ValueError("duplicates require duplicate-sample checkpoint non-attempt")
        elif self.outcome == "rejected":
            if checkpoint_outcome != PrefixCheckpointNotAttempted(
                PrefixCheckpointNotAttemptedReason.SAMPLE_REJECTED
            ):
                raise ValueError("rejections require sample-rejected checkpoint non-attempt")
        elif checkpoint_outcome != PrefixCheckpointNotCommitted() and checkpoint_outcome != (
            PrefixCheckpointNotAttempted(
                PrefixCheckpointNotAttemptedReason.FAILURE_BEFORE_POLICY
            )
        ):
            raise ValueError(
                "failed observations require NotCommitted or failure-before-policy"
            )
        if any(evaluation.sample_key != self.sample_key for evaluation in self.evaluations):
            raise ValueError("learning observation evaluations must align with its sample")
        candidate_keys = tuple(evaluation.candidate_key for evaluation in self.evaluations)
        if len(candidate_keys) != len(set(candidate_keys)):
            raise ValueError("learning observation evaluations must have unique candidate keys")


@dataclass(frozen=True, slots=True)
class LearningUpdate:
    sample: StoredSample
    prediction_record: PredictionRecord
    evaluations: tuple[PredictionEvaluation, ...]
    prefix_checkpoint_command: PrefixCheckpointCommand
    drift: DriftObservation | None = None

    def __post_init__(self) -> None:
        if self.sample.sample_key != self.prediction_record.sample_key:
            raise ValueError("learning update sample and prediction record must align")
        if any(evaluation.sample_key != self.sample.sample_key for evaluation in self.evaluations):
            raise ValueError("learning update evaluations must align with the sample")
        candidate_by_key = {
            candidate.candidate_key: candidate for candidate in self.prediction_record.candidates
        }
        evaluation_by_key = {
            evaluation.candidate_key: evaluation for evaluation in self.evaluations
        }
        if len(evaluation_by_key) != len(self.evaluations):
            raise ValueError("learning update evaluations must have unique candidate keys")
        if set(evaluation_by_key) != set(candidate_by_key):
            raise ValueError("learning update must evaluate every prediction candidate exactly once")
        for candidate_key, evaluation in evaluation_by_key.items():
            candidate = candidate_by_key[candidate_key]
            if not math.isclose(
                evaluation.predicted_tokens,
                candidate.unscaled_tokens,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError("learning update evaluation must match its prediction candidate")
            if evaluation.actual_tokens != self.sample.actual_input_tokens:
                raise ValueError("learning update evaluation actual must match its sample")
        if not isinstance(
            self.prefix_checkpoint_command,
            (
                NoPrefixCheckpointChange,
                ReplacePrefixCheckpoint,
                DeleteRecoveredPrefixCheckpoint,
            ),
        ):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("learning update requires a prefix checkpoint command")


def _validate_sample_key(sample_key: SampleKey) -> None:
    if len(sample_key) != 3:
        raise ValueError("sample key must have three members")
    process_boot_id, request_id, attempt_index = sample_key
    if not process_boot_id or not request_id:
        raise ValueError("sample key strings must be non-empty")
    _require_nonnegative_int("sample key attempt index", attempt_index)
