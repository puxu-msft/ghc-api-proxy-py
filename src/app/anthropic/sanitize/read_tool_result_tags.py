import copy
from typing import Any

from app.anthropic.sanitize.system_reminders import strip_system_reminders


def strip_read_tool_result_tags(block: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(block)
    if result.get("type") == "tool_result" and result.get("tool_name") == "Read":
        content = result.get("content")
        if isinstance(content, str):
            result["content"] = strip_system_reminders(content)
    return result