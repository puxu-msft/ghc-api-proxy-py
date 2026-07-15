from app.anthropic.message_tools import preprocess_tools
from app.anthropic.server_tool_filter import filter_server_tool_blocks


def test_preprocess_tools_marks_deferred_and_injects_search() -> None:
    tools = [{"name": "Read", "input_schema": {"type": "object"}}]
    result = preprocess_tools(
        tools,
        inject_tool_search=True,
        non_deferred={"Read"},
    )
    assert result[0]["name"] == "Read"
    assert "defer_loading" not in result[0]
    assert result[-1]["type"] == "tool_search_tool_regex_20251119"


def test_server_tool_filter_removes_matching_blocks_and_remaps_indexes() -> None:
    blocks = [
        {"type": "text", "text": "before"},
        {"type": "server_tool_use", "name": "web_search_20250305", "id": "s1"},
        {"type": "text", "text": "after"},
    ]
    filtered, index_map = filter_server_tool_blocks(blocks, denied_prefixes={"web_search_"})
    assert [block["text"] for block in filtered] == ["before", "after"]
    assert index_map == {0: 0, 2: 1}