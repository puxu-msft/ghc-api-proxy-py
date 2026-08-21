"""Choosing a reasoning effort against what a model actually publishes.

The catalog recorded in `tests/int/cassettes/anthropic_to_responses_stream.json` is the reason these are shaped the way they are: real Copilot models publish *different* effort sets — three names for `grok-4.5`, four without `none` for `gpt-5.3-codex`, six including `max` for `gpt-5.6-terra`. So the cases below are capability sets, not models, and every one of them asserts the same invariant from a different angle: whatever comes back is either nothing or a name that was on offer.
"""

import pytest

from app.pipeline.translation_driver.reasoning import (
    EFFORT_LADDER,
    ReasoningIntent,
    ReasoningIntentInvalid,
    intent_from_thinking,
    resolve,
    unused_thinking_fields,
)

# The three shapes the real catalog actually shows, named for what distinguishes them.
NO_NONE = ("low", "medium", "high", "xhigh")
WITH_NONE = ("none", "low", "medium", "high", "xhigh")
NARROW = ("low", "medium", "high")
FULL = ("none", "low", "medium", "high", "xhigh", "max")


def test_a_budget_lands_on_a_rung_the_model_offers() -> None:
    for budget, expected in ((1_000, "low"), (5_000, "medium"), (10_000, "high"), (20_000, "xhigh"), (50_000, "max")):
        resolution = resolve(ReasoningIntent(mode="budget", budget_tokens=budget), FULL)
        assert resolution.effort == expected, budget


def test_a_budget_above_what_the_model_offers_comes_down_rather_than_up() -> None:
    """`grok-4.5` publishes only low/medium/high. A 50k budget wants `max`; sending `max` is a 400 and sending `high` is the honest nearest thing this model can do."""
    resolution = resolve(ReasoningIntent(mode="budget", budget_tokens=50_000), NARROW)

    assert resolution.effort == "high"
    assert resolution.approximated
    assert "max" in resolution.reason


def test_disabled_becomes_none_where_none_exists() -> None:
    resolution = resolve(ReasoningIntent(mode="disabled"), WITH_NONE)

    assert resolution.effort == "none"
    assert not resolution.approximated


def test_disabled_falls_to_the_weakest_rung_where_none_does_not_exist() -> None:
    """`gpt-5.3-codex` has no `none`, and omitting the field is measured to give upstream's default of `medium` — so "off" has to be said as the weakest thing sayable, and said to be an approximation."""
    resolution = resolve(ReasoningIntent(mode="disabled"), NO_NONE)

    assert resolution.effort == "low"
    assert resolution.approximated
    assert "weaker than anything" in resolution.reason


def test_adaptive_asks_for_high_and_settles_for_less() -> None:
    assert resolve(ReasoningIntent(mode="adaptive"), FULL).effort == "high"
    assert resolve(ReasoningIntent(mode="adaptive"), NARROW).effort == "high"
    assert resolve(ReasoningIntent(mode="adaptive"), ("low",)).effort == "low"


def test_adaptive_never_climbs_past_what_it_asked_for() -> None:
    """Effort costs money. A model offering `max` does not get `max` because the request said "you decide"."""
    assert resolve(ReasoningIntent(mode="adaptive"), FULL).effort == "high"


def test_an_unknown_catalog_and_an_empty_one_are_different_answers_and_neither_guesses() -> None:
    absent = resolve(ReasoningIntent(mode="adaptive"), None)
    empty = resolve(ReasoningIntent(mode="adaptive"), ())

    assert absent.effort is None and empty.effort is None
    assert "publishes no" in absent.reason
    assert "advertises no" in empty.reason


@pytest.mark.parametrize("capabilities", [NO_NONE, WITH_NONE, NARROW, FULL, ("max",), ("none",)])
def test_the_chosen_effort_is_always_one_the_model_offers(capabilities: tuple[str, ...]) -> None:
    """The one invariant. Swept over every intent this project can form, against every capability shape the real catalog shows."""
    intents = [ReasoningIntent(mode="disabled"), ReasoningIntent(mode="adaptive")]
    intents += [ReasoningIntent(mode="budget", budget_tokens=n) for n in (1, 3_000, 8_000, 16_000, 30_000, 1_000_000)]

    for intent in intents:
        resolution = resolve(intent, capabilities)
        assert resolution.effort is None or resolution.effort in capabilities, (intent, capabilities)


def test_every_rung_the_ladder_names_can_actually_be_chosen() -> None:
    """Each rung, pinned to the input that reaches it.

    An earlier version compared the *set* of reachable efforts against `set(EFFORT_LADDER)`, which
    is not a test: deleting `max` from the ladder shrinks both sides at once and it stayed green
    while a 30k budget silently fell to a different rung. Pinning each pair means removing a rung
    from the ladder, or moving a threshold, fails here with the pair that changed.
    """
    assert resolve(ReasoningIntent(mode="disabled"), FULL).effort == "none"
    assert resolve(ReasoningIntent(mode="budget", budget_tokens=1), FULL).effort == "low"
    assert resolve(ReasoningIntent(mode="budget", budget_tokens=3_000), FULL).effort == "medium"
    assert resolve(ReasoningIntent(mode="budget", budget_tokens=8_000), FULL).effort == "high"
    assert resolve(ReasoningIntent(mode="budget", budget_tokens=16_000), FULL).effort == "xhigh"
    assert resolve(ReasoningIntent(mode="budget", budget_tokens=30_000), FULL).effort == "max"
    # And the ladder names nothing this project cannot reach, which is the half the pairs above cannot say.
    assert set(EFFORT_LADDER) == {"none", "low", "medium", "high", "xhigh", "max"}


def test_thinking_is_read_into_the_three_modes() -> None:
    assert intent_from_thinking(None) is None
    assert intent_from_thinking({"type": "disabled"}) == ReasoningIntent(mode="disabled")
    assert intent_from_thinking({"type": "adaptive"}) == ReasoningIntent(mode="adaptive")
    assert intent_from_thinking({"type": "auto"}) == ReasoningIntent(mode="adaptive")
    assert intent_from_thinking({"type": "enabled", "budget_tokens": 5000}) == ReasoningIntent(
        mode="budget", budget_tokens=5000
    )


def test_enabled_without_a_budget_is_adaptive_rather_than_refused() -> None:
    """Anthropic accepts the body, so refusing it here would reject a request upstream would have taken."""
    assert intent_from_thinking({"type": "enabled"}) == ReasoningIntent(mode="adaptive")


def test_a_boolean_budget_is_refused_rather_than_read_as_one_token() -> None:
    """`True` is an `int` in Python. Without the explicit `bool` check, `budget_tokens: true` asks for a one-token budget — a wrong answer that no test of integers would find."""
    with pytest.raises(ReasoningIntentInvalid) as raised:
        intent_from_thinking({"type": "enabled", "budget_tokens": True})

    assert raised.value.field_path == "thinking.budget_tokens"


@pytest.mark.parametrize(
    ("thinking", "field_path"),
    [
        ({"type": "sideways"}, "thinking.type"),
        ({"type": 3}, "thinking.type"),
        ({}, "thinking.type"),
        ({"type": "enabled", "budget_tokens": 0}, "thinking.budget_tokens"),
        ({"type": "enabled", "budget_tokens": -5}, "thinking.budget_tokens"),
        ({"type": "enabled", "budget_tokens": "lots"}, "thinking.budget_tokens"),
        ("enabled", "thinking"),
    ],
)
def test_a_thinking_field_that_cannot_be_read_names_the_field_it_could_not_read(
    thinking: object, field_path: str
) -> None:
    with pytest.raises(ReasoningIntentInvalid) as raised:
        intent_from_thinking(thinking)

    assert raised.value.field_path == field_path


def test_fields_a_mode_does_not_read_are_named() -> None:
    """`disabled` ignores a budget the client meant. Answering "nothing was lost" about it would be false, and `thinking` no longer travels in `extensions` where the drop used to be reported."""
    disabled = ReasoningIntent(mode="disabled")
    assert unused_thinking_fields({"type": "disabled", "budget_tokens": 8000}, disabled) == ("budget_tokens",)
    assert unused_thinking_fields({"type": "disabled"}, disabled) == ()

    budget = ReasoningIntent(mode="budget", budget_tokens=5000)
    assert unused_thinking_fields({"type": "enabled", "budget_tokens": 5000}, budget) == ()
    assert unused_thinking_fields({"type": "enabled", "budget_tokens": 5000, "mode": "deep"}, budget) == ("mode",)

    assert unused_thinking_fields({"type": "disabled"}, None) == ()
