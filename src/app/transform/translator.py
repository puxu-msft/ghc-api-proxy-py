import copy
import json
from typing import Any, cast


def openai_to_anthropic(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    source_messages = result.pop("messages", [])
    output_messages: list[dict[str, Any]] = []
    system_parts: list[str] = []
    for message in source_messages:
        role = message.get("role")
        if role == "system":
            if isinstance(message.get("content"), str):
                system_parts.append(message["content"])
            continue
        output = copy.deepcopy(message)
        if role == "assistant" and message.get("tool_calls"):
            blocks: list[dict[str, Any]] = []
            if message.get("content"):
                blocks.append({"type": "text", "text": message["content"]})
            for call in message["tool_calls"]:
                function = call["function"]
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call["id"],
                        "name": function["name"],
                        "input": json.loads(function["arguments"]),
                    }
                )
            output["content"] = blocks
            output.pop("tool_calls", None)
        elif role == "tool":
            tool_result = {
                "type": "tool_result",
                "tool_use_id": message.get("tool_call_id"),
                "content": message.get("content", ""),
            }
            output["role"] = "user"
            output["content"] = [tool_result]
            output.pop("tool_call_id", None)
        output_messages.append(output)
    result["messages"] = output_messages
    if system_parts:
        result["system"] = "\n".join(system_parts)
    return result


def anthropic_to_openai(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    source_messages = result.pop("messages", [])
    output_messages: list[dict[str, Any]] = []
    system = result.pop("system", None)
    if isinstance(system, str):
        output_messages.append({"role": "system", "content": system})
    elif isinstance(system, list):
        system_blocks = cast(list[dict[str, Any]], system)
        text = "\n".join(
            str(block.get("text", ""))
            for block in system_blocks
            if block.get("type") == "text"
        )
        if text:
            output_messages.append({"role": "system", "content": text})
    for message in source_messages:
        output = copy.deepcopy(message)
        content = message.get("content")
        if isinstance(content, list):
            blocks = cast(list[dict[str, Any]], content)
            texts = [
                str(block.get("text", ""))
                for block in blocks
                if block.get("type") == "text"
            ]
            calls = [block for block in blocks if block.get("type") == "tool_use"]
            results = [block for block in blocks if block.get("type") == "tool_result"]
            if results:
                for block in results:
                    tool_message = {
                        key: copy.deepcopy(value)
                        for key, value in block.items()
                        if key not in ("type", "tool_use_id")
                    }
                    tool_message.update(
                        {
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id"),
                            "content": block.get("content", ""),
                        }
                    )
                    output_messages.append(tool_message)
                continue
            output["content"] = "".join(texts) or None
            if calls:
                output["tool_calls"] = [
                    {
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {}), separators=(",", ":")),
                        },
                    }
                    for block in calls
                ]
        output_messages.append(output)
    result["messages"] = output_messages
    return result
