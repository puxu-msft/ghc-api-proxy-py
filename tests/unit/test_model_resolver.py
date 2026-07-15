import pytest

from app.transform.model_resolver import ModelResolutionError, ModelResolver, normalize_for_matching


def test_normalize_for_matching_unifies_dots_and_case() -> None:
    assert normalize_for_matching("Claude-Opus-4.6") == "claude-opus-4-6"


def test_exact_override_and_chained_override() -> None:
    resolver = ModelResolver(
        available_ids={"claude-opus-4.6-fast"},
        model_overrides={"fast": "opus-fast", "opus-fast": "claude-opus-4.6-fast"},
    )

    assert resolver.resolve("fast") == "claude-opus-4.6-fast"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("claude-opus-4-6", "claude-opus-4.6"),
        ("claude-opus-4-6-fast", "claude-opus-4.6-fast"),
        ("claude-sonnet-4-6-20250514", "claude-sonnet-4.6"),
        ("opus[1m]", "claude-opus-4.6-1m"),
    ],
)
def test_normalization_and_modifiers(raw: str, expected: str) -> None:
    resolver = ModelResolver(
        available_ids={
            "claude-opus-4.6",
            "claude-opus-4.6-fast",
            "claude-opus-4.6-1m",
            "claude-sonnet-4.6",
        },
        model_overrides={},
    )

    assert resolver.resolve(raw) == expected


def test_short_alias_uses_first_available_preference() -> None:
    resolver = ModelResolver(
        available_ids={"claude-opus-4.5", "claude-opus-4"},
        model_overrides={},
    )

    assert resolver.resolve("opus") == "claude-opus-4.5"


def test_model_overrides_precede_model_mappings() -> None:
    resolver = ModelResolver(
        available_ids={"override", "mapping"},
        model_overrides={"alias": "override"},
        model_mappings={"alias": "mapping"},
    )

    assert resolver.resolve("alias") == "override"


def test_family_override_redirects_versioned_name() -> None:
    resolver = ModelResolver(
        available_ids={"claude-opus-4.6", "claude-opus-4.6-1m"},
        model_overrides={"opus": "claude-opus-4.6-1m"},
    )

    assert resolver.resolve("claude-opus-4-6") == "claude-opus-4.6-1m"


def test_override_cycle_is_rejected() -> None:
    resolver = ModelResolver(
        available_ids=set(),
        model_overrides={"a": "b", "b": "a"},
    )

    with pytest.raises(ModelResolutionError, match="cycle"):
        resolver.resolve("a")


def test_unknown_model_is_passed_through() -> None:
    resolver = ModelResolver(available_ids=set(), model_overrides={})

    assert resolver.resolve("future-model") == "future-model"