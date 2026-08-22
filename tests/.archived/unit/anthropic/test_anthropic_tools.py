from app.anthropic.message_tools import preprocess_tools


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


def test_preprocess_tools_does_not_modify_typed_tool_declarations() -> None:
    tools = [{"name": "native", "type": "web_search_20250305", "future": True}]

    result = preprocess_tools(tools, inject_tool_search=False)

    assert result == tools
