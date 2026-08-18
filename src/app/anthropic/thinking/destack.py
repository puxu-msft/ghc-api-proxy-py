import copy
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from app.anthropic.thinking.protection import THINKING_TYPES

SYNTHETIC_SEPARATOR = "[ghc-api-proxy: thinking separator]"
type DestackStrategy = Literal["passthrough", "insert_text", "move_blocks"]


def _is_thinking(block: Mapping[str, Any]) -> bool:
    return block.get("type") in THINKING_TYPES


def _has_adjacent(content: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        _is_thinking(content[index - 1]) and _is_thinking(content[index])
        for index in range(1, len(content))
    )


def destack_content(
    content: Sequence[Mapping[str, Any]],
    strategy: DestackStrategy,
) -> tuple[list[dict[str, Any]], bool]:
    if strategy == "passthrough" or not _has_adjacent(content):
        return [dict(block) for block in content], False
    if strategy == "insert_text":
        output: list[dict[str, Any]] = []
        for block in content:
            if output and _is_thinking(output[-1]) and _is_thinking(block):
                output.append({"type": "text", "text": SYNTHETIC_SEPARATOR})
            output.append(copy.deepcopy(dict(block)))
        return output, True
    thoughts = [copy.deepcopy(dict(block)) for block in content if _is_thinking(block)]
    separators = [
        copy.deepcopy(dict(block))
        for block in content
        if not _is_thinking(block)
        and (block.get("type") != "text" or str(block.get("text", "")).strip())
    ]
    output = []
    for index, thought in enumerate(thoughts):
        output.append(thought)
        if index < len(thoughts) - 1:
            output.append(
                separators.pop(0)
                if separators
                else {"type": "text", "text": SYNTHETIC_SEPARATOR}
            )
    output.extend(separators)
    return output, True
