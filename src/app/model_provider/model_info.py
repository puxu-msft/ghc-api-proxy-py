"""Local model metadata for a bridge upstream whose catalog publishes none.

Some upstreams answer `/models` with ids and nothing else — opencode Zen returns
`{id, object, created, owned_by}` and no name, capability, limit or price. Routing still
works, because it asks config and the catalog only for endpoint support, but every
client-facing projection of the catalog comes out empty: no context window, no cost, no
protocol per model. The operator knows those facts, so the file this module loads is
where they are written down.

Entries are in the catalog entry shape the proxy reads everywhere else
(`capabilities.supports`, `capabilities.limits`, `supported_endpoints`, `pricing`), so a
merged entry needs no translation anywhere downstream.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from app.config.paths import expand_user_path

logger = logging.getLogger(__name__)

MODEL_INFO_SCHEMA_VERSION = 1

# How long a sample is taken at face value. Model catalogs and prices move — opencode's
# own tier gained and lost models within the weeks this was written — and a document is
# a measurement on the day it was taken, not a standing fact.
MODEL_INFO_MAX_AGE_DAYS = 90


class ModelInfoError(ValueError):
    """The configured model-info file is missing or unsafe to use."""


@dataclass(frozen=True, slots=True)
class ModelInfoDocument:
    """A loaded document, its entries, and how old the sample they came from is.

    `retrieved_at` is provenance, so it is reported rather than enforced: a date that
    cannot be read is a warning and no staleness verdict, never a refusal to start. What
    it must not be is silent — a stale sample and a current one produce the same catalog,
    and only this field tells them apart.
    """

    path: Path
    models: dict[str, dict[str, Any]]
    retrieved_at: date | None = None

    @property
    def age_days(self) -> int | None:
        if self.retrieved_at is None:
            return None
        return (datetime.now(UTC).date() - self.retrieved_at).days

    @property
    def is_stale(self) -> bool | None:
        """Whether the sample has aged out, or `None` when there is no date to judge.

        Tri-state rather than false-for-unknown: an unreadable date and a date from this
        morning are not the same answer, and reporting the first as `stale: false` is how
        a reader concludes the catalog was verified when nobody verified it.
        """
        age = self.age_days
        if age is None:
            return None
        return age > MODEL_INFO_MAX_AGE_DAYS

    def freshness(self) -> dict[str, Any]:
        """The provenance `/api/status` reports beside the catalog it produced."""
        return {
            "path": str(self.path),
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "age_days": self.age_days,
            "stale": self.is_stale,
        }


def _retrieved_at(document: Mapping[str, Any], path: Path) -> date | None:
    value = document.get("retrieved_at")
    if value is None:
        logger.warning(
            "model info %s carries no retrieved_at; its age cannot be judged", path
        )
        return None
    if not isinstance(value, str):
        logger.warning("model info %s has a non-string retrieved_at", path)
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        logger.warning("model info %s has an unreadable retrieved_at %r", path, value)
        return None


def load_model_info(path: str) -> ModelInfoDocument:
    resolved = expand_user_path(path)
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError as error:
        raise ModelInfoError(f"cannot read model info file {resolved}") from error
    except json.JSONDecodeError as error:
        raise ModelInfoError(f"model info file {resolved} is not valid JSON") from error

    if not isinstance(raw, dict):
        raise ModelInfoError("model info must be an object")
    document = cast(dict[str, Any], raw)
    if document.get("schema_version") != MODEL_INFO_SCHEMA_VERSION:
        raise ModelInfoError("unsupported model info schema version")

    models = document.get("models")
    if not isinstance(models, Mapping) or not models:
        raise ModelInfoError("model info must carry a non-empty models mapping")

    entries: dict[str, dict[str, Any]] = {}
    for model_id, entry in cast(Mapping[Any, Any], models).items():
        if not isinstance(model_id, str) or not model_id.strip():
            raise ModelInfoError("model info keys must be non-empty model ids")
        if model_id != model_id.strip():
            raise ModelInfoError("model info model ids may not have surrounding whitespace")
        if not isinstance(entry, Mapping):
            raise ModelInfoError(f"model info for {model_id!r} must be an object")
        entries[model_id] = dict(cast(Mapping[str, Any], entry))

    loaded = ModelInfoDocument(
        path=resolved,
        models=entries,
        retrieved_at=_retrieved_at(document, resolved),
    )
    if loaded.is_stale:
        logger.warning(
            "model info %s was sampled %s days ago (limit %s); prices and model lists "
            "drift, so regenerate it",
            resolved,
            loaded.age_days,
            MODEL_INFO_MAX_AGE_DAYS,
        )
    return loaded


def merge_model_info(
    upstream: Mapping[str, Any],
    local: Mapping[str, Any],
) -> dict[str, Any]:
    """One upstream catalog entry with the local entry laid over it.

    Mappings merge key by key so a local file can add `capabilities.supports` facts
    without deleting the ones upstream did publish — filling a gap is the whole point,
    and a wholesale replace would turn every omission in the local file into a claim
    that the fact is absent. Every other value is taken from the local file, which is
    the operator's own statement about the model and outranks what upstream said.
    """
    merged = dict(upstream)
    for key, value in local.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = merge_model_info(
                cast(Mapping[str, Any], current),
                cast(Mapping[str, Any], value),
            )
            continue
        merged[key] = value
    return merged
