from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

THINKING_TYPES = frozenset({"thinking", "redacted_thinking"})
type ThinkingPolicy = Literal["preserve", "stripped"]
type SanitizeMode = Literal[
    "false",
    "all_empty",
    "signature_empty",
    "thinking_empty",
    "any_empty",
]


def _is_thinking_block(block: object) -> bool:
    if not isinstance(block, Mapping):
        return False
    return cast(Mapping[str, Any], block).get("type") in THINKING_TYPES


def has_thinking_blocks(message: Mapping[str, Any]) -> bool:
    if message.get("role") != "assistant" or not isinstance(message.get("content"), list):
        return False
    return any(_is_thinking_block(block) for block in cast(list[object], message["content"]))


def should_preserve_thinking_blocks(
    message: Mapping[str, Any],
    policy: ThinkingPolicy,
) -> bool:
    return policy != "stripped" and has_thinking_blocks(message)


def sanitize_empty_thinking(
    content: Sequence[Mapping[str, Any]],
    mode: SanitizeMode,
) -> tuple[list[dict[str, Any]], int]:
    if mode == "false":
        return [dict(block) for block in content], 0
    output: list[dict[str, Any]] = []
    removed = 0
    for block in content:
        if block.get("type") not in THINKING_TYPES:
            output.append(dict(block))
            continue
        thinking_empty = not block.get("thinking") and not block.get("data")
        signature_empty = not block.get("signature")
        should_remove = {
            "all_empty": thinking_empty and signature_empty,
            "signature_empty": signature_empty,
            "thinking_empty": thinking_empty,
            "any_empty": thinking_empty or signature_empty,
        }[mode]
        if should_remove:
            removed += 1
        else:
            output.append(dict(block))
    return output, removed
