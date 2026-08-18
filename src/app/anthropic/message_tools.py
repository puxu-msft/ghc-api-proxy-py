import copy
from collections.abc import Iterable, Sequence
from typing import Any


def preprocess_tools(
    tools: Sequence[dict[str, Any]],
    *,
    inject_tool_search: bool,
    non_deferred: Iterable[str] = (),
) -> list[dict[str, Any]]:
    eager = set(non_deferred)
    output = [copy.deepcopy(tool) for tool in tools]
    for tool in output:
        name = tool.get("name")
        tool_type = tool.get("type")
        if tool_type is None and isinstance(name, str) and name not in eager:
            tool["defer_loading"] = True
    has_search = any(
        str(tool.get("type", "")).startswith("tool_search")
        for tool in output
    )
    if inject_tool_search and not has_search:
        output.append(
            {
                "type": "tool_search_tool_regex_20251119",
                "name": "tool_search_tool_regex",
            }
        )
    return output
