"""What the real client does with a search this proxy cannot run.

Every other test of this behaviour asserts on what the proxy produced. None of them can answer the question that decided the design: whether the client accepts a synthesised `web_search_tool_result_error` and carries on, or chokes on it. That question needs the real binary, and this is the only group that has one.

The setup is the two-stage shape the client actually uses. A test cannot make Claude Code issue a web search; only a reply that calls `WebSearch` can. So the script answers the first request with that tool call, and everything after it is the client's own doing — including the separate sub-request it raises, which is the one the proxy intercepts.
"""

from pathlib import Path
from typing import Any, cast

from _harness import run_claude, running_proxy
from _upstream import (
    BASE_URL,
    ScriptedUpstream,
    anthropic_text,
    anthropic_tool_call,
    responses_hosted_search,
    responses_text,
    responses_tool_call,
)

SEARCH_TOOLS = ["--allowedTools", "WebSearch"]


def test_a_hosted_search_native_pair_reaches_the_real_client_and_conversation_continues(
    config_dir: Path,
) -> None:
    """The positive D6 path through the real binary and all three model turns."""
    query = "bun 1.3 release notes"
    search_answer = "hosted-search-answer-Q7v2"
    final = "after-hosted-search-R8k3"
    upstream = ScriptedUpstream(
        replies=[
            responses_tool_call("WebSearch", {"query": query}),
            responses_hosted_search(query, search_answer),
            responses_text(final),
        ]
    )
    overrides = {
        "model_translation": {"to_openai_responses": {"hosted_web_search": True}},
        "model_providers": {
            "ghc": {
                "type": "github_copilot",
                "api_base_url": BASE_URL,
                "models_support_web_search": ["gpt-model"],
            }
        },
    }

    with running_proxy(upstream, overrides=overrides) as proxy:
        result = run_claude(
            "search for bun 1.3",
            proxy=proxy,
            config_dir=config_dir,
            model="gpt-model",
            extra_args=SEARCH_TOOLS,
        )

    assert result.returncode == 0, result.stderr
    assert final in result.stdout, result.stdout
    assert [exchange.path for exchange in upstream.seen] == [
        "/responses",
        "/responses",
        "/responses",
    ]
    assert upstream.seen[1].tool_types == ["web_search"]
    third_input = upstream.seen[2].body.get("input")
    assert isinstance(third_input, list), third_input
    matching_outputs: list[Any] = [
        cast(dict[str, Any], item).get("output")
        for item in cast(list[Any], third_input)
        if isinstance(item, dict)
        and cast(dict[str, Any], item).get("type") == "function_call_output"
        and cast(dict[str, Any], item).get("call_id") == "call_scripted"
    ]
    assert len(matching_outputs) == 1, third_input
    rendered = str(matching_outputs[0])
    assert "Web search error: unavailable" in rendered, rendered
    assert search_answer in rendered, rendered


def test_a_search_the_proxy_cannot_run_never_reaches_upstream(config_dir: Path) -> None:
    """The failure this whole design exists to prevent, checked at the only place it is visible.

    Upstream is scripted with exactly two replies and sees exactly two requests, while the proxy handles three: the middle one is the search sub-request, answered by the proxy and never forwarded. If it *had* been forwarded with its tool stripped, upstream would have been asked a third time — and would have answered from memory, under a heading the client attaches whether a search happened or not.

    Asserted on the count rather than on the absence of a `web_search_` type, because a stripped declaration and an intercepted request look identical from upstream's side except for this.
    """
    upstream = ScriptedUpstream(
        replies=[
            anthropic_tool_call("WebSearch", {"query": "bun 1.3 release notes"}),
            anthropic_text("answered without the search"),
        ]
    )

    with running_proxy(upstream) as proxy:
        result = run_claude(
            "search for bun 1.3",
            proxy=proxy,
            config_dir=config_dir,
            extra_args=SEARCH_TOOLS,
        )

    assert result.returncode == 0, result.stderr
    assert len(upstream.seen) == 2, [exchange.path for exchange in upstream.seen]
    # And upstream was never offered a server tool under any spelling, on either request.
    for exchange in upstream.seen:
        assert not [kind for kind in exchange.tool_types if kind.startswith(("web_search", "web_fetch"))]


def test_the_conversation_survives_the_failed_search(config_dir: Path) -> None:
    """The other half: refusing is only better than fabricating if the turn still finishes.

    A synthesised reply the client could not parse would show up here as a non-zero exit or a run that never reaches the scripted final answer — both of which the proxy's own tests would call a success.
    """
    final = "e2e-after-search-Zx91"
    upstream = ScriptedUpstream(
        replies=[
            anthropic_tool_call("WebSearch", {"query": "anything"}),
            anthropic_text(final),
        ]
    )

    with running_proxy(upstream) as proxy:
        result = run_claude(
            "search for anything",
            proxy=proxy,
            config_dir=config_dir,
            extra_args=SEARCH_TOOLS,
        )

    assert result.returncode == 0, result.stderr
    assert final in result.stdout, result.stdout


def test_the_model_is_told_the_search_failed_rather_than_shown_invented_findings(
    config_dir: Path,
) -> None:
    """The fact the entire choice turns on, read off what the client sent back on the next turn.

    The client renders the synthesised error itself, into the same block it would have put results in: `Web search results for query: "..."` followed by `Web search error: unavailable`. So the model is told, in the client's own words, that the search did not produce anything — under the heading that would otherwise have introduced findings.

    That heading is why removing the declaration was unacceptable. It is attached whether or not a search happened, so a model answering from memory has its recollection presented beneath it as though searched. Here the same heading is followed by an error, and nothing is passed off as a finding.

    Asserted on the rendered text rather than on `is_error`, which the client does not set for this:
    a search that fails is a result it knows how to describe, not a tool that broke.
    """
    upstream = ScriptedUpstream(
        replies=[
            anthropic_tool_call("WebSearch", {"query": "bun 1.3"}),
            anthropic_text("done"),
        ]
    )

    with running_proxy(upstream) as proxy:
        run_claude(
            "search for bun 1.3", proxy=proxy, config_dir=config_dir, extra_args=SEARCH_TOOLS
        )

    assert len(upstream.seen) == 2
    returned = str(upstream.seen[1].body.get("messages", ""))
    assert "Web search error: unavailable" in returned, returned[:600]
