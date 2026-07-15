import copy
from typing import Any, cast


def sanitize_chat_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tool_call_ids: set[str] = {
        call_id
        for message in messages
        for call in cast(list[object], message.get("tool_calls", []))
        if isinstance(call, dict)
        for call_id in [cast(dict[str, Any], call).get("id")]
        if isinstance(call_id, str)
    }
    tool_result_ids = {
        message.get("tool_call_id")
        for message in messages
        if message.get("role") == "tool" and isinstance(message.get("tool_call_id"), str)
    }
    paired = tool_call_ids & tool_result_ids
    cleaned: list[dict[str, Any]] = []
    for source in messages:
        message = copy.deepcopy(source)
        if message.get("role") == "tool" and message.get("tool_call_id") not in paired:
            continue
        if isinstance(message.get("tool_calls"), list):
            message["tool_calls"] = [
                call
                for call in cast(list[object], message["tool_calls"])
                if isinstance(call, dict)
                and cast(dict[str, Any], call).get("id") in paired
            ]
            if not message["tool_calls"]:
                message.pop("tool_calls")
        cleaned.append(message)
    return cleaned