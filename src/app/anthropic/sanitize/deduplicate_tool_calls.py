import copy
import json
from collections.abc import Sequence
from typing import Any, Literal, cast


def deduplicate_tool_calls(
    messages: Sequence[dict[str, Any]],
    mode: Literal["input", "result"],
) -> list[dict[str, Any]]:
    pairs: dict[str, tuple[int, int]] = {}
    result_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, message in enumerate(messages):
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in cast(list[object], content):
            if not isinstance(block, dict):
                continue
            typed_block = cast(dict[str, Any], block)
            if typed_block.get("type") == "tool_result" and isinstance(
                typed_block.get("tool_use_id"), str
            ):
                result_by_id[typed_block["tool_use_id"]] = (index, typed_block)
    for index, message in enumerate(messages):
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in cast(list[object], content):
            if not isinstance(block, dict):
                continue
            typed_block = cast(dict[str, Any], block)
            if typed_block.get("type") != "tool_use" or typed_block.get("id") not in result_by_id:
                continue
            result_index, result = result_by_id[typed_block["id"]]
            signature_data: list[Any] = [
                typed_block.get("name"),
                typed_block.get("input"),
            ]
            if mode == "result":
                signature_data.append(result.get("content"))
            signature = json.dumps(signature_data, sort_keys=True, separators=(",", ":"))
            pairs[signature] = (index, result_index)
    keep_indexes = {index for pair in pairs.values() for index in pair}
    tool_indexes = {
        index
        for index, message in enumerate(messages)
        if any(
            cast(dict[str, Any], block).get("type") in ("tool_use", "tool_result")
            for block in cast(list[object], message.get("content", []))
            if isinstance(block, dict)
        )
    }
    return [
        copy.deepcopy(message)
        for index, message in enumerate(messages)
        if index in keep_indexes or index not in tool_indexes
    ]