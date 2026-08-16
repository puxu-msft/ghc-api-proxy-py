import pytest

from app.pipeline.timeouts import resolve_timeout


def test_scalar_applies_when_nothing_matches() -> None:
    assert resolve_timeout("claude-opus-5", 300, {"gpt": 60}) == 300


def test_substring_key_matches_anywhere_in_the_name() -> None:
    assert resolve_timeout("claude-opus-5", 300, {"opus": 60}) == 60


def test_glob_key_matches_the_whole_name() -> None:
    assert resolve_timeout("gpt-5.6-terra", 300, {"gpt-*": 90}) == 90


def test_wildcard_matches_every_model() -> None:
    assert resolve_timeout("anything", 300, {"*": 30}) == 30


def test_literal_beats_a_glob() -> None:
    # Both match; the spec ranks a literal substring above a glob.
    assert resolve_timeout("gpt-5.6-terra", 300, {"gpt-*": 90, "terra": 45}) == 45


def test_glob_beats_the_wildcard() -> None:
    assert resolve_timeout("gpt-5.6-terra", 300, {"*": 30, "gpt-*": 90}) == 90


def test_longest_key_wins_within_one_class() -> None:
    assert resolve_timeout("claude-opus-5", 300, {"opus": 60, "claude-opus": 75}) == 75


def test_longest_glob_wins_among_globs() -> None:
    assert resolve_timeout("gpt-5.6-terra", 300, {"gpt-*": 90, "gpt-5.6-*": 120}) == 120


def test_override_of_zero_disables_rather_than_falling_back() -> None:
    # 0 means disabled in this spec, so a matching 0 is a decision, not an absent value.
    assert resolve_timeout("claude-opus-5", 300, {"opus": 0}) == 0


def test_resolution_does_not_depend_on_mapping_order() -> None:
    forward = {"*": 30, "gpt-*": 90, "terra": 45}
    reversed_order = {"terra": 45, "gpt-*": 90, "*": 30}
    assert resolve_timeout("gpt-5.6-terra", 300, forward) == resolve_timeout(
        "gpt-5.6-terra", 300, reversed_order
    )


@pytest.mark.parametrize("model", ["gpt-5.6-terra", "claude-opus-5", ""])
def test_empty_overrides_always_give_the_scalar(model: str) -> None:
    assert resolve_timeout(model, 1200, {}) == 1200
