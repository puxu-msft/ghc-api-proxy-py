from app.anthropic.sanitize import sanitize_messages
from app.models.anthropic import AnthropicMessage, AnthropicTool, ContentBlock


def _message(role: str, content: list[dict[str, object]]) -> AnthropicMessage:
    return AnthropicMessage.model_validate({"role": role, "content": content})


def _content(messages: list[AnthropicMessage], index: int) -> list[ContentBlock]:
    content = messages[index].content
    assert isinstance(content, list)
    return content


def test_only_immediately_following_user_message_can_complete_tool_use() -> None:
    messages = [
        _message("assistant", [{"type": "tool_use", "id": "call-1", "name": "Read", "input": {}}]),
        _message("assistant", [{"type": "text", "text": "intervening"}]),
        _message("user", [{"type": "tool_result", "tool_use_id": "call-1", "content": "late"}]),
    ]

    result = sanitize_messages(messages, [])

    assert result.orphaned_tool_uses_removed == 1
    assert result.orphaned_tool_results_removed == 1
    assert len(result.messages) == 1
    assert _content(result.messages, 0)[0].text == "intervening"


def test_result_before_tool_use_is_removed_without_dropping_text() -> None:
    messages = [
        _message(
            "user",
            [
                {"type": "tool_result", "tool_use_id": "future", "content": "stale"},
                {"type": "text", "text": "keep"},
            ],
        ),
        _message(
            "assistant",
            [{"type": "tool_use", "id": "future", "name": "Read", "input": {}}],
        ),
        _message(
            "user",
            [{"type": "tool_result", "tool_use_id": "future", "content": "valid"}],
        ),
    ]

    result = sanitize_messages(messages, [])

    assert result.orphaned_tool_results_removed == 1
    assert _content(result.messages, 0)[0].text == "keep"
    assert _content(result.messages, 2)[0].content == "valid"


def test_parallel_pairs_keep_complete_pair_and_remove_missing_pair() -> None:
    messages = [
        _message(
            "assistant",
            [
                {"type": "tool_use", "id": "call-a", "name": "Read", "input": {}},
                {"type": "tool_use", "id": "call-b", "name": "Write", "input": {}},
            ],
        ),
        _message(
            "user",
            [
                {"type": "tool_result", "tool_use_id": "call-a", "content": "ok"},
                {"type": "text", "text": "continue"},
            ],
        ),
    ]

    result = sanitize_messages(messages, [])

    assert result.orphaned_tool_uses_removed == 1
    assert result.orphaned_tool_results_removed == 0
    assistant = _content(result.messages, 0)
    user = _content(result.messages, 1)
    assert [block.id for block in assistant if block.type == "tool_use"] == ["call-a"]
    assert [block.tool_use_id for block in user if block.type == "tool_result"] == ["call-a"]


def test_duplicate_call_and_result_ids_keep_only_first_blocks() -> None:
    messages = [
        _message(
            "assistant",
            [
                {"type": "tool_use", "id": "dup", "name": "Read", "input": {"n": 1}},
                {"type": "tool_use", "id": "dup", "name": "Read", "input": {"n": 2}},
            ],
        ),
        _message(
            "user",
            [
                {"type": "tool_result", "tool_use_id": "dup", "content": "first"},
                {"type": "tool_result", "tool_use_id": "dup", "content": "second"},
            ],
        ),
    ]

    result = sanitize_messages(messages, [])

    assert result.orphaned_tool_uses_removed == 1
    assert result.orphaned_tool_results_removed == 1
    assert len(_content(result.messages, 0)) == 1
    assert _content(result.messages, 0)[0].input == {"n": 1}
    assert len(_content(result.messages, 1)) == 1
    assert _content(result.messages, 1)[0].content == "first"


def test_tool_use_without_id_is_removed() -> None:
    messages = [
        _message(
            "assistant",
            [
                {"type": "tool_use", "name": "Read", "input": {}},
                {"type": "tool_use", "id": "", "name": "Read", "input": {}},
                {"type": "text", "text": "keep"},
            ],
        )
    ]

    result = sanitize_messages(messages, [])

    assert result.orphaned_tool_uses_removed == 2
    assert [block.text for block in _content(result.messages, 0)] == ["keep"]


def test_cross_round_duplicate_id_keeps_oldest_complete_pair() -> None:
    messages = [
        _message(
            "assistant",
            [{"type": "tool_use", "id": "same", "name": "Read", "input": {"round": 1}}],
        ),
        _message("user", [{"type": "tool_result", "tool_use_id": "same", "content": "one"}]),
        _message(
            "assistant",
            [{"type": "tool_use", "id": "same", "name": "Read", "input": {"round": 2}}],
        ),
        _message("user", [{"type": "tool_result", "tool_use_id": "same", "content": "two"}]),
    ]

    result = sanitize_messages(messages, [])

    assert result.orphaned_tool_uses_removed == 1
    assert result.orphaned_tool_results_removed == 1
    assert len(result.messages) == 2
    assert _content(result.messages, 0)[0].input == {"round": 1}
    assert _content(result.messages, 1)[0].content == "one"


def test_cross_round_duplicate_id_does_not_reassign_an_orphaned_first_use() -> None:
    messages = [
        _message(
            "assistant",
            [{"type": "tool_use", "id": "same", "name": "Read", "input": {"round": 1}}],
        ),
        _message("assistant", [{"type": "text", "text": "intervening"}]),
        _message(
            "assistant",
            [{"type": "tool_use", "id": "same", "name": "Read", "input": {"round": 2}}],
        ),
        _message("user", [{"type": "tool_result", "tool_use_id": "same", "content": "two"}]),
    ]

    result = sanitize_messages(messages, [])

    assert result.orphaned_tool_uses_removed == 2
    assert result.orphaned_tool_results_removed == 1
    assert len(result.messages) == 1
    assert _content(result.messages, 0)[0].text == "intervening"


def test_tool_results_are_stably_moved_before_other_user_content() -> None:
    messages = [
        _message("assistant", [{"type": "tool_use", "id": "call", "name": "Read", "input": {}}]),
        _message(
            "user",
            [
                {"type": "text", "text": "before"},
                {"type": "tool_result", "tool_use_id": "call", "content": "result"},
                {"type": "image", "source": {"type": "base64", "data": "AA=="}},
                {"type": "text", "text": "after"},
            ],
        ),
    ]

    result = sanitize_messages(messages, [])

    user = _content(result.messages, 1)
    assert [block.type for block in user] == ["tool_result", "text", "image", "text"]
    assert [block.text for block in user if block.type == "text"] == ["before", "after"]


def test_unmatched_tool_block_is_removed_without_dropping_mixed_message() -> None:
    messages = [
        _message(
            "assistant",
            [
                {"type": "text", "text": "keep"},
                {"type": "tool_use", "id": "orphan", "name": "Read", "input": {}},
            ],
        )
    ]

    result = sanitize_messages(messages, [])

    assert len(result.messages) == 1
    assert [block.text for block in _content(result.messages, 0)] == ["keep"]


def test_tool_pair_repair_is_idempotent_and_fixes_only_retained_name() -> None:
    tools = [AnthropicTool(name="Read", input_schema={"type": "object"})]
    messages = [
        _message(
            "assistant",
            [
                {"type": "tool_use", "id": "kept", "name": "read", "input": {}},
                {"type": "tool_use", "id": "dropped", "name": "read", "input": {}},
            ],
        ),
        _message("user", [{"type": "tool_result", "tool_use_id": "kept", "content": "ok"}]),
    ]

    first = sanitize_messages(messages, tools)
    second = sanitize_messages(first.messages, tools)

    assert first.tool_names_fixed == 1
    assert second.messages == first.messages
    assert second.orphaned_tool_uses_removed == 0
    assert second.orphaned_tool_results_removed == 0
    assert second.tool_names_fixed == 0
