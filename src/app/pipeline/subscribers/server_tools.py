"""Server-tool declarations upstream refuses, removed before the request is sent.

Copilot's Anthropic Messages endpoint does not execute Anthropic's native server tools. A request carrying one is rejected whole — `The use of the web search tool is not supported.` with `unsupported_value` — so one declaration the client added on its own costs the entire turn, and the client's next turn replays the same declaration and is rejected again.

The first-party client reached the same conclusion and acts on it the same way: VS Code's Copilot Chat filters `tool.type.startsWith('web_search')` out of the tools array before forwarding (`oaiLanguageModelServer.ts`), and tells its Claude Code integration `disallowedTools: ['WebSearch']` under a comment reading `CAPI does not yet support the WebSearch tool`.

Removing a declaration removes a capability, which is why this is loud rather than silent: the model is no longer offered a tool the client believes it has. That is a real loss, and it is still the better of the two outcomes on offer, because the alternative is not "web search works" but "nothing works".

**Scoped to the Anthropic leg on purpose.** What decides this is the endpoint, not the client: no Claude model in the catalog advertises `/responses` at all, and the `/responses` endpoint does execute hosted web search natively, measured on gpt-5.5. Whether *this* spelling — an Anthropic `web_search_YYYYMMDD` declaration carried onto a Responses request by translation — is accepted there has not been measured; upstream was only ever asked with the Responses spelling `{"type": "web_search"}`. So the Responses leg is left alone because nothing has been measured rejecting it, not because it is known to work. Mapping the Anthropic declaration onto the Responses builtin is a separate product capability: it has to be decided before translation rather than here, and it cannot ship without the response side, because a reply carrying `web_search_call` items has nowhere to go in the Anthropic protocol today.
"""

import logging
from typing import Any, cast

from app.pipeline.request import RequestContext, WireFormat

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:server-tool-capability"

# Only what upstream has actually been measured rejecting on this leg.
#
# `web_search`: today's 400, and the reason this module exists.
# `web_fetch`: rejected too, and it says so in different words — `{"message": "rejected tool(s): web_fetch", "code": "invalid_request_body"}`. Two shapes for one rule is exactly why the predicate here reads the declaration we send rather than the wording that comes back; a matcher written against one message would have let the other through.
#
# No trailing underscore, so both spellings are caught: Anthropic dates its server tools (`web_search_20250305`) while the OpenAI form is bare (`web_search`), and the bare form really does arrive here — a `/responses` request naming a Claude model falls back to the Anthropic endpoint and the translator carries `tools` across verbatim.
#
# Deliberately absent: `memory_`, `tool_search_`, `text_editor_`, `bash_`, `computer_`. Those are executed by the client, not by the model's host, and Claude Code really does send some of them. Nothing has been measured rejecting them, so removing them would break working requests to prevent a failure nobody has seen. The reference implementation strips all ten known prefixes and is wrong to.
_REJECTED_TYPE_PREFIXES: tuple[str, ...] = ("web_search", "web_fetch")


def _rejected_type(tool: Any) -> str | None:
    """The declared type when upstream is known to reject it, else `None`.

    A `type` that is absent, null, or not a string belongs to an ordinary client tool and is left alone. So is `custom`. Only a string naming one of the measured-rejected families counts, so a server tool this endpoint has never been asked about travels unchanged and gets named by upstream rather than removed on a guess.
    """
    if not isinstance(tool, dict):
        return None
    declared = cast(dict[str, Any], tool).get("type")
    if not isinstance(declared, str):
        return None
    if declared.startswith(_REJECTED_TYPE_PREFIXES):
        return declared
    return None


def _drop_dangling_choice(payload: dict[str, Any]) -> None:
    """Remove a `tool_choice` that now points at nothing.

    Two ways it can dangle. It names a tool that is no longer declared, or it demands *some* tool of a request that no longer declares any. Both are rejected upstream on their own, so leaving one behind would trade the rejection this module exists to prevent for another one — and `Tool 'web_search' not found in provided tools` is exactly the wording that would come back.

    Decided against what survives rather than against what was removed. A declaration carrying no `name` cannot be recorded on the way out, and a choice pointing at it would then have looked like a choice pointing at something still present.

    `auto` with tools still present is left exactly as it was: it neither names a missing tool nor demands one, and rewriting it would change what the client asked for to no purpose. A malformed choice — `type` of `tool` with no name — is also left alone, because this module removes what upstream is known to reject rather than tidying what the client got wrong.
    """
    choice = payload.get("tool_choice")
    if choice is None:
        return
    remaining = payload.get("tools")
    if not remaining:
        # Nothing left to choose from. `auto` and `none` are as unroutable as `any` once the array is gone, because the field is only accepted alongside a non-empty `tools`.
        del payload["tool_choice"]
        return
    if not isinstance(choice, dict) or not isinstance(remaining, list):
        return
    entry = cast(dict[str, Any], choice)
    if entry.get("type") != "tool":
        return
    named = entry.get("name")
    if not isinstance(named, str):
        return
    declared: set[Any] = {
        cast(dict[str, Any], tool).get("name")
        for tool in cast(list[Any], remaining)
        if isinstance(tool, dict)
    }
    if named not in declared:
        del payload["tool_choice"]


async def adapt_server_tools(context: RequestContext) -> None:
    """Drop server-tool declarations the routed endpoint will reject.

    Reads the route rather than the inbound format, because what upstream accepts is a property of the endpoint being spoken to. A request that arrived in another protocol and was translated *into* Anthropic shape belongs here too, and gets the same treatment for the same reason; one that was translated *out* of it does not, and its `tools` is a different protocol's field that happens to share the name.
    """
    if context.target_format is not WireFormat.ANTHROPIC_MESSAGES:
        return
    payload = context.payload
    tools_value = payload.get("tools")
    if not isinstance(tools_value, list):
        return
    tools = cast(list[Any], tools_value)

    kept: list[Any] = []
    dropped: list[str] = []
    dropped_names: set[str] = set()
    for tool in tools:
        declared = _rejected_type(tool)
        if declared is None:
            kept.append(tool)
            continue
        name = cast(dict[str, Any], tool).get("name")
        dropped.append(declared)
        if isinstance(name, str):
            dropped_names.add(name)

    if not dropped:
        return

    if kept:
        payload["tools"] = kept
    else:
        # Not `[]`. An empty array is a different thing to say than saying nothing, and upstream has not been asked whether it accepts one; absent is the spelling every request without tools already uses.
        del payload["tools"]

    _drop_dangling_choice(payload)

    # INFO rather than WARNING. Once a client has web search switched on this fires on every request it sends, and `observability/logging.py` reserves WARNING for what is not routine — a line that repeats hundreds of times a session is not a warning, it is a setting. Not DEBUG either: unlike the blank-text repair next door this removes a capability the client asked for, and an operator wondering why web search never runs should not have to turn on debug logging to find out.
    logger.info(
        "dropped %d server-tool declaration(s) this endpoint rejects: %s — the model will not be offered %s",
        len(dropped),
        ", ".join(sorted(dropped)),
        ", ".join(sorted(dropped_names)) if dropped_names else "them",
    )
