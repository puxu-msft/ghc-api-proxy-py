import copy
import json
from collections.abc import Sequence
from typing import Any, Literal


def deduplicate_tool_calls(
    messages: Sequence[dict[str, Any]],
    mode: Literal["input", "result"],
) -> list[dict[str, Any]]:
    pairs: dict[str, tuple[int, int]] = {}
    result_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, message in enumerate(messages):
        for block in message.get("content", []):
            if block.get("type") == "tool_result" and isinstance(block.get("tool_use_id"), str):
                result_by_id[block["tool_use_id"]] = (index, block)
    for index, message in enumerate(messages):
        for block in message.get("content", []):
            if block.get("type") != "tool_use" or block.get("id") not in result_by_id:
                continue
            result_index, result = result_by_id[block["id"]]
            signature_data = [block.get("name"), block.get("input")]
            if mode == "result":
                signature_data.append(result.get("content"))
            signature = json.dumps(signature_data, sort_keys=True, separators=(",", ":"))
            pairs[signature] = (index, result_index)
    keep_indexes = {index for pair in pairs.values() for index in pair}
    return [
        copy.deepcopy(message)
        for index, message in enumerate(messages)
        if index in keep_indexes
    ]