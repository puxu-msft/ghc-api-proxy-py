"""Align a wire-selected reasoning effort with the target model's published capabilities.

Thinking enablement and effort selection are already settled before this module is called. This module never derives effort from `thinking.budget_tokens`; it only preserves an exact published value or aligns a selected value along the shared effort ladder.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

# Weakest to strongest. The catalog lists names but never says they are ordered, so the order is stated here as this project's own and used for every comparison — `supported[-1]` would be reading an order out of a list that does not promise one.
#
# `minimal` is on this ladder because it is on the wire, not because anything documents it: it appears in the catalog recorded at `tests/int/cassettes/anthropic_to_responses_stream.json` on the gemini flash models. The official first-party client does not recognise the name either — it passes unknown levels through untouched — so a name missing from *this* ladder is not merely unranked, it is invisible: `_weakest` iterates the ladder, so a model publishing `["minimal", "low", …]` would have `disabled` answered with `low` while the reason said "weaker than anything this model offers", which is false. The assertion cannot catch that, because `low` really is on offer.
EFFORT_LADDER: tuple[str, ...] = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
ANTHROPIC_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
RESPONSES_EFFORTS = frozenset({"none", "minimal", *ANTHROPIC_EFFORTS})

class EffortSource(StrEnum):
    ANTHROPIC_DEFAULT = "anthropic-default"
    ANTHROPIC_TOP_LEVEL = "anthropic-top-level"
    ANTHROPIC_PER_MESSAGE = "anthropic-per-message"
    RESPONSES = "responses"


@dataclass(frozen=True, slots=True)
class ThinkingEffortIntent:
    enabled: bool
    effort: str | None
    effort_source: EffortSource


@dataclass(frozen=True, slots=True)
class ThinkingTargetProfile:
    modes: tuple[str, ...]
    can_disable: bool
    disabled_max_effort: str | None = None
    manual_budget_tokens: int | None = None


CompiledThinkingProfiles = tuple[tuple[re.Pattern[str], ThinkingTargetProfile], ...]


@dataclass(frozen=True, slots=True)
class ReasoningResolution:
    """The effort to send, and whether saying it that way cost anything.

    `effort` of `None` means send no `reasoning` field at all — which, per the module docstring, is *not* a way to express "off". It is what a target that publishes no efforts gets, and it is always accompanied by a reason.

    `approximated` is true when the requested rung was not on offer and another published rung was used, or when no rankable rung could be selected. `reason` says which, in words meant for whoever reads the loss record.
    """

    effort: str | None
    approximated: bool = False
    reason: str = ""


def _at_or_below(desired: str, supported: frozenset[str]) -> str | None:
    """The strongest supported rung no stronger than `desired`.

    Downward rather than nearest: effort costs money and latency, so a request that cannot be met exactly is met with less rather than more — *where there is anything below it*. When there is not, the caller falls back to `_weakest`, which is the only path that can answer with something stronger than was asked for. A desired rung this ladder does not know returns `None` here and is handled by the caller.
    """
    if desired not in EFFORT_LADDER:
        return None
    for rung in reversed(EFFORT_LADDER[: EFFORT_LADDER.index(desired) + 1]):
        if rung in supported:
            return rung
    return None


def _weakest(supported: frozenset[str]) -> str | None:
    """The lowest rung on offer — the floor used when the request asked for *less* than any of them.

    This is the one place the answer can come out stronger than what was asked for, and it is unavoidable rather than a preference: `disabled` against a model whose weakest published effort is `medium` has no downward option, and the alternative is sending nothing, which is measured to give upstream's default instead. Going up is reported as an approximation with both rungs named, so a request paying for more thinking than it asked for says so.
    """
    for rung in EFFORT_LADDER:
        if rung in supported:
            return rung
    return None


def align_anthropic_effort(
    desired: str, capabilities: tuple[str, ...] | None
) -> ReasoningResolution:
    """Fit a Responses effort onto the Anthropic effort names a target publishes.

    The catalog may advertise names from another protocol or future names this proxy cannot place. The Anthropic writer may emit only Anthropic's five levels, so intersect before using the shared alignment policy. `None` remains distinct from an explicitly empty or incompatible capability set.
    """
    compatible = (
        None
        if capabilities is None
        else tuple(value for value in capabilities if value in ANTHROPIC_EFFORTS)
    )
    return _align_effort(desired, compatible, candidate_domain="Anthropic-compatible")


def align_effort(desired: str, capabilities: tuple[str, ...] | None) -> ReasoningResolution:
    """Fit an effort name somebody already chose onto what this model publishes.

    A name the catalog publishes is sent verbatim, ranked or not. That branch is first on purpose: `EFFORT_LADDER` is this project's ordering and the catalog is the authority on membership, so a model publishing an effort nobody here has heard of still gets it.

    When nothing rankable can be fitted, this answers `None` rather than guessing at the cost of a name the ladder cannot place. Callers decide whether omission is legal for their wire contract; disabled reasoning is handled separately because it must be stated as `none` rather than omitted.
    """
    return _align_effort(desired, capabilities)


def _align_effort(
    desired: str,
    capabilities: tuple[str, ...] | None,
    *,
    candidate_domain: str | None = None,
) -> ReasoningResolution:
    if capabilities is None:
        reason = (
            f"the catalog publishes no {candidate_domain} reasoning effort candidates for this model"
            if candidate_domain is not None
            else "the catalog publishes no reasoning efforts for this model"
        )
        return ReasoningResolution(effort=None, approximated=True, reason=reason)
    supported = frozenset(capabilities)
    if not supported:
        reason = (
            f"this model advertises no {candidate_domain} reasoning effort candidates"
            if candidate_domain is not None
            else "this model advertises no reasoning efforts"
        )
        return ReasoningResolution(effort=None, approximated=True, reason=reason)
    if desired in supported:
        return ReasoningResolution(effort=desired)
    chosen = _at_or_below(desired, supported)
    if chosen is not None:
        reason = (
            f"asked for {desired}, which is not among this model's published {candidate_domain} candidates; sent {chosen}"
            if candidate_domain is not None
            else f"asked for {desired}, which this model does not offer; sent {chosen}"
        )
        return ReasoningResolution(effort=chosen, approximated=True, reason=reason)
    floor = _weakest(supported)
    if floor is None:
        # Everything this model publishes is a name `EFFORT_LADDER` cannot place, so there is no "weakest" to fall back to — `_weakest` walks the ladder and sees none of them.
        # Answering `None` here rather than picking one is the point: an unrankable name could be cheaper or far more expensive than what was asked for, and there is nothing to tell which.
        published = ", ".join(sorted(supported))
        return ReasoningResolution(
            effort=None,
            approximated=True,
            reason=(
                f"asked for {desired}; this model publishes only effort names this proxy cannot"
                f" rank ({published}), so none was chosen"
            ),
        )
    if candidate_domain is not None:
        rankability = "" if desired in EFFORT_LADDER else ", which this proxy cannot rank"
        reason = f"asked for {desired}{rankability}; {floor} is the weakest {candidate_domain} candidate published by this model, so {floor} was sent"
    elif desired in EFFORT_LADDER:
        reason = f"asked for {desired}, which is weaker than anything this model offers; sent {floor}"
    else:
        # The other way to reach the floor, and it used to be reported as the one above — which said the request asked for less than everything on offer, about a name nothing here can compare.
        reason = f"asked for {desired}, which this proxy cannot rank and this model does not publish; sent its weakest, {floor}"
    return ReasoningResolution(effort=floor, approximated=True, reason=reason)
