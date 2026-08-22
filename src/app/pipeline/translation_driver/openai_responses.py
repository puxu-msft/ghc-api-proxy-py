"""OpenAI Responses translators.

`docs/.human-controlled/message-translation.md` shows `instructions` as an array of role-bearing objects, and notes we do
not need that flexibility yet. The Copilot upstream does not offer it either: measured on
2026-08-18, it accepts `instructions` only as a string and answers `failed to parse request` to
every array form tried — `[str]`, `[{role, content: str}]`, `[{role, content: [{type: text}]}]`,
the same with `input_text`, and with an explicit `type: message`. So the blocks are joined here.

That drops the per-block `cache_control` marker, which `Conversion` records — but it does not drop
prompt caching. Measured on 2026-08-18: the same 24082-token body sent twice with a plain string
`instructions` and no cache field at all reported `cached_tokens` 0 then 24079. This endpoint
caches by prefix on its own, so the marker Anthropic needs has nothing to do here. Sending the
Anthropic field anyway is refused — `Unknown parameter: 'input[0].content[0].cache_control'`.

The Anthropic passthrough path keeps the blocks and their markers intact.
"""

import json
import logging
from collections.abc import Callable, Mapping
from typing import Any, cast

from app.config.schema import SystemPromptPlacement, WebSearchConstraintPolicy
from app.pipeline.server_tool_text import call_text, web_search_call_text
from app.pipeline.translation_driver.content import (
    BlockKind,
    ContentBlock,
    OpaqueFormat,
    ReasoningState,
    SemanticMessage,
)
from app.pipeline.translation_driver.reasoning import resolve
from app.pipeline.translation_driver.semantic import (
    Conversion,
    LossCode,
    SemanticRequest,
    SystemBlock,
    TranslationRefused,
    TranslationTarget,
    system_blocks_from_value,
)

WIRE_FORMAT = "openai-responses"

logger = logging.getLogger(__name__)

_PASSTHROUGH_KEYS = frozenset(
    {"model", "instructions", "input", "tools", "stream", "max_output_tokens", "temperature"}
)
SYSTEM_ROLE = "system"


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = cast(list[object], value)
    return [dict[str, Any](cast(Mapping[str, Any], e)) for e in entries if isinstance(e, Mapping)]


def _blocks_from_instructions(value: object) -> tuple[list[SystemBlock], LossCode | None]:
    """Read `instructions`, which may be a string or role-bearing entries."""
    if isinstance(value, str) or value is None:
        return system_blocks_from_value(value)
    if not isinstance(value, list):
        return [], LossCode.SYSTEM_FIELD_MALFORMED

    blocks: list[SystemBlock] = []
    problem: LossCode | None = None
    for entry in cast(list[object], value):
        if not isinstance(entry, Mapping):
            problem = LossCode.SYSTEM_FIELD_MALFORMED
            continue
        item = cast(Mapping[str, Any], entry)
        role = item.get("role")
        if role is not None and role != SYSTEM_ROLE:
            # Roles other than system are part of the richer shape we do not use yet.
            problem = LossCode.INSTRUCTIONS_ROLE_NOT_CARRIED
            continue
        found, issue = system_blocks_from_value(item.get("content"))
        blocks.extend(found)
        problem = problem or issue
    return blocks, problem


def from_openai_responses(payload: Mapping[str, Any]) -> SemanticRequest:
    blocks, problem = _blocks_from_instructions(payload.get("instructions"))
    model = payload.get("model")
    request = SemanticRequest(
        model=model if isinstance(model, str) else "",
        system=blocks,
        messages=_messages_from_input(payload.get("input")),
        tools=_dict_list(payload.get("tools")),
        stream=bool(payload.get("stream", False)),
        source_format=WIRE_FORMAT,
    )
    if problem is not None:
        request.conversion.record(problem, "instructions")

    max_output = payload.get("max_output_tokens")
    if isinstance(max_output, int):
        request.max_output_tokens = max_output
    temperature = payload.get("temperature")
    if isinstance(temperature, int | float):
        request.temperature = float(temperature)

    request.extensions = {
        key: value for key, value in payload.items() if key not in _PASSTHROUGH_KEYS
    }
    return request


def _instructions_value(blocks: list[SystemBlock], request: SemanticRequest) -> str:
    """Join the system blocks into the one shape this upstream accepts.

    Blank-line separated so two blocks do not run into one sentence. Per-block metadata is named
    rather than dropped in silence — `cache_control` in practice, which this endpoint neither takes
    nor needs, since it caches by prefix without being told where the boundaries are.
    """
    dropped = sorted({key for block in blocks for key in block.metadata})
    if dropped:
        request.conversion.record(
            LossCode.SYSTEM_METADATA_NOT_CARRIED,
            f"into {WIRE_FORMAT} instructions: {', '.join(dropped)}",
        )
    return "\n\n".join(block.text for block in blocks)


def _function_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Put one tool in the shape the Responses endpoint takes.

    Anthropic names the schema `input_schema` and carries no `type`; Responses wants a flat
    function tool with `parameters`. Passing the Anthropic shape through earns
    `One of the tools requested is invalid.` — measured 2026-08-18.

    A tool that already looks like a Responses tool is left alone, so a Responses-to-Responses
    round trip does not get rewritten.
    """
    if "input_schema" not in tool:
        return tool
    converted = {key: value for key, value in tool.items() if key != "input_schema"}
    converted["type"] = tool.get("type", "function")
    converted["parameters"] = tool["input_schema"]
    return converted


# The family this endpoint executes itself, under its own name. Anthropic spells the declaration `web_search_20250305`; sending that spelling costs the whole turn — `Invalid value: 'web_search_20250305'`, measured 2026-08-20 against gpt-5.6-sol — while `{"type": "web_search"}` returns 200 and really does run the search.
#
# `web_fetch_` is deliberately *not* here, and it is not the same case: this endpoint refuses `web_fetch` under every spelling tried, so there is nothing to map it to. `hosted-web-search-spec.md` §13 has that family refused locally rather than removed quietly, which is its own piece of work.
#
# Nor are `memory_`, `tool_search_`, `text_editor_`, `bash_` and `computer_`. Those are executed by the client, not by the model's host, so there is no hosted equivalent to name — they travel unchanged today and are recorded in `.dev/docs/hosted-web-search/reports/260820-websearch-responses-leg-400-fix.md` §5.1 as the gap that leaves.
_ANTHROPIC_SERVER_TOOL_FAMILIES: tuple[str, ...] = ("web_search_",)

# The spelling this endpoint answers 200 to and actually executes. Upstream normalises it to `web_search_preview` in the tool echo of its reply, which is how we know the two are the same thing to it.
_WEB_SEARCH_TYPE = "web_search"

# What the endpoint accepts beside `type`, measured: `user_location` is written back verbatim in the 200 response.
_WEB_SEARCH_PASSTHROUGH = frozenset({"user_location"})

# Present on the Anthropic declaration and deliberately not forwarded. `name` has no place in a builtin tool object; `cache_control` is a prompt-caching marker this endpoint neither takes nor needs, since it caches by prefix on its own.
_WEB_SEARCH_IGNORED = frozenset({"type", "name", "cache_control"})

# Cannot travel — `Unknown parameter: 'tools[0].max_uses'` — but losing it reverses nothing. It is a ceiling on cost, so the turn goes on without it and upstream reports `tool_usage.web_search.num_requests` back for anyone who wants to know what it actually did.
_WEB_SEARCH_DROPPED = frozenset({"max_uses"})

# The keys of `user_location` this endpoint has been seen to accept and echo. Anything else is removed rather than forwarded: the measured reaction to an unknown sub-parameter is a 400 on the whole request, so passing one through would cost the turn to carry a field upstream does not know.
_USER_LOCATION_KEYS = frozenset({"type", "city", "region", "country", "timezone"})

# Narrowings the client asked for that cannot be expressed upstream. Dropping one does not merely lose a preference — it turns a restriction into a no-op, and nothing downstream can detect that, because the search results never pass through this proxy at all.
_UNREPRESENTABLE_CONSTRAINTS: tuple[str, ...] = ("allowed_domains", "blocked_domains")


def _is_anthropic_server_tool(tool: dict[str, Any]) -> bool:
    """Whether this declaration is an Anthropic server tool under its dated spelling.

    Matched on the date suffix, not on the family prefix alone, and that is the whole difficulty. `web_search_preview` and `web_search_preview_2025_03_11` are values this endpoint *does* accept — they are in the enumeration it prints when it refuses one — so a bare `web_search_` prefix test would strip them out of a Responses-to-Responses crossing that had every right to them. Anthropic dates its server tools `<family>_<YYYYMMDD>`, which nothing on the Responses side spells that way.

    Reading the date rather than the exact value also survives the next version: the declaration in production today is `web_search_20250305`, and matching it literally would go quiet the day Anthropic issues the next one.
    """
    declared = tool.get("type")
    if not isinstance(declared, str):
        return False
    for family in _ANTHROPIC_SERVER_TOOL_FAMILIES:
        if not declared.startswith(family):
            continue
        suffix = declared[len(family) :]
        # `isascii` as well as `isdigit`, because the latter alone accepts other scripts' digits.
        if len(suffix) == 8 and suffix.isascii() and suffix.isdigit():
            return True
    return False


def _web_search_tool(
    tool: dict[str, Any], conversion: Conversion, policy: WebSearchConstraintPolicy
) -> dict[str, Any]:
    """One Anthropic web search declaration in the spelling this endpoint executes.

    The whole mapping is the `type`. Everything else the client may have attached is either accepted verbatim (`user_location`) or cannot travel at all, and the difference between those two costs a turn: the measured reaction to an unknown sub-parameter is a 400 on the whole request, not a shrug.

    `max_uses` is dropped and recorded. It is a *ceiling on cost*, so losing it means more searches and more latency, but it reverses no claim the client made — and upstream reports `tool_usage.web_search.num_requests` back, so what actually happened stays observable.

    `allowed_domains` / `blocked_domains` refuse the request instead. They are a narrowing the client asked for, and dropping one turns a restriction into a no-op that **cannot be detected after the fact**: the search runs upstream and its results reach the model directly, so this proxy never sees which sites were read and has nothing to check them against. Carrying on would mean the model reading pages the client explicitly ruled out while the client is told nothing. Which of those happens is `web_search_domain_restrictions`: `error` refuses, `drop_fields` sends the search without them and records the widening. The default is `drop_fields` and that is a deliberate departure from the spec's D1 ruling — every one of 190 measured client sub-requests carries a non-empty `allowed_domains`, so `error` as the default is not "occasionally refuse" but "never search". Set `error` to have the ruled behaviour back.

    A field outside the allowed set refuses too, rather than being stripped. An unknown field today is a field with meaning tomorrow, and silently removing one turns whatever it asked for into a no-op — the same failure as the domain lists, arriving later and with nobody watching for it.
    """
    mapped: dict[str, Any] = {"type": _WEB_SEARCH_TYPE}
    declared = cast(str, tool.get("type"))
    for key, value in tool.items():
        if key in _WEB_SEARCH_IGNORED:
            continue
        if key in _WEB_SEARCH_PASSTHROUGH:
            mapped[key] = _user_location(value, conversion) if key == "user_location" else value
            continue
        if key in _UNREPRESENTABLE_CONSTRAINTS:
            if not value:
                # An empty list narrows nothing, so there is nothing to lose by not sending it.
                conversion.record(
                    LossCode.SERVER_TOOL_CONSTRAINT_DROPPED,
                    f"{declared}.{key} into {WIRE_FORMAT}: empty, so it restricts nothing",
                )
                continue
            if policy == "error":
                raise TranslationRefused(
                    f"{key} cannot be sent to this endpoint, and dropping it would let the search"
                    " read sites this request ruled out without anything being able to detect it",
                    code="server_tool_constraint_not_representable",
                    field_path=f"tools.{declared}.{key}",
                )
            conversion.record(
                LossCode.SERVER_TOOL_CONSTRAINT_DROPPED,
                f"{declared}.{key} into {WIRE_FORMAT}: upstream has no such parameter, so the"
                " search may read outside the requested set",
            )
            logger.warning(
                "web search %s cannot be sent to this endpoint; the search will run without it and this proxy cannot check what was read",
                key,
            )
            continue
        if key in _WEB_SEARCH_DROPPED:
            conversion.record(
                LossCode.SERVER_TOOL_CONSTRAINT_DROPPED,
                f"{declared}.{key} into {WIRE_FORMAT}: upstream has no such parameter",
            )
            continue
        raise TranslationRefused(
            f"{key} is not a field this endpoint's web search accepts, and removing it would"
            " silently discard whatever it asked for",
            code="unsupported_field",
            field_path=f"tools.{declared}.{key}",
        )
    return mapped


def _user_location(value: Any, conversion: Conversion) -> Any:
    """`user_location` reduced to the keys this endpoint is known to accept.

    Forwarded verbatim otherwise — the Anthropic shape and the shape upstream echoes back are key-for-key identical, measured. An unknown key is removed rather than carried because the measured cost of one is the whole request; a `null` value is kept, because upstream's own default echo contains nulls and they are legal.
    """
    if not isinstance(value, dict):
        return value
    entry = cast(dict[str, Any], value)
    extra = sorted(entry.keys() - _USER_LOCATION_KEYS)
    if not extra:
        return entry
    for key in extra:
        conversion.record(
            LossCode.SERVER_TOOL_CONSTRAINT_DROPPED,
            f"user_location.{key} into {WIRE_FORMAT}: not a key this endpoint is known to accept",
        )
    return {key: item for key, item in entry.items() if key in _USER_LOCATION_KEYS}


def _tools_for_upstream(
    request: SemanticRequest, policy: WebSearchConstraintPolicy
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """The declarations to send, with web search in the spelling this endpoint runs.

    Anthropic's dated spelling costs the whole turn here; `{"type": "web_search"}` is accepted and the upstream really executes the search, returning the answer with the results already folded into it. So the declaration is translated rather than removed — removing it was this repair's first form and it traded a broken turn for a silently missing capability.

    Whether the model behind this actually runs the search is decided elsewhere, and after this: `subscribers/hosted-web-search-gate` reads the resolved model against `models_support_web_search` at `attempt.prepare`. It has to be there rather than here, because this is handed the name the *client* asked for. So this translates unconditionally and the gate answers the request when the answer is no.

    What comes back needs no separate arrangement: a `web_search_call` item has no Anthropic spelling, and both the streaming and non-streaming paths render it as the same line of text that the Anthropic leg flattens its history into.
    """
    kept: list[dict[str, Any]] = []
    mapped: list[str] = []
    mapped_names: set[str] = set()
    function_names: set[str] = set()
    seen_web_search = False
    for tool in request.tools:
        if _is_anthropic_server_tool(tool):
            mapped.append(cast(str, tool["type"]))
            name = tool.get("name")
            if isinstance(name, str):
                # Kept so a `tool_choice` that named this declaration can follow it: the builtin object it becomes has no `name` of its own to match against.
                mapped_names.add(name)
            translated = _web_search_tool(tool, request.conversion, policy)
            if seen_web_search:
                # One builtin, however many declarations arrived. Two identical `{"type": "web_search"}` entries is a shape upstream has never been asked about, and a duplicate says nothing the first one did not.
                request.conversion.record(
                    LossCode.SERVER_TOOL_CONSTRAINT_DROPPED,
                    f"{tool['type']} into {WIRE_FORMAT}: merged into the web search already declared",
                )
                continue
            seen_web_search = True
            kept.append(translated)
            continue
        ordinary = tool.get("name")
        if isinstance(ordinary, str):
            function_names.add(ordinary)
        kept.append(_function_tool(tool))
    if mapped:
        # INFO rather than DEBUG: a client with web search switched on triggers this every request, so it is a setting and not a warning — but it is also the only place an operator can see that the declaration they sent is not the one that went out.
        logger.info(
            "translated %d Anthropic web search declaration(s) into this endpoint's own spelling: %s -> %s",
            len(mapped),
            ", ".join(sorted(mapped)),
            _WEB_SEARCH_TYPE,
        )
    return kept, mapped_names, function_names


def blocks_from_item(item: dict[str, Any]) -> tuple[str, tuple[ContentBlock, ...]]:
    """Read one Responses item as the role it belongs to and the blocks it holds.

    Shared by the request `input` reader and the response `output` reader: an item means the same
    thing in both, and two copies of this would drift the moment one gained an item type.
    """
    kind = str(item.get("type", ""))
    if kind == "message":
        return (
            str(item.get("role", "user")),
            tuple(_block_from_content_part(part) for part in _dict_list(item.get("content"))),
        )
    if kind == "function_call":
        return "assistant", (
            ContentBlock(
                BlockKind.TOOL_USE,
                call_id=str(item.get("call_id") or item.get("id", "")),
                name=str(item.get("name", "")),
                arguments=_decoded_arguments(item.get("arguments")),
                raw=item,
            ),
        )
    if kind == "function_call_output":
        return "user", (
            ContentBlock(
                BlockKind.TOOL_RESULT,
                call_id=str(item.get("call_id", "")),
                output=item.get("output"),
                raw=item,
            ),
        )
    if kind == "reasoning":
        encrypted = str(item.get("encrypted_content", ""))
        return "assistant", (
            ContentBlock(
                BlockKind.REASONING,
                text=_summary_text(item.get("summary")),
                reasoning=(
                    ReasoningState(OpaqueFormat.RESPONSES_ENCRYPTED, encrypted)
                    if encrypted
                    else None
                ),
                raw=item,
            ),
        )
    if kind == "web_search_call":
        # A search the upstream ran itself. It has no Anthropic spelling and nothing to revive: the item carries a query, a status and an opaque id, and the results are not in it — they reached the model directly and are already folded into the answer text that follows. So what is left to say is what was searched for, and it is said in the same words the Anthropic leg flattens its own history into.
        return "assistant", (
            ContentBlock(BlockKind.TEXT, text=web_search_call_text(item.get("action")), raw=item),
        )
    return "user", (ContentBlock(BlockKind.UNKNOWN, raw=item),)


def _messages_from_input(value: object) -> list[SemanticMessage]:
    """Read Responses `input` items back into typed messages.

    Each item becomes its own message, because Responses has no message grouping to preserve: a
    `function_call` is a top-level item, not a block inside an assistant turn.
    """
    messages: list[SemanticMessage] = []
    for item in _dict_list(value):
        role, blocks = blocks_from_item(item)
        messages.append(SemanticMessage(role, blocks))
    return messages


def _block_from_content_part(part: dict[str, Any]) -> ContentBlock:
    kind = str(part.get("type", ""))
    if kind in {"input_text", "output_text", "text"}:
        return ContentBlock(BlockKind.TEXT, text=str(part.get("text", "")), raw=part)
    if kind == "input_image":
        return ContentBlock(BlockKind.IMAGE, raw=part)
    return ContentBlock(BlockKind.UNKNOWN, raw=part)


def _summary_text(value: object) -> str:
    return "".join(str(part.get("text", "")) for part in _dict_list(value))


def _decoded_arguments(value: object) -> Any:
    """`arguments` is a JSON string on the wire; the model holds the decoded value.

    A string that does not parse is kept as-is rather than discarded — a malformed tool call is
    still what the model produced, and losing it would hide the defect.
    """
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


# Measured against real traffic on 2026-08-18: the existing service sends exactly these item
# shapes for the same conversation — `message` with `input_text`, `function_call` whose
# `arguments` is a JSON *string*, `function_call_output` whose `output` is a string, and
# `reasoning` carrying `encrypted_content`.
def _input_from_messages(
    messages: list[SemanticMessage],
    conversion: Conversion,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        parts: list[dict[str, Any]] = []
        for block in message.blocks:
            item = _item_from_block(block, message.role, conversion)
            if item is not None:
                # Text and images belong inside one message item; everything else is top-level,
                # so an accumulated message must be flushed before the standalone item goes out
                # or the conversation order changes.
                if "type" in item and item["type"] in {"input_text", "output_text", "input_image"}:
                    parts.append(item)
                    continue
                if parts:
                    items.append(_message_item(message.role, parts))
                    parts = []
                items.append(item)
        if parts:
            items.append(_message_item(message.role, parts))
    return items


def _message_item(role: str, parts: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "message", "role": role, "content": parts}


def item_from_block(
    block: ContentBlock,
    role: str,
    conversion: Conversion,
) -> dict[str, Any] | None:
    """Render one block as a Responses item, or None when it may not cross."""
    return _item_from_block(block, role, conversion)


def _item_from_block(
    block: ContentBlock,
    role: str,
    conversion: Conversion,
) -> dict[str, Any] | None:
    if block.kind is BlockKind.TEXT:
        # `output_text` is the assistant's own words; anything the model is being *given* is
        # `input_text`, which is why the role decides rather than the block.
        part_type = "output_text" if role == "assistant" else "input_text"
        return {"type": part_type, "text": block.text}
    if block.kind is BlockKind.IMAGE:
        return dict(block.raw) if block.raw else None
    if block.kind is BlockKind.TOOL_USE:
        return {
            "type": "function_call",
            "call_id": block.call_id,
            "name": block.name,
            "arguments": _encoded_arguments(block.arguments),
        }
    if block.kind is BlockKind.TOOL_RESULT:
        return {
            "type": "function_call_output",
            "call_id": block.call_id,
            "output": _flattened_output(block, conversion),
        }
    if block.kind is BlockKind.REASONING:
        return _reasoning_item(block, conversion)
    flattened = _server_tool_block_as_text(block)
    if flattened is not None:
        conversion.record(
            LossCode.SERVER_TOOL_NOT_CARRIED,
            f"{flattened[0]} into {WIRE_FORMAT}: flattened to text",
        )
        return {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": flattened[1]}],
        }
    conversion.record(LossCode.BLOCK_NOT_CARRIED, f"{block.kind.value} into {WIRE_FORMAT}")
    return None


def _server_tool_block_as_text(block: ContentBlock) -> tuple[str, str] | None:
    """An Anthropic server-tool block rendered as text, or `None` when it is not one.

    These arrive because *we sent them*. When a search cannot run, this proxy answers with a `server_tool_use` paired with a failed `web_search_tool_result`, and the client replays that turn verbatim on the next request. There is no `server_tool_use` in the Responses protocol, so without this the whole assistant turn is dropped — not merely the two blocks, since a message left with no content is not carried either.

    What that cost is worth stating plainly: the model would be shown two consecutive user turns and no trace of the search, so it does not know one was attempted, does not know it failed, and is free to try again — producing the same failure, dropped the same way. Telling it once and then forgetting is worse than not telling it, because the second turn looks like the first.

    Text rather than a downgraded `function_call`, for the reason the Anthropic leg gives at the same decision: a downgraded pair refers to a tool this request does not declare, while text refers to nothing. The wording comes from `pipeline/server_tool_text.py`, which is also what the Anthropic leg flattens with — one history, one shape, whichever leg it crosses.
    """
    raw = block.raw
    if not raw:
        return None
    kind = raw.get("type")
    if kind == "server_tool_use":
        name = raw.get("name")
        if not isinstance(name, str):
            return None
        return kind, call_text(name, raw.get("input"))
    if not isinstance(kind, str) or not kind.endswith("_tool_result") or kind == "tool_result":
        return None
    family = kind[: -len("_tool_result")]
    content = raw.get("content")
    if isinstance(content, dict):
        code = cast(dict[str, Any], content).get("error_code")
        if isinstance(code, str) and code:
            return kind, f"[{family} failed: {code}]"
    return kind, f"[{family} results omitted]"


def _encoded_arguments(value: Any) -> str:
    """Responses wants a JSON string here, not an object. Sending an object is a 400."""
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _flattened_output(block: ContentBlock, conversion: Conversion) -> str:
    """`function_call_output.output` is a string, while Anthropic's `content` may be blocks.

    Text blocks join; anything else has no slot here and is recorded rather than silently
    swallowed, which is what happens to an image inside a tool result.
    """
    output = block.output
    if isinstance(output, str):
        return output
    if output is None:
        return ""
    if isinstance(output, list):
        texts: list[str] = []
        dropped = False
        for part in cast(list[object], output):
            if isinstance(part, Mapping):
                entry = cast(Mapping[str, Any], part)
                if str(entry.get("type", "")) == "text":
                    texts.append(str(entry.get("text", "")))
                    continue
            dropped = True
        if dropped:
            conversion.record(
                LossCode.TOOL_RESULT_CONTENT_FLATTENED,
                f"non-text tool result content for {block.call_id}",
            )
        return "".join(texts)
    return json.dumps(output, ensure_ascii=False)


def _reasoning_item(block: ContentBlock, conversion: Conversion) -> dict[str, Any] | None:
    """Render reasoning, or refuse and say so.

    Refusing matters more than rendering. Anthropic's signature is a value only Anthropic can
    produce; writing it into `encrypted_content` would hand upstream something it never issued.
    A carrier this proxy signed is different — the Responses payload is inside it, and taking it
    back out is recovery, not invention.
    """
    state = block.reasoning
    if state is None:
        return {"type": "reasoning", "summary": _summary_parts(block.text)}
    if state.format is OpaqueFormat.RESPONSES_ENCRYPTED:
        return {
            "type": "reasoning",
            "summary": _summary_parts(block.text),
            "encrypted_content": state.value,
        }
    if state.format is OpaqueFormat.PROXY_CARRIER:
        # A carrier this proxy issued. With a payload it round-trips value-exact; bare, `spec.md`
        # says TRANSFORM — restore a summary-only reasoning item rather than drop the block. It
        # used to be dropped, which lost the turn's reasoning entirely on the way back.
        item: dict[str, Any] = {
            "type": "reasoning",
            "summary": _summary_parts(block.text),
        }
        if state.encrypted_content:
            item["encrypted_content"] = state.encrypted_content
        return item
    conversion.record(
        LossCode.REASONING_STATE_NOT_PORTABLE,
        f"{state.format.value} cannot be written as {WIRE_FORMAT} encrypted_content",
    )
    return None


def _summary_parts(text: str) -> list[dict[str, Any]]:
    return [{"type": "summary_text", "text": text}] if text else []


def _place_in_instructions(payload: dict[str, Any], request: SemanticRequest) -> None:
    """`instructions-joint-string`: the blocks as one string in the top-level field."""
    payload["instructions"] = _instructions_value(request.system, request)


# Total rather than defaulted, the same reasoning as `layout_strategy` in the request hook: the
# schema admits exactly the spellings the config defines, so a missing case is a bug here rather
# than an operator's typo, and a fallback would silently reshape the request.
#
# One entry today. A second — `as-role-system`, the prompt as a `role: system` message at the head
# of `input` — adds a function and a line; the endpoint was measured to accept that shape.
_SYSTEM_PROMPT_PLACEMENTS: dict[
    SystemPromptPlacement, Callable[[dict[str, Any], SemanticRequest], None]
] = {
    "instructions-joint-string": _place_in_instructions,
}


def _carry_forced_search(
    payload: dict[str, Any],
    request: SemanticRequest,
    mapped_names: set[str],
    function_names: set[str],
) -> None:
    """Carry an Anthropic `tool_choice` that demanded the search across the format boundary.

    `tool_choice` is not a key any translator claims, so it rides in `extensions` and is dropped whole when the formats differ — correct for the general case, and wrong for this one. Measured over 190 real Claude Code sub-requests, 95 of them force the search this way, and those requests exist for no other purpose: the client has already decided a search is what it wants and sends a turn saying `Perform a web search for the query: X`.

    Losing it there is worse than losing a preference. The model, no longer obliged to search, may answer from memory instead — and the client renders whatever comes back under a `Web search results for query:` heading regardless. A dropped `tool_choice` is one of the ways that heading ends up over text nothing searched for.

    Upstream takes `{"type": "web_search"}` here: measured 200, echoed back normalised, with a `web_search_call` in the output and `num_requests` of 1. It forces the search rather than merely tolerating the field.
    """
    if payload.get("tool_choice") is not None:
        return
    choice = request.extensions.get("tool_choice")
    if not isinstance(choice, dict):
        return
    entry = cast(dict[str, Any], choice)
    named = entry.get("name")
    if not isinstance(named, str) or named not in mapped_names:
        return
    if named in function_names:
        # Ambiguous: the name is also an ordinary function tool's. Forcing a hosted search would be
        # answering a question only the client can answer.
        return
    payload["tool_choice"] = {"type": _WEB_SEARCH_TYPE}


def _repoint_tool_choice(
    payload: dict[str, Any], mapped_names: set[str], function_names: set[str]
) -> None:
    """Follow a `tool_choice` that named a web search declaration into the builtin spelling.

    A builtin tool object carries no `name` — it is `{"type": "web_search"}` and nothing else — so a choice that named the Anthropic declaration now points at something with no name to match. Left alone it costs the turn on its own account, which would be the mapping trading one rejection for another.

    Upstream takes `{"type": "web_search"}` in the choice position: measured 200, echoed back normalised as `web_search_preview`, with `tool_usage.web_search.num_requests` of 1 and a `web_search_call` in the output. It really does force the search rather than merely being tolerated.

    Only reachable on the same-format crossing today. Anthropic's `tool_choice` is not a key any translator claims, so it rides in `extensions` and is dropped on the way to another format — the Anthropic leg's forced choice never arrives here at all, which is its own gap and recorded as one.
    """
    choice = payload.get("tool_choice")
    if not isinstance(choice, dict):
        return
    entry = cast(dict[str, Any], choice)
    named = entry.get("name")
    if not isinstance(named, str) or named not in mapped_names:
        return
    if named in function_names:
        # The name resolves to an ordinary function tool as well. Which one the client meant is its
        # own ambiguity to own, and answering it by forcing a hosted search would be this proxy
        # inventing the answer — so the choice is left exactly as it arrived.
        return
    payload["tool_choice"] = {"type": _WEB_SEARCH_TYPE}


def _drop_dangling_tool_choice(payload: dict[str, Any]) -> None:
    """Remove a `tool_choice` left pointing at a declaration that is no longer being sent.

    Only reachable on the same-format crossing. Anthropic's `tool_choice` is not a key any translator claims, so it rides in `extensions` and is dropped on the way to another format — but a Responses request replays its own extensions verbatim, and a client that sent the Anthropic spelling of a declaration can have named it here too.

    Left behind, it trades one rejection for another: the declaration would no longer be refused, and the choice naming a tool that is not declared would be. That is the same reasoning, and the same two cases, as `_drop_dangling_choice` on the Anthropic leg — a choice that names a missing tool, and a choice of any kind once nothing is left to choose from.
    """
    choice = payload.get("tool_choice")
    if choice is None:
        return
    remaining = payload.get("tools")
    if not remaining:
        del payload["tool_choice"]
        return
    if not isinstance(choice, dict) or not isinstance(remaining, list):
        return
    entry = cast(dict[str, Any], choice)
    named = entry.get("name")
    if not isinstance(named, str):
        return
    declared = {
        cast(dict[str, Any], tool).get("name")
        for tool in cast(list[Any], remaining)
        if isinstance(tool, dict)
    }
    if named not in declared:
        del payload["tool_choice"]


def to_openai_responses(
    request: SemanticRequest,
    target_model: TranslationTarget | None = None,
    *,
    system_prompts: SystemPromptPlacement = "instructions-joint-string",
    web_search_domain_restrictions: WebSearchConstraintPolicy = "drop_fields",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": request.model,
        "input": _input_from_messages(request.messages, request.conversion),
    }
    if request.system:
        _SYSTEM_PROMPT_PLACEMENTS[system_prompts](payload, request)
    dropped_any = False
    mapped_names: set[str] = set()
    function_names: set[str] = set()
    if request.tools:
        tools, mapped_names, function_names = _tools_for_upstream(request, web_search_domain_restrictions)
        dropped_any = len(tools) != len(request.tools)
        if tools:
            # Not `[]` when everything was removed. An empty array is a different thing to say than saying nothing, and absent is the spelling every request without tools already uses.
            payload["tools"] = tools
    if request.stream:
        payload["stream"] = True
    if request.max_output_tokens is not None:
        payload["max_output_tokens"] = request.max_output_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    _apply_reasoning(payload, request, target_model or TranslationTarget())
    payload.update(request.extensions_for(WIRE_FORMAT))
    # After the extensions, because that is where `tool_choice` arrives on the crossing where it survives at all. Repointing comes first: a choice that named a mapped declaration is not dangling, it just has a new spelling to follow.
    if mapped_names:
        _carry_forced_search(payload, request, mapped_names, function_names)
        _repoint_tool_choice(payload, mapped_names, function_names)
    if dropped_any:
        _drop_dangling_tool_choice(payload)
    return payload


def _apply_reasoning(
    payload: dict[str, Any], request: SemanticRequest, target_model: TranslationTarget
) -> None:
    """Write the `reasoning` object this request's intent resolves to, if any.

    Nothing is written when the request expressed no intent. That is the pre-existing behaviour and it stays: a body that never mentioned `thinking` should not start carrying a reasoning policy because this function was added.

    When there *is* an intent, the target's own published effort names decide what it becomes — `resolve` will not return a name this model does not offer. An intent that cannot be rendered at all is recorded as a loss rather than dropped in silence, because the request asked for something and did not get it.
    """
    intent = request.reasoning
    if intent is None:
        return
    resolution = resolve(intent, target_model.reasoning_efforts)
    if resolution.effort is None:
        request.conversion.record(
            LossCode.REASONING_INTENT_NOT_CARRIED,
            f"{intent.mode} reasoning was not sent: {resolution.reason}",
        )
        return
    payload["reasoning"] = {"effort": resolution.effort}
    if resolution.approximated:
        detail = resolution.reason or f"{intent.mode} reasoning was sent as effort {resolution.effort}"
        request.conversion.record(LossCode.REASONING_INTENT_APPROXIMATED, detail)
