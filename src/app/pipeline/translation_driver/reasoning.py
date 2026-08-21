"""Turning a request's reasoning intent into an effort the target model actually offers.

Two facts meet here and neither is negotiable. The client says how much thinking it wants, in Anthropic's vocabulary — off, adaptive, or a token budget. The catalog says which effort names this particular model accepts, and **that set differs per model**: the real Copilot catalog recorded in `tests/int/cassettes/anthropic_to_responses_stream.json` gives `gpt-5.3-codex` four names without `none`, `gpt-5.5` five with it, `gpt-5.6-terra` six including `max`, and `grok-4.5` only three. A mapping that hard-codes any name is a mapping that eventually sends one the model does not take.

So the one hard invariant is `resolution.effort is None or resolution.effort in capabilities`. It is asserted at the end of `resolve` rather than trusted, because the failure it prevents is silent: an unsupported effort name is a 400 from the gateway on a request that looked fine here. The reference implementation this was compared against checks its capability list on two of its five branches and hard-codes the other three; the three that are hard-coded happen to be supported by every model in today's catalog, which is exactly why nobody notices until a catalog changes.

Omission is not "off". Measured on a real `gpt-5.5` exchange: a request carrying no `reasoning` at all comes back with `"reasoning":{"effort":"medium",...}` — the upstream default. So `thinking: {"type": "disabled"}` has to be *said*, and saying it means finding a name for it.

The thresholds are this project's policy, not an upstream fact. Nothing in the catalog publishes a budget-to-effort correspondence, and the Responses models publish no `min_thinking_budget`/`max_thinking_budget` at all — those belong to the Claude models on the other endpoint and borrowing them would be inventing a contract.
"""

from dataclasses import dataclass

# Weakest to strongest. The catalog lists names but never says they are ordered, so the order is stated here as this project's own and used for every comparison — `supported[-1]` would be reading an order out of a list that does not promise one.
EFFORT_LADDER: tuple[str, ...] = ("none", "low", "medium", "high", "xhigh", "max")

# Which rung a `thinking.budget_tokens` asks for. Lower bounds, read as "this many tokens or more". Policy, not measurement: see the module docstring.
BUDGET_LADDER: tuple[tuple[int, str], ...] = (
    (30_000, "max"),
    (16_000, "xhigh"),
    (8_000, "high"),
    (3_000, "medium"),
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

    Downward rather than nearest: effort costs money and latency, so a request that cannot be met exactly is met with less rather than more. A desired rung this ladder does not know returns `None` here and is handled by the caller.
    """
    if desired not in EFFORT_LADDER:
        return None
    for rung in reversed(EFFORT_LADDER[: EFFORT_LADDER.index(desired) + 1]):
        if rung in supported:
            return rung
    return None


def _weakest(supported: frozenset[str]) -> str | None:
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
