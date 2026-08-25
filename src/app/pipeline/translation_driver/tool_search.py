"""Which tool is the client's tool-search tool, and what it becomes on the Responses leg.

**The problem this exists for.** Anthropic's wire has two kinds of tool search. The hosted kind declares itself — `tool_search_tool_regex_20251119` and its BM25 sibling carry a `type`, so recognising one is a lookup. The custom kind, which is what Claude Code uses, is **an ordinary function tool with nothing to distinguish it**: the client executes the search itself and returns `tool_reference` blocks. Anthropic's own documentation specifies only that output side; the declaration carries no marker at all.

So identifying it is a guess, and this module is mostly about making that guess narrow and making its failure mode "do nothing" rather than "do something wrong".

**Why a wrong guess is expensive.** Promotion *replaces*: the tool identified as the search tool leaves `tools` and comes back as `{"type": "tool_search"}`. Measured — leaving it in place beside the builtin makes the model call it instead, so the builtin does nothing and the deferred tools never load. Which means mistaking an ordinary tool for the search tool deletes a capability the client declared, and does it silently: the model simply never sees that tool again.

**The order below is that cost made into control flow.** A gate that excludes almost every request; then a protocol-grade check that cannot be wrong but is unavailable on the first turn; then a name match against the two names first-party clients are known to hardcode; then nothing. Each step can decline, and declining means the caller strips `defer_loading` exactly as it did before this feature existed — a shape that works.

Spec: `.dev/docs/anthropic-responses-bridge/spec.md`「Tools 与 tool choice」.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from app.pipeline.translation_driver.content import BlockKind, ContentBlock, SemanticMessage

# Anthropic's hosted tool-search declarations, matched on the family rather than the exact dated spelling — `tool_search_tool_regex_20251119` and `tool_search_tool_bm25_20251119` today, and whatever date comes next.
HOSTED_SEARCH_PREFIXES: tuple[str, ...] = ("tool_search_tool_regex", "tool_search_tool_bm25")

# The names first-party clients hardcode for their own client-executed search tool. **Two entries, and they disagree** — Claude Code says `ToolSearch` (`app.pretty.js`, verbatim across 2.1.207/226/241), VS Code Copilot Chat says `tool_search` (`CUSTOM_TOOL_SEARCH_NAME`). That disagreement is the evidence that this is application convention and not protocol, which is also why the list is a constant here rather than a config key: it is an observation of what clients are called, not a dial an operator tunes.
CLIENT_SEARCH_NAMES: frozenset[str] = frozenset({"ToolSearch", "tool_search"})


def is_hosted_search_tool(tool: Mapping[str, Any]) -> bool:
    """Whether this declaration is Anthropic's *hosted* tool search."""
    declared = tool.get("type")
    if not isinstance(declared, str):
        return False
    return any(declared.startswith(prefix) for prefix in HOSTED_SEARCH_PREFIXES)


def has_deferred_tool(tools: Iterable[Mapping[str, Any]]) -> bool:
    """The gate: does this request actually use deferred loading?

    `defer_loading: true` is only meaningful under a tool-search mechanism, so its absence means no identification needs to happen at all. This is what keeps the name match below from ever looking at an ordinary request — a tool called `ToolSearch` in a request with no deferred tools is never examined, let alone promoted.
    """
    return any(tool.get("defer_loading") is True for tool in tools)


def _search_name_from_history(messages: Sequence[SemanticMessage]) -> str:
    """The search tool's name, read off a `tool_reference` the client already returned.

    **This is the only identification here that cannot be wrong.** Returning `tool_reference` blocks from a tool result *is* the definition of a custom search tool in Anthropic's documentation, so the call it answers names the search tool by construction. Its limit is availability, not accuracy: on the first turn there is no history to read, and the first turn is where the tools array has to be decided.

    Matched by `call_id` rather than by position: a turn may carry several tool results, and the one carrying references is not necessarily the first.
    """
    referenced: set[str] = set()
    for message in messages:
        for block in message.blocks:
            if block.kind is BlockKind.TOOL_RESULT and _carries_tool_reference(block):
                referenced.add(block.call_id)
    if not referenced:
        return ""
    for message in messages:
        for block in message.blocks:
            if block.kind is BlockKind.TOOL_USE and block.call_id in referenced and block.name:
                return block.name
    return ""


def _carries_tool_reference(block: ContentBlock) -> bool:
    output = block.output
    if not isinstance(output, list):
        return False
    for part in cast(list[Any], output):
        if isinstance(part, Mapping) and cast(Mapping[str, Any], part).get("type") == "tool_reference":
            return True
    return False


def resolve_client_search_tool(
    tools: Sequence[Mapping[str, Any]], messages: Sequence[SemanticMessage]
) -> str:
    """The name of the client's own search tool, or `""` when it cannot be identified.

    `""` is a real answer and the caller must honour it by leaving the request alone apart from removing `defer_loading` — see the module docstring for why declining beats guessing.

    Hosted declarations are not this function's business: they identify themselves and take the `server` execution path.
    """
    if not has_deferred_tool(tools):
        return ""

    from_history = _search_name_from_history(messages)
    if from_history:
        return from_history

    named = [
        str(tool.get("name"))
        for tool in tools
        if isinstance(tool.get("name"), str) and tool.get("name") in CLIENT_SEARCH_NAMES
    ]
    # Exactly one. Two tools both bearing known search names is a request nobody has been observed to send, and picking either would be inventing a rule; the safe answer is the one that changes nothing.
    return named[0] if len(named) == 1 else ""


def as_client_search_tool(tool: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """The client's search tool, in the shape the Responses leg spells it.

    Returns the tool and **the names of any fields this proxy had to invent**. Inventing one is defensible — upstream refuses a client-executed search with no description — but it puts words in the body the client never wrote, and `SYNTHETIC_TURN_ADDED` exists precisely so an addition is visible to whoever reads the record.

    `description` is required rather than optional decoration — upstream refuses a client-executed search without one (`Client-executed tool_search requires a description.`), so an empty description would trade this request's 400 for another. The client's own text is carried across; a tool that arrived without any gets a sentence describing what the model is being offered, because the alternative is a refusal.

    `parameters` carries the client's `input_schema` so the model's `arguments` come back in the shape that tool expects — which is what lets the response side hand them straight back as the tool's own input.
    """
    invented: list[str] = []
    described = tool.get("description")
    if not (isinstance(described, str) and described.strip()):
        described = "Search for tools that are available but not yet loaded."
        invented.append("description")
    schema = tool.get("input_schema")
    if not isinstance(schema, Mapping) or not schema:
        schema = {"type": "object", "properties": {"query": {"type": "string"}}}
        invented.append("parameters")
    return {
        "type": "tool_search",
        "execution": "client",
        "description": described,
        "parameters": dict(cast(Mapping[str, Any], schema)),
    }, tuple(invented)


HOSTED_SEARCH_TOOL: dict[str, Any] = {"type": "tool_search", "execution": "server"}


@dataclass(frozen=True, slots=True)
class SearchContext:
    """What the history writer needs to know to render a tool search on this leg.

    Built once per request. Empty when no client search tool was identified, and an empty one makes every branch that consults it inert — which is how "declined to identify" turns into "wrote the history exactly as before".
    """

    tool_name: str = ""
    # The ids of the calls that went to that tool. A `tool_result` is a search result iff it answers one of these; matching on the id rather than on the content means a result that happens to carry no references is still recognised as belonging to the search.
    call_ids: frozenset[str] = frozenset()
    # Every tool the request declares, already in Responses shape, indexed by name. `tool_reference` names a tool; `tool_search_output` needs its whole definition, and this is where that definition comes from.
    definitions: Mapping[str, dict[str, Any]] = field(default_factory=lambda: dict[str, dict[str, Any]]())

    @property
    def active(self) -> bool:
        return bool(self.tool_name)

    def is_search_call(self, call_id: str) -> bool:
        return bool(call_id) and call_id in self.call_ids

    def loaded_tools(self, output: Any) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
        """The definitions a `tool_result` full of `tool_reference` blocks is asking for, and what it could not carry.

        A `tool_reference` is an instruction — load this tool's schema — so the honest rendering is the tool's definition, not a sentence saying a tool was found. A name this request does not declare is skipped rather than invented: the client asked for something that is not on the table, and a fabricated schema is worse than a shorter list.

        **But skipping without a trace is its own defect**, which is why the second half of the return exists. A result carrying text, an error, or a name this request no longer declares would otherwise render as a search that completed and found nothing — the model told a comfortable falsehood while the client said something else entirely. The caller records these; nothing here is dropped in silence.
        """
        if not isinstance(output, list):
            # A string result — the shape a client uses to say something in prose. Nothing to load, and the caller needs to know the difference between this and an empty search.
            return [], ("non-reference tool result content",) if output else ()
        loaded: list[dict[str, Any]] = []
        uncarried: list[str] = []
        for part in cast(list[Any], output):
            if not isinstance(part, Mapping):
                uncarried.append("non-object tool result part")
                continue
            entry = cast(Mapping[str, Any], part)
            if entry.get("type") != "tool_reference":
                uncarried.append(f"{entry.get('type') or 'untyped'} part")
                continue
            name = entry.get("tool_name")
            if isinstance(name, str) and name in self.definitions:
                loaded.append(dict(self.definitions[name]))
            else:
                uncarried.append(f"reference to undeclared tool {name!r}")
        return loaded, tuple(uncarried)
