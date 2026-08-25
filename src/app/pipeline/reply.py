"""A finished reply, read back in the vocabulary the client asked in.

Split out of `app.server.handler` on 2026-08-22. These three read a reply that has already arrived whole — they neither drive the request nor write to the wire, which is why they are neither the driver nor the edge.
"""

from typing import Any, cast

from app.core.chain import Chain
from app.pipeline.delivery import CompletedBlock
from app.pipeline.delivery.assembling import Terminal
from app.pipeline.delivery.formats.anthropic_messages import (
    terminal_from_anthropic,
)
from app.pipeline.delivery_policy import dialect_for
from app.pipeline.driver import CLIENT_SEARCH_TOOL, HandledRequest
from app.pipeline.request import WireFormat


def response_payload(chain: Chain, handled: HandledRequest, body: dict[str, Any]) -> dict[str, Any]:
    """Bring an upstream body back to the format the client asked in.

    Without this a translated route answers in the upstream's shape, which the client did not ask for and cannot parse.
    """
    route = handled.route
    if handled.synthesized:
        # Already in the client's format: this proxy wrote it, in the shape the client asked in.
        # Translating it would carry an Anthropic body through the Responses reader, which has no `server_tool_use` to read and would hand back the reply with its two blocks missing.
        return body
    if not route.translation_required:
        return body
    translated, semantic = chain.translators.translate_response(
        body,
        source=route.target_format,
        target=route.inbound_format,
        # Put here by the request half. Without it a `tool_search_call` has no name to come back under, and the client is handed a turn in which the model appears to have said nothing while it is in fact waiting for a search.
        client_search_tool=str(handled.context.extras.get(CLIENT_SEARCH_TOOL, "")),
    )
    if not semantic.conversion.lossless:
        handled.context.extras["response_conversion_losses"] = list(semantic.conversion.losses)
    return translated

def blocks_from_anthropic(body: dict[str, Any]) -> list[CompletedBlock]:
    """Read the content blocks out of an Anthropic-shaped response body."""
    content = body.get("content")
    if not isinstance(content, list):
        return []
    blocks: list[CompletedBlock] = []
    for index, raw in enumerate(cast(list[object], content)):
        if not isinstance(raw, dict):
            continue
        payload = cast(dict[str, Any], raw)
        blocks.append(
            CompletedBlock(index=index, kind=str(payload.get("type", "")), payload=payload)
        )
    return blocks

def reply_summary(handled: HandledRequest, payload: dict[str, Any]) -> Terminal | None:
    """Summarise a buffered reply for the console line, or `None` when this route's shape cannot be read.

    `payload` is in the **client's** format by the time it gets here, which is what decides whether it can be read at all: only an Anthropic-shaped body has the `content` blocks the reader wants. An inbound `/responses` or `/chat/completions` request keeps its own shape end to end, and reading one of those as Anthropic finds nothing — silently, since an absent `content` is indistinguishable from a reply that had none.

    Returning `None` rather than an empty summary is the honest answer: those lines carry no reasoning or tool fields today, which is a gap worth closing but not one to paper over with a record that says a reply had nothing in it. See `.dev/docs/tui/deferred.md`.

    The dialect is separate and comes from the route, because which *words* to use is about the upstream leg while which *reader* to use is about the client leg, and on a translated route those are two different formats.
    """
    if handled.route.inbound_format is not WireFormat.ANTHROPIC_MESSAGES:
        return None
    return terminal_from_anthropic(payload, blocks_from_anthropic(payload), dialect=dialect_for(handled))
