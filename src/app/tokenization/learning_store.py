from __future__ import annotations
# ruff: noqa: I001

import asyncio
import hashlib
import json
import math
import sqlite3
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

import aiosqlite

from app.config.paths import tokenization_learning_path
from app.tokenization.learning_schema import (
    CREATE_SCHEMA_STATEMENTS,
    SCHEMA_MANIFEST_DIGEST,
    SCHEMA_VERSION,
    V1_INDEXES,
    V1_TABLES,
    ColumnManifest,
    ForeignKeyManifest,
    IndexColumnManifest,
    IndexManifest,
    TableManifest,
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
    DeleteRecoveredPrefixCheckpoint,
    DuplicateSampleMetadata,
    EstimateFeatures,
    ExactAnchor,
    ExactCountMismatchMetadata,
    FeatureName,
    FeatureValue,
    FeatureVector,
    FixedContextContribution,
    IdentityVersionChangeMetadata,
    InconsistentUsageMetadata,
    LearningIdentity,
    LearningReasonCode,
    LearningReasonMetadata,
    LearningSnapshot,
    LearningUpdate,
    MethodChampion,
    MigrationFailedMetadata,
    MissingUsageMetadata,
    OperationCancelledMetadata,
    PredictionCandidateKey,
    PredictionCandidateVariant,
    PredictionEvaluation,
    PredictionMethod,
    PredictionRecord,
    PrefixAnchor,
    PrefixCheckpointApplied,
    PrefixCheckpointCapacityReason,
    PrefixCheckpointCapacityRejected,
    PrefixCheckpointCapacityRolledOver,
    PrefixCheckpointCommand,
    PrefixCheckpointDeleted,
    PrefixCheckpointMode,
    PrefixCheckpointNotAttempted,
    PrefixCheckpointNotAttemptedReason,
    PrefixCheckpointNotCommitted,
    PrefixCheckpointStoreOutcome,
    PrefixChampionErrorTriple,
    PendingPrefixChampionErrorTriple,
    PrefixEligibilityCheckpoint,
    ReplacePrefixCheckpoint,
    NoPrefixCheckpointChange,
    InputItemContribution,
    PrefixFingerprint,
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

_MAX_IDENTITY_TEXT_BYTES = 1_024
_MAX_SAMPLE_KEY_TEXT_BYTES = 1_024
_MAX_JSON_BYTES = 64 * 1_024
_SQLITE_PARAMETER_CHUNK = 300

type Transition = Callable[[LearningSnapshot], LearningUpdate]
type ReaderStepHook = Callable[[str], Awaitable[None]]
type TraceCallback = Callable[[str], None]
type ThreadProbe = Callable[[str, int], None]
type ConnectionFactory = Callable[[Path, bool], aiosqlite.Connection]
type ActionHook = Callable[[str, StoreCancellationPhase], Awaitable[None]]
type ActionTrace = Callable[[str, bool], None]
type Clock = Callable[[], int]
type _IdentityKey = tuple[str, str, str, str, str, str, int, int]
type _SampleOwnerKey = tuple[int, int, str, str, int]
type _Row = tuple[Any, ...]

_T = TypeVar("_T")

_ACTION_BASE_SHAPES = (
    *(('ONE', value) for value in (
        'lock.start.lifecycle',
        'lock.snapshot.lifecycle',
        'lock.snapshot.reader',
        'lock.apply.lifecycle',
        'lock.apply.writer',
        'lock.event.lifecycle',
        'lock.event.writer',
        'lock.anchor-use.lifecycle',
        'lock.anchor-use.writer',
        'lock.prune.lifecycle',
        'lock.prune.writer',
        'lock.close.lifecycle',
        'lock.close.reader',
        'lock.close.writer',
        'lock.close.shared-completion',
        'connection.inspect.open',
        'connection.inspect.close',
        'connection.writer.open',
        'connection.writer.close',
        'connection.reader.open',
        'connection.reader.close',
        'instrument.writer.thread-probe-install',
        'instrument.writer.trace-install',
        'instrument.reader.thread-probe-install',
        'instrument.reader.trace-install',
        'tx.inspect.commit',
        'tx.inspect.rollback',
        'tx.migration.commit',
        'tx.migration.rollback',
        'tx.refresh.commit',
        'tx.refresh.rollback',
        'tx.apply.commit',
        'tx.apply.rollback',
        'tx.event.commit',
        'tx.event.rollback',
        'tx.anchor-use.commit',
        'tx.anchor-use.rollback',
        'tx.prune.commit',
        'tx.prune.rollback',
        'cpu.state-decode',
        'cpu.transition',
        'retry.busy-sleep',
    )),
    *(('EC', value) for value in (
        'tx.inspect.begin',
        'tx.migration.begin',
        'tx.refresh.begin',
        'tx.apply.begin',
        'tx.event.begin',
        'tx.anchor-use.begin',
        'tx.prune.begin',
        'pragma.writer.foreign-keys-set',
        'pragma.writer.busy-timeout-set',
        'pragma.writer.synchronous-set',
        'pragma.reader.foreign-keys-set',
        'pragma.reader.busy-timeout-set',
        'pragma.reader.synchronous-set',
        'pragma.reader.query-only-set',
        'schema.create-statement',
        'schema.meta-insert',
        'epoch.owner-insert',
        'epoch.sample-insert',
        'epoch.prediction-insert',
        'identity.active-epoch-update',
        'sample.insert',
        'prediction-record.insert',
        'evaluation.insert',
        'exact-anchor.insert',
        'prefix-anchor.insert',
        'prefix-checkpoint.upsert',
        'prefix-checkpoint.delete',
        'identity.revision-update',
        'global-revision.update',
        'sample.delete',
        'evaluation.delete',
        'epoch.empty-delete',
        'identity.empty-delete',
        'event.insert',
        'event.ids-delete',
        'event.bucket-prune',
        'event.global-prune',
        'anchor-use.sample-update',
    )),
    *(('EFC', value) for value in (
        'pragma.writer.foreign-keys-read',
        'pragma.reader.foreign-keys-read',
        'pragma.writer.journal-mode-wal',
        'pragma.reader.data-version',
        'pragma.inspect.quick-check',
        'pragma.writer.checkpoint',
        'instrument.worker-probe',
        'schema.objects-read',
        'schema.meta-read',
        'schema.table-list-read',
        'schema.table-xinfo-read',
        'schema.table-ddl-read',
        'schema.index-list-read',
        'schema.index-xinfo-read',
        'schema.foreign-keys-read',
        'state.schema-meta-read',
        'state.identities-read',
        'state.epochs-read',
        'state.samples-read',
        'state.prediction-records-read',
        'state.evaluations-read',
        'state.exact-anchors-read',
        'state.prefix-anchors-read',
        'state.prefix-checkpoints-read',
        'state.events-read',
        'apply.duplicate-read',
        'identity.lookup',
        'identity.insert-returning',
        'global-revision.read',
        'identity.revision-read',
        'sample.exists',
    )),
)


def _expand_action_ids() -> frozenset[str]:
    result: set[str] = set()
    for shape, base in _ACTION_BASE_SHAPES:
        if shape == 'ONE':
            result.add(base)
        elif shape == 'EC':
            result.update((f'{base}.execute', f'{base}.cursor-close'))
        else:
            result.update((f'{base}.execute', f'{base}.fetch', f'{base}.cursor-close'))
    return frozenset(result)


CONFIRMED_ACTION_IDS = _expand_action_ids()
if len(_ACTION_BASE_SHAPES) != 111 or len(CONFIRMED_ACTION_IDS) != 211:
    raise RuntimeError('confirmed action registry does not match the V1 contract')


class LearningStoreError(RuntimeError):
    """Base error for the versioned token-learning store."""


class LearningStoreStateError(LearningStoreError):
    """Raised when a lifecycle operation is unavailable."""


class LearningStoreStartupReason(StrEnum):
    CORRUPT = "corrupt"
    UNSUPPORTED_SCHEMA = "unsupported-schema"
    MANIFEST_MISMATCH = "manifest-mismatch"
    INVALID_STATE = "invalid-state"
    MIGRATION_FAILED = "migration-failed"


class LearningStoreStartupError(LearningStoreError):
    """Raised when startup cannot safely use the existing database."""

    def __init__(self, reason: LearningStoreStartupReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


class UnsupportedLearningSchemaError(LearningStoreStartupError):
    """Raised for a database whose declared version is unsupported."""

    def __init__(self) -> None:
        super().__init__(LearningStoreStartupReason.UNSUPPORTED_SCHEMA)


class LearningStoreTransitionError(LearningStoreError):
    """Raised when a pure transition fails or changes analyzed facts."""


class StoreOperationCancelled(asyncio.CancelledError):
    """Cancellation with a determinate durable outcome."""

    def __init__(
        self,
        phase: StoreCancellationPhase,
        committed_observation: TokenLearningObservation | None,
    ) -> None:
        self.phase = phase
        self.committed_observation = committed_observation
        super().__init__(phase.value)


class _InstrumentableConnection(Protocol):
    async def set_trace_callback(self, handler: TraceCallback) -> None: ...

    async def create_function(
        self,
        name: str,
        num_params: int,
        func: Callable[..., object],
        deterministic: bool = False,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class LearningApplyResult:
    observation: TokenLearningObservation
    snapshot: LearningSnapshot


@dataclass(frozen=True, slots=True)
class UnresolvedLearningIdentity:
    actual_provider: str
    endpoint: str
    estimator_generation: int

    def __post_init__(self) -> None:
        _require_bounded_text("actual_provider", self.actual_provider, _MAX_IDENTITY_TEXT_BYTES)
        _require_bounded_text("endpoint", self.endpoint, _MAX_IDENTITY_TEXT_BYTES)
        if type(self.estimator_generation) is not int or self.estimator_generation < 1:
            raise ValueError("estimator_generation must be a positive integer")


@dataclass(frozen=True, slots=True)
class _StoreLimits:
    samples_per_identity: int = 4_096
    samples_global: int = 32_768
    actuals_per_fingerprint: int = 5
    evaluations_per_window: int = 128
    events_per_identity: int = 4_096
    events_global: int = 32_768
    prefix_checkpoints_per_identity: int = 4_096
    prefix_checkpoints_global: int = 32_768

    def __post_init__(self) -> None:
        for name, value in (
            ("samples_per_identity", self.samples_per_identity),
            ("samples_global", self.samples_global),
            ("actuals_per_fingerprint", self.actuals_per_fingerprint),
            ("evaluations_per_window", self.evaluations_per_window),
            ("events_per_identity", self.events_per_identity),
            ("events_global", self.events_global),
            ("prefix_checkpoints_per_identity", self.prefix_checkpoints_per_identity),
            ("prefix_checkpoints_global", self.prefix_checkpoints_global),
        ):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")


_DEFAULT_LIMITS = _StoreLimits()


@dataclass(frozen=True, slots=True)
class _ConfirmedResult[T]:
    value: T
    cancellation_requested: bool


class _ActionCancelled(BaseException):
    def __init__(
        self,
        phase: StoreCancellationPhase,
        action_error: BaseException | None = None,
    ) -> None:
        self.phase = phase
        self.action_error = action_error
        super().__init__(phase.value)


@dataclass(frozen=True, slots=True)
class _IdentityState:
    identity_id: int
    identity: LearningIdentity
    revision: int


@dataclass(frozen=True, slots=True)
class _EpochState:
    identity_id: int
    epoch: int
    created_order: int


@dataclass(frozen=True, slots=True)
class _PersistentSample:
    sample_id: int
    identity_id: int
    epoch: int
    last_used_order: int
    sample: StoredSample

    @property
    def owner_key(self) -> _SampleOwnerKey:
        return (self.identity_id, self.epoch, *self.sample.sample_key)


@dataclass(frozen=True, slots=True)
class _PersistentPrediction:
    identity_id: int
    sample_epoch: int
    prediction_epoch: int
    record: PredictionRecord

    @property
    def owner_key(self) -> _SampleOwnerKey:
        return (self.identity_id, self.sample_epoch, *self.record.sample_key)


@dataclass(frozen=True, slots=True)
class _PersistentEvaluation:
    identity_id: int
    sample_epoch: int
    prediction_epoch: int
    profile_key_hash: str
    ordinal: int
    evaluation: PredictionEvaluation

    @property
    def owner_key(self) -> _SampleOwnerKey:
        return (self.identity_id, self.sample_epoch, *self.evaluation.sample_key)


@dataclass(frozen=True, slots=True)
class _PersistentExactAnchor:
    identity_id: int
    epoch: int
    sample_key: SampleKey
    full_fingerprint: str
    actual_tokens: int

    @property
    def owner_key(self) -> _SampleOwnerKey:
        return (self.identity_id, self.epoch, *self.sample_key)


@dataclass(frozen=True, slots=True)
class _PersistentPrefixAnchor:
    identity_id: int
    epoch: int
    anchor: PrefixAnchor

    @property
    def owner_key(self) -> _SampleOwnerKey:
        return (self.identity_id, self.epoch, *self.anchor.sample_key)


@dataclass(frozen=True, slots=True)
class _PersistentPrefixCheckpoint:
    identity_id: int
    epoch: int
    checkpoint: PrefixEligibilityCheckpoint


@dataclass(frozen=True, slots=True)
class _PersistentEvent:
    event_id: int
    identity_id: int | None
    learning_epoch: int | None
    sample_key: SampleKey | None
    bucket_key: str
    observation: TokenLearningObservation
    unresolved_identity: UnresolvedLearningIdentity | None
    created_at_us: int


@dataclass(frozen=True, slots=True)
class ValidatedPersistentState:
    global_revision: int
    identities: tuple[_IdentityState, ...]
    epochs: tuple[_EpochState, ...]
    samples: tuple[_PersistentSample, ...]
    prediction_records: tuple[_PersistentPrediction, ...]
    evaluations: tuple[_PersistentEvaluation, ...]
    reconstructed_evaluations: tuple[_PersistentEvaluation, ...]
    exact_anchors: tuple[_PersistentExactAnchor, ...]
    prefix_anchors: tuple[_PersistentPrefixAnchor, ...]
    prefix_checkpoints: tuple[_PersistentPrefixCheckpoint, ...]
    events: tuple[_PersistentEvent, ...]
    active_snapshots: tuple[tuple[_IdentityKey, LearningSnapshot], ...]

    def snapshot(self, identity: LearningIdentity) -> LearningSnapshot:
        key = _identity_key(identity)
        for candidate_key, snapshot in self.active_snapshots:
            if candidate_key == key:
                return snapshot
        return _empty_snapshot(identity)


@dataclass(frozen=True, slots=True)
class _AllRows:
    meta: tuple[_Row, ...]
    identities: tuple[_Row, ...]
    epochs: tuple[_Row, ...]
    samples: tuple[_Row, ...]
    prediction_records: tuple[_Row, ...]
    evaluations: tuple[_Row, ...]
    exact_anchors: tuple[_Row, ...]
    prefix_anchors: tuple[_Row, ...]
    prefix_checkpoints: tuple[_Row, ...]
    events: tuple[_Row, ...]


@dataclass(frozen=True, slots=True)
class _EncodedSample:
    components_json: str
    profile_key_json: str
    profile_key_hash: str
    feature_vector_json: str
    prefix_fingerprints_json: str
    fixed_context_contribution_json: str
    input_item_contributions_json: str
    low_confidence_reasons_json: str


@dataclass(frozen=True, slots=True)
class _PreparedUpdate:
    update: LearningUpdate
    sample: _EncodedSample
    candidates_json: str
    method_champions_json: str


@dataclass(frozen=True, slots=True)
class _PrunePlan:
    sample_owners: tuple[_SampleOwnerKey, ...]
    evaluation_keys: tuple[tuple[_SampleOwnerKey, PredictionCandidateKey], ...]
    affected_identity_ids: frozenset[int]


@dataclass(frozen=True, slots=True)
class _CloseOutcome:
    error: Exception | None = None
    cancellation_phase: StoreCancellationPhase | None = None


class TokenLearningStore:
    """Persist compact history behind one immutable-snapshot interface."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        busy_retry_timeout: float = 5.0,
        busy_retry_delay: float = 0.01,
        _limits: _StoreLimits = _DEFAULT_LIMITS,
        _reader_step_hook: ReaderStepHook | None = None,
        _trace_callback: TraceCallback | None = None,
        _thread_probe: ThreadProbe | None = None,
        _connection_factory: ConnectionFactory | None = None,
        _action_hook: ActionHook | None = None,
        _action_trace: ActionTrace | None = None,
        _clock: Clock | None = None,
    ) -> None:
        if not math.isfinite(busy_retry_timeout) or busy_retry_timeout < 0:
            raise ValueError("busy_retry_timeout must be finite and nonnegative")
        if not math.isfinite(busy_retry_delay) or busy_retry_delay <= 0:
            raise ValueError("busy_retry_delay must be finite and positive")
        self._path = path if path is not None else tokenization_learning_path()
        self._busy_retry_timeout = busy_retry_timeout
        self._busy_retry_delay = busy_retry_delay
        self._limits = _limits
        self._reader_step_hook = _reader_step_hook
        self._trace_callback = _trace_callback
        self._thread_probe = _thread_probe
        self._connection_factory = _connection_factory or _default_connection_factory
        self._action_hook = _action_hook
        self._action_trace = _action_trace
        self._clock = _clock or _now_us
        self._writer: aiosqlite.Connection | None = None
        self._reader: aiosqlite.Connection | None = None
        self._writer_lock = asyncio.Lock()
        self._reader_lock = asyncio.Lock()
        self._reader_refreshing = False
        self._lifecycle_lock = asyncio.Lock()
        self._state = "new"
        self._close_completion: asyncio.Future[_CloseOutcome] | None = None
        self._physical_close_task: asyncio.Task[None] | None = None
        self._validated_state = _empty_persistent_state()
        self._cache: dict[_IdentityKey, LearningSnapshot] = {}
        self._reader_data_version: int | None = None
        self._last_refresh_error: Exception | None = None
        self._created_schema = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def last_refresh_error(self) -> Exception | None:
        return self._last_refresh_error

    async def start(self) -> None:
        lifecycle_acquired = False
        try:
            await self._acquire_lock(
                self._lifecycle_lock,
                action_id="lock.start.lifecycle",
                phase=StoreCancellationPhase.LOCK_WAIT,
                honor_cancellation=True,
            )
            lifecycle_acquired = True
            if self._state != "new":
                raise LearningStoreStateError(
                    f"learning store cannot start from state {self._state}"
                )
            self._state = "starting"
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                if self._path.exists():
                    await self._inspect_existing_with_retry()
                writer, state, created = await self._open_writer_with_migration_retry()
                self._writer = writer
                self._created_schema = created
                reader = await self._open_connection(
                    read_only=False,
                    role="reader",
                )
                self._reader = reader
                await self._install_connection_instrumentation(reader, "reader")
                await self._configure_connection(reader, query_only=True)
                state = await self._read_validated_transaction(reader)
                self._reader_data_version = await self._read_data_version(reader)
                self._publish_state(state)
            except StoreOperationCancelled:
                await self._close_all_connections(honor_cancellation=False)
                self._state = "failed"
                raise
            except _ActionCancelled as cancelled:
                await self._close_all_connections(honor_cancellation=False)
                self._state = "failed"
                raise _public_cancellation(cancelled) from cancelled.action_error
            except LearningStoreStartupError:
                await self._close_all_connections(honor_cancellation=False)
                self._state = "failed"
                raise
            except BaseException as error:
                await self._close_all_connections(honor_cancellation=False)
                self._state = "failed"
                if isinstance(error, asyncio.CancelledError):
                    raise StoreOperationCancelled(
                        StoreCancellationPhase.LOCK_WAIT,
                        None,
                    ) from error
                if isinstance(error, Exception):
                    raise LearningStoreStartupError(
                        LearningStoreStartupReason.MIGRATION_FAILED
                    ) from error
                raise
            self._state = "running"
        except StoreOperationCancelled:
            raise
        except _ActionCancelled as cancelled:
            raise _public_cancellation(cancelled) from cancelled.action_error
        except asyncio.CancelledError as error:
            raise StoreOperationCancelled(StoreCancellationPhase.LOCK_WAIT, None) from error
        finally:
            if lifecycle_acquired:
                self._lifecycle_lock.release()

    async def snapshot_for_prediction(self, identity: LearningIdentity) -> LearningSnapshot:
        _validate_identity(identity)
        lifecycle_acquired = False
        reader_acquired = False
        refreshing = False
        key = _identity_key(identity)
        cached = self._cache.get(key, _empty_snapshot(identity))
        try:
            await self._acquire_lock(
                self._lifecycle_lock,
                action_id="lock.snapshot.lifecycle",
                phase=StoreCancellationPhase.LOCK_WAIT,
                honor_cancellation=True,
            )
            lifecycle_acquired = True
            self._require_running()
            if self._close_completion is not None:
                raise LearningStoreStateError("learning store is closing")
            if self._reader_refreshing:
                return replace(cached, is_stale=True)
            self._reader_refreshing = True
            refreshing = True
            await self._acquire_lock(
                self._reader_lock,
                action_id="lock.snapshot.reader",
                phase=StoreCancellationPhase.LOCK_WAIT,
                honor_cancellation=True,
            )
            reader_acquired = True
            self._lifecycle_lock.release()
            lifecycle_acquired = False
            reader = self._require_reader()
            data_version = await self._read_data_version(reader)
            if self._reader_data_version == data_version:
                return self._cache.get(key, _empty_snapshot(identity))
            state = await self._read_validated_transaction(reader)
            self._reader_data_version = data_version
            self._publish_state(state)
            self._last_refresh_error = None
            return self._cache.get(key, _empty_snapshot(identity))
        except _ActionCancelled as cancelled:
            raise _public_cancellation(cancelled) from cancelled.action_error
        except StoreOperationCancelled:
            raise
        except asyncio.CancelledError as error:
            raise StoreOperationCancelled(StoreCancellationPhase.LOCK_WAIT, None) from error
        except LearningStoreStateError:
            raise
        except Exception as error:
            self._last_refresh_error = error
            return replace(cached, is_stale=True)
        finally:
            if reader_acquired:
                self._reader_lock.release()
            if lifecycle_acquired:
                self._lifecycle_lock.release()
            if refreshing:
                self._reader_refreshing = False

    async def apply_sample(
        self,
        analyzed_sample: StoredSample,
        transition: Transition,
    ) -> LearningApplyResult:
        _validate_sample_logical(analyzed_sample)
        writer_acquired = False
        try:
            await self._acquire_operation_lock(
                lifecycle_action_id="lock.apply.lifecycle",
                resource_lock=self._writer_lock,
                resource_action_id="lock.apply.writer",
            )
            writer_acquired = True
            return await self._apply_with_retry(analyzed_sample, transition)
        except StoreOperationCancelled:
            raise
        except _ActionCancelled as cancelled:
            raise _public_cancellation(cancelled) from cancelled.action_error
        except asyncio.CancelledError as error:
            raise StoreOperationCancelled(StoreCancellationPhase.LOCK_WAIT, None) from error
        finally:
            if writer_acquired:
                self._writer_lock.release()

    async def record_event(
        self,
        observation: TokenLearningObservation,
        identity: LearningIdentity | UnresolvedLearningIdentity,
    ) -> None:
        if observation.outcome == "committed":
            raise ValueError("committed observations must be recorded by apply_sample")
        _validate_observation_for_storage(observation)
        if isinstance(identity, LearningIdentity):
            _validate_identity(identity)
            if observation.drift is not None and not _same_identity_base(
                observation.drift.identity,
                identity,
            ):
                raise ValueError("event drift identity must match its resolved identity")
        elif observation.drift is not None:
            raise ValueError("an unresolved learning event cannot carry drift")
        writer_acquired = False
        try:
            await self._acquire_operation_lock(
                lifecycle_action_id="lock.event.lifecycle",
                resource_lock=self._writer_lock,
                resource_action_id="lock.event.writer",
            )
            writer_acquired = True
            await self._record_event_with_retry(observation, identity)
        except StoreOperationCancelled:
            raise
        except _ActionCancelled as cancelled:
            raise _public_cancellation(cancelled) from cancelled.action_error
        except asyncio.CancelledError as error:
            raise StoreOperationCancelled(StoreCancellationPhase.LOCK_WAIT, None) from error
        finally:
            if writer_acquired:
                self._writer_lock.release()

    async def record_anchor_use(self, intent: AnchorUseIntent) -> AnchorUseOutcome:
        _validate_identity(intent.identity)
        writer_acquired = False
        try:
            await self._acquire_operation_lock(
                lifecycle_action_id="lock.anchor-use.lifecycle",
                resource_lock=self._writer_lock,
                resource_action_id="lock.anchor-use.writer",
            )
            writer_acquired = True
            return await self._record_anchor_use_with_retry(intent)
        except StoreOperationCancelled:
            raise
        except _ActionCancelled as cancelled:
            raise _public_cancellation(cancelled) from cancelled.action_error
        except asyncio.CancelledError as error:
            raise StoreOperationCancelled(StoreCancellationPhase.LOCK_WAIT, None) from error
        finally:
            if writer_acquired:
                self._writer_lock.release()

    async def prune(self) -> None:
        writer_acquired = False
        try:
            await self._acquire_operation_lock(
                lifecycle_action_id="lock.prune.lifecycle",
                resource_lock=self._writer_lock,
                resource_action_id="lock.prune.writer",
            )
            writer_acquired = True
            await self._prune_with_retry()
        except StoreOperationCancelled:
            raise
        except _ActionCancelled as cancelled:
            raise _public_cancellation(cancelled) from cancelled.action_error
        except asyncio.CancelledError as error:
            raise StoreOperationCancelled(StoreCancellationPhase.LOCK_WAIT, None) from error
        finally:
            if writer_acquired:
                self._writer_lock.release()

    def close(self) -> Awaitable[None]:
        if self._state == "closed":
            return self._closed_close()
        owner_ticket = self._close_completion is None
        if owner_ticket:
            self._close_completion = asyncio.get_running_loop().create_future()
            self._physical_close_task = asyncio.create_task(
                self._close_owner(self._close_completion)
            )
        assert self._close_completion is not None
        return self._wait_for_close(
            self._close_completion,
            owner_ticket=owner_ticket,
        )

    async def _closed_close(self) -> None:
        return

    async def _wait_for_close(
        self,
        completion: asyncio.Future[_CloseOutcome],
        *,
        owner_ticket: bool,
    ) -> None:
        result = await self._confirmed(
            completion,
            StoreCancellationPhase.CLOSE_WAIT,
            "lock.close.shared-completion",
            raw=False,
        )
        if result.value.error is not None:
            raise result.value.error
        cancellation_phase = result.value.cancellation_phase
        if cancellation_phase is None and result.cancellation_requested:
            cancellation_phase = (
                StoreCancellationPhase.CLOSE_LOCK_WAIT
                if owner_ticket
                else StoreCancellationPhase.CLOSE_WAIT
            )
        if cancellation_phase is not None:
            raise StoreOperationCancelled(cancellation_phase, None)

    async def _close_owner(
        self,
        completion: asyncio.Future[_CloseOutcome],
    ) -> None:
        lifecycle_acquired = False
        reader_acquired = False
        writer_acquired = False
        cancellation_phase: StoreCancellationPhase | None = None
        errors: list[Exception] = []
        try:
            lifecycle_cancelled = await self._acquire_lock(
                self._lifecycle_lock,
                action_id="lock.close.lifecycle",
                phase=StoreCancellationPhase.CLOSE_LOCK_WAIT,
                honor_cancellation=False,
            )
            lifecycle_acquired = True
            if lifecycle_cancelled:
                cancellation_phase = StoreCancellationPhase.CLOSE_LOCK_WAIT
            if self._state == "closed":
                return
            self._state = "closing"
            reader_cancelled = await self._acquire_lock(
                self._reader_lock,
                action_id="lock.close.reader",
                phase=StoreCancellationPhase.CLOSE_LOCK_WAIT,
                honor_cancellation=False,
            )
            reader_acquired = True
            if reader_cancelled and cancellation_phase is None:
                cancellation_phase = StoreCancellationPhase.CLOSE_LOCK_WAIT
            writer_cancelled = await self._acquire_lock(
                self._writer_lock,
                action_id="lock.close.writer",
                phase=StoreCancellationPhase.CLOSE_LOCK_WAIT,
                honor_cancellation=False,
            )
            writer_acquired = True
            if writer_cancelled and cancellation_phase is None:
                cancellation_phase = StoreCancellationPhase.CLOSE_LOCK_WAIT
            if self._writer is not None:
                try:
                    await self._checkpoint(self._writer)
                except _ActionCancelled as error:
                    cancellation_phase = cancellation_phase or error.phase
                except Exception as error:
                    errors.append(error)
            if self._reader is not None:
                try:
                    reader_close_cancelled = await self._close_connection(
                        self._reader,
                        role="reader",
                        honor_cancellation=False,
                    )
                    if reader_close_cancelled and cancellation_phase is None:
                        cancellation_phase = StoreCancellationPhase.CONNECTION_CLOSE
                except _ActionCancelled as error:
                    cancellation_phase = cancellation_phase or error.phase
                    if isinstance(error.action_error, Exception):
                        errors.append(error.action_error)
                except Exception as error:
                    errors.append(error)
                self._reader = None
            if self._writer is not None:
                try:
                    writer_close_cancelled = await self._close_connection(
                        self._writer,
                        role="writer",
                        honor_cancellation=False,
                    )
                    if writer_close_cancelled and cancellation_phase is None:
                        cancellation_phase = StoreCancellationPhase.CONNECTION_CLOSE
                except _ActionCancelled as error:
                    cancellation_phase = cancellation_phase or error.phase
                    if isinstance(error.action_error, Exception):
                        errors.append(error.action_error)
                except Exception as error:
                    errors.append(error)
                self._writer = None
            self._cache.clear()
            self._state = "closed"
        except Exception as error:
            errors.append(error)
            self._state = "closed"
        finally:
            if writer_acquired:
                self._writer_lock.release()
            if reader_acquired:
                self._reader_lock.release()
            if lifecycle_acquired:
                self._lifecycle_lock.release()
            outcome_error = (
                LearningStoreError("learning store close failed")
                if errors
                else None
            )
            if outcome_error is not None:
                outcome_error.__cause__ = ExceptionGroup(
                    "close failures",
                    errors,
                )
            if not completion.done():
                completion.set_result(
                    _CloseOutcome(outcome_error, cancellation_phase)
                )

    async def _confirmed(
        self,
        awaitable: Awaitable[_T],
        phase: StoreCancellationPhase,
        action_id: str,
        *,
        raw: bool,
    ) -> _ConfirmedResult[_T]:
        if action_id not in CONFIRMED_ACTION_IDS:
            raise LearningStoreError(f"unregistered confirmed action: {action_id}")
        task = asyncio.ensure_future(awaitable)
        if self._action_trace is not None:
            self._action_trace(action_id, raw)
        cancellation_requested = False
        hook_error: BaseException | None = None
        if self._action_hook is not None:
            try:
                await self._action_hook(action_id, phase)
            except asyncio.CancelledError:
                cancellation_requested = True
            except BaseException as error:
                hook_error = error
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancellation_requested = True
            except BaseException:
                break
        try:
            value = task.result()
        except BaseException as error:
            if cancellation_requested:
                raise _ActionCancelled(phase, error) from error
            raise
        if hook_error is not None:
            raise hook_error
        return _ConfirmedResult(value, cancellation_requested)

    async def _acquire_lock(
        self,
        lock: asyncio.Lock,
        *,
        action_id: str,
        phase: StoreCancellationPhase,
        honor_cancellation: bool,
    ) -> bool:
        result = await self._confirmed(
            lock.acquire(),
            phase,
            action_id,
            raw=False,
        )
        if result.value is not True:
            raise LearningStoreError("asyncio lock acquisition returned false")
        if result.cancellation_requested and honor_cancellation:
            lock.release()
            raise _ActionCancelled(phase)
        return result.cancellation_requested

    async def _acquire_operation_lock(
        self,
        *,
        lifecycle_action_id: str,
        resource_lock: asyncio.Lock,
        resource_action_id: str,
    ) -> asyncio.Lock:
        await self._acquire_lock(
            self._lifecycle_lock,
            action_id=lifecycle_action_id,
            phase=StoreCancellationPhase.LOCK_WAIT,
            honor_cancellation=True,
        )
        try:
            self._require_running()
            if self._close_completion is not None:
                raise LearningStoreStateError("learning store is closing")
            await self._acquire_lock(
                resource_lock,
                action_id=resource_action_id,
                phase=StoreCancellationPhase.LOCK_WAIT,
                honor_cancellation=True,
            )
        finally:
            self._lifecycle_lock.release()
        return resource_lock

    async def _open_connection(
        self,
        *,
        read_only: bool,
        role: str,
    ) -> aiosqlite.Connection:
        if role not in ("inspect", "writer", "reader"):
            raise ValueError("connection role is not registered")
        connection = self._connection_factory(self._path, read_only)
        try:
            result = await self._confirmed(
                connection,
                StoreCancellationPhase.OPEN,
                f"connection.{role}.open",
                raw=True,
            )
        except _ActionCancelled:
            await self._close_connection(
                connection,
                role=role,
                honor_cancellation=False,
            )
            raise
        if result.cancellation_requested:
            await self._close_connection(
                connection,
                role=role,
                honor_cancellation=False,
            )
            raise _ActionCancelled(StoreCancellationPhase.OPEN)
        return result.value

    async def _close_connection(
        self,
        connection: aiosqlite.Connection,
        *,
        role: str,
        honor_cancellation: bool = True,
    ) -> bool:
        result = await self._confirmed(
            connection.close(),
            StoreCancellationPhase.CONNECTION_CLOSE,
            f"connection.{role}.close",
            raw=True,
        )
        if result.cancellation_requested and honor_cancellation:
            raise _ActionCancelled(StoreCancellationPhase.CONNECTION_CLOSE)
        return result.cancellation_requested

    async def _close_all_connections(self, *, honor_cancellation: bool) -> None:
        if not self._lifecycle_lock.locked():
            raise LearningStoreError("connection cleanup requires lifecycle ownership")
        reader_acquired = False
        writer_acquired = False
        errors: list[Exception] = []
        try:
            await self._acquire_lock(
                self._reader_lock,
                action_id="lock.close.reader",
                phase=StoreCancellationPhase.CLOSE_LOCK_WAIT,
                honor_cancellation=False,
            )
            reader_acquired = True
            await self._acquire_lock(
                self._writer_lock,
                action_id="lock.close.writer",
                phase=StoreCancellationPhase.CLOSE_LOCK_WAIT,
                honor_cancellation=False,
            )
            writer_acquired = True
            for role, connection in (("reader", self._reader), ("writer", self._writer)):
                if connection is None:
                    continue
                try:
                    await self._close_connection(
                        connection,
                        role=role,
                        honor_cancellation=honor_cancellation,
                    )
                except Exception as error:
                    errors.append(error)
                except _ActionCancelled:
                    if honor_cancellation:
                        raise
            self._reader = None
            self._writer = None
        finally:
            if writer_acquired:
                self._writer_lock.release()
            if reader_acquired:
                self._reader_lock.release()
        if errors:
            raise LearningStoreError("connection cleanup failed") from ExceptionGroup(
                "connection cleanup failures",
                errors,
            )

    async def _execute_sql(
        self,
        connection: aiosqlite.Connection,
        sql: str,
        parameters: Iterable[Any] = (),
        *,
        phase: StoreCancellationPhase,
        action_base: str,
        honor_cancellation: bool = True,
    ) -> None:
        result = await self._confirmed(
            connection.execute(sql, tuple(parameters)),
            phase,
            f"{action_base}.execute",
            raw=True,
        )
        cursor = result.value
        pending_phase = phase if result.cancellation_requested else None
        try:
            close_result = await self._confirmed(
                cursor.close(),
                StoreCancellationPhase.CURSOR_CLOSE,
                f"{action_base}.cursor-close",
                raw=True,
            )
            if close_result.cancellation_requested and pending_phase is None:
                pending_phase = StoreCancellationPhase.CURSOR_CLOSE
        finally:
            if pending_phase is not None and not honor_cancellation:
                pending_phase = None
        if pending_phase is not None:
            raise _ActionCancelled(pending_phase)

    async def _fetchall_sql(
        self,
        connection: aiosqlite.Connection,
        sql: str,
        parameters: Iterable[Any] = (),
        *,
        action_base: str,
        phase: StoreCancellationPhase = StoreCancellationPhase.READ,
        honor_cancellation: bool = True,
    ) -> tuple[_Row, ...]:
        execute_result = await self._confirmed(
            connection.execute(sql, tuple(parameters)),
            phase,
            f"{action_base}.execute",
            raw=True,
        )
        cursor = execute_result.value
        pending_phase = phase if execute_result.cancellation_requested else None
        rows: Iterable[Any] = ()
        try:
            if pending_phase is None:
                fetch_result = await self._confirmed(
                    cursor.fetchall(),
                    phase,
                    f"{action_base}.fetch",
                    raw=True,
                )
                rows = fetch_result.value
                if fetch_result.cancellation_requested:
                    pending_phase = phase
            close_result = await self._confirmed(
                cursor.close(),
                StoreCancellationPhase.CURSOR_CLOSE,
                f"{action_base}.cursor-close",
                raw=True,
            )
            if close_result.cancellation_requested and pending_phase is None:
                pending_phase = StoreCancellationPhase.CURSOR_CLOSE
        except BaseException as error:
            try:
                await self._close_cursor(
                    cursor,
                    action_id=f"{action_base}.cursor-close",
                    honor_cancellation=False,
                )
            except BaseException as close_error:
                raise LearningStoreError("cursor action and cleanup both failed") from BaseExceptionGroup(
                    "cursor action and cleanup failures",
                    [error, close_error],
                )
            raise
        if pending_phase is not None and honor_cancellation:
            raise _ActionCancelled(pending_phase)
        return tuple(tuple(row) for row in rows)

    async def _fetchone_sql(
        self,
        connection: aiosqlite.Connection,
        sql: str,
        parameters: Iterable[Any] = (),
        *,
        action_base: str,
        phase: StoreCancellationPhase = StoreCancellationPhase.READ,
        honor_cancellation: bool = True,
    ) -> _Row | None:
        rows = await self._fetchall_sql(
            connection,
            sql,
            parameters,
            action_base=action_base,
            phase=phase,
            honor_cancellation=honor_cancellation,
        )
        if len(rows) > 1:
            raise LearningStoreError("query expected at most one row")
        return rows[0] if rows else None

    async def _close_cursor(
        self,
        cursor: aiosqlite.Cursor,
        *,
        action_id: str,
        honor_cancellation: bool,
    ) -> None:
        result = await self._confirmed(
            cursor.close(),
            StoreCancellationPhase.CURSOR_CLOSE,
            action_id,
            raw=True,
        )
        if result.cancellation_requested and honor_cancellation:
            raise _ActionCancelled(StoreCancellationPhase.CURSOR_CLOSE)

    async def _run_cpu(
        self,
        function: Callable[..., _T],
        *args: object,
        phase: StoreCancellationPhase,
        action_id: str,
    ) -> _T:
        result = await self._confirmed(
            asyncio.to_thread(function, *args),
            phase,
            action_id,
            raw=False,
        )
        if result.cancellation_requested:
            raise _ActionCancelled(phase)
        return result.value

    async def _begin(
        self,
        connection: aiosqlite.Connection,
        *,
        immediate: bool,
        action_base: str,
    ) -> None:
        await self._execute_sql(
            connection,
            "BEGIN IMMEDIATE" if immediate else "BEGIN",
            phase=StoreCancellationPhase.BEGIN,
            action_base=action_base,
        )

    async def _commit(
        self,
        connection: aiosqlite.Connection,
        *,
        action_id: str,
    ) -> bool:
        result = await self._confirmed(
            connection.commit(),
            StoreCancellationPhase.COMMIT,
            action_id,
            raw=True,
        )
        return result.cancellation_requested

    async def _rollback(
        self,
        connection: aiosqlite.Connection,
        *,
        action_id: str,
        honor_cancellation: bool = False,
    ) -> None:
        result = await self._confirmed(
            connection.rollback(),
            StoreCancellationPhase.ROLLBACK,
            action_id,
            raw=True,
        )
        if result.cancellation_requested and honor_cancellation:
            raise _ActionCancelled(StoreCancellationPhase.ROLLBACK)

    async def _checkpoint(self, connection: aiosqlite.Connection) -> None:
        deadline = time.monotonic() + self._busy_retry_timeout
        while True:
            try:
                await self._fetchall_sql(
                    connection,
                    "PRAGMA wal_checkpoint(PASSIVE)",
                    action_base="pragma.writer.checkpoint",
                    phase=StoreCancellationPhase.CHECKPOINT,
                )
                return
            except sqlite3.OperationalError as error:
                if not _is_busy(error) or time.monotonic() >= deadline:
                    raise
                await self._busy_sleep(deadline)

    async def _busy_sleep(self, deadline: float) -> None:
        result = await self._confirmed(
            asyncio.sleep(
                min(
                    self._busy_retry_delay,
                    max(0.0, deadline - time.monotonic()),
                )
            ),
            StoreCancellationPhase.BUSY_RETRY,
            "retry.busy-sleep",
            raw=False,
        )
        if result.cancellation_requested:
            raise _ActionCancelled(StoreCancellationPhase.BUSY_RETRY)

    async def _install_connection_instrumentation(
        self,
        connection: aiosqlite.Connection,
        owner: str,
    ) -> None:
        if self._thread_probe is not None:
            probe = self._thread_probe

            def record(label: object) -> int:
                probe(f"{owner}:{label}", _thread_id())
                return 1

            create_result = await self._confirmed(
                cast(_InstrumentableConnection, connection).create_function(
                    "__token_learning_thread_probe",
                    1,
                    record,
                ),
                StoreCancellationPhase.PRAGMA,
                f"instrument.{owner}.thread-probe-install",
                raw=True,
            )
            if create_result.cancellation_requested:
                raise _ActionCancelled(StoreCancellationPhase.PRAGMA)
        if self._trace_callback is not None:
            trace_result = await self._confirmed(
                cast(_InstrumentableConnection, connection).set_trace_callback(
                    self._trace_callback
                ),
                StoreCancellationPhase.PRAGMA,
                f"instrument.{owner}.trace-install",
                raw=True,
            )
            if trace_result.cancellation_requested:
                raise _ActionCancelled(StoreCancellationPhase.PRAGMA)

    async def _probe_worker(
        self,
        connection: aiosqlite.Connection,
        label: str,
    ) -> None:
        if self._thread_probe is None:
            return
        row = await self._fetchone_sql(
            connection,
            "SELECT __token_learning_thread_probe(?)",
            (label,),
            action_base="instrument.worker-probe",
        )
        if row != (1,):
            raise LearningStoreError("SQLite worker probe did not run")

    async def _configure_connection(
        self,
        connection: aiosqlite.Connection,
        *,
        query_only: bool,
    ) -> None:
        role = "reader" if query_only else "writer"
        await self._execute_sql(
            connection,
            "PRAGMA foreign_keys=ON",
            phase=StoreCancellationPhase.PRAGMA,
            action_base=f"pragma.{role}.foreign-keys-set",
        )
        await self._execute_sql(
            connection,
            "PRAGMA busy_timeout=0",
            phase=StoreCancellationPhase.PRAGMA,
            action_base=f"pragma.{role}.busy-timeout-set",
        )
        await self._execute_sql(
            connection,
            "PRAGMA synchronous=NORMAL",
            phase=StoreCancellationPhase.PRAGMA,
            action_base=f"pragma.{role}.synchronous-set",
        )
        if query_only:
            await self._execute_sql(
                connection,
                "PRAGMA query_only=ON",
                phase=StoreCancellationPhase.PRAGMA,
                action_base="pragma.reader.query-only-set",
            )
        foreign_keys = await self._fetchone_sql(
            connection,
            "PRAGMA foreign_keys",
            phase=StoreCancellationPhase.PRAGMA,
            action_base=f"pragma.{role}.foreign-keys-read",
        )
        if foreign_keys != (1,):
            raise LearningStoreStartupError(
                LearningStoreStartupReason.MIGRATION_FAILED
            )

    async def _inspect_existing_with_retry(self) -> None:
        deadline = time.monotonic() + self._busy_retry_timeout
        while True:
            try:
                await self._inspect_existing_read_only()
                return
            except sqlite3.OperationalError as error:
                if not _is_busy(error) or time.monotonic() >= deadline:
                    raise
                await self._busy_sleep(deadline)

    async def _inspect_existing_read_only(self) -> bool:
        connection: aiosqlite.Connection | None = None
        began = False
        committed = False
        empty = False
        try:
            connection = await self._open_connection(read_only=True, role="inspect")
            began = True
            await self._begin(
                connection,
                immediate=False,
                action_base="tx.inspect.begin",
            )
            quick_check = await self._fetchone_sql(
                connection,
                "PRAGMA quick_check",
                action_base="pragma.inspect.quick-check",
            )
            if quick_check != ("ok",):
                raise LearningStoreStartupError(LearningStoreStartupReason.CORRUPT)
            objects = await self._schema_objects(connection)
            empty = not objects
            if objects:
                await self._validate_schema(connection)
                await self._read_all_state(connection)
            commit_cancelled = await self._commit(
                connection,
                action_id="tx.inspect.commit",
            )
            committed = True
            if commit_cancelled:
                raise _ActionCancelled(StoreCancellationPhase.COMMIT)
            return empty
        except sqlite3.OperationalError as error:
            if began and not committed and connection is not None:
                await self._rollback(
                    connection,
                    action_id="tx.inspect.rollback",
                )
            if _is_busy(error):
                raise
            raise LearningStoreStartupError(
                LearningStoreStartupReason.CORRUPT
            ) from error
        except sqlite3.DatabaseError as error:
            if began and not committed and connection is not None:
                await self._rollback(
                    connection,
                    action_id="tx.inspect.rollback",
                )
            raise LearningStoreStartupError(
                LearningStoreStartupReason.CORRUPT
            ) from error
        except BaseException:
            if began and not committed and connection is not None:
                await self._rollback(
                    connection,
                    action_id="tx.inspect.rollback",
                )
            raise
        finally:
            if connection is not None:
                await self._close_connection(
                    connection,
                    role="inspect",
                )

    async def _open_writer_with_migration_retry(
        self,
    ) -> tuple[aiosqlite.Connection, ValidatedPersistentState, bool]:
        deadline = time.monotonic() + self._busy_retry_timeout
        while True:
            connection: aiosqlite.Connection | None = None
            began = False
            committed = False
            try:
                connection = await self._open_connection(
                    read_only=False,
                    role="writer",
                )
                await self._install_connection_instrumentation(connection, "writer")
                await self._configure_connection(connection, query_only=False)
                journal = await self._fetchone_sql(
                    connection,
                    "PRAGMA journal_mode=WAL",
                    phase=StoreCancellationPhase.PRAGMA,
                    action_base="pragma.writer.journal-mode-wal",
                )
                if journal is None or str(journal[0]).lower() != "wal":
                    raise LearningStoreStartupError(
                        LearningStoreStartupReason.MIGRATION_FAILED
                    )
                began = True
                await self._begin(
                    connection,
                    immediate=True,
                    action_base="tx.migration.begin",
                )
                objects = await self._schema_objects(connection)
                created = not objects
                if created:
                    for statement in CREATE_SCHEMA_STATEMENTS:
                        await self._execute_sql(
                            connection,
                            statement,
                            phase=StoreCancellationPhase.INSERT,
                            action_base="schema.create-statement",
                        )
                    await self._execute_sql(
                        connection,
                        "INSERT INTO schema_meta(singleton, version, manifest_digest, global_revision) VALUES (1, ?, ?, 0)",
                        (SCHEMA_VERSION, SCHEMA_MANIFEST_DIGEST),
                        phase=StoreCancellationPhase.INSERT,
                        action_base="schema.meta-insert",
                    )
                await self._validate_schema(connection)
                state = await self._read_all_state(connection)
                commit_cancelled = await self._commit(
                    connection,
                    action_id="tx.migration.commit",
                )
                committed = True
                if commit_cancelled:
                    raise _ActionCancelled(StoreCancellationPhase.COMMIT)
                return connection, state, created
            except sqlite3.OperationalError as error:
                if began and not committed and connection is not None:
                    await self._rollback(
                        connection,
                        action_id="tx.migration.rollback",
                    )
                if connection is not None:
                    await self._close_connection(
                        connection,
                        role="writer",
                        honor_cancellation=False,
                    )
                if not _is_busy(error) or time.monotonic() >= deadline:
                    raise
                if self._path.exists():
                    await self._inspect_existing_with_retry()
                await self._busy_sleep(deadline)
            except BaseException:
                if began and not committed and connection is not None:
                    await self._rollback(
                        connection,
                        action_id="tx.migration.rollback",
                    )
                if connection is not None:
                    await self._close_connection(
                        connection,
                        role="writer",
                        honor_cancellation=False,
                    )
                raise

    async def _schema_objects(
        self,
        connection: aiosqlite.Connection,
    ) -> tuple[_Row, ...]:
        return await self._fetchall_sql(
            connection,
            """
            SELECT type, name
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """,
            action_base="schema.objects-read",
        )

    async def _validate_schema(self, connection: aiosqlite.Connection) -> None:
        try:
            objects = await self._schema_objects(connection)
            if ("table", "schema_meta") not in objects:
                raise LearningStoreStartupError(
                    LearningStoreStartupReason.MANIFEST_MISMATCH
                )
            meta = await self._fetchall_sql(
                connection,
                "SELECT singleton, version, manifest_digest FROM schema_meta ORDER BY singleton",
                action_base="schema.meta-read",
            )
            if len(meta) != 1 or meta[0][0] != 1:
                raise LearningStoreStartupError(
                    LearningStoreStartupReason.MANIFEST_MISMATCH
                )
            if meta[0][1] != SCHEMA_VERSION:
                raise UnsupportedLearningSchemaError
            if meta[0][2] != SCHEMA_MANIFEST_DIGEST:
                raise LearningStoreStartupError(
                    LearningStoreStartupReason.MANIFEST_MISMATCH
                )
            expected_objects = tuple(
                sorted(
                    [("table", table.name) for table in V1_TABLES]
                    + [("index", index.name) for index in V1_INDEXES]
                )
            )
            if objects != expected_objects:
                raise LearningStoreStartupError(
                    LearningStoreStartupReason.MANIFEST_MISMATCH
                )
            table_list = await self._fetchall_sql(
                connection,
                "PRAGMA table_list",
                action_base="schema.table-list-read",
            )
            strict_by_name = {
                _as_str("table name", row[1]): bool(_as_int("strict", row[5]))
                for row in table_list
                if row[0] == "main" and not str(row[1]).startswith("sqlite_")
            }
            for expected in V1_TABLES:
                actual = await self._actual_table_manifest(
                    connection,
                    expected.name,
                    strict_by_name,
                )
                normalized_expected = replace(
                    expected,
                    checks=tuple(sorted(expected.checks)),
                    foreign_keys=tuple(
                        sorted(expected.foreign_keys, key=_foreign_key_sort_key)
                    ),
                )
                if actual != normalized_expected:
                    raise LearningStoreStartupError(
                        LearningStoreStartupReason.MANIFEST_MISMATCH
                    )
            actual_named_indexes: list[IndexManifest] = []
            for expected in V1_INDEXES:
                actual_named_indexes.append(
                    await self._actual_index_manifest(connection, expected.name)
                )
            if tuple(actual_named_indexes) != V1_INDEXES:
                raise LearningStoreStartupError(
                    LearningStoreStartupReason.MANIFEST_MISMATCH
                )
            foreign_key_errors = await self._fetchall_sql(
                connection,
                "PRAGMA foreign_key_check",
                action_base="schema.foreign-keys-read",
            )
            if foreign_key_errors:
                raise LearningStoreStartupError(
                    LearningStoreStartupReason.INVALID_STATE
                )
        except UnsupportedLearningSchemaError:
            raise
        except LearningStoreStartupError:
            raise
        except sqlite3.DatabaseError as error:
            raise LearningStoreStartupError(
                LearningStoreStartupReason.CORRUPT
            ) from error
        except Exception as error:
            raise LearningStoreStartupError(
                LearningStoreStartupReason.MANIFEST_MISMATCH
            ) from error

    async def _actual_table_manifest(
        self,
        connection: aiosqlite.Connection,
        table_name: str,
        strict_by_name: Mapping[str, bool],
    ) -> TableManifest:
        quoted = _quote_pragma_name(table_name)
        column_rows = await self._fetchall_sql(
            connection,
            f"PRAGMA table_xinfo({quoted})",
            action_base="schema.table-xinfo-read",
        )
        columns = tuple(
            ColumnManifest(
                name=_as_str("column name", row[1]),
                declared_type=_as_str("column type", row[2]).upper(),
                not_null=bool(_as_int("column notnull", row[3])),
                default=None if row[4] is None else _as_str("column default", row[4]),
                primary_key_position=_as_int("column pk", row[5]),
            )
            for row in column_rows
            if _as_int("column hidden", row[6]) == 0
        )
        sql_row = await self._fetchone_sql(
            connection,
            "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = ?",
            (table_name,),
            action_base="schema.table-ddl-read",
        )
        if sql_row is None:
            raise LearningStoreStartupError(
                LearningStoreStartupReason.MANIFEST_MISMATCH
            )
        checks = tuple(sorted(_extract_checks(_as_str("table sql", sql_row[0]))))
        foreign_key_rows = await self._fetchall_sql(
            connection,
            f"PRAGMA foreign_key_list({quoted})",
            action_base="schema.foreign-keys-read",
        )
        grouped: dict[int, list[_Row]] = defaultdict(list)
        for row in foreign_key_rows:
            grouped[_as_int("foreign key id", row[0])].append(row)
        foreign_keys = tuple(
            sorted(
                (
                    ForeignKeyManifest(
                        parent_table=_as_str("foreign key table", rows[0][2]),
                        from_columns=tuple(
                            _as_str("foreign key from", row[3])
                            for row in sorted(rows, key=lambda value: _as_int("foreign key seq", value[1]))
                        ),
                        to_columns=tuple(
                            _as_str("foreign key to", row[4])
                            for row in sorted(rows, key=lambda value: _as_int("foreign key seq", value[1]))
                        ),
                        on_update=_as_str("foreign key update", rows[0][5]),
                        on_delete=_as_str("foreign key delete", rows[0][6]),
                        match=_as_str("foreign key match", rows[0][7]),
                    )
                    for rows in grouped.values()
                ),
                key=_foreign_key_sort_key,
            )
        )
        normalized_ddl = _normalize_ddl_v1(_as_str("table sql", sql_row[0]))
        return TableManifest(
            name=table_name,
            columns=columns,
            checks=checks,
            foreign_keys=foreign_keys,
            strict=strict_by_name.get(table_name, False),
            ddl_digest=hashlib.sha256(normalized_ddl.encode("utf-8")).hexdigest(),
        )

    async def _actual_index_manifest(
        self,
        connection: aiosqlite.Connection,
        index_name: str,
    ) -> IndexManifest:
        row = await self._fetchone_sql(
            connection,
            "SELECT tbl_name FROM sqlite_schema WHERE type = 'index' AND name = ?",
            (index_name,),
            action_base="schema.index-list-read",
        )
        if row is None:
            raise LearningStoreStartupError(
                LearningStoreStartupReason.MANIFEST_MISMATCH
            )
        table = _as_str("index table", row[0])
        list_rows = await self._fetchall_sql(
            connection,
            f"PRAGMA index_list({_quote_pragma_name(table)})",
            action_base="schema.index-list-read",
        )
        list_row = next(
            (candidate for candidate in list_rows if candidate[1] == index_name),
            None,
        )
        if list_row is None:
            raise LearningStoreStartupError(
                LearningStoreStartupReason.MANIFEST_MISMATCH
            )
        xinfo = await self._fetchall_sql(
            connection,
            f"PRAGMA index_xinfo({_quote_pragma_name(index_name)})",
            action_base="schema.index-xinfo-read",
        )
        columns = tuple(
            IndexColumnManifest(
                name=_as_str("index column", value[2]),
                descending=bool(_as_int("index descending", value[3])),
                collation=_as_str("index collation", value[4]),
            )
            for value in sorted(xinfo, key=lambda candidate: _as_int("index seq", candidate[0]))
            if _as_int("index key", value[5]) == 1
        )
        return IndexManifest(
            name=index_name,
            table=table,
            unique=bool(_as_int("index unique", list_row[2])),
            columns=columns,
            partial=bool(_as_int("index partial", list_row[4])),
        )

    async def _read_validated_transaction(
        self,
        connection: aiosqlite.Connection,
    ) -> ValidatedPersistentState:
        began = False
        committed = False
        try:
            began = True
            await self._begin(
                connection,
                immediate=False,
                action_base="tx.refresh.begin",
            )
            state = await self._read_all_state(connection)
            commit_cancelled = await self._commit(
                connection,
                action_id="tx.refresh.commit",
            )
            committed = True
            if commit_cancelled:
                raise _ActionCancelled(StoreCancellationPhase.COMMIT)
            return state
        except BaseException:
            if began and not committed:
                await self._rollback(
                    connection,
                    action_id="tx.refresh.rollback",
                )
            raise

    async def _read_all_state(
        self,
        connection: aiosqlite.Connection,
        *,
        enforce_bounds: bool = True,
    ) -> ValidatedPersistentState:
        meta = await self._fetchall_sql(
            connection,
            "SELECT singleton, version, manifest_digest, global_revision FROM schema_meta ORDER BY singleton",
            action_base="state.schema-meta-read",
        )
        identities = await self._fetchall_sql(
            connection,
            _IDENTITIES_SQL,
            action_base="state.identities-read",
        )
        if self._reader_step_hook is not None:
            await self._reader_step_hook("after-identities")
        epochs = await self._fetchall_sql(
            connection,
            _EPOCHS_SQL,
            action_base="state.epochs-read",
        )
        samples = await self._fetchall_sql(
            connection,
            _SAMPLES_SQL,
            action_base="state.samples-read",
        )
        prediction_records = await self._fetchall_sql(
            connection,
            _PREDICTION_RECORDS_SQL,
            action_base="state.prediction-records-read",
        )
        evaluations = await self._fetchall_sql(
            connection,
            _EVALUATIONS_SQL,
            action_base="state.evaluations-read",
        )
        exact_anchors = await self._fetchall_sql(
            connection,
            _EXACT_ANCHORS_SQL,
            action_base="state.exact-anchors-read",
        )
        prefix_anchors = await self._fetchall_sql(
            connection,
            _PREFIX_ANCHORS_SQL,
            action_base="state.prefix-anchors-read",
        )
        prefix_checkpoints = await self._fetchall_sql(
            connection,
            _PREFIX_CHECKPOINTS_SQL,
            action_base="state.prefix-checkpoints-read",
        )
        events = await self._fetchall_sql(
            connection,
            _EVENTS_SQL,
            action_base="state.events-read",
        )
        rows = _AllRows(
            meta=meta,
            identities=identities,
            epochs=epochs,
            samples=samples,
            prediction_records=prediction_records,
            evaluations=evaluations,
            exact_anchors=exact_anchors,
            prefix_anchors=prefix_anchors,
            prefix_checkpoints=prefix_checkpoints,
            events=events,
        )
        try:
            return await self._run_cpu(
                _decode_persistent_state,
                rows,
                self._limits,
                enforce_bounds,
                phase=StoreCancellationPhase.READ,
                action_id="cpu.state-decode",
            )
        except LearningStoreStartupError:
            raise
        except Exception as error:
            raise LearningStoreStartupError(
                LearningStoreStartupReason.INVALID_STATE
            ) from error

    async def _read_data_version(self, connection: aiosqlite.Connection) -> int:
        row = await self._fetchone_sql(
            connection,
            "PRAGMA data_version",
            phase=StoreCancellationPhase.PRAGMA,
            action_base="pragma.reader.data-version",
        )
        if row is None:
            raise LearningStoreError("SQLite did not return data_version")
        return _as_int("data_version", row[0])

    async def _apply_with_retry(
        self,
        analyzed_sample: StoredSample,
        transition: Transition,
    ) -> LearningApplyResult:
        deadline = time.monotonic() + self._busy_retry_timeout
        while True:
            try:
                return await self._apply_once(analyzed_sample, transition)
            except sqlite3.OperationalError as error:
                if not _is_busy(error) or time.monotonic() >= deadline:
                    raise
                await self._busy_sleep(deadline)

    async def _apply_once(
        self,
        analyzed_sample: StoredSample,
        transition: Transition,
    ) -> LearningApplyResult:
        writer = self._require_writer()
        began = False
        committed = False
        final_result: LearningApplyResult | None = None
        try:
            began = True
            await self._begin(
                writer,
                immediate=True,
                action_base="tx.apply.begin",
            )
            await self._probe_worker(writer, "apply")
            duplicate = await self._fetchone_sql(
                writer,
                """
                SELECT identity_id, epoch
                FROM samples
                WHERE process_boot_id = ? AND request_id = ? AND attempt_index = ?
                """,
                analyzed_sample.sample_key,
                action_base="apply.duplicate-read",
            )
            if duplicate is not None:
                final_result = await self._record_duplicate_locked(
                    writer,
                    analyzed_sample.sample_key,
                    _as_int("identity_id", duplicate[0]),
                    _as_int("sample epoch", duplicate[1]),
                )
                final_state = await self._read_all_state(writer)
                commit_cancelled = await self._commit(
                    writer,
                    action_id="tx.apply.commit",
                )
                committed = True
                self._publish_state(final_state)
                if commit_cancelled:
                    raise StoreOperationCancelled(
                        StoreCancellationPhase.COMMIT,
                        final_result.observation,
                    )
                return final_result
            before_state = await self._read_all_state(writer)
            identity_state = _find_identity(before_state, analyzed_sample.identity)
            if identity_state is None:
                identity_id = await self._ensure_identity(
                    writer,
                    analyzed_sample.identity,
                )
                identity_state = _IdentityState(
                    identity_id=identity_id,
                    identity=analyzed_sample.identity,
                    revision=0,
                )
                snapshot = _empty_snapshot(analyzed_sample.identity)
            else:
                snapshot = before_state.snapshot(analyzed_sample.identity)
            next_global_revision = before_state.global_revision + 1
            try:
                prepared = await self._run_cpu(
                    _run_and_prepare_transition,
                    transition,
                    snapshot,
                    analyzed_sample,
                    next_global_revision,
                    phase=StoreCancellationPhase.TRANSITION,
                    action_id="cpu.transition",
                )
            except _ActionCancelled:
                raise
            except Exception as error:
                raise LearningStoreTransitionError(
                    "learning transition failed"
                ) from error
            checkpoint_outcome = await self._insert_update_locked(
                writer,
                identity_state.identity_id,
                snapshot,
                before_state,
                prepared,
                next_global_revision,
            )
            transition_state = await self._read_all_state(
                writer,
                enforce_bounds=False,
            )
            prune_plan = _compute_prune_plan(transition_state, self._limits)
            pruned_sample_owners = set(prune_plan.sample_owners)
            remaining_events = tuple(
                event
                for event in transition_state.events
                if _event_owner_key(event) not in pruned_sample_owners
            )
            sample_owner = (
                identity_state.identity_id,
                prepared.update.sample.identity.learning_epoch,
                *prepared.update.sample.sample_key,
            )
            sample_will_exist = sample_owner not in pruned_sample_owners
            identity_will_exist = sample_will_exist or any(
                sample.identity_id == identity_state.identity_id
                and sample.owner_key not in pruned_sample_owners
                for sample in transition_state.samples
            ) or any(
                event.identity_id == identity_state.identity_id
                for event in remaining_events
            )
            transition_identity = next(
                candidate
                for candidate in transition_state.identities
                if candidate.identity_id == identity_state.identity_id
            )
            planned_event_epoch = (
                prepared.update.sample.identity.learning_epoch
                if sample_will_exist
                else transition_identity.identity.learning_epoch
            )
            planned_event_identity: LearningIdentity | UnresolvedLearningIdentity
            if identity_will_exist:
                planned_event_identity = replace(
                    prepared.update.sample.identity,
                    learning_epoch=planned_event_epoch,
                )
            else:
                planned_event_identity = _unresolved_from_identity(
                    prepared.update.sample.identity
                )
            planned_bucket = (
                _identity_bucket_key(planned_event_identity)
                if isinstance(planned_event_identity, LearningIdentity)
                else _unresolved_bucket_key(planned_event_identity)
            )
            event_victim_ids = _compute_event_victim_ids(
                remaining_events,
                self._limits,
                new_bucket=planned_bucket,
            )
            affected = set(prune_plan.affected_identity_ids)
            affected.add(identity_state.identity_id)
            affected.update(
                event.identity_id
                for event in remaining_events
                if event.event_id in event_victim_ids
                and event.identity_id is not None
            )
            await self._increment_revisions_before_delete(
                writer,
                affected,
                next_global_revision,
            )
            await self._apply_prune_plan(writer, prune_plan)
            await self._delete_empty_metadata(writer)
            current_row = await self._fetchone_sql(
                writer,
                "SELECT revision, active_epoch FROM identity_state WHERE identity_id = ?",
                (identity_state.identity_id,),
                action_base="identity.revision-read",
            )
            sample_exists = await self._sample_exists(
                writer,
                identity_state.identity_id,
                prepared.update.sample.identity.learning_epoch,
                prepared.update.sample.sample_key,
            )
            final_observation = TokenLearningObservation(
                sample_key=prepared.update.sample.sample_key,
                outcome="committed",
                reason_code=LearningReasonCode.SAMPLE_COMMITTED,
                metadata=SampleCommittedMetadata(
                    prepared.update.sample.actual_input_tokens
                ),
                prefix_checkpoint_outcome=checkpoint_outcome,
                evaluations=prepared.update.evaluations,
                revision=snapshot.revision + 1,
                learning_epoch=prepared.update.sample.identity.learning_epoch,
                drift=prepared.update.drift,
            )
            event_identity: LearningIdentity | UnresolvedLearningIdentity
            event_identity_id: int | None
            event_epoch: int | None
            event_sample_key: SampleKey | None
            if current_row is None:
                final_observation = _pruned_observation(
                    prepared.update,
                    snapshot.revision + 1,
                    checkpoint_outcome,
                )
                event_identity = _unresolved_from_identity(
                    prepared.update.sample.identity
                )
                event_identity_id = None
                event_epoch = None
                event_sample_key = None
            else:
                revision = _as_int("revision", current_row[0])
                active_epoch = _as_int("active epoch", current_row[1])
                if sample_exists:
                    final_observation = replace(
                        final_observation,
                        revision=revision,
                        learning_epoch=prepared.update.sample.identity.learning_epoch,
                    )
                    event_sample_key = prepared.update.sample.sample_key
                    event_epoch = prepared.update.sample.identity.learning_epoch
                else:
                    final_observation = _pruned_observation(
                        prepared.update,
                        revision,
                        checkpoint_outcome,
                    )
                    event_sample_key = None
                    event_epoch = active_epoch
                event_identity = replace(
                    prepared.update.sample.identity,
                    learning_epoch=event_epoch,
                )
                event_identity_id = identity_state.identity_id
            await self._insert_event_locked(
                writer,
                final_observation,
                identity=event_identity,
                identity_id=event_identity_id,
                learning_epoch=event_epoch,
                sample_key=event_sample_key,
            )
            await self._delete_event_ids(writer, event_victim_ids)
            await self._delete_empty_metadata(writer)
            final_state = await self._read_all_state(writer)
            final_snapshot = final_state.snapshot(prepared.update.sample.identity)
            final_result = LearningApplyResult(
                observation=final_observation,
                snapshot=final_snapshot,
            )
            commit_cancelled = await self._commit(
                writer,
                action_id="tx.apply.commit",
            )
            committed = True
            self._publish_state(final_state)
            if commit_cancelled:
                raise StoreOperationCancelled(
                    StoreCancellationPhase.COMMIT,
                    final_observation,
                )
            return final_result
        except StoreOperationCancelled:
            raise
        except _ActionCancelled as cancelled:
            if began and not committed:
                await self._rollback(
                    writer,
                    action_id="tx.apply.rollback",
                )
            raise _public_cancellation(cancelled) from cancelled.action_error
        except BaseException:
            if began and not committed:
                await self._rollback(
                    writer,
                    action_id="tx.apply.rollback",
                )
            raise

    async def _record_duplicate_locked(
        self,
        connection: aiosqlite.Connection,
        sample_key: SampleKey,
        identity_id: int,
        sample_epoch: int,
    ) -> LearningApplyResult:
        state = await self._read_all_state(connection)
        identity_state = next(
            (
                candidate
                for candidate in state.identities
                if candidate.identity_id == identity_id
            ),
            None,
        )
        if identity_state is None:
            raise LearningStoreError("duplicate sample identity is absent")
        observation = TokenLearningObservation(
            sample_key=sample_key,
            outcome="duplicate",
            reason_code=LearningReasonCode.DUPLICATE_SAMPLE,
            metadata=DuplicateSampleMetadata(identity_state.revision),
            prefix_checkpoint_outcome=PrefixCheckpointNotAttempted(
                PrefixCheckpointNotAttemptedReason.DUPLICATE_SAMPLE
            ),
            revision=identity_state.revision,
            learning_epoch=sample_epoch,
        )
        await self._insert_event_locked(
            connection,
            observation,
            identity=replace(identity_state.identity, learning_epoch=sample_epoch),
            identity_id=identity_id,
            learning_epoch=sample_epoch,
            sample_key=sample_key,
        )
        await self._prune_events_locked(connection)
        await self._delete_empty_metadata(connection)
        return LearningApplyResult(
            observation=observation,
            snapshot=state.snapshot(identity_state.identity),
        )

    async def _ensure_identity(
        self,
        connection: aiosqlite.Connection,
        identity: LearningIdentity,
    ) -> int:
        row = await self._fetchone_sql(
            connection,
            _FETCH_IDENTITY_ID_SQL,
            _identity_key(identity),
            action_base="identity.lookup",
        )
        if row is not None:
            return _as_int("identity_id", row[0])
        inserted = await self._fetchone_sql(
            connection,
            """
            INSERT INTO identity_state(
                actual_provider,
                resolved_model,
                endpoint,
                wire_format,
                tokenizer,
                descriptor_fingerprint,
                estimator_generation,
                profile_schema_revision,
                active_epoch,
                revision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            RETURNING identity_id
            """,
            (*_identity_key(identity), identity.learning_epoch),
            phase=StoreCancellationPhase.INSERT,
            action_base="identity.insert-returning",
        )
        if inserted is None:
            raise LearningStoreError("identity insert did not return an identifier")
        identity_id = _as_int("identity_id", inserted[0])
        global_revision = await self._current_global_revision(connection)
        await self._execute_sql(
            connection,
            "INSERT INTO epoch_state(identity_id, epoch, created_order) VALUES (?, ?, ?)",
            (identity_id, identity.learning_epoch, global_revision),
            phase=StoreCancellationPhase.INSERT,
            action_base="epoch.owner-insert",
        )
        return identity_id

    async def _insert_update_locked(
        self,
        connection: aiosqlite.Connection,
        identity_id: int,
        snapshot: LearningSnapshot,
        before_state: ValidatedPersistentState,
        prepared: _PreparedUpdate,
        insertion_order: int,
    ) -> PrefixCheckpointStoreOutcome:
        update = prepared.update
        sample = update.sample
        sample_epoch = sample.identity.learning_epoch
        prediction_epoch = update.prediction_record.selected.learning_epoch
        await self._execute_sql(
            connection,
            "INSERT OR IGNORE INTO epoch_state(identity_id, epoch, created_order) VALUES (?, ?, ?)",
            (identity_id, sample_epoch, insertion_order),
            phase=StoreCancellationPhase.INSERT,
            action_base="epoch.sample-insert",
        )
        await self._execute_sql(
            connection,
            "INSERT OR IGNORE INTO epoch_state(identity_id, epoch, created_order) VALUES (?, ?, ?)",
            (identity_id, prediction_epoch, snapshot.revision),
            phase=StoreCancellationPhase.INSERT,
            action_base="epoch.prediction-insert",
        )
        if update.drift is not None:
            await self._execute_sql(
                connection,
                "UPDATE identity_state SET active_epoch = ? WHERE identity_id = ?",
                (sample_epoch, identity_id),
                phase=StoreCancellationPhase.UPDATE,
                action_base="identity.active-epoch-update",
            )
        await self._execute_sql(
            connection,
            """
            INSERT INTO samples(
                identity_id,
                epoch,
                process_boot_id,
                request_id,
                attempt_index,
                observed_at_us,
                actual_input_tokens,
                last_used_order,
                raw_body_sha256,
                feature_raw_body_sha256,
                known_tokens,
                capability_visual_tokens,
                components_json,
                profile_key_json,
                profile_key_hash,
                feature_vector_json,
                full_fingerprint,
                context_fingerprint,
                prefix_fingerprints_json,
                low_confidence_reasons_json,
                committed_order,
                fixed_context_contribution_json,
                input_item_contributions_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity_id,
                sample_epoch,
                sample.sample_key[0],
                sample.sample_key[1],
                sample.sample_key[2],
                sample.observed_at_us,
                sample.actual_input_tokens,
                insertion_order,
                sample.raw_body_sha256,
                sample.features.raw_sent_body_sha256,
                sample.features.known_tokens,
                sample.features.capability_visual_tokens,
                prepared.sample.components_json,
                prepared.sample.profile_key_json,
                prepared.sample.profile_key_hash,
                prepared.sample.feature_vector_json,
                sample.features.full_fingerprint,
                sample.features.context_fingerprint,
                prepared.sample.prefix_fingerprints_json,
                prepared.sample.low_confidence_reasons_json,
                sample.committed_order,
                prepared.sample.fixed_context_contribution_json,
                prepared.sample.input_item_contributions_json,
            ),
            phase=StoreCancellationPhase.INSERT,
            action_base="sample.insert",
        )
        record = update.prediction_record
        await self._execute_sql(
            connection,
            """
            INSERT INTO prediction_records(
                identity_id,
                sample_epoch,
                process_boot_id,
                request_id,
                attempt_index,
                prediction_epoch,
                profile_key_hash,
                selected_method,
                selected_variant,
                history_revision,
                method_champions_json,
                candidates_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity_id,
                sample_epoch,
                sample.sample_key[0],
                sample.sample_key[1],
                sample.sample_key[2],
                prediction_epoch,
                prepared.sample.profile_key_hash,
                record.selected_key.method.value,
                record.selected_key.variant.value,
                record.selected.history_revision,
                prepared.method_champions_json,
                prepared.candidates_json,
            ),
            phase=StoreCancellationPhase.INSERT,
            action_base="prediction-record.insert",
        )
        for ordinal, evaluation in enumerate(update.evaluations):
            await self._execute_sql(
                connection,
                """
                INSERT INTO evaluations(
                    identity_id,
                    sample_epoch,
                    process_boot_id,
                    request_id,
                    attempt_index,
                    method,
                    candidate_variant,
                    prediction_epoch,
                    profile_key_hash,
                    ordinal,
                    predicted_tokens,
                    actual_tokens,
                    absolute_error,
                    signed_relative_error,
                    absolute_percentage_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity_id,
                    sample_epoch,
                    sample.sample_key[0],
                    sample.sample_key[1],
                    sample.sample_key[2],
                    evaluation.method.value,
                    evaluation.candidate_key.variant.value,
                    prediction_epoch,
                    prepared.sample.profile_key_hash,
                    ordinal,
                    evaluation.predicted_tokens,
                    evaluation.actual_tokens,
                    evaluation.absolute_error,
                    evaluation.signed_relative_error,
                    evaluation.absolute_percentage_error,
                ),
                phase=StoreCancellationPhase.INSERT,
                action_base="evaluation.insert",
            )
        await self._execute_sql(
            connection,
            """
            INSERT INTO exact_anchors(
                identity_id,
                epoch,
                process_boot_id,
                request_id,
                attempt_index,
                full_fingerprint,
                actual_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity_id,
                sample_epoch,
                sample.sample_key[0],
                sample.sample_key[1],
                sample.sample_key[2],
                sample.features.full_fingerprint,
                sample.actual_input_tokens,
            ),
            phase=StoreCancellationPhase.INSERT,
            action_base="exact-anchor.insert",
        )
        if sample.features.prefix_fingerprints:
            prefix = sample.features.prefix_fingerprints[-1]
            await self._execute_sql(
                connection,
                """
                INSERT INTO prefix_anchors(
                    identity_id,
                    epoch,
                    process_boot_id,
                    request_id,
                    attempt_index,
                    context_fingerprint,
                    item_count,
                    prefix_fingerprint,
                    actual_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity_id,
                    sample_epoch,
                    sample.sample_key[0],
                    sample.sample_key[1],
                    sample.sample_key[2],
                    sample.features.context_fingerprint,
                    prefix.item_count,
                    prefix.digest,
                    sample.actual_input_tokens,
                ),
                phase=StoreCancellationPhase.INSERT,
                action_base="prefix-anchor.insert",
            )
        return await self._apply_prefix_checkpoint_command(
            connection,
            identity_id,
            sample_epoch,
            before_state,
            update.prefix_checkpoint_command,
            state_revision=snapshot.revision + 1,
            updated_order=insertion_order,
        )

    async def _apply_prefix_checkpoint_command(
        self,
        connection: aiosqlite.Connection,
        identity_id: int,
        epoch: int,
        before_state: ValidatedPersistentState,
        command: PrefixCheckpointCommand,
        *,
        state_revision: int,
        updated_order: int,
    ) -> PrefixCheckpointStoreOutcome:
        # A checkpoint never survives after its epoch leaves the active identity
        # state. This is deliberately independent of sample cascades.
        await self._execute_sql(
            connection,
            """
            DELETE FROM prefix_checkpoints
            WHERE EXISTS (
                SELECT 1 FROM identity_state
                WHERE identity_state.identity_id = prefix_checkpoints.identity_id
                  AND identity_state.active_epoch != prefix_checkpoints.epoch
            )
            """,
            phase=StoreCancellationPhase.UPDATE,
            action_base="prefix-checkpoint.delete",
        )
        if isinstance(command, NoPrefixCheckpointChange):
            return command
        profile_json = _encode_json(
            _profile_payload(command.profile_key), "prefix checkpoint profile"
        )
        profile_hash = hashlib.sha256(profile_json.encode("utf-8")).hexdigest()
        existing = await self._fetchone_sql(
            connection,
            """
            SELECT state_revision FROM prefix_checkpoints
            WHERE identity_id = ? AND epoch = ? AND profile_key_json = ?
            """,
            (identity_id, epoch, profile_json),
            action_base="state.prefix-checkpoints-read",
        )
        actual_revision = (
            None if existing is None else _as_positive_int("prefix checkpoint state revision", existing[0])
        )
        if isinstance(command, ReplacePrefixCheckpoint):
            if actual_revision != command.expected_prior_state_revision:
                raise LearningStoreTransitionError("prefix checkpoint expected revision does not match")
            evidence = cast(tuple[PrefixChampionErrorTriple, ...], command.evidence)
            evidence_json = _encode_json(
                [
                    [
                        item.prefix_absolute_percentage_error,
                        item.profile_absolute_percentage_error,
                        item.cold_start_absolute_percentage_error,
                        item.committed_order,
                    ]
                    for item in evidence
                ],
                "prefix checkpoint evidence",
            )
            await self._execute_sql(
                connection,
                """
                INSERT INTO prefix_checkpoints(
                    identity_id, epoch, profile_key_json, profile_key_hash, mode,
                    evidence_json, state_revision, updated_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity_id, epoch, profile_key_json) DO UPDATE SET
                    profile_key_hash = excluded.profile_key_hash,
                    mode = excluded.mode,
                    evidence_json = excluded.evidence_json,
                    state_revision = excluded.state_revision,
                    updated_order = excluded.updated_order
                """,
                (
                    identity_id,
                    epoch,
                    profile_json,
                    profile_hash,
                    command.mode.value,
                    evidence_json,
                    state_revision,
                    updated_order,
                ),
                phase=StoreCancellationPhase.INSERT,
                action_base="prefix-checkpoint.upsert",
            )
            if actual_revision is None:
                active_before = {
                    (identity.identity_id, identity.identity.learning_epoch)
                    for identity in before_state.identities
                }
                prior_active = tuple(
                    checkpoint
                    for checkpoint in before_state.prefix_checkpoints
                    if (checkpoint.identity_id, checkpoint.epoch) in active_before
                )
                prior_identity_count = sum(
                    checkpoint.identity_id == identity_id and checkpoint.epoch == epoch
                    for checkpoint in prior_active
                )
                over_identity = prior_identity_count + 1 > self._limits.prefix_checkpoints_per_identity
                over_global = len(prior_active) + 1 > self._limits.prefix_checkpoints_global
                if over_identity or over_global:
                    if over_global and prior_identity_count == 0:
                        await self._execute_sql(
                            connection,
                            """
                            DELETE FROM prefix_checkpoints
                            WHERE identity_id = ? AND epoch = ? AND profile_key_json = ?
                            """,
                            (identity_id, epoch, profile_json),
                            phase=StoreCancellationPhase.UPDATE,
                            action_base="prefix-checkpoint.delete",
                        )
                        return PrefixCheckpointCapacityRejected(
                            command.profile_key,
                            PrefixCheckpointCapacityReason.PREFIX_CHECKPOINT_CAPACITY,
                        )
                    await self._execute_sql(
                        connection,
                        "DELETE FROM prefix_checkpoints WHERE identity_id = ? AND epoch = ?",
                        (identity_id, epoch),
                        phase=StoreCancellationPhase.UPDATE,
                        action_base="prefix-checkpoint.delete",
                    )
                    next_epoch = epoch + 1
                    await self._execute_sql(
                        connection,
                        "INSERT OR IGNORE INTO epoch_state(identity_id, epoch, created_order) VALUES (?, ?, ?)",
                        (identity_id, next_epoch, updated_order),
                        phase=StoreCancellationPhase.INSERT,
                        action_base="epoch.owner-insert",
                    )
                    await self._execute_sql(
                        connection,
                        "UPDATE identity_state SET active_epoch = ? WHERE identity_id = ?",
                        (next_epoch, identity_id),
                        phase=StoreCancellationPhase.UPDATE,
                        action_base="identity.active-epoch-update",
                    )
                    return PrefixCheckpointCapacityRolledOver(
                        command.profile_key,
                        epoch,
                        next_epoch,
                        PrefixCheckpointCapacityReason.PREFIX_CHECKPOINT_CAPACITY,
                    )
            return PrefixCheckpointApplied(command.profile_key, state_revision, updated_order)
        if actual_revision != command.expected_prior_state_revision:
            raise LearningStoreTransitionError("prefix checkpoint expected revision does not match")
        await self._execute_sql(
            connection,
            """
            DELETE FROM prefix_checkpoints
            WHERE identity_id = ? AND epoch = ? AND profile_key_json = ?
            """,
            (identity_id, epoch, profile_json),
            phase=StoreCancellationPhase.UPDATE,
            action_base="prefix-checkpoint.delete",
        )
        return PrefixCheckpointDeleted(command.profile_key, state_revision, updated_order)

    async def _increment_revisions_before_delete(
        self,
        connection: aiosqlite.Connection,
        identity_ids: Iterable[int],
        new_global_revision: int,
    ) -> None:
        identifiers = tuple(sorted(set(identity_ids)))
        for chunk in _chunks(identifiers, _SQLITE_PARAMETER_CHUNK):
            placeholders = ", ".join("?" for _ in chunk)
            await self._execute_sql(
                connection,
                f"UPDATE identity_state SET revision = revision + 1 WHERE identity_id IN ({placeholders})",
                chunk,
                phase=StoreCancellationPhase.UPDATE,
                action_base="identity.revision-update",
            )
        await self._execute_sql(
            connection,
            "UPDATE schema_meta SET global_revision = ? WHERE singleton = 1",
            (new_global_revision,),
            phase=StoreCancellationPhase.UPDATE,
            action_base="global-revision.update",
        )

    async def _apply_prune_plan(
        self,
        connection: aiosqlite.Connection,
        plan: _PrunePlan,
    ) -> None:
        for owner in plan.sample_owners:
            await self._execute_sql(
                connection,
                """
                DELETE FROM samples
                WHERE identity_id = ? AND epoch = ?
                  AND process_boot_id = ? AND request_id = ? AND attempt_index = ?
                """,
                owner,
                phase=StoreCancellationPhase.UPDATE,
                action_base="sample.delete",
            )
        for owner, candidate_key in plan.evaluation_keys:
            await self._execute_sql(
                connection,
                """
                DELETE FROM evaluations
                WHERE identity_id = ? AND sample_epoch = ?
                  AND process_boot_id = ? AND request_id = ? AND attempt_index = ?
                  AND method = ? AND candidate_variant = ?
                """,
                (*owner, candidate_key.method.value, candidate_key.variant.value),
                phase=StoreCancellationPhase.UPDATE,
                action_base="evaluation.delete",
            )

    async def _delete_empty_metadata(self, connection: aiosqlite.Connection) -> None:
        await self._execute_sql(
            connection,
            """
            DELETE FROM epoch_state
            WHERE epoch != (
                SELECT active_epoch
                FROM identity_state
                WHERE identity_state.identity_id = epoch_state.identity_id
            )
              AND NOT EXISTS (
                  SELECT 1 FROM samples
                  WHERE samples.identity_id = epoch_state.identity_id
                    AND samples.epoch = epoch_state.epoch
              )
              AND NOT EXISTS (
                  SELECT 1 FROM prediction_records
                  WHERE prediction_records.identity_id = epoch_state.identity_id
                    AND prediction_records.prediction_epoch = epoch_state.epoch
              )
              AND NOT EXISTS (
                  SELECT 1 FROM evaluations
                  WHERE evaluations.identity_id = epoch_state.identity_id
                    AND evaluations.prediction_epoch = epoch_state.epoch
              )
              AND NOT EXISTS (
                  SELECT 1 FROM learning_events
                  WHERE learning_events.identity_id = epoch_state.identity_id
                    AND learning_events.learning_epoch = epoch_state.epoch
              )
            """,
            phase=StoreCancellationPhase.UPDATE,
            action_base="epoch.empty-delete",
        )
        await self._execute_sql(
            connection,
            """
            DELETE FROM identity_state
            WHERE NOT EXISTS (
                SELECT 1 FROM samples
                WHERE samples.identity_id = identity_state.identity_id
            )
              AND NOT EXISTS (
                SELECT 1 FROM learning_events
                WHERE learning_events.identity_id = identity_state.identity_id
            )
            """,
            phase=StoreCancellationPhase.UPDATE,
            action_base="identity.empty-delete",
        )

    async def _sample_exists(
        self,
        connection: aiosqlite.Connection,
        identity_id: int,
        epoch: int,
        sample_key: SampleKey,
    ) -> bool:
        row = await self._fetchone_sql(
            connection,
            """
            SELECT 1 FROM samples
            WHERE identity_id = ? AND epoch = ?
              AND process_boot_id = ? AND request_id = ? AND attempt_index = ?
            """,
            (identity_id, epoch, *sample_key),
            action_base="sample.exists",
        )
        return row == (1,)

    async def _insert_event_locked(
        self,
        connection: aiosqlite.Connection,
        observation: TokenLearningObservation,
        *,
        identity: LearningIdentity | UnresolvedLearningIdentity,
        identity_id: int | None,
        learning_epoch: int | None,
        sample_key: SampleKey | None,
    ) -> None:
        _validate_observation_for_storage(observation)
        metadata_json = _encode_learning_metadata(
            observation.reason_code,
            observation.metadata,
        )
        drift_reason: str | None = None
        drift_metadata: str | None = None
        if observation.drift is not None:
            drift_reason = observation.drift.reason_code.value
            drift_metadata = _encode_drift_metadata(observation.drift)
        if isinstance(identity, LearningIdentity):
            bucket_key = _identity_bucket_key(identity)
            unresolved = (None, None, None)
        else:
            bucket_key = _unresolved_bucket_key(identity)
            unresolved = (
                identity.actual_provider,
                identity.endpoint,
                identity.estimator_generation,
            )
        sample_columns: tuple[object | None, object | None, object | None] = (
            (None, None, None) if sample_key is None else sample_key
        )
        await self._execute_sql(
            connection,
            """
            INSERT INTO learning_events(
                identity_id,
                learning_epoch,
                sample_process_boot_id,
                sample_request_id,
                sample_attempt_index,
                bucket_key,
                process_boot_id,
                request_id,
                attempt_index,
                outcome,
                reason_code,
                metadata_json,
                prefix_checkpoint_outcome_json,
                revision,
                drift_reason_code,
                drift_metadata_json,
                evaluations_json,
                unresolved_provider,
                unresolved_endpoint,
                unresolved_generation,
                created_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity_id,
                learning_epoch,
                *sample_columns,
                bucket_key,
                observation.sample_key[0],
                observation.sample_key[1],
                observation.sample_key[2],
                observation.outcome,
                observation.reason_code.value,
                metadata_json,
                _encode_prefix_checkpoint_outcome(observation.prefix_checkpoint_outcome),
                observation.revision,
                drift_reason,
                drift_metadata,
                _encode_evaluations(observation.evaluations),
                *unresolved,
                self._clock(),
            ),
            phase=StoreCancellationPhase.INSERT,
            action_base="event.insert",
        )

    async def _delete_event_ids(
        self,
        connection: aiosqlite.Connection,
        event_ids: Iterable[int],
    ) -> None:
        identifiers = tuple(sorted(set(event_ids)))
        for chunk in _chunks(identifiers, _SQLITE_PARAMETER_CHUNK):
            placeholders = ", ".join("?" for _ in chunk)
            await self._execute_sql(
                connection,
                f"DELETE FROM learning_events WHERE event_id IN ({placeholders})",
                chunk,
                phase=StoreCancellationPhase.UPDATE,
                action_base="event.ids-delete",
            )

    async def _prune_events_locked(self, connection: aiosqlite.Connection) -> None:
        await self._execute_sql(
            connection,
            """
            DELETE FROM learning_events
            WHERE event_id IN (
                SELECT event_id
                FROM (
                    SELECT
                        event_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY bucket_key
                            ORDER BY event_id DESC
                        ) AS retained_rank
                    FROM learning_events
                )
                WHERE retained_rank > ?
            )
            """,
            (self._limits.events_per_identity,),
            phase=StoreCancellationPhase.UPDATE,
            action_base="event.bucket-prune",
        )
        await self._execute_sql(
            connection,
            """
            DELETE FROM learning_events
            WHERE event_id IN (
                SELECT event_id
                FROM learning_events
                ORDER BY event_id DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self._limits.events_global,),
            phase=StoreCancellationPhase.UPDATE,
            action_base="event.global-prune",
        )

    async def _record_event_with_retry(
        self,
        observation: TokenLearningObservation,
        identity: LearningIdentity | UnresolvedLearningIdentity,
    ) -> None:
        deadline = time.monotonic() + self._busy_retry_timeout
        while True:
            try:
                await self._record_event_once(observation, identity)
                return
            except sqlite3.OperationalError as error:
                if not _is_busy(error) or time.monotonic() >= deadline:
                    raise
                await self._busy_sleep(deadline)

    async def _record_event_once(
        self,
        observation: TokenLearningObservation,
        identity: LearningIdentity | UnresolvedLearningIdentity,
    ) -> None:
        writer = self._require_writer()
        began = False
        committed = False
        final_observation = observation
        try:
            began = True
            await self._begin(
                writer,
                immediate=True,
                action_base="tx.event.begin",
            )
            state = await self._read_all_state(writer)
            next_global = state.global_revision + 1
            event_bucket = (
                _identity_bucket_key(identity)
                if isinstance(identity, LearningIdentity)
                else _unresolved_bucket_key(identity)
            )
            event_victim_ids = _compute_event_victim_ids(
                state.events,
                self._limits,
                new_bucket=event_bucket,
            )
            affected = {
                event.identity_id
                for event in state.events
                if event.event_id in event_victim_ids
                and event.identity_id is not None
            }
            identity_id: int | None = None
            event_epoch: int | None = None
            if isinstance(identity, LearningIdentity):
                identity_id = await self._ensure_identity(writer, identity)
                affected.add(identity_id)
                event_epoch = identity.learning_epoch
                await self._execute_sql(
                    writer,
                    "INSERT OR IGNORE INTO epoch_state(identity_id, epoch, created_order) VALUES (?, ?, ?)",
                    (identity_id, event_epoch, next_global),
                    phase=StoreCancellationPhase.INSERT,
                    action_base="epoch.owner-insert",
                )
                await self._increment_revisions_before_delete(
                    writer,
                    affected,
                    next_global,
                )
                revision_row = await self._fetchone_sql(
                    writer,
                    "SELECT revision FROM identity_state WHERE identity_id = ?",
                    (identity_id,),
                    action_base="identity.revision-read",
                )
                if revision_row is None:
                    raise LearningStoreError("event identity disappeared")
                final_observation = replace(
                    observation,
                    revision=_as_int("revision", revision_row[0]),
                    learning_epoch=event_epoch,
                )
            else:
                await self._increment_revisions_before_delete(
                    writer,
                    affected,
                    next_global,
                )
            await self._insert_event_locked(
                writer,
                final_observation,
                identity=identity,
                identity_id=identity_id,
                learning_epoch=event_epoch,
                sample_key=None,
            )
            await self._delete_event_ids(writer, event_victim_ids)
            await self._delete_empty_metadata(writer)
            final_state = await self._read_all_state(writer)
            commit_cancelled = await self._commit(
                writer,
                action_id="tx.event.commit",
            )
            committed = True
            self._publish_state(final_state)
            if commit_cancelled:
                raise StoreOperationCancelled(
                    StoreCancellationPhase.COMMIT,
                    final_observation,
                )
        except StoreOperationCancelled:
            raise
        except _ActionCancelled as cancelled:
            if began and not committed:
                await self._rollback(
                    writer,
                    action_id="tx.event.rollback",
                )
            raise _public_cancellation(cancelled) from cancelled.action_error
        except BaseException:
            if began and not committed:
                await self._rollback(
                    writer,
                    action_id="tx.event.rollback",
                )
            raise

    async def _record_anchor_use_with_retry(
        self,
        intent: AnchorUseIntent,
    ) -> AnchorUseOutcome:
        deadline = time.monotonic() + self._busy_retry_timeout
        while True:
            try:
                return await self._record_anchor_use_once(intent)
            except sqlite3.OperationalError as error:
                if not _is_busy(error) or time.monotonic() >= deadline:
                    raise
                await self._busy_sleep(deadline)

    async def _record_anchor_use_once(
        self,
        intent: AnchorUseIntent,
    ) -> AnchorUseOutcome:
        writer = self._require_writer()
        began = False
        committed = False
        try:
            began = True
            await self._begin(
                writer,
                immediate=True,
                action_base="tx.anchor-use.begin",
            )
            state = await self._read_all_state(writer)
            identity_state = _find_identity(state, intent.identity)
            if identity_state is None or not _anchor_intent_matches(
                state,
                identity_state.identity_id,
                intent,
            ):
                commit_cancelled = await self._commit(
                    writer,
                    action_id="tx.anchor-use.commit",
                )
                committed = True
                if commit_cancelled:
                    raise StoreOperationCancelled(
                        StoreCancellationPhase.COMMIT,
                        None,
                    )
                return AnchorUseOutcome.PRUNED
            next_global = state.global_revision + 1
            for sample_key in intent.source_sample_keys:
                await self._execute_sql(
                    writer,
                    """
                    UPDATE samples
                    SET last_used_order = ?
                    WHERE identity_id = ? AND epoch = ?
                      AND process_boot_id = ? AND request_id = ? AND attempt_index = ?
                    """,
                    (
                        next_global,
                        identity_state.identity_id,
                        intent.learning_epoch,
                        *sample_key,
                    ),
                    phase=StoreCancellationPhase.UPDATE,
                    action_base="anchor-use.sample-update",
                )
            await self._increment_revisions_before_delete(
                writer,
                (identity_state.identity_id,),
                next_global,
            )
            final_state = await self._read_all_state(writer)
            commit_cancelled = await self._commit(
                writer,
                action_id="tx.anchor-use.commit",
            )
            committed = True
            self._publish_state(final_state)
            if commit_cancelled:
                raise StoreOperationCancelled(
                    StoreCancellationPhase.COMMIT,
                    None,
                )
            return AnchorUseOutcome.RECORDED
        except StoreOperationCancelled:
            raise
        except _ActionCancelled as cancelled:
            if began and not committed:
                await self._rollback(
                    writer,
                    action_id="tx.anchor-use.rollback",
                )
            raise _public_cancellation(cancelled) from cancelled.action_error
        except BaseException:
            if began and not committed:
                await self._rollback(
                    writer,
                    action_id="tx.anchor-use.rollback",
                )
            raise

    async def _prune_with_retry(self) -> None:
        deadline = time.monotonic() + self._busy_retry_timeout
        while True:
            try:
                await self._prune_once()
                return
            except sqlite3.OperationalError as error:
                if not _is_busy(error) or time.monotonic() >= deadline:
                    raise
                await self._busy_sleep(deadline)

    async def _prune_once(self) -> None:
        writer = self._require_writer()
        began = False
        committed = False
        try:
            began = True
            await self._begin(
                writer,
                immediate=True,
                action_base="tx.prune.begin",
            )
            state = await self._read_all_state(
                writer,
                enforce_bounds=False,
            )
            plan = _compute_prune_plan(state, self._limits)
            event_victim_ids = _compute_event_victim_ids(
                state.events,
                self._limits,
                new_bucket=None,
            )
            if plan.sample_owners or plan.evaluation_keys or event_victim_ids:
                next_global = state.global_revision + 1
                affected = set(plan.affected_identity_ids)
                affected.update(
                    event.identity_id
                    for event in state.events
                    if event.event_id in event_victim_ids
                    and event.identity_id is not None
                )
                await self._increment_revisions_before_delete(
                    writer,
                    affected,
                    next_global,
                )
                await self._apply_prune_plan(writer, plan)
                await self._delete_event_ids(writer, event_victim_ids)
                await self._delete_empty_metadata(writer)
            final_state = await self._read_all_state(writer)
            commit_cancelled = await self._commit(
                writer,
                action_id="tx.prune.commit",
            )
            committed = True
            self._publish_state(final_state)
            if commit_cancelled:
                raise StoreOperationCancelled(
                    StoreCancellationPhase.COMMIT,
                    None,
                )
        except StoreOperationCancelled:
            raise
        except _ActionCancelled as cancelled:
            if began and not committed:
                await self._rollback(
                    writer,
                    action_id="tx.prune.rollback",
                )
            raise _public_cancellation(cancelled) from cancelled.action_error
        except BaseException:
            if began and not committed:
                await self._rollback(
                    writer,
                    action_id="tx.prune.rollback",
                )
            raise

    async def _current_global_revision(
        self,
        connection: aiosqlite.Connection,
    ) -> int:
        row = await self._fetchone_sql(
            connection,
            "SELECT global_revision FROM schema_meta WHERE singleton = 1",
            action_base="global-revision.read",
        )
        if row is None:
            raise LearningStoreError("schema metadata is absent")
        return _as_int("global revision", row[0])

    def _publish_state(self, state: ValidatedPersistentState) -> None:
        if state.global_revision < self._validated_state.global_revision:
            return
        self._validated_state = state
        self._cache = dict(state.active_snapshots)

    def _require_running(self) -> None:
        if self._state != "running":
            raise LearningStoreStateError(
                f"learning store is not running: {self._state}"
            )

    def _require_writer(self) -> aiosqlite.Connection:
        if self._writer is None:
            raise LearningStoreStateError("learning store writer is not open")
        return self._writer

    def _require_reader(self) -> aiosqlite.Connection:
        if self._reader is None:
            raise LearningStoreStateError("learning store reader is not open")
        return self._reader


_IDENTITIES_SQL = """
SELECT
    identity_id,
    actual_provider,
    resolved_model,
    endpoint,
    wire_format,
    tokenizer,
    descriptor_fingerprint,
    estimator_generation,
    profile_schema_revision,
    active_epoch,
    revision
FROM identity_state
ORDER BY identity_id
"""

_EPOCHS_SQL = """
SELECT identity_id, epoch, created_order
FROM epoch_state
ORDER BY identity_id, epoch
"""

_SAMPLES_SQL = """
SELECT
    sample_id,
    identity_id,
    epoch,
    process_boot_id,
    request_id,
    attempt_index,
    observed_at_us,
    actual_input_tokens,
    last_used_order,
    raw_body_sha256,
    feature_raw_body_sha256,
    known_tokens,
    capability_visual_tokens,
    components_json,
    profile_key_json,
    profile_key_hash,
    feature_vector_json,
    full_fingerprint,
    context_fingerprint,
    prefix_fingerprints_json,
    low_confidence_reasons_json,
    committed_order,
    fixed_context_contribution_json,
    input_item_contributions_json
FROM samples
ORDER BY identity_id, epoch, observed_at_us, process_boot_id, request_id, attempt_index
"""

_PREDICTION_RECORDS_SQL = """
SELECT
    identity_id,
    sample_epoch,
    process_boot_id,
    request_id,
    attempt_index,
    prediction_epoch,
    profile_key_hash,
    selected_method,
    selected_variant,
    history_revision,
    method_champions_json,
    candidates_json
FROM prediction_records
ORDER BY identity_id, sample_epoch, process_boot_id, request_id, attempt_index
"""

_EVALUATIONS_SQL = """
SELECT
    identity_id,
    sample_epoch,
    process_boot_id,
    request_id,
    attempt_index,
    method,
    candidate_variant,
    prediction_epoch,
    profile_key_hash,
    ordinal,
    predicted_tokens,
    actual_tokens,
    absolute_error,
    signed_relative_error,
    absolute_percentage_error
FROM evaluations
ORDER BY identity_id, sample_epoch, process_boot_id, request_id, attempt_index, ordinal
"""

_EXACT_ANCHORS_SQL = """
SELECT
    identity_id,
    epoch,
    process_boot_id,
    request_id,
    attempt_index,
    full_fingerprint,
    actual_tokens
FROM exact_anchors
ORDER BY identity_id, epoch, full_fingerprint, process_boot_id, request_id, attempt_index
"""

_PREFIX_ANCHORS_SQL = """
SELECT
    identity_id,
    epoch,
    process_boot_id,
    request_id,
    attempt_index,
    context_fingerprint,
    item_count,
    prefix_fingerprint,
    actual_tokens
FROM prefix_anchors
ORDER BY identity_id, epoch, item_count DESC, process_boot_id, request_id, attempt_index
"""

_PREFIX_CHECKPOINTS_SQL = """
SELECT
    identity_id,
    epoch,
    profile_key_json,
    profile_key_hash,
    mode,
    evidence_json,
    state_revision,
    updated_order
FROM prefix_checkpoints
ORDER BY identity_id, epoch, profile_key_json
"""

_EVENTS_SQL = """
SELECT
    event_id,
    identity_id,
    learning_epoch,
    sample_process_boot_id,
    sample_request_id,
    sample_attempt_index,
    bucket_key,
    process_boot_id,
    request_id,
    attempt_index,
    outcome,
    reason_code,
    metadata_json,
    prefix_checkpoint_outcome_json,
    revision,
    drift_reason_code,
    drift_metadata_json,
    evaluations_json,
    unresolved_provider,
    unresolved_endpoint,
    unresolved_generation,
    created_at_us
FROM learning_events
ORDER BY event_id
"""

_FETCH_IDENTITY_ID_SQL = """
SELECT identity_id
FROM identity_state
WHERE actual_provider = ?
  AND resolved_model = ?
  AND endpoint = ?
  AND wire_format = ?
  AND tokenizer = ?
  AND descriptor_fingerprint = ?
  AND estimator_generation = ?
  AND profile_schema_revision = ?
"""


def _default_connection_factory(
    path: Path,
    read_only: bool,
) -> aiosqlite.Connection:
    if read_only:
        return aiosqlite.connect(
            f"{path.resolve().as_uri()}?mode=ro",
            uri=True,
            isolation_level=None,
            timeout=0,
        )
    return aiosqlite.connect(
        path,
        isolation_level=None,
        timeout=0,
    )


def _thread_id() -> int:
    import threading

    return threading.get_ident()


def _public_cancellation(cancelled: _ActionCancelled) -> StoreOperationCancelled:
    return StoreOperationCancelled(cancelled.phase, None)


def _empty_persistent_state() -> ValidatedPersistentState:
    return ValidatedPersistentState(
        global_revision=0,
        identities=(),
        epochs=(),
        samples=(),
        prediction_records=(),
        evaluations=(),
        reconstructed_evaluations=(),
        exact_anchors=(),
        prefix_anchors=(),
        prefix_checkpoints=(),
        events=(),
        active_snapshots=(),
    )


def _decode_persistent_state(
    rows: _AllRows,
    limits: _StoreLimits,
    enforce_bounds: bool,
) -> ValidatedPersistentState:
    if len(rows.meta) != 1 or rows.meta[0][:3] != (
        1,
        SCHEMA_VERSION,
        SCHEMA_MANIFEST_DIGEST,
    ):
        raise LearningStoreStartupError(
            LearningStoreStartupReason.MANIFEST_MISMATCH
        )
    global_revision = _as_nonnegative_int("global_revision", rows.meta[0][3])
    identities = tuple(_decode_identity(row) for row in rows.identities)
    identity_by_id = {identity.identity_id: identity for identity in identities}
    if len(identity_by_id) != len(identities):
        raise ValueError("identity ids must be unique")
    epochs = tuple(_decode_epoch(row, identity_by_id) for row in rows.epochs)
    epoch_keys = {(epoch.identity_id, epoch.epoch) for epoch in epochs}
    for identity in identities:
        if (identity.identity_id, identity.identity.learning_epoch) not in epoch_keys:
            raise ValueError("active identity epoch is absent")
    samples = tuple(
        _decode_sample(row, identity_by_id, epoch_keys) for row in rows.samples
    )
    sample_by_owner = {sample.owner_key: sample for sample in samples}
    if len(sample_by_owner) != len(samples):
        raise ValueError("sample owner keys must be unique")
    sample_global_keys = {sample.sample.sample_key for sample in samples}
    if len(sample_global_keys) != len(samples):
        raise ValueError("global sample keys must be unique")
    committed_orders = tuple(sample.sample.committed_order for sample in samples)
    if (
        any(order is None for order in committed_orders)
        or len(set(committed_orders)) != len(committed_orders)
        or any(
            cast(int, order) > global_revision + (0 if enforce_bounds else 1)
            for order in committed_orders
        )
    ):
        raise ValueError("persistent samples require globally unique committed orders")
    predictions = tuple(
        _decode_prediction(row, identity_by_id, epoch_keys, sample_by_owner)
        for row in rows.prediction_records
    )
    evaluations = tuple(
        _decode_evaluation(row, epoch_keys, sample_by_owner)
        for row in rows.evaluations
    )
    exact_anchors = tuple(
        _decode_exact_anchor(row, sample_by_owner) for row in rows.exact_anchors
    )
    prefix_anchors = tuple(
        _decode_prefix_anchor(row, identity_by_id, sample_by_owner)
        for row in rows.prefix_anchors
    )
    prefix_checkpoints = tuple(
        _decode_prefix_checkpoint(row, identity_by_id, epoch_keys)
        for row in rows.prefix_checkpoints
    )
    events = tuple(
        _decode_event(row, identity_by_id, epoch_keys, sample_by_owner)
        for row in rows.events
    )
    reconstructed_evaluations = _validate_derived_graph(
        identities,
        epochs,
        samples,
        predictions,
        evaluations,
        exact_anchors,
        prefix_anchors,
        prefix_checkpoints,
        events,
        diagnostic_limit=limits.evaluations_per_window,
    )
    if enforce_bounds:
        _validate_state_bounds(
            identities,
            samples,
            evaluations,
            exact_anchors,
            prefix_checkpoints,
            events,
            limits,
        )
    snapshots = tuple(
        (
            _identity_key(identity.identity),
            _project_snapshot(
                identity,
                samples,
                predictions,
                evaluations,
                exact_anchors,
                prefix_anchors,
                prefix_checkpoints,
            ),
        )
        for identity in identities
    )
    return ValidatedPersistentState(
        global_revision=global_revision,
        identities=identities,
        epochs=epochs,
        samples=samples,
        prediction_records=predictions,
        evaluations=evaluations,
        reconstructed_evaluations=reconstructed_evaluations,
        exact_anchors=exact_anchors,
        prefix_anchors=prefix_anchors,
        prefix_checkpoints=prefix_checkpoints,
        events=events,
        active_snapshots=snapshots,
    )


def _decode_identity(row: _Row) -> _IdentityState:
    identity = LearningIdentity(
        actual_provider=_as_str("actual_provider", row[1]),
        resolved_model=_as_str("resolved_model", row[2]),
        endpoint=_as_str("endpoint", row[3]),
        wire_format=_as_str("wire_format", row[4]),
        tokenizer=_as_str("tokenizer", row[5]),
        descriptor_fingerprint=_as_str("descriptor_fingerprint", row[6]),
        estimator_generation=_as_positive_int("estimator_generation", row[7]),
        profile_schema_revision=_as_positive_int(
            "profile_schema_revision",
            row[8],
        ),
        learning_epoch=_as_nonnegative_int("active_epoch", row[9]),
    )
    _validate_identity(identity)
    return _IdentityState(
        identity_id=_as_positive_int("identity_id", row[0]),
        identity=identity,
        revision=_as_nonnegative_int("revision", row[10]),
    )


def _decode_epoch(
    row: _Row,
    identity_by_id: Mapping[int, _IdentityState],
) -> _EpochState:
    identity_id = _as_positive_int("epoch identity_id", row[0])
    if identity_id not in identity_by_id:
        raise ValueError("epoch identity is absent")
    return _EpochState(
        identity_id,
        _as_nonnegative_int("epoch", row[1]),
        _as_nonnegative_int("created_order", row[2]),
    )


def _decode_sample(
    row: _Row,
    identity_by_id: Mapping[int, _IdentityState],
    epoch_keys: set[tuple[int, int]],
) -> _PersistentSample:
    identity_id = _as_positive_int("sample identity_id", row[1])
    epoch = _as_nonnegative_int("sample epoch", row[2])
    if (identity_id, epoch) not in epoch_keys:
        raise ValueError("sample epoch owner is absent")
    identity_state = identity_by_id[identity_id]
    identity = replace(identity_state.identity, learning_epoch=epoch)
    profile = _decode_profile(row[14])
    profile_json = _encode_json(_profile_payload(profile), "profile key")
    profile_hash = hashlib.sha256(profile_json.encode("utf-8")).hexdigest()
    if profile_hash != _as_str("profile_key_hash", row[15]):
        raise ValueError("stored profile key hash does not match canonical profile")
    features = EstimateFeatures(
        known_tokens=_as_nonnegative_int("known_tokens", row[11]),
        capability_visual_tokens=(
            None
            if row[12] is None
            else _as_nonnegative_int("capability_visual_tokens", row[12])
        ),
        components=_decode_components(row[13]),
        profile_key=profile,
        feature_vector=_decode_feature_vector(row[16]),
        full_fingerprint=_as_str("full_fingerprint", row[17]),
        context_fingerprint=_as_str("context_fingerprint", row[18]),
        prefix_fingerprints=_decode_prefix_fingerprints(row[19]),
        low_confidence_reasons=_decode_string_tuple(
            row[20],
            "low-confidence reasons",
        ),
        estimator_generation=identity.estimator_generation,
        profile_schema_revision=identity.profile_schema_revision,
        raw_sent_body_sha256=(
            None
            if row[10] is None
            else _as_str("feature_raw_body_sha256", row[10])
        ),
        fixed_context_contribution=_decode_fixed_context_contribution(row[22]),
        input_item_contributions=_decode_input_item_contributions(row[23]),
    )
    sample = StoredSample(
        sample_key=(
            _as_str("process_boot_id", row[3]),
            _as_str("request_id", row[4]),
            _as_nonnegative_int("attempt_index", row[5]),
        ),
        identity=identity,
        features=features,
        actual_input_tokens=_as_nonnegative_int(
            "actual_input_tokens",
            row[7],
        ),
        raw_body_sha256=_as_str("raw_body_sha256", row[9]),
        observed_at_us=_as_nonnegative_int("observed_at_us", row[6]),
        committed_order=_as_positive_int("committed_order", row[21]),
    )
    _validate_sample_for_storage(sample)
    return _PersistentSample(
        sample_id=_as_positive_int("sample_id", row[0]),
        identity_id=identity_id,
        epoch=epoch,
        last_used_order=_as_positive_int("last_used_order", row[8]),
        sample=sample,
    )


def _decode_prediction(
    row: _Row,
    identity_by_id: Mapping[int, _IdentityState],
    epoch_keys: set[tuple[int, int]],
    sample_by_owner: Mapping[_SampleOwnerKey, _PersistentSample],
) -> _PersistentPrediction:
    identity_id = _as_positive_int("prediction identity_id", row[0])
    sample_epoch = _as_nonnegative_int("prediction sample_epoch", row[1])
    sample_key = (
        _as_str("prediction process_boot_id", row[2]),
        _as_str("prediction request_id", row[3]),
        _as_nonnegative_int("prediction attempt_index", row[4]),
    )
    owner = (identity_id, sample_epoch, *sample_key)
    sample = sample_by_owner.get(owner)
    if sample is None:
        raise ValueError("prediction source sample is absent")
    prediction_epoch = _as_nonnegative_int("prediction epoch", row[5])
    if (identity_id, prediction_epoch) not in epoch_keys:
        raise ValueError("prediction epoch is absent")
    profile_hash = _as_str("prediction profile hash", row[6])
    expected_hash = hashlib.sha256(
        _encode_json(
            _profile_payload(sample.sample.features.profile_key),
            "profile key",
        ).encode("utf-8")
    ).hexdigest()
    if profile_hash != expected_hash:
        raise ValueError("prediction profile hash does not match source sample")
    identity = replace(
        identity_by_id[identity_id].identity,
        learning_epoch=prediction_epoch,
    )
    record = _decode_prediction_record(
        sample_key,
        identity,
        sample.sample.features.profile_key,
        _as_str("selected_method", row[7]),
        _as_str("selected_variant", row[8]),
        _as_nonnegative_int("history_revision", row[9]),
        row[10],
        row[11],
    )
    return _PersistentPrediction(
        identity_id,
        sample_epoch,
        prediction_epoch,
        record,
    )


def _decode_evaluation(
    row: _Row,
    epoch_keys: set[tuple[int, int]],
    sample_by_owner: Mapping[_SampleOwnerKey, _PersistentSample],
) -> _PersistentEvaluation:
    identity_id = _as_positive_int("evaluation identity_id", row[0])
    sample_epoch = _as_nonnegative_int("evaluation sample_epoch", row[1])
    sample_key = (
        _as_str("evaluation process_boot_id", row[2]),
        _as_str("evaluation request_id", row[3]),
        _as_nonnegative_int("evaluation attempt_index", row[4]),
    )
    owner = (identity_id, sample_epoch, *sample_key)
    sample = sample_by_owner.get(owner)
    if sample is None:
        raise ValueError("evaluation source sample is absent")
    prediction_epoch = _as_nonnegative_int("evaluation prediction_epoch", row[7])
    if (identity_id, prediction_epoch) not in epoch_keys:
        raise ValueError("evaluation prediction epoch is absent")
    profile_hash = _as_str("evaluation profile hash", row[8])
    expected_hash = hashlib.sha256(
        _encode_json(
            _profile_payload(sample.sample.features.profile_key),
            "profile key",
        ).encode("utf-8")
    ).hexdigest()
    if profile_hash != expected_hash:
        raise ValueError("evaluation profile hash does not match source sample")
    method = PredictionMethod(_as_str("evaluation method", row[5]))
    evaluation = PredictionEvaluation(
        sample_key=sample_key,
        method=method,
        candidate_key=PredictionCandidateKey(
            method,
            PredictionCandidateVariant(_as_str("evaluation variant", row[6])),
        ),
        predicted_tokens=_as_number("predicted_tokens", row[10]),
        actual_tokens=_as_nonnegative_int("actual_tokens", row[11]),
        absolute_error=_as_nonnegative_number("absolute_error", row[12]),
        signed_relative_error=(
            None
            if row[13] is None
            else _as_number("signed_relative_error", row[13])
        ),
        absolute_percentage_error=(
            None
            if row[14] is None
            else _as_nonnegative_number(
                "absolute_percentage_error",
                row[14],
            )
        ),
    )
    if evaluation.actual_tokens != sample.sample.actual_input_tokens:
        raise ValueError("evaluation actual does not match source sample")
    return _PersistentEvaluation(
        identity_id,
        sample_epoch,
        prediction_epoch,
        profile_hash,
        _as_nonnegative_int("evaluation ordinal", row[9]),
        evaluation,
    )


def _decode_exact_anchor(
    row: _Row,
    sample_by_owner: Mapping[_SampleOwnerKey, _PersistentSample],
) -> _PersistentExactAnchor:
    identity_id = _as_positive_int("exact identity_id", row[0])
    epoch = _as_nonnegative_int("exact epoch", row[1])
    sample_key = (
        _as_str("exact process_boot_id", row[2]),
        _as_str("exact request_id", row[3]),
        _as_nonnegative_int("exact attempt_index", row[4]),
    )
    source = sample_by_owner.get((identity_id, epoch, *sample_key))
    if source is None:
        raise ValueError("exact anchor source is absent")
    fingerprint = _as_str("exact fingerprint", row[5])
    actual = _as_nonnegative_int("exact actual", row[6])
    if (
        fingerprint != source.sample.features.full_fingerprint
        or actual != source.sample.actual_input_tokens
    ):
        raise ValueError("exact anchor does not match source sample")
    return _PersistentExactAnchor(
        identity_id,
        epoch,
        sample_key,
        fingerprint,
        actual,
    )


def _decode_prefix_anchor(
    row: _Row,
    identity_by_id: Mapping[int, _IdentityState],
    sample_by_owner: Mapping[_SampleOwnerKey, _PersistentSample],
) -> _PersistentPrefixAnchor:
    identity_id = _as_positive_int("prefix identity_id", row[0])
    epoch = _as_nonnegative_int("prefix epoch", row[1])
    sample_key = (
        _as_str("prefix process_boot_id", row[2]),
        _as_str("prefix request_id", row[3]),
        _as_nonnegative_int("prefix attempt_index", row[4]),
    )
    source = sample_by_owner.get((identity_id, epoch, *sample_key))
    if source is None:
        raise ValueError("prefix anchor source is absent")
    prefix = PrefixFingerprint(
        item_count=_as_positive_int("prefix item_count", row[6]),
        digest=_as_str("prefix fingerprint", row[7]),
    )
    if (
        _as_str("context fingerprint", row[5])
        != source.sample.features.context_fingerprint
        or prefix not in source.sample.features.prefix_fingerprints
        or _as_nonnegative_int("prefix actual", row[8])
        != source.sample.actual_input_tokens
    ):
        raise ValueError("prefix anchor does not match source sample")
    identity = replace(
        identity_by_id[identity_id].identity,
        learning_epoch=epoch,
    )
    return _PersistentPrefixAnchor(
        identity_id,
        epoch,
        PrefixAnchor(
            identity=identity,
            context_fingerprint=source.sample.features.context_fingerprint,
            prefix_fingerprint=prefix,
            actual_tokens=source.sample.actual_input_tokens,
            sample_key=sample_key,
            observed_at_us=source.sample.observed_at_us,
        ),
    )


def _decode_prefix_checkpoint(
    row: _Row,
    identity_by_id: Mapping[int, _IdentityState],
    epoch_keys: set[tuple[int, int]],
) -> _PersistentPrefixCheckpoint:
    identity_id = _as_positive_int("prefix checkpoint identity_id", row[0])
    epoch = _as_nonnegative_int("prefix checkpoint epoch", row[1])
    if identity_id not in identity_by_id or (identity_id, epoch) not in epoch_keys:
        raise ValueError("prefix checkpoint epoch owner is absent")
    profile = _decode_profile(row[2])
    canonical_json = _encode_json(_profile_payload(profile), "prefix checkpoint profile")
    if canonical_json != _as_str("prefix checkpoint profile JSON", row[2]):
        raise ValueError("prefix checkpoint profile JSON is not canonical")
    expected_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    if expected_hash != _as_str("prefix checkpoint profile hash", row[3]):
        raise ValueError("prefix checkpoint profile hash does not match canonical profile")
    mode = PrefixCheckpointMode(_as_str("prefix checkpoint mode", row[4]))
    evidence_items = _decode_json_list(row[5], "prefix checkpoint evidence")
    evidence: list[PrefixChampionErrorTriple] = []
    for item in evidence_items:
        if not isinstance(item, list):
            raise ValueError("prefix checkpoint evidence has invalid compact shape")
        values = cast(list[object], item)
        if len(values) != 4:
            raise ValueError("prefix checkpoint evidence has invalid compact shape")
        evidence.append(
            PrefixChampionErrorTriple(
                _as_nonnegative_number("prefix checkpoint prefix APE", values[0]),
                None
                if values[1] is None
                else _as_nonnegative_number("prefix checkpoint profile APE", values[1]),
                _as_nonnegative_number("prefix checkpoint cold APE", values[2]),
                _as_positive_int("prefix checkpoint evidence order", values[3]),
            )
        )
    return _PersistentPrefixCheckpoint(
        identity_id,
        epoch,
        PrefixEligibilityCheckpoint(
            profile,
            mode,
            tuple(evidence),
            _as_positive_int("prefix checkpoint state revision", row[6]),
            _as_positive_int("prefix checkpoint updated order", row[7]),
        ),
    )


def _decode_event(
    row: _Row,
    identity_by_id: Mapping[int, _IdentityState],
    epoch_keys: set[tuple[int, int]],
    sample_by_owner: Mapping[_SampleOwnerKey, _PersistentSample],
) -> _PersistentEvent:
    event_id = _as_positive_int("event_id", row[0])
    identity_id = None if row[1] is None else _as_positive_int("event identity_id", row[1])
    learning_epoch = None if row[2] is None else _as_nonnegative_int("event epoch", row[2])
    sample_values = row[3:6]
    sample_key: SampleKey | None
    if all(value is None for value in sample_values):
        sample_key = None
    elif all(value is not None for value in sample_values):
        sample_key = (
            _as_str("event sample process_boot_id", sample_values[0]),
            _as_str("event sample request_id", sample_values[1]),
            _as_nonnegative_int("event sample attempt_index", sample_values[2]),
        )
    else:
        raise ValueError("event sample key must be all present or all absent")
    event_sample_key = (
        _as_str("event process_boot_id", row[7]),
        _as_str("event request_id", row[8]),
        _as_nonnegative_int("event attempt_index", row[9]),
    )
    outcome = _decode_outcome(row[10])
    reason_code = LearningReasonCode(_as_str("event reason_code", row[11]))
    metadata = _decode_learning_metadata(reason_code, row[12])
    checkpoint_outcome = _decode_prefix_checkpoint_outcome(row[13])
    evaluations = _decode_event_evaluations(row[17])
    if any(evaluation.sample_key != event_sample_key for evaluation in evaluations):
        raise ValueError("event evaluation sample keys do not match event")
    unresolved: UnresolvedLearningIdentity | None = None
    identity: LearningIdentity | None = None
    if identity_id is None:
        if learning_epoch is not None or sample_key is not None:
            raise ValueError("unresolved event cannot carry recognized links")
        unresolved = UnresolvedLearningIdentity(
            _as_str("unresolved_provider", row[18]),
            _as_str("unresolved_endpoint", row[19]),
            _as_positive_int("unresolved_generation", row[20]),
        )
        expected_bucket = _unresolved_bucket_key(unresolved)
    else:
        if learning_epoch is None or (identity_id, learning_epoch) not in epoch_keys:
            raise ValueError("recognized event epoch is absent")
        if any(value is not None for value in row[18:21]):
            raise ValueError("recognized event carries unresolved identity fields")
        identity = replace(
            identity_by_id[identity_id].identity,
            learning_epoch=learning_epoch,
        )
        expected_bucket = _identity_bucket_key(identity)
        if sample_key is not None and (
            identity_id,
            learning_epoch,
            *sample_key,
        ) not in sample_by_owner:
            raise ValueError("event sample link is absent")
    bucket = _as_str("event bucket", row[6])
    if bucket != expected_bucket:
        raise ValueError("event bucket does not match canonical identity")
    drift = None
    if row[15] is not None:
        if identity is None:
            raise ValueError("unresolved event cannot carry drift")
        reason = DriftReasonCode(_as_str("drift reason", row[15]))
        drift = _decode_drift(
            identity,
            reason,
            row[16],
        )
    observation = TokenLearningObservation(
        sample_key=event_sample_key,
        outcome=outcome,
        reason_code=reason_code,
        metadata=metadata,
        prefix_checkpoint_outcome=checkpoint_outcome,
        evaluations=evaluations,
        revision=(
            None
            if row[14] is None
            else _as_nonnegative_int("event revision", row[14])
        ),
        learning_epoch=learning_epoch,
        drift=drift,
    )
    _validate_observation_for_storage(observation)
    return _PersistentEvent(
        event_id,
        identity_id,
        learning_epoch,
        sample_key,
        bucket,
        observation,
        unresolved,
        _as_nonnegative_int("created_at_us", row[21]),
    )


def _validate_derived_graph(
    identities: tuple[_IdentityState, ...],
    epochs: tuple[_EpochState, ...],
    samples: tuple[_PersistentSample, ...],
    predictions: tuple[_PersistentPrediction, ...],
    evaluations: tuple[_PersistentEvaluation, ...],
    exact_anchors: tuple[_PersistentExactAnchor, ...],
    prefix_anchors: tuple[_PersistentPrefixAnchor, ...],
    prefix_checkpoints: tuple[_PersistentPrefixCheckpoint, ...],
    events: tuple[_PersistentEvent, ...],
    *,
    diagnostic_limit: int,
) -> tuple[_PersistentEvaluation, ...]:
    sample_by_owner = {sample.owner_key: sample for sample in samples}
    predictions_by_owner: dict[_SampleOwnerKey, list[_PersistentPrediction]] = defaultdict(list)
    exact_by_owner: dict[_SampleOwnerKey, list[_PersistentExactAnchor]] = defaultdict(list)
    prefix_by_owner: dict[_SampleOwnerKey, list[_PersistentPrefixAnchor]] = defaultdict(list)
    for prediction in predictions:
        predictions_by_owner[prediction.owner_key].append(prediction)
    for anchor in exact_anchors:
        exact_by_owner[anchor.owner_key].append(anchor)
    for anchor in prefix_anchors:
        prefix_by_owner[anchor.owner_key].append(anchor)
    for owner, sample in sample_by_owner.items():
        if len(predictions_by_owner[owner]) != 1:
            raise ValueError("each retained sample requires exactly one prediction record")
        if len(exact_by_owner[owner]) != 1:
            raise ValueError("each retained sample requires exactly one exact anchor")
        prefixes = prefix_by_owner[owner]
        chain = sample.sample.features.prefix_fingerprints
        if not chain:
            if prefixes:
                raise ValueError("sample without prefix chain cannot have prefix anchor")
        elif len(prefixes) != 1:
            raise ValueError("sample with prefix chain requires exactly one prefix anchor")
        elif prefixes[0].anchor.prefix_fingerprint != chain[-1]:
            raise ValueError("prefix anchor must identify the final source prefix")
    if set(predictions_by_owner) - set(sample_by_owner):
        raise ValueError("prediction record has no retained source sample")
    if set(exact_by_owner) - set(sample_by_owner):
        raise ValueError("exact anchor has no retained source sample")
    if set(prefix_by_owner) - set(sample_by_owner):
        raise ValueError("prefix anchor has no retained source sample")

    reconstructed: list[_PersistentEvaluation] = []
    reconstructed_by_key: dict[
        tuple[_SampleOwnerKey, PredictionCandidateKey],
        _PersistentEvaluation,
    ] = {}
    for prediction in predictions:
        source = sample_by_owner[prediction.owner_key]
        profile_hash = hashlib.sha256(
            _encode_json(
                _profile_payload(source.sample.features.profile_key),
                "profile key",
            ).encode("utf-8")
        ).hexdigest()
        for ordinal, candidate in enumerate(prediction.record.candidates):
            evaluation = _evaluation_from_candidate(
                prediction.record.sample_key,
                candidate,
                source.sample.actual_input_tokens,
            )
            persistent = _PersistentEvaluation(
                identity_id=prediction.identity_id,
                sample_epoch=prediction.sample_epoch,
                prediction_epoch=prediction.prediction_epoch,
                profile_key_hash=profile_hash,
                ordinal=ordinal,
                evaluation=evaluation,
            )
            key = (prediction.owner_key, candidate.candidate_key)
            if key in reconstructed_by_key:
                raise ValueError("prediction candidates must be unique per candidate key")
            reconstructed_by_key[key] = persistent
            reconstructed.append(persistent)

    persisted_by_key: dict[
        tuple[_SampleOwnerKey, PredictionCandidateKey],
        _PersistentEvaluation,
    ] = {}
    for evaluation in evaluations:
        key = (evaluation.owner_key, evaluation.evaluation.candidate_key)
        if key in persisted_by_key:
            raise ValueError("persisted evaluation rows must be unique")
        expected = reconstructed_by_key.get(key)
        if expected is None:
            raise ValueError("persisted evaluation has no matching record candidate")
        if evaluation != expected:
            raise ValueError("persisted evaluation does not match record candidate")
        persisted_by_key[key] = evaluation

    windows: dict[
        tuple[int, int, str, PredictionCandidateKey],
        list[_PersistentEvaluation],
    ] = defaultdict(list)
    for evaluation in reconstructed:
        windows[
            (
                evaluation.identity_id,
                evaluation.prediction_epoch,
                evaluation.profile_key_hash,
                evaluation.evaluation.candidate_key,
            )
        ].append(evaluation)
    for window in windows.values():
        newest = sorted(
            window,
            key=lambda value: _newest_sample_sort_key(
                sample_by_owner[value.owner_key].sample
            ),
        )[:diagnostic_limit]
        for evaluation in newest:
            key = (evaluation.owner_key, evaluation.evaluation.candidate_key)
            if key not in persisted_by_key:
                raise ValueError("newest diagnostic evaluation row is missing")

    for event in events:
        if event.sample_key is None:
            if event.observation.outcome == "committed" and (
                event.observation.reason_code is not LearningReasonCode.PRUNED
            ):
                raise ValueError("sample-less committed event must record pruning")
            continue
        if event.identity_id is None or event.learning_epoch is None:
            raise ValueError("sample-linked event requires recognized identity and epoch")
        owner = (
            event.identity_id,
            event.learning_epoch,
            *event.sample_key,
        )
        source = sample_by_owner.get(owner)
        if source is None:
            raise ValueError("sample-linked event source is absent")
        if event.observation.sample_key != event.sample_key:
            raise ValueError("event observation key does not match linked sample")
        if isinstance(event.observation.metadata, SampleCommittedMetadata) and (
            event.observation.metadata.actual_input_tokens
            != source.sample.actual_input_tokens
        ):
            raise ValueError("event committed actual does not match linked sample")
        for evaluation in event.observation.evaluations:
            expected = reconstructed_by_key.get((owner, evaluation.candidate_key))
            if expected is None or evaluation != expected.evaluation:
                raise ValueError("event evaluation does not match record candidate")
        if (
            event.observation.reason_code is LearningReasonCode.SAMPLE_COMMITTED
            and {
                evaluation.candidate_key
                for evaluation in event.observation.evaluations
            }
            != {
                candidate.candidate_key
                for candidate in predictions_by_owner[owner][0].record.candidates
            }
        ):
            raise ValueError("committed event must include every candidate evaluation")
        if event.observation.learning_epoch != source.epoch:
            raise ValueError("event observation epoch does not match linked sample")
        if event.observation.drift is not None:
            source_prediction = predictions_by_owner[owner][0]
            selected = source_prediction.record.selected
            drift = event.observation.drift
            if (
                drift.previous_epoch != source_prediction.prediction_epoch
                or drift.previous_epoch != selected.learning_epoch
                or drift.identity != selected.identity
                or drift.new_epoch != source.epoch
                or not _same_identity_base(
                    drift.identity,
                    source.sample.identity,
                )
            ):
                raise ValueError("event drift transition does not match linked prediction")

    checkpoint_keys = {
        (checkpoint.identity_id, checkpoint.epoch, checkpoint.checkpoint.profile_key)
        for checkpoint in prefix_checkpoints
    }
    if len(checkpoint_keys) != len(prefix_checkpoints):
        raise ValueError("prefix checkpoints must have unique canonical identities")

    epoch_references: set[tuple[int, int]] = set()
    identity_references: set[int] = set()
    for sample in samples:
        epoch_references.add((sample.identity_id, sample.epoch))
        identity_references.add(sample.identity_id)
    for prediction in predictions:
        epoch_references.add((prediction.identity_id, prediction.sample_epoch))
        epoch_references.add((prediction.identity_id, prediction.prediction_epoch))
        identity_references.add(prediction.identity_id)
    for evaluation in evaluations:
        epoch_references.add((evaluation.identity_id, evaluation.sample_epoch))
        epoch_references.add((evaluation.identity_id, evaluation.prediction_epoch))
        identity_references.add(evaluation.identity_id)
    for anchor in exact_anchors:
        epoch_references.add((anchor.identity_id, anchor.epoch))
        identity_references.add(anchor.identity_id)
    for anchor in prefix_anchors:
        epoch_references.add((anchor.identity_id, anchor.epoch))
        identity_references.add(anchor.identity_id)
    for checkpoint in prefix_checkpoints:
        epoch_references.add((checkpoint.identity_id, checkpoint.epoch))
        identity_references.add(checkpoint.identity_id)
    for event in events:
        if event.identity_id is not None and event.learning_epoch is not None:
            epoch_references.add((event.identity_id, event.learning_epoch))
            identity_references.add(event.identity_id)
    active_epochs = {
        (identity.identity_id, identity.identity.learning_epoch)
        for identity in identities
    }
    for epoch in epochs:
        key = (epoch.identity_id, epoch.epoch)
        if key not in active_epochs and key not in epoch_references:
            raise ValueError("inactive epoch metadata is unreferenced")
    for identity in identities:
        if identity.identity_id not in identity_references:
            raise ValueError("identity metadata is unreferenced")
    return tuple(reconstructed)


def _evaluation_from_candidate(
    sample_key: SampleKey,
    candidate: TokenPrediction,
    actual_tokens: int,
) -> PredictionEvaluation:
    absolute_error = abs(candidate.unscaled_tokens - actual_tokens)
    return PredictionEvaluation(
        sample_key=sample_key,
        method=candidate.method,
        candidate_key=candidate.candidate_key,
        predicted_tokens=candidate.unscaled_tokens,
        actual_tokens=actual_tokens,
        absolute_error=absolute_error,
        signed_relative_error=(
            None
            if actual_tokens == 0
            else (candidate.unscaled_tokens - actual_tokens) / actual_tokens
        ),
        absolute_percentage_error=(
            None if actual_tokens == 0 else absolute_error / actual_tokens
        ),
    )


def _project_snapshot(
    identity_state: _IdentityState,
    samples: tuple[_PersistentSample, ...],
    predictions: tuple[_PersistentPrediction, ...],
    evaluations: tuple[_PersistentEvaluation, ...],
    exact_anchors: tuple[_PersistentExactAnchor, ...],
    prefix_anchors: tuple[_PersistentPrefixAnchor, ...],
    prefix_checkpoints: tuple[_PersistentPrefixCheckpoint, ...],
) -> LearningSnapshot:
    identity = identity_state.identity
    identity_id = identity_state.identity_id
    epoch = identity.learning_epoch
    active_persistent = tuple(
        sample
        for sample in samples
        if sample.identity_id == identity_id and sample.epoch == epoch
    )
    active_by_key = {sample.sample.sample_key: sample for sample in active_persistent}
    active_samples = tuple(
        sample.sample
        for sample in sorted(
            active_persistent,
            key=lambda value: _newest_sample_sort_key(value.sample),
        )
    )
    exact_rows = tuple(
        anchor
        for anchor in exact_anchors
        if anchor.identity_id == identity_id and anchor.epoch == epoch
    )
    grouped_exact: dict[str, list[_PersistentExactAnchor]] = defaultdict(list)
    for anchor in sorted(
        exact_rows,
        key=lambda value: (
            value.full_fingerprint,
            *_newest_sample_sort_key(active_by_key[value.sample_key].sample),
        ),
    ):
        grouped_exact[anchor.full_fingerprint].append(anchor)
    exact = tuple(
        ExactAnchor(
            identity=identity,
            full_fingerprint=fingerprint,
            actual_tokens=tuple(anchor.actual_tokens for anchor in anchors),
            sample_keys=tuple(anchor.sample_key for anchor in anchors),
        )
        for fingerprint, anchors in grouped_exact.items()
    )
    prefix = tuple(
        anchor.anchor
        for anchor in sorted(
            (
                anchor
                for anchor in prefix_anchors
                if anchor.identity_id == identity_id and anchor.epoch == epoch
            ),
            key=lambda value: (
                -value.anchor.prefix_fingerprint.item_count,
                -value.anchor.observed_at_us,
                _sample_key_binary(value.anchor.sample_key),
            ),
        )
    )
    active_predictions = tuple(
        prediction.record
        for prediction in sorted(
            (
                prediction
                for prediction in predictions
                if prediction.identity_id == identity_id
                and prediction.sample_epoch == epoch
                and prediction.prediction_epoch == epoch
            ),
            key=lambda value: _newest_sample_sort_key(
                active_by_key[value.record.sample_key].sample
            ),
        )
    )
    active_evaluations = tuple(
        evaluation.evaluation
        for evaluation in sorted(
            (
                evaluation
                for evaluation in evaluations
                if evaluation.identity_id == identity_id
                and evaluation.sample_epoch == epoch
                and evaluation.prediction_epoch == epoch
            ),
            key=lambda value: (
                *_newest_sample_sort_key(
                    active_by_key[value.evaluation.sample_key].sample
                ),
                value.ordinal,
            ),
        )
    )
    active_checkpoints = tuple(
        checkpoint.checkpoint
        for checkpoint in sorted(
            (
                checkpoint
                for checkpoint in prefix_checkpoints
                if checkpoint.identity_id == identity_id and checkpoint.epoch == epoch
            ),
            key=lambda value: _encode_json(
                _profile_payload(value.checkpoint.profile_key), "prefix checkpoint profile"
            ),
        )
    )
    return LearningSnapshot(
        identity=identity,
        revision=identity_state.revision,
        active_epoch=epoch,
        samples=active_samples,
        exact_anchors=exact,
        prefix_anchors=prefix,
        prefix_checkpoints=active_checkpoints,
        prediction_records=active_predictions,
        evaluations=active_evaluations,
    )


def _validate_state_bounds(
    identities: tuple[_IdentityState, ...],
    samples: tuple[_PersistentSample, ...],
    evaluations: tuple[_PersistentEvaluation, ...],
    exact_anchors: tuple[_PersistentExactAnchor, ...],
    prefix_checkpoints: tuple[_PersistentPrefixCheckpoint, ...],
    events: tuple[_PersistentEvent, ...],
    limits: _StoreLimits,
) -> None:
    if len(samples) > limits.samples_global:
        raise ValueError("global sample bound is exceeded")
    samples_by_identity: dict[int, int] = defaultdict(int)
    for sample in samples:
        samples_by_identity[sample.identity_id] += 1
    if any(count > limits.samples_per_identity for count in samples_by_identity.values()):
        raise ValueError("per-identity sample bound is exceeded")
    exact_counts: dict[tuple[int, int, str], int] = defaultdict(int)
    for anchor in exact_anchors:
        exact_counts[(anchor.identity_id, anchor.epoch, anchor.full_fingerprint)] += 1
    if any(count > limits.actuals_per_fingerprint for count in exact_counts.values()):
        raise ValueError("exact actual bound is exceeded")
    evaluation_counts: dict[tuple[int, int, str, PredictionCandidateKey], int] = defaultdict(int)
    sample_by_owner = {sample.owner_key: sample for sample in samples}
    for evaluation in evaluations:
        sample = sample_by_owner[evaluation.owner_key]
        profile_hash = hashlib.sha256(
            _encode_json(
                _profile_payload(sample.sample.features.profile_key),
                "profile key",
            ).encode("utf-8")
        ).hexdigest()
        evaluation_counts[
            (
                evaluation.identity_id,
                evaluation.prediction_epoch,
                profile_hash,
                evaluation.evaluation.candidate_key,
            )
        ] += 1
    if any(count > limits.evaluations_per_window for count in evaluation_counts.values()):
        raise ValueError("evaluation window bound is exceeded")
    active_epochs = {
        (identity.identity_id, identity.identity.learning_epoch)
        for identity in identities
    }
    active_checkpoints = tuple(
        checkpoint
        for checkpoint in prefix_checkpoints
        if (checkpoint.identity_id, checkpoint.epoch) in active_epochs
    )
    if len(active_checkpoints) > limits.prefix_checkpoints_global:
        raise ValueError("global prefix checkpoint bound is exceeded")
    checkpoint_counts: dict[tuple[int, int], int] = defaultdict(int)
    for checkpoint in active_checkpoints:
        checkpoint_counts[(checkpoint.identity_id, checkpoint.epoch)] += 1
    if any(
        count > limits.prefix_checkpoints_per_identity
        for count in checkpoint_counts.values()
    ):
        raise ValueError("per-identity prefix checkpoint bound is exceeded")
    if len(events) > limits.events_global:
        raise ValueError("global event bound is exceeded")
    event_counts: dict[str, int] = defaultdict(int)
    for event in events:
        event_counts[event.bucket_key] += 1
    if any(count > limits.events_per_identity for count in event_counts.values()):
        raise ValueError("per-identity event bound is exceeded")
    identity_ids = {identity.identity_id for identity in identities}
    if any(sample.identity_id not in identity_ids for sample in samples):
        raise ValueError("sample references unknown identity")


def _event_owner_key(event: _PersistentEvent) -> _SampleOwnerKey | None:
    if (
        event.identity_id is None
        or event.learning_epoch is None
        or event.sample_key is None
    ):
        return None
    return (
        event.identity_id,
        event.learning_epoch,
        *event.sample_key,
    )


def _compute_event_victim_ids(
    events: tuple[_PersistentEvent, ...],
    limits: _StoreLimits,
    *,
    new_bucket: str | None,
) -> frozenset[int]:
    retained = {event.event_id: event for event in events}
    victims: set[int] = set()
    by_bucket: dict[str, list[_PersistentEvent]] = defaultdict(list)
    for event in events:
        by_bucket[event.bucket_key].append(event)
    for bucket, values in by_bucket.items():
        additional = 1 if bucket == new_bucket else 0
        excess = len(values) + additional - limits.events_per_identity
        if excess > 0:
            victims.update(
                event.event_id
                for event in sorted(values, key=lambda value: value.event_id)[:excess]
            )
    for event_id in victims:
        retained.pop(event_id, None)
    global_excess = len(retained) + (1 if new_bucket is not None else 0) - limits.events_global
    if global_excess > 0:
        victims.update(sorted(retained)[:global_excess])
    return frozenset(victims)


def _compute_prune_plan(
    state: ValidatedPersistentState,
    limits: _StoreLimits,
) -> _PrunePlan:
    retained = {sample.owner_key: sample for sample in state.samples}
    victims: list[_SampleOwnerKey] = []

    def remove(owner: _SampleOwnerKey) -> None:
        if owner in retained:
            victims.append(owner)
            retained.pop(owner)

    exact_groups: dict[tuple[int, int, str], list[_PersistentSample]] = defaultdict(list)
    exact_fingerprints = {
        anchor.owner_key: anchor.full_fingerprint for anchor in state.exact_anchors
    }
    for sample in retained.values():
        fingerprint = exact_fingerprints.get(sample.owner_key)
        if fingerprint is not None:
            exact_groups[(sample.identity_id, sample.epoch, fingerprint)].append(sample)
    for group in exact_groups.values():
        while sum(sample.owner_key in retained for sample in group) > limits.actuals_per_fingerprint:
            candidates = [sample for sample in group if sample.owner_key in retained]
            remove(
                min(candidates, key=lambda value: _sample_victim_key(value, state)).owner_key
            )

    for identity in state.identities:
        while sum(
            sample.identity_id == identity.identity_id
            for sample in retained.values()
        ) > limits.samples_per_identity:
            candidates = [
                sample
                for sample in retained.values()
                if sample.identity_id == identity.identity_id
            ]
            remove(
                min(candidates, key=lambda value: _sample_victim_key(value, state)).owner_key
            )

    while len(retained) > limits.samples_global:
        identities_with_samples = {
            sample.identity_id for sample in retained.values()
        }
        victim_identity = min(
            (
                identity
                for identity in state.identities
                if identity.identity_id in identities_with_samples
            ),
            key=lambda value: _identity_victim_key(
                value,
                tuple(retained.values()),
                state,
            ),
        )
        candidates = [
            sample
            for sample in retained.values()
            if sample.identity_id == victim_identity.identity_id
        ]
        remove(
            min(candidates, key=lambda value: _sample_victim_key(value, state)).owner_key
        )

    evaluation_victims: list[tuple[_SampleOwnerKey, PredictionCandidateKey]] = []
    windows: dict[
        tuple[int, int, str, PredictionCandidateKey],
        list[_PersistentEvaluation],
    ] = defaultdict(list)
    for evaluation in state.evaluations:
        if evaluation.owner_key not in retained:
            continue
        windows[
            (
                evaluation.identity_id,
                evaluation.prediction_epoch,
                evaluation.profile_key_hash,
                evaluation.evaluation.candidate_key,
            )
        ].append(evaluation)
    for window in windows.values():
        ordered = sorted(
            window,
            key=lambda value: _newest_sample_sort_key(
                retained[value.owner_key].sample
            ),
        )
        for evaluation in ordered[limits.evaluations_per_window :]:
            evaluation_victims.append(
                (evaluation.owner_key, evaluation.evaluation.candidate_key)
            )
    affected = {
        owner[0] for owner in victims
    } | {owner[0] for owner, _method in evaluation_victims}
    return _PrunePlan(
        sample_owners=tuple(victims),
        evaluation_keys=tuple(evaluation_victims),
        affected_identity_ids=frozenset(affected),
    )


def _sample_victim_key(
    sample: _PersistentSample,
    state: ValidatedPersistentState,
) -> tuple[object, ...]:
    identity = next(
        value for value in state.identities if value.identity_id == sample.identity_id
    )
    has_exact = any(anchor.owner_key == sample.owner_key for anchor in state.exact_anchors)
    prefix_items = [
        anchor.anchor.prefix_fingerprint.item_count
        for anchor in state.prefix_anchors
        if anchor.owner_key == sample.owner_key
    ]
    anchor_use = sample.last_used_order if has_exact or prefix_items else -1
    coverage = max(prefix_items, default=-1)
    return (
        0 if sample.epoch != identity.identity.learning_epoch else 1,
        anchor_use,
        coverage,
        sample.sample.observed_at_us,
        *_sample_key_binary(sample.sample.sample_key),
    )


def _identity_victim_key(
    identity: _IdentityState,
    retained_samples: tuple[_PersistentSample, ...],
    state: ValidatedPersistentState,
) -> tuple[object, ...]:
    samples = tuple(
        sample
        for sample in retained_samples
        if sample.identity_id == identity.identity_id
    )
    owners = {sample.owner_key for sample in samples}
    has_active = any(
        sample.epoch == identity.identity.learning_epoch for sample in samples
    )
    anchor_uses = [
        sample.last_used_order
        for sample in samples
        if any(anchor.owner_key == sample.owner_key for anchor in state.exact_anchors)
        or any(anchor.owner_key == sample.owner_key for anchor in state.prefix_anchors)
    ]
    coverages = [
        anchor.anchor.prefix_fingerprint.item_count
        for anchor in state.prefix_anchors
        if anchor.owner_key in owners
    ]
    oldest = min((sample.sample.observed_at_us for sample in samples), default=-1)
    return (
        1 if has_active else 0,
        max(anchor_uses, default=-1),
        max(coverages, default=-1),
        oldest,
        *_identity_binary_key(identity.identity),
    )


def _anchor_intent_matches(
    state: ValidatedPersistentState,
    identity_id: int,
    intent: AnchorUseIntent,
) -> bool:
    identity = next(
        candidate
        for candidate in state.identities
        if candidate.identity_id == identity_id
    )
    if identity.identity.learning_epoch != intent.learning_epoch:
        return False
    if intent.kind is AnchorKind.EXACT:
        source_keys = tuple(
            anchor.sample_key
            for anchor in state.exact_anchors
            if anchor.identity_id == identity_id
            and anchor.epoch == intent.learning_epoch
            and anchor.full_fingerprint == intent.fingerprint
        )
        return set(source_keys) == set(intent.source_sample_keys) and len(
            source_keys
        ) == len(intent.source_sample_keys)
    source_key = intent.source_sample_keys[0]
    return any(
        anchor.identity_id == identity_id
        and anchor.epoch == intent.learning_epoch
        and anchor.anchor.sample_key == source_key
        and anchor.anchor.prefix_fingerprint.digest == intent.fingerprint
        for anchor in state.prefix_anchors
    )


def _find_identity(
    state: ValidatedPersistentState,
    identity: LearningIdentity,
) -> _IdentityState | None:
    key = _identity_key(identity)
    return next(
        (
            candidate
            for candidate in state.identities
            if _identity_key(candidate.identity) == key
        ),
        None,
    )


def _run_and_prepare_transition(
    transition: Transition,
    snapshot: LearningSnapshot,
    analyzed_sample: StoredSample,
    next_global_revision: int,
) -> _PreparedUpdate:
    update = transition(snapshot)
    _validate_update(update, analyzed_sample, snapshot)
    update = _stamp_update(update, next_global_revision)
    return _PreparedUpdate(
        update=update,
        sample=_encode_sample(update.sample),
        candidates_json=_encode_candidates(update.prediction_record.candidates),
        method_champions_json=_encode_method_champions(
            update.prediction_record.method_champions
        ),
    )


def _validate_update(
    update: LearningUpdate,
    analyzed_sample: StoredSample,
    snapshot: LearningSnapshot,
) -> None:
    sample = update.sample
    if sample.sample_key != analyzed_sample.sample_key:
        raise ValueError("transition changed the analyzed sample key")
    if not _same_identity_base(sample.identity, analyzed_sample.identity):
        raise ValueError("transition changed the analyzed sample identity")
    if sample.committed_order is not None:
        raise ValueError("policy sample must not pre-fill committed_order")
    if replace(sample, identity=analyzed_sample.identity) != analyzed_sample:
        raise ValueError("transition changed analyzed sample facts other than learning epoch")
    record = update.prediction_record
    if record.selected.identity != snapshot.identity:
        raise ValueError("prediction record must use transaction-fresh snapshot identity")
    if record.selected.history_revision != snapshot.revision:
        raise ValueError("prediction record must use transaction-fresh snapshot revision")
    if record.selected.profile_key != sample.features.profile_key:
        raise ValueError("prediction record profile must match analyzed sample")
    if update.drift is None:
        if sample.identity.learning_epoch != snapshot.active_epoch:
            raise ValueError("sample epoch must match active epoch without drift")
    else:
        drift = update.drift
        if not _same_identity_base(drift.identity, snapshot.identity):
            raise ValueError("drift identity must match transaction-fresh snapshot")
        if drift.previous_epoch != snapshot.active_epoch:
            raise ValueError("drift must advance from transaction-fresh active epoch")
        if drift.new_epoch != sample.identity.learning_epoch:
            raise ValueError("drift epoch must match stored sample epoch")
    _validate_sample_logical(sample)
    if update.drift is not None and not isinstance(
        update.prefix_checkpoint_command, NoPrefixCheckpointChange
    ):
        raise ValueError("drift requires NoPrefixCheckpointChange")
    _validate_prefix_checkpoint_command(update.prefix_checkpoint_command)


def _validate_prefix_checkpoint_command(command: PrefixCheckpointCommand) -> None:
    if type(command) is NoPrefixCheckpointChange:
        return
    if type(command) is ReplacePrefixCheckpoint:
        ReplacePrefixCheckpoint(
            command.profile_key,
            command.mode,
            command.evidence,
            command.expected_prior_state_revision,
        )
        return
    if type(command) is DeleteRecoveredPrefixCheckpoint:
        DeleteRecoveredPrefixCheckpoint(
            command.profile_key,
            command.expected_prior_state_revision,
        )
        return
    raise ValueError("prefix checkpoint command must be a closed logical variant")


def _stamp_update(update: LearningUpdate, next_global_revision: int) -> LearningUpdate:
    sample = replace(update.sample, committed_order=next_global_revision)
    command = update.prefix_checkpoint_command
    if isinstance(command, ReplacePrefixCheckpoint):
        evidence = tuple(
            PrefixChampionErrorTriple.from_pending(value, next_global_revision)
            if isinstance(value, PendingPrefixChampionErrorTriple)
            else value
            for value in command.evidence
        )
        command = ReplacePrefixCheckpoint(
            command.profile_key,
            command.mode,
            evidence,
            command.expected_prior_state_revision,
        )
    return replace(update, sample=sample, prefix_checkpoint_command=command)


def _pruned_observation(
    update: LearningUpdate,
    revision: int,
    checkpoint_outcome: PrefixCheckpointStoreOutcome,
) -> TokenLearningObservation:
    return TokenLearningObservation(
        sample_key=update.sample.sample_key,
        outcome="committed",
        reason_code=LearningReasonCode.PRUNED,
        metadata=PrunedMetadata(1),
        prefix_checkpoint_outcome=checkpoint_outcome,
        evaluations=update.evaluations,
        revision=revision,
        learning_epoch=update.sample.identity.learning_epoch,
        drift=update.drift,
    )


def _encode_sample(sample: StoredSample) -> _EncodedSample:
    if sample.committed_order is None:
        raise ValueError("sample codec requires a positive committed_order")
    profile_key_json = _encode_json(
        _profile_payload(sample.features.profile_key),
        "profile key",
    )
    return _EncodedSample(
        components_json=_encode_json(
            [
                {
                    "kind": component.kind,
                    "tokens": component.tokens,
                    "instances": component.instances,
                }
                for component in sample.features.components
            ],
            "token components",
        ),
        profile_key_json=profile_key_json,
        profile_key_hash=hashlib.sha256(
            profile_key_json.encode("utf-8")
        ).hexdigest(),
        feature_vector_json=_encode_json(
            [
                {
                    "name": feature.name.value,
                    "present": feature.present,
                    "value": feature.value,
                }
                for feature in sample.features.feature_vector.values
            ],
            "feature vector",
        ),
        prefix_fingerprints_json=_encode_json(
            [prefix.digest for prefix in sample.features.prefix_fingerprints],
            "prefix fingerprints",
        ),
        fixed_context_contribution_json=_encode_json(
            [
                sample.features.fixed_context_contribution.visible_tokens,
                sample.features.fixed_context_contribution.framing_tokens,
                sample.features.fixed_context_contribution.prior_residual_tokens,
            ],
            "fixed context contribution",
        ),
        input_item_contributions_json=_encode_json(
            [
                [
                    contribution.visible_tokens,
                    contribution.item_framing_tokens,
                    contribution.nested_framing_tokens,
                    contribution.capability_visual_tokens,
                    contribution.prior_residual_tokens,
                ]
                for contribution in sample.features.input_item_contributions
            ],
            "input item contributions",
        ),
        low_confidence_reasons_json=_encode_json(
            list(sample.features.low_confidence_reasons),
            "low-confidence reasons",
        ),
    )


def _encode_candidates(candidates: tuple[TokenPrediction, ...]) -> str:
    return _encode_json(
        [
            {
                "method": candidate.candidate_key.method.value,
                "variant": candidate.candidate_key.variant.value,
                "unscaled_tokens": candidate.unscaled_tokens,
                "sample_count": candidate.sample_count,
                "low_confidence_reasons": list(
                    candidate.low_confidence_reasons
                ),
            }
            for candidate in candidates
        ],
        "prediction candidates",
    )


def _encode_method_champions(champions: tuple[MethodChampion, ...]) -> str:
    champion_by_method = {champion.method: champion for champion in champions}
    return _encode_json(
        [
            {
                "method": method.value,
                "variant": champion_by_method[method].candidate_key.variant.value,
                "eligible_for_selection": champion_by_method[method].eligible_for_selection,
            }
            for method in PredictionMethod
            if method in champion_by_method
        ],
        "method champions",
    )


def _decode_method_champions(value: object) -> tuple[MethodChampion, ...]:
    champions: list[MethodChampion] = []
    for raw in _decode_json_list(value, "method champions"):
        item = _require_mapping(raw, "method champion")
        _require_exact_keys(
            item,
            {"method", "variant", "eligible_for_selection"},
            "method champion",
        )
        method = PredictionMethod(_as_str("champion method", item["method"]))
        champions.append(
            MethodChampion(
                PredictionCandidateKey(
                    method,
                    PredictionCandidateVariant(_as_str("champion variant", item["variant"])),
                ),
                _as_bool("champion eligibility", item["eligible_for_selection"]),
            )
        )
    if tuple(champion.method for champion in champions) != tuple(
        method for method in PredictionMethod if any(value.method is method for value in champions)
    ):
        raise ValueError("method champions must use canonical method order")
    return tuple(champions)


def _decode_prediction_record(
    sample_key: SampleKey,
    identity: LearningIdentity,
    profile: ProfileKey,
    selected_method_value: str,
    selected_variant_value: str,
    history_revision: int,
    method_champions_value: object,
    candidates_value: object,
) -> PredictionRecord:
    payload = _decode_json_list(candidates_value, "prediction candidates")
    candidates: list[TokenPrediction] = []
    for value in payload:
        candidate = _require_mapping(value, "prediction candidate")
        _require_exact_keys(
            candidate,
            {
                "method",
                "variant",
                "unscaled_tokens",
                "sample_count",
                "low_confidence_reasons",
            },
            "prediction candidate",
        )
        method = PredictionMethod(_as_str("candidate method", candidate["method"]))
        candidates.append(
            TokenPrediction(
                identity=identity,
                profile_key=profile,
                method=method,
                candidate_key=PredictionCandidateKey(
                    method,
                    PredictionCandidateVariant(
                        _as_str("candidate variant", candidate["variant"])
                    ),
                ),
                unscaled_tokens=_as_number(
                    "candidate unscaled_tokens",
                    candidate["unscaled_tokens"],
                ),
                sample_count=_as_nonnegative_int(
                    "candidate sample_count",
                    candidate["sample_count"],
                ),
                history_revision=history_revision,
                learning_epoch=identity.learning_epoch,
                low_confidence_reasons=_as_string_tuple_value(
                    candidate["low_confidence_reasons"],
                    "candidate low-confidence reasons",
                ),
            )
        )
    selected_key = PredictionCandidateKey(
        PredictionMethod(selected_method_value),
        PredictionCandidateVariant(selected_variant_value),
    )
    return PredictionRecord(
        sample_key,
        selected_key,
        tuple(candidates),
        _decode_method_champions(method_champions_value),
    )


def _encode_evaluations(
    evaluations: tuple[PredictionEvaluation, ...],
) -> str:
    return _encode_json(
        [
            {
                "sample_key": list(evaluation.sample_key),
                "method": evaluation.method.value,
                "variant": evaluation.candidate_key.variant.value,
                "predicted_tokens": evaluation.predicted_tokens,
                "actual_tokens": evaluation.actual_tokens,
                "absolute_error": evaluation.absolute_error,
                "signed_relative_error": evaluation.signed_relative_error,
                "absolute_percentage_error": evaluation.absolute_percentage_error,
            }
            for evaluation in evaluations
        ],
        "prediction evaluations",
    )


def _decode_event_evaluations(
    value: object,
) -> tuple[PredictionEvaluation, ...]:
    payload = _decode_json_list(value, "event evaluations")
    evaluations: list[PredictionEvaluation] = []
    for value in payload:
        item = _require_mapping(value, "event evaluation")
        _require_exact_keys(
            item,
            {
                "sample_key",
                "method",
                "variant",
                "predicted_tokens",
                "actual_tokens",
                "absolute_error",
                "signed_relative_error",
                "absolute_percentage_error",
            },
            "event evaluation",
        )
        sample_values = item["sample_key"]
        if not isinstance(sample_values, list):
            raise ValueError("event evaluation sample key is invalid")
        sample_items = cast(list[object], sample_values)
        if len(sample_items) != 3:
            raise ValueError("event evaluation sample key is invalid")
        method = PredictionMethod(_as_str("evaluation method", item["method"]))
        evaluations.append(
            PredictionEvaluation(
                sample_key=(
                    _as_str("evaluation process_boot_id", sample_items[0]),
                    _as_str("evaluation request_id", sample_items[1]),
                    _as_nonnegative_int(
                        "evaluation attempt_index",
                        sample_items[2],
                    ),
                ),
                method=method,
                candidate_key=PredictionCandidateKey(
                    method,
                    PredictionCandidateVariant(_as_str("evaluation variant", item["variant"])),
                ),
                predicted_tokens=_as_number(
                    "evaluation predicted_tokens",
                    item["predicted_tokens"],
                ),
                actual_tokens=_as_nonnegative_int(
                    "evaluation actual_tokens",
                    item["actual_tokens"],
                ),
                absolute_error=_as_nonnegative_number(
                    "evaluation absolute_error",
                    item["absolute_error"],
                ),
                signed_relative_error=(
                    None
                    if item["signed_relative_error"] is None
                    else _as_number(
                        "evaluation signed_relative_error",
                        item["signed_relative_error"],
                    )
                ),
                absolute_percentage_error=(
                    None
                    if item["absolute_percentage_error"] is None
                    else _as_nonnegative_number(
                        "evaluation absolute_percentage_error",
                        item["absolute_percentage_error"],
                    )
                ),
            )
        )
    return tuple(evaluations)


def _encode_learning_metadata(
    reason: LearningReasonCode,
    metadata: LearningReasonMetadata,
) -> str:
    if reason is LearningReasonCode.SAMPLE_COMMITTED:
        value = {
            "actual_input_tokens": cast(
                SampleCommittedMetadata,
                metadata,
            ).actual_input_tokens
        }
    elif reason is LearningReasonCode.DUPLICATE_SAMPLE:
        value = {
            "existing_revision": cast(
                DuplicateSampleMetadata,
                metadata,
            ).existing_revision
        }
    elif reason is LearningReasonCode.QUEUE_FULL:
        queue = cast(QueueFullMetadata, metadata)
        value = {
            "pending_items": queue.pending_items,
            "pending_body_bytes": queue.pending_body_bytes,
        }
    elif reason is LearningReasonCode.ANALYSIS_FAILED:
        value = {
            "stage": cast(AnalysisFailedMetadata, metadata).stage.value
        }
    elif reason is LearningReasonCode.OPERATION_CANCELLED:
        value = {
            "phase": cast(OperationCancelledMetadata, metadata).phase.value
        }
    elif reason is LearningReasonCode.PRUNED:
        value = {
            "pruned_sample_count": cast(
                PrunedMetadata,
                metadata,
            ).pruned_sample_count
        }
    else:
        value = {}
    return _encode_json(value, "learning reason metadata")


def _encode_prefix_checkpoint_outcome(outcome: PrefixCheckpointStoreOutcome) -> str:
    if isinstance(outcome, NoPrefixCheckpointChange):
        value: dict[str, object] = {"kind": "no-change"}
    elif isinstance(outcome, PrefixCheckpointApplied):
        value = {
            "kind": "applied",
            "profile_key": _profile_payload(outcome.profile_key),
            "state_revision": outcome.state_revision,
            "updated_order": outcome.updated_order,
        }
    elif isinstance(outcome, PrefixCheckpointDeleted):
        value = {
            "kind": "deleted",
            "profile_key": _profile_payload(outcome.profile_key),
            "state_revision": outcome.state_revision,
            "updated_order": outcome.updated_order,
        }
    elif isinstance(outcome, PrefixCheckpointNotAttempted):
        value = {"kind": "not-attempted", "reason": outcome.reason.value}
    elif isinstance(outcome, PrefixCheckpointNotCommitted):
        value = {"kind": "not-committed"}
    elif isinstance(outcome, PrefixCheckpointCapacityRejected):
        value = {
            "kind": "capacity-rejected",
            "profile_key": _profile_payload(outcome.profile_key),
            "reason": outcome.reason.value,
        }
    else:
        value = {
            "kind": "capacity-rolled-over",
            "profile_key": _profile_payload(outcome.profile_key),
            "previous_epoch": outcome.previous_epoch,
            "new_epoch": outcome.new_epoch,
            "reason": outcome.reason.value,
        }
    return _encode_json(value, "prefix checkpoint outcome")


def _decode_prefix_checkpoint_outcome(value: object) -> PrefixCheckpointStoreOutcome:
    payload = _require_mapping(_decode_json(value, "prefix checkpoint outcome"), "prefix checkpoint outcome")
    kind = _as_str("prefix checkpoint outcome kind", payload.get("kind"))
    if kind == "no-change":
        _require_exact_keys(payload, {"kind"}, "prefix checkpoint outcome")
        return NoPrefixCheckpointChange()
    if kind == "not-attempted":
        _require_exact_keys(payload, {"kind", "reason"}, "prefix checkpoint outcome")
        return PrefixCheckpointNotAttempted(
            PrefixCheckpointNotAttemptedReason(_as_str("prefix checkpoint skipped reason", payload["reason"]))
        )
    if kind == "not-committed":
        _require_exact_keys(payload, {"kind"}, "prefix checkpoint outcome")
        return PrefixCheckpointNotCommitted()
    if kind == "capacity-rejected":
        _require_exact_keys(
            payload, {"kind", "profile_key", "reason"}, "prefix checkpoint outcome"
        )
        return PrefixCheckpointCapacityRejected(
            _decode_profile(_encode_json(payload["profile_key"], "prefix checkpoint outcome profile")),
            PrefixCheckpointCapacityReason(
                _as_str("prefix checkpoint capacity reason", payload["reason"])
            ),
        )
    if kind == "capacity-rolled-over":
        _require_exact_keys(
            payload,
            {"kind", "profile_key", "previous_epoch", "new_epoch", "reason"},
            "prefix checkpoint outcome",
        )
        return PrefixCheckpointCapacityRolledOver(
            _decode_profile(_encode_json(payload["profile_key"], "prefix checkpoint outcome profile")),
            _as_nonnegative_int("prefix checkpoint previous epoch", payload["previous_epoch"]),
            _as_nonnegative_int("prefix checkpoint new epoch", payload["new_epoch"]),
            PrefixCheckpointCapacityReason(
                _as_str("prefix checkpoint capacity reason", payload["reason"])
            ),
        )
    if kind in {"applied", "deleted"}:
        _require_exact_keys(
            payload,
            {"kind", "profile_key", "state_revision", "updated_order"},
            "prefix checkpoint outcome",
        )
        arguments = (
            _decode_profile(_encode_json(payload["profile_key"], "prefix checkpoint outcome profile")),
            _as_positive_int("prefix checkpoint outcome state revision", payload["state_revision"]),
            _as_positive_int("prefix checkpoint outcome updated order", payload["updated_order"]),
        )
        return PrefixCheckpointApplied(*arguments) if kind == "applied" else PrefixCheckpointDeleted(*arguments)
    raise ValueError("prefix checkpoint outcome kind is unsupported")


def _decode_learning_metadata(
    reason: LearningReasonCode,
    value: object,
) -> LearningReasonMetadata:
    payload = _require_mapping(
        _decode_json(value, "learning reason metadata"),
        "learning reason metadata",
    )
    if reason is LearningReasonCode.SAMPLE_COMMITTED:
        _require_exact_keys(payload, {"actual_input_tokens"}, "sample committed metadata")
        return SampleCommittedMetadata(
            _as_nonnegative_int(
                "metadata actual_input_tokens",
                payload["actual_input_tokens"],
            )
        )
    if reason is LearningReasonCode.DUPLICATE_SAMPLE:
        _require_exact_keys(payload, {"existing_revision"}, "duplicate metadata")
        return DuplicateSampleMetadata(
            _as_nonnegative_int(
                "metadata existing_revision",
                payload["existing_revision"],
            )
        )
    if reason is LearningReasonCode.QUEUE_FULL:
        _require_exact_keys(
            payload,
            {"pending_items", "pending_body_bytes"},
            "queue-full metadata",
        )
        return QueueFullMetadata(
            _as_nonnegative_int("pending_items", payload["pending_items"]),
            _as_nonnegative_int(
                "pending_body_bytes",
                payload["pending_body_bytes"],
            ),
        )
    if reason is LearningReasonCode.ANALYSIS_FAILED:
        _require_exact_keys(payload, {"stage"}, "analysis-failed metadata")
        return AnalysisFailedMetadata(
            AnalysisFailureStage(_as_str("analysis stage", payload["stage"]))
        )
    if reason is LearningReasonCode.OPERATION_CANCELLED:
        _require_exact_keys(payload, {"phase"}, "operation-cancelled metadata")
        return OperationCancelledMetadata(
            StoreCancellationPhase(
                _as_str("cancellation phase", payload["phase"])
            )
        )
    if reason is LearningReasonCode.PRUNED:
        _require_exact_keys(payload, {"pruned_sample_count"}, "pruned metadata")
        return PrunedMetadata(
            _as_nonnegative_int(
                "pruned_sample_count",
                payload["pruned_sample_count"],
            )
        )
    _require_exact_keys(payload, set(), "empty learning metadata")
    if reason is LearningReasonCode.SAMPLE_INELIGIBLE:
        return SampleIneligibleMetadata()
    if reason is LearningReasonCode.MISSING_USAGE:
        return MissingUsageMetadata()
    if reason is LearningReasonCode.INCONSISTENT_USAGE:
        return InconsistentUsageMetadata()
    if reason is LearningReasonCode.STORE_UNAVAILABLE:
        return StoreUnavailableMetadata()
    if reason is LearningReasonCode.MIGRATION_FAILED:
        return MigrationFailedMetadata()
    return CommitFailedMetadata()


def _encode_drift_metadata(drift: DriftObservation) -> str:
    if drift.reason_code is DriftReasonCode.PROFILE_ERROR_REGRESSION:
        metadata = cast(ProfileErrorRegressionMetadata, drift.metadata)
        value = {
            "kind": drift.kind,
            "identity_epoch": drift.identity.learning_epoch,
            "previous_epoch": drift.previous_epoch,
            "new_epoch": drift.new_epoch,
            "evidence_count": drift.evidence_count,
            "reference_count": metadata.reference_count,
            "recent_count": metadata.recent_count,
        }
    elif drift.reason_code is DriftReasonCode.EXACT_COUNT_MISMATCH:
        metadata = cast(ExactCountMismatchMetadata, drift.metadata)
        value = {
            "kind": drift.kind,
            "identity_epoch": drift.identity.learning_epoch,
            "previous_epoch": drift.previous_epoch,
            "new_epoch": drift.new_epoch,
            "evidence_count": drift.evidence_count,
            "consecutive_count": metadata.consecutive_count,
        }
    else:
        metadata = cast(IdentityVersionChangeMetadata, drift.metadata)
        value = {
            "kind": drift.kind,
            "identity_epoch": drift.identity.learning_epoch,
            "previous_epoch": drift.previous_epoch,
            "new_epoch": drift.new_epoch,
            "evidence_count": drift.evidence_count,
            "previous_generation": metadata.previous_generation,
            "new_generation": metadata.new_generation,
        }
    return _encode_json(value, "drift metadata")


def _decode_drift(
    identity: LearningIdentity,
    reason: DriftReasonCode,
    value: object,
) -> DriftObservation:
    payload = _require_mapping(
        _decode_json(value, "drift metadata"),
        "drift metadata",
    )
    common = {
        "kind",
        "identity_epoch",
        "previous_epoch",
        "new_epoch",
        "evidence_count",
    }
    if reason is DriftReasonCode.PROFILE_ERROR_REGRESSION:
        _require_exact_keys(
            payload,
            common | {"reference_count", "recent_count"},
            "profile drift metadata",
        )
        metadata = ProfileErrorRegressionMetadata(
            _as_nonnegative_int("reference_count", payload["reference_count"]),
            _as_nonnegative_int("recent_count", payload["recent_count"]),
        )
    elif reason is DriftReasonCode.EXACT_COUNT_MISMATCH:
        _require_exact_keys(
            payload,
            common | {"consecutive_count"},
            "exact drift metadata",
        )
        metadata = ExactCountMismatchMetadata(
            _as_nonnegative_int(
                "consecutive_count",
                payload["consecutive_count"],
            )
        )
    else:
        _require_exact_keys(
            payload,
            common | {"previous_generation", "new_generation"},
            "identity drift metadata",
        )
        metadata = IdentityVersionChangeMetadata(
            _as_positive_int(
                "previous_generation",
                payload["previous_generation"],
            ),
            _as_positive_int(
                "new_generation",
                payload["new_generation"],
            ),
        )
    identity_epoch = _as_nonnegative_int(
        "identity_epoch",
        payload["identity_epoch"],
    )
    previous_epoch = _as_nonnegative_int(
        "previous_epoch",
        payload["previous_epoch"],
    )
    return DriftObservation(
        identity=replace(identity, learning_epoch=identity_epoch),
        kind=cast(Any, _as_str("drift kind", payload["kind"])),
        previous_epoch=previous_epoch,
        new_epoch=_as_nonnegative_int("new_epoch", payload["new_epoch"]),
        evidence_count=_as_nonnegative_int(
            "evidence_count",
            payload["evidence_count"],
        ),
        reason_code=reason,
        metadata=metadata,
    )


def _encode_json(value: object, name: str) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(encoded.encode("utf-8")) > _MAX_JSON_BYTES:
        raise ValueError(f"{name} exceeds the {_MAX_JSON_BYTES}-byte storage limit")
    return encoded


def _decode_json(value: object, name: str) -> object:
    text = _as_str(name, value)
    if len(text.encode("utf-8")) > _MAX_JSON_BYTES:
        raise ValueError(f"stored {name} exceeds the {_MAX_JSON_BYTES}-byte limit")
    return json.loads(text)


def _decode_json_list(value: object, name: str) -> list[object]:
    decoded = _decode_json(value, name)
    if not isinstance(decoded, list):
        raise ValueError(f"stored {name} must be a list")
    return cast(list[object], decoded)


def _decode_components(value: object) -> tuple[TokenComponent, ...]:
    result: list[TokenComponent] = []
    for item in _decode_json_list(value, "token components"):
        payload = _require_mapping(item, "token component")
        _require_exact_keys(payload, {"kind", "tokens", "instances"}, "token component")
        result.append(
            TokenComponent(
                _as_str("component kind", payload["kind"]),
                _as_nonnegative_int("component tokens", payload["tokens"]),
                _as_nonnegative_int(
                    "component instances",
                    payload["instances"],
                ),
            )
        )
    return tuple(result)


def _profile_payload(profile: ProfileKey) -> dict[str, object]:
    return {
        "item_kinds": list(profile.item_kinds),
        "reasoning_origins": list(profile.reasoning_origins),
        "media_kinds": list(profile.media_kinds),
        "unknown_type_digests": list(profile.unknown_type_digests),
        "unknown_type_count": profile.unknown_type_count,
        "unknown_type_overflow": profile.unknown_type_overflow,
        "has_previous_response_id": profile.has_previous_response_id,
        "context_management_mode": profile.context_management_mode,
        "truncation_mode": profile.truncation_mode,
    }


def _decode_profile(value: object) -> ProfileKey:
    payload = _require_mapping(_decode_json(value, "profile key"), "profile key")
    _require_exact_keys(
        payload,
        {
            "item_kinds",
            "reasoning_origins",
            "media_kinds",
            "unknown_type_digests",
            "unknown_type_count",
            "unknown_type_overflow",
            "has_previous_response_id",
            "context_management_mode",
            "truncation_mode",
        },
        "profile key",
    )
    return ProfileKey(
        item_kinds=_as_string_tuple_value(payload["item_kinds"], "item_kinds"),
        reasoning_origins=_as_string_tuple_value(
            payload["reasoning_origins"],
            "reasoning_origins",
        ),
        media_kinds=_as_string_tuple_value(payload["media_kinds"], "media_kinds"),
        unknown_type_digests=_as_string_tuple_value(
            payload["unknown_type_digests"],
            "unknown_type_digests",
        ),
        unknown_type_count=_as_nonnegative_int(
            "unknown_type_count",
            payload["unknown_type_count"],
        ),
        unknown_type_overflow=_as_bool(
            "unknown_type_overflow",
            payload["unknown_type_overflow"],
        ),
        has_previous_response_id=_as_bool(
            "has_previous_response_id",
            payload["has_previous_response_id"],
        ),
        context_management_mode=_as_str(
            "context_management_mode",
            payload["context_management_mode"],
        ),
        truncation_mode=_as_str(
            "truncation_mode",
            payload["truncation_mode"],
        ),
    )


def _decode_feature_vector(value: object) -> FeatureVector:
    values: list[FeatureValue] = []
    for item in _decode_json_list(value, "feature vector"):
        payload = _require_mapping(item, "feature value")
        _require_exact_keys(payload, {"name", "present", "value"}, "feature value")
        values.append(
            FeatureValue(
                FeatureName(_as_str("feature name", payload["name"])),
                _as_bool("feature present", payload["present"]),
                _as_nonnegative_int("feature value", payload["value"]),
            )
        )
    return FeatureVector(tuple(values))


def _decode_prefix_fingerprints(
    value: object,
) -> tuple[PrefixFingerprint, ...]:
    return tuple(
        PrefixFingerprint(index, _as_str("prefix digest", item))
        for index, item in enumerate(
            _decode_json_list(value, "prefix fingerprints"), start=1
        )
    )


def _decode_fixed_context_contribution(value: object) -> FixedContextContribution:
    parts = _decode_json_list(value, "fixed context contribution")
    if len(parts) != 3:
        raise ValueError("fixed context contribution must have compact arity three")
    return FixedContextContribution(
        _as_nonnegative_int("fixed context visible tokens", parts[0]),
        _as_nonnegative_int("fixed context framing tokens", parts[1]),
        _as_number("fixed context prior residual", parts[2]),
    )


def _decode_input_item_contributions(value: object) -> tuple[InputItemContribution, ...]:
    result: list[InputItemContribution] = []
    for raw in _decode_json_list(value, "input item contributions"):
        if not isinstance(raw, list):
            raise ValueError("input item contribution must have compact arity five")
        parts = cast(list[object], raw)
        if len(parts) != 5:
            raise ValueError("input item contribution must have compact arity five")
        result.append(
            InputItemContribution(
                _as_nonnegative_int("item visible tokens", parts[0]),
                _as_nonnegative_int("item framing tokens", parts[1]),
                _as_nonnegative_int("item nested framing tokens", parts[2]),
                None if parts[3] is None else _as_nonnegative_int("item visual tokens", parts[3]),
                _as_number("item prior residual", parts[4]),
            )
        )
    return tuple(result)


def _decode_string_tuple(value: object, name: str) -> tuple[str, ...]:
    return _as_string_tuple_value(_decode_json(value, name), name)


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    mapping = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        raise ValueError(f"{name} keys must be strings")
    return cast(Mapping[str, object], mapping)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    name: str,
) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} has an unsupported field set")


def _as_string_tuple_value(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"{name} must contain strings")
    return tuple(cast(list[str], items))


def _decode_outcome(value: object) -> Any:
    text = _as_str("event outcome", value)
    if text not in ("committed", "duplicate", "rejected", "failed"):
        raise ValueError("event outcome is unsupported")
    return text


def _identity_key(identity: LearningIdentity) -> _IdentityKey:
    return (
        identity.actual_provider,
        identity.resolved_model,
        identity.endpoint,
        identity.wire_format,
        identity.tokenizer,
        identity.descriptor_fingerprint,
        identity.estimator_generation,
        identity.profile_schema_revision,
    )


def _identity_binary_key(identity: LearningIdentity) -> tuple[object, ...]:
    return (
        identity.actual_provider.encode("utf-8"),
        identity.resolved_model.encode("utf-8"),
        identity.endpoint.encode("utf-8"),
        identity.wire_format.encode("utf-8"),
        identity.tokenizer.encode("utf-8"),
        identity.descriptor_fingerprint.encode("ascii"),
        identity.estimator_generation,
        identity.profile_schema_revision,
    )


def _same_identity_base(first: LearningIdentity, second: LearningIdentity) -> bool:
    return _identity_key(first) == _identity_key(second)


def _identity_bucket_key(identity: LearningIdentity) -> str:
    payload = _encode_json(
        [*_identity_key(identity), identity.learning_epoch],
        "learning identity",
    )
    return f"identity:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _unresolved_bucket_key(identity: UnresolvedLearningIdentity) -> str:
    payload = _encode_json(
        [
            identity.actual_provider,
            identity.endpoint,
            identity.estimator_generation,
        ],
        "unresolved learning identity",
    )
    return f"unresolved:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _unresolved_from_identity(
    identity: LearningIdentity,
) -> UnresolvedLearningIdentity:
    return UnresolvedLearningIdentity(
        identity.actual_provider,
        identity.endpoint,
        identity.estimator_generation,
    )


def _empty_snapshot(identity: LearningIdentity) -> LearningSnapshot:
    return LearningSnapshot(identity, 0, identity.learning_epoch)


def _sample_key_binary(sample_key: SampleKey) -> tuple[bytes, bytes, int]:
    return (
        sample_key[0].encode("utf-8"),
        sample_key[1].encode("utf-8"),
        sample_key[2],
    )


def _newest_key_for_sample_key(sample_key: SampleKey) -> tuple[object, ...]:
    return (
        _DescendingBytes(sample_key[0].encode("utf-8")),
        _DescendingBytes(sample_key[1].encode("utf-8")),
        -sample_key[2],
    )


def _newest_sample_sort_key(sample: StoredSample) -> tuple[object, ...]:
    return (
        -sample.observed_at_us,
        *_newest_key_for_sample_key(sample.sample_key),
    )


@dataclass(frozen=True, slots=True)
class _DescendingBytes:
    value: bytes

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, _DescendingBytes):
            return NotImplemented
        return self.value > other.value


def _validate_identity(identity: LearningIdentity) -> None:
    for name, value in (
        ("actual_provider", identity.actual_provider),
        ("resolved_model", identity.resolved_model),
        ("endpoint", identity.endpoint),
        ("wire_format", identity.wire_format),
        ("tokenizer", identity.tokenizer),
    ):
        _require_bounded_text(name, value, _MAX_IDENTITY_TEXT_BYTES)


def _validate_sample_logical(sample: StoredSample) -> None:
    _validate_identity(sample.identity)
    _require_bounded_text(
        "process_boot_id",
        sample.sample_key[0],
        _MAX_SAMPLE_KEY_TEXT_BYTES,
    )
    _require_bounded_text(
        "request_id",
        sample.sample_key[1],
        _MAX_SAMPLE_KEY_TEXT_BYTES,
    )


def _validate_sample_for_storage(sample: StoredSample) -> None:
    _validate_sample_logical(sample)
    if sample.committed_order is None:
        raise ValueError("persistent sample requires positive committed_order")
    _encode_sample(sample)


def _validate_observation_for_storage(
    observation: TokenLearningObservation,
) -> None:
    _require_bounded_text(
        "process_boot_id",
        observation.sample_key[0],
        _MAX_SAMPLE_KEY_TEXT_BYTES,
    )
    _require_bounded_text(
        "request_id",
        observation.sample_key[1],
        _MAX_SAMPLE_KEY_TEXT_BYTES,
    )
    if any(
        evaluation.sample_key != observation.sample_key
        for evaluation in observation.evaluations
    ):
        raise ValueError("event evaluations must match observation sample key")
    _encode_learning_metadata(observation.reason_code, observation.metadata)
    _encode_evaluations(observation.evaluations)
    if observation.drift is not None:
        _encode_drift_metadata(observation.drift)



def _require_bounded_text(name: str, value: str, byte_limit: int) -> None:
    if not value:
        raise ValueError(f"{name} must be non-empty")
    if len(value.encode("utf-8")) > byte_limit:
        raise ValueError(f"{name} exceeds the {byte_limit}-byte storage limit")


def _as_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    return value


def _as_bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")
    return value


def _as_int(name: str, value: object) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def _as_nonnegative_int(name: str, value: object) -> int:
    result = _as_int(name, value)
    if result < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return result


def _as_positive_int(name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _as_number(name: str, value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be numeric")
    result = float(cast(int | float, value))
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _as_nonnegative_number(name: str, value: object) -> float:
    result = _as_number(name, value)
    if result < 0:
        raise ValueError(f"{name} must be nonnegative")
    return result


def _now_us() -> int:
    return time.time_ns() // 1_000


def _is_busy(error: sqlite3.OperationalError) -> bool:
    code = getattr(error, "sqlite_errorcode", None)
    primary = None if code is None else code & 0xFF
    return primary in {
        sqlite3.SQLITE_BUSY,
        sqlite3.SQLITE_LOCKED,
    } or "locked" in str(error).lower()


def _chunks(
    values: tuple[int, ...],
    size: int,
) -> Iterable[tuple[int, ...]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _quote_pragma_name(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise ValueError("invalid PRAGMA object name")
    return f'"{value}"'


def _normalize_sql(value: str) -> str:
    return " ".join(value.strip().split())


def _normalize_ddl_v1(sql: str) -> str:
    tokens: list[str] = []
    index = 0
    while index < len(sql):
        character = sql[index]
        if character.isspace():
            index += 1
            continue
        if character in ("'", '"', "`", "["):
            closing = "]" if character == "[" else character
            start = index
            index += 1
            while index < len(sql):
                if sql[index] == closing:
                    if (
                        closing != "]"
                        and index + 1 < len(sql)
                        and sql[index + 1] == closing
                    ):
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            tokens.append(sql[start:index])
            continue
        if character.isalnum() or character in ("_", "$", "."):
            start = index
            while index < len(sql) and (
                sql[index].isalnum() or sql[index] in ("_", "$", ".")
            ):
                index += 1
            tokens.append(sql[start:index].lower())
            continue
        operator = sql[index : index + 2]
        if operator in ("<=", ">=", "!=", "<>", "||", "=="):
            tokens.append(operator)
            index += 2
            continue
        tokens.append(character)
        index += 1
    return " ".join(tokens)


def _extract_checks(sql: str) -> tuple[str, ...]:
    result: list[str] = []
    upper = sql.upper()
    offset = 0
    while True:
        index = upper.find("CHECK", offset)
        if index < 0:
            break
        cursor = index + len("CHECK")
        while cursor < len(sql) and sql[cursor].isspace():
            cursor += 1
        if cursor >= len(sql) or sql[cursor] != "(":
            offset = cursor
            continue
        depth = 1
        start = cursor + 1
        cursor += 1
        quote: str | None = None
        while cursor < len(sql) and depth:
            character = sql[cursor]
            if quote is not None:
                if character == quote:
                    if cursor + 1 < len(sql) and sql[cursor + 1] == quote:
                        cursor += 1
                    else:
                        quote = None
            elif character in ("'", '"'):
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            cursor += 1
        if depth != 0:
            raise ValueError("unbalanced CHECK expression")
        result.append(_normalize_sql(sql[start : cursor - 1]))
        offset = cursor
    return tuple(result)


def _foreign_key_sort_key(value: ForeignKeyManifest) -> tuple[object, ...]:
    return (
        value.parent_table,
        value.from_columns,
        value.to_columns,
        value.on_update,
        value.on_delete,
        value.match,
    )
