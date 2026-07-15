import copy
from collections.abc import Mapping, Sequence
from typing import Any, cast

from app.anthropic.thinking.destack import SYNTHETIC_SEPARATOR
from app.anthropic.thinking.protection import THINKING_TYPES


def strip_all_thinking(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    output = [copy.deepcopy(dict(message)) for message in messages]
    removed = 0
    for message in output:
        content = message.get("content")
        if message.get("role") != "assistant" or not isinstance(content, list):
            continue
        kept: list[Any] = []
        for block in cast(list[Any], content):
            if not isinstance(block, Mapping):
                kept.append(block)
                continue
            typed_block = cast(Mapping[str, Any], block)
            strippable = typed_block.get("type") in THINKING_TYPES or (
                typed_block.get("type") == "text"
                and typed_block.get("text") == SYNTHETIC_SEPARATOR
            )
            if strippable:
                removed += 1
            else:
                kept.append(dict(typed_block))
        message["content"] = kept
    return output, removed