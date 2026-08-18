from app.anthropic.sanitize.result import SanitizationResult
from app.anthropic.sanitize.text_blocks import filter_empty_text_blocks
from app.anthropic.sanitize.tool_blocks import process_tool_blocks
from app.models.anthropic import AnthropicMessage, AnthropicTool


def sanitize_messages(
    messages: list[AnthropicMessage],
    tools: list[AnthropicTool],
) -> SanitizationResult:
    cleaned, orphan_uses, orphan_results, names_fixed = process_tool_blocks(
        messages,
        tools,
    )
    cleaned, empty_removed = filter_empty_text_blocks(cleaned)
    cleaned = [
        message
        for message in cleaned
        if not isinstance(message.content, list) or message.content
    ]
    return SanitizationResult(
        messages=cleaned,
        orphaned_tool_uses_removed=orphan_uses,
        orphaned_tool_results_removed=orphan_results,
        empty_text_blocks_removed=empty_removed,
        tool_names_fixed=names_fixed,
    )


__all__ = ["SanitizationResult", "sanitize_messages"]
