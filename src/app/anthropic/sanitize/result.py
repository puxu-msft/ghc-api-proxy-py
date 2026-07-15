from dataclasses import dataclass

from app.models.anthropic import AnthropicMessage


@dataclass(frozen=True, slots=True)
class SanitizationResult:
    messages: list[AnthropicMessage]
    orphaned_tool_uses_removed: int = 0
    orphaned_tool_results_removed: int = 0
    empty_text_blocks_removed: int = 0
    tool_names_fixed: int = 0