"""Server-tool declarations this endpoint cannot execute, refused before the request is sent.

Copilot's Anthropic Messages endpoint does not run Anthropic's native server tools. A request carrying one is rejected whole — `The use of the web search tool is not supported.` with `unsupported_value` — so the question was never whether the client gets its search. It was what the client is told instead.

**This used to remove the declaration and let the turn continue, and that was the wrong answer.** It reads as the gentler one: the conversation survives, one capability short. What it actually produces on the client that sends these is a fabrication. Claude Code runs a web search as its own sub-request, carrying `Perform a web search for the query: X` and a `tools` array holding nothing but the search — measured over 190 real ones, every single time. Strip its only tool and the request does not fail; the model answers from memory, and the client renders the reply under a `Web search results for query:` heading it attaches unconditionally. No `is_error`, no marker. Remembered text comes back labelled as searched fact, and nothing downstream can tell the difference.

Refusing produces the opposite, and it is on record rather than reasoned: when a search sub-request returned 400, the client handed the main conversation a `tool_result` with `is_error: true`, and the model said it would not mistake an interface failure for the fact not existing — then reached for WebFetch and finished the task. A refused search costs a turn. A silently invented one costs the answer's truth.

**The history is still rewritten rather than refused.** A transcript carrying `server_tool_use` calls and `*_tool_result` answers from an earlier session is rejected on its own account, and there is nothing dishonest about flattening those into text: they are a record of searches that really happened, not a claim that one is happening now. They become plain text rather than a client `tool_use` / `tool_result` pair, because a downgraded pair refers to a tool this request does not declare, while text refers to nothing.

**Scoped to the Anthropic leg, and the Responses leg has its own answer.** That endpoint does execute hosted web search, under its own spelling — measured 2026-08-20 on gpt-5.5, `{"type": "web_search"}` returns 200 while the Anthropic `web_search_20250305` spelling returns 400. So that leg translates the declaration and renders what comes back (`translation_driver/openai_responses.py`, `delivery/assembler.py`), and refuses only when the model is not known to search at all (`subscribers/hosted_web_search.py`).

The one thing the two legs share is the wording of a flattened history: both use `pipeline/server_tool_text.py`. A conversation is not pinned to one leg — the same history moves between them when a client switches model — and two renderings would leave one session carrying two shapes of the same fact, with nothing to report it.
"""

import logging
from typing import Any, cast

from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.server_tool_text import call_subject
from app.pipeline.subscribers.counting import COUNTING_ONLY
from app.pipeline.translation_driver.semantic import TranslationRefused

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


def _family(name: str) -> str | None:
    """The rejected server-tool family a type or tool name belongs to, else `None`."""
    for prefix in _REJECTED_TYPE_PREFIXES:
        if name.startswith(prefix):
            return prefix
    return None


def _describe_one(item: Any) -> str | None:
    """One line for one result, or `None` when it says nothing worth a line.

    `encrypted_content` is deliberately not among the fields read. It is the bulk of a search result's bytes and is opaque to everyone but upstream, so carrying it would multiply the history's size to say nothing.
    """
    if not isinstance(item, dict):
        return None
    result = cast(dict[str, Any], item)
    title = result.get("title")
    url = result.get("url")
    has_title = isinstance(title, str) and title.strip()
    has_url = isinstance(url, str) and url.strip()
    if has_title and has_url:
        return f"- {title} — {url}"
    if has_url:
        return f"- {url}"
    if has_title:
        # A result with a title and no URL still names what was read. Dropping it would let a turn that fetched three pages report two.
        return f"- {title}"
    return None


def _failure_of(content: Any) -> str | None:
    """The error code when this result payload is a failure, else `None`.

    Read off `type` and `error_code` rather than off the payload's *shape*. A single object is not evidence of failure: a successful `web_fetch_tool_result` carries one object too, and treating shape as the discriminator reported a fetch that worked as one that failed — and threw away its URL and text on the way.
    """
    if not isinstance(content, dict):
        return None
    entry = cast(dict[str, Any], content)
    kind = entry.get("type")
    code = entry.get("error_code")
    failed = (isinstance(kind, str) and kind.endswith("_error")) or code is not None
    if not failed:
        return None
    return code if isinstance(code, str) else ""


def _render_results(content: Any, family: str) -> str:
    """Turn a server-tool result's payload into something a model can still read.

    Three payload shapes reach here: a list of results (`web_search`), a single result object (`web_fetch`), and an error object (either family).
    """
    failure = _failure_of(content)
    if failure is not None:
        return f"[{family} failed: {failure}]" if failure else f"[{family} failed]"
    items: list[Any] = (
        cast(list[Any], content) if isinstance(content, list) else [content] if content else []
    )
    lines = [line for line in (_describe_one(item) for item in items) if line is not None]
    if not lines:
        return f"[{family} results omitted]"
    return "\n".join([f"[{family} results]", *lines])


def _as_text(entry: dict[str, Any], text: str) -> dict[str, Any]:
    """The replacement block, carrying over what the original said about caching.

    `cache_control` is a property of the position in the prompt, not of the block's kind, so a breakpoint the client placed here still marks the same boundary once the block is text. Dropping it would silently move where the prefix ends.
    """
    replacement: dict[str, Any] = {"type": "text", "text": text}
    cache_control = entry.get("cache_control")
    if cache_control is not None:
        replacement["cache_control"] = cache_control
    return replacement


def _flatten_history_block(block: Any) -> dict[str, Any] | None:
    """The text a rejected server-tool block becomes, or `None` to leave the block alone.

    Flattened to text rather than downgraded to a client `tool_use` / `tool_result` pair, which is what the reference implementation does. That downgrade only works while the tool stays declared; here the declaration has just been removed, so a surviving reference would be rejected in its own right — the reference project matches `Tool 'X' not found in provided tools` for that case, which this project has not measured for itself. Text refers to nothing and so cannot dangle either way.

    Repairing these in place is not on the table either: upstream requires a real, non-empty `encrypted_content` on every search result and rejects both an empty string and any placeholder, measured by the reference project. Whatever a client replays, we cannot make it sendable.
    """
    if not isinstance(block, dict):
        return None
    entry = cast(dict[str, Any], block)
    block_type = entry.get("type")
    if not isinstance(block_type, str):
        return None

    if block_type == "server_tool_use":
        name = entry.get("name")
        if not isinstance(name, str):
            return None
        family = _family(name)
        if family is None:
            return None
        return _as_text(entry, f"[{family}]{call_subject(entry.get('input'))}")

    # `tool_result` on its own is the client-side one and belongs to a tool we never touched.
    if block_type == "tool_result" or not block_type.endswith("_tool_result"):
        return None
    family = _family(block_type)
    if family is None:
        return None
    return _as_text(entry, _render_results(entry.get("content"), family))


def _flatten_history(payload: dict[str, Any]) -> int:
    """Replace rejected server-tool blocks left in the history, returning how many.

    Runs whether or not this request declared anything. A history block is rejected on its own account, so a client that has since stopped asking for web search still replays turns from when it did.
    """
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return 0
    flattened = 0
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
            replacement = _flatten_history_block(block)
            if replacement is None:
                rebuilt.append(block)
                continue
            rebuilt.append(replacement)
            touched = True
            flattened += 1
        if touched:
            entry["content"] = rebuilt
    return flattened


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

    # Named for the operator before the refusal, which is the client's to see.
    logger.info(
        "refusing %d server-tool declaration(s) this endpoint cannot execute: %s",
        len(dropped),
        ", ".join(sorted(dropped)),
    )
    raise TranslationRefused(
        f"this endpoint does not execute {', '.join(sorted(dropped))}, and answering without it"
        " would return remembered text where the client expects a search",
        code="server_tool_not_executable",
        field_path=f"tools.{sorted(dropped)[0]}",
    )


async def adapt_server_tools(context: RequestContext) -> None:
    """Drop server-tool declarations the routed endpoint will reject, and flatten what they left in the history.

    Reads the route rather than the inbound format, because what upstream accepts is a property of the endpoint being spoken to. A request that arrived in another protocol and was translated *into* Anthropic shape belongs here too, and gets the same treatment for the same reason; one that was translated *out* of it does not, and its `tools` is a different protocol's field that happens to share the name.

    Two passes, and the history one is not conditional on the first. Removing the declaration prevents the rejection this module is named for; leaving the turns that declaration produced would simply buy a different one.
    """
    if context.target_format is not WireFormat.ANTHROPIC_MESSAGES:
        return
    payload = context.payload

    if not context.extras.get(COUNTING_ONLY):
        # Measuring is exempt: nothing is executed, so nothing can come back invented. The history
        # is still flattened below, because that is what makes the measured body the one that would
        # actually be sent.
        _refuse_declarations(payload)
    flattened = _flatten_history(payload)
    if flattened:
        # INFO for the same reason as the declaration line below: routine for a session that used web search, but it rewrites what the model is shown, which is not something to bury in debug.
        logger.info(
            "flattened %d server-tool block(s) left in the history into text; upstream would have rejected them",
            flattened,
        )
