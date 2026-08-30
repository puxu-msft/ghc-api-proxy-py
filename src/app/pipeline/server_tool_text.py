"""One rendering of a server-tool call as text, shared by both legs.

A `web_search` call reaches a client through two different routes and has to look the same on both. On the Anthropic leg `builtin:server-tool-capability` flattens the blocks a past turn left in the history, because that endpoint refuses them. On the Responses leg the upstream executes the search itself and reports it as a `web_search_call` item, and this renders that too.

**That second caller is a gap, not a translation.** The reason written here until 2026-08-30 was that a `web_search_call` "has no Anthropic spelling", which is false: Anthropic spells it `server_tool_use` paired with `web_search_tool_result`, `hosted-web-search-spec.md` §5.3 froze the shape, and the user ruled it (D6) on 2026-08-20. The item's results really are absent from the item — they arrive later, as `url_citation` annotations on the text that follows — so restoring the pair means reading those, which nothing does yet. Until that lands, the Responses leg renders text; what it must not do is call that outcome inevitable, which is what the old wording did and what kept it from being fixed.

Both are "say in text what the model did", and they must say it the same way. A conversation is not pinned to one leg: the same history moves between them when a client switches model, and two renderings would leave one session carrying two shapes of the same fact. Nothing would report that — it is not an error at either end, just a history that quietly stopped being uniform. So the wording lives in one place and neither caller spells it out.
"""

from typing import Any, cast

WEB_SEARCH = "web_search"


def call_subject(raw_input: Any) -> str:
    """What the call was about, as a trailing fragment, or the empty string.

    Reads `query` and `url` because the families name their argument differently — `web_search` asks a question, `web_fetch` names a page — and a renderer that knew only about the first turned every fetch into a bare `[web_fetch]`.

    Stripped, because the surrounding text is generated: a trailing newline in the client's query would put whitespace at the end of an assistant turn, which upstream rejects separately.
    """
    if not isinstance(raw_input, dict):
        return ""
    entry = cast(dict[str, Any], raw_input)
    for key in ("query", "url"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return f" {value.strip()}"
    return ""


def call_text(family: str, raw_input: Any) -> str:
    """The line that stands in for one server-tool call."""
    return f"[{family}]{call_subject(raw_input)}"


def web_search_call_text(action: Any) -> str:
    """The line for a Responses `web_search_call`, read off its `action`.

    `action` carries `query` and `queries` together, with the same content in both — measured on this project's own cassettes. `query` is preferred and `queries` is the fallback, so a future response that drops the singular still says what was searched for.

    Absent entirely on an item that never got that far, which the caller must tolerate: a `status` of `incomplete` has been observed with no `action` at all. That renders as a bare `[web_search]`, which is true — a search happened and we cannot say what for.

    Deliberately *not* carrying the item's `id`. The reference implementation puts it in the text, where it arrives as 416 characters of opaque base64 in the middle of an assistant turn: it inflates every subsequent request, it means nothing to the model reading it, and it publishes a server-side handle to the client. It is a reference this project has already decided not to continue (no continuation carrier), so nothing downstream can spend it.
    """
    if not isinstance(action, dict):
        return call_text(WEB_SEARCH, None)
    entry = cast(dict[str, Any], action)
    query = entry.get("query")
    if not (isinstance(query, str) and query.strip()):
        queries = entry.get("queries")
        if isinstance(queries, list):
            joined = ", ".join(
                q.strip() for q in cast(list[Any], queries) if isinstance(q, str) and q.strip()
            )
            query = joined or None
    return call_text(WEB_SEARCH, {"query": query} if isinstance(query, str) else None)
