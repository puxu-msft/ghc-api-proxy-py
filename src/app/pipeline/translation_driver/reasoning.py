"""Turning a request's reasoning intent into an effort the target model actually offers.

Two facts meet here and neither is negotiable. The client says how much thinking it wants, in Anthropic's vocabulary — off, adaptive, or a token budget. The catalog says which effort names this particular model accepts, and **that set differs per model**: the real Copilot catalog recorded in `tests/int/cassettes/anthropic_to_responses_stream.json` gives `gpt-5.3-codex` four names without `none`, `gpt-5.5` five with it, `gpt-5.6-terra` six including `max`, `grok-4.5` only three, and the gemini flash models a `minimal` that appears nowhere else. A mapping that hard-codes any name is a mapping that eventually sends one the model does not take.

So the one hard invariant is `resolution.effort is None or resolution.effort in capabilities`. It is asserted at the end of `resolve` rather than trusted, because the failure it prevents is silent: an unsupported effort name is a 400 from the gateway on a request that looked fine here. The reference implementation this was compared against checks its capability list on two of its five branches and hard-codes the other three; the three that are hard-coded happen to be supported by every model in today's catalog, which is exactly why nobody notices until a catalog changes.

Omission is not "off". Measured on a real `gpt-5.5` exchange: a request carrying no `reasoning` at all comes back with `"reasoning":{"effort":"medium",...}` — the upstream default. So `thinking: {"type": "disabled"}` has to be *said*, and saying it means finding a name for it.

The thresholds are this project's policy, not an upstream fact, and a reading of the first-party client settled that there is no upstream rule to adopt: `vscode-copilot-chat` never converts a budget into an effort on either leg — on the Anthropic side it sends `thinking.budget_tokens` and `output_config.effort` as independent fields. Nothing in the catalog publishes a correspondence either, and the Responses models publish no `min_thinking_budget`/`max_thinking_budget` at all — those belong to the Claude models on the other endpoint and borrowing them would be inventing a contract.

Two things that client *does* settle, and both are followed here: the effort set comes from the catalog and is never hard-coded (its own type for it is an open `string[]`, and it passes names it does not recognise straight through), and `reasoning` carries only `effort` and `summary` — `context` and `mode` appear nowhere in it.
"""

from dataclasses import dataclass
from typing import cast

# Weakest to strongest. The catalog lists names but never says they are ordered, so the order is stated here as this project's own and used for every comparison — `supported[-1]` would be reading an order out of a list that does not promise one.
#
# `minimal` is on this ladder because it is on the wire, not because anything documents it: it appears in the catalog recorded at `tests/int/cassettes/anthropic_to_responses_stream.json` on the gemini flash models. The official first-party client does not recognise the name either — it passes unknown levels through untouched — so a name missing from *this* ladder is not merely unranked, it is invisible: `_weakest` iterates the ladder, so a model publishing `["minimal", "low", …]` would have `disabled` answered with `low` while the reason said "weaker than anything this model offers", which is false. The assertion cannot catch that, because `low` really is on offer.
EFFORT_LADDER: tuple[str, ...] = ("none", "minimal", "low", "medium", "high", "xhigh", "max")

# Which rung a `thinking.budget_tokens` asks for. Lower bounds, read as "this many tokens or more". Policy, not measurement — and a search of the first-party client established that there is no upstream rule to find: it never converts a budget into an effort at all, sending `thinking.budget_tokens` and `output_config.effort` side by side as independent fields.
#
# The one external datum that bears on the numbers is the official client's default budget of 16000. A user who configured nothing should not land in the second-strongest rung, so 16000 sits at `high` rather than at `xhigh`, and the rest are spaced around it. That is a sanity check against a default, not a rule anybody published.
BUDGET_LADDER: tuple[tuple[int, str], ...] = (
    (32_000, "max"),
    (24_000, "xhigh"),
    (16_000, "high"),
    (8_000, "medium"),
)
BUDGET_FLOOR = "low"

# What `thinking: {"type": "adaptive"}` asks for. Adaptive means "decide for me", and this is the rung it decides on when the target has no adaptive mode of its own to hand the decision to.
ADAPTIVE_EFFORT = "high"


class ReasoningIntentInvalid(ValueError):
    """The `thinking` field is not one of the shapes Anthropic defines.

    Separate from a loss because it is the client's mistake rather than a limit of the crossing: a `budget_tokens` of `-1` or a `type` nobody has heard of cannot be approximated into anything, and carrying on would mean choosing an effort the request never asked for.

    Carries the field path so the caller can tell the client which part of its body is the problem.
    """

    def __init__(self, message: str, *, field_path: str) -> None:
        super().__init__(message)
        self.field_path = field_path


@dataclass(frozen=True, slots=True)
class ReasoningIntent:
    """How much reasoning the request asked for, in nobody's wire vocabulary.

    `mode` is what was asked, and the other two fields carry the argument for the modes that take one. Protocol-neutral on purpose: `budget` is how Anthropic says it and `effort` is how the Responses API says it, and an intermediate form that stored either spelling would have to be rewritten the first time a third format arrived.
    """

    mode: str
    budget_tokens: int | None = None
    effort: str | None = None


@dataclass(frozen=True, slots=True)
class ReasoningResolution:
    """The effort to send, and whether saying it that way cost anything.

    `effort` of `None` means send no `reasoning` field at all — which, per the module docstring, is *not* a way to express "off". It is what a target that publishes no efforts gets, and it is always accompanied by a reason.

    `approximated` is true when the answer is not what was asked for: a continuous budget landed on a discrete rung, or the rung the request wanted was not on offer and a lower one was used. `reason` says which, in words meant for whoever reads the loss record.
    """

    effort: str | None
    approximated: bool = False
    reason: str = ""


def intent_from_thinking(thinking: object) -> ReasoningIntent | None:
    """Read Anthropic's `thinking` field, or `None` when the request did not set one.

    Rejects rather than guesses. `budget_tokens` must be a positive `int` and specifically not a `bool` — `True` is an `int` in Python, and a client sending `{"type": "enabled", "budget_tokens": true}` would otherwise be read as asking for one token.
    """
    if thinking is None:
        return None
    if not isinstance(thinking, dict):
        raise ReasoningIntentInvalid("thinking must be an object", field_path="thinking")
    field = dict[str, object](thinking)  # pyright: ignore[reportUnknownArgumentType]
    kind = field.get("type")
    if not isinstance(kind, str):
        raise ReasoningIntentInvalid("thinking.type must be a string", field_path="thinking.type")
    if kind == "disabled":
        return ReasoningIntent(mode="disabled")
    if kind in ("adaptive", "auto"):
        return ReasoningIntent(mode="adaptive")
    if kind != "enabled":
        raise ReasoningIntentInvalid(f"unknown thinking.type {kind!r}", field_path="thinking.type")

    budget = field.get("budget_tokens")
    if budget is None:
        # `enabled` without a budget is still a request to think; it just does not say how much. Treated as adaptive rather than refused, because refusing would reject a body Anthropic accepts.
        return ReasoningIntent(mode="adaptive")
    if isinstance(budget, bool) or not isinstance(budget, int):
        raise ReasoningIntentInvalid(
            "thinking.budget_tokens must be an integer", field_path="thinking.budget_tokens"
        )
    if budget <= 0:
        raise ReasoningIntentInvalid(
            "thinking.budget_tokens must be positive", field_path="thinking.budget_tokens"
        )
    return ReasoningIntent(mode="budget", budget_tokens=budget)


# What each mode actually reads out of `thinking`. Anything else the client sent is not refused — Anthropic may add fields and refusing them would reject bodies it accepts — but it is not silently eaten either, because `thinking` is now claimed by the reader and a claimed field no longer travels in `extensions` where an unclaimed one would have been reported.
_CONSUMED_BY_MODE = {
    "disabled": frozenset({"type"}),
    "adaptive": frozenset({"type"}),
    "budget": frozenset({"type", "budget_tokens"}),
}


def unused_thinking_fields(thinking: object, intent: ReasoningIntent | None) -> tuple[str, ...]:
    """The keys of `thinking` this intent did not read, sorted.

    `{"type": "disabled", "budget_tokens": 8000}` is the case worth naming: the budget is real, the client meant it, and `disabled` ignores it entirely. Answering "nothing was lost" there would be false.
    """
    if intent is None or not isinstance(thinking, dict):
        return ()
    consumed = _CONSUMED_BY_MODE.get(intent.mode, frozenset({"type"}))
    return tuple(sorted(key for key in cast(dict[str, object], thinking) if key not in consumed))


def _desired(intent: ReasoningIntent) -> str:
    """The rung this intent asks for, before anything is known about what the target offers."""
    if intent.mode == "disabled":
        return "none"
    if intent.mode == "adaptive":
        return ADAPTIVE_EFFORT
    if intent.mode == "effort" and intent.effort:
        return intent.effort
    budget = intent.budget_tokens or 0
    for threshold, rung in BUDGET_LADDER:
        if budget >= threshold:
            return rung
    return BUDGET_FLOOR


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


def resolve(intent: ReasoningIntent, capabilities: tuple[str, ...] | None) -> ReasoningResolution:
    """Choose the effort to send for this intent against this model's published names.

    `capabilities` of `None` means the catalog said nothing about this model's efforts — which is not the same as an empty tuple, where it said "none at all". Neither gets an effort, and both say why, because filling in a guess is how a request quietly starts asking for something it did not ask for.

    The invariant every branch below is written to hold is checked here rather than assumed. It is the one property that matters and the one whose violation is invisible from inside this process: an effort name the model does not offer is a 400 from the gateway, arriving long after this function returned something that looked reasonable.
    """
    resolution = _resolve(intent, capabilities)
    if resolution.effort is not None and resolution.effort not in (capabilities or ()):
        raise AssertionError(
            f"resolver chose {resolution.effort!r}, which is not among {capabilities!r}"
        )
    return resolution


def _resolve(intent: ReasoningIntent, capabilities: tuple[str, ...] | None) -> ReasoningResolution:
    if capabilities is None:
        return ReasoningResolution(
            effort=None,
            approximated=True,
            reason="the catalog publishes no reasoning efforts for this model",
        )
    supported = frozenset(capabilities)
    if not supported:
        return ReasoningResolution(
            effort=None,
            approximated=True,
            reason="this model advertises no reasoning efforts",
        )

    desired = _desired(intent)
    chosen = _at_or_below(desired, supported)
    if chosen == desired:
        return ReasoningResolution(effort=chosen, approximated=intent.mode == "budget")
    if chosen is not None:
        return ReasoningResolution(
            effort=chosen,
            approximated=True,
            reason=f"asked for {desired}, which this model does not offer; sent {chosen}",
        )
    # Nothing at or below what was asked for. The request wanted less thinking than the weakest thing on offer — `disabled` against a model that always reasons is the case that reaches here — so the floor is the closest this target can come.
    floor = _weakest(supported)
    if floor is None:
        return ReasoningResolution(
            effort=None,
            approximated=True,
            reason="this model advertises no reasoning efforts",
        )
    return ReasoningResolution(
        effort=floor,
        approximated=True,
        reason=f"asked for {desired}, which is weaker than anything this model offers; sent {floor}",
    )
