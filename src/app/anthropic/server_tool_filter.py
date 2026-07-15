import copy
from collections.abc import Iterable, Sequence
from typing import Any


def filter_server_tool_blocks(
    blocks: Sequence[dict[str, Any]],
    *,
    denied_prefixes: Iterable[str],
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    prefixes = tuple(denied_prefixes)
    output: list[dict[str, Any]] = []
    index_map: dict[int, int] = {}
    for old_index, block in enumerate(blocks):
        name = block.get("name")
        denied = (
            block.get("type") == "server_tool_use"
            and isinstance(name, str)
            and name.startswith(prefixes)
        )
        if denied:
            continue
        index_map[old_index] = len(output)
        output.append(copy.deepcopy(block))
    return output, index_map