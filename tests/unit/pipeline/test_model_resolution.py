import pytest

from app.pipeline.model_resolution import candidate_keys, canonical, resolve_model

AVAILABLE = frozenset({"claude-opus-5", "claude-sonnet-5", "gpt-5.6-luna", "gpt-5.6-terra"})


def resolve(name: str, mappings: dict[str, str] | None = None) -> str:
    return resolve_model(name, mappings=mappings or {}, available=AVAILABLE).resolved


def test_dot_and_dash_are_interchangeable_in_the_key() -> None:
    # The spec's worked example: inbound claude-opus-4-5 hits the claude-opus-4.5 mapping.
    assert resolve("claude-opus-4-5", {"claude-opus-4.5": "claude-opus-5"}) == "claude-opus-5"
    assert resolve("claude-opus-4.5", {"claude-opus-4-5": "claude-opus-5"}) == "claude-opus-5"


def test_matching_is_case_insensitive() -> None:
    assert resolve("OPUS", {"opus": "claude-opus-5"}) == "claude-opus-5"
    assert resolve("opus", {"OPUS": "claude-opus-5"}) == "claude-opus-5"


def test_bracket_suffix_prefers_the_suffixed_key() -> None:
    # The spec tries opus-1m before opus.
    mappings = {"opus-1m": "claude-sonnet-5", "opus": "claude-opus-5"}
    assert resolve("opus[1m]", mappings) == "claude-sonnet-5"


def test_bracket_suffix_falls_back_to_the_base_key() -> None:
    assert resolve("opus[1m]", {"opus": "claude-opus-5"}) == "claude-opus-5"


def test_date_suffix_is_not_stripped() -> None:
    # Since 2026/07/16 the date suffix must be configured explicitly.
    # An unmapped dated name therefore does not silently reach the undated model.
    assert resolve("claude-opus-4-5-20251101", {"claude-opus-4.5": "claude-opus-5"}) == (
        "claude-opus-4-5-20251101"
    )


def test_explicitly_configured_date_suffix_resolves() -> None:
    mappings = {"claude-opus-4-5-20251101": "claude-opus-5"}
    assert resolve("claude-opus-4-5-20251101", mappings) == "claude-opus-5"


def test_available_model_needs_no_mapping() -> None:
    assert resolve("claude-opus-5") == "claude-opus-5"


def test_unmapped_unknown_name_passes_through() -> None:
    outcome = resolve_model("mystery", mappings={}, available=AVAILABLE)
    assert outcome.resolved == "mystery"
    assert outcome.passthrough is True


def test_mapping_target_is_resolved_as_an_alias_when_not_available() -> None:
    # gpt is not a model; it maps to another alias that does resolve.
    mappings = {"gpt": "fast", "fast": "gpt-5.6-luna"}
    outcome = resolve_model("gpt", mappings=mappings, available=AVAILABLE)
    assert outcome.resolved == "gpt-5.6-luna"
    assert outcome.hops == 2


def test_mapping_to_an_unavailable_target_abandons_the_mapping() -> None:
    # The spec: if still unavailable, abandon the mapping and pass through so upstream rejects it.
    outcome = resolve_model(
        "opus",
        mappings={"opus": "claude-opus-99"},
        available=AVAILABLE,
    )
    assert outcome.resolved == "opus"
    assert outcome.passthrough is True


def test_alias_cycle_terminates_and_passes_through() -> None:
    outcome = resolve_model(
        "a",
        mappings={"a": "b", "b": "a"},
        available=AVAILABLE,
    )
    assert outcome.resolved == "a"
    assert outcome.passthrough is True


def test_resolution_reports_the_key_that_matched() -> None:
    outcome = resolve_model(
        "claude-opus-4-5",
        mappings={"claude-opus-4.5": "claude-opus-5"},
        available=AVAILABLE,
    )
    assert outcome.matched_key == "claude-opus-4.5"


def test_target_spelling_follows_the_catalog_not_the_mapping() -> None:
    # The mapping writes gpt-5-6-luna; the catalog spells it gpt-5.6-luna.
    assert resolve("gpt", {"gpt": "gpt-5-6-luna"}) == "gpt-5.6-luna"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Claude-Opus-4.5", "claude-opus-4-5"),
        ("  opus  ", "opus"),
        ("GPT-5.6-Terra", "gpt-5-6-terra"),
    ],
)
def test_canonical_folds_case_and_separators(raw: str, expected: str) -> None:
    assert canonical(raw) == expected


def test_candidate_order_for_a_bracket_name() -> None:
    assert candidate_keys("opus[1m]") == ("opus[1m]", "opus-1m", "opus")


def test_candidate_order_for_a_plain_name() -> None:
    assert candidate_keys("opus") == ("opus",)
