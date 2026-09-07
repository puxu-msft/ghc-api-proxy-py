from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ColumnManifest:
    name: str
    declared_type: str
    not_null: bool
    default: str | None
    primary_key_position: int


@dataclass(frozen=True, slots=True)
class ForeignKeyManifest:
    parent_table: str
    from_columns: tuple[str, ...]
    to_columns: tuple[str, ...]
    on_update: str = "NO ACTION"
    on_delete: str = "NO ACTION"
    match: str = "NONE"


@dataclass(frozen=True, slots=True)
class TableManifest:
    name: str
    columns: tuple[ColumnManifest, ...]
    checks: tuple[str, ...]
    foreign_keys: tuple[ForeignKeyManifest, ...] = ()
    strict: bool = True
    ddl_digest: str = ""


@dataclass(frozen=True, slots=True)
class IndexColumnManifest:
    name: str
    descending: bool = False
    collation: str = "BINARY"


@dataclass(frozen=True, slots=True)
class IndexManifest:
    name: str
    table: str
    unique: bool
    columns: tuple[IndexColumnManifest, ...]
    partial: bool = False


def _column(
    name: str,
    declared_type: str,
    *,
    not_null: bool = True,
    default: str | None = None,
    primary_key_position: int = 0,
) -> ColumnManifest:
    return ColumnManifest(name, declared_type, not_null, default, primary_key_position)


def _index_columns(*names: str) -> tuple[IndexColumnManifest, ...]:
    return tuple(IndexColumnManifest(name.removesuffix(" DESC"), name.endswith(" DESC")) for name in names)


_V1_TABLES_WITHOUT_DDL = (
    TableManifest(
        "schema_meta",
        (
            _column("singleton", "INTEGER", primary_key_position=1),
            _column("version", "INTEGER"),
            _column("manifest_digest", "TEXT"),
            _column("global_revision", "INTEGER", default="0"),
        ),
        (
            "singleton = 1",
            "version = 1",
            "length(manifest_digest) = 64 AND manifest_digest NOT GLOB '*[^0-9a-f]*'",
            "global_revision >= 0",
        ),
    ),
    TableManifest(
        "identity_state",
        (
            _column("identity_id", "INTEGER", not_null=False, primary_key_position=1),
            _column("actual_provider", "TEXT"),
            _column("resolved_model", "TEXT"),
            _column("endpoint", "TEXT"),
            _column("wire_format", "TEXT"),
            _column("tokenizer", "TEXT"),
            _column("descriptor_fingerprint", "TEXT"),
            _column("estimator_generation", "INTEGER"),
            _column("profile_schema_revision", "INTEGER"),
            _column("active_epoch", "INTEGER"),
            _column("revision", "INTEGER", default="0"),
        ),
        (
            "estimator_generation >= 1",
            "profile_schema_revision >= 1",
            "active_epoch >= 0",
            "revision >= 0",
        ),
    ),
    TableManifest(
        "epoch_state",
        (
            _column("identity_id", "INTEGER", primary_key_position=1),
            _column("epoch", "INTEGER", primary_key_position=2),
            _column("created_order", "INTEGER"),
        ),
        ("epoch >= 0", "created_order >= 0"),
        (ForeignKeyManifest("identity_state", ("identity_id",), ("identity_id",), on_delete="CASCADE"),),
    ),
    TableManifest(
        "samples",
        (
            _column("sample_id", "INTEGER", not_null=False, primary_key_position=1),
            _column("identity_id", "INTEGER"),
            _column("epoch", "INTEGER"),
            _column("process_boot_id", "TEXT"),
            _column("request_id", "TEXT"),
            _column("attempt_index", "INTEGER"),
            _column("observed_at_us", "INTEGER"),
            _column("actual_input_tokens", "INTEGER"),
            _column("last_used_order", "INTEGER"),
            _column("raw_body_sha256", "TEXT"),
            _column("feature_raw_body_sha256", "TEXT", not_null=False),
            _column("known_tokens", "INTEGER"),
            _column("capability_visual_tokens", "INTEGER", not_null=False),
            _column("components_json", "TEXT"),
            _column("profile_key_json", "TEXT"),
            _column("profile_key_hash", "TEXT"),
            _column("feature_vector_json", "TEXT"),
            _column("full_fingerprint", "TEXT"),
            _column("context_fingerprint", "TEXT"),
            _column("prefix_fingerprints_json", "TEXT"),
            _column("low_confidence_reasons_json", "TEXT"),
            _column("committed_order", "INTEGER"),
            _column("fixed_context_contribution_json", "TEXT"),
            _column("input_item_contributions_json", "TEXT"),
        ),
        (
            "epoch >= 0",
            "attempt_index >= 0",
            "observed_at_us >= 0",
            "actual_input_tokens >= 0",
            "last_used_order >= 1",
            "known_tokens >= 0",
            "capability_visual_tokens IS NULL OR capability_visual_tokens >= 0",
            "committed_order >= 1",
        ),
        (ForeignKeyManifest("epoch_state", ("identity_id", "epoch"), ("identity_id", "epoch"), on_delete="CASCADE"),),
    ),
    TableManifest(
        "prefix_checkpoints",
        (
            _column("identity_id", "INTEGER", primary_key_position=1),
            _column("epoch", "INTEGER", primary_key_position=2),
            _column("profile_key_json", "TEXT", primary_key_position=3),
            _column("profile_key_hash", "TEXT"),
            _column("mode", "TEXT"),
            _column("evidence_json", "TEXT"),
            _column("state_revision", "INTEGER"),
            _column("updated_order", "INTEGER"),
        ),
        (
            "epoch >= 0",
            "mode IN ('eligible', 'demoted')",
            "state_revision >= 1",
            "updated_order >= 1",
        ),
        (ForeignKeyManifest("epoch_state", ("identity_id", "epoch"), ("identity_id", "epoch"), on_delete="CASCADE"),),
    ),
    TableManifest(
        "prediction_records",
        (
            _column("identity_id", "INTEGER", primary_key_position=1),
            _column("sample_epoch", "INTEGER", primary_key_position=2),
            _column("process_boot_id", "TEXT", primary_key_position=3),
            _column("request_id", "TEXT", primary_key_position=4),
            _column("attempt_index", "INTEGER", primary_key_position=5),
            _column("prediction_epoch", "INTEGER"),
            _column("profile_key_hash", "TEXT"),
            _column("selected_method", "TEXT"),
            _column("selected_variant", "TEXT"),
            _column("history_revision", "INTEGER"),
            _column("method_champions_json", "TEXT"),
            _column("candidates_json", "TEXT"),
        ),
        ("sample_epoch >= 0", "attempt_index >= 0", "prediction_epoch >= 0", "history_revision >= 0"),
        (
            ForeignKeyManifest(
                "samples",
                ("identity_id", "sample_epoch", "process_boot_id", "request_id", "attempt_index"),
                ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"),
                on_delete="CASCADE",
            ),
            ForeignKeyManifest(
                "epoch_state",
                ("identity_id", "prediction_epoch"),
                ("identity_id", "epoch"),
                on_delete="CASCADE",
            ),
        ),
    ),
    TableManifest(
        "evaluations",
        (
            _column("identity_id", "INTEGER", primary_key_position=1),
            _column("sample_epoch", "INTEGER", primary_key_position=2),
            _column("process_boot_id", "TEXT", primary_key_position=3),
            _column("request_id", "TEXT", primary_key_position=4),
            _column("attempt_index", "INTEGER", primary_key_position=5),
            _column("method", "TEXT", primary_key_position=6),
            _column("candidate_variant", "TEXT", primary_key_position=7),
            _column("prediction_epoch", "INTEGER"),
            _column("profile_key_hash", "TEXT"),
            _column("ordinal", "INTEGER"),
            _column("predicted_tokens", "REAL"),
            _column("actual_tokens", "INTEGER"),
            _column("absolute_error", "REAL"),
            _column("signed_relative_error", "REAL", not_null=False),
            _column("absolute_percentage_error", "REAL", not_null=False),
        ),
        (
            "sample_epoch >= 0",
            "attempt_index >= 0",
            "prediction_epoch >= 0",
            "ordinal >= 0",
            "actual_tokens >= 0",
            "absolute_error >= 0",
            "absolute_percentage_error IS NULL OR absolute_percentage_error >= 0",
            "(method = 'history-exact' AND candidate_variant = 'median') OR (method = 'history-prefix' AND candidate_variant IN ('deterministic', 'additive', 'multiplicative')) OR (method = 'profile-calibrated' AND candidate_variant IN ('additive', 'multiplicative')) OR (method = 'cold-start' AND candidate_variant = 'deterministic')",
        ),
        (
            ForeignKeyManifest(
                "samples",
                ("identity_id", "sample_epoch", "process_boot_id", "request_id", "attempt_index"),
                ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"),
                on_delete="CASCADE",
            ),
            ForeignKeyManifest(
                "epoch_state",
                ("identity_id", "prediction_epoch"),
                ("identity_id", "epoch"),
                on_delete="CASCADE",
            ),
        ),
    ),
    TableManifest(
        "exact_anchors",
        (
            _column("identity_id", "INTEGER", primary_key_position=1),
            _column("epoch", "INTEGER", primary_key_position=2),
            _column("process_boot_id", "TEXT", primary_key_position=3),
            _column("request_id", "TEXT", primary_key_position=4),
            _column("attempt_index", "INTEGER", primary_key_position=5),
            _column("full_fingerprint", "TEXT"),
            _column("actual_tokens", "INTEGER"),
        ),
        ("epoch >= 0", "attempt_index >= 0", "actual_tokens >= 0"),
        (
            ForeignKeyManifest(
                "samples",
                ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"),
                ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"),
                on_delete="CASCADE",
            ),
        ),
    ),
    TableManifest(
        "prefix_anchors",
        (
            _column("identity_id", "INTEGER", primary_key_position=1),
            _column("epoch", "INTEGER", primary_key_position=2),
            _column("process_boot_id", "TEXT", primary_key_position=3),
            _column("request_id", "TEXT", primary_key_position=4),
            _column("attempt_index", "INTEGER", primary_key_position=5),
            _column("context_fingerprint", "TEXT"),
            _column("item_count", "INTEGER"),
            _column("prefix_fingerprint", "TEXT"),
            _column("actual_tokens", "INTEGER"),
        ),
        ("epoch >= 0", "attempt_index >= 0", "item_count >= 1", "actual_tokens >= 0"),
        (
            ForeignKeyManifest(
                "samples",
                ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"),
                ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"),
                on_delete="CASCADE",
            ),
        ),
    ),
    TableManifest(
        "learning_events",
        (
            _column("event_id", "INTEGER", not_null=False, primary_key_position=1),
            _column("identity_id", "INTEGER", not_null=False),
            _column("learning_epoch", "INTEGER", not_null=False),
            _column("sample_process_boot_id", "TEXT", not_null=False),
            _column("sample_request_id", "TEXT", not_null=False),
            _column("sample_attempt_index", "INTEGER", not_null=False),
            _column("bucket_key", "TEXT"),
            _column("process_boot_id", "TEXT"),
            _column("request_id", "TEXT"),
            _column("attempt_index", "INTEGER"),
            _column("outcome", "TEXT"),
            _column("reason_code", "TEXT"),
            _column("metadata_json", "TEXT"),
            _column("prefix_checkpoint_outcome_json", "TEXT"),
            _column("revision", "INTEGER", not_null=False),
            _column("drift_reason_code", "TEXT", not_null=False),
            _column("drift_metadata_json", "TEXT", not_null=False),
            _column("evaluations_json", "TEXT"),
            _column("unresolved_provider", "TEXT", not_null=False),
            _column("unresolved_endpoint", "TEXT", not_null=False),
            _column("unresolved_generation", "INTEGER", not_null=False),
            _column("created_at_us", "INTEGER"),
        ),
        (
            "learning_epoch IS NULL OR learning_epoch >= 0",
            "sample_attempt_index IS NULL OR sample_attempt_index >= 0",
            "attempt_index >= 0",
            "outcome IN ('committed', 'duplicate', 'rejected', 'failed')",
            "reason_code IN ('sample-committed', 'duplicate-sample', 'sample-ineligible', 'missing-usage', 'inconsistent-usage', 'queue-full', 'analysis-failed', 'operation-cancelled', 'store-unavailable', 'migration-failed', 'commit-failed', 'pruned')",
            "revision IS NULL OR revision >= 0",
            "(drift_reason_code IS NULL) = (drift_metadata_json IS NULL)",
            "drift_reason_code IS NULL OR drift_reason_code IN ('profile-error-regression', 'exact-count-mismatch', 'identity-version-change')",
            "unresolved_generation IS NULL OR unresolved_generation >= 1",
            "created_at_us >= 0",
            "(sample_process_boot_id IS NULL AND sample_request_id IS NULL AND sample_attempt_index IS NULL) OR (sample_process_boot_id IS NOT NULL AND sample_request_id IS NOT NULL AND sample_attempt_index IS NOT NULL)",
            "(identity_id IS NOT NULL AND learning_epoch IS NOT NULL AND unresolved_provider IS NULL AND unresolved_endpoint IS NULL AND unresolved_generation IS NULL) OR (identity_id IS NULL AND learning_epoch IS NULL AND sample_process_boot_id IS NULL AND sample_request_id IS NULL AND sample_attempt_index IS NULL AND unresolved_provider IS NOT NULL AND unresolved_endpoint IS NOT NULL AND unresolved_generation IS NOT NULL)",
            "outcome != 'committed' OR reason_code = 'pruned' OR sample_process_boot_id IS NOT NULL",
        ),
        (
            ForeignKeyManifest(
                "epoch_state",
                ("identity_id", "learning_epoch"),
                ("identity_id", "epoch"),
                on_delete="CASCADE",
            ),
            ForeignKeyManifest(
                "samples",
                (
                    "identity_id",
                    "learning_epoch",
                    "sample_process_boot_id",
                    "sample_request_id",
                    "sample_attempt_index",
                ),
                ("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"),
                on_delete="CASCADE",
            ),
        ),
    ),
)

_V1_TABLE_DDL_DIGESTS = {
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
V1_TABLES = tuple(
    replace(table, ddl_digest=_V1_TABLE_DDL_DIGESTS[table.name])
    for table in _V1_TABLES_WITHOUT_DDL
)

V1_INDEXES = (
    IndexManifest(
        "identity_state_identity_key_uq",
        "identity_state",
        True,
        _index_columns(
            "actual_provider",
            "resolved_model",
            "endpoint",
            "wire_format",
            "tokenizer",
            "descriptor_fingerprint",
            "estimator_generation",
            "profile_schema_revision",
        ),
    ),
    IndexManifest("samples_global_key_uq", "samples", True, _index_columns("process_boot_id", "request_id", "attempt_index")),
    IndexManifest(
        "samples_owner_key_uq",
        "samples",
        True,
        _index_columns("identity_id", "epoch", "process_boot_id", "request_id", "attempt_index"),
    ),
    IndexManifest(
        "samples_identity_epoch_order",
        "samples",
        False,
        _index_columns("identity_id", "epoch", "observed_at_us DESC", "process_boot_id", "request_id", "attempt_index"),
    ),
    IndexManifest(
        "samples_identity_fingerprint_order",
        "samples",
        False,
        _index_columns("identity_id", "epoch", "full_fingerprint", "observed_at_us DESC", "process_boot_id", "request_id", "attempt_index"),
    ),
    IndexManifest(
        "prediction_records_identity_epoch",
        "prediction_records",
        False,
        _index_columns("identity_id", "prediction_epoch", "process_boot_id", "request_id", "attempt_index"),
    ),
    IndexManifest(
        "evaluations_window",
        "evaluations",
        False,
        _index_columns("identity_id", "prediction_epoch", "profile_key_hash", "method", "candidate_variant", "process_boot_id", "request_id", "attempt_index"),
    ),
    IndexManifest(
        "exact_anchors_lookup",
        "exact_anchors",
        False,
        _index_columns("identity_id", "epoch", "full_fingerprint", "process_boot_id", "request_id", "attempt_index"),
    ),
    IndexManifest(
        "prefix_anchors_lookup",
        "prefix_anchors",
        False,
        _index_columns("identity_id", "epoch", "context_fingerprint", "item_count DESC", "process_boot_id", "request_id", "attempt_index"),
    ),
    IndexManifest(
        "prefix_checkpoints_hash_lookup",
        "prefix_checkpoints",
        False,
        _index_columns("identity_id", "epoch", "profile_key_hash"),
    ),
    IndexManifest("learning_events_bucket_order", "learning_events", False, _index_columns("bucket_key", "event_id DESC")),
    IndexManifest(
        "learning_events_identity_epoch",
        "learning_events",
        False,
        _index_columns("identity_id", "learning_epoch", "event_id DESC"),
    ),
)


def _manifest_payload() -> dict[str, object]:
    return {
        "version": SCHEMA_VERSION,
        "tables": [asdict(table) for table in V1_TABLES],
        "indexes": [asdict(index) for index in V1_INDEXES],
    }


SCHEMA_MANIFEST_JSON = json.dumps(
    _manifest_payload(),
    ensure_ascii=True,
    allow_nan=False,
    separators=(",", ":"),
    sort_keys=True,
)
SCHEMA_MANIFEST_DIGEST = hashlib.sha256(SCHEMA_MANIFEST_JSON.encode("ascii")).hexdigest()

CREATE_TABLE_STATEMENTS = (
    """
    CREATE TABLE schema_meta (
        singleton INTEGER NOT NULL PRIMARY KEY CHECK (singleton = 1),
        version INTEGER NOT NULL CHECK (version = 1),
        manifest_digest TEXT NOT NULL CHECK (length(manifest_digest) = 64 AND manifest_digest NOT GLOB '*[^0-9a-f]*'),
        global_revision INTEGER NOT NULL DEFAULT 0 CHECK (global_revision >= 0)
    ) STRICT
    """,
    """
    CREATE TABLE identity_state (
        identity_id INTEGER PRIMARY KEY AUTOINCREMENT,
        actual_provider TEXT COLLATE BINARY NOT NULL,
        resolved_model TEXT COLLATE BINARY NOT NULL,
        endpoint TEXT COLLATE BINARY NOT NULL,
        wire_format TEXT COLLATE BINARY NOT NULL,
        tokenizer TEXT COLLATE BINARY NOT NULL,
        descriptor_fingerprint TEXT COLLATE BINARY NOT NULL,
        estimator_generation INTEGER NOT NULL CHECK (estimator_generation >= 1),
        profile_schema_revision INTEGER NOT NULL CHECK (profile_schema_revision >= 1),
        active_epoch INTEGER NOT NULL CHECK (active_epoch >= 0),
        revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)
    ) STRICT
    """,
    """
    CREATE TABLE epoch_state (
        identity_id INTEGER NOT NULL,
        epoch INTEGER NOT NULL CHECK (epoch >= 0),
        created_order INTEGER NOT NULL CHECK (created_order >= 0),
        PRIMARY KEY (identity_id, epoch),
        FOREIGN KEY (identity_id) REFERENCES identity_state(identity_id) ON DELETE CASCADE
    ) STRICT
    """,
    """
    CREATE TABLE samples (
        sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
        identity_id INTEGER NOT NULL,
        epoch INTEGER NOT NULL CHECK (epoch >= 0),
        process_boot_id TEXT COLLATE BINARY NOT NULL,
        request_id TEXT COLLATE BINARY NOT NULL,
        attempt_index INTEGER NOT NULL CHECK (attempt_index >= 0),
        observed_at_us INTEGER NOT NULL CHECK (observed_at_us >= 0),
        actual_input_tokens INTEGER NOT NULL CHECK (actual_input_tokens >= 0),
        last_used_order INTEGER NOT NULL CHECK (last_used_order >= 1),
        raw_body_sha256 TEXT COLLATE BINARY NOT NULL,
        feature_raw_body_sha256 TEXT COLLATE BINARY,
        known_tokens INTEGER NOT NULL CHECK (known_tokens >= 0),
        capability_visual_tokens INTEGER CHECK (capability_visual_tokens IS NULL OR capability_visual_tokens >= 0),
        components_json TEXT NOT NULL,
        profile_key_json TEXT NOT NULL,
        profile_key_hash TEXT COLLATE BINARY NOT NULL,
        feature_vector_json TEXT NOT NULL,
        full_fingerprint TEXT COLLATE BINARY NOT NULL,
        context_fingerprint TEXT COLLATE BINARY NOT NULL,
        prefix_fingerprints_json TEXT NOT NULL,
        low_confidence_reasons_json TEXT NOT NULL,
        committed_order INTEGER NOT NULL CHECK (committed_order >= 1),
        fixed_context_contribution_json TEXT NOT NULL,
        input_item_contributions_json TEXT NOT NULL,
        FOREIGN KEY (identity_id, epoch) REFERENCES epoch_state(identity_id, epoch) ON DELETE CASCADE
    ) STRICT
    """,
    """
    CREATE TABLE prefix_checkpoints (
        identity_id INTEGER NOT NULL,
        epoch INTEGER NOT NULL CHECK (epoch >= 0),
        profile_key_json TEXT COLLATE BINARY NOT NULL,
        profile_key_hash TEXT COLLATE BINARY NOT NULL,
        mode TEXT NOT NULL CHECK (mode IN ('eligible', 'demoted')),
        evidence_json TEXT NOT NULL,
        state_revision INTEGER NOT NULL CHECK (state_revision >= 1),
        updated_order INTEGER NOT NULL CHECK (updated_order >= 1),
        PRIMARY KEY (identity_id, epoch, profile_key_json),
        FOREIGN KEY (identity_id, epoch) REFERENCES epoch_state(identity_id, epoch) ON DELETE CASCADE
    ) STRICT
    """,
    """
    CREATE TABLE prediction_records (
        identity_id INTEGER NOT NULL,
        sample_epoch INTEGER NOT NULL CHECK (sample_epoch >= 0),
        process_boot_id TEXT COLLATE BINARY NOT NULL,
        request_id TEXT COLLATE BINARY NOT NULL,
        attempt_index INTEGER NOT NULL CHECK (attempt_index >= 0),
        prediction_epoch INTEGER NOT NULL CHECK (prediction_epoch >= 0),
        profile_key_hash TEXT COLLATE BINARY NOT NULL,
        selected_method TEXT NOT NULL,
        selected_variant TEXT NOT NULL,
        history_revision INTEGER NOT NULL CHECK (history_revision >= 0),
        method_champions_json TEXT NOT NULL,
        candidates_json TEXT NOT NULL,
        PRIMARY KEY (identity_id, sample_epoch, process_boot_id, request_id, attempt_index),
        FOREIGN KEY (identity_id, sample_epoch, process_boot_id, request_id, attempt_index) REFERENCES samples(identity_id, epoch, process_boot_id, request_id, attempt_index) ON DELETE CASCADE,
        FOREIGN KEY (identity_id, prediction_epoch) REFERENCES epoch_state(identity_id, epoch) ON DELETE CASCADE
    ) STRICT
    """,
    """
    CREATE TABLE evaluations (
        identity_id INTEGER NOT NULL,
        sample_epoch INTEGER NOT NULL CHECK (sample_epoch >= 0),
        process_boot_id TEXT COLLATE BINARY NOT NULL,
        request_id TEXT COLLATE BINARY NOT NULL,
        attempt_index INTEGER NOT NULL CHECK (attempt_index >= 0),
        method TEXT NOT NULL,
        candidate_variant TEXT NOT NULL,
        prediction_epoch INTEGER NOT NULL CHECK (prediction_epoch >= 0),
        profile_key_hash TEXT COLLATE BINARY NOT NULL,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        predicted_tokens REAL NOT NULL,
        actual_tokens INTEGER NOT NULL CHECK (actual_tokens >= 0),
        absolute_error REAL NOT NULL CHECK (absolute_error >= 0),
        signed_relative_error REAL,
        absolute_percentage_error REAL CHECK (absolute_percentage_error IS NULL OR absolute_percentage_error >= 0),
        CHECK ((method = 'history-exact' AND candidate_variant = 'median') OR (method = 'history-prefix' AND candidate_variant IN ('deterministic', 'additive', 'multiplicative')) OR (method = 'profile-calibrated' AND candidate_variant IN ('additive', 'multiplicative')) OR (method = 'cold-start' AND candidate_variant = 'deterministic')),
        PRIMARY KEY (identity_id, sample_epoch, process_boot_id, request_id, attempt_index, method, candidate_variant),
        FOREIGN KEY (identity_id, sample_epoch, process_boot_id, request_id, attempt_index) REFERENCES samples(identity_id, epoch, process_boot_id, request_id, attempt_index) ON DELETE CASCADE,
        FOREIGN KEY (identity_id, prediction_epoch) REFERENCES epoch_state(identity_id, epoch) ON DELETE CASCADE
    ) STRICT
    """,
    """
    CREATE TABLE exact_anchors (
        identity_id INTEGER NOT NULL,
        epoch INTEGER NOT NULL CHECK (epoch >= 0),
        process_boot_id TEXT COLLATE BINARY NOT NULL,
        request_id TEXT COLLATE BINARY NOT NULL,
        attempt_index INTEGER NOT NULL CHECK (attempt_index >= 0),
        full_fingerprint TEXT COLLATE BINARY NOT NULL,
        actual_tokens INTEGER NOT NULL CHECK (actual_tokens >= 0),
        PRIMARY KEY (identity_id, epoch, process_boot_id, request_id, attempt_index),
        FOREIGN KEY (identity_id, epoch, process_boot_id, request_id, attempt_index) REFERENCES samples(identity_id, epoch, process_boot_id, request_id, attempt_index) ON DELETE CASCADE
    ) STRICT
    """,
    """
    CREATE TABLE prefix_anchors (
        identity_id INTEGER NOT NULL,
        epoch INTEGER NOT NULL CHECK (epoch >= 0),
        process_boot_id TEXT COLLATE BINARY NOT NULL,
        request_id TEXT COLLATE BINARY NOT NULL,
        attempt_index INTEGER NOT NULL CHECK (attempt_index >= 0),
        context_fingerprint TEXT COLLATE BINARY NOT NULL,
        item_count INTEGER NOT NULL CHECK (item_count >= 1),
        prefix_fingerprint TEXT COLLATE BINARY NOT NULL,
        actual_tokens INTEGER NOT NULL CHECK (actual_tokens >= 0),
        PRIMARY KEY (identity_id, epoch, process_boot_id, request_id, attempt_index),
        FOREIGN KEY (identity_id, epoch, process_boot_id, request_id, attempt_index) REFERENCES samples(identity_id, epoch, process_boot_id, request_id, attempt_index) ON DELETE CASCADE
    ) STRICT
    """,
    """
    CREATE TABLE learning_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        identity_id INTEGER,
        learning_epoch INTEGER CHECK (learning_epoch IS NULL OR learning_epoch >= 0),
        sample_process_boot_id TEXT COLLATE BINARY,
        sample_request_id TEXT COLLATE BINARY,
        sample_attempt_index INTEGER CHECK (sample_attempt_index IS NULL OR sample_attempt_index >= 0),
        bucket_key TEXT COLLATE BINARY NOT NULL,
        process_boot_id TEXT COLLATE BINARY NOT NULL,
        request_id TEXT COLLATE BINARY NOT NULL,
        attempt_index INTEGER NOT NULL CHECK (attempt_index >= 0),
        outcome TEXT NOT NULL CHECK (outcome IN ('committed', 'duplicate', 'rejected', 'failed')),
        reason_code TEXT NOT NULL CHECK (reason_code IN ('sample-committed', 'duplicate-sample', 'sample-ineligible', 'missing-usage', 'inconsistent-usage', 'queue-full', 'analysis-failed', 'operation-cancelled', 'store-unavailable', 'migration-failed', 'commit-failed', 'pruned')),
        metadata_json TEXT NOT NULL,
        prefix_checkpoint_outcome_json TEXT NOT NULL,
        revision INTEGER CHECK (revision IS NULL OR revision >= 0),
        drift_reason_code TEXT CHECK (drift_reason_code IS NULL OR drift_reason_code IN ('profile-error-regression', 'exact-count-mismatch', 'identity-version-change')),
        drift_metadata_json TEXT,
        evaluations_json TEXT NOT NULL,
        unresolved_provider TEXT COLLATE BINARY,
        unresolved_endpoint TEXT COLLATE BINARY,
        unresolved_generation INTEGER CHECK (unresolved_generation IS NULL OR unresolved_generation >= 1),
        created_at_us INTEGER NOT NULL CHECK (created_at_us >= 0),
        CHECK ((drift_reason_code IS NULL) = (drift_metadata_json IS NULL)),
        CHECK ((sample_process_boot_id IS NULL AND sample_request_id IS NULL AND sample_attempt_index IS NULL) OR (sample_process_boot_id IS NOT NULL AND sample_request_id IS NOT NULL AND sample_attempt_index IS NOT NULL)),
        CHECK ((identity_id IS NOT NULL AND learning_epoch IS NOT NULL AND unresolved_provider IS NULL AND unresolved_endpoint IS NULL AND unresolved_generation IS NULL) OR (identity_id IS NULL AND learning_epoch IS NULL AND sample_process_boot_id IS NULL AND sample_request_id IS NULL AND sample_attempt_index IS NULL AND unresolved_provider IS NOT NULL AND unresolved_endpoint IS NOT NULL AND unresolved_generation IS NOT NULL)),
        CHECK (outcome != 'committed' OR reason_code = 'pruned' OR sample_process_boot_id IS NOT NULL),
        FOREIGN KEY (identity_id, learning_epoch) REFERENCES epoch_state(identity_id, epoch) ON DELETE CASCADE,
        FOREIGN KEY (identity_id, learning_epoch, sample_process_boot_id, sample_request_id, sample_attempt_index) REFERENCES samples(identity_id, epoch, process_boot_id, request_id, attempt_index) ON DELETE CASCADE
    ) STRICT
    """,
)

CREATE_INDEX_STATEMENTS = (
    "CREATE UNIQUE INDEX identity_state_identity_key_uq ON identity_state(actual_provider, resolved_model, endpoint, wire_format, tokenizer, descriptor_fingerprint, estimator_generation, profile_schema_revision)",
    "CREATE UNIQUE INDEX samples_global_key_uq ON samples(process_boot_id, request_id, attempt_index)",
    "CREATE UNIQUE INDEX samples_owner_key_uq ON samples(identity_id, epoch, process_boot_id, request_id, attempt_index)",
    "CREATE INDEX samples_identity_epoch_order ON samples(identity_id, epoch, observed_at_us DESC, process_boot_id, request_id, attempt_index)",
    "CREATE INDEX samples_identity_fingerprint_order ON samples(identity_id, epoch, full_fingerprint, observed_at_us DESC, process_boot_id, request_id, attempt_index)",
    "CREATE INDEX prediction_records_identity_epoch ON prediction_records(identity_id, prediction_epoch, process_boot_id, request_id, attempt_index)",
    "CREATE INDEX evaluations_window ON evaluations(identity_id, prediction_epoch, profile_key_hash, method, candidate_variant, process_boot_id, request_id, attempt_index)",
    "CREATE INDEX exact_anchors_lookup ON exact_anchors(identity_id, epoch, full_fingerprint, process_boot_id, request_id, attempt_index)",
    "CREATE INDEX prefix_anchors_lookup ON prefix_anchors(identity_id, epoch, context_fingerprint, item_count DESC, process_boot_id, request_id, attempt_index)",
    "CREATE INDEX prefix_checkpoints_hash_lookup ON prefix_checkpoints(identity_id, epoch, profile_key_hash)",
    "CREATE INDEX learning_events_bucket_order ON learning_events(bucket_key, event_id DESC)",
    "CREATE INDEX learning_events_identity_epoch ON learning_events(identity_id, learning_epoch, event_id DESC)",
)

CREATE_SCHEMA_STATEMENTS = (*CREATE_TABLE_STATEMENTS, *CREATE_INDEX_STATEMENTS)
