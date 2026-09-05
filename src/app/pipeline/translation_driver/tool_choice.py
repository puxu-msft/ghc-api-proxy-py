"""Tool selection intent shared by the request readers and outbound writers.

Only exact supported shapes are claimed. Unclaimed values remain in extensions for same-format replay; a cross-format writer must refuse a choice it cannot interpret rather than silently relax it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

_ANTHROPIC_CHOICE_KEYS = {
    "auto": frozenset({"type", "disable_parallel_tool_use"}),
    "any": frozenset({"type", "disable_parallel_tool_use"}),
    "none": frozenset({"type", "disable_parallel_tool_use"}),
    "tool": frozenset({"type", "name", "disable_parallel_tool_use"}),
}


@dataclass(frozen=True, slots=True)
class ToolChoiceIntent:
    """A selection mode and optional named tool, independent of wire spelling.

    ``disable_parallel=None`` is silence; ``False`` preserves an explicit Anthropic value for same-format replay without imposing a cross-format restriction.
    """

    mode: str
    name: str | None = None
    disable_parallel: bool | None = None


def intent_from_anthropic_tool_choice(value: object) -> ToolChoiceIntent | None:
    """Read a supported Anthropic shape without discarding unknown fields."""
    if not isinstance(value, Mapping):
        return None
    choice = dict[str, Any](cast(Mapping[str, Any], value))
    mode = choice.get("type")
    if not isinstance(mode, str) or mode not in _ANTHROPIC_CHOICE_KEYS:
        return None
    if set(choice) - _ANTHROPIC_CHOICE_KEYS[mode]:
        return None
    # A present null is not absence: decline the whole shape so replay stays exact.
    if "disable_parallel_tool_use" in choice and not isinstance(
        choice["disable_parallel_tool_use"], bool
    ):
        return None
    disable = choice.get("disable_parallel_tool_use")
    name: str | None = None
    if mode == "tool":
        candidate = choice.get("name")
        if not isinstance(candidate, str) or not candidate:
            return None
        name = candidate
    return ToolChoiceIntent(mode=mode, name=name, disable_parallel=disable)


def intent_from_responses_tool_choice(
    choice: object, parallel_tool_calls: object
) -> ToolChoiceIntent | None:
    """Read supported Responses choices; only explicit false imposes a parallel restriction."""
    disable = True if parallel_tool_calls is False else None
    if choice == "auto":
        return ToolChoiceIntent(mode="auto", disable_parallel=disable)
    if choice == "required":
        return ToolChoiceIntent(mode="any", disable_parallel=disable)
    if choice == "none":
        return ToolChoiceIntent(mode="none", disable_parallel=disable)
    if isinstance(choice, Mapping) and set(cast(Mapping[str, Any], choice)) == {"type", "name"}:
        entry = dict[str, Any](cast(Mapping[str, Any], choice))
        if entry.get("type") == "function":
            name = entry.get("name")
            if isinstance(name, str) and name:
                return ToolChoiceIntent(mode="tool", name=name, disable_parallel=disable)
    return None
