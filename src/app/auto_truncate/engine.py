import copy
from collections.abc import Sequence
from typing import Any, cast


def truncate_messages(
    messages: Sequence[dict[str, Any]],
    *,
    keep_recent_fraction: float = 0.3,
) -> list[dict[str, Any]]:
    preserved_system = [
        copy.deepcopy(message)
        for message in messages
        if message.get("role") == "system"
    ]
    conversational = [message for message in messages if message.get("role") != "system"]
    keep_count = max(1, int(len(conversational) * keep_recent_fraction))
    recent = [copy.deepcopy(message) for message in conversational[-keep_count:]]
    for message in recent[:-1]:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in cast(list[object], content):
            if not isinstance(block, dict):
                continue
            typed_block = cast(dict[str, Any], block)
            if typed_block.get("type") == "tool_result":
                typed_block["content"] = "[truncated tool result]"
    return [*preserved_system, *recent]