import pytest

from app.pipeline.model_resolution import (
    ModelResolution,
    candidate_keys,
    canonical,
    discover_provider,
    find_alias_cycles,
    inspect_mappings,
    resolve_against_catalog,
    split_provider_qualifier,
)

AVAILABLE = frozenset({"claude-opus-5", "claude-sonnet-5", "gpt-5.6-luna", "gpt-5.6-terra"})
PROVIDERS = frozenset({"A", "B"})


def resolve_full(
    name: str,
    mappings: dict[str, str] | None = None,
    *,
    available: frozenset[str] = AVAILABLE,
    providers: frozenset[str] = frozenset(),
) -> ModelResolution:
    """Both passes, the way `decide_route` runs them.

    Kept here rather than imported because the production caller also has to pick a provider between the two passes; these tests are about the name, so they hand the same catalog to whatever the walk chose.
    """
    discovery = discover_provider(name, mappings=mappings or {}, provider_names=providers)
    return resolve_against_catalog(
        name,
        discovery.target,
        available=available,
        matched_key=discovery.matched_key,
        hops=discovery.hops,
    )


def resolve(name: str, mappings: dict[str, str] | None = None) -> str:
    return resolve_full(name, mappings).resolved


# --- name resolution, unchanged by multi-provider routing ---------------------------------


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
    outcome = resolve_full("mystery")
    assert outcome.resolved == "mystery"
    assert outcome.passthrough is True


def test_mapping_target_is_resolved_as_an_alias_when_not_available() -> None:
    # gpt is not a model; it maps to another alias that does resolve.
    outcome = resolve_full("gpt", {"gpt": "fast", "fast": "gpt-5.6-luna"})
    assert outcome.resolved == "gpt-5.6-luna"
    assert outcome.hops == 2


def test_mapping_to_an_unavailable_target_abandons_the_mapping() -> None:
    # The spec: if still unavailable, abandon the mapping and pass through.
    outcome = resolve_full("opus", {"opus": "claude-opus-99"})
    assert outcome.resolved == "opus"
    assert outcome.passthrough is True


def test_alias_cycle_terminates_and_passes_through() -> None:
    outcome = resolve_full("a", {"a": "b", "b": "a"})
    assert outcome.resolved == "a"
    assert outcome.passthrough is True


def test_resolution_reports_the_key_that_matched() -> None:
    outcome = resolve_full("claude-opus-4-5", {"claude-opus-4.5": "claude-opus-5"})
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


# --- passthrough keeps sending the client's own name -------------------------------------


def test_an_abandoned_mapping_falls_back_to_a_name_the_catalog_does_have() -> None:
    """Spec §2.4. This is the behaviour an earlier draft wrongly claimed was unreachable.

    The name is both a mapping key and a real model. Its target is gone, so the mapping is abandoned — and the fallback lands on a name the catalog offers, so the request is servable rather than refused. Nothing about it reaches `UnknownModel`.
    """
    outcome = resolve_full("claude-opus-5", {"claude-opus-5": "claude-opus-99"})
    assert outcome.resolved == "claude-opus-5"
    assert outcome.passthrough is True
    # The point of the test: a passthrough result can still name something real.
    assert outcome.resolved in AVAILABLE


# --- provider qualifiers -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("claude-opus-5", (None, "claude-opus-5", False)),
        ("A/claude-opus-5", ("A", "claude-opus-5", True)),
        ("zzz/claude-opus-5", (None, "claude-opus-5", True)),
        # First separator wins, so a model name may keep one.
        ("A/vendor/model", ("A", "vendor/model", True)),
        ("zzz/vendor/model", (None, "vendor/model", True)),
        # Leading separator: the head is empty, which is no provider, so it is a typo — and lands on the fallback path rather than being read as unqualified.
        ("/claude-opus-5", (None, "claude-opus-5", True)),
        # Exact match only: the provider is `A`, and `a` is a different key.
        ("a/claude-opus-5", (None, "claude-opus-5", True)),
        # Qualified but with nothing after the separator.
        ("A/", ("A", "", True)),
        ("", (None, "", False)),
    ],
)
def test_split_provider_qualifier(value: str, expected: tuple[str | None, str, bool]) -> None:
    assert split_provider_qualifier(value, PROVIDERS) == expected


def test_a_recognised_qualifier_ends_the_walk() -> None:
    """Spec §2.2 rule 1."""
    discovery = discover_provider(
        "claude-opus-4.8",
        mappings={"claude-opus-4.8": "A/claude-opus-5"},
        provider_names=PROVIDERS,
    )
    assert discovery.provider == "A"
    assert discovery.origin == "qualified"
    assert discovery.target == "claude-opus-5"


def test_an_unrecognised_qualifier_drops_the_prefix_and_asks_for_the_fallback() -> None:
    """Spec §2.2 rule 2. The model name survives; only the bad provider name is discarded."""
    discovery = discover_provider(
        "x", mappings={"x": "typo/claude-opus-5"}, provider_names=PROVIDERS
    )
    assert discovery.provider == ""
    assert discovery.origin == "fallback"
    assert discovery.target == "claude-opus-5"


def test_an_unrecognised_qualifier_is_still_a_terminus() -> None:
    """Spec §2.2 rule 2, the part that was ruled on separately.

    If the stripped value were demoted to an alias and the walk continued, it would read the qualifier on the next entry and serve the request from B — so a single mistyped letter would silently pick a provider, instead of taking the fallback path built for exactly this mistake.
    """
    discovery = discover_provider(
        "x",
        mappings={"x": "a/claude-opus-5", "claude-opus-5": "B/claude-opus-5"},
        provider_names=PROVIDERS,
    )
    assert discovery.origin == "fallback"
    assert discovery.provider != "B"


def test_an_unqualified_value_keeps_walking() -> None:
    """Spec §2.2 rule 3."""
    discovery = discover_provider(
        "fable",
        mappings={"fable": "opus", "opus": "A/claude-opus-5"},
        provider_names=PROVIDERS,
    )
    assert discovery.provider == "A"
    assert discovery.hops == 2


def test_a_chain_with_no_qualifier_anywhere_asks_for_the_default() -> None:
    """Spec §2.2 rule 4a."""
    discovery = discover_provider(
        "fable", mappings={"fable": "claude-opus-5"}, provider_names=PROVIDERS
    )
    assert discovery.origin == "default"
    assert discovery.provider == ""
    assert discovery.target == "claude-opus-5"
    assert discovery.hops == 1


def test_exhausting_the_hop_budget_still_answers_with_a_name() -> None:
    """Spec §2.2 rule 4b: the walk stops, and whatever name it stopped on is the answer."""
    discovery = discover_provider("a", mappings={"a": "b", "b": "a"}, provider_names=PROVIDERS)
    assert discovery.origin == "default"
    assert discovery.hops == 8
    assert discovery.target in {"a", "b"}


def test_the_walk_does_not_stop_at_a_catalog_name_before_reading_a_qualifier() -> None:
    """Spec §9.2 — the reason the walk ignores catalogs entirely.

    `claude-opus-5` is in the catalog and sits mid-chain. An algorithm that stopped there would never read the qualifier written on that model's own entry, and the same model would be served by different providers depending on whether the client spelled it `fable` or `claude-opus-5`.
    """
    discovery = discover_provider(
        "fable",
        mappings={"fable": "claude-opus-5", "claude-opus-5": "A/claude-opus-5"},
        provider_names=PROVIDERS,
    )
    assert discovery.provider == "A"


def test_a_self_mapping_with_a_qualifier_is_not_a_cycle() -> None:
    """Spec §6.1: this is the only way to route a model whose name needs no rewriting."""
    discovery = discover_provider(
        "claude-opus-5",
        mappings={"claude-opus-5": "A/claude-opus-5"},
        provider_names=PROVIDERS,
    )
    assert discovery.provider == "A"
    assert discovery.target == "claude-opus-5"
    assert discovery.hops == 1


# --- static inspection of the mapping table ----------------------------------------------


def test_a_self_mapping_is_not_reported_as_a_cycle() -> None:
    assert find_alias_cycles({"claude-opus-5": "A/claude-opus-5"}, PROVIDERS) == ()


def test_two_names_pointing_at_each_other_are_a_cycle() -> None:
    cycles = find_alias_cycles({"opus": "claude-opus-5", "claude-opus-5": "opus"}, PROVIDERS)
    assert cycles == (("claude-opus-5", "opus"),)


def test_a_cycle_is_reported_once_however_many_names_lead_into_it() -> None:
    mappings = {"a": "b", "b": "c", "c": "a", "d": "a", "e": "d"}
    assert len(find_alias_cycles(mappings, PROVIDERS)) == 1


def test_a_plain_chain_is_not_a_cycle() -> None:
    assert find_alias_cycles({"a": "b", "b": "c"}, PROVIDERS) == ()


def test_an_unknown_provider_is_reported_with_what_will_happen_to_it() -> None:
    with_fallback = inspect_mappings({"x": "typo/claude-opus-5"}, PROVIDERS, fallback="B")
    without = inspect_mappings({"x": "typo/claude-opus-5"}, PROVIDERS)
    assert [p.kind for p in with_fallback] == ["unknown-provider"]
    assert [p.kind for p in without] == ["unknown-provider"]
    # Same defect, different consequence — and the consequence is what the operator acts on.
    # The quoted name is asserted, not a bare `B`: an independent verifier's first probe passed while the message said only "the fallback provider", because `B` happened to appear in the "configured: A, B" list further along the same string.
    assert "fallback provider 'B'" in with_fallback[0].detail
    assert "REFUSED" in without[0].detail


def test_an_empty_model_name_is_reported() -> None:
    problems = inspect_mappings({"x": "A/"}, PROVIDERS)
    assert [p.kind for p in problems] == ["empty-model"]


def test_an_empty_value_is_reported() -> None:
    problems = inspect_mappings({"x": ""}, PROVIDERS)
    assert [p.kind for p in problems] == ["empty-model"]


def test_a_cycle_is_reported() -> None:
    problems = inspect_mappings({"a": "b", "b": "a"}, PROVIDERS)
    assert [p.kind for p in problems] == ["cycle"]
    assert problems[0].keys == ("a", "b")


def test_a_cycle_is_reported_using_the_spelling_the_operator_wrote() -> None:
    """The keys are compared folded and reported verbatim, and only the second half is negotiable.

    Reporting the folded form is what an earlier version did, and it hands the operator a string that is not in their configuration file: `claude-opus-4.5` comes back as `claude-opus-4-5`, greps for nothing, and the one actionable thing the warning had to offer is gone.
    """
    mappings = {"claude-opus-4.5": "Claude-Sonnet-4.5", "claude-sonnet-4.5": "claude-opus-4.5"}
    (cycle,) = find_alias_cycles(mappings, PROVIDERS)
    assert set(cycle) == {"claude-opus-4.5", "claude-sonnet-4.5"}
    for name in cycle:
        assert name in mappings


def test_a_healthy_table_reports_nothing() -> None:
    mappings = {"opus": "claude-opus-5", "claude-opus-5": "A/claude-opus-5"}
    assert inspect_mappings(mappings, PROVIDERS) == ()
