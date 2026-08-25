"""Identifying the client's tool-search tool, and declining to.

Most of these are about **not** identifying one. Promotion replaces the tool it picks, so a wrong answer deletes a capability the client declared and does it silently — which makes "declines correctly" the property worth the most tests.
"""

from typing import Any

from app.pipeline.translation_driver.content import BlockKind, ContentBlock, SemanticMessage
from app.pipeline.translation_driver.tool_search import (
    CLIENT_SEARCH_NAMES,
    as_client_search_tool,
    has_deferred_tool,
    is_hosted_search_tool,
    resolve_client_search_tool,
)

SEARCH_TOOL: dict[str, Any] = {
    "name": "ToolSearch",
    "description": "Fetches full schema definitions for deferred tools so they can be called.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
}
DEFERRED: dict[str, Any] = {
    "name": "get_weather",
    "description": "Get the weather.",
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
    "defer_loading": True,
}
PLAIN: dict[str, Any] = {"name": "Read", "input_schema": {"type": "object"}}


def tool_use(call_id: str, name: str) -> ContentBlock:
    return ContentBlock(kind=BlockKind.TOOL_USE, call_id=call_id, name=name)


def tool_result(call_id: str, output: Any) -> ContentBlock:
    return ContentBlock(kind=BlockKind.TOOL_RESULT, call_id=call_id, output=output)


def test_a_request_with_no_deferred_tool_is_not_examined_at_all() -> None:
    """The gate, and the reason a tool called `ToolSearch` is usually safe from this code.

    Without `defer_loading` there is no tool-search mechanism in play, so there is nothing to identify — and an ordinary tool that happens to carry a known search name never even reaches the name match.
    """
    assert resolve_client_search_tool([SEARCH_TOOL, PLAIN], []) == ""
    assert has_deferred_tool([SEARCH_TOOL, PLAIN]) is False


def test_the_known_name_is_used_once_a_deferred_tool_is_present() -> None:
    assert resolve_client_search_tool([SEARCH_TOOL, DEFERRED], []) == "ToolSearch"


def test_history_names_the_search_tool_even_when_it_is_called_something_else() -> None:
    """The one identification that cannot be wrong, and it outranks the name list.

    Returning `tool_reference` blocks *is* the definition of a custom search tool, so the call they answer names it by construction. A client using a name nobody hardcoded is identified correctly from the second turn on — which is also the case the name list alone would get wrong.
    """
    messages = [
        SemanticMessage(role="assistant", blocks=(tool_use("call_1", "FindTools"),)),
        SemanticMessage(
            role="user",
            blocks=(tool_result("call_1", [{"type": "tool_reference", "tool_name": "get_weather"}]),),
        ),
    ]

    assert resolve_client_search_tool([{"name": "FindTools", "input_schema": {}}, DEFERRED], messages) == "FindTools"


def test_history_wins_over_a_tool_that_merely_carries_a_known_name() -> None:
    """Both signals present and disagreeing: the protocol-grade one decides.

    A client could plausibly ship both an ordinary tool named `ToolSearch` and a differently-named real search tool. The name list would pick the wrong one; the history cannot.
    """
    messages = [
        SemanticMessage(role="assistant", blocks=(tool_use("call_1", "FindTools"),)),
        SemanticMessage(
            role="user",
            blocks=(tool_result("call_1", [{"type": "tool_reference", "tool_name": "get_weather"}]),),
        ),
    ]
    tools: list[dict[str, Any]] = [SEARCH_TOOL, {"name": "FindTools", "input_schema": {}}, DEFERRED]

    assert resolve_client_search_tool(tools, messages) == "FindTools"


def test_an_unrecognised_name_with_no_history_declines() -> None:
    """The case the whole module is shaped around: a real search tool this code cannot identify.

    Declining means the caller strips `defer_loading` and sends a request that works, minus the token saving. Guessing would mean picking some other tool and deleting it from the request.
    """
    assert resolve_client_search_tool([{"name": "FindTools", "input_schema": {}}, DEFERRED], []) == ""


def test_two_known_names_decline_rather_than_pick_one() -> None:
    """Nobody has been observed sending this, so any tie-break would be invented."""
    both: list[dict[str, Any]] = [SEARCH_TOOL, {"name": "tool_search", "input_schema": {}}, DEFERRED]

    assert resolve_client_search_tool(both, []) == ""


def test_a_tool_result_without_tool_references_does_not_name_anything() -> None:
    """An ordinary tool result must not be read as evidence about tool search."""
    messages = [
        SemanticMessage(role="assistant", blocks=(tool_use("call_1", "Read"),)),
        SemanticMessage(role="user", blocks=(tool_result("call_1", [{"type": "text", "text": "file contents"}]),)),
    ]

    assert resolve_client_search_tool([{"name": "Read", "input_schema": {}}, DEFERRED], messages) == ""


def test_the_hosted_declaration_is_recognised_by_family_not_by_date() -> None:
    """Anthropic dates these, so matching the exact spelling would go quiet on the next release."""
    assert is_hosted_search_tool({"type": "tool_search_tool_regex_20251119"}) is True
    assert is_hosted_search_tool({"type": "tool_search_tool_bm25_20251119"}) is True
    assert is_hosted_search_tool({"type": "tool_search_tool_regex_20261231"}) is True
    assert is_hosted_search_tool({"name": "ToolSearch"}) is False
    assert is_hosted_search_tool({"type": "web_search_20250305"}) is False


def test_promotion_carries_the_description_upstream_insists_on() -> None:
    """Upstream refuses a client-executed search with no description, so this cannot be optional."""
    promoted = as_client_search_tool(SEARCH_TOOL)

    assert promoted["type"] == "tool_search"
    assert promoted["execution"] == "client"
    assert promoted["description"] == SEARCH_TOOL["description"]
    assert promoted["parameters"] == SEARCH_TOOL["input_schema"]


def test_a_tool_with_no_description_still_gets_one() -> None:
    """The alternative is trading this request's 400 for a different 400."""
    promoted = as_client_search_tool({"name": "FindTools", "input_schema": {"type": "object"}})

    assert isinstance(promoted["description"], str)
    assert promoted["description"].strip()


def test_the_known_names_are_the_two_first_party_clients_hardcode() -> None:
    """Pinned because they disagree, and that disagreement is the argument for the list existing.

    Claude Code hardcodes `ToolSearch`; VS Code Copilot Chat hardcodes `tool_search`. If a future edit collapsed these to one name, half the clients this feature exists for would stop being recognised.
    """
    assert frozenset({"ToolSearch", "tool_search"}) == CLIENT_SEARCH_NAMES
