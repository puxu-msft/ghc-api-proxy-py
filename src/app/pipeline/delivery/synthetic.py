"""A reply this proxy writes itself, when a search cannot be run but must still be answered.

The alternative to answering is refusing, and both are honest — neither claims a search happened. What decides between them is what the client does next with each.

Claude Code issues a web search as its own sub-request: `tools` holds nothing but the search, the user turn reads `Perform a web search for the query: X`, and whatever comes back is rendered into the main conversation under a `Web search results for query:` heading attached unconditionally. A refusal reaches that conversation as `tool_result` with `is_error: true` and the model handles it well — measured. But it reaches it *after the client has retried*, three times in the one case on record, because an HTTP error is a transport failure as far as the client is concerned and transport failures are worth retrying. A search that cannot run is not going to start working on the third attempt.

So the reply is synthesised instead, in the shape Anthropic defines for exactly this: `server_tool_use` paired with a `web_search_tool_result` whose content is a single `web_search_tool_result_error` object. That is a 200 carrying a failed tool, not a failed request — the documented contract is that a search error "still returns a 200 (success) response", with `content` as one object rather than a list. Nothing retries it, and the model is told in its own protocol that the search failed rather than being handed an HTTP error string to interpret.

`error_code` is `unavailable`, which the documented enumeration defines as an internal error. The alternatives name conditions that did not happen: `too_many_requests`, `max_uses_exceeded`, `query_too_long`, `request_too_large`, `invalid_tool_input`. Nothing was too long or too frequent — this endpoint does not run the tool.

**What this is not.** It is not a search that returned nothing: `content: []` is the documented shape for that, and it would be a claim about the web rather than about us. It is not text explaining the situation either, because the client's heading would present that explanation as the search's findings. The error object is the only form that says "the search did not happen" in a vocabulary the client already parses.

**Untested against the real client, and deliberately recorded as such.** The refusal path has a transcript behind it; this one has the protocol documentation and nothing else. If the client turns out to handle it worse, the evidence for the alternative is in `.dev/docs/hosted-web-search/reports/260820-claude-code-websearch-request-forensics.md` §4.2.
"""

from typing import Any, cast

import orjson

# The documented error code for "an internal error occurred", which is what a proxy that cannot
# reach the tool at all amounts to from the client's side.
ERROR_CODE = "unavailable"

_MAX_QUERY = 400


def query_from_request(payload: Any) -> str:
    """The search the client was asking for, read off the turn that asked for it.

    The sub-request carries one user turn and it says what to search for, so the last user text is the query — no parsing of the client's phrasing, which would break the moment it was reworded. Returned whole rather than stripped of the `Perform a web search for the query:` preamble for the same reason.

    Reads both shapes, because by the time this runs the body may have been translated: the Anthropic leg still has `messages` with `text` blocks, the Responses leg has `input` with `input_text` ones. Taking it off whichever is present beats snapshotting the original body, which would put a copy of every request in memory to serve the rare one that fails this way.

    Empty when there is nothing to read. A `server_tool_use` with an empty query still pairs correctly with its error result, and inventing a query would be the one kind of dishonesty this whole path exists to avoid.
    """
    if not isinstance(payload, dict):
        return ""
    body = cast(dict[str, Any], payload)
    raw = body.get("messages")
    if not isinstance(raw, list):
        raw = body.get("input")
    if not isinstance(raw, list):
        return ""
    for message in reversed(cast(list[Any], raw)):
        if not isinstance(message, dict):
            continue
        turn = cast(dict[str, Any], message)
        if turn.get("role") != "user":
            continue
        content = turn.get("content")
        if isinstance(content, str):
            return content[:_MAX_QUERY]
        if not isinstance(content, list):
            continue
        for block in reversed(cast(list[Any], content)):
            if not isinstance(block, dict):
                continue
            part = cast(dict[str, Any], block)
            if part.get("type") not in {"text", "input_text"}:
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text[:_MAX_QUERY]
    return ""


def failed_search_blocks(query: str, *, call_id: str) -> list[dict[str, Any]]:
    """The pair of content blocks that says a search was attempted and did not run.

    Both are required. The result block references its call by `tool_use_id`, so a result without its `server_tool_use` refers to nothing, and a call without its result is an unanswered tool the client would wait on.
    """
    return [
        {
            "type": "server_tool_use",
            "id": call_id,
            "name": "web_search",
            "input": {"query": query},
        },
        {
            "type": "web_search_tool_result",
            "tool_use_id": call_id,
            # A single object, not a list. The documented shape for an error, and the same
            # discriminator `subscribers/server_tools.py` reads when flattening one of these later.
            "content": {"type": "web_search_tool_result_error", "error_code": ERROR_CODE},
        },
    ]


def failed_search_body(query: str, *, message_id: str, model: str, call_id: str) -> dict[str, Any]:
    """The whole non-streaming reply."""
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": failed_search_blocks(query, call_id=call_id),
        # `end_turn`, not `tool_use`: there is nothing here for the client to execute. The search
        # was the model's host's to run, and it is already over.
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


def failed_search_sse(query: str, *, message_id: str, model: str, call_id: str) -> bytes:
    """The same reply as an Anthropic SSE stream.

    Written in the upstream's own vocabulary rather than as finished client bytes, so it goes through the same assembler, buffer and delivery path every real reply takes. A synthetic response that bypassed those would be the one reply in the system whose framing nothing else had ever exercised.
    """
    blocks = failed_search_blocks(query, call_id=call_id)
    frames: list[str] = [
        _frame(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            },
        )
    ]
    for index, block in enumerate(blocks):
        frames.append(
            _frame(
                "content_block_start",
                {"type": "content_block_start", "index": index, "content_block": block},
            )
        )
        frames.append(
            _frame("content_block_stop", {"type": "content_block_stop", "index": index})
        )
    frames.append(
        _frame(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 0},
            },
        )
    )
    frames.append(_frame("message_stop", {"type": "message_stop"}))
    return "".join(frames).encode()


def _frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n"
