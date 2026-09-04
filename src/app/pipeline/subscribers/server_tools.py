"""Server-tool declarations this endpoint cannot execute, refused before the request is sent.

Copilot's Anthropic Messages endpoint does not run Anthropic's native server tools. A request carrying one is rejected whole — `The use of the web search tool is not supported.` with `unsupported_value` — so the question was never whether the client gets its search. It was what the client is told instead.

**This used to remove the declaration and let the turn continue, and that was the wrong answer.** It reads as the gentler one: the conversation survives, one capability short. What it actually produces on the client that sends these is a fabrication. Claude Code runs a web search as its own sub-request, carrying `Perform a web search for the query: X` and a `tools` array holding nothing but the search — measured over 190 real ones, every single time. Strip its only tool and the request does not fail; the model answers from memory, and the client renders the reply under a `Web search results for query:` heading it attaches unconditionally. No `is_error`, no marker. Remembered text comes back labelled as searched fact, and nothing downstream can tell the difference.

So this raises instead, and `handle()` answers it: the reply becomes a `server_tool_use` paired with a `web_search_tool_result` carrying a single error object — the shape Anthropic defines for a search that did not run. Not an HTTP error, though that was the first form of this fix: the transcript showing the model degrade well on a 400 also shows three attempts before it did. **Those three are the main-conversation model calling `WebSearch` again, not the transport retrying** — corrected 2026-08-30 against the client's own retry table, which does not retry a 400 at all. What the failed tool buys is narrower than it used to say here: the client has no *mechanism* that repeats a failed tool result, where an error string in a `tool_result` demonstrably drew three repeat calls from the model. Whether the model repeats a failed tool result too has not been measured.

**The history is rewritten rather than refused, and on this client that path has never once run.** Flattening a past `server_tool_use` call and its `*_tool_result` answer into text is honest where refusing the declaration is not: those blocks are a record of searches that really happened, not a claim that one is happening now. They become plain text rather than a client `tool_use` / `tool_result` pair, because a downgraded pair refers to a tool this request does not declare, while text refers to nothing.

What the earlier version of this docstring got wrong was implying such a transcript is what arrives. Measured 2026-08-20 across five history databases: on Claude Code these blocks **never enter the main conversation**. Its main `messages` carry an ordinary `tool_use` named `WebSearch` — a plain function tool with no `type` at all, which `_rejected_type` ignores and this module therefore never touches. The server-tool declaration lives only in the throwaway sub-request, and that sub-request carries no history. So the flattening below is for transcripts from somewhere else: another provider, a direct Anthropic session, a client that does not split the two. That is a real shape and worth handling; it is not one this project has seen.

**Nothing here has a production sighting at all.** This project's own `history.db` holds 8,966 requests and not one of them reached this module — every measurement above comes from the existing Bun service's records and from client transcripts. The behaviour is derived from what the client demonstrably sends and from what upstream demonstrably answers, not from having watched this code run.

**Scoped to the Anthropic leg, and the Responses leg has its own answer.** That endpoint does execute hosted web search, under its own spelling — measured 2026-08-20 on gpt-5.5, `{"type": "web_search"}` returns 200 while the Anthropic `web_search_20250305` spelling returns 400. So that leg translates the declaration and renders what comes back (`translation_driver/openai_responses.py`, `delivery/assembler.py`), and refuses when the feature is switched off — which it is by default — or when the model is not known to search at all (`subscribers/hosted_web_search.py`).

The one thing the two legs share is the wording of a flattened history: both use `pipeline/server_tool_text.py`. A conversation is not pinned to one leg — the same history moves between them when a client switches model — and two renderings would leave one session carrying two shapes of the same fact, with nothing to report it.
"""

import logging
from typing import Any, cast

from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.server_tool_text import WEB_SEARCH, render_server_tool_block
from app.pipeline.subscribers.counting import COUNTING_ONLY
from app.pipeline.translation_driver.semantic import (
    Loss,
    LossCode,
    TranslationRefused,
    WebSearchNotExecutable,
)

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:server-tool-capability"
_REQUEST_LOSSES = "conversion_losses"


def _record_loss(context: RequestContext, detail: str) -> None:
    recorded = context.extras.get(_REQUEST_LOSSES)
    if not isinstance(recorded, list):
        recorded = []
        context.extras[_REQUEST_LOSSES] = recorded
    cast(list[Any], recorded).append(Loss(LossCode.SERVER_TOOL_NOT_CARRIED, detail))

# Only what upstream has actually been measured rejecting on this leg.
#
# `web_search`: today's 400, and the reason this module exists.
# `web_fetch`: rejected too, and it says so in different words — `{"message": "rejected tool(s): web_fetch", "code": "invalid_request_body"}`. Two shapes for one rule is exactly why the predicate here reads the declaration we send rather than the wording that comes back; a matcher written against one message would have let the other through.
#
# No trailing underscore, so both spellings are caught: Anthropic dates its server tools (`web_search_20250305`) while the OpenAI form is bare (`web_search`). The bare form has a route to this leg — a `/responses` request naming a Claude model finds no `/responses` on that model, routes to Messages instead, and `to_anthropic_messages` assigns `tools` across verbatim — but that is read off the code, not off a request anyone has seen. Every measured arrival here carries the dated spelling.
#
# Deliberately absent: `memory_`, `tool_search_`, `text_editor_`, `bash_`, `computer_`. Those are executed by the client, not by the model's host, and Claude Code really does send some of them. Nothing has been measured rejecting them, so refusing them would break working requests to prevent a failure nobody has seen. The reference implementation strips all ten known prefixes and is wrong to.
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


def _family(name: str) -> str | None:
    """The rejected server-tool family a type or tool name belongs to, else `None`."""
    for prefix in _REJECTED_TYPE_PREFIXES:
        if name.startswith(prefix):
            return prefix
    return None


def _flatten_history(payload: dict[str, Any]) -> tuple[int, tuple[str, ...]]:
    """Replace server-tool history blocks and return each structured loss."""
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return 0, ()
    flattened = 0
    losses: list[str] = []
    for message in cast(list[Any], messages):
        if not isinstance(message, dict):
            continue
        entry = cast(dict[str, Any], message)
        content = entry.get("content")
        if not isinstance(content, list):
            continue
        rebuilt: list[Any] = []
        touched = False
        for block in cast(list[Any], content):
            rendering = render_server_tool_block(
                block,
                families=_REJECTED_TYPE_PREFIXES,
            )
            if rendering is None:
                rebuilt.append(block)
                continue
            rebuilt.append(rendering.as_text_block())
            touched = True
            flattened += 1
            detail = f"{rendering.source_type} flattened to text"
            if rendering.dropped_opaque:
                detail += "; opaque encrypted_content not carried"
            losses.append(detail)
        if touched:
            entry["content"] = rebuilt
    return flattened, tuple(losses)


def _refuse_declarations(payload: dict[str, Any]) -> None:
    """Remove the declarations, and any `tool_choice` left pointing at one."""
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

    # **Which exception decides which reply**, so the two families are separated here rather than at the handler.
    #
    # `WebSearchNotExecutable` is what `handle()` answers with a synthesised `server_tool_use` / `web_search_tool_result` pair. That pair says *a web search* failed, and it is the only thing this proxy knows how to synthesise — so raising it for a `web_fetch` declaration told the client a search it never asked for had failed. Measured 2026-08-30: a `web_fetch_20250910` declaration came back as HTTP 200 whose first block was `server_tool_use name="web_search"`, with the fetch prompt as its query.
    #
    # `web_fetch` gets the plain refusal, which the error contract turns into a 400 in the client's own dialect — `hosted-web-search-spec.md` §13, "声明继续 REJECT". Three independent reasons, none of them "web_fetch matters less" (`.dev/docs/hosted-web-search/reports/260830-claude-code-web-fetch-client-behaviour.md`): Claude Code never declares it as a server tool at all, so the synthesis is unreachable on the only client in use; the argument that makes synthesis right for web search does not transfer, because it rests on that client's search sub-request carrying one tool and its unconditional `Web search results for query:` heading, and a fetch has neither; and `web_fetch_tool_result` has no consumer in that client — it falls through the renderer's `default` and shows a blank turn.
    #
    # A mixed declaration takes the plain refusal too. The synthesis can only speak for the search half, so answering one would report the fetch as never mentioned. Ruled here rather than in the Spec's own words: §13 does not cover the combination, and this is the reading that states no falsehood. Registered in the Spec at §8.3 as this project's derivation.
    families = {_family(declared) for declared in dropped}
    searches_only = families == {WEB_SEARCH}

    # Named for the operator before the refusal, which is the client's to see.
    logger.info(
        "answering %d server-tool declaration(s) this endpoint cannot execute as failed: %s",
        len(dropped),
        ", ".join(sorted(dropped)),
    )
    refusal = WebSearchNotExecutable if searches_only else TranslationRefused
    # The `remembered text` half is a claim about web search specifically — the client's heading presents whatever comes back as the search's findings — so it is only said when that is what was refused. A fetch carries no such heading, and asserting it would be inventing a consequence.
    because = (
        ", and answering without it would return remembered text where the client expects a search"
        if searches_only
        else ""
    )
    raise refusal(
        f"this endpoint does not execute {', '.join(sorted(dropped))}{because}",
        code="server_tool_not_executable",
        field_path=f"tools.{sorted(dropped)[0]}",
    )


async def adapt_server_tools(context: RequestContext) -> None:
    """Refuse a declaration this endpoint cannot execute, and flatten what earlier ones left in the history.

    Reads the route rather than the inbound format, because what upstream accepts is a property of the endpoint being spoken to. A request that arrived in another protocol and was translated *into* Anthropic shape belongs here too, and gets the same treatment for the same reason; one that was translated *out* of it does not, and its `tools` is a different protocol's field that happens to share the name.

    Two passes, and only the second can be reached with a declaration present: refusing raises, so a request that declares a search this endpoint cannot run never gets its history rewritten. Nothing is lost by that — the request is not being sent. The flattening therefore runs for the requests that declare nothing and still carry blocks from a turn that did, and on the counting leg, where refusing is suspended and the measured body should be the one that would actually go out.
    """
    if context.target_format is not WireFormat.ANTHROPIC_MESSAGES:
        return
    payload = context.payload

    if not context.extras.get(COUNTING_ONLY):
        # Measuring is exempt: nothing is executed, so nothing can come back invented. The history is still flattened below, because that is what makes the measured body the one that would actually be sent.
        _refuse_declarations(payload)
    flattened, losses = _flatten_history(payload)
    if flattened:
        # INFO for the same reason as the declaration line below: routine for a session that used web search, but it rewrites what the model is shown, which is not something to bury in debug.
        logger.info(
            "flattened %d server-tool block(s) left in the history into text; upstream would have rejected them",
            flattened,
        )
    for detail in losses:
        _record_loss(context, detail)
