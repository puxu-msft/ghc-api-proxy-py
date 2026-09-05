"""What the server-tool subscriber refuses, and what it must leave alone.

It used to remove the declaration and let the turn go on. On the client that sends these, that produced a fabrication rather than a degradation: a web search arrives as its own sub-request whose `tools` array holds nothing else, so stripping it leaves a request that succeeds by answering from memory — and the client labels the reply `Web search results for query:` regardless. The cases that matter most are therefore the ones where nothing is refused: a history being flattened, a client-executed tool, a leg this does not own.
"""

from typing import Any

import pytest

from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.counting import COUNTING_ONLY
from app.pipeline.subscribers.server_tools import adapt_server_tools
from app.pipeline.translation_driver.semantic import (
    Loss,
    LossCode,
    TranslationRefused,
    WebSearchNotExecutable,
)

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


async def test_a_web_search_declaration_is_refused_rather_than_removed() -> None:
    """Removing it would let the turn succeed by answering from memory, under a heading the client attaches unconditionally. Refusing is the only way to not search without claiming to have searched."""
    ctx = context({"tools": [CALCULATOR, WEB_SEARCH]})

    with pytest.raises(TranslationRefused) as caught:
        await adapt_server_tools(ctx)

    assert caught.value.code == "server_tool_not_executable"
    assert "web_search_20250305" in caught.value.field_path


async def test_the_refusal_names_the_declaration_that_caused_it() -> None:
    """A client told only "bad request" cannot tell which of its tools this endpoint will not run."""
    ctx = context({"tools": [WEB_SEARCH]})

    with pytest.raises(TranslationRefused) as caught:
        await adapt_server_tools(ctx)

    assert "web_search_20250305" in str(caught.value)


async def test_counting_measures_the_body_instead_of_refusing_it() -> None:
    """Counting reports how large a request is; it sends nothing and produces no reply, so there is nothing that could come back invented. Refusing here would turn a question that has an answer into an error and push the client onto its local estimate for nothing."""
    ctx = context({"tools": [CALCULATOR, WEB_SEARCH]})
    ctx.extras[COUNTING_ONLY] = True

    await adapt_server_tools(ctx)

    assert ctx.payload["tools"] == [CALCULATOR, WEB_SEARCH]


async def test_client_executed_typed_tools_are_left_alone() -> None:
    # Claude Code really sends these, and nothing has been measured rejecting them. Removing them would break working requests to prevent a failure nobody has seen.
    text_editor: dict[str, Any] = {"type": "text_editor_20250124", "name": "str_replace_editor"}
    memory: dict[str, Any] = {"type": "memory_20250818", "name": "memory"}
    ctx = context({"tools": [text_editor, memory]})

    await adapt_server_tools(ctx)

    assert ctx.payload["tools"] == [text_editor, memory]


async def test_web_fetch_is_refused_too_despite_upstream_wording_it_differently() -> None:
    """Upstream refuses this family in different words — `rejected tool(s): web_fetch` — which is why the predicate reads the declaration being sent rather than the wording that comes back.

    The **exact** exception matters here and `TranslationRefused` alone would not say it: `WebSearchNotExecutable` is a subclass, and it is the one `handle()` answers with a synthesised failed *search*. A fetch raising that told the client a search it never declared had run and failed.
    """
    ctx = context({"tools": [{"type": "web_fetch_20250910", "name": "web_fetch"}]})

    with pytest.raises(TranslationRefused) as refusal:
        await adapt_server_tools(ctx)
    assert not isinstance(refusal.value, WebSearchNotExecutable)


async def test_a_web_search_declaration_still_raises_the_subclass_that_gets_synthesised() -> None:
    """The positive side of the same split, and without it the family test has no discriminating power.

    Both branches raise a `TranslationRefused`, so a test that asserts only the base class passes whichever branch runs. Collapsing `searches_only` to a constant `False` would send a plain web search down the fetch path — 400 instead of the 200 carrying a failed tool that `hosted-web-search-spec.md` §8.3 requires — and every fetch-side assertion would stay green through it.

    The message is asserted too. Its `remembered text where the client expects a search` half is a claim about what the client does with a stripped search declaration, and it is only true of searches; the fetch branch deliberately drops it.
    """
    ctx = context({"tools": [{"type": "web_search_20250305", "name": "web_search"}]})

    with pytest.raises(WebSearchNotExecutable) as refusal:
        await adapt_server_tools(ctx)
    assert "remembered text where the client expects a search" in str(refusal.value)


async def test_the_bare_openai_spelling_is_refused_too() -> None:
    """A `/responses` request naming a Claude model falls back to this endpoint with `tools` carried across verbatim, so the bare spelling really does arrive here."""
    ctx = context({"tools": [{"type": "web_search", "name": "web_search"}]})

    with pytest.raises(TranslationRefused):
        await adapt_server_tools(ctx)


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


SEARCH_CALL: dict[str, Any] = {
    "type": "server_tool_use",
    "id": "srvtoolu_1",
    "name": "web_search",
    "input": {"query": "today's date"},
}
SEARCH_RESULT: dict[str, Any] = {
    "type": "web_search_tool_result",
    "tool_use_id": "srvtoolu_1",
    "content": [
        {
            "type": "web_search_result",
            "title": "Example",
            "url": "https://example.com",
            "encrypted_content": "AAAA" * 200,
        }
    ],
}


async def test_a_search_turn_left_in_the_history_becomes_text() -> None:
    ctx = context(
        {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "when?"}]},
                {"role": "assistant", "content": [SEARCH_CALL, SEARCH_RESULT]},
            ]
        }
    )

    await adapt_server_tools(ctx)

    blocks = ctx.payload["messages"][1]["content"]
    assert [block["type"] for block in blocks] == ["text", "text"]
    assert blocks[0]["text"] == "[web_search] today's date"
    assert blocks[1]["text"] == "[web_search results]\n- Example — https://example.com"


async def test_the_opaque_bulk_of_a_result_is_not_carried_into_the_text() -> None:
    # `encrypted_content` is most of a result's bytes and means nothing to anyone but upstream. Upstream also rejects it unless it is genuine, so there is no repairing it either — only leaving it out and recording that loss.
    ctx = context({"messages": [{"role": "assistant", "content": [SEARCH_RESULT]}]})

    await adapt_server_tools(ctx)

    assert "AAAA" not in ctx.payload["messages"][0]["content"][0]["text"]
    assert ctx.extras["conversion_losses"] == [
        Loss(
            LossCode.SERVER_TOOL_NOT_CARRIED,
            "web_search_tool_result flattened to text; opaque encrypted_content not carried",
        )
    ]


async def test_a_failed_search_turn_says_so_rather_than_pretending_it_returned_nothing() -> None:
    failed: dict[str, Any] = {
        "type": "web_search_tool_result",
        "tool_use_id": "srvtoolu_1",
        "content": {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"},
    }
    ctx = context({"messages": [{"role": "assistant", "content": [failed]}]})

    await adapt_server_tools(ctx)

    assert ctx.payload["messages"][0]["content"][0]["text"] == "[web_search failed: max_uses_exceeded]"


async def test_the_history_is_flattened_even_when_this_request_declares_nothing() -> None:
    # A client that has since switched web search off still replays the turns from when it was on, and those are rejected on their own account.
    ctx = context({"messages": [{"role": "assistant", "content": [SEARCH_CALL, SEARCH_RESULT]}]})

    await adapt_server_tools(ctx)

    assert all(block["type"] == "text" for block in ctx.payload["messages"][0]["content"])


async def test_a_client_side_tool_result_is_not_mistaken_for_a_server_one() -> None:
    # Plain `tool_result` belongs to a tool that was never removed. Matching on the `_tool_result` suffix alone would have swallowed it.
    client_result: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": "toolu_1",
        "content": "42",
    }
    ctx = context({"messages": [{"role": "user", "content": [client_result]}]})

    await adapt_server_tools(ctx)

    assert ctx.payload["messages"][0]["content"] == [client_result]


async def test_a_server_tool_family_we_do_not_strip_keeps_its_blocks() -> None:
    # The declaration for these survives, so the blocks referring to it still have something to refer to.
    code_call: dict[str, Any] = {
        "type": "server_tool_use",
        "id": "srvtoolu_2",
        "name": "code_execution",
        "input": {"code": "1+1"},
    }
    ctx = context({"messages": [{"role": "assistant", "content": [code_call]}]})

    await adapt_server_tools(ctx)

    assert ctx.payload["messages"][0]["content"] == [code_call]


async def test_a_history_with_nothing_to_flatten_is_left_exactly_as_it_was() -> None:
    payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
    }
    ctx = context(payload)

    await adapt_server_tools(ctx)

    assert ctx.payload == {
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
    }


async def test_a_successful_fetch_is_not_reported_as_a_failure() -> None:
    """A single object is not evidence of failure — `web_fetch` returns one when it works.

    Reading the payload's shape instead of its `type` turned a fetch that worked into `[web_fetch failed]` and threw away the URL on the way.
    """
    fetched: dict[str, Any] = {
        "type": "web_fetch_tool_result",
        "tool_use_id": "srvtoolu_9",
        "content": {
            "type": "web_fetch_result",
            "url": "https://example.com/page",
            "retrieved_at": "2026-08-20T00:00:00Z",
        },
    }
    ctx = context({"messages": [{"role": "assistant", "content": [fetched]}]})

    await adapt_server_tools(ctx)

    text = ctx.payload["messages"][0]["content"][0]["text"]
    assert text == "[web_fetch results]\n- https://example.com/page"


async def test_a_fetch_call_names_the_page_it_asked_for() -> None:
    # `web_fetch` puts its argument under `url`, not `query`. A renderer that knew only `query` made every fetch a bare `[web_fetch]`.
    call: dict[str, Any] = {
        "type": "server_tool_use",
        "id": "srvtoolu_9",
        "name": "web_fetch",
        "input": {"url": "https://example.com/page"},
    }
    ctx = context({"messages": [{"role": "assistant", "content": [call]}]})

    await adapt_server_tools(ctx)

    assert ctx.payload["messages"][0]["content"][0]["text"] == "[web_fetch] https://example.com/page"


async def test_a_result_with_a_title_and_no_url_still_gets_a_line() -> None:
    # Dropping it would let a turn that read three pages report two.
    titled: dict[str, Any] = {
        "type": "web_search_tool_result",
        "tool_use_id": "srvtoolu_1",
        "content": [{"type": "web_search_result", "title": "Untitled source"}],
    }
    ctx = context({"messages": [{"role": "assistant", "content": [titled]}]})

    await adapt_server_tools(ctx)

    assert ctx.payload["messages"][0]["content"][0]["text"] == "[web_search results]\n- Untitled source"


async def test_a_cache_breakpoint_survives_the_flattening() -> None:
    # `cache_control` marks a position in the prompt, not a kind of block. Dropping it moves where the cached prefix ends without saying so.
    marked: dict[str, Any] = {**SEARCH_RESULT, "cache_control": {"type": "ephemeral"}}
    ctx = context({"messages": [{"role": "assistant", "content": [marked]}]})

    await adapt_server_tools(ctx)

    assert ctx.payload["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}


async def test_a_query_does_not_bring_its_trailing_whitespace_along() -> None:
    # It would land at the end of an assistant turn, which upstream rejects on its own terms.
    call: dict[str, Any] = {**SEARCH_CALL, "input": {"query": "today's date\n\n"}}
    ctx = context({"messages": [{"role": "assistant", "content": [call]}]})

    await adapt_server_tools(ctx)

    assert ctx.payload["messages"][0]["content"][0]["text"] == "[web_search] today's date"
