"""The local model-info document: what it may say, and what it overrides.

The file exists because some upstreams answer `/models` with ids and nothing else, so
every client-facing projection of their catalog comes out empty. What it says is the
operator's own statement about those models, which is why it is allowed to outrank
upstream — and why a malformed file has to stop the start-up rather than quietly leave
the catalog as bare as it was.

The file is also a sample taken on a day. Prices and model lists drift, so the day is
reported — loudly when the sample is old — but never enforced: refusing to start over
provenance would take a working deployment down for a date.
"""

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from app.model_provider.model_info import (
    MODEL_INFO_MAX_AGE_DAYS,
    MODEL_INFO_SCHEMA_VERSION,
    ModelInfoError,
    load_model_info,
    merge_model_info,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRIBUTED = (
    REPO_ROOT / "src" / "app" / "model_provider" / "opencode-go-20260916.json"
)
LOGGER = "app.model_provider.model_info"
_RATES = {"input", "output", "cacheRead", "cacheWrite"}


def today() -> date:
    return datetime.now(UTC).date()


def written(tmp_path: Path, document: object) -> str:
    path = tmp_path / "model-info.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def document(models: object, **extra: object) -> dict[str, object]:
    return {
        "schema_version": MODEL_INFO_SCHEMA_VERSION,
        "retrieved_at": today().isoformat(),
        "models": models,
        **extra,
    }


def test_a_document_loads_its_entries(tmp_path: Path) -> None:
    path = written(
        tmp_path,
        document(
            {
                "kimi-k3": {"name": "Kimi K3", "supported_endpoints": ["/v1/messages"]},
                "glm-5.3": {"name": "GLM 5.3"},
            }
        ),
    )

    loaded = load_model_info(path)

    assert set(loaded.models) == {"kimi-k3", "glm-5.3"}
    assert loaded.models["kimi-k3"]["name"] == "Kimi K3"


def test_a_missing_file_names_the_path_it_could_not_read(tmp_path: Path) -> None:
    missing = str(tmp_path / "absent.json")

    with pytest.raises(ModelInfoError) as raised:
        load_model_info(missing)

    assert missing in str(raised.value)


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "model-info.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ModelInfoError, match="not valid JSON"):
        load_model_info(str(path))


@pytest.mark.parametrize(
    "payload",
    [
        {"models": {"kimi-k3": {}}},
        {"schema_version": 2, "models": {"kimi-k3": {}}},
        {"schema_version": 0, "models": {"kimi-k3": {}}},
        {"schema_version": "1", "models": {"kimi-k3": {}}},
    ],
)
def test_an_unknown_schema_version_is_rejected(tmp_path: Path, payload: object) -> None:
    with pytest.raises(ModelInfoError, match="schema version"):
        load_model_info(written(tmp_path, payload))


@pytest.mark.parametrize(
    "models",
    [{}, [], "kimi-k3", None],
)
def test_a_missing_or_empty_models_mapping_is_rejected(
    tmp_path: Path, models: object
) -> None:
    with pytest.raises(ModelInfoError, match="non-empty models mapping"):
        load_model_info(written(tmp_path, document(models)))


@pytest.mark.parametrize("model_id", ["", "   ", " kimi-k3", "kimi-k3 "])
def test_blank_or_padded_model_ids_are_rejected(
    tmp_path: Path, model_id: str
) -> None:
    with pytest.raises(ModelInfoError, match="model ids"):
        load_model_info(written(tmp_path, document({model_id: {}})))


@pytest.mark.parametrize("entry", ["Kimi K3", ["Kimi K3"], 7, None])
def test_a_non_object_entry_is_rejected(tmp_path: Path, entry: object) -> None:
    with pytest.raises(ModelInfoError, match="must be an object"):
        load_model_info(written(tmp_path, document({"kimi-k3": entry})))


def test_a_top_level_non_object_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ModelInfoError, match="must be an object"):
        load_model_info(written(tmp_path, ["kimi-k3"]))


def test_a_configured_path_expands_shell_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`${VAR:-fallback}` is the form the config uses, and the fallback is the point.

    The file lives where the variable points on machines that set it, and at the
    fallback everywhere else, so the fallback has to resolve too.
    """
    written(tmp_path, document({"kimi-k3": {}}))
    monkeypatch.delenv("GHC_MODEL_INFO", raising=False)

    loaded = load_model_info(f"${{GHC_MODEL_INFO:-{tmp_path}}}/model-info.json")

    assert set(loaded.models) == {"kimi-k3"}


def test_merge_keeps_upstream_keys_the_file_omits() -> None:
    merged = merge_model_info(
        {"id": "kimi-k3", "object": "model", "created": 1_789_000_000},
        {"name": "Kimi K3"},
    )

    assert merged == {
        "id": "kimi-k3",
        "object": "model",
        "created": 1_789_000_000,
        "name": "Kimi K3",
    }


def test_merge_takes_the_file_for_every_scalar_it_states() -> None:
    merged = merge_model_info(
        {"id": "kimi-k3", "name": "kimi-k3"},
        {"name": "Kimi K3"},
    )

    assert merged["name"] == "Kimi K3"


def test_merge_adds_nested_keys_without_dropping_siblings() -> None:
    """Filling a gap is the whole point, and upstream's published facts stay published."""
    merged = merge_model_info(
        {
            "id": "kimi-k3",
            "capabilities": {
                "supports": {"tool_call": True},
                "limits": {"max_context_window_tokens": 1_048_576},
            },
        },
        {"capabilities": {"supports": {"vision": False}}},
    )

    assert merged["capabilities"] == {
        "supports": {"tool_call": True, "vision": False},
        "limits": {"max_context_window_tokens": 1_048_576},
    }


def test_merge_replaces_a_list_rather_than_extending_it() -> None:
    """`supported_endpoints` is a set of claims, not a running total."""
    merged = merge_model_info(
        {"id": "kimi-k3", "supported_endpoints": ["/responses"]},
        {"supported_endpoints": ["/v1/messages", "/chat/completions"]},
    )

    assert merged["supported_endpoints"] == ["/v1/messages", "/chat/completions"]


def test_merge_does_not_mutate_its_inputs() -> None:
    upstream = {"id": "kimi-k3", "capabilities": {"supports": {"tool_call": True}}}
    local = {"capabilities": {"supports": {"vision": True}}}

    merge_model_info(upstream, local)

    assert upstream == {"id": "kimi-k3", "capabilities": {"supports": {"tool_call": True}}}
    assert local == {"capabilities": {"supports": {"vision": True}}}


def test_the_contributed_opencode_go_document_is_usable() -> None:
    """The shipped document is hand-maintained, so its shape is asserted, not assumed.

    A typo here decides whether an operator's `/models` is described or bare, and a
    silently empty one would look exactly like upstream's own answer.
    """
    loaded = load_model_info(str(CONTRIBUTED))
    entries = loaded.models

    assert len(entries) >= 20
    for entry in entries.values():
        assert isinstance(entry.get("name"), str) and entry["name"].strip()
        advertised = entry["supported_endpoints"]
        assert isinstance(advertised, list) and advertised
        endpoints = cast(list[str], advertised)
        assert set(endpoints) <= {"/chat/completions", "/responses", "/v1/messages"}
        limits = entry["capabilities"]["limits"]
        assert limits["max_context_window_tokens"] > 0
        assert limits["max_output_tokens"] > 0
        assert_rate_complete(entry["pricing"])


def test_the_rolling_flash_alias_describes_what_it_points_at() -> None:
    """`deepseek-flash` is upstream's "latest Flash", not a model that defies description.

    models.dev's own `deepseek/deepseek-flash` entry is named "DeepSeek V4.1 Flash" and
    carries v4.1's limits and rates, so the document states the same thing instead of
    advertising a model whose context window and price it declines to state — an empty
    entry reads to a client as a model nobody has information about. The entry will drift
    when upstream moves the alias, which is what the sample date is for.
    """
    entries = load_model_info(str(CONTRIBUTED)).models
    alias = entries["deepseek-flash"]
    target = entries["deepseek-v4.1-flash"]

    assert alias["name"] == target["name"]
    assert alias["capabilities"] == target["capabilities"]
    assert alias["pricing"] == target["pricing"]
    assert "rolling alias" in alias["description"]
    # The probes were run against the alias id, so these are its own answer.
    assert alias["supported_endpoints"] == ["/chat/completions", "/responses", "/v1/messages"]


def assert_rate_complete(pricing: dict[str, object]) -> None:
    """`_pi_cost` needs all four rates, in the base tier and in every tier beside it.

    One missing rate does not degrade the projection, it removes the whole cost block,
    so a tiered entry that omits a rate describes a model that costs nothing — the
    failure this asserts against is silent by construction.
    """
    tiers = pricing.get("tiers")
    if tiers is None:
        assert set(pricing) == _RATES
        return
    assert isinstance(tiers, list)
    tier_list = cast(list[dict[str, object]], tiers)
    base = next(tier for tier in tier_list if tier["name"] == "default")
    assert set(base) == _RATES | {"name"}
    for tier in tier_list:
        if tier is base:
            continue
        # `input_min_tokens` is the tier's threshold, and `_pi_cost` drops the block
        # rather than guess when it is absent or unreadable.
        assert set(tier) == _RATES | {"name", "input_min_tokens"}
        assert cast(int, tier["input_min_tokens"]) > 1


def test_the_contributed_document_says_when_it_was_sampled() -> None:
    """Without the date a stale sample is indistinguishable from a current one."""
    loaded = load_model_info(str(CONTRIBUTED))

    assert loaded.retrieved_at is not None
    assert loaded.age_days is not None and loaded.age_days >= 0


def reported(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == LOGGER]


def test_a_current_sample_is_loaded_without_complaint(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = written(tmp_path, document({"kimi-k3": {}}))

    with caplog.at_level(logging.WARNING):
        loaded = load_model_info(path)

    assert loaded.age_days == 0
    assert loaded.is_stale is False
    assert reported(caplog) == []


def test_an_old_sample_is_reported_and_still_loaded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Provenance warns; it never refuses.

    Refusing to start over a date would turn a working deployment into a broken one the
    moment the sample aged out, and the catalog it produced is still the best available
    answer for what those models are.
    """
    sampled = today() - timedelta(days=MODEL_INFO_MAX_AGE_DAYS + 1)
    path = written(tmp_path, document({"kimi-k3": {}}, retrieved_at=sampled.isoformat()))

    with caplog.at_level(logging.WARNING):
        loaded = load_model_info(path)

    assert loaded.is_stale is True
    assert loaded.age_days == MODEL_INFO_MAX_AGE_DAYS + 1
    assert set(loaded.models) == {"kimi-k3"}
    assert len(reported(caplog)) == 1
    assert str(loaded.age_days) in reported(caplog)[0]
    assert str(MODEL_INFO_MAX_AGE_DAYS) in reported(caplog)[0]


@pytest.mark.parametrize("retrieved_at", [None, "", "yesterday", 20_260_916, "2026-13-01"])
def test_an_unreadable_sample_date_is_reported_not_enforced(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, retrieved_at: object
) -> None:
    """A date that cannot be read is a warning, never a failure to load."""
    path = written(tmp_path, document({"kimi-k3": {}}, retrieved_at=retrieved_at))

    with caplog.at_level(logging.WARNING):
        loaded = load_model_info(path)

    assert loaded.retrieved_at is None
    assert loaded.age_days is None
    assert loaded.is_stale is None
    assert set(loaded.models) == {"kimi-k3"}
    assert len(reported(caplog)) == 1
    assert "retrieved_at" in reported(caplog)[0]


def test_a_sample_dated_ahead_of_the_clock_is_not_ancient(tmp_path: Path) -> None:
    """Clock skew and hand-written typos must not read as a long-expired sample."""
    path = written(
        tmp_path,
        document({"kimi-k3": {}}, retrieved_at=(today() + timedelta(days=5)).isoformat()),
    )

    loaded = load_model_info(path)

    assert loaded.age_days == -5
    assert loaded.is_stale is False


def test_freshness_carries_what_the_status_document_reports(tmp_path: Path) -> None:
    path = written(tmp_path, document({"kimi-k3": {}}))

    assert load_model_info(path).freshness() == {
        "path": path,
        "retrieved_at": today().isoformat(),
        "age_days": 0,
        "stale": False,
    }


def test_freshness_without_a_date_says_nothing_rather_than_zero(tmp_path: Path) -> None:
    """`age_days: 0` would read as today, which is the one thing unknown age is not."""
    path = written(tmp_path, document({"kimi-k3": {}}, retrieved_at=None))

    assert load_model_info(path).freshness() == {
        "path": path,
        "retrieved_at": None,
        "age_days": None,
        "stale": None,
    }
