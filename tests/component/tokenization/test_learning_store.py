from __future__ import annotations
# ruff: noqa: I001

import asyncio
import hashlib
import json
import shutil
import sqlite3
import threading
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import aiosqlite
import pytest

import app.tokenization.learning_store as learning_store_module
from app.config.paths import tokenization_learning_path, tokenization_state_path, user_data_path
from app.tokenization.learning_store import (
    LearningApplyResult,
    LearningStoreStartupError,
    LearningStoreStartupReason,
    LearningStoreStateError,
    LearningStoreTransitionError,
    StoreOperationCancelled,
    TokenLearningStore,
    UnresolvedLearningIdentity,
    UnsupportedLearningSchemaError,
    ValidatedPersistentState,
    _StoreLimits,  # pyright: ignore[reportPrivateUsage]
)
from app.tokenization.types import (
    AnalysisFailedMetadata,
    AnalysisFailureStage,
    AnchorKind,
    AnchorUseIntent,
    AnchorUseOutcome,
    CommitFailedMetadata,
    DriftObservation,
    DriftReasonCode,
    DuplicateSampleMetadata,
    EstimateFeatures,
    ExactCountMismatchMetadata,
    FeatureName,
    FeatureVector,
    FixedContextContribution,
    InputItemContribution,
    IdentityVersionChangeMetadata,
    InconsistentUsageMetadata,
    LearningIdentity,
    LearningReasonCode,
    LearningSnapshot,
    LearningUpdate,
    MethodChampion,
    MigrationFailedMetadata,
    MissingUsageMetadata,
    NoPrefixCheckpointChange,
    OperationCancelledMetadata,
    PredictionCandidateKey,
    PredictionCandidateVariant,
    PredictionEvaluation,
    PredictionMethod,
    PredictionRecord,
    PrefixFingerprint,
    PrefixCheckpointNotAttempted,
    PrefixCheckpointNotAttemptedReason,
    PrefixCheckpointNotCommitted,
    PrefixCheckpointMode,
    PrefixCheckpointApplied,
    PrefixCheckpointCapacityRejected,
    PrefixCheckpointCapacityRolledOver,
    PendingPrefixChampionErrorTriple,
    PrefixChampionErrorTriple,
    PrefixEligibilityCheckpoint,
    ReplacePrefixCheckpoint,
    DeleteRecoveredPrefixCheckpoint,
    ProfileErrorRegressionMetadata,
    ProfileKey,
    PrunedMetadata,
    QueueFullMetadata,
    SampleCommittedMetadata,
    SampleIneligibleMetadata,
    SampleKey,
    StoreCancellationPhase,
    StoredSample,
    StoreUnavailableMetadata,
    TokenComponent,
    TokenLearningObservation,
    TokenPrediction,
)

EXPECTED_MANIFEST_DIGEST = "6637acd47e5dfd77316218a2c28713852a2d0962f286974b2a977320c87929cf"
EXPECTED_TABLE_DDL_DIGESTS = {
    "schema_meta": "7f9e205943982384c03ec5ed3ca70b5120dc14868ea101d4803380380ec7adc0",
    "identity_state": "acddf5655f3fb5784515ef57e6744f42853178b00e680d2c720840b0a8bc523c",
    "epoch_state": "6a69ca401c1a815fdcdbccf3840fd4feaff2929989823f9f1caacb18370f47ce",
    "samples": "bf4816999b655a9e75bdb208f7f13f35622d787e86de82226c4cd9a775ab9d5b",
    "prefix_checkpoints": "c29d36259f5515836d7784572bf0d09654f1fe74d6d710f4ae5eaf02dff668fa",
    "prediction_records": "b4ab4b923a7958a6cd089bcef5401e792f7e7b25ccc5b62a994eefd8be717d00",
    "evaluations": "bfb7fda5d6b2d25c800f10224445d66b6ddec4203903a8db83c14dfb54093beb",
    "exact_anchors": "0f54940dc321b3b004c8195b8123fa0554d8dbdfc0be6364dbbe604b4cd24608",
    "prefix_anchors": "b30d1052145729f0253cee767869b4ae45e08042c86336acf05ea173328527d1",
    "learning_events": "f050799e83b097de0167b8b2d5c810b2f8ac945289ea443a00e7615b8b0cb9a6",
}
EXPECTED_ACTION_BASES = frozenset((
    "lock.start.lifecycle",
    "lock.snapshot.lifecycle",
    "lock.snapshot.reader",
    "lock.apply.lifecycle",
    "lock.apply.writer",
    "lock.event.lifecycle",
    "lock.event.writer",
    "lock.anchor-use.lifecycle",
    "lock.anchor-use.writer",
    "lock.prune.lifecycle",
    "lock.prune.writer",
    "lock.close.lifecycle",
    "lock.close.reader",
    "lock.close.writer",
    "lock.close.shared-completion",
    "connection.inspect.open",
    "connection.inspect.close",
    "connection.writer.open",
    "connection.writer.close",
    "connection.reader.open",
    "connection.reader.close",
    "instrument.writer.thread-probe-install",
    "instrument.writer.trace-install",
    "instrument.reader.thread-probe-install",
    "instrument.reader.trace-install",
    "tx.inspect.begin",
    "tx.migration.begin",
    "tx.refresh.begin",
    "tx.apply.begin",
    "tx.event.begin",
    "tx.anchor-use.begin",
    "tx.prune.begin",
    "tx.inspect.commit",
    "tx.inspect.rollback",
    "tx.migration.commit",
    "tx.migration.rollback",
    "tx.refresh.commit",
    "tx.refresh.rollback",
    "tx.apply.commit",
    "tx.apply.rollback",
    "tx.event.commit",
    "tx.event.rollback",
    "tx.anchor-use.commit",
    "tx.anchor-use.rollback",
    "tx.prune.commit",
    "tx.prune.rollback",
    "cpu.state-decode",
    "cpu.transition",
    "retry.busy-sleep",
    "pragma.writer.foreign-keys-set",
    "pragma.writer.busy-timeout-set",
    "pragma.writer.synchronous-set",
    "pragma.reader.foreign-keys-set",
    "pragma.reader.busy-timeout-set",
    "pragma.reader.synchronous-set",
    "pragma.reader.query-only-set",
    "pragma.writer.foreign-keys-read",
    "pragma.reader.foreign-keys-read",
    "pragma.writer.journal-mode-wal",
    "pragma.reader.data-version",
    "pragma.inspect.quick-check",
    "pragma.writer.checkpoint",
    "instrument.worker-probe",
    "schema.objects-read",
    "schema.meta-read",
    "schema.table-list-read",
    "schema.table-xinfo-read",
    "schema.table-ddl-read",
    "schema.index-list-read",
    "schema.index-xinfo-read",
    "schema.foreign-keys-read",
    "schema.create-statement",
    "schema.meta-insert",
    "state.schema-meta-read",
    "state.identities-read",
    "state.epochs-read",
    "state.samples-read",
    "state.prediction-records-read",
    "state.evaluations-read",
    "state.exact-anchors-read",
    "state.prefix-anchors-read",
    "state.prefix-checkpoints-read",
    "state.events-read",
    "apply.duplicate-read",
    "identity.lookup",
    "identity.insert-returning",
    "global-revision.read",
    "identity.revision-read",
    "sample.exists",
    "epoch.owner-insert",
    "epoch.sample-insert",
    "epoch.prediction-insert",
    "identity.active-epoch-update",
    "sample.insert",
    "prediction-record.insert",
    "evaluation.insert",
    "exact-anchor.insert",
    "prefix-anchor.insert",
    "prefix-checkpoint.upsert",
    "prefix-checkpoint.delete",
    "identity.revision-update",
    "global-revision.update",
    "sample.delete",
    "evaluation.delete",
    "epoch.empty-delete",
    "identity.empty-delete",
    "event.insert",
    "event.ids-delete",
    "event.bucket-prune",
    "event.global-prune",
    "anchor-use.sample-update",
))
EXPECTED_ACTION_IDS = frozenset((
    "prefix-checkpoint.delete.cursor-close",
    "prefix-checkpoint.delete.execute",
    "prefix-checkpoint.upsert.cursor-close",
    "prefix-checkpoint.upsert.execute",
    "state.prefix-checkpoints-read.cursor-close",
    "state.prefix-checkpoints-read.execute",
    "state.prefix-checkpoints-read.fetch",
    "anchor-use.sample-update.cursor-close",
    "anchor-use.sample-update.execute",
    "apply.duplicate-read.cursor-close",
    "apply.duplicate-read.execute",
    "apply.duplicate-read.fetch",
    "connection.inspect.close",
    "connection.inspect.open",
    "connection.reader.close",
    "connection.reader.open",
    "connection.writer.close",
    "connection.writer.open",
    "cpu.state-decode",
    "cpu.transition",
    "epoch.empty-delete.cursor-close",
    "epoch.empty-delete.execute",
    "epoch.owner-insert.cursor-close",
    "epoch.owner-insert.execute",
    "epoch.prediction-insert.cursor-close",
    "epoch.prediction-insert.execute",
    "epoch.sample-insert.cursor-close",
    "epoch.sample-insert.execute",
    "evaluation.delete.cursor-close",
    "evaluation.delete.execute",
    "evaluation.insert.cursor-close",
    "evaluation.insert.execute",
    "event.bucket-prune.cursor-close",
    "event.bucket-prune.execute",
    "event.global-prune.cursor-close",
    "event.global-prune.execute",
    "event.ids-delete.cursor-close",
    "event.ids-delete.execute",
    "event.insert.cursor-close",
    "event.insert.execute",
    "exact-anchor.insert.cursor-close",
    "exact-anchor.insert.execute",
    "global-revision.read.cursor-close",
    "global-revision.read.execute",
    "global-revision.read.fetch",
    "global-revision.update.cursor-close",
    "global-revision.update.execute",
    "identity.active-epoch-update.cursor-close",
    "identity.active-epoch-update.execute",
    "identity.empty-delete.cursor-close",
    "identity.empty-delete.execute",
    "identity.insert-returning.cursor-close",
    "identity.insert-returning.execute",
    "identity.insert-returning.fetch",
    "identity.lookup.cursor-close",
    "identity.lookup.execute",
    "identity.lookup.fetch",
    "identity.revision-read.cursor-close",
    "identity.revision-read.execute",
    "identity.revision-read.fetch",
    "identity.revision-update.cursor-close",
    "identity.revision-update.execute",
    "instrument.reader.thread-probe-install",
    "instrument.reader.trace-install",
    "instrument.worker-probe.cursor-close",
    "instrument.worker-probe.execute",
    "instrument.worker-probe.fetch",
    "instrument.writer.thread-probe-install",
    "instrument.writer.trace-install",
    "lock.anchor-use.lifecycle",
    "lock.anchor-use.writer",
    "lock.apply.lifecycle",
    "lock.apply.writer",
    "lock.close.lifecycle",
    "lock.close.reader",
    "lock.close.shared-completion",
    "lock.close.writer",
    "lock.event.lifecycle",
    "lock.event.writer",
    "lock.prune.lifecycle",
    "lock.prune.writer",
    "lock.snapshot.lifecycle",
    "lock.snapshot.reader",
    "lock.start.lifecycle",
    "pragma.inspect.quick-check.cursor-close",
    "pragma.inspect.quick-check.execute",
    "pragma.inspect.quick-check.fetch",
    "pragma.reader.busy-timeout-set.cursor-close",
    "pragma.reader.busy-timeout-set.execute",
    "pragma.reader.data-version.cursor-close",
    "pragma.reader.data-version.execute",
    "pragma.reader.data-version.fetch",
    "pragma.reader.foreign-keys-read.cursor-close",
    "pragma.reader.foreign-keys-read.execute",
    "pragma.reader.foreign-keys-read.fetch",
    "pragma.reader.foreign-keys-set.cursor-close",
    "pragma.reader.foreign-keys-set.execute",
    "pragma.reader.query-only-set.cursor-close",
    "pragma.reader.query-only-set.execute",
    "pragma.reader.synchronous-set.cursor-close",
    "pragma.reader.synchronous-set.execute",
    "pragma.writer.busy-timeout-set.cursor-close",
    "pragma.writer.busy-timeout-set.execute",
    "pragma.writer.checkpoint.cursor-close",
    "pragma.writer.checkpoint.execute",
    "pragma.writer.checkpoint.fetch",
    "pragma.writer.foreign-keys-read.cursor-close",
    "pragma.writer.foreign-keys-read.execute",
    "pragma.writer.foreign-keys-read.fetch",
    "pragma.writer.foreign-keys-set.cursor-close",
    "pragma.writer.foreign-keys-set.execute",
    "pragma.writer.journal-mode-wal.cursor-close",
    "pragma.writer.journal-mode-wal.execute",
    "pragma.writer.journal-mode-wal.fetch",
    "pragma.writer.synchronous-set.cursor-close",
    "pragma.writer.synchronous-set.execute",
    "prediction-record.insert.cursor-close",
    "prediction-record.insert.execute",
    "prefix-anchor.insert.cursor-close",
    "prefix-anchor.insert.execute",
    "retry.busy-sleep",
    "sample.delete.cursor-close",
    "sample.delete.execute",
    "sample.exists.cursor-close",
    "sample.exists.execute",
    "sample.exists.fetch",
    "sample.insert.cursor-close",
    "sample.insert.execute",
    "schema.create-statement.cursor-close",
    "schema.create-statement.execute",
    "schema.foreign-keys-read.cursor-close",
    "schema.foreign-keys-read.execute",
    "schema.foreign-keys-read.fetch",
    "schema.index-list-read.cursor-close",
    "schema.index-list-read.execute",
    "schema.index-list-read.fetch",
    "schema.index-xinfo-read.cursor-close",
    "schema.index-xinfo-read.execute",
    "schema.index-xinfo-read.fetch",
    "schema.meta-insert.cursor-close",
    "schema.meta-insert.execute",
    "schema.meta-read.cursor-close",
    "schema.meta-read.execute",
    "schema.meta-read.fetch",
    "schema.objects-read.cursor-close",
    "schema.objects-read.execute",
    "schema.objects-read.fetch",
    "schema.table-ddl-read.cursor-close",
    "schema.table-ddl-read.execute",
    "schema.table-ddl-read.fetch",
    "schema.table-list-read.cursor-close",
    "schema.table-list-read.execute",
    "schema.table-list-read.fetch",
    "schema.table-xinfo-read.cursor-close",
    "schema.table-xinfo-read.execute",
    "schema.table-xinfo-read.fetch",
    "state.epochs-read.cursor-close",
    "state.epochs-read.execute",
    "state.epochs-read.fetch",
    "state.evaluations-read.cursor-close",
    "state.evaluations-read.execute",
    "state.evaluations-read.fetch",
    "state.events-read.cursor-close",
    "state.events-read.execute",
    "state.events-read.fetch",
    "state.exact-anchors-read.cursor-close",
    "state.exact-anchors-read.execute",
    "state.exact-anchors-read.fetch",
    "state.identities-read.cursor-close",
    "state.identities-read.execute",
    "state.identities-read.fetch",
    "state.prediction-records-read.cursor-close",
    "state.prediction-records-read.execute",
    "state.prediction-records-read.fetch",
    "state.prefix-anchors-read.cursor-close",
    "state.prefix-anchors-read.execute",
    "state.prefix-anchors-read.fetch",
    "state.samples-read.cursor-close",
    "state.samples-read.execute",
    "state.samples-read.fetch",
    "state.schema-meta-read.cursor-close",
    "state.schema-meta-read.execute",
    "state.schema-meta-read.fetch",
    "tx.anchor-use.begin.cursor-close",
    "tx.anchor-use.begin.execute",
    "tx.anchor-use.commit",
    "tx.anchor-use.rollback",
    "tx.apply.begin.cursor-close",
    "tx.apply.begin.execute",
    "tx.apply.commit",
    "tx.apply.rollback",
    "tx.event.begin.cursor-close",
    "tx.event.begin.execute",
    "tx.event.commit",
    "tx.event.rollback",
    "tx.inspect.begin.cursor-close",
    "tx.inspect.begin.execute",
    "tx.inspect.commit",
    "tx.inspect.rollback",
    "tx.migration.begin.cursor-close",
    "tx.migration.begin.execute",
    "tx.migration.commit",
    "tx.migration.rollback",
    "tx.prune.begin.cursor-close",
    "tx.prune.begin.execute",
    "tx.prune.commit",
    "tx.prune.rollback",
    "tx.refresh.begin.cursor-close",
    "tx.refresh.begin.execute",
    "tx.refresh.commit",
    "tx.refresh.rollback",
))
EXPECTED_BINARY_COLUMNS = {
    "identity_state": ("actual_provider", "resolved_model", "endpoint", "wire_format", "tokenizer", "descriptor_fingerprint"),
    "samples": ("process_boot_id", "request_id", "raw_body_sha256", "feature_raw_body_sha256", "profile_key_hash", "full_fingerprint", "context_fingerprint"),
    "prediction_records": ("process_boot_id", "request_id", "profile_key_hash"),
    "evaluations": ("process_boot_id", "request_id", "profile_key_hash"),
    "exact_anchors": ("process_boot_id", "request_id", "full_fingerprint"),
    "prefix_anchors": ("process_boot_id", "request_id", "context_fingerprint", "prefix_fingerprint"),
    "prefix_checkpoints": ("profile_key_json", "profile_key_hash"),
    "learning_events": ("sample_process_boot_id", "sample_request_id", "bucket_key", "process_boot_id", "request_id", "unresolved_provider", "unresolved_endpoint"),
}
EXPECTED_CHECK_FRAGMENTS = {
    "schema_meta": ("singleton = 1", "version = 1", "length(manifest_digest) = 64", "global_revision >= 0"),
    "identity_state": ("estimator_generation >= 1", "profile_schema_revision >= 1", "active_epoch >= 0", "revision >= 0"),
    "epoch_state": ("epoch >= 0", "created_order >= 0"),
    "samples": ("epoch >= 0", "attempt_index >= 0", "observed_at_us >= 0", "actual_input_tokens >= 0", "last_used_order >= 1", "known_tokens >= 0", "capability_visual_tokens IS NULL OR capability_visual_tokens >= 0"),
    "prediction_records": ("sample_epoch >= 0", "attempt_index >= 0", "prediction_epoch >= 0", "history_revision >= 0"),
    "evaluations": ("sample_epoch >= 0", "attempt_index >= 0", "prediction_epoch >= 0", "ordinal >= 0", "actual_tokens >= 0", "absolute_error >= 0", "absolute_percentage_error IS NULL OR absolute_percentage_error >= 0", "method = 'history-exact' AND candidate_variant = 'median'", "method = 'history-prefix' AND candidate_variant IN ('deterministic', 'additive', 'multiplicative')", "method = 'profile-calibrated' AND candidate_variant IN ('additive', 'multiplicative')", "method = 'cold-start' AND candidate_variant = 'deterministic'"),
    "exact_anchors": ("epoch >= 0", "attempt_index >= 0", "actual_tokens >= 0"),
    "prefix_anchors": ("epoch >= 0", "attempt_index >= 0", "item_count >= 1", "actual_tokens >= 0"),
    "prefix_checkpoints": (
        "epoch >= 0",
        "mode IN ('eligible', 'demoted')",
        "state_revision >= 1",
        "updated_order >= 1",
    ),
    "learning_events": (
        "learning_epoch IS NULL OR learning_epoch >= 0",
        "sample_attempt_index IS NULL OR sample_attempt_index >= 0",
        "attempt_index >= 0",
        "outcome IN ('committed', 'duplicate', 'rejected', 'failed')",
        "reason_code IN ('sample-committed'",
        "revision IS NULL OR revision >= 0",
        "drift_reason_code IS NULL OR drift_reason_code IN ('profile-error-regression'",
        "unresolved_generation IS NULL OR unresolved_generation >= 1",
        "created_at_us >= 0",
        "(drift_reason_code IS NULL) = (drift_metadata_json IS NULL)",
        "sample_process_boot_id IS NULL AND sample_request_id IS NULL AND sample_attempt_index IS NULL",
        "identity_id IS NOT NULL AND learning_epoch IS NOT NULL",
        "outcome != 'committed' OR reason_code = 'pruned' OR sample_process_boot_id IS NOT NULL",
    ),
}
EXPECTED_TABLE_COLUMNS = {
    "schema_meta": ("singleton", "version", "manifest_digest", "global_revision"),
    "identity_state": (
        "identity_id",
        "actual_provider",
        "resolved_model",
        "endpoint",
        "wire_format",
        "tokenizer",
        "descriptor_fingerprint",
        "estimator_generation",
        "profile_schema_revision",
        "active_epoch",
        "revision",
    ),
    "epoch_state": ("identity_id", "epoch", "created_order"),
    "samples": (
        "sample_id",
        "identity_id",
        "epoch",
        "process_boot_id",
        "request_id",
        "attempt_index",
        "observed_at_us",
        "actual_input_tokens",
        "last_used_order",
        "raw_body_sha256",
        "feature_raw_body_sha256",
        "known_tokens",
        "capability_visual_tokens",
        "components_json",
        "profile_key_json",
        "profile_key_hash",
        "feature_vector_json",
        "full_fingerprint",
        "context_fingerprint",
        "prefix_fingerprints_json",
        "low_confidence_reasons_json",
        "committed_order",
        "fixed_context_contribution_json",
        "input_item_contributions_json",
    ),
    "prefix_checkpoints": (
        "identity_id",
        "epoch",
        "profile_key_json",
        "profile_key_hash",
        "mode",
        "evidence_json",
        "state_revision",
        "updated_order",
    ),
    "prediction_records": (
        "identity_id",
        "sample_epoch",
        "process_boot_id",
        "request_id",
        "attempt_index",
        "prediction_epoch",
        "profile_key_hash",
        "selected_method",
        "selected_variant",
        "history_revision",
        "method_champions_json",
        "candidates_json",
    ),
    "evaluations": (
        "identity_id",
        "sample_epoch",
        "process_boot_id",
        "request_id",
        "attempt_index",
        "method",
        "candidate_variant",
        "prediction_epoch",
        "profile_key_hash",
        "ordinal",
        "predicted_tokens",
        "actual_tokens",
        "absolute_error",
        "signed_relative_error",
        "absolute_percentage_error",
    ),
    "exact_anchors": (
        "identity_id",
        "epoch",
        "process_boot_id",
        "request_id",
        "attempt_index",
        "full_fingerprint",
        "actual_tokens",
    ),
    "prefix_anchors": (
        "identity_id",
        "epoch",
        "process_boot_id",
        "request_id",
        "attempt_index",
        "context_fingerprint",
        "item_count",
        "prefix_fingerprint",
        "actual_tokens",
    ),
    "learning_events": (
        "event_id",
        "identity_id",
        "learning_epoch",
        "sample_process_boot_id",
        "sample_request_id",
        "sample_attempt_index",
        "bucket_key",
        "process_boot_id",
        "request_id",
        "attempt_index",
        "outcome",
        "reason_code",
        "metadata_json",
        "prefix_checkpoint_outcome_json",
        "revision",
        "drift_reason_code",
        "drift_metadata_json",
        "evaluations_json",
        "unresolved_provider",
        "unresolved_endpoint",
        "unresolved_generation",
        "created_at_us",
    ),
}
INTEGER_COLUMNS = {
    "singleton",
    "version",
    "global_revision",
    "identity_id",
    "estimator_generation",
    "profile_schema_revision",
    "active_epoch",
    "revision",
    "epoch",
    "created_order",
    "sample_id",
    "attempt_index",
    "observed_at_us",
    "actual_input_tokens",
    "last_used_order",
    "committed_order",
    "state_revision",
    "updated_order",
    "known_tokens",
    "capability_visual_tokens",
    "sample_epoch",
    "prediction_epoch",
    "history_revision",
    "ordinal",
    "actual_tokens",
    "item_count",
    "event_id",
    "learning_epoch",
    "sample_attempt_index",
    "unresolved_generation",
    "created_at_us",
}
REAL_COLUMNS = {
    "predicted_tokens",
    "absolute_error",
    "signed_relative_error",
    "absolute_percentage_error",
}
NULLABLE_COLUMNS = {
    ("identity_state", "identity_id"),
    ("samples", "sample_id"),
    ("samples", "feature_raw_body_sha256"),
    ("samples", "capability_visual_tokens"),
    ("evaluations", "signed_relative_error"),
    ("evaluations", "absolute_percentage_error"),
    ("learning_events", "event_id"),
    ("learning_events", "identity_id"),
    ("learning_events", "learning_epoch"),
    ("learning_events", "sample_process_boot_id"),
    ("learning_events", "sample_request_id"),
    ("learning_events", "sample_attempt_index"),
    ("learning_events", "revision"),
    ("learning_events", "drift_reason_code"),
    ("learning_events", "drift_metadata_json"),
    ("learning_events", "unresolved_provider"),
    ("learning_events", "unresolved_endpoint"),
    ("learning_events", "unresolved_generation"),
}
PRIMARY_KEY_POSITIONS = {
    ("schema_meta", "singleton"): 1,
    ("identity_state", "identity_id"): 1,
    ("epoch_state", "identity_id"): 1,
    ("epoch_state", "epoch"): 2,
    ("samples", "sample_id"): 1,
    ("learning_events", "event_id"): 1,
}
for _table in ("prediction_records", "exact_anchors", "prefix_anchors"):
    for _position, _column in enumerate(
        ("identity_id", "sample_epoch" if _table == "prediction_records" else "epoch", "process_boot_id", "request_id", "attempt_index"),
        start=1,
    ):
        PRIMARY_KEY_POSITIONS[(_table, _column)] = _position
for _position, _column in enumerate(
    ("identity_id", "sample_epoch", "process_boot_id", "request_id", "attempt_index", "method", "candidate_variant"),
    start=1,
):
    PRIMARY_KEY_POSITIONS[("evaluations", _column)] = _position
for _position, _column in enumerate(
    ("identity_id", "epoch", "profile_key_json"),
    start=1,
):
    PRIMARY_KEY_POSITIONS[("prefix_checkpoints", _column)] = _position
COLUMN_DEFAULTS = {
    ("schema_meta", "global_revision"): "0",
    ("identity_state", "revision"): "0",
}
UNIQUE_INDEXES = {
    "identity_state_identity_key_uq",
    "samples_global_key_uq",
    "samples_owner_key_uq",
}
DESCENDING_INDEX_COLUMNS = {
    ("samples_identity_epoch_order", "observed_at_us"),
    ("samples_identity_fingerprint_order", "observed_at_us"),
    ("prefix_anchors_lookup", "item_count"),
    ("learning_events_bucket_order", "event_id"),
    ("learning_events_identity_epoch", "event_id"),
}
EXPECTED_INDEX_COLUMNS = {
    "identity_state_identity_key_uq": (
        "actual_provider",
        "resolved_model",
        "endpoint",
        "wire_format",
        "tokenizer",
        "descriptor_fingerprint",
        "estimator_generation",
        "profile_schema_revision",
    ),
    "samples_global_key_uq": ("process_boot_id", "request_id", "attempt_index"),
    "samples_owner_key_uq": (
        "identity_id",
        "epoch",
        "process_boot_id",
        "request_id",
        "attempt_index",
    ),
    "samples_identity_epoch_order": (
        "identity_id",
        "epoch",
        "observed_at_us",
        "process_boot_id",
        "request_id",
        "attempt_index",
    ),
    "samples_identity_fingerprint_order": (
        "identity_id",
        "epoch",
        "full_fingerprint",
        "observed_at_us",
        "process_boot_id",
        "request_id",
        "attempt_index",
    ),
    "prediction_records_identity_epoch": (
        "identity_id",
        "prediction_epoch",
        "process_boot_id",
        "request_id",
        "attempt_index",
    ),
    "evaluations_window": (
        "identity_id",
        "prediction_epoch",
        "profile_key_hash",
        "method",
        "candidate_variant",
        "process_boot_id",
        "request_id",
        "attempt_index",
    ),
    "exact_anchors_lookup": (
        "identity_id",
        "epoch",
        "full_fingerprint",
        "process_boot_id",
        "request_id",
        "attempt_index",
    ),
    "prefix_anchors_lookup": (
        "identity_id",
        "epoch",
        "context_fingerprint",
        "item_count",
        "process_boot_id",
        "request_id",
        "attempt_index",
    ),
    "prefix_checkpoints_hash_lookup": (
        "identity_id",
        "epoch",
        "profile_key_hash",
    ),
    "learning_events_bucket_order": ("bucket_key", "event_id"),
    "learning_events_identity_epoch": ("identity_id", "learning_epoch", "event_id"),
}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _independent_normalized_ddl(sql: str) -> str:
    result: list[str] = []
    position = 0
    while position < len(sql):
        current = sql[position]
        if current.isspace():
            position += 1
        elif current in ("'", '"', "`", "["):
            terminator = "]" if current == "[" else current
            start = position
            position += 1
            while position < len(sql):
                if sql[position] == terminator:
                    if (
                        terminator != "]"
                        and position + 1 < len(sql)
                        and sql[position + 1] == terminator
                    ):
                        position += 2
                        continue
                    position += 1
                    break
                position += 1
            result.append(sql[start:position])
        elif current.isalnum() or current in ("_", "$", "."):
            start = position
            while position < len(sql) and (
                sql[position].isalnum() or sql[position] in ("_", "$", ".")
            ):
                position += 1
            result.append(sql[start:position].lower())
        elif sql[position : position + 2] in ("<=", ">=", "!=", "<>", "||", "=="):
            result.append(sql[position : position + 2])
            position += 2
        else:
            result.append(current)
            position += 1
    return " ".join(result)


def _expected_identity_bucket(identity: LearningIdentity) -> str:
    payload = json.dumps(
        [
            identity.actual_provider,
            identity.resolved_model,
            identity.endpoint,
            identity.wire_format,
            identity.tokenizer,
            identity.descriptor_fingerprint,
            identity.estimator_generation,
            identity.profile_schema_revision,
            identity.learning_epoch,
        ],
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"identity:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _identity(
    *,
    actual_provider: str = "provider-a",
    resolved_model: str = "model-a",
    endpoint: str = "responses",
    wire_format: str = "openai-responses",
    tokenizer: str = "o200k_base",
    descriptor_fingerprint: str | None = None,
    estimator_generation: int = 1,
    profile_schema_revision: int = 1,
    learning_epoch: int = 0,
) -> LearningIdentity:
    return LearningIdentity(
        actual_provider=actual_provider,
        resolved_model=resolved_model,
        endpoint=endpoint,
        wire_format=wire_format,
        tokenizer=tokenizer,
        descriptor_fingerprint=descriptor_fingerprint or _digest("descriptor"),
        estimator_generation=estimator_generation,
        profile_schema_revision=profile_schema_revision,
        learning_epoch=learning_epoch,
    )


def _sample(
    index: int,
    *,
    identity: LearningIdentity | None = None,
    sample_key: tuple[str, str, int] | None = None,
    fingerprint: str | None = None,
    actual: int | None = None,
    observed_at_us: int | None = None,
    prefix_count: int = 1,
    profile_suffix: str = "",
    capability_visual_tokens: int | None = None,
) -> StoredSample:
    selected_identity = identity or _identity()
    known_tokens = max(10 + index, 4 * prefix_count)
    observations: dict[FeatureName, int | None] = {name: None for name in FeatureName}
    observations[FeatureName.KNOWN_TOTAL] = known_tokens
    observations[FeatureName.MESSAGE_ITEM_COUNT] = 1
    observations[FeatureName.MEDIA_COUNT] = 0
    unknown_digest = _digest(f"unknown-{profile_suffix}")
    profile = ProfileKey(
        item_kinds=("message",),
        reasoning_origins=(),
        media_kinds=(),
        unknown_type_digests=(unknown_digest,),
        unknown_type_count=1,
        unknown_type_overflow=False,
        has_previous_response_id=False,
        context_management_mode="none",
        truncation_mode=f"none-{profile_suffix}",
    )
    body_digest = _digest(
        f"body-{index}-{selected_identity.actual_provider}-{selected_identity.estimator_generation}"
    )
    prefixes = tuple(
        PrefixFingerprint(item_count=value, digest=_digest(f"prefix-{index}-{value}"))
        for value in range(1, prefix_count + 1)
    )
    features = EstimateFeatures(
        known_tokens=known_tokens,
        capability_visual_tokens=(
            0 if prefix_count == 0 and capability_visual_tokens is None else capability_visual_tokens
        ),
        components=(TokenComponent(kind="message", tokens=known_tokens, instances=1),),
        profile_key=profile,
        feature_vector=FeatureVector.from_observations(observations),
        full_fingerprint=_digest(f"full-{index}" if fingerprint is None else fingerprint),
        context_fingerprint=_digest("context"),
        prefix_fingerprints=prefixes,
        low_confidence_reasons=("zero-prior:unknown-items",),
        estimator_generation=selected_identity.estimator_generation,
        profile_schema_revision=selected_identity.profile_schema_revision,
        raw_sent_body_sha256=body_digest,
        fixed_context_contribution=FixedContextContribution(
            known_tokens if prefix_count == 0 else 0, 0, 0.0
        ),
        input_item_contributions=tuple(
            InputItemContribution(
                known_tokens - (4 * prefix_count) if value == 1 else 0,
                4,
                0,
                capability_visual_tokens if value == prefix_count else 0,
                0.0,
            )
            for value in range(1, prefix_count + 1)
        ),
    )
    key = sample_key or (
        "boot",
        f"request-{index}-{selected_identity.actual_provider}-{selected_identity.estimator_generation}",
        0,
    )
    return StoredSample(
        sample_key=key,
        identity=selected_identity,
        features=features,
        actual_input_tokens=known_tokens + 2 if actual is None else actual,
        raw_body_sha256=body_digest,
        observed_at_us=index + 1 if observed_at_us is None else observed_at_us,
    )


def _transition_for(
    sample: StoredSample,
    *,
    seen_revisions: list[int] | None = None,
    thread_ids: list[int] | None = None,
    entered: threading.Event | None = None,
    release: threading.Event | None = None,
    drift: bool = False,
) -> Callable[[LearningSnapshot], LearningUpdate]:
    def transition(snapshot: LearningSnapshot) -> LearningUpdate:
        if seen_revisions is not None:
            seen_revisions.append(snapshot.revision)
        if thread_ids is not None:
            thread_ids.append(threading.get_ident())
        if entered is not None:
            entered.set()
        if release is not None and not release.wait(timeout=5):
            raise TimeoutError("test did not release transition")
        sample_epoch = snapshot.active_epoch + 1 if drift else snapshot.active_epoch
        stored_sample = replace(
            sample,
            identity=replace(snapshot.identity, learning_epoch=sample_epoch),
        )
        candidate_key = PredictionCandidateKey(
            PredictionMethod.COLD_START,
            PredictionCandidateVariant.DETERMINISTIC,
        )
        prediction = TokenPrediction(
            identity=snapshot.identity,
            profile_key=stored_sample.features.profile_key,
            method=PredictionMethod.COLD_START,
            candidate_key=candidate_key,
            unscaled_tokens=float(stored_sample.features.known_tokens),
            sample_count=len(snapshot.samples),
            history_revision=snapshot.revision,
            learning_epoch=snapshot.active_epoch,
            low_confidence_reasons=stored_sample.features.low_confidence_reasons,
        )
        record = PredictionRecord(
            stored_sample.sample_key,
            candidate_key,
            (prediction,),
            (MethodChampion(candidate_key, True),),
        )
        actual = stored_sample.actual_input_tokens
        absolute_error = abs(prediction.unscaled_tokens - actual)
        evaluation = PredictionEvaluation(
            sample_key=stored_sample.sample_key,
            method=prediction.method,
            candidate_key=prediction.candidate_key,
            predicted_tokens=prediction.unscaled_tokens,
            actual_tokens=actual,
            absolute_error=absolute_error,
            signed_relative_error=(prediction.unscaled_tokens - actual) / actual if actual else None,
            absolute_percentage_error=absolute_error / actual if actual else None,
        )
        drift_observation = None
        if drift:
            drift_observation = DriftObservation(
                identity=snapshot.identity,
                kind="exact",
                previous_epoch=snapshot.active_epoch,
                new_epoch=sample_epoch,
                evidence_count=3,
                reason_code=DriftReasonCode.EXACT_COUNT_MISMATCH,
                metadata=ExactCountMismatchMetadata(3),
            )
        _observation = TokenLearningObservation(
            sample_key=stored_sample.sample_key,
            outcome="committed",
            reason_code=LearningReasonCode.SAMPLE_COMMITTED,
            metadata=SampleCommittedMetadata(stored_sample.actual_input_tokens),
            prefix_checkpoint_outcome=NoPrefixCheckpointChange(),
            evaluations=(evaluation,),
            revision=snapshot.revision + 1,
            learning_epoch=sample_epoch,
            drift=drift_observation,
        )
        return LearningUpdate(
            sample=stored_sample,
            prediction_record=record,
            evaluations=(evaluation,),
            prefix_checkpoint_command=NoPrefixCheckpointChange(),
            drift=drift_observation,
        )

    return transition


def _multi_variant_transition_for(sample: StoredSample) -> Callable[[LearningSnapshot], LearningUpdate]:
    def transition(snapshot: LearningSnapshot) -> LearningUpdate:
        stored_sample = replace(sample, identity=snapshot.identity)
        keys = (
            PredictionCandidateKey(
                PredictionMethod.HISTORY_PREFIX,
                PredictionCandidateVariant.DETERMINISTIC,
            ),
            PredictionCandidateKey(
                PredictionMethod.HISTORY_PREFIX,
                PredictionCandidateVariant.ADDITIVE,
            ),
            PredictionCandidateKey(
                PredictionMethod.COLD_START,
                PredictionCandidateVariant.DETERMINISTIC,
            ),
        )
        candidates = tuple(
            TokenPrediction(
                identity=snapshot.identity,
                profile_key=stored_sample.features.profile_key,
                method=key.method,
                candidate_key=key,
                unscaled_tokens=float(stored_sample.features.known_tokens + offset),
                sample_count=len(snapshot.samples),
                history_revision=snapshot.revision,
                learning_epoch=snapshot.active_epoch,
                low_confidence_reasons=stored_sample.features.low_confidence_reasons,
            )
            for offset, key in enumerate(keys)
        )
        record = PredictionRecord(
            stored_sample.sample_key,
            keys[1],
            candidates,
            (
                MethodChampion(keys[1], True),
                MethodChampion(keys[2], True),
            ),
        )
        evaluations = tuple(
            PredictionEvaluation(
                sample_key=stored_sample.sample_key,
                method=candidate.method,
                candidate_key=candidate.candidate_key,
                predicted_tokens=candidate.unscaled_tokens,
                actual_tokens=stored_sample.actual_input_tokens,
                absolute_error=abs(candidate.unscaled_tokens - stored_sample.actual_input_tokens),
                signed_relative_error=(
                    None
                    if stored_sample.actual_input_tokens == 0
                    else (candidate.unscaled_tokens - stored_sample.actual_input_tokens)
                    / stored_sample.actual_input_tokens
                ),
                absolute_percentage_error=(
                    None
                    if stored_sample.actual_input_tokens == 0
                    else abs(candidate.unscaled_tokens - stored_sample.actual_input_tokens)
                    / stored_sample.actual_input_tokens
                ),
            )
            for candidate in candidates
        )
        _observation = TokenLearningObservation(
            sample_key=stored_sample.sample_key,
            outcome="committed",
            reason_code=LearningReasonCode.SAMPLE_COMMITTED,
            metadata=SampleCommittedMetadata(stored_sample.actual_input_tokens),
            prefix_checkpoint_outcome=NoPrefixCheckpointChange(),
            evaluations=evaluations,
            revision=snapshot.revision + 1,
            learning_epoch=snapshot.active_epoch,
        )
        return LearningUpdate(stored_sample, record, evaluations, NoPrefixCheckpointChange())

    return transition


async def _rows(
    path: Path,
    sql: str,
    parameters: tuple[object, ...] = (),
) -> tuple[tuple[Any, ...], ...]:
    async with (
        aiosqlite.connect(path, isolation_level=None, timeout=0) as connection,
        connection.execute(sql, parameters) as cursor,
    ):
        values = await cursor.fetchall()
    return tuple(tuple(value) for value in values)


async def _scalar(
    path: Path,
    sql: str,
    parameters: tuple[object, ...] = (),
) -> Any:
    rows = await _rows(path, sql, parameters)
    assert len(rows) == 1
    assert len(rows[0]) == 1
    return rows[0][0]


async def _assert_write_lock_available(path: Path) -> None:
    async with aiosqlite.connect(path, isolation_level=None, timeout=0) as connection:
        await connection.execute("PRAGMA busy_timeout=0")
        await connection.execute("BEGIN IMMEDIATE")
        await connection.rollback()


async def _wait_thread_event(event: threading.Event) -> None:
    for _ in range(500):
        if event.is_set():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("worker thread did not reach barrier")


@dataclass(slots=True)
class _CancelPlan:
    targets: tuple[tuple[str | StoreCancellationPhase, int], ...] = ()
    armed: bool = False
    action_counts: dict[str, int] = field(
        init=False,
        default_factory=lambda: defaultdict(int),
    )
    phase_counts: dict[StoreCancellationPhase, int] = field(
        init=False,
        default_factory=lambda: defaultdict(int),
    )
    fired: list[str | StoreCancellationPhase] = field(
        init=False,
        default_factory=lambda: list[str | StoreCancellationPhase](),
    )

    async def __call__(
        self,
        action_id: str,
        phase: StoreCancellationPhase,
    ) -> None:
        if not self.armed:
            return
        self.action_counts[action_id] += 1
        self.phase_counts[phase] += 1
        action_target = (action_id, self.action_counts[action_id])
        phase_target = (phase, self.phase_counts[phase])
        if action_target in self.targets:
            self.fired.append(action_id)
        elif phase_target in self.targets:
            self.fired.append(phase)
        else:
            return
        task = asyncio.current_task()
        assert task is not None
        task.cancel()

    def arm(
        self,
        *targets: tuple[str | StoreCancellationPhase, int],
    ) -> None:
        self.targets = targets
        self.action_counts.clear()
        self.phase_counts.clear()
        self.fired.clear()
        self.armed = True

    def disarm(self) -> None:
        self.armed = False
        self.targets = ()
        self.action_counts.clear()
        self.phase_counts.clear()


@dataclass(slots=True)
class _ThreadEvidence:
    constructors: list[int]
    closes: list[int]
    workers: list[tuple[str, int]]
    cursor_opens: list[int] = field(default_factory=lambda: list[int]())
    cursor_closes: list[int] = field(default_factory=lambda: list[int]())


def _raw_counting_factory(
    raw_calls: list[str],
) -> Callable[[Path, bool], aiosqlite.Connection]:
    def factory(path: Path, read_only: bool) -> aiosqlite.Connection:
        if read_only:
            connection = aiosqlite.connect(
                f"{path.resolve().as_uri()}?mode=ro",
                uri=True,
                isolation_level=None,
                timeout=0,
            )
        else:
            connection = aiosqlite.connect(
                path,
                isolation_level=None,
                timeout=0,
            )
        dynamic = cast(Any, connection)
        original_connect = dynamic._connect
        original_execute = dynamic._execute

        async def tracked_connect() -> aiosqlite.Connection:
            raw_calls.append("open")
            return await original_connect()

        async def tracked_execute(*args: object, **kwargs: object) -> Any:
            raw_calls.append("queued")
            return await original_execute(*args, **kwargs)

        dynamic._connect = tracked_connect
        dynamic._execute = tracked_execute
        return connection

    return factory


def _tracking_factory(evidence: _ThreadEvidence) -> Callable[[Path, bool], aiosqlite.Connection]:
    class TrackingCursor(sqlite3.Cursor):
        def __init__(self, connection: sqlite3.Connection) -> None:
            super().__init__(connection)
            evidence.cursor_opens.append(id(self))

        def close(self) -> None:
            evidence.cursor_closes.append(id(self))
            super().close()

    class TrackingConnection(sqlite3.Connection):
        def __init__(
            self,
            database: str,
            *,
            uri: bool,
            isolation_level: None,
            timeout: float,
        ) -> None:
            evidence.constructors.append(threading.get_ident())
            super().__init__(
                database,
                uri=uri,
                isolation_level=isolation_level,
                timeout=timeout,
            )

        def execute(
            self,
            sql: str,
            parameters: Any = (),
        ) -> sqlite3.Cursor:
            cursor = self.cursor(TrackingCursor)
            try:
                return cursor.execute(sql, parameters)
            except BaseException:
                cursor.close()
                raise

        def close(self) -> None:
            evidence.closes.append(threading.get_ident())
            super().close()

    def factory(path: Path, read_only: bool) -> aiosqlite.Connection:
        target = f"{path.resolve().as_uri()}?mode=ro" if read_only else str(path)

        def connector() -> sqlite3.Connection:
            return TrackingConnection(
                target,
                uri=read_only,
                isolation_level=None,
                timeout=0,
            )

        return aiosqlite.Connection(connector, 64)

    return factory


def _event(
    index: int,
    reason: LearningReasonCode = LearningReasonCode.SAMPLE_INELIGIBLE,
) -> TokenLearningObservation:
    metadata: Any
    if reason is LearningReasonCode.SAMPLE_INELIGIBLE:
        metadata = SampleIneligibleMetadata()
        outcome = "rejected"
    elif reason is LearningReasonCode.MISSING_USAGE:
        metadata = MissingUsageMetadata()
        outcome = "rejected"
    elif reason is LearningReasonCode.INCONSISTENT_USAGE:
        metadata = InconsistentUsageMetadata()
        outcome = "rejected"
    elif reason is LearningReasonCode.QUEUE_FULL:
        metadata = QueueFullMetadata(index, index * 1024)
        outcome = "rejected"
    elif reason is LearningReasonCode.ANALYSIS_FAILED:
        metadata = AnalysisFailedMetadata(AnalysisFailureStage.FEATURE_EXTRACTION)
        outcome = "failed"
    elif reason is LearningReasonCode.OPERATION_CANCELLED:
        metadata = OperationCancelledMetadata(StoreCancellationPhase.TRANSITION)
        outcome = "failed"
    elif reason is LearningReasonCode.STORE_UNAVAILABLE:
        metadata = StoreUnavailableMetadata()
        outcome = "failed"
    elif reason is LearningReasonCode.MIGRATION_FAILED:
        metadata = MigrationFailedMetadata()
        outcome = "failed"
    elif reason is LearningReasonCode.COMMIT_FAILED:
        metadata = CommitFailedMetadata()
        outcome = "failed"
    else:
        metadata = PrunedMetadata(1)
        outcome = "rejected"
    checkpoint_outcome = (
        PrefixCheckpointNotAttempted(
            PrefixCheckpointNotAttemptedReason.SAMPLE_REJECTED
        )
        if outcome == "rejected"
        else PrefixCheckpointNotCommitted()
    )
    return TokenLearningObservation(
        sample_key=("boot", f"event-{index}", 0),
        outcome=cast(Any, outcome),
        reason_code=reason,
        metadata=metadata,
        prefix_checkpoint_outcome=checkpoint_outcome,
    )


async def _expect_action_cancellation(
    awaitable: Awaitable[Any],
    plan: _CancelPlan,
    action_id: str,
) -> StoreOperationCancelled:
    plan.arm((action_id, 1))
    task = asyncio.ensure_future(awaitable)
    with pytest.raises(StoreOperationCancelled) as caught:
        await task
    assert task.cancelled()
    plan.disarm()
    return caught.value


def test_confirmed_action_ledger_matches_independent_fixed_contract_literal() -> None:
    production_bases = {
        base
        for _shape, base in learning_store_module._ACTION_BASE_SHAPES  # pyright: ignore[reportPrivateUsage]
    }

    assert len(EXPECTED_ACTION_BASES) == 111
    assert len(EXPECTED_ACTION_IDS) == 211
    assert production_bases == EXPECTED_ACTION_BASES
    assert learning_store_module.CONFIRMED_ACTION_IDS == EXPECTED_ACTION_IDS


@dataclass(slots=True)
class _PreparedCancellationScenario:
    path: Path
    plan: _CancelPlan
    evidence: _ThreadEvidence
    store: TokenLearningStore
    operation_factory: Callable[[], Awaitable[Any]]
    baseline_global_revision: int
    baseline_sample_count: int
    baseline_event_count: int
    baseline_cache_revision: int
    auxiliary_stores: tuple[TokenLearningStore, ...] = ()
    blocker: aiosqlite.Connection | None = None


_CancellationOperationFactory = Callable[
    [Path, _CancelPlan, _ThreadEvidence],
    Awaitable[_PreparedCancellationScenario],
]


@dataclass(frozen=True, slots=True)
class _RealCallCancellationScenario:
    name: str
    action_bases: frozenset[str]
    operation_factory: _CancellationOperationFactory
    postcondition: str
    trigger_action_id: str | None = None
    trigger_phase: StoreCancellationPhase | None = None
    committed_observation: bool = False


def _tracked_store(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
    *,
    limits: _StoreLimits | None = None,
) -> TokenLearningStore:
    return TokenLearningStore(
        path,
        _limits=_StoreLimits() if limits is None else limits,
        _action_hook=plan,
        _thread_probe=lambda _label, _thread: None,
        _trace_callback=lambda _statement: None,
        _connection_factory=_tracking_factory(evidence),
    )


async def _scenario_baseline(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
    store: TokenLearningStore,
    operation_factory: Callable[[], Awaitable[Any]],
    *,
    auxiliary_stores: tuple[TokenLearningStore, ...] = (),
    blocker: aiosqlite.Connection | None = None,
) -> _PreparedCancellationScenario:
    evidence.cursor_opens.clear()
    evidence.cursor_closes.clear()
    global_revision = await _scalar(path, "SELECT global_revision FROM schema_meta")
    sample_count = await _scalar(path, "SELECT count(*) FROM samples")
    event_count = await _scalar(path, "SELECT count(*) FROM learning_events")
    return _PreparedCancellationScenario(
        path,
        plan,
        evidence,
        store,
        operation_factory,
        global_revision,
        sample_count,
        event_count,
        store._validated_state.global_revision,  # pyright: ignore[reportPrivateUsage]
        auxiliary_stores,
        blocker,
    )


async def _prepare_fresh_start_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    store = _tracked_store(path, plan, evidence)
    return _PreparedCancellationScenario(
        path,
        plan,
        evidence,
        store,
        store.start,
        0,
        0,
        0,
        0,
    )


async def _prepare_existing_start_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    seed = TokenLearningStore(path)
    await seed.start()
    await seed.close()
    store = _tracked_store(path, plan, evidence)
    return _PreparedCancellationScenario(
        path,
        plan,
        evidence,
        store,
        store.start,
        0,
        0,
        0,
        0,
    )


async def _prepare_snapshot_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    writer = TokenLearningStore(path)
    await writer.start()
    first = _sample(0)
    await writer.apply_sample(first, _transition_for(first))
    store = _tracked_store(path, plan, evidence)
    await store.start()
    await writer.apply_sample(_sample(1), _transition_for(_sample(1)))
    return await _scenario_baseline(
        path,
        plan,
        evidence,
        store,
        lambda: store.snapshot_for_prediction(first.identity),
        auxiliary_stores=(writer,),
    )


async def _prepare_apply_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    store = _tracked_store(path, plan, evidence)
    await store.start()
    sample = _sample(10)
    return await _scenario_baseline(
        path,
        plan,
        evidence,
        store,
        lambda: store.apply_sample(sample, _transition_for(sample, drift=True)),
    )


def _checkpoint_transition(
    sample: StoredSample,
    command: object,
) -> Callable[[LearningSnapshot], LearningUpdate]:
    ordinary = _transition_for(sample)

    def transition(snapshot: LearningSnapshot) -> LearningUpdate:
        return replace(
            ordinary(snapshot),
            prefix_checkpoint_command=cast(Any, command),
        )

    return transition


async def _prepare_checkpoint_upsert_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    store = _tracked_store(path, plan, evidence)
    await store.start()
    sample = _sample(10)
    command = ReplacePrefixCheckpoint(
        sample.features.profile_key,
        PrefixCheckpointMode.ELIGIBLE,
        (),
        None,
    )
    return await _scenario_baseline(
        path, plan, evidence, store,
        lambda: store.apply_sample(sample, _checkpoint_transition(sample, command)),
    )


async def _prepare_checkpoint_delete_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    store = _tracked_store(path, plan, evidence)
    await store.start()
    initial = _sample(9)
    await store.apply_sample(
        initial,
        _checkpoint_transition(
            initial,
            ReplacePrefixCheckpoint(
                initial.features.profile_key,
                PrefixCheckpointMode.ELIGIBLE,
                (),
                None,
            ),
        ),
    )
    sample = _sample(10)
    command = DeleteRecoveredPrefixCheckpoint(sample.features.profile_key, 1)
    return await _scenario_baseline(
        path, plan, evidence, store,
        lambda: store.apply_sample(sample, _checkpoint_transition(sample, command)),
    )


async def _prepare_event_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    store = _tracked_store(path, plan, evidence)
    await store.start()
    return await _scenario_baseline(
        path,
        plan,
        evidence,
        store,
        lambda: store.record_event(
            _event(1000),
            UnresolvedLearningIdentity("real-call-event", "responses", 1),
        ),
    )


async def _prepare_anchor_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    store = _tracked_store(path, plan, evidence)
    await store.start()
    sample = _sample(0)
    await store.apply_sample(sample, _transition_for(sample))
    intent = AnchorUseIntent(
        AnchorKind.EXACT,
        sample.identity,
        0,
        sample.features.full_fingerprint,
        (sample.sample_key,),
    )
    return await _scenario_baseline(
        path,
        plan,
        evidence,
        store,
        lambda: store.record_anchor_use(intent),
    )


async def _prepare_prune_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    initial_limits = _StoreLimits(
        samples_per_identity=10,
        samples_global=10,
        actuals_per_fingerprint=10,
        evaluations_per_window=10,
        events_per_identity=10,
        events_global=20,
    )
    store = _tracked_store(path, plan, evidence, limits=initial_limits)
    await store.start()
    first = _sample(0, fingerprint="prune-shared")
    second = _sample(1, fingerprint="prune-shared")
    foreign = _sample(2, identity=_identity(actual_provider="prune-foreign"))
    await store.apply_sample(first, _transition_for(first))
    await store.apply_sample(second, _transition_for(second))
    await store.apply_sample(foreign, _transition_for(foreign))
    for index in range(3):
        await store.record_event(
            _event(1100 + index),
            UnresolvedLearningIdentity("prune-unresolved", "responses", 1),
        )
    store._limits = _StoreLimits(  # pyright: ignore[reportPrivateUsage]
        samples_per_identity=1,
        samples_global=1,
        actuals_per_fingerprint=1,
        evaluations_per_window=1,
        events_per_identity=1,
        events_global=1,
    )
    return await _scenario_baseline(path, plan, evidence, store, store.prune)


async def _prepare_evaluation_prune_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    initial_limits = _StoreLimits(
        samples_per_identity=10,
        samples_global=10,
        actuals_per_fingerprint=10,
        evaluations_per_window=10,
        events_per_identity=10,
        events_global=20,
    )
    store = _tracked_store(path, plan, evidence, limits=initial_limits)
    await store.start()
    for index in range(3):
        sample = _sample(index)
        await store.apply_sample(sample, _transition_for(sample))
    store._limits = replace(initial_limits, evaluations_per_window=1)  # pyright: ignore[reportPrivateUsage]
    return await _scenario_baseline(path, plan, evidence, store, store.prune)


async def _prepare_duplicate_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    store = _tracked_store(path, plan, evidence)
    await store.start()
    sample = _sample(0)
    await store.apply_sample(sample, _transition_for(sample))
    return await _scenario_baseline(
        path,
        plan,
        evidence,
        store,
        lambda: store.apply_sample(sample, _transition_for(sample)),
    )


async def _prepare_close_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    store = _tracked_store(path, plan, evidence)
    await store.start()
    return await _scenario_baseline(path, plan, evidence, store, store.close)


async def _prepare_busy_cancellation(
    path: Path,
    plan: _CancelPlan,
    evidence: _ThreadEvidence,
) -> _PreparedCancellationScenario:
    store = _tracked_store(path, plan, evidence)
    await store.start()
    blocker = await aiosqlite.connect(path, isolation_level=None, timeout=0)
    await blocker.execute("PRAGMA busy_timeout=0")
    await blocker.execute("BEGIN IMMEDIATE")
    sample = _sample(10)
    return await _scenario_baseline(
        path,
        plan,
        evidence,
        store,
        lambda: store.apply_sample(sample, _transition_for(sample)),
        blocker=blocker,
    )


_FRESH_START_BASES = frozenset({
    "connection.writer.open",
    "connection.reader.open",
    "instrument.writer.thread-probe-install",
    "instrument.writer.trace-install",
    "instrument.reader.thread-probe-install",
    "instrument.reader.trace-install",
    "tx.migration.begin",
    "tx.migration.commit",
    "pragma.writer.foreign-keys-set",
    "pragma.writer.busy-timeout-set",
    "pragma.writer.synchronous-set",
    "pragma.reader.foreign-keys-set",
    "pragma.reader.busy-timeout-set",
    "pragma.reader.synchronous-set",
    "pragma.reader.query-only-set",
    "pragma.writer.foreign-keys-read",
    "pragma.reader.foreign-keys-read",
    "pragma.writer.journal-mode-wal",
    "schema.objects-read",
    "schema.meta-read",
    "schema.table-list-read",
    "schema.table-xinfo-read",
    "schema.table-ddl-read",
    "schema.index-list-read",
    "schema.index-xinfo-read",
    "schema.foreign-keys-read",
    "schema.create-statement",
    "schema.meta-insert",
})
_EXISTING_START_BASES = frozenset({
    "connection.inspect.open",
    "connection.inspect.close",
    "tx.inspect.begin",
    "tx.inspect.commit",
    "pragma.inspect.quick-check",
})
_SNAPSHOT_BASES = frozenset({
    "lock.snapshot.lifecycle",
    "lock.snapshot.reader",
    "tx.refresh.begin",
    "tx.refresh.commit",
    "pragma.reader.data-version",
    "cpu.state-decode",
    "state.schema-meta-read",
    "state.identities-read",
    "state.epochs-read",
    "state.samples-read",
    "state.prediction-records-read",
    "state.evaluations-read",
    "state.exact-anchors-read",
    "state.prefix-anchors-read",
    "state.prefix-checkpoints-read",
    "state.events-read",
})
_APPLY_BASES = frozenset({
    "lock.apply.lifecycle",
    "lock.apply.writer",
    "tx.apply.begin",
    "cpu.transition",
    "instrument.worker-probe",
    "apply.duplicate-read",
    "identity.lookup",
    "identity.insert-returning",
    "global-revision.read",
    "identity.revision-read",
    "sample.exists",
    "epoch.owner-insert",
    "epoch.sample-insert",
    "epoch.prediction-insert",
    "identity.active-epoch-update",
    "sample.insert",
    "prediction-record.insert",
    "evaluation.insert",
    "exact-anchor.insert",
    "prefix-anchor.insert",
    "identity.revision-update",
    "global-revision.update",
    "epoch.empty-delete",
    "identity.empty-delete",
    "event.insert",
})
_EVENT_BASES = frozenset({
    "lock.event.lifecycle",
    "lock.event.writer",
    "tx.event.begin",
})
_ANCHOR_BASES = frozenset({
    "lock.anchor-use.lifecycle",
    "lock.anchor-use.writer",
    "tx.anchor-use.begin",
    "anchor-use.sample-update",
})
_PRUNE_BASES = frozenset({
    "lock.prune.lifecycle",
    "lock.prune.writer",
    "tx.prune.begin",
    "sample.delete",
    "event.ids-delete",
})
_DUPLICATE_BASES = frozenset({
    "event.bucket-prune",
    "event.global-prune",
})
_CLOSE_BASES = frozenset({
    "lock.close.lifecycle",
    "lock.close.reader",
    "lock.close.writer",
    "lock.close.shared-completion",
    "connection.writer.close",
    "connection.reader.close",
    "pragma.writer.checkpoint",
})

_REAL_CALL_CANCELLATION_SCENARIOS = (
    _RealCallCancellationScenario(
        "start-lock",
        frozenset({"lock.start.lifecycle"}),
        _prepare_fresh_start_cancellation,
        "start-lock-released",
    ),
    _RealCallCancellationScenario(
        "fresh-start",
        _FRESH_START_BASES,
        _prepare_fresh_start_cancellation,
        "startup-recoverable",
    ),
    _RealCallCancellationScenario(
        "existing-start",
        _EXISTING_START_BASES,
        _prepare_existing_start_cancellation,
        "startup-recoverable",
    ),
    _RealCallCancellationScenario(
        "snapshot-refresh",
        _SNAPSHOT_BASES,
        _prepare_snapshot_cancellation,
        "reader-state-retained",
    ),
    _RealCallCancellationScenario(
        "apply-precommit",
        _APPLY_BASES,
        _prepare_apply_cancellation,
        "writer-rolled-back",
    ),
    _RealCallCancellationScenario(
        "prefix-checkpoint-upsert",
        frozenset({"prefix-checkpoint.upsert"}),
        _prepare_checkpoint_upsert_cancellation,
        "writer-rolled-back",
    ),
    _RealCallCancellationScenario(
        "prefix-checkpoint-delete",
        frozenset({"prefix-checkpoint.delete"}),
        _prepare_checkpoint_delete_cancellation,
        "writer-rolled-back",
    ),
    _RealCallCancellationScenario(
        "apply-commit",
        frozenset({"tx.apply.commit"}),
        _prepare_apply_cancellation,
        "writer-committed",
        committed_observation=True,
    ),
    _RealCallCancellationScenario(
        "event-precommit",
        _EVENT_BASES,
        _prepare_event_cancellation,
        "writer-rolled-back",
    ),
    _RealCallCancellationScenario(
        "event-commit",
        frozenset({"tx.event.commit"}),
        _prepare_event_cancellation,
        "writer-committed",
        committed_observation=True,
    ),
    _RealCallCancellationScenario(
        "anchor-use-precommit",
        _ANCHOR_BASES,
        _prepare_anchor_cancellation,
        "writer-rolled-back",
    ),
    _RealCallCancellationScenario(
        "anchor-use-commit",
        frozenset({"tx.anchor-use.commit"}),
        _prepare_anchor_cancellation,
        "writer-committed",
    ),
    _RealCallCancellationScenario(
        "prune-precommit",
        _PRUNE_BASES,
        _prepare_prune_cancellation,
        "writer-rolled-back",
    ),
    _RealCallCancellationScenario(
        "prune-commit",
        frozenset({"tx.prune.commit"}),
        _prepare_prune_cancellation,
        "writer-committed",
    ),
    _RealCallCancellationScenario(
        "evaluation-pruning",
        frozenset({"evaluation.delete"}),
        _prepare_evaluation_prune_cancellation,
        "writer-rolled-back",
    ),
    _RealCallCancellationScenario(
        "duplicate-event-pruning",
        _DUPLICATE_BASES,
        _prepare_duplicate_cancellation,
        "writer-rolled-back",
    ),
    _RealCallCancellationScenario(
        "busy-retry",
        frozenset({"retry.busy-sleep"}),
        _prepare_busy_cancellation,
        "writer-rolled-back",
    ),
    _RealCallCancellationScenario(
        "close",
        _CLOSE_BASES,
        _prepare_close_cancellation,
        "closed",
    ),
    _RealCallCancellationScenario(
        "inspect-rollback",
        frozenset({"tx.inspect.rollback"}),
        _prepare_existing_start_cancellation,
        "startup-recoverable",
        "pragma.inspect.quick-check.fetch",
        StoreCancellationPhase.READ,
    ),
    _RealCallCancellationScenario(
        "migration-rollback",
        frozenset({"tx.migration.rollback"}),
        _prepare_fresh_start_cancellation,
        "startup-recoverable",
        "schema.create-statement.execute",
        StoreCancellationPhase.INSERT,
    ),
    _RealCallCancellationScenario(
        "refresh-rollback",
        frozenset({"tx.refresh.rollback"}),
        _prepare_snapshot_cancellation,
        "reader-state-retained",
        "state.schema-meta-read.fetch",
        StoreCancellationPhase.READ,
    ),
    _RealCallCancellationScenario(
        "apply-rollback",
        frozenset({"tx.apply.rollback"}),
        _prepare_apply_cancellation,
        "writer-rolled-back",
        "cpu.transition",
        StoreCancellationPhase.TRANSITION,
    ),
    _RealCallCancellationScenario(
        "event-rollback",
        frozenset({"tx.event.rollback"}),
        _prepare_event_cancellation,
        "writer-rolled-back",
        "state.schema-meta-read.fetch",
        StoreCancellationPhase.READ,
    ),
    _RealCallCancellationScenario(
        "anchor-use-rollback",
        frozenset({"tx.anchor-use.rollback"}),
        _prepare_anchor_cancellation,
        "writer-rolled-back",
        "state.schema-meta-read.fetch",
        StoreCancellationPhase.READ,
    ),
    _RealCallCancellationScenario(
        "prune-rollback",
        frozenset({"tx.prune.rollback"}),
        _prepare_prune_cancellation,
        "writer-rolled-back",
        "state.schema-meta-read.fetch",
        StoreCancellationPhase.READ,
    ),
)


def _action_base(action_id: str) -> str:
    for suffix in (".cursor-close", ".execute", ".fetch"):
        if action_id.endswith(suffix):
            return action_id.removesuffix(suffix)
    return action_id


def _real_call_scenario_by_action_id() -> dict[str, _RealCallCancellationScenario]:
    by_base: dict[str, _RealCallCancellationScenario] = {}
    for scenario in _REAL_CALL_CANCELLATION_SCENARIOS:
        for base in scenario.action_bases:
            assert base not in by_base, base
            by_base[base] = scenario
    result = {
        action_id: by_base[_action_base(action_id)]
        for action_id in EXPECTED_ACTION_IDS
    }
    assert set(result) == EXPECTED_ACTION_IDS
    assert set(by_base) == EXPECTED_ACTION_BASES
    return result


_REAL_CALL_SCENARIO_BY_ACTION_ID = _real_call_scenario_by_action_id()


_BEGIN_BASES = frozenset({
    "tx.inspect.begin",
    "tx.migration.begin",
    "tx.refresh.begin",
    "tx.apply.begin",
    "tx.event.begin",
    "tx.anchor-use.begin",
    "tx.prune.begin",
})
_PRAGMA_BASES = frozenset({
    "pragma.writer.foreign-keys-set",
    "pragma.writer.busy-timeout-set",
    "pragma.writer.synchronous-set",
    "pragma.reader.foreign-keys-set",
    "pragma.reader.busy-timeout-set",
    "pragma.reader.synchronous-set",
    "pragma.reader.query-only-set",
    "pragma.writer.foreign-keys-read",
    "pragma.reader.foreign-keys-read",
    "pragma.writer.journal-mode-wal",
    "pragma.reader.data-version",
    "instrument.writer.thread-probe-install",
    "instrument.writer.trace-install",
    "instrument.reader.thread-probe-install",
    "instrument.reader.trace-install",
})
_READ_BASES = frozenset({
    "pragma.inspect.quick-check",
    "instrument.worker-probe",
    "schema.objects-read",
    "schema.meta-read",
    "schema.table-list-read",
    "schema.table-xinfo-read",
    "schema.table-ddl-read",
    "schema.index-list-read",
    "schema.index-xinfo-read",
    "schema.foreign-keys-read",
    "state.schema-meta-read",
    "state.identities-read",
    "state.epochs-read",
    "state.samples-read",
    "state.prediction-records-read",
    "state.evaluations-read",
    "state.exact-anchors-read",
    "state.prefix-anchors-read",
    "state.events-read",
    "apply.duplicate-read",
    "identity.lookup",
    "global-revision.read",
    "identity.revision-read",
    "sample.exists",
})
_INSERT_BASES = frozenset({
    "schema.create-statement",
    "schema.meta-insert",
    "identity.insert-returning",
    "epoch.owner-insert",
    "epoch.sample-insert",
    "epoch.prediction-insert",
    "sample.insert",
    "prediction-record.insert",
    "evaluation.insert",
    "exact-anchor.insert",
    "prefix-anchor.insert",
    "event.insert",
})
_UPDATE_BASES = frozenset({
    "identity.active-epoch-update",
    "identity.revision-update",
    "global-revision.update",
    "sample.delete",
    "evaluation.delete",
    "epoch.empty-delete",
    "identity.empty-delete",
    "event.ids-delete",
    "event.bucket-prune",
    "event.global-prune",
    "anchor-use.sample-update",
})


def _expected_cancellation_phase(
    action_id: str,
    scenario: _RealCallCancellationScenario,
) -> StoreCancellationPhase:
    if scenario.trigger_phase is not None:
        return scenario.trigger_phase
    base = _action_base(action_id)
    if action_id.endswith(".cursor-close"):
        return StoreCancellationPhase.CURSOR_CLOSE
    if base.startswith("lock.close."):
        return StoreCancellationPhase.CLOSE_LOCK_WAIT
    if base.startswith("lock."):
        return StoreCancellationPhase.LOCK_WAIT
    if base.startswith("connection.") and base.endswith(".open"):
        return StoreCancellationPhase.OPEN
    if base.startswith("connection.") and base.endswith(".close"):
        return StoreCancellationPhase.CONNECTION_CLOSE
    if base == "pragma.writer.checkpoint":
        return StoreCancellationPhase.CHECKPOINT
    if base in _BEGIN_BASES:
        return StoreCancellationPhase.BEGIN
    if base in _PRAGMA_BASES:
        return StoreCancellationPhase.PRAGMA
    if base in _READ_BASES or base in {"cpu.state-decode", "state.prefix-checkpoints-read"}:
        return StoreCancellationPhase.READ
    if base == "prefix-checkpoint.upsert":
        return StoreCancellationPhase.INSERT
    if base == "prefix-checkpoint.delete":
        return StoreCancellationPhase.UPDATE
    if base in _INSERT_BASES:
        return StoreCancellationPhase.INSERT
    if base in _UPDATE_BASES:
        return StoreCancellationPhase.UPDATE
    if base == "cpu.transition":
        return StoreCancellationPhase.TRANSITION
    if base == "retry.busy-sleep":
        return StoreCancellationPhase.BUSY_RETRY
    if base.endswith(".commit"):
        return StoreCancellationPhase.COMMIT
    raise AssertionError(f"missing expected cancellation phase for {action_id}")


async def _assert_all_tracked_resources_closed(
    prepared: _PreparedCancellationScenario,
) -> None:
    assert sorted(prepared.evidence.cursor_closes) == sorted(prepared.evidence.cursor_opens)
    assert len(prepared.evidence.closes) == len(prepared.evidence.constructors)


async def _assert_real_call_postcondition(
    prepared: _PreparedCancellationScenario,
    scenario: _RealCallCancellationScenario,
    caught: StoreOperationCancelled,
) -> None:
    store = prepared.store
    assert not store._lifecycle_lock.locked()  # pyright: ignore[reportPrivateUsage]
    assert not store._reader_lock.locked()  # pyright: ignore[reportPrivateUsage]
    assert not store._writer_lock.locked()  # pyright: ignore[reportPrivateUsage]
    assert sorted(prepared.evidence.cursor_closes) == sorted(prepared.evidence.cursor_opens)
    if scenario.postcondition == "start-lock-released":
        assert store._state == "new"  # pyright: ignore[reportPrivateUsage]
        assert not prepared.path.exists()
        prepared.plan.disarm()
        await store.start()
        return
    if scenario.postcondition == "startup-recoverable":
        assert store._state == "failed"  # pyright: ignore[reportPrivateUsage]
        await _assert_all_tracked_resources_closed(prepared)
        replacement = TokenLearningStore(prepared.path)
        await replacement.start()
        await replacement.close()
        return
    if scenario.postcondition == "reader-state-retained":
        assert caught.committed_observation is None
        assert store._reader_refreshing is False  # pyright: ignore[reportPrivateUsage]
        assert store._validated_state.global_revision == prepared.baseline_cache_revision  # pyright: ignore[reportPrivateUsage]
        await _assert_write_lock_available(prepared.path)
        prepared.plan.disarm()
        refreshed = await store.snapshot_for_prediction(_identity())
        assert refreshed.revision == prepared.baseline_global_revision
        return
    if scenario.postcondition == "writer-rolled-back":
        assert caught.committed_observation is None
        await _assert_write_lock_available(prepared.path)
        assert await _scalar(prepared.path, "SELECT global_revision FROM schema_meta") == prepared.baseline_global_revision
        assert await _scalar(prepared.path, "SELECT count(*) FROM samples") == prepared.baseline_sample_count
        assert await _scalar(prepared.path, "SELECT count(*) FROM learning_events") == prepared.baseline_event_count
        assert store._validated_state.global_revision == prepared.baseline_cache_revision  # pyright: ignore[reportPrivateUsage]
        return
    if scenario.postcondition == "writer-committed":
        durable_revision = await _scalar(prepared.path, "SELECT global_revision FROM schema_meta")
        assert durable_revision > prepared.baseline_global_revision
        assert store._validated_state.global_revision == durable_revision  # pyright: ignore[reportPrivateUsage]
        assert (caught.committed_observation is not None) is scenario.committed_observation
        await _assert_write_lock_available(prepared.path)
        return
    if scenario.postcondition == "closed":
        assert caught.committed_observation is None
        assert store._state == "closed"  # pyright: ignore[reportPrivateUsage]
        await _assert_all_tracked_resources_closed(prepared)
        await _assert_write_lock_available(prepared.path)
        return
    raise AssertionError(f"unknown real-call postcondition {scenario.postcondition}")


async def _cleanup_real_call_scenario(
    prepared: _PreparedCancellationScenario,
) -> None:
    prepared.plan.disarm()
    if prepared.blocker is not None:
        await prepared.blocker.rollback()
        await prepared.blocker.close()
        prepared.blocker = None
    for store in (prepared.store, *prepared.auxiliary_stores):
        if store._state != "closed":  # pyright: ignore[reportPrivateUsage]
            await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action_id", sorted(EXPECTED_ACTION_IDS))
async def test_each_fixed_action_id_cancels_at_its_real_call_site(
    tmp_path: Path,
    action_id: str,
) -> None:
    scenario = _REAL_CALL_SCENARIO_BY_ACTION_ID[action_id]
    path = tmp_path / f"{scenario.name}-{hashlib.sha256(action_id.encode()).hexdigest()[:10]}.sqlite3"
    plan = _CancelPlan()
    evidence = _ThreadEvidence([], [], [])
    prepared = await scenario.operation_factory(path, plan, evidence)
    targets = (
        ((scenario.trigger_action_id, 1), (action_id, 1))
        if scenario.trigger_action_id is not None
        else ((action_id, 1),)
    )
    plan.arm(*targets)
    task = asyncio.ensure_future(prepared.operation_factory())
    try:
        with pytest.raises(StoreOperationCancelled) as raised:
            await task
        assert task.cancelled()
        assert raised.value.phase is _expected_cancellation_phase(action_id, scenario)
        assert action_id in plan.fired
        if scenario.trigger_action_id is not None:
            assert plan.fired == [scenario.trigger_action_id, action_id]
        else:
            assert plan.fired == [action_id]
        if prepared.blocker is not None:
            await prepared.blocker.rollback()
            await prepared.blocker.close()
            prepared.blocker = None
        await _assert_real_call_postcondition(prepared, scenario, raised.value)
    finally:
        await _cleanup_real_call_scenario(prepared)


@pytest.mark.asyncio
async def test_runtime_confirmed_action_trace_covers_fixed_literal(tmp_path: Path) -> None:
    seen: set[str] = set()
    raw_seen: list[str] = []
    raw_calls: list[str] = []
    connection_factory = _raw_counting_factory(raw_calls)

    def trace(action_id: str, raw: bool) -> None:
        seen.add(action_id)
        if raw:
            raw_seen.append(action_id)

    main_path = tmp_path / "runtime-ledger.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=5,
        samples_global=20,
        actuals_per_fingerprint=5,
        evaluations_per_window=1,
        events_per_identity=1,
        events_global=1,
    )
    main = TokenLearningStore(
        main_path,
        _limits=limits,
        _thread_probe=lambda _label, _thread: None,
        _trace_callback=lambda _statement: None,
        _action_trace=trace,
        _connection_factory=connection_factory,
    )
    await main.start()
    await main.snapshot_for_prediction(_identity())
    first = _sample(0)
    second = _sample(1)
    drifting = _sample(2)
    await main.apply_sample(
        first,
        _checkpoint_transition(
            first,
            ReplacePrefixCheckpoint(
                first.features.profile_key,
                PrefixCheckpointMode.ELIGIBLE,
                (),
                None,
            ),
        ),
    )
    await main.apply_sample(
        second,
        _checkpoint_transition(
            second,
            DeleteRecoveredPrefixCheckpoint(
                second.features.profile_key,
                1,
            ),
        ),
    )
    await main.apply_sample(drifting, _transition_for(drifting, drift=True))
    await main.apply_sample(drifting, _transition_for(drifting))
    await main.record_anchor_use(
        AnchorUseIntent(
            AnchorKind.EXACT,
            replace(drifting.identity, learning_epoch=1),
            1,
            drifting.features.full_fingerprint,
            (drifting.sample_key,),
        )
    )
    await main.record_event(
        _event(900),
        UnresolvedLearningIdentity("runtime", "responses", 1),
    )
    main._limits = replace(limits, samples_per_identity=1)  # pyright: ignore[reportPrivateUsage]
    await main.prune()

    foreign = TokenLearningStore(
        main_path,
        _action_trace=trace,
        _connection_factory=connection_factory,
    )
    await foreign.start()
    foreign_sample = _sample(50, identity=_identity(actual_provider="foreign"))
    await foreign.apply_sample(foreign_sample, _transition_for(foreign_sample))
    await main.snapshot_for_prediction(first.identity)
    await foreign.close()

    owner_awaitable = main.close()
    waiter_awaitable = main.close()
    await asyncio.gather(owner_awaitable, waiter_awaitable)

    async def rollback_scenario(
        name: str,
        target_id: str,
        operation: Callable[[TokenLearningStore, _CancelPlan], Awaitable[Any]],
    ) -> None:
        path = tmp_path / f"rollback-{name}.sqlite3"
        seed = TokenLearningStore(
            path,
            _action_trace=trace,
            _connection_factory=connection_factory,
        )
        await seed.start()
        sample = _sample(0)
        await seed.apply_sample(sample, _transition_for(sample))
        await seed.close()
        plan = _CancelPlan()
        candidate = TokenLearningStore(
            path,
            _action_hook=plan,
            _action_trace=trace,
            _connection_factory=connection_factory,
        )
        await candidate.start()
        await _expect_action_cancellation(operation(candidate, plan), plan, target_id)
        if candidate._state == "running":  # pyright: ignore[reportPrivateUsage]
            await candidate.close()

    async def apply_cancel(store: TokenLearningStore, _plan: _CancelPlan) -> Any:
        sample = _sample(10)
        return await store.apply_sample(sample, _transition_for(sample))

    async def event_cancel(store: TokenLearningStore, _plan: _CancelPlan) -> Any:
        return await store.record_event(
            _event(901),
            UnresolvedLearningIdentity("runtime-event", "responses", 1),
        )

    async def anchor_cancel(store: TokenLearningStore, _plan: _CancelPlan) -> Any:
        snapshot = await store.snapshot_for_prediction(_identity())
        source = snapshot.samples[0]
        return await store.record_anchor_use(
            AnchorUseIntent(
                AnchorKind.EXACT,
                source.identity,
                source.identity.learning_epoch,
                source.features.full_fingerprint,
                (source.sample_key,),
            )
        )

    async def prune_cancel(store: TokenLearningStore, _plan: _CancelPlan) -> Any:
        extra = _sample(11)
        await store.apply_sample(extra, _transition_for(extra))
        store._limits = replace(store._limits, samples_per_identity=1)  # pyright: ignore[reportPrivateUsage]
        return await store.prune()

    await rollback_scenario("apply", "cpu.transition", apply_cancel)
    await rollback_scenario("event", "event.insert.execute", event_cancel)
    await rollback_scenario("anchor", "anchor-use.sample-update.execute", anchor_cancel)
    await rollback_scenario("prune", "sample.delete.execute", prune_cancel)

    inspect_path = tmp_path / "inspect-rollback.sqlite3"
    inspect_seed = TokenLearningStore(
        inspect_path,
        _action_trace=trace,
        _connection_factory=connection_factory,
    )
    await inspect_seed.start()
    await inspect_seed.close()
    inspect_plan = _CancelPlan((("pragma.inspect.quick-check.fetch", 1),), True)
    with pytest.raises(StoreOperationCancelled):
        await TokenLearningStore(
            inspect_path,
            _action_hook=inspect_plan,
            _action_trace=trace,
            _connection_factory=connection_factory,
        ).start()

    migration_plan = _CancelPlan((("schema.create-statement.execute", 1),), True)
    with pytest.raises(StoreOperationCancelled):
        await TokenLearningStore(
            tmp_path / "migration-rollback.sqlite3",
            _action_hook=migration_plan,
            _action_trace=trace,
            _connection_factory=connection_factory,
        ).start()

    refresh_path = tmp_path / "refresh-rollback.sqlite3"
    refresh_writer = TokenLearningStore(
        refresh_path,
        _action_trace=trace,
        _connection_factory=connection_factory,
    )
    await refresh_writer.start()
    refresh_sample = _sample(0)
    await refresh_writer.apply_sample(refresh_sample, _transition_for(refresh_sample))
    refresh_plan = _CancelPlan()
    refresh_reader = TokenLearningStore(
        refresh_path,
        _action_hook=refresh_plan,
        _action_trace=trace,
        _connection_factory=connection_factory,
    )
    await refresh_reader.start()
    next_sample = _sample(1)
    await refresh_writer.apply_sample(next_sample, _transition_for(next_sample))
    await _expect_action_cancellation(
        refresh_reader.snapshot_for_prediction(refresh_sample.identity),
        refresh_plan,
        "state.samples-read.fetch",
    )
    await refresh_reader.close()
    await refresh_writer.close()

    busy_path = tmp_path / "runtime-busy.sqlite3"
    busy_store = TokenLearningStore(
        busy_path,
        busy_retry_delay=0.001,
        _action_trace=trace,
        _connection_factory=connection_factory,
    )
    await busy_store.start()
    locker = await aiosqlite.connect(busy_path, isolation_level=None, timeout=0)
    await locker.execute("PRAGMA busy_timeout=0")
    await locker.execute("BEGIN IMMEDIATE")
    busy_sample = _sample(0)
    busy_task = asyncio.ensure_future(
        busy_store.apply_sample(busy_sample, _transition_for(busy_sample))
    )
    for _ in range(500):
        if "retry.busy-sleep" in seen:
            break
        await asyncio.sleep(0.001)
    assert "retry.busy-sleep" in seen
    await locker.rollback()
    await locker.close()
    await busy_task
    await busy_store.close()

    assert seen == EXPECTED_ACTION_IDS, sorted(EXPECTED_ACTION_IDS - seen)
    assert set(raw_seen) == {
        action_id
        for action_id in EXPECTED_ACTION_IDS
        if not action_id.startswith("lock.")
        and not action_id.startswith("cpu.")
        and action_id != "retry.busy-sleep"
    }
    assert len(raw_calls) == len(raw_seen)


@pytest.mark.asyncio
async def test_fresh_schema_manifest_pragmas_path_and_lifecycle(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "learning.sqlite3"
    trace: list[str] = []
    store = TokenLearningStore(path, _trace_callback=trace.append)
    identity = _identity()

    assert store._limits == _StoreLimits(  # pyright: ignore[reportPrivateUsage]
        samples_per_identity=4_096,
        samples_global=32_768,
        actuals_per_fingerprint=5,
        evaluations_per_window=128,
        events_per_identity=4_096,
        events_global=32_768,
    )
    assert tokenization_learning_path() == user_data_path() / "tokenization-learning.sqlite3"
    assert tokenization_learning_path() != tokenization_state_path()
    with pytest.raises(LearningStoreStateError):
        await store.snapshot_for_prediction(identity)

    await store.start()

    assert path.is_file()
    assert await _rows(
        path,
        "SELECT version, manifest_digest, global_revision FROM schema_meta",
    ) == ((1, EXPECTED_MANIFEST_DIGEST, 0),)
    assert await _scalar(path, "PRAGMA journal_mode") == "wal"
    assert any("PRAGMA synchronous=NORMAL" in statement for statement in trace)
    assert any("PRAGMA busy_timeout=0" in statement for statement in trace)
    assert any("PRAGMA foreign_keys=ON" in statement for statement in trace)
    assert await store.snapshot_for_prediction(identity) == LearningSnapshot(identity, 0, 0)

    await store.close()
    await store.close()
    with pytest.raises(LearningStoreStateError):
        await store.snapshot_for_prediction(identity)


@pytest.mark.asyncio
async def test_independent_schema_introspection_matches_complete_v1(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    store = TokenLearningStore(path)
    await store.start()
    await store.close()

    connection = sqlite3.connect(path)
    try:
        tables = {
            row[1]
            for row in connection.execute("PRAGMA table_list")
            if row[0] == "main" and not row[1].startswith("sqlite_")
        }
        assert tables == set(EXPECTED_TABLE_COLUMNS)
        assert all(
            row[5] == 1
            for row in connection.execute("PRAGMA table_list")
            if row[0] == "main" and row[1] in tables
        )
        for table, expected_columns in EXPECTED_TABLE_COLUMNS.items():
            expected_signature = tuple(
                (
                    column,
                    "INTEGER"
                    if column in INTEGER_COLUMNS
                    else "REAL"
                    if column in REAL_COLUMNS
                    else "TEXT",
                    (table, column) not in NULLABLE_COLUMNS,
                    COLUMN_DEFAULTS.get((table, column)),
                    PRIMARY_KEY_POSITIONS.get((table, column), 0),
                )
                for column in expected_columns
            )
            actual_signature = tuple(
                (row[1], row[2], bool(row[3]), row[4], row[5])
                for row in connection.execute(f'PRAGMA table_xinfo("{table}")')
                if row[6] == 0
            )
            assert actual_signature == expected_signature
            table_sql = cast(
                str,
                connection.execute(
                    "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = ?",
                    (table,),
                ).fetchone()[0],
            )
            assert hashlib.sha256(
                _independent_normalized_ddl(table_sql).encode("utf-8")
            ).hexdigest() == EXPECTED_TABLE_DDL_DIGESTS[table]
            whitespace_normalized = " ".join(table_sql.split())
            for check in EXPECTED_CHECK_FRAGMENTS[table]:
                assert check in whitespace_normalized
            for column in EXPECTED_BINARY_COLUMNS.get(table, ()):
                assert f"{column} TEXT COLLATE BINARY" in whitespace_normalized
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert indexes == set(EXPECTED_INDEX_COLUMNS)
        for index, expected_columns in EXPECTED_INDEX_COLUMNS.items():
            table = connection.execute(
                "SELECT tbl_name FROM sqlite_schema WHERE type = 'index' AND name = ?",
                (index,),
            ).fetchone()[0]
            list_row = next(
                row
                for row in connection.execute(f'PRAGMA index_list("{table}")')
                if row[1] == index
            )
            actual = tuple(
                (row[2], bool(row[3]), row[4])
                for row in connection.execute(f'PRAGMA index_xinfo("{index}")')
                if row[5] == 1
            )
            expected = tuple(
                (
                    column,
                    (index, column) in DESCENDING_INDEX_COLUMNS,
                    "BINARY",
                )
                for column in expected_columns
            )
            assert actual == expected
            assert bool(list_row[2]) is (index in UNIQUE_INDEXES)
            assert bool(list_row[4]) is False
        sample_owner = (
            "samples",
            ("identity_id", "sample_epoch", "process_boot_id", "request_id", "attempt_index"),
            ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"),
            "NO ACTION",
            "CASCADE",
        )
        expected_foreign_keys = {
            "epoch_state": {
                ("identity_state", ("identity_id",), ("identity_id",), "NO ACTION", "CASCADE")
            },
            "samples": {
                ("epoch_state", ("identity_id", "epoch"), ("identity_id", "epoch"), "NO ACTION", "CASCADE")
            },
            "prediction_records": {
                sample_owner,
                ("epoch_state", ("identity_id", "prediction_epoch"), ("identity_id", "epoch"), "NO ACTION", "CASCADE"),
            },
            "evaluations": {
                sample_owner,
                ("epoch_state", ("identity_id", "prediction_epoch"), ("identity_id", "epoch"), "NO ACTION", "CASCADE"),
            },
            "exact_anchors": {
                ("samples", ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"), ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"), "NO ACTION", "CASCADE")
            },
            "prefix_anchors": {
                ("samples", ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"), ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"), "NO ACTION", "CASCADE")
            },
            "learning_events": {
                ("epoch_state", ("identity_id", "learning_epoch"), ("identity_id", "epoch"), "NO ACTION", "CASCADE"),
                ("samples", ("identity_id", "learning_epoch", "sample_process_boot_id", "sample_request_id", "sample_attempt_index"), ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"), "NO ACTION", "CASCADE"),
            },
        }
        for table, expected_fks in expected_foreign_keys.items():
            grouped: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
            for row in connection.execute(f'PRAGMA foreign_key_list("{table}")'):
                grouped[row[0]].append(tuple(row))
            actual_fks = {
                (
                    values[0][2],
                    tuple(value[3] for value in sorted(values, key=lambda item: item[1])),
                    tuple(value[4] for value in sorted(values, key=lambda item: item[1])),
                    values[0][5],
                    values[0][6],
                )
                for values in grouped.values()
            }
            assert actual_fks == expected_fks
        event_sql = cast(
            str,
            connection.execute(
                "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'learning_events'"
            ).fetchone()[0],
        )
        assert "reason_code IN ('sample-committed'" in event_sql
        assert "sample_process_boot_id IS NULL" in event_sql
        assert "unresolved_provider IS NOT NULL" in event_sql
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_apply_returns_independent_expected_snapshot_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    sample = _sample(0, actual=0, prefix_count=2)
    store = TokenLearningStore(path)
    await store.start()

    result = await store.apply_sample(sample, _transition_for(sample))

    candidate_key = PredictionCandidateKey(
        PredictionMethod.COLD_START,
        PredictionCandidateVariant.DETERMINISTIC,
    )
    prediction = TokenPrediction(
        identity=sample.identity,
        profile_key=sample.features.profile_key,
        method=PredictionMethod.COLD_START,
        candidate_key=candidate_key,
        unscaled_tokens=float(sample.features.known_tokens),
        sample_count=0,
        history_revision=0,
        learning_epoch=0,
        low_confidence_reasons=sample.features.low_confidence_reasons,
    )
    record = PredictionRecord(
        sample.sample_key,
        candidate_key,
        (prediction,),
        (MethodChampion(candidate_key, True),),
    )
    evaluation = PredictionEvaluation(
        sample_key=sample.sample_key,
        method=prediction.method,
        candidate_key=prediction.candidate_key,
        predicted_tokens=prediction.unscaled_tokens,
        actual_tokens=0,
        absolute_error=prediction.unscaled_tokens,
        signed_relative_error=None,
        absolute_percentage_error=None,
    )
    expected_observation = TokenLearningObservation(
        sample.sample_key,
        "committed",
        LearningReasonCode.SAMPLE_COMMITTED,
        SampleCommittedMetadata(0),
        NoPrefixCheckpointChange(),
        (evaluation,),
        1,
        0,
    )
    expected_snapshot = LearningSnapshot(
        identity=sample.identity,
        revision=1,
        active_epoch=0,
        samples=(replace(sample, committed_order=1),),
        exact_anchors=(
            learning_store_module.ExactAnchor(
                sample.identity,
                sample.features.full_fingerprint,
                (0,),
                (sample.sample_key,),
            ),
        ),
        prefix_anchors=(
            learning_store_module.PrefixAnchor(
                sample.identity,
                sample.features.context_fingerprint,
                sample.features.prefix_fingerprints[-1],
                0,
                sample.sample_key,
                sample.observed_at_us,
            ),
        ),
        prediction_records=(record,),
        evaluations=(evaluation,),
    )
    assert result == LearningApplyResult(expected_observation, expected_snapshot)
    assert await _rows(
        path,
        "SELECT (SELECT count(*) FROM samples), (SELECT count(*) FROM prediction_records), (SELECT count(*) FROM evaluations), (SELECT count(*) FROM exact_anchors), (SELECT count(*) FROM prefix_anchors), (SELECT count(*) FROM learning_events)",
    ) == ((1, 1, 1, 1, 1, 1),)
    await store.close()

    restarted = TokenLearningStore(path)
    await restarted.start()
    assert await restarted.snapshot_for_prediction(sample.identity) == expected_snapshot
    await restarted.close()


@pytest.mark.asyncio
async def test_application_duplicate_check_skips_transition_and_revision(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    sample = _sample(0)
    seen: list[int] = []
    store = TokenLearningStore(path)
    await store.start()
    first = await store.apply_sample(sample, _transition_for(sample, seen_revisions=seen))

    duplicate = await store.apply_sample(sample, _transition_for(sample, seen_revisions=seen))

    assert seen == [0]
    assert duplicate.observation == TokenLearningObservation(
        sample.sample_key,
        "duplicate",
        LearningReasonCode.DUPLICATE_SAMPLE,
        DuplicateSampleMetadata(1),
        PrefixCheckpointNotAttempted(PrefixCheckpointNotAttemptedReason.DUPLICATE_SAMPLE),
        revision=1,
        learning_epoch=0,
    )
    assert duplicate.snapshot == first.snapshot
    assert await _scalar(path, "SELECT revision FROM identity_state") == 1
    assert await _scalar(path, "SELECT global_revision FROM schema_meta") == 1
    await store.close()


@pytest.mark.asyncio
async def test_database_unique_sample_key_is_independent_last_line_of_defense(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    first = _sample(0)
    second_identity = _identity(actual_provider="provider-b")
    second = _sample(1, identity=second_identity, sample_key=first.sample_key)
    store = TokenLearningStore(path)
    await store.start()
    await store.apply_sample(first, _transition_for(first))
    await store.apply_sample(_sample(2, identity=second_identity), _transition_for(_sample(2, identity=second_identity)))
    await store.close()

    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    identity_id = connection.execute(
        "SELECT identity_id FROM identity_state WHERE actual_provider = 'provider-b'"
    ).fetchone()[0]
    profile_json = json.dumps(
        {
            "context_management_mode": second.features.profile_key.context_management_mode,
            "has_previous_response_id": False,
            "item_kinds": ["message"],
            "media_kinds": [],
            "reasoning_origins": [],
            "truncation_mode": second.features.profile_key.truncation_mode,
            "unknown_type_count": 1,
            "unknown_type_digests": list(second.features.profile_key.unknown_type_digests),
            "unknown_type_overflow": False,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        connection.execute(
            """
            INSERT INTO samples(
                identity_id, epoch, process_boot_id, request_id, attempt_index,
                observed_at_us, actual_input_tokens, last_used_order, raw_body_sha256,
                feature_raw_body_sha256, known_tokens, components_json, profile_key_json,
                profile_key_hash, feature_vector_json, full_fingerprint, context_fingerprint,
                prefix_fingerprints_json, low_confidence_reasons_json, committed_order,
                fixed_context_contribution_json, input_item_contributions_json
            ) VALUES (?, 0, ?, ?, ?, ?, ?, 99, ?, ?, ?, '[]', ?, ?, '[]', ?, ?, '[]', '[]', 3, '[0,0,0]', '[]')
            """,
            (
                identity_id,
                *second.sample_key,
                second.observed_at_us,
                second.actual_input_tokens,
                second.raw_body_sha256,
                second.features.raw_sent_body_sha256,
                second.features.known_tokens,
                profile_json,
                hashlib.sha256(profile_json.encode()).hexdigest(),
                second.features.full_fingerprint,
                second.features.context_fingerprint,
            ),
        )
    connection.close()


@pytest.mark.asyncio
async def test_learning_event_failure_rolls_back_sample_revision_and_derived_rows(tmp_path: Path) -> None:
    path = tmp_path / "event-failure.sqlite3"
    store = TokenLearningStore(path)
    await store.start()
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TRIGGER reject_learning_event
        BEFORE INSERT ON learning_events
        BEGIN
            SELECT RAISE(ABORT, 'injected event failure');
        END;
        """
    )
    connection.commit()
    connection.close()
    sample = _sample(0)

    with pytest.raises(sqlite3.IntegrityError, match="injected event failure"):
        await store.apply_sample(sample, _transition_for(sample))

    assert await _rows(
        path,
        "SELECT (SELECT global_revision FROM schema_meta), (SELECT count(*) FROM identity_state), (SELECT count(*) FROM samples), (SELECT count(*) FROM prediction_records), (SELECT count(*) FROM evaluations), (SELECT count(*) FROM exact_anchors), (SELECT count(*) FROM prefix_anchors), (SELECT count(*) FROM learning_events)",
    ) == ((0, 0, 0, 0, 0, 0, 0, 0),)
    await _assert_write_lock_available(path)
    await store.close()


@pytest.mark.asyncio
async def test_two_writers_serialize_transition_on_latest_revision(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    first_store = TokenLearningStore(path, busy_retry_delay=0.001)
    second_store = TokenLearningStore(path, busy_retry_delay=0.001)
    await first_store.start()
    await second_store.start()
    seed = _sample(0)
    await first_store.apply_sample(seed, _transition_for(seed))
    first = _sample(1)
    second = _sample(2)
    entered = threading.Event()
    release = threading.Event()
    second_revisions: list[int] = []
    first_task = asyncio.ensure_future(
        first_store.apply_sample(
            first,
            _transition_for(first, entered=entered, release=release),
        )
    )
    await _wait_thread_event(entered)
    second_task = asyncio.ensure_future(
        second_store.apply_sample(
            second,
            _transition_for(second, seen_revisions=second_revisions),
        )
    )
    await asyncio.sleep(0.05)
    assert second_revisions == []
    release.set()

    first_result, second_result = await asyncio.gather(first_task, second_task)

    assert first_result.snapshot.revision == 2
    assert second_revisions == [2]
    assert second_result.snapshot.revision == 3
    assert {sample.sample_key for sample in second_result.snapshot.samples} == {
        seed.sample_key,
        first.sample_key,
        second.sample_key,
    }
    await first_store.close()
    await second_store.close()


@pytest.mark.asyncio
async def test_reader_explicit_transaction_never_mixes_revisions(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    writer = TokenLearningStore(path)
    await writer.start()
    first = _sample(0)
    second = _sample(1)
    third = _sample(2)
    await writer.apply_sample(first, _transition_for(first))
    entered = asyncio.Event()
    release = asyncio.Event()
    hook_enabled = False

    async def hook(stage: str) -> None:
        assert stage == "after-identities"
        if hook_enabled:
            entered.set()
            await release.wait()

    reader = TokenLearningStore(path, _reader_step_hook=hook)
    await reader.start()
    hook_enabled = True
    await writer.apply_sample(second, _transition_for(second))
    read_task = asyncio.ensure_future(reader.snapshot_for_prediction(first.identity))
    await asyncio.wait_for(entered.wait(), timeout=2)
    await writer.apply_sample(third, _transition_for(third))
    stale_during_refresh = await reader.snapshot_for_prediction(first.identity)
    assert stale_during_refresh.revision == 1
    assert stale_during_refresh.is_stale is True
    release.set()
    interleaved = await read_task

    assert interleaved.revision == 2
    assert len(interleaved.samples) == 2
    refreshed = await reader.snapshot_for_prediction(first.identity)
    assert refreshed.revision == 3
    assert len(refreshed.samples) == 3
    await reader.close()
    await writer.close()


@pytest.mark.asyncio
async def test_local_cache_and_foreign_data_version_refresh(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    local = TokenLearningStore(path)
    foreign = TokenLearningStore(path)
    await local.start()
    await foreign.start()
    first = _sample(0)
    second = _sample(1)

    applied = await local.apply_sample(first, _transition_for(first))
    assert await local.snapshot_for_prediction(first.identity) == applied.snapshot
    await foreign.apply_sample(second, _transition_for(second))
    refreshed = await local.snapshot_for_prediction(first.identity)

    assert refreshed.revision == 2
    assert {sample.sample_key for sample in refreshed.samples} == {
        first.sample_key,
        second.sample_key,
    }
    await foreign.close()
    await local.close()


@pytest.mark.asyncio
async def test_concurrent_fresh_starters_converge_after_both_inspect_empty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning.sqlite3"
    path.touch()
    both_inspected = asyncio.Event()
    release = asyncio.Event()
    inspection_count = 0

    async def empty_inspection_barrier(
        action_id: str,
        _phase: StoreCancellationPhase,
    ) -> None:
        nonlocal inspection_count
        if action_id != "connection.inspect.close":
            return
        inspection_count += 1
        if inspection_count == 2:
            both_inspected.set()
        await release.wait()

    first = TokenLearningStore(
        path,
        busy_retry_delay=0.001,
        _action_hook=empty_inspection_barrier,
    )
    second = TokenLearningStore(
        path,
        busy_retry_delay=0.001,
        _action_hook=empty_inspection_barrier,
    )
    first_task = asyncio.ensure_future(first.start())
    second_task = asyncio.ensure_future(second.start())
    await asyncio.wait_for(both_inspected.wait(), timeout=2)
    assert inspection_count == 2
    assert not first_task.done()
    assert not second_task.done()
    release.set()

    await asyncio.gather(first_task, second_task)

    assert sorted((first._created_schema, second._created_schema)) == [  # pyright: ignore[reportPrivateUsage]
        False,
        True,
    ]
    assert await _rows(path, "SELECT version, manifest_digest FROM schema_meta") == (
        (1, EXPECTED_MANIFEST_DIGEST),
    )
    await first.close()
    await second.close()


@pytest.mark.asyncio
async def test_corrupt_unsupported_fake_v1_and_inactive_corruption_preserve_bytes(
    tmp_path: Path,
) -> None:
    corrupt_path = tmp_path / "corrupt.sqlite3"
    corrupt_bytes = b"not sqlite\x00evidence"
    corrupt_path.write_bytes(corrupt_bytes)
    with pytest.raises(LearningStoreStartupError) as corrupt_error:
        await TokenLearningStore(corrupt_path).start()
    assert corrupt_error.value.reason is LearningStoreStartupReason.CORRUPT
    assert corrupt_path.read_bytes() == corrupt_bytes

    unsupported_path = tmp_path / "unsupported.sqlite3"
    connection = sqlite3.connect(unsupported_path)
    connection.execute(
        "CREATE TABLE schema_meta(singleton INTEGER PRIMARY KEY, version INTEGER, manifest_digest TEXT, global_revision INTEGER)"
    )
    connection.execute(
        "INSERT INTO schema_meta VALUES (1, 99, ?, 0)",
        (EXPECTED_MANIFEST_DIGEST,),
    )
    connection.commit()
    connection.close()
    unsupported_bytes = unsupported_path.read_bytes()
    with pytest.raises(UnsupportedLearningSchemaError):
        await TokenLearningStore(unsupported_path).start()
    assert unsupported_path.read_bytes() == unsupported_bytes

    fake_path = tmp_path / "fake.sqlite3"
    valid = TokenLearningStore(fake_path)
    await valid.start()
    await valid.close()
    connection = sqlite3.connect(fake_path)
    connection.execute("DROP INDEX samples_global_key_uq")
    connection.commit()
    connection.close()
    fake_bytes = fake_path.read_bytes()
    with pytest.raises(LearningStoreStartupError) as fake_error:
        await TokenLearningStore(fake_path).start()
    assert fake_error.value.reason is LearningStoreStartupReason.MANIFEST_MISMATCH
    assert fake_path.read_bytes() == fake_bytes

    digest_path = tmp_path / "digest.sqlite3"
    digest_store = TokenLearningStore(digest_path)
    await digest_store.start()
    await digest_store.close()
    connection = sqlite3.connect(digest_path)
    connection.execute("UPDATE schema_meta SET manifest_digest = ?", (_digest("wrong-manifest"),))
    connection.commit()
    connection.close()
    digest_bytes = digest_path.read_bytes()
    with pytest.raises(LearningStoreStartupError) as digest_error:
        await TokenLearningStore(digest_path).start()
    assert digest_error.value.reason is LearningStoreStartupReason.MANIFEST_MISMATCH
    assert digest_path.read_bytes() == digest_bytes

    nocase_path = tmp_path / "nocase.sqlite3"
    nocase_store = TokenLearningStore(nocase_path)
    await nocase_store.start()
    await nocase_store.close()
    connection = sqlite3.connect(nocase_path)
    connection.execute("PRAGMA writable_schema=ON")
    connection.execute(
        """
        UPDATE sqlite_schema
        SET sql = replace(
            sql,
            'components_json TEXT NOT NULL',
            'components_json TEXT COLLATE NOCASE NOT NULL'
        )
        WHERE type = 'table' AND name = 'samples'
        """
    )
    connection.execute("PRAGMA writable_schema=OFF")
    connection.commit()
    connection.close()
    nocase_bytes = nocase_path.read_bytes()
    with pytest.raises(LearningStoreStartupError) as nocase_error:
        await TokenLearningStore(nocase_path).start()
    assert nocase_error.value.reason is LearningStoreStartupReason.MANIFEST_MISMATCH
    assert nocase_path.read_bytes() == nocase_bytes

    inactive_path = tmp_path / "inactive.sqlite3"
    active = TokenLearningStore(inactive_path)
    await active.start()
    first = _sample(0)
    drifting = _sample(1)
    await active.apply_sample(first, _transition_for(first))
    await active.apply_sample(drifting, _transition_for(drifting, drift=True))
    await active.close()
    connection = sqlite3.connect(inactive_path)
    connection.execute("UPDATE samples SET profile_key_hash = ? WHERE epoch = 0", (_digest("bad"),))
    connection.commit()
    connection.close()
    inactive_bytes = inactive_path.read_bytes()
    with pytest.raises(LearningStoreStartupError) as inactive_error:
        await TokenLearningStore(inactive_path).start()
    assert inactive_error.value.reason is LearningStoreStartupReason.INVALID_STATE
    assert inactive_path.read_bytes() == inactive_bytes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption_sql",
    [
        "UPDATE samples SET profile_key_hash = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'",
        "UPDATE learning_events SET bucket_key = 'identity:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'",
        "UPDATE exact_anchors SET full_fingerprint = 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'",
        "UPDATE prediction_records SET profile_key_hash = 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd'",
    ],
)
async def test_startup_recomputes_hash_bucket_and_anchor_links(
    tmp_path: Path,
    corruption_sql: str,
) -> None:
    path = tmp_path / f"corruption-{hashlib.sha256(corruption_sql.encode()).hexdigest()[:8]}.sqlite3"
    sample = _sample(0)
    store = TokenLearningStore(path)
    await store.start()
    await store.apply_sample(sample, _transition_for(sample))
    await store.close()
    connection = sqlite3.connect(path)
    connection.execute(corruption_sql)
    connection.commit()
    connection.close()
    before = path.read_bytes()

    with pytest.raises(LearningStoreStartupError) as caught:
        await TokenLearningStore(path).start()

    assert caught.value.reason is LearningStoreStartupReason.INVALID_STATE
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_store_stamps_pending_checkpoint_evidence_before_durable_codec(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pending-checkpoint.sqlite3"
    sample = _sample(0)
    with pytest.raises(ValueError, match="sample codec requires a positive committed_order"):
        learning_store_module._encode_sample(sample)  # pyright: ignore[reportPrivateUsage]
    store = TokenLearningStore(path)
    await store.start()
    command = ReplacePrefixCheckpoint(
        sample.features.profile_key,
        PrefixCheckpointMode.ELIGIBLE,
        (PendingPrefixChampionErrorTriple(0.2, None, 0.1),),
        None,
    )

    result = await store.apply_sample(
        sample,
        _checkpoint_transition(sample, command),
    )

    checkpoint = result.snapshot.prefix_checkpoints[0]
    assert result.snapshot.samples[0].committed_order == 1
    assert checkpoint.state_revision == checkpoint.updated_order == 1
    assert checkpoint.evidence[0].committed_order == 1
    assert isinstance(result.observation.prefix_checkpoint_outcome, PrefixCheckpointApplied)
    await store.close()

    restarted = TokenLearningStore(path)
    await restarted.start()
    restored = await restarted.snapshot_for_prediction(sample.identity)
    assert restored.prefix_checkpoints == (checkpoint,)
    await restarted.close()


@pytest.mark.asyncio
async def test_checkpoint_capacity_rolls_over_current_identity_and_rejects_zero_benefit_global(
    tmp_path: Path,
) -> None:
    rollover_path = tmp_path / "checkpoint-rollover.sqlite3"
    rollover_store = TokenLearningStore(
        rollover_path,
        _limits=_StoreLimits(
            prefix_checkpoints_per_identity=1,
            prefix_checkpoints_global=10,
        ),
    )
    await rollover_store.start()
    first = _sample(0, profile_suffix="a")
    second = _sample(1, profile_suffix="b")
    for sample in (first, second):
        result = await rollover_store.apply_sample(
            sample,
            _checkpoint_transition(
                sample,
                ReplacePrefixCheckpoint(
                    sample.features.profile_key,
                    PrefixCheckpointMode.ELIGIBLE,
                    (),
                    None,
                ),
            ),
        )
    assert isinstance(
        result.observation.prefix_checkpoint_outcome,
        PrefixCheckpointCapacityRolledOver,
    )
    assert result.snapshot.active_epoch == 1
    assert result.snapshot.samples == result.snapshot.prefix_checkpoints == ()
    await rollover_store.close()

    reject_path = tmp_path / "checkpoint-reject.sqlite3"
    reject_store = TokenLearningStore(
        reject_path,
        _limits=_StoreLimits(
            prefix_checkpoints_per_identity=10,
            prefix_checkpoints_global=1,
        ),
    )
    await reject_store.start()
    owner = _sample(2, profile_suffix="owner")
    await reject_store.apply_sample(
        owner,
        _checkpoint_transition(
            owner,
            ReplacePrefixCheckpoint(
                owner.features.profile_key,
                PrefixCheckpointMode.ELIGIBLE,
                (),
                None,
            ),
        ),
    )
    blocked = _sample(
        3,
        identity=_identity(actual_provider="other"),
        profile_suffix="blocked",
    )
    rejected = await reject_store.apply_sample(
        blocked,
        _checkpoint_transition(
            blocked,
            ReplacePrefixCheckpoint(
                blocked.features.profile_key,
                PrefixCheckpointMode.ELIGIBLE,
                (),
                None,
            ),
        ),
    )
    assert isinstance(
        rejected.observation.prefix_checkpoint_outcome,
        PrefixCheckpointCapacityRejected,
    )
    assert rejected.snapshot.samples == (replace(blocked, committed_order=2),)
    assert rejected.snapshot.prefix_checkpoints == ()
    await reject_store.close()


@pytest.mark.asyncio
async def test_malformed_pending_checkpoint_commands_reject_before_codec_or_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "malformed-pending.sqlite3"
    store = TokenLearningStore(path)
    await store.start()
    seed = _sample(0)
    await store.apply_sample(seed, _transition_for(seed))
    baseline = path.read_bytes()
    baseline_revision = await _scalar(path, "SELECT global_revision FROM schema_meta")
    baseline_events = await _scalar(path, "SELECT count(*) FROM learning_events")
    baseline_checkpoints = await _scalar(path, "SELECT count(*) FROM prefix_checkpoints")
    pending = PendingPrefixChampionErrorTriple(0.2, None, 0.1)
    persisted = PrefixChampionErrorTriple(0.2, None, 0.1, 1)

    def forged_replace(
        evidence: tuple[PrefixChampionErrorTriple | PendingPrefixChampionErrorTriple, ...],
    ) -> ReplacePrefixCheckpoint:
        command = object.__new__(ReplacePrefixCheckpoint)
        object.__setattr__(command, "profile_key", seed.features.profile_key)
        object.__setattr__(command, "mode", PrefixCheckpointMode.ELIGIBLE)
        object.__setattr__(command, "evidence", evidence)
        object.__setattr__(command, "expected_prior_state_revision", None)
        return command

    original_encode = learning_store_module._encode_sample  # pyright: ignore[reportPrivateUsage]

    def fail_if_encoded(candidate: StoredSample) -> object:
        if candidate.committed_order is None:
            raise AssertionError("malformed logical command reached persistent codec")
        return original_encode(candidate)

    monkeypatch.setattr(learning_store_module, "_encode_sample", fail_if_encoded)
    for evidence in (
        (pending, pending),
        (pending, persisted),
        (cast(Any, object.__new__(PrefixChampionErrorTriple)),),
    ):
        sample = _sample(len(evidence) + 10 + (1 if evidence[0] is pending else 0))
        with pytest.raises(LearningStoreTransitionError):
            await store.apply_sample(
                sample,
                _checkpoint_transition(sample, forged_replace(evidence)),
            )
    with pytest.raises(ValueError, match="public checkpoint evidence"):
        PrefixEligibilityCheckpoint(
            seed.features.profile_key,
            PrefixCheckpointMode.ELIGIBLE,
            (cast(Any, pending),),
            1,
            1,
        )
    assert path.read_bytes() == baseline
    assert await _scalar(path, "SELECT global_revision FROM schema_meta") == baseline_revision
    assert await _scalar(path, "SELECT count(*) FROM learning_events") == baseline_events
    assert await _scalar(path, "SELECT count(*) FROM prefix_checkpoints") == baseline_checkpoints
    await store.close()


@pytest.mark.asyncio
async def test_current_sample_prune_keeps_applied_checkpoint_and_event_truth(
    tmp_path: Path,
) -> None:
    path = tmp_path / "checkpoint-current-prune.sqlite3"
    store = TokenLearningStore(
        path,
        _limits=_StoreLimits(samples_per_identity=1),
    )
    await store.start()
    retained = _sample(0, observed_at_us=10)
    await store.apply_sample(retained, _transition_for(retained))
    connection = sqlite3.connect(path)
    connection.execute("UPDATE samples SET last_used_order = 100")
    connection.commit()
    connection.close()
    current = _sample(1, observed_at_us=1, profile_suffix="current")

    result = await store.apply_sample(
        current,
        _checkpoint_transition(
            current,
            ReplacePrefixCheckpoint(
                current.features.profile_key,
                PrefixCheckpointMode.ELIGIBLE,
                (),
                None,
            ),
        ),
    )

    assert result.observation.reason_code is LearningReasonCode.PRUNED
    assert isinstance(result.observation.prefix_checkpoint_outcome, PrefixCheckpointApplied)
    assert tuple(sample.sample_key for sample in result.snapshot.samples) == (
        retained.sample_key,
    )
    assert tuple(
        checkpoint.profile_key for checkpoint in result.snapshot.prefix_checkpoints
    ) == (current.features.profile_key,)
    event_rows = await _rows(
        path,
        "SELECT sample_process_boot_id, prefix_checkpoint_outcome_json FROM learning_events ORDER BY event_id DESC LIMIT 1",
    )
    assert event_rows[0][0] is None
    assert json.loads(cast(str, event_rows[0][1]))["kind"] == "applied"
    await store.close()


@pytest.mark.asyncio
async def test_drift_requires_nochange_and_removes_old_epoch_checkpoints(
    tmp_path: Path,
) -> None:
    path = tmp_path / "checkpoint-drift.sqlite3"
    store = TokenLearningStore(path)
    await store.start()
    first = _sample(0)
    await store.apply_sample(
        first,
        _checkpoint_transition(
            first,
            ReplacePrefixCheckpoint(
                first.features.profile_key,
                PrefixCheckpointMode.ELIGIBLE,
                (),
                None,
            ),
        ),
    )
    drifting = _sample(1)
    result = await store.apply_sample(drifting, _transition_for(drifting, drift=True))

    assert result.snapshot.active_epoch == 1
    assert result.snapshot.prefix_checkpoints == ()
    assert result.observation.prefix_checkpoint_outcome == NoPrefixCheckpointChange()
    await store.close()


def test_failed_observation_rejects_duplicate_and_rejected_checkpoint_non_attempts() -> None:
    common: dict[str, Any] = {
        "sample_key": ("boot", "failed-checkpoint", 0),
        "outcome": "failed",
        "reason_code": LearningReasonCode.ANALYSIS_FAILED,
        "metadata": AnalysisFailedMetadata(AnalysisFailureStage.PERSISTENCE),
    }
    for reason in (
        PrefixCheckpointNotAttemptedReason.DUPLICATE_SAMPLE,
        PrefixCheckpointNotAttemptedReason.SAMPLE_REJECTED,
    ):
        with pytest.raises(ValueError, match="NotCommitted or failure-before-policy"):
            TokenLearningObservation(
                **common,
                prefix_checkpoint_outcome=PrefixCheckpointNotAttempted(reason),
            )
    assert TokenLearningObservation(
        **common,
        prefix_checkpoint_outcome=PrefixCheckpointNotAttempted(
            PrefixCheckpointNotAttemptedReason.FAILURE_BEFORE_POLICY
        ),
    ).outcome == "failed"
    assert TokenLearningObservation(
        **common,
        prefix_checkpoint_outcome=PrefixCheckpointNotCommitted(),
    ).outcome == "failed"


@pytest.mark.asyncio
async def test_startup_rejects_failed_event_with_wrong_not_attempted_reason(
    tmp_path: Path,
) -> None:
    path = tmp_path / "failed-outcome-corruption.sqlite3"
    store = TokenLearningStore(path)
    await store.start()
    await store.record_event(
        _event(0, LearningReasonCode.ANALYSIS_FAILED),
        UnresolvedLearningIdentity("failed-event", "responses", 1),
    )
    await store.close()
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE learning_events SET prefix_checkpoint_outcome_json = ?",
        ('{"kind":"not-attempted","reason":"duplicate-sample"}',),
    )
    connection.commit()
    connection.close()
    before = path.read_bytes()

    with pytest.raises(LearningStoreStartupError) as caught:
        await TokenLearningStore(path).start()

    assert caught.value.reason is LearningStoreStartupReason.INVALID_STATE
    assert path.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "prefix_count"),
    [
        ("missing-prediction", 1),
        ("missing-exact", 1),
        ("missing-prefix", 1),
        ("extra-prefix", 0),
        ("evaluation-mismatch", 1),
        ("evaluation-extra", 1),
        ("event-key-mismatch", 1),
        ("event-metadata-mismatch", 1),
        ("unreferenced-epoch", 1),
        ("unreferenced-identity", 1),
    ],
)
async def test_complete_derived_graph_rejects_each_single_corruption(
    tmp_path: Path,
    case: str,
    prefix_count: int,
) -> None:
    path = tmp_path / f"graph-{case}.sqlite3"
    sample = _sample(0, prefix_count=prefix_count)
    store = TokenLearningStore(path)
    await store.start()
    await store.apply_sample(sample, _transition_for(sample))
    await store.close()
    connection = sqlite3.connect(path)
    if case == "missing-prediction":
        connection.execute("DELETE FROM evaluations")
        connection.execute("DELETE FROM prediction_records")
        connection.execute("DELETE FROM learning_events")
    elif case == "missing-exact":
        connection.execute("DELETE FROM exact_anchors")
    elif case == "missing-prefix":
        connection.execute("DELETE FROM prefix_anchors")
    elif case == "extra-prefix":
        connection.execute(
            """
            INSERT INTO prefix_anchors(
                identity_id, epoch, process_boot_id, request_id, attempt_index,
                context_fingerprint, item_count, prefix_fingerprint, actual_tokens
            ) VALUES (1, 0, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                *sample.sample_key,
                sample.features.context_fingerprint,
                _digest("fabricated-prefix"),
                sample.actual_input_tokens,
            ),
        )
    elif case == "evaluation-mismatch":
        connection.execute(
            """
            UPDATE evaluations
            SET predicted_tokens = 11.0,
                absolute_error = 1.0,
                signed_relative_error = ?,
                absolute_percentage_error = ?
            """,
            (-1 / 12, 1 / 12),
        )
    elif case == "evaluation-extra":
        connection.execute(
            """
            INSERT INTO evaluations(
                identity_id, sample_epoch, process_boot_id, request_id, attempt_index,
                method, candidate_variant, prediction_epoch, profile_key_hash, ordinal,
                predicted_tokens, actual_tokens, absolute_error, signed_relative_error,
                absolute_percentage_error
            )
            SELECT identity_id, sample_epoch, process_boot_id, request_id, attempt_index,
                   'history-exact', 'median', prediction_epoch, profile_key_hash, 1, 10.0,
                   12, 2.0, -1.0 / 6.0, 1.0 / 6.0
            FROM prediction_records
            """
        )
    elif case == "event-key-mismatch":
        connection.execute("UPDATE learning_events SET request_id = 'different-event-key'")
    elif case == "event-metadata-mismatch":
        connection.execute(
            "UPDATE learning_events SET metadata_json = '{\"actual_input_tokens\":999}'"
        )
    elif case == "unreferenced-epoch":
        connection.execute(
            "INSERT INTO epoch_state(identity_id, epoch, created_order) VALUES (1, 9, 9)"
        )
    else:
        connection.execute(
            """
            INSERT INTO identity_state(
                actual_provider, resolved_model, endpoint, wire_format, tokenizer,
                descriptor_fingerprint, estimator_generation, profile_schema_revision,
                active_epoch, revision
            ) VALUES ('orphan', 'model', 'responses', 'openai-responses', 'tokenizer', ?, 1, 1, 0, 0)
            """,
            (_digest("orphan-descriptor"),),
        )
        orphan_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO epoch_state(identity_id, epoch, created_order) VALUES (?, 0, 0)",
            (orphan_id,),
        )
    connection.commit()
    connection.close()
    before = path.read_bytes()

    with pytest.raises(LearningStoreStartupError) as caught:
        await TokenLearningStore(path).start()

    assert caught.value.reason is LearningStoreStartupReason.INVALID_STATE
    assert path.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "corrupt_value"),
    [
        ("previous_epoch", 0),
        ("identity_epoch", 0),
        ("new_epoch", 3),
    ],
)
async def test_three_epoch_drift_event_rejects_each_prediction_relation_corruption(
    tmp_path: Path,
    field: str,
    corrupt_value: int,
) -> None:
    path = tmp_path / f"drift-relation-{field}.sqlite3"
    store = TokenLearningStore(path)
    await store.start()
    first = _sample(0)
    second = _sample(1)
    third = _sample(2)
    await store.apply_sample(first, _transition_for(first))
    await store.apply_sample(second, _transition_for(second, drift=True))
    await store.apply_sample(third, _transition_for(third, drift=True))
    await store.close()

    connection = sqlite3.connect(path)
    row = connection.execute(
        "SELECT event_id, drift_metadata_json FROM learning_events WHERE learning_epoch = 2"
    ).fetchone()
    assert row is not None
    metadata = json.loads(cast(str, row[1]))
    assert metadata == {
        "evidence_count": 3,
        "identity_epoch": 1,
        "kind": "exact",
        "consecutive_count": 3,
        "new_epoch": 2,
        "previous_epoch": 1,
    }
    metadata[field] = corrupt_value
    connection.execute(
        "UPDATE learning_events SET drift_metadata_json = ? WHERE event_id = ?",
        (json.dumps(metadata, separators=(",", ":"), sort_keys=True), row[0]),
    )
    connection.commit()
    connection.close()
    before = path.read_bytes()

    with pytest.raises(LearningStoreStartupError) as caught:
        await TokenLearningStore(path).start()

    assert caught.value.reason is LearningStoreStartupReason.INVALID_STATE
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_newest_128_diagnostics_and_160_record_reconstruction_are_independent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "diagnostic-window.sqlite3"
    template = _sample(0, prefix_count=0, actual=12, observed_at_us=1)
    store = TokenLearningStore(path)
    await store.start()
    await store.apply_sample(template, _transition_for(template))
    await store.close()
    connection = sqlite3.connect(path)
    template_row = connection.execute(
        """
        SELECT components_json, profile_key_json, profile_key_hash,
               feature_vector_json, context_fingerprint,
               prefix_fingerprints_json, low_confidence_reasons_json,
               fixed_context_contribution_json, input_item_contributions_json
        FROM samples
        LIMIT 1
        """
    ).fetchone()
    candidates_json = json.dumps(
        [
            {
                "low_confidence_reasons": ["zero-prior:unknown-items"],
                "method": "cold-start",
                "variant": "deterministic",
                "sample_count": 0,
                "unscaled_tokens": 10.0,
            }
        ],
        separators=(",", ":"),
        sort_keys=True,
    )
    champions_json = json.dumps(
        [
            {
                "eligible_for_selection": True,
                "method": "cold-start",
                "variant": "deterministic",
            }
        ],
        separators=(",", ":"),
        sort_keys=True,
    )
    for index in range(1, 160):
        sample_key = ("bulk", f"request-{index:03d}", 0)
        body_digest = _digest(f"bulk-body-{index}")
        full_fingerprint = _digest(f"bulk-full-{index}")
        connection.execute(
            """
            INSERT INTO samples(
                identity_id, epoch, process_boot_id, request_id, attempt_index,
                observed_at_us, actual_input_tokens, last_used_order,
                raw_body_sha256, feature_raw_body_sha256, known_tokens,
                capability_visual_tokens, components_json, profile_key_json,
                profile_key_hash, feature_vector_json, full_fingerprint,
                context_fingerprint, prefix_fingerprints_json,
                low_confidence_reasons_json, committed_order,
                fixed_context_contribution_json, input_item_contributions_json
            ) VALUES (1, 0, ?, ?, ?, ?, 12, ?, ?, ?, 10, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                *sample_key,
                index + 1,
                index + 1,
                body_digest,
                body_digest,
                template_row[0],
                template_row[1],
                template_row[2],
                template_row[3],
                full_fingerprint,
                template_row[4],
                template_row[5],
                template_row[6],
                index + 1,
                template_row[7],
                template_row[8],
            ),
        )
        connection.execute(
            """
            INSERT INTO prediction_records(
                identity_id, sample_epoch, process_boot_id, request_id,
                attempt_index, prediction_epoch, profile_key_hash,
                selected_method, selected_variant, history_revision,
                method_champions_json, candidates_json
            ) VALUES (1, 0, ?, ?, ?, 0, ?, 'cold-start', 'deterministic', ?, ?, ?)
            """,
            (*sample_key, template_row[2], index, champions_json, candidates_json),
        )
        connection.execute(
            """
            INSERT INTO evaluations(
                identity_id, sample_epoch, process_boot_id, request_id,
                attempt_index, method, candidate_variant, prediction_epoch,
                profile_key_hash, ordinal, predicted_tokens, actual_tokens,
                absolute_error, signed_relative_error, absolute_percentage_error
            ) VALUES (1, 0, ?, ?, ?, 'cold-start', 'deterministic', 0, ?, 0, 10.0, 12, 2.0, ?, ?)
            """,
            (*sample_key, template_row[2], -1 / 6, 1 / 6),
        )
        connection.execute(
            """
            INSERT INTO exact_anchors(
                identity_id, epoch, process_boot_id, request_id,
                attempt_index, full_fingerprint, actual_tokens
            ) VALUES (1, 0, ?, ?, ?, ?, 12)
            """,
            (*sample_key, full_fingerprint),
        )
    connection.execute(
        """
        DELETE FROM evaluations
        WHERE (identity_id, sample_epoch, process_boot_id, request_id, attempt_index, method, candidate_variant) IN (
            SELECT evaluations.identity_id, evaluations.sample_epoch,
                   evaluations.process_boot_id, evaluations.request_id,
                   evaluations.attempt_index, evaluations.method,
                   evaluations.candidate_variant
            FROM evaluations
            JOIN samples
              ON samples.identity_id = evaluations.identity_id
             AND samples.epoch = evaluations.sample_epoch
             AND samples.process_boot_id = evaluations.process_boot_id
             AND samples.request_id = evaluations.request_id
             AND samples.attempt_index = evaluations.attempt_index
            ORDER BY samples.observed_at_us ASC,
                     samples.process_boot_id COLLATE BINARY ASC,
                     samples.request_id COLLATE BINARY ASC,
                     samples.attempt_index ASC
            LIMIT 32
        )
        """
    )
    connection.execute("UPDATE identity_state SET revision = 160")
    connection.execute("UPDATE schema_meta SET global_revision = 160")
    connection.commit()
    connection.close()

    restored = TokenLearningStore(path)
    await restored.start()
    state = restored._validated_state  # pyright: ignore[reportPrivateUsage]
    assert len(state.samples) == 160
    assert len(state.prediction_records) == 160
    assert len(state.reconstructed_evaluations) == 160
    assert len(state.evaluations) == 128
    sample_by_owner = {sample.owner_key: sample for sample in state.samples}
    ordered = sorted(
        state.reconstructed_evaluations,
        key=lambda value: (
            -sample_by_owner[value.owner_key].sample.observed_at_us,
            sample_by_owner[value.owner_key].sample.sample_key,
        ),
    )
    recent = ordered[:32]
    reference = ordered[32:160]
    assert len(recent) == 32
    assert len(reference) == 128
    assert {value.owner_key for value in recent}.isdisjoint(
        value.owner_key for value in reference
    )
    assert {
        (
            value.evaluation.predicted_tokens,
            value.evaluation.actual_tokens,
            value.evaluation.absolute_error,
            value.evaluation.signed_relative_error,
            value.evaluation.absolute_percentage_error,
        )
        for value in ordered
    } == {(10.0, 12, 2.0, -1 / 6, 1 / 6)}
    await restored.close()

    missing_newest = tmp_path / "missing-newest.sqlite3"
    shutil.copyfile(path, missing_newest)
    connection = sqlite3.connect(missing_newest)
    connection.execute(
        """
        DELETE FROM evaluations
        WHERE request_id = 'request-159'
        """
    )
    connection.commit()
    connection.close()
    with pytest.raises(LearningStoreStartupError) as missing_error:
        await TokenLearningStore(missing_newest).start()
    assert missing_error.value.reason is LearningStoreStartupReason.INVALID_STATE

    ordinal_mismatch = tmp_path / "ordinal-mismatch.sqlite3"
    shutil.copyfile(path, ordinal_mismatch)
    connection = sqlite3.connect(ordinal_mismatch)
    connection.execute("UPDATE evaluations SET ordinal = 1 WHERE request_id = 'request-159'")
    connection.commit()
    connection.close()
    with pytest.raises(LearningStoreStartupError) as ordinal_error:
        await TokenLearningStore(ordinal_mismatch).start()
    assert ordinal_error.value.reason is LearningStoreStartupReason.INVALID_STATE

    extra = tmp_path / "extra-evaluation.sqlite3"
    shutil.copyfile(path, extra)
    connection = sqlite3.connect(extra)
    row = connection.execute(
        """
        SELECT identity_id, epoch, process_boot_id, request_id, attempt_index,
               profile_key_hash, actual_input_tokens
        FROM samples
        ORDER BY observed_at_us DESC
        LIMIT 1
        """
    ).fetchone()
    connection.execute(
        """
        INSERT INTO evaluations(
            identity_id, sample_epoch, process_boot_id, request_id,
            attempt_index, method, candidate_variant, prediction_epoch,
            profile_key_hash, ordinal, predicted_tokens, actual_tokens,
            absolute_error, signed_relative_error, absolute_percentage_error
        ) VALUES (?, ?, ?, ?, ?, 'history-exact', 'median', 0, ?, 1, 10.0, ?, 2.0, ?, ?)
        """,
        (*row[:5], row[5], row[6], -1 / 6, 1 / 6),
    )
    connection.commit()
    connection.close()
    with pytest.raises(LearningStoreStartupError) as extra_error:
        await TokenLearningStore(extra).start()
    assert extra_error.value.reason is LearningStoreStartupReason.INVALID_STATE


@pytest.mark.asyncio
async def test_private_state_all_epochs_and_public_snapshot_active_epoch_only(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    event_times = iter((1_001, 1_002, 1_003))
    store = TokenLearningStore(path, _clock=lambda: next(event_times))
    await store.start()
    first = _sample(0)
    drifting = _sample(1)
    other = _sample(2, identity=_identity(actual_provider="provider-b"))
    first_result = await store.apply_sample(first, _transition_for(first))
    drift_result = await store.apply_sample(drifting, _transition_for(drifting, drift=True))
    other_result = await store.apply_sample(other, _transition_for(other))

    private = store._validated_state  # pyright: ignore[reportPrivateUsage]
    public = await store.snapshot_for_prediction(first.identity)

    assert isinstance(private, ValidatedPersistentState)
    assert private.global_revision == 3
    assert tuple(
        (state.identity_id, state.identity, state.revision)
        for state in private.identities
    ) == (
        (1, replace(first.identity, learning_epoch=1), 2),
        (2, other.identity, 1),
    )
    assert tuple(
        (epoch.identity_id, epoch.epoch, epoch.created_order)
        for epoch in private.epochs
    ) == ((1, 0, 0), (1, 1, 2), (2, 0, 2))
    assert tuple(
        (
            sample.sample_id,
            sample.identity_id,
            sample.epoch,
            sample.last_used_order,
            sample.sample,
        )
        for sample in private.samples
    ) == (
        (1, 1, 0, 1, replace(first, committed_order=1)),
        (2, 1, 1, 2, replace(drifting, identity=replace(first.identity, learning_epoch=1), committed_order=2)),
        (3, 2, 0, 3, replace(other, committed_order=3)),
    )
    assert tuple(
        (
            record.identity_id,
            record.sample_epoch,
            record.prediction_epoch,
            record.record.sample_key,
            record.record.selected.history_revision,
        )
        for record in private.prediction_records
    ) == (
        (1, 0, 0, first.sample_key, 0),
        (1, 1, 0, drifting.sample_key, 1),
        (2, 0, 0, other.sample_key, 0),
    )
    assert tuple(
        (
            event.event_id,
            event.identity_id,
            event.learning_epoch,
            event.sample_key,
            event.bucket_key,
            event.observation,
            event.created_at_us,
        )
        for event in private.events
    ) == (
        (
            1,
            1,
            0,
            first.sample_key,
            _expected_identity_bucket(first.identity),
            first_result.observation,
            1_001,
        ),
        (
            2,
            1,
            1,
            drifting.sample_key,
            _expected_identity_bucket(replace(first.identity, learning_epoch=1)),
            drift_result.observation,
            1_002,
        ),
        (
            3,
            2,
            0,
            other.sample_key,
            _expected_identity_bucket(other.identity),
            other_result.observation,
            1_003,
        ),
    )
    assert len(private.exact_anchors) == 3
    assert len(private.prefix_anchors) == 3
    assert len(private.evaluations) == 3
    assert len(private.reconstructed_evaluations) == 3
    assert public == drift_result.snapshot
    assert public.identity.actual_provider == "provider-a"
    assert public.active_epoch == 1
    assert {sample.sample_key for sample in public.samples} == {drifting.sample_key}
    assert public.prediction_records == ()
    assert public.evaluations == ()
    assert all(sample.identity.actual_provider == "provider-a" for sample in public.samples)
    await store.close()


@pytest.mark.asyncio
async def test_composite_relations_reject_cross_identity_epoch_and_partial_event_links(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning.sqlite3"
    first = _sample(0)
    second = _sample(1, identity=_identity(actual_provider="provider-b"))
    store = TokenLearningStore(path)
    await store.start()
    await store.apply_sample(first, _transition_for(first))
    await store.apply_sample(second, _transition_for(second))
    await store.close()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    first_id = connection.execute(
        "SELECT identity_id FROM identity_state WHERE actual_provider = 'provider-a'"
    ).fetchone()[0]
    second_id = connection.execute(
        "SELECT identity_id FROM identity_state WHERE actual_provider = 'provider-b'"
    ).fetchone()[0]
    profile_hash = connection.execute(
        "SELECT profile_key_hash FROM samples WHERE identity_id = ?",
        (first_id,),
    ).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO prediction_records VALUES (?, 0, ?, ?, ?, 0, ?, 'cold-start', 'deterministic', 0, '[]', '[]')
            """,
            (second_id, *first.sample_key, profile_hash),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO evaluations VALUES (?, 0, ?, ?, ?, 'cold-start', 'deterministic', 0, ?, 0, 1.0, 1, 0.0, 0.0, 0.0)
            """,
            (second_id, *first.sample_key, profile_hash),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO exact_anchors VALUES (?, 0, ?, ?, ?, ?, 1)",
            (second_id, *first.sample_key, first.features.full_fingerprint),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO prefix_anchors VALUES (?, 0, ?, ?, ?, ?, 1, ?, 1)",
            (
                second_id,
                *first.sample_key,
                first.features.context_fingerprint,
                first.features.prefix_fingerprints[-1].digest,
            ),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO learning_events(
                identity_id, learning_epoch, sample_process_boot_id,
                bucket_key, process_boot_id, request_id, attempt_index,
                outcome, reason_code, metadata_json, evaluations_json, created_at_us
            ) VALUES (?, 0, ?, 'bucket', 'boot', 'partial', 0, 'rejected', 'sample-ineligible', '{}', '[]', 1)
            """,
            (first_id, first.sample_key[0]),
        )
    connection.close()


@pytest.mark.asyncio
async def test_closed_reason_variants_round_trip_and_free_text_cannot_enter_db(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    store = TokenLearningStore(path)
    await store.start()
    unresolved = UnresolvedLearningIdentity("provider-u", "responses", 1)
    reasons = (
        LearningReasonCode.SAMPLE_INELIGIBLE,
        LearningReasonCode.MISSING_USAGE,
        LearningReasonCode.INCONSISTENT_USAGE,
        LearningReasonCode.QUEUE_FULL,
        LearningReasonCode.ANALYSIS_FAILED,
        LearningReasonCode.OPERATION_CANCELLED,
        LearningReasonCode.STORE_UNAVAILABLE,
        LearningReasonCode.MIGRATION_FAILED,
        LearningReasonCode.COMMIT_FAILED,
        LearningReasonCode.PRUNED,
    )
    for index, reason in enumerate(reasons):
        await store.record_event(_event(index, reason), unresolved)

    assert set(
        value[0] for value in await _rows(path, "SELECT reason_code FROM learning_events")
    ) == {reason.value for reason in reasons}
    identity = _identity(actual_provider="drift-provider")
    drifts = (
        DriftObservation(
            identity,
            "profile",
            0,
            1,
            48,
            DriftReasonCode.PROFILE_ERROR_REGRESSION,
            ProfileErrorRegressionMetadata(32, 16),
        ),
        DriftObservation(
            identity,
            "exact",
            0,
            1,
            3,
            DriftReasonCode.EXACT_COUNT_MISMATCH,
            ExactCountMismatchMetadata(3),
        ),
        DriftObservation(
            identity,
            "exact",
            0,
            1,
            1,
            DriftReasonCode.IDENTITY_VERSION_CHANGE,
            IdentityVersionChangeMetadata(1, 2),
        ),
    )
    for index, drift in enumerate(drifts, start=100):
        observation = TokenLearningObservation(
            ("boot", f"drift-{index}", 0),
            "failed",
            LearningReasonCode.ANALYSIS_FAILED,
            AnalysisFailedMetadata(AnalysisFailureStage.PERSISTENCE),
            PrefixCheckpointNotAttempted(
                PrefixCheckpointNotAttemptedReason.FAILURE_BEFORE_POLICY
            ),
            drift=drift,
        )
        await store.record_event(observation, identity)
    assert set(
        row[0]
        for row in await _rows(
            path,
            "SELECT drift_reason_code FROM learning_events WHERE drift_reason_code IS NOT NULL",
        )
    ) == {reason.value for reason in DriftReasonCode}
    before_count = await _scalar(path, "SELECT count(*) FROM learning_events")
    marker = "raw prompt must not persist"
    with pytest.raises(TypeError):
        cast(Any, TokenLearningObservation)(
            sample_key=("boot", "raw", 0),
            outcome="failed",
            detail=marker,
        )
    with pytest.raises(TypeError):
        cast(Any, AnalysisFailedMetadata)(stage=marker, detail=marker)
    with pytest.raises(ValueError, match="closed enum"):
        AnalysisFailedMetadata(cast(Any, marker))
    with pytest.raises(ValueError, match="closed enum"):
        OperationCancelledMetadata(cast(Any, marker))
    with pytest.raises(ValueError, match="closed enum"):
        TokenLearningObservation(
            ("boot", "bad-code", 0),
            "failed",
            cast(Any, marker),
            CommitFailedMetadata(),
            NoPrefixCheckpointChange(),
        )
    assert await _scalar(path, "SELECT count(*) FROM learning_events") == before_count
    await store.close()
    restarted = TokenLearningStore(path)
    await restarted.start()
    assert len(restarted._validated_state.events) == before_count  # pyright: ignore[reportPrivateUsage]
    await restarted.close()
    assert marker.encode() not in path.read_bytes()


@pytest.mark.asyncio
async def test_all_sample_evaluation_event_bounds_cascade_and_empty_metadata(tmp_path: Path) -> None:
    path = tmp_path / "bounds.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=3,
        samples_global=4,
        actuals_per_fingerprint=2,
        evaluations_per_window=2,
        events_per_identity=2,
        events_global=3,
    )
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    repeated = [_sample(index, fingerprint="same") for index in range(3)]
    for sample in repeated:
        await store.apply_sample(sample, _transition_for(sample))
    snapshot = await store.snapshot_for_prediction(repeated[0].identity)
    assert len(snapshot.samples) == 2
    assert len(snapshot.exact_anchors[0].actual_tokens) == 2
    assert len(snapshot.evaluations) == 2
    assert await _rows(
        path,
        "SELECT (SELECT count(*) FROM samples), (SELECT count(*) FROM prediction_records), (SELECT count(*) FROM evaluations), (SELECT count(*) FROM exact_anchors), (SELECT count(*) FROM prefix_anchors), (SELECT count(*) FROM learning_events)",
    ) == ((2, 2, 2, 2, 2, 2),)

    for index in range(3, 6):
        sample = _sample(index)
        await store.apply_sample(sample, _transition_for(sample))
    assert await _scalar(path, "SELECT count(*) FROM samples WHERE identity_id = 1") == 3
    second_identity = _identity(actual_provider="provider-b")
    for index in range(6, 9):
        sample = _sample(index, identity=second_identity)
        await store.apply_sample(sample, _transition_for(sample))
    assert await _scalar(path, "SELECT count(*) FROM samples") == 4
    for table in (
        "prediction_records",
        "evaluations",
        "exact_anchors",
        "prefix_anchors",
    ):
        assert await _scalar(
            path,
            f"SELECT count(*) FROM {table} WHERE (identity_id, sample_epoch, process_boot_id, request_id, attempt_index) NOT IN (SELECT identity_id, epoch, process_boot_id, request_id, attempt_index FROM samples)"
            if table in ("prediction_records", "evaluations")
            else f"SELECT count(*) FROM {table} WHERE (identity_id, epoch, process_boot_id, request_id, attempt_index) NOT IN (SELECT identity_id, epoch, process_boot_id, request_id, attempt_index FROM samples)",
        ) == 0

    unresolved = UnresolvedLearningIdentity("provider-u", "responses", 1)
    for index in range(5):
        await store.record_event(_event(200 + index), unresolved)
    assert await _scalar(
        path,
        "SELECT count(*) FROM learning_events WHERE unresolved_provider = 'provider-u'",
    ) <= 2
    assert await _scalar(path, "SELECT count(*) FROM learning_events") <= 3
    transient = _identity(actual_provider="transient")
    await store.record_event(_event(300), transient)
    for index in range(4):
        await store.record_event(
            _event(400 + index),
            UnresolvedLearningIdentity(f"other-{index}", "responses", 1),
        )
    assert await _scalar(path, "SELECT count(*) FROM learning_events") == 3
    assert await _scalar(
        path,
        "SELECT count(*) FROM identity_state WHERE actual_provider = 'transient'",
    ) == 0
    await store.close()


@pytest.mark.asyncio
async def test_rejection_event_revision_precedes_event_cap_delete(tmp_path: Path) -> None:
    path = tmp_path / "event-revision.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=5,
        samples_global=10,
        actuals_per_fingerprint=5,
        evaluations_per_window=20,
        events_per_identity=1,
        events_global=10,
    )
    identity = _identity(actual_provider="event-provider")
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    await store.record_event(_event(0), identity)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE event_delete_audit(identity_revision INTEGER, global_revision INTEGER);
        CREATE TRIGGER audit_event_delete BEFORE DELETE ON learning_events BEGIN
            INSERT INTO event_delete_audit
            SELECT (SELECT revision FROM identity_state WHERE identity_id = OLD.identity_id),
                   (SELECT global_revision FROM schema_meta);
        END;
        """
    )
    connection.commit()
    connection.close()

    await store.record_event(_event(1), identity)

    assert await _rows(path, "SELECT * FROM event_delete_audit") == ((2, 2),)
    assert await _rows(
        path,
        "SELECT revision, reason_code FROM learning_events",
    ) == ((2, "sample-ineligible"),)
    await store.close()


@pytest.mark.asyncio
async def test_anchor_use_records_confirmed_sources_and_pruned_is_noop(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    store = TokenLearningStore(path)
    await store.start()
    first = _sample(0, fingerprint="same")
    second = _sample(1, fingerprint="same")
    await store.apply_sample(first, _transition_for(first))
    await store.apply_sample(second, _transition_for(second))
    before = await _rows(
        path,
        "SELECT process_boot_id, request_id, attempt_index, last_used_order FROM samples ORDER BY request_id",
    )
    revision_before = await _scalar(path, "SELECT revision FROM identity_state")
    intent = AnchorUseIntent(
        AnchorKind.EXACT,
        first.identity,
        0,
        first.features.full_fingerprint,
        (first.sample_key, second.sample_key),
    )

    outcome = await store.record_anchor_use(intent)

    assert outcome is AnchorUseOutcome.RECORDED
    after = await _rows(
        path,
        "SELECT process_boot_id, request_id, attempt_index, last_used_order FROM samples ORDER BY request_id",
    )
    assert {row[3] for row in after} == {3}
    assert before != after
    assert await _scalar(path, "SELECT revision FROM identity_state") == revision_before + 1
    assert await _scalar(path, "SELECT global_revision FROM schema_meta") == 3

    prefix_intent = AnchorUseIntent(
        AnchorKind.PREFIX,
        second.identity,
        0,
        second.features.prefix_fingerprints[-1].digest,
        (second.sample_key,),
    )
    assert await store.record_anchor_use(prefix_intent) is AnchorUseOutcome.RECORDED
    prefix_after = await _rows(
        path,
        "SELECT request_id, last_used_order FROM samples ORDER BY request_id",
    )
    assert prefix_after == (
        (first.sample_key[1], 3),
        (second.sample_key[1], 4),
    )

    missing = replace(intent, source_sample_keys=(("boot", "missing", 0),))
    revision_before_missing = await _scalar(path, "SELECT revision FROM identity_state")
    assert await store.record_anchor_use(missing) is AnchorUseOutcome.PRUNED
    assert await _scalar(path, "SELECT revision FROM identity_state") == revision_before_missing
    await store.close()


@pytest.mark.asyncio
async def test_pruning_orders_confirmed_use_then_prefix_coverage_timestamp_and_binary_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=5,
        samples_global=20,
        actuals_per_fingerprint=5,
        evaluations_per_window=20,
        events_per_identity=20,
        events_global=20,
    )
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    used = _sample(0, observed_at_us=10, prefix_count=1)
    coverage = _sample(1, observed_at_us=10, prefix_count=3)
    old = _sample(2, observed_at_us=5, prefix_count=1)
    binary_first = _sample(
        3,
        sample_key=("A", "same", 2),
        observed_at_us=10,
        prefix_count=1,
    )
    binary_later = _sample(
        4,
        sample_key=("B", "same", 1),
        observed_at_us=10,
        prefix_count=1,
    )
    for sample in (used, coverage, old, binary_first, binary_later):
        await store.apply_sample(sample, _transition_for(sample))
    connection = sqlite3.connect(path)
    connection.execute("UPDATE samples SET last_used_order = 10")
    connection.commit()
    connection.close()
    store._limits = replace(limits, samples_per_identity=4)  # pyright: ignore[reportPrivateUsage]

    await store.prune()

    retained = {
        (row[0], row[1], row[2])
        for row in await _rows(
            path,
            "SELECT process_boot_id, request_id, attempt_index FROM samples",
        )
    }
    assert old.sample_key not in retained
    assert coverage.sample_key in retained
    assert binary_first.sample_key in retained
    assert binary_later.sample_key in retained
    await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dimension", "first_key", "second_key", "first_time", "second_time", "first_prefix", "second_prefix"),
    [
        ("coverage", ("boot", "first", 0), ("boot", "second", 0), 10, 10, 1, 3),
        ("timestamp", ("boot", "first", 0), ("boot", "second", 0), 5, 10, 1, 1),
        ("boot-binary", ("A", "same", 0), ("B", "same", 0), 10, 10, 1, 1),
        ("request-binary", ("same", "A", 0), ("same", "B", 0), 10, 10, 1, 1),
        ("attempt-numeric", ("same", "same", 2), ("same", "same", 10), 10, 10, 1, 1),
    ],
)
async def test_each_sample_prune_dimension_has_exact_victim(
    tmp_path: Path,
    dimension: str,
    first_key: SampleKey,
    second_key: SampleKey,
    first_time: int,
    second_time: int,
    first_prefix: int,
    second_prefix: int,
) -> None:
    path = tmp_path / f"sample-order-{dimension}.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=2,
        samples_global=10,
        actuals_per_fingerprint=5,
        evaluations_per_window=20,
        events_per_identity=20,
        events_global=20,
    )
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    first = _sample(
        0,
        sample_key=first_key,
        observed_at_us=first_time,
        prefix_count=first_prefix,
    )
    second = _sample(
        1,
        sample_key=second_key,
        observed_at_us=second_time,
        prefix_count=second_prefix,
    )
    await store.apply_sample(first, _transition_for(first))
    await store.apply_sample(second, _transition_for(second))
    connection = sqlite3.connect(path)
    connection.execute("UPDATE samples SET last_used_order = 10")
    connection.commit()
    connection.close()
    store._limits = replace(limits, samples_per_identity=1)  # pyright: ignore[reportPrivateUsage]

    await store.prune()

    assert await _rows(
        path,
        "SELECT process_boot_id, request_id, attempt_index FROM samples",
    ) == (second_key,)
    await store.close()


@pytest.mark.asyncio
async def test_confirmed_anchor_use_precedes_creation_order_for_prune(tmp_path: Path) -> None:
    path = tmp_path / "confirmed-use-order.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=2,
        samples_global=10,
        actuals_per_fingerprint=5,
        evaluations_per_window=20,
        events_per_identity=20,
        events_global=20,
    )
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    first = _sample(0)
    second = _sample(1)
    await store.apply_sample(first, _transition_for(first))
    await store.apply_sample(second, _transition_for(second))
    await store.record_anchor_use(
        AnchorUseIntent(
            AnchorKind.EXACT,
            first.identity,
            0,
            first.features.full_fingerprint,
            (first.sample_key,),
        )
    )
    store._limits = replace(limits, samples_per_identity=1)  # pyright: ignore[reportPrivateUsage]

    await store.prune()

    assert await _rows(
        path,
        "SELECT process_boot_id, request_id, attempt_index FROM samples",
    ) == (first.sample_key,)
    await store.close()


@pytest.mark.asyncio
async def test_inactive_epoch_prunes_before_active_and_global_identity_order_is_stable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=2,
        samples_global=3,
        actuals_per_fingerprint=5,
        evaluations_per_window=20,
        events_per_identity=20,
        events_global=20,
    )
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    old = _sample(0)
    drift = _sample(1)
    active = _sample(2)
    other_a = _sample(3, identity=_identity(actual_provider="a-provider"))
    other_b = _sample(4, identity=_identity(actual_provider="b-provider"))
    await store.apply_sample(old, _transition_for(old))
    await store.apply_sample(drift, _transition_for(drift, drift=True))
    await store.apply_sample(active, _transition_for(active))
    assert await _scalar(path, "SELECT count(*) FROM samples WHERE epoch = 0 AND identity_id = 1") == 0
    await store.apply_sample(other_a, _transition_for(other_a))
    await store.apply_sample(other_b, _transition_for(other_b))

    assert await _scalar(path, "SELECT count(*) FROM samples") == 3
    providers = {
        row[0]
        for row in await _rows(
            path,
            "SELECT DISTINCT actual_provider FROM identity_state JOIN samples USING(identity_id)",
        )
    }
    assert "provider-a" in providers
    assert providers <= {"provider-a", "a-provider", "b-provider"}
    await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("dimension", ("confirmed-use", "coverage", "oldest", "identity-key"))
async def test_each_global_identity_prune_dimension_has_exact_victim(
    tmp_path: Path,
    dimension: str,
) -> None:
    path = tmp_path / f"identity-order-{dimension}.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=5,
        samples_global=2,
        actuals_per_fingerprint=5,
        evaluations_per_window=20,
        events_per_identity=20,
        events_global=20,
    )
    first_identity = _identity(actual_provider="a-provider")
    second_identity = _identity(actual_provider="b-provider")
    first = _sample(
        0,
        identity=first_identity,
        observed_at_us=5 if dimension == "oldest" else 10,
        prefix_count=1,
    )
    second = _sample(
        1,
        identity=second_identity,
        observed_at_us=10,
        prefix_count=3 if dimension == "coverage" else 1,
    )
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    await store.apply_sample(first, _transition_for(first))
    await store.apply_sample(second, _transition_for(second))
    if dimension == "confirmed-use":
        await store.record_anchor_use(
            AnchorUseIntent(
                AnchorKind.EXACT,
                first_identity,
                0,
                first.features.full_fingerprint,
                (first.sample_key,),
            )
        )
    else:
        connection = sqlite3.connect(path)
        connection.execute("UPDATE samples SET last_used_order = 10")
        connection.commit()
        connection.close()
    store._limits = replace(limits, samples_global=1)  # pyright: ignore[reportPrivateUsage]

    await store.prune()

    retained_provider = await _scalar(
        path,
        "SELECT actual_provider FROM identity_state JOIN samples USING(identity_id)",
    )
    if dimension == "confirmed-use":
        assert retained_provider == "a-provider"
    else:
        assert retained_provider == "b-provider"
    await store.close()


@pytest.mark.asyncio
async def test_global_prune_prefers_identity_without_active_evidence(tmp_path: Path) -> None:
    path = tmp_path / "identity-no-active.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=5,
        samples_global=2,
        actuals_per_fingerprint=5,
        evaluations_per_window=20,
        events_per_identity=20,
        events_global=20,
    )
    inactive_identity = _identity(actual_provider="z-inactive")
    active_identity = _identity(actual_provider="a-active")
    inactive = _sample(0, identity=inactive_identity)
    active = _sample(1, identity=active_identity)
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    await store.apply_sample(inactive, _transition_for(inactive))
    await store.apply_sample(active, _transition_for(active))
    connection = sqlite3.connect(path)
    identity_id = connection.execute(
        "SELECT identity_id FROM identity_state WHERE actual_provider = 'z-inactive'"
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO epoch_state(identity_id, epoch, created_order) VALUES (?, 1, 2)",
        (identity_id,),
    )
    connection.execute(
        "UPDATE identity_state SET active_epoch = 1 WHERE identity_id = ?",
        (identity_id,),
    )
    connection.commit()
    connection.close()
    store._limits = replace(limits, samples_global=1)  # pyright: ignore[reportPrivateUsage]

    await store.prune()

    assert await _scalar(
        path,
        "SELECT actual_provider FROM identity_state JOIN samples USING(identity_id)",
    ) == "a-active"
    await store.close()


@pytest.mark.asyncio
async def test_revision_is_incremented_before_cascade_delete_and_event_is_post_revision(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=1,
        samples_global=1,
        actuals_per_fingerprint=5,
        evaluations_per_window=20,
        events_per_identity=20,
        events_global=20,
    )
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    first = _sample(0, identity=_identity(actual_provider="a-provider"))
    second = _sample(1, identity=_identity(actual_provider="b-provider"))
    await store.apply_sample(first, _transition_for(first))
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE delete_audit(
            table_name TEXT,
            identity_id INTEGER,
            identity_revision INTEGER,
            global_revision INTEGER,
            event_count INTEGER
        );
        CREATE TRIGGER audit_sample_delete BEFORE DELETE ON samples BEGIN
            INSERT INTO delete_audit
            SELECT 'samples', OLD.identity_id,
                   (SELECT revision FROM identity_state WHERE identity_id = OLD.identity_id),
                   (SELECT global_revision FROM schema_meta),
                   (SELECT count(*) FROM learning_events);
        END;
        CREATE TRIGGER audit_identity_delete BEFORE DELETE ON identity_state BEGIN
            INSERT INTO delete_audit
            SELECT 'identity_state', OLD.identity_id, OLD.revision,
                   (SELECT global_revision FROM schema_meta),
                   (SELECT count(*) FROM learning_events);
        END;
        """
    )
    connection.commit()
    connection.close()

    await store.apply_sample(second, _transition_for(second))

    audit = await _rows(
        path,
        "SELECT table_name, identity_revision, global_revision, event_count FROM delete_audit ORDER BY rowid",
    )
    assert audit == (("samples", 2, 2, 1), ("identity_state", 2, 2, 0))
    assert await _rows(
        path,
        "SELECT revision, reason_code FROM learning_events ORDER BY event_id",
    ) == ((1, "sample-committed"),)
    assert await _scalar(path, "SELECT global_revision FROM schema_meta") == 2
    await store.close()


@pytest.mark.asyncio
async def test_same_identity_event_is_inserted_after_delete_with_new_revision(tmp_path: Path) -> None:
    path = tmp_path / "same-identity-revision.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=1,
        samples_global=10,
        actuals_per_fingerprint=5,
        evaluations_per_window=20,
        events_per_identity=20,
        events_global=20,
    )
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    first = _sample(0)
    second = _sample(1)
    await store.apply_sample(first, _transition_for(first))
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE same_identity_audit(
            identity_revision INTEGER,
            global_revision INTEGER,
            event_count INTEGER
        );
        CREATE TRIGGER audit_same_identity BEFORE DELETE ON samples BEGIN
            INSERT INTO same_identity_audit
            SELECT (SELECT revision FROM identity_state WHERE identity_id = OLD.identity_id),
                   (SELECT global_revision FROM schema_meta),
                   (SELECT count(*) FROM learning_events);
        END;
        """
    )
    connection.commit()
    connection.close()

    result = await store.apply_sample(second, _transition_for(second))

    assert await _rows(path, "SELECT * FROM same_identity_audit") == ((2, 2, 1),)
    assert result.observation.revision == 2
    assert await _rows(
        path,
        "SELECT revision, reason_code FROM learning_events",
    ) == ((2, "sample-committed"),)
    await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actual_provider", "provider-b"),
        ("resolved_model", "model-b"),
        ("endpoint", "messages"),
        ("wire_format", "anthropic-messages"),
        ("tokenizer", "cl100k_base"),
        ("descriptor_fingerprint", _digest("descriptor-b")),
        ("estimator_generation", 2),
        ("profile_schema_revision", 2),
    ],
)
async def test_each_identity_dimension_isolated(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    path = tmp_path / f"{field}.sqlite3"
    baseline_identity = _identity()
    changed_identity = replace(baseline_identity, **{field: value})
    baseline = _sample(0, identity=baseline_identity)
    changed = _sample(1, identity=changed_identity)
    store = TokenLearningStore(path)
    await store.start()
    await store.apply_sample(baseline, _transition_for(baseline))
    await store.apply_sample(changed, _transition_for(changed))

    assert (await store.snapshot_for_prediction(baseline_identity)).samples == (
        replace(baseline, committed_order=1),
    )
    assert (await store.snapshot_for_prediction(changed_identity)).samples == (
        replace(changed, committed_order=2),
    )
    assert await _scalar(path, "SELECT count(*) FROM identity_state") == 2
    await store.close()


@pytest.mark.asyncio
async def test_busy_writer_keeps_event_loop_and_foreground_snapshot_progressing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning.sqlite3"
    store = TokenLearningStore(path, busy_retry_timeout=2, busy_retry_delay=0.2)
    await store.start()
    sample = _sample(0)
    locker = await aiosqlite.connect(path, isolation_level=None, timeout=0)
    await locker.execute("PRAGMA busy_timeout=0")
    await locker.execute("BEGIN IMMEDIATE")
    done = asyncio.Event()
    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        while not done.is_set():
            ticks += 1
            await asyncio.sleep(0)

    apply_task = asyncio.ensure_future(store.apply_sample(sample, _transition_for(sample)))
    heartbeat_task = asyncio.ensure_future(heartbeat())
    wait_started = time.monotonic()
    await asyncio.sleep(0.05)
    assert time.monotonic() - wait_started < 0.3
    foreground = await asyncio.wait_for(store.snapshot_for_prediction(sample.identity), timeout=0.15)
    assert foreground.revision == 0
    assert not apply_task.done()
    assert ticks > 10
    await locker.rollback()
    await locker.close()
    result = await asyncio.wait_for(apply_task, timeout=2)
    done.set()
    await heartbeat_task
    assert result.snapshot.revision == 1
    await store.close()


@pytest.mark.asyncio
async def test_true_connection_constructor_close_and_worker_provenance(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite3"
    loop_thread = threading.get_ident()
    evidence = _ThreadEvidence([], [], [])
    transition_threads: list[int] = []
    store = TokenLearningStore(
        path,
        _connection_factory=_tracking_factory(evidence),
        _thread_probe=lambda label, thread_id: evidence.workers.append((label, thread_id)),
    )
    sample = _sample(0)

    await store.start()
    await store.snapshot_for_prediction(sample.identity)
    await store.apply_sample(sample, _transition_for(sample, thread_ids=transition_threads))
    await store.close()

    assert len(evidence.constructors) >= 2
    assert len(evidence.closes) == len(evidence.constructors)
    assert all(thread_id != loop_thread for thread_id in evidence.constructors)
    assert all(thread_id != loop_thread for thread_id in evidence.closes)
    assert evidence.workers
    assert all(thread_id != loop_thread for _label, thread_id in evidence.workers)
    assert transition_threads
    assert all(thread_id != loop_thread for thread_id in transition_threads)
    assert not hasattr(store, "raw_connection")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phase", "occurrence"),
    [
        (StoreCancellationPhase.BEGIN, 1),
        *((StoreCancellationPhase.READ, occurrence) for occurrence in range(1, 24)),
        *((StoreCancellationPhase.CURSOR_CLOSE, occurrence) for occurrence in range(1, 13)),
        *((StoreCancellationPhase.INSERT, occurrence) for occurrence in range(1, 11)),
        (StoreCancellationPhase.TRANSITION, 1),
        *((StoreCancellationPhase.UPDATE, occurrence) for occurrence in range(1, 7)),
    ],
)
async def test_precommit_cancellation_matrix_rolls_back_and_preserves_task_semantics(
    tmp_path: Path,
    phase: StoreCancellationPhase,
    occurrence: int,
) -> None:
    path = tmp_path / f"cancel-{phase.value}-{occurrence}.sqlite3"
    plan = _CancelPlan()
    store = TokenLearningStore(path, _action_hook=plan)
    await store.start()
    sample = _sample(0)
    plan.arm((phase, occurrence))
    task = asyncio.ensure_future(store.apply_sample(sample, _transition_for(sample)))

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.phase is phase
    assert caught.value.committed_observation is None
    assert task.cancelled()
    assert plan.fired == [phase]
    assert await _scalar(path, "SELECT count(*) FROM samples") == 0
    assert await _scalar(path, "SELECT global_revision FROM schema_meta") == 0
    await _assert_write_lock_available(path)
    plan.disarm()
    assert (await store.apply_sample(sample, _transition_for(sample))).snapshot.revision == 1
    await store.close()


@pytest.mark.asyncio
async def test_second_cancellation_during_confirmed_rollback_cannot_interrupt_cleanup(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rollback-cancel.sqlite3"
    plan = _CancelPlan()
    store = TokenLearningStore(path, _action_hook=plan)
    await store.start()
    sample = _sample(0)
    plan.arm(
        (StoreCancellationPhase.TRANSITION, 1),
        (StoreCancellationPhase.ROLLBACK, 1),
    )
    task = asyncio.ensure_future(store.apply_sample(sample, _transition_for(sample)))

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.phase is StoreCancellationPhase.TRANSITION
    assert caught.value.committed_observation is None
    assert task.cancelled()
    assert plan.fired == [
        StoreCancellationPhase.TRANSITION,
        StoreCancellationPhase.ROLLBACK,
    ]
    await _assert_write_lock_available(path)
    assert await _scalar(path, "SELECT count(*) FROM samples") == 0
    plan.disarm()
    await store.close()


@pytest.mark.asyncio
async def test_commit_cancellation_reports_durable_observation_and_retry_is_duplicate(
    tmp_path: Path,
) -> None:
    path = tmp_path / "commit-cancel.sqlite3"
    plan = _CancelPlan()
    store = TokenLearningStore(path, _action_hook=plan)
    await store.start()
    sample = _sample(0)
    plan.arm((StoreCancellationPhase.COMMIT, 1))
    task = asyncio.ensure_future(store.apply_sample(sample, _transition_for(sample)))

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.phase is StoreCancellationPhase.COMMIT
    assert caught.value.committed_observation is not None
    assert caught.value.committed_observation.outcome == "committed"
    assert task.cancelled()
    assert await _scalar(path, "SELECT count(*) FROM samples") == 1
    assert await _scalar(path, "SELECT global_revision FROM schema_meta") == 1
    plan.disarm()
    retry = await store.apply_sample(sample, _transition_for(sample))
    assert retry.observation.outcome == "duplicate"
    await store.close()


@pytest.mark.asyncio
async def test_open_cancellation_confirms_connection_close_before_propagating(tmp_path: Path) -> None:
    path = tmp_path / "open-cancel.sqlite3"
    plan = _CancelPlan(((StoreCancellationPhase.OPEN, 1),), True)
    evidence = _ThreadEvidence([], [], [])
    store = TokenLearningStore(
        path,
        _action_hook=plan,
        _connection_factory=_tracking_factory(evidence),
    )
    task = asyncio.ensure_future(store.start())

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.phase is StoreCancellationPhase.OPEN
    assert task.cancelled()
    assert evidence.constructors
    assert evidence.closes == evidence.constructors
    replacement = TokenLearningStore(path)
    await replacement.start()
    await replacement.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase",
    [
        StoreCancellationPhase.CHECKPOINT,
        StoreCancellationPhase.CONNECTION_CLOSE,
    ],
)
async def test_shutdown_cancellation_confirms_all_connections_closed(
    tmp_path: Path,
    phase: StoreCancellationPhase,
) -> None:
    path = tmp_path / f"close-{phase.value}.sqlite3"
    plan = _CancelPlan()
    evidence = _ThreadEvidence([], [], [])
    store = TokenLearningStore(
        path,
        _action_hook=plan,
        _connection_factory=_tracking_factory(evidence),
    )
    await store.start()
    plan.arm((phase, 1))
    task = asyncio.ensure_future(store.close())

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.phase is phase
    assert task.cancelled()
    assert len(evidence.closes) == len(evidence.constructors)
    with pytest.raises(LearningStoreStateError):
        await store.snapshot_for_prediction(_identity())
    await _assert_write_lock_available(path)


@pytest.mark.asyncio
async def test_close_physically_waits_for_idle_writer_lock_owner(tmp_path: Path) -> None:
    path = tmp_path / "close-idle-writer-owner.sqlite3"
    store = TokenLearningStore(path)
    await store.start()
    owner_ready = asyncio.Event()
    owner_release = asyncio.Event()

    async def hold_writer_owner() -> None:
        await store._acquire_operation_lock(  # pyright: ignore[reportPrivateUsage]
            lifecycle_action_id="lock.apply.lifecycle",
            resource_lock=store._writer_lock,  # pyright: ignore[reportPrivateUsage]
            resource_action_id="lock.apply.writer",
        )
        owner_ready.set()
        try:
            await owner_release.wait()
        finally:
            store._writer_lock.release()  # pyright: ignore[reportPrivateUsage]

    owner_task = asyncio.ensure_future(hold_writer_owner())
    await asyncio.wait_for(owner_ready.wait(), timeout=2)
    close_task = asyncio.ensure_future(store.close())
    await asyncio.sleep(0.03)
    assert not close_task.done()
    owner_release.set()

    await owner_task
    await close_task
    with pytest.raises(LearningStoreStateError):
        await store.snapshot_for_prediction(_identity())


@pytest.mark.asyncio
async def test_cancelled_close_waits_for_active_writer_owner_before_physical_close(
    tmp_path: Path,
) -> None:
    path = tmp_path / "close-writer-wait.sqlite3"
    evidence = _ThreadEvidence([], [], [])
    store = TokenLearningStore(
        path,
        _connection_factory=_tracking_factory(evidence),
    )
    await store.start()
    sample = _sample(0)
    entered = threading.Event()
    release = threading.Event()
    apply_task = asyncio.ensure_future(
        store.apply_sample(
            sample,
            _transition_for(sample, entered=entered, release=release),
        )
    )
    await _wait_thread_event(entered)
    close_task = asyncio.ensure_future(store.close())
    await asyncio.sleep(0.02)
    close_task.cancel()
    await asyncio.sleep(0.02)
    assert not close_task.done()
    assert not apply_task.done()
    release.set()

    result = await apply_task
    with pytest.raises(StoreOperationCancelled) as caught:
        await close_task

    assert result.observation.outcome == "committed"
    assert caught.value.phase is StoreCancellationPhase.CLOSE_LOCK_WAIT
    assert close_task.cancelled()
    assert len(evidence.closes) == len(evidence.constructors)
    with pytest.raises(LearningStoreStateError):
        await store.apply_sample(_sample(1), _transition_for(_sample(1)))


@pytest.mark.asyncio
async def test_cancelled_close_waits_for_active_reader_owner_before_physical_close(
    tmp_path: Path,
) -> None:
    path = tmp_path / "close-reader-wait.sqlite3"
    writer = TokenLearningStore(path)
    await writer.start()
    first = _sample(0)
    second = _sample(1)
    await writer.apply_sample(first, _transition_for(first))
    entered = asyncio.Event()
    release = asyncio.Event()
    hook_enabled = False

    async def reader_hook(stage: str) -> None:
        assert stage == "after-identities"
        if hook_enabled:
            entered.set()
            await release.wait()

    evidence = _ThreadEvidence([], [], [])
    reader = TokenLearningStore(
        path,
        _reader_step_hook=reader_hook,
        _connection_factory=_tracking_factory(evidence),
    )
    await reader.start()
    hook_enabled = True
    await writer.apply_sample(second, _transition_for(second))
    refresh_task = asyncio.ensure_future(reader.snapshot_for_prediction(first.identity))
    await asyncio.wait_for(entered.wait(), timeout=2)
    close_task = asyncio.ensure_future(reader.close())
    await asyncio.sleep(0.02)
    close_task.cancel()
    await asyncio.sleep(0.02)
    assert not close_task.done()
    assert not refresh_task.done()
    release.set()

    refreshed = await refresh_task
    with pytest.raises(StoreOperationCancelled) as caught:
        await close_task

    assert refreshed.revision == 2
    assert caught.value.phase is StoreCancellationPhase.CLOSE_LOCK_WAIT
    assert close_task.cancelled()
    assert len(evidence.closes) == len(evidence.constructors)
    await writer.close()


@pytest.mark.asyncio
async def test_cancelled_close_waits_for_lifecycle_owner_then_active_writer(
    tmp_path: Path,
) -> None:
    path = tmp_path / "close-lifecycle-wait.sqlite3"
    writer_waiting = asyncio.Event()

    async def action_hook(
        action_id: str,
        _phase: StoreCancellationPhase,
    ) -> None:
        if action_id == "lock.apply.writer":
            writer_waiting.set()

    store = TokenLearningStore(path, _action_hook=action_hook)
    await store.start()
    await store._writer_lock.acquire()  # pyright: ignore[reportPrivateUsage]
    sample = _sample(0)
    apply_task = asyncio.ensure_future(store.apply_sample(sample, _transition_for(sample)))
    await asyncio.wait_for(writer_waiting.wait(), timeout=2)
    close_task = asyncio.ensure_future(store.close())
    await asyncio.sleep(0.02)
    close_task.cancel()
    await asyncio.sleep(0.02)
    assert not close_task.done()
    store._writer_lock.release()  # pyright: ignore[reportPrivateUsage]

    result = await apply_task
    with pytest.raises(StoreOperationCancelled) as caught:
        await close_task

    assert result.observation.outcome == "committed"
    assert caught.value.phase is StoreCancellationPhase.CLOSE_LOCK_WAIT
    assert close_task.cancelled()


@pytest.mark.asyncio
async def test_concurrent_close_callers_share_one_physical_completion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "concurrent-close.sqlite3"
    evidence = _ThreadEvidence([], [], [])
    store = TokenLearningStore(
        path,
        _connection_factory=_tracking_factory(evidence),
    )
    await store.start()
    entered = threading.Event()
    release = threading.Event()
    sample = _sample(0)
    apply_task = asyncio.ensure_future(
        store.apply_sample(
            sample,
            _transition_for(sample, entered=entered, release=release),
        )
    )
    await _wait_thread_event(entered)
    owner_awaitable = store.close()
    waiter_awaitable = store.close()
    owner_task = asyncio.ensure_future(owner_awaitable)
    waiter_task = asyncio.ensure_future(waiter_awaitable)
    await asyncio.sleep(0.02)
    waiter_task.cancel()
    await asyncio.sleep(0.02)
    assert not waiter_task.done()
    release.set()

    await apply_task
    await owner_task
    with pytest.raises(StoreOperationCancelled) as caught:
        await waiter_task

    assert caught.value.phase is StoreCancellationPhase.CLOSE_WAIT
    assert waiter_task.cancelled()
    assert len(evidence.closes) == len(evidence.constructors)
    await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("read_occurrence", range(1, 11))
async def test_reader_cancellation_keeps_previous_validated_snapshot(
    tmp_path: Path,
    read_occurrence: int,
) -> None:
    path = tmp_path / f"reader-cancel-{read_occurrence}.sqlite3"
    writer = TokenLearningStore(path)
    await writer.start()
    first = _sample(0)
    second = _sample(1)
    await writer.apply_sample(first, _transition_for(first))
    plan = _CancelPlan()
    reader = TokenLearningStore(path, _action_hook=plan)
    await reader.start()
    baseline = await reader.snapshot_for_prediction(first.identity)
    await writer.apply_sample(second, _transition_for(second))
    plan.arm((StoreCancellationPhase.READ, read_occurrence))
    task = asyncio.ensure_future(reader.snapshot_for_prediction(first.identity))

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.committed_observation is None
    assert task.cancelled()
    assert reader._validated_state.global_revision == baseline.revision  # pyright: ignore[reportPrivateUsage]
    plan.disarm()
    assert (await reader.snapshot_for_prediction(first.identity)).revision == 2
    await reader.close()
    await writer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase",
    [StoreCancellationPhase.BEGIN, StoreCancellationPhase.COMMIT],
)
async def test_reader_begin_and_commit_cancellation_are_determinate(
    tmp_path: Path,
    phase: StoreCancellationPhase,
) -> None:
    path = tmp_path / f"reader-{phase.value}.sqlite3"
    writer = TokenLearningStore(path)
    await writer.start()
    first = _sample(0)
    second = _sample(1)
    await writer.apply_sample(first, _transition_for(first))
    plan = _CancelPlan()
    reader = TokenLearningStore(path, _action_hook=plan)
    await reader.start()
    baseline = await reader.snapshot_for_prediction(first.identity)
    await writer.apply_sample(second, _transition_for(second))
    plan.arm((phase, 1))
    task = asyncio.ensure_future(reader.snapshot_for_prediction(first.identity))

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.phase is phase
    assert caught.value.committed_observation is None
    assert task.cancelled()
    assert reader._validated_state.global_revision == baseline.revision  # pyright: ignore[reportPrivateUsage]
    await _assert_write_lock_available(path)
    plan.disarm()
    assert (await reader.snapshot_for_prediction(first.identity)).revision == 2
    await reader.close()
    await writer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase",
    (
        StoreCancellationPhase.PRAGMA,
        StoreCancellationPhase.CURSOR_CLOSE,
        StoreCancellationPhase.BEGIN,
        StoreCancellationPhase.INSERT,
        StoreCancellationPhase.COMMIT,
    ),
)
async def test_fresh_migration_cancellation_is_determinate_and_recoverable(
    tmp_path: Path,
    phase: StoreCancellationPhase,
) -> None:
    path = tmp_path / f"migration-{phase.value}.sqlite3"
    plan = _CancelPlan(((phase, 1),), True)
    evidence = _ThreadEvidence([], [], [])
    task = asyncio.ensure_future(
        TokenLearningStore(
            path,
            _action_hook=plan,
            _connection_factory=_tracking_factory(evidence),
        ).start()
    )

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.phase is phase
    assert caught.value.committed_observation is None
    assert task.cancelled()
    assert len(evidence.closes) == len(evidence.constructors)
    replacement = TokenLearningStore(path)
    await replacement.start()
    assert await _rows(path, "SELECT version, manifest_digest FROM schema_meta") == (
        (1, EXPECTED_MANIFEST_DIGEST),
    )
    await replacement.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("open_occurrence", (1, 2))
async def test_missing_path_each_connection_open_cancellation_is_closed(
    tmp_path: Path,
    open_occurrence: int,
) -> None:
    path = tmp_path / f"missing-open-{open_occurrence}.sqlite3"
    plan = _CancelPlan(((StoreCancellationPhase.OPEN, open_occurrence),), True)
    evidence = _ThreadEvidence([], [], [])
    task = asyncio.ensure_future(
        TokenLearningStore(
            path,
            _action_hook=plan,
            _connection_factory=_tracking_factory(evidence),
        ).start()
    )

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.phase is StoreCancellationPhase.OPEN
    assert task.cancelled()
    assert len(evidence.closes) == len(evidence.constructors)
    replacement = TokenLearningStore(path)
    await replacement.start()
    await replacement.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("open_occurrence", (1, 2, 3))
async def test_existing_path_inspector_writer_and_reader_open_cancellation_is_closed(
    tmp_path: Path,
    open_occurrence: int,
) -> None:
    path = tmp_path / f"existing-open-{open_occurrence}.sqlite3"
    seed = TokenLearningStore(path)
    await seed.start()
    await seed.close()
    plan = _CancelPlan(((StoreCancellationPhase.OPEN, open_occurrence),), True)
    evidence = _ThreadEvidence([], [], [])
    task = asyncio.ensure_future(
        TokenLearningStore(
            path,
            _action_hook=plan,
            _connection_factory=_tracking_factory(evidence),
        ).start()
    )

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.phase is StoreCancellationPhase.OPEN
    assert task.cancelled()
    assert len(evidence.closes) == len(evidence.constructors)
    replacement = TokenLearningStore(path)
    await replacement.start()
    await replacement.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "phase"),
    [
        ("event", StoreCancellationPhase.INSERT),
        ("event", StoreCancellationPhase.COMMIT),
        ("anchor", StoreCancellationPhase.UPDATE),
        ("anchor", StoreCancellationPhase.COMMIT),
        ("prune", StoreCancellationPhase.UPDATE),
        ("prune", StoreCancellationPhase.COMMIT),
    ],
)
async def test_event_anchor_and_prune_share_confirmed_cancellation_protocol(
    tmp_path: Path,
    operation: str,
    phase: StoreCancellationPhase,
) -> None:
    path = tmp_path / f"{operation}-{phase.value}.sqlite3"
    limits = _StoreLimits(
        samples_per_identity=2,
        samples_global=20,
        actuals_per_fingerprint=5,
        evaluations_per_window=20,
        events_per_identity=20,
        events_global=20,
    )
    plan = _CancelPlan()
    store = TokenLearningStore(path, _limits=limits, _action_hook=plan)
    await store.start()
    first = _sample(0, fingerprint="same")
    second = _sample(1, fingerprint="same")
    await store.apply_sample(first, _transition_for(first))
    await store.apply_sample(second, _transition_for(second))
    if operation == "event":
        action = store.record_event(
            _event(99),
            UnresolvedLearningIdentity("provider-u", "responses", 1),
        )
    elif operation == "anchor":
        action = store.record_anchor_use(
            AnchorUseIntent(
                AnchorKind.EXACT,
                first.identity,
                0,
                first.features.full_fingerprint,
                (first.sample_key, second.sample_key),
            )
        )
    else:
        store._limits = replace(limits, samples_per_identity=1)  # pyright: ignore[reportPrivateUsage]
        action = store.prune()
    before_global = await _scalar(path, "SELECT global_revision FROM schema_meta")
    before_samples = await _scalar(path, "SELECT count(*) FROM samples")
    plan.arm((phase, 1))
    task = asyncio.ensure_future(action)

    with pytest.raises(StoreOperationCancelled) as caught:
        await task

    assert caught.value.phase is phase
    assert task.cancelled()
    await _assert_write_lock_available(path)
    if phase is StoreCancellationPhase.COMMIT:
        assert await _scalar(path, "SELECT global_revision FROM schema_meta") >= before_global
    else:
        assert await _scalar(path, "SELECT global_revision FROM schema_meta") == before_global
        assert await _scalar(path, "SELECT count(*) FROM samples") == before_samples
    plan.disarm()
    await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("visual_tokens", [None, 0, 6])
async def test_capability_visual_tokens_round_trip_preserves_presence_and_sqlite_type(
    tmp_path: Path,
    visual_tokens: int | None,
) -> None:
    path = tmp_path / f"visual-{visual_tokens}.sqlite3"
    sample = _sample(0, capability_visual_tokens=visual_tokens)
    store = TokenLearningStore(path)
    await store.start()
    result = await store.apply_sample(sample, _transition_for(sample))

    assert result.snapshot.samples[0].features.capability_visual_tokens == visual_tokens
    expected_storage = "null" if visual_tokens is None else "integer"
    assert await _rows(
        path,
        "SELECT capability_visual_tokens, typeof(capability_visual_tokens) FROM samples",
    ) == ((visual_tokens, expected_storage),)
    with pytest.raises(sqlite3.IntegrityError):
        async with aiosqlite.connect(path) as connection:
            await connection.execute("UPDATE samples SET capability_visual_tokens = -1")
    with pytest.raises(sqlite3.IntegrityError):
        async with aiosqlite.connect(path) as connection:
            await connection.execute("UPDATE samples SET capability_visual_tokens = x'00'")
    await store.close()

    restarted = TokenLearningStore(path)
    await restarted.start()
    assert (await restarted.snapshot_for_prediction(sample.identity)).samples[0].features.capability_visual_tokens == visual_tokens
    await restarted.close()


@pytest.mark.asyncio
async def test_candidate_keys_champions_and_event_json_round_trip_without_decision_intent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "candidate-keys.sqlite3"
    sample = _sample(0, capability_visual_tokens=6)
    store = TokenLearningStore(path)
    await store.start()

    result = await store.apply_sample(sample, _multi_variant_transition_for(sample))

    record = result.snapshot.prediction_records[0]
    assert record.selected_key == PredictionCandidateKey(
        PredictionMethod.HISTORY_PREFIX,
        PredictionCandidateVariant.ADDITIVE,
    )
    assert tuple(candidate.candidate_key for candidate in record.candidates) == (
        PredictionCandidateKey(
            PredictionMethod.HISTORY_PREFIX,
            PredictionCandidateVariant.DETERMINISTIC,
        ),
        PredictionCandidateKey(
            PredictionMethod.HISTORY_PREFIX,
            PredictionCandidateVariant.ADDITIVE,
        ),
        PredictionCandidateKey(
            PredictionMethod.COLD_START,
            PredictionCandidateVariant.DETERMINISTIC,
        ),
    )
    assert tuple(evaluation.candidate_key for evaluation in result.snapshot.evaluations) == tuple(
        candidate.candidate_key for candidate in record.candidates
    )
    row = (await _rows(
        path,
        "SELECT selected_method, selected_variant, method_champions_json, candidates_json FROM prediction_records",
    ))[0]
    champions = json.loads(row[2])
    candidates = json.loads(row[3])
    event_evaluations = json.loads((await _rows(path, "SELECT evaluations_json FROM learning_events"))[0][0])
    assert row[:2] == ("history-prefix", "additive")
    assert [set(item) for item in champions] == [
        {"method", "variant", "eligible_for_selection"},
        {"method", "variant", "eligible_for_selection"},
    ]
    assert all(set(item) == {"method", "variant", "unscaled_tokens", "sample_count", "low_confidence_reasons"} for item in candidates)
    assert all(set(item) == {"sample_key", "method", "variant", "predicted_tokens", "actual_tokens", "absolute_error", "signed_relative_error", "absolute_percentage_error"} for item in event_evaluations)
    assert "intent" not in row[2] + row[3] + json.dumps(event_evaluations)
    assert "anchor_use_intent" not in " ".join(
        value[0] or ""
        for value in await _rows(path, "SELECT sql FROM sqlite_schema WHERE sql IS NOT NULL")
    )
    with pytest.raises(sqlite3.IntegrityError):
        async with aiosqlite.connect(path) as connection:
            await connection.execute(
                "UPDATE evaluations SET candidate_variant = 'additive' WHERE method = 'cold-start'"
            )
    await store.close()

    restarted = TokenLearningStore(path)
    await restarted.start()
    assert await restarted.snapshot_for_prediction(sample.identity) == result.snapshot
    await restarted.close()


@pytest.mark.asyncio
async def test_diagnostic_retention_budget_is_independent_per_candidate_key(tmp_path: Path) -> None:
    path = tmp_path / "per-candidate-budget.sqlite3"
    limits = replace(_StoreLimits(), evaluations_per_window=2)
    store = TokenLearningStore(path, _limits=limits)
    await store.start()
    for index in range(3):
        sample = _sample(index, profile_suffix="shared")
        await store.apply_sample(sample, _multi_variant_transition_for(sample))

    assert await _rows(
        path,
        "SELECT method, candidate_variant, count(*) FROM evaluations GROUP BY method, candidate_variant ORDER BY method, candidate_variant",
    ) == (
        ("cold-start", "deterministic", 2),
        ("history-prefix", "additive", 2),
        ("history-prefix", "deterministic", 2),
    )
    assert await _scalar(path, "SELECT count(*) FROM prediction_records") == 3
    await store.close()

    restarted = TokenLearningStore(path, _limits=limits)
    await restarted.start()
    snapshot = await restarted.snapshot_for_prediction(_identity())
    assert len(snapshot.prediction_records) == 3
    assert len(snapshot.evaluations) == 6
    await restarted.close()


def test_candidate_encoder_has_exact_durable_field_set_without_intent() -> None:
    sample = _sample(0)
    update = _multi_variant_transition_for(sample)(LearningSnapshot(sample.identity, 0, 0))

    candidates = json.loads(
        learning_store_module._encode_candidates(  # pyright: ignore[reportPrivateUsage]
            update.prediction_record.candidates
        )
    )

    assert all(
        set(item)
        == {
            "method",
            "variant",
            "unscaled_tokens",
            "sample_count",
            "low_confidence_reasons",
        }
        for item in candidates
    )
    assert "intent" not in json.dumps(candidates)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "selected-key",
        "champion-eligibility",
        "candidate-key",
        "evaluation-key",
        "event-evaluation-key",
        "event-evaluation-duplicate",
    ],
)
async def test_candidate_key_graph_rejects_independent_raw_corruption(
    tmp_path: Path,
    case: str,
) -> None:
    source = tmp_path / "candidate-source.sqlite3"
    sample = _sample(0)
    store = TokenLearningStore(source)
    await store.start()
    await store.apply_sample(sample, _multi_variant_transition_for(sample))
    await store.close()
    path = tmp_path / f"candidate-{case}.sqlite3"
    shutil.copyfile(source, path)
    connection = sqlite3.connect(path)
    if case == "selected-key":
        connection.execute("UPDATE prediction_records SET selected_variant = 'multiplicative'")
    elif case == "champion-eligibility":
        champions = json.loads(
            connection.execute("SELECT method_champions_json FROM prediction_records").fetchone()[0]
        )
        champions[-1]["eligible_for_selection"] = False
        connection.execute(
            "UPDATE prediction_records SET method_champions_json = ?",
            (json.dumps(champions, separators=(",", ":"), sort_keys=True),),
        )
    elif case == "candidate-key":
        candidates = json.loads(
            connection.execute("SELECT candidates_json FROM prediction_records").fetchone()[0]
        )
        candidates[0]["variant"] = "median"
        connection.execute(
            "UPDATE prediction_records SET candidates_json = ?",
            (json.dumps(candidates, separators=(",", ":"), sort_keys=True),),
        )
    elif case == "evaluation-key":
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE evaluations SET candidate_variant = 'median' WHERE method = 'history-prefix' AND candidate_variant = 'deterministic'"
        )
    else:
        evaluations = json.loads(
            connection.execute("SELECT evaluations_json FROM learning_events").fetchone()[0]
        )
        if case == "event-evaluation-key":
            evaluations[0]["variant"] = "median"
        else:
            evaluations.append(evaluations[0].copy())
        connection.execute(
            "UPDATE learning_events SET evaluations_json = ?",
            (json.dumps(evaluations, separators=(",", ":"), sort_keys=True),),
        )
    connection.commit()
    connection.close()
    before = path.read_bytes()

    with pytest.raises(LearningStoreStartupError) as caught:
        await TokenLearningStore(path).start()

    assert caught.value.reason is LearningStoreStartupReason.INVALID_STATE
    assert path.read_bytes() == before
