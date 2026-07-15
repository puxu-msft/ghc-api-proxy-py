from app.anthropic.sanitize import sanitize_messages
from app.models.anthropic import AnthropicMessage, AnthropicTool


def test_tool_pair_is_preserved_and_tool_name_case_is_fixed() -> None:
    messages = [
        AnthropicMessage.model_validate(
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "tool-1", "name": "read", "input": {}}],
            }
        ),
        AnthropicMessage.model_validate(
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "tool-1", "content": "ok"}],
            }
        ),
    ]
    tools = [AnthropicTool(name="Read", input_schema={"type": "object"})]

    result = sanitize_messages(messages, tools)

    assert result.orphaned_tool_uses_removed == 0
    assert result.orphaned_tool_results_removed == 0
    content = result.messages[0].content
    assert isinstance(content, list)
    assert content[0].name == "Read"


def test_orphan_tool_blocks_and_empty_text_are_removed() -> None:
    messages = [
        AnthropicMessage.model_validate(
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": ""},
                    {"type": "tool_use", "id": "orphan-use", "name": "Read", "input": {}},
                    {"type": "text", "text": "keep"},
                ],
            }
        ),
        AnthropicMessage.model_validate(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "orphan-result", "content": "x"}
                ],
            }
        ),
    ]

    result = sanitize_messages(messages, [])

    assert result.orphaned_tool_uses_removed == 1
    assert result.orphaned_tool_results_removed == 1
    assert result.empty_text_blocks_removed == 1
    assistant_content = result.messages[0].content
    assert isinstance(assistant_content, list)
    assert [block.text for block in assistant_content] == ["keep"]
    assert result.messages[1].content == []


def test_string_content_is_not_rewritten() -> None:
    message = AnthropicMessage(role="user", content="hello")

    result = sanitize_messages([message], [])

    assert result.messages == [message]