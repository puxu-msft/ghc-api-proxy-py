from app.models.anthropic import AnthropicMessage, AnthropicTool, ContentBlock


def process_tool_blocks(
    messages: list[AnthropicMessage],
    tools: list[AnthropicTool],
) -> tuple[list[AnthropicMessage], int, int, int]:
    canonical_names = {tool.name.lower(): tool.name for tool in tools}
    seen_use_ids: set[str] = set()
    handled_result_messages: set[int] = set()
    rewritten = list(messages)
    orphan_uses = 0
    orphan_results = 0
    fixed = 0

    for index, message in enumerate(messages):
        if message.role != "assistant" or not isinstance(message.content, list):
            continue

        candidate_indexes: dict[str, int] = {}
        removed_use_indexes: set[int] = set()
        for block_index, block in enumerate(message.content):
            if block.type != "tool_use":
                continue
            if not block.id or block.id in seen_use_ids:
                removed_use_indexes.add(block_index)
                orphan_uses += 1
                continue
            seen_use_ids.add(block.id)
            candidate_indexes[block.id] = block_index

        result_message_index = index + 1
        result_message = (
            messages[result_message_index]
            if result_message_index < len(messages)
            and messages[result_message_index].role == "user"
            else None
        )
        first_result_indexes: dict[str, int] = {}
        if result_message is not None and isinstance(result_message.content, list):
            for block_index, block in enumerate(result_message.content):
                if (
                    block.type == "tool_result"
                    and block.tool_use_id
                    and block.tool_use_id not in first_result_indexes
                ):
                    first_result_indexes[block.tool_use_id] = block_index

        matched_ids = candidate_indexes.keys() & first_result_indexes.keys()
        for tool_use_id, block_index in candidate_indexes.items():
            if tool_use_id not in matched_ids:
                removed_use_indexes.add(block_index)
                orphan_uses += 1

        assistant_blocks: list[ContentBlock] = []
        for block_index, block in enumerate(message.content):
            if block_index in removed_use_indexes:
                continue
            if block.type == "tool_use" and block.name:
                canonical = canonical_names.get(block.name.lower())
                if canonical and canonical != block.name:
                    block = block.model_copy(update={"name": canonical})
                    fixed += 1
            assistant_blocks.append(block)
        rewritten[index] = message.model_copy(update={"content": assistant_blocks})

        if result_message is not None and isinstance(result_message.content, list):
            kept_results: list[ContentBlock] = []
            other_blocks: list[ContentBlock] = []
            for block_index, block in enumerate(result_message.content):
                if block.type != "tool_result":
                    other_blocks.append(block)
                    continue
                if (
                    block.tool_use_id in matched_ids
                    and first_result_indexes.get(block.tool_use_id) == block_index
                ):
                    kept_results.append(block)
                else:
                    orphan_results += 1
            rewritten[result_message_index] = result_message.model_copy(
                update={"content": [*kept_results, *other_blocks]}
            )
            handled_result_messages.add(result_message_index)

    for index, message in enumerate(messages):
        if (
            message.role != "user"
            or index in handled_result_messages
            or not isinstance(message.content, list)
        ):
            continue
        blocks: list[ContentBlock] = []
        for block in message.content:
            if block.type == "tool_result":
                orphan_results += 1
                continue
            blocks.append(block)
        rewritten[index] = message.model_copy(update={"content": blocks})

    cleaned = [
        message
        for message in rewritten
        if not isinstance(message.content, list) or message.content
    ]
    return cleaned, orphan_uses, orphan_results, fixed
