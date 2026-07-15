from app.models.anthropic import AnthropicMessage, AnthropicTool, ContentBlock


def process_tool_blocks(
    messages: list[AnthropicMessage],
    tools: list[AnthropicTool],
) -> tuple[list[AnthropicMessage], int, int, int]:
    tool_use_ids: set[str] = set()
    result_ids: set[str] = set()
    for message in messages:
        if not isinstance(message.content, list):
            continue
        for block in message.content:
            if block.type == "tool_use" and block.id:
                tool_use_ids.add(block.id)
            elif block.type == "tool_result" and block.tool_use_id:
                result_ids.add(block.tool_use_id)

    orphan_uses = tool_use_ids - result_ids
    orphan_results = result_ids - tool_use_ids
    canonical_names = {tool.name.lower(): tool.name for tool in tools}
    fixed = 0
    cleaned: list[AnthropicMessage] = []
    for message in messages:
        if not isinstance(message.content, list):
            cleaned.append(message)
            continue
        blocks: list[ContentBlock] = []
        for block in message.content:
            if block.type == "tool_use" and block.id in orphan_uses:
                continue
            if block.type == "tool_result" and block.tool_use_id in orphan_results:
                continue
            if block.type == "tool_use" and block.name:
                canonical = canonical_names.get(block.name.lower())
                if canonical and canonical != block.name:
                    block = block.model_copy(update={"name": canonical})
                    fixed += 1
            blocks.append(block)
        cleaned.append(message.model_copy(update={"content": blocks}))
    return cleaned, len(orphan_uses), len(orphan_results), fixed