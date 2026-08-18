from app.models.anthropic import AnthropicMessage, ContentBlock


def filter_empty_text_blocks(
    messages: list[AnthropicMessage],
) -> tuple[list[AnthropicMessage], int]:
    removed = 0
    cleaned: list[AnthropicMessage] = []
    for message in messages:
        if not isinstance(message.content, list):
            cleaned.append(message)
            continue
        blocks: list[ContentBlock] = []
        for block in message.content:
            if block.type == "text" and not (block.text or "").strip():
                removed += 1
                continue
            blocks.append(block)
        cleaned.append(message.model_copy(update={"content": blocks}))
    return cleaned, removed
