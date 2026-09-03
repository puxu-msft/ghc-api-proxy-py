"""Align an already-selected effort against the model catalog."""

import pytest

from app.config.schema import ThinkingTargetProfileConfig
from app.pipeline.routing import compile_thinking_profiles, select_thinking_profile
from app.pipeline.translation_driver.reasoning import (
    ANTHROPIC_EFFORTS,
    EFFORT_LADDER,
    RESPONSES_EFFORTS,
    align_anthropic_effort,
    align_effort,
)

NO_NONE = ("low", "medium", "high", "xhigh")
NARROW = ("low", "medium", "high")
FULL = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def test_an_exact_effort_is_kept() -> None:
    resolution = align_effort("xhigh", NO_NONE)

    assert resolution.effort == "xhigh"
    assert resolution.approximated is False


def test_an_unavailable_effort_comes_down_to_the_strongest_supported_level() -> None:
    resolution = align_effort("max", NARROW)

    assert resolution.effort == "high"
    assert resolution.approximated is True
    assert resolution.reason == "asked for max, which this model does not offer; sent high"


def test_an_effort_below_every_supported_level_uses_the_weakest_level() -> None:
    resolution = align_effort("low", ("high", "xhigh"))

    assert resolution.effort == "high"
    assert resolution.approximated is True
    assert resolution.reason == "asked for low, which is weaker than anything this model offers; sent high"


def test_unknown_and_empty_capabilities_both_omit_effort_with_distinct_reasons() -> None:
    absent = align_effort("high", None)
    empty = align_effort("high", ())

    assert absent.effort is None
    assert absent.reason == "the catalog publishes no reasoning efforts for this model"
    assert empty.effort is None
    assert empty.reason == "this model advertises no reasoning efforts"


def test_an_exact_unranked_catalog_effort_is_still_kept() -> None:
    resolution = align_effort("future-level", ("future-level",))

    assert resolution.effort == "future-level"
    assert resolution.approximated is False


def test_unrankable_capabilities_are_not_guessed() -> None:
    resolution = align_effort("high", ("future-level",))

    assert resolution.effort is None
    assert resolution.approximated is True
    assert resolution.reason == "asked for high; this model publishes only effort names this proxy cannot rank (future-level), so none was chosen"


def test_anthropic_alignment_uses_only_anthropic_effort_candidates() -> None:
    exact = align_anthropic_effort("high", ("none", "minimal", "high", "future-level"))
    incompatible = align_anthropic_effort("high", ("none", "minimal", "future-level"))

    assert exact.effort == "high"
    assert exact.approximated is False
    assert incompatible.effort is None
    assert incompatible.reason == "this model advertises no Anthropic-compatible reasoning effort candidates"


def test_anthropic_downward_alignment_names_the_compatible_candidate_domain() -> None:
    resolution = align_anthropic_effort("max", ("minimal", "medium", "high"))

    assert resolution.effort == "high"
    assert resolution.approximated is True
    assert resolution.reason == "asked for max, which is not among this model's published Anthropic-compatible candidates; sent high"


@pytest.mark.parametrize("desired", EFFORT_LADDER)
@pytest.mark.parametrize("capabilities", [NO_NONE, NARROW, FULL, ("max",), ("future-level",)])
def test_aligned_effort_is_always_published_by_the_model(
    desired: str,
    capabilities: tuple[str, ...],
) -> None:
    resolution = align_effort(desired, capabilities)

    assert resolution.effort is None or resolution.effort in capabilities


def test_wire_effort_sets_are_explicit() -> None:
    assert {"low", "medium", "high", "xhigh", "max"} == ANTHROPIC_EFFORTS
    assert {
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    } == RESPONSES_EFFORTS


def test_thinking_profile_selection_uses_the_last_full_match() -> None:
    profiles = compile_thinking_profiles(
        {
            r"claude-opus-.*": ThinkingTargetProfileConfig(
                modes=("adaptive",),
                can_disable=True,
            ),
            r"claude-opus-5": ThinkingTargetProfileConfig(
                modes=("enabled", "adaptive"),
                can_disable=False,
                manual_budget_tokens=2048,
            ),
        }
    )

    selected = select_thinking_profile(profiles, "claude-opus-5")

    assert selected is not None
    pattern, profile = selected
    assert pattern == r"claude-opus-5"
    assert profile.modes == ("enabled", "adaptive")
    assert profile.can_disable is False
    assert profile.manual_budget_tokens == 2048


def test_thinking_profile_selection_does_not_accept_a_partial_match() -> None:
    profiles = compile_thinking_profiles(
        {
            r"claude-opus-5": ThinkingTargetProfileConfig(
                modes=("adaptive",),
                can_disable=True,
            )
        }
    )

    assert select_thinking_profile(profiles, "prefix-claude-opus-5") is None
    assert select_thinking_profile(profiles, "claude-opus-5-suffix") is None
