from anthropic.types import ServerToolUseBlock, WebSearchToolResultBlock

from app.pipeline.anthropic_server_tools import (
    project_web_search_action,
    unavailable_web_search_pair,
)
from app.pipeline.delivery.formats.anthropic_messages_synthetic_reply import (
    failed_search_blocks,
)
from app.pipeline.server_tool_text import web_search_call_text


def test_a_search_query_is_normalized_for_a_responses_action() -> None:
    projected = project_web_search_action(
        {"type": "search", "query": "  current weather\n"}
    )

    assert projected.input == {"query": "current weather"}
    assert projected.readable == "current weather"
    assert projected.loss_detail == ""


def test_open_page_and_find_actions_remain_readable_without_becoming_queries() -> None:
    opened = project_web_search_action(
        {"type": "open_page", "url": "https://example.com/page"}
    )
    found = project_web_search_action(
        {
            "type": "find_in_page",
            "url": "https://example.com/page",
            "pattern": "needle",
        }
    )

    assert opened.input == {}
    assert opened.readable == "open_page https://example.com/page"
    assert "open_page" in opened.loss_detail
    assert found.input == {}
    assert found.readable == "find_in_page https://example.com/page needle"
    assert "needle" in found.loss_detail
    assert web_search_call_text(
        {"type": "find_in_page", "url": "https://example.com/page", "pattern": "needle"}
    ) == "[web_search] find_in_page https://example.com/page needle"


def test_an_unavailable_pair_is_schema_shaped_and_uses_one_local_id() -> None:
    pair = unavailable_web_search_pair(
        {"type": "search", "query": "release notes"},
        call_id="srvtoolu_local",
    )

    assert pair.call == {
        "type": "server_tool_use",
        "id": "srvtoolu_local",
        "name": "web_search",
        "input": {"query": "release notes"},
    }
    assert pair.result == {
        "type": "web_search_tool_result",
        "tool_use_id": "srvtoolu_local",
        "content": {
            "type": "web_search_tool_result_error",
            "error_code": "unavailable",
        },
    }
    ServerToolUseBlock.model_validate(pair.call)
    WebSearchToolResultBlock.model_validate(pair.result)


def test_generated_ids_are_local_unique_and_not_the_upstream_handle() -> None:
    upstream_id = "opaque-upstream-id"

    first = unavailable_web_search_pair(
        {"type": "search", "query": "one", "id": upstream_id}
    )
    second = unavailable_web_search_pair(
        {"type": "search", "query": "two", "id": upstream_id}
    )

    assert first.call["id"].startswith("srvtoolu_")
    assert len(first.call["id"].removeprefix("srvtoolu_")) == 24
    assert first.call["id"] != second.call["id"]
    assert upstream_id not in first.call["id"]
    assert first.result["tool_use_id"] == first.call["id"]
    assert second.result["tool_use_id"] == second.call["id"]


def test_the_synthetic_failure_keeps_the_request_query_value_exact() -> None:
    query = "  Perform a web search for bun\n"

    call, _ = failed_search_blocks(query, call_id="srvtoolu_local")

    assert call["input"] == {"query": query}
