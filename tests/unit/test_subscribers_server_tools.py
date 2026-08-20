"""What the server-tool subscriber removes, and what it must leave alone.

The failure it exists to prevent is a whole-request 400, so the cases that matter most are the ones where removing a declaration is not enough on its own — a `tool_choice` left pointing at what was just removed produces a second rejection in place of the first.
"""

from typing import Any

from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.server_tools import adapt_server_tools

WEB_SEARCH: dict[str, Any] = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
CALCULATOR: dict[str, Any] = {"name": "calculator", "input_schema": {"type": "object"}}


def context(payload: dict[str, Any], *, target: WireFormat = WireFormat.ANTHROPIC_MESSAGES) -> RequestContext:
    ctx = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-opus-5",
        payload=payload,
    )
    ctx.target_format = target
    return ctx


async def test_a_web_search_declaration_is_removed_and_the_client_tools_are_not() -> None:
    ctx = context({"tools": [CALCULATOR, WEB_SEARCH]})

    await adapt_server_tools(ctx)

    assert ctx.payload["tools"] == [CALCULATOR]


async def test_the_tools_field_goes_away_rather_than_becoming_empty() -> None:
    # `[]` has never been put to upstream and says something different from saying nothing.
    ctx = context({"tools": [WEB_SEARCH]})

    await adapt_server_tools(ctx)

    assert "tools" not in ctx.payload


async def test_a_choice_naming_the_removed_tool_goes_with_it() -> None:
    # Left behind, this trades the rejection being prevented for `Tool 'web_search' not found`.
    ctx = context(
        {"tools": [CALCULATOR, WEB_SEARCH], "tool_choice": {"type": "tool", "name": "web_search"}}
    )

    await adapt_server_tools(ctx)

    assert ctx.payload["tools"] == [CALCULATOR]
    assert "tool_choice" not in ctx.payload


async def test_a_choice_naming_a_surviving_tool_is_kept() -> None:
    ctx = context(
        {"tools": [CALCULATOR, WEB_SEARCH], "tool_choice": {"type": "tool", "name": "calculator"}}
    )

    await adapt_server_tools(ctx)

    assert ctx.payload["tool_choice"] == {"type": "tool", "name": "calculator"}


async def test_any_choice_goes_when_no_tool_is_left_to_choose() -> None:
    ctx = context({"tools": [WEB_SEARCH], "tool_choice": {"type": "any"}})

    await adapt_server_tools(ctx)

    assert "tools" not in ctx.payload
    assert "tool_choice" not in ctx.payload


async def test_client_executed_typed_tools_are_left_alone() -> None:
    # Claude Code really sends these, and nothing has been measured rejecting them. Removing them would break working requests to prevent a failure nobody has seen.
    text_editor: dict[str, Any] = {"type": "text_editor_20250124", "name": "str_replace_editor"}
    memory: dict[str, Any] = {"type": "memory_20250818", "name": "memory"}
    ctx = context({"tools": [text_editor, memory]})

    await adapt_server_tools(ctx)

    assert ctx.payload["tools"] == [text_editor, memory]


async def test_web_fetch_is_removed_too_despite_upstream_wording_it_differently() -> None:
    # Upstream answers `rejected tool(s): web_fetch` with `invalid_request_body` rather than the web-search wording, which is why the predicate reads what we send instead of what comes back.
    web_fetch: dict[str, Any] = {"type": "web_fetch_20250910", "name": "web_fetch"}
    ctx = context({"tools": [CALCULATOR, web_fetch]})

    await adapt_server_tools(ctx)

    assert ctx.payload["tools"] == [CALCULATOR]


async def test_the_bare_openai_spelling_is_removed_too() -> None:
    # A `/responses` request naming a Claude model falls back to the Anthropic endpoint and the translator carries `tools` across verbatim, so the undated OpenAI form really does arrive on this leg.
    bare: dict[str, Any] = {"type": "web_search"}
    ctx = context({"tools": [CALCULATOR, bare]})

    await adapt_server_tools(ctx)

    assert ctx.payload["tools"] == [CALCULATOR]


async def test_a_choice_dangles_even_when_the_removed_declaration_had_no_name() -> None:
    # Deciding against what was removed cannot see this one: there was no name to record. Deciding against what survives can.
    nameless: dict[str, Any] = {"type": "web_search_20250305"}
    ctx = context(
        {"tools": [CALCULATOR, nameless], "tool_choice": {"type": "tool", "name": "web_search"}}
    )

    await adapt_server_tools(ctx)

    assert ctx.payload["tools"] == [CALCULATOR]
    assert "tool_choice" not in ctx.payload


async def test_a_translated_route_is_not_touched() -> None:
    # By this point a translated payload is no longer Anthropic-shaped; a `tools` found there belongs to another protocol and reading it as this one would be reading the wrong field.
    payload: dict[str, Any] = {"tools": [WEB_SEARCH]}
    ctx = context(payload, target=WireFormat.OPENAI_RESPONSES)

    await adapt_server_tools(ctx)

    assert ctx.payload["tools"] == [WEB_SEARCH]


async def test_a_request_with_nothing_to_drop_is_left_exactly_as_it_was() -> None:
    payload: dict[str, Any] = {"tools": [CALCULATOR], "tool_choice": {"type": "auto"}}
    ctx = context(payload)

    await adapt_server_tools(ctx)

    assert ctx.payload == {"tools": [CALCULATOR], "tool_choice": {"type": "auto"}}


async def test_a_request_declaring_no_tools_is_left_exactly_as_it_was() -> None:
    payload: dict[str, Any] = {"messages": []}
    ctx = context(payload)

    await adapt_server_tools(ctx)

    assert ctx.payload == {"messages": []}
