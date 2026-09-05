"""Anthropic server-tool blocks this proxy writes itself.

The two response paths consume different upstream shapes — a complete Responses body and an SSE item — but they owe the Anthropic client one wire contract. Building the pair here keeps the call id, required input object, result error shape, and action-loss description identical on both paths. The synthetic failed-search reply uses the same builder for the same reason.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

WEB_SEARCH = "web_search"
WEB_SEARCH_RESULT = "web_search_tool_result"
UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class WebSearchActionProjection:
    """The part of a Responses web-search action Anthropic can carry."""

    input: dict[str, Any]
    readable: str = ""
    loss_detail: str = ""


@dataclass(frozen=True, slots=True)
class UnavailableWebSearchPair:
    """One schema-valid server-tool call and its unavailable result."""

    call: dict[str, Any]
    result: dict[str, Any]
    action: WebSearchActionProjection

    @property
    def blocks(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.call, self.result


def new_server_tool_call_id() -> str:
    """Mint the short local identity used only to correlate this pair."""
    return f"srvtoolu_{uuid4().hex[:24]}"


def project_web_search_action(action: object) -> WebSearchActionProjection:
    """Project one legal Responses action without inventing an Anthropic input.

    Anthropic's web-search call has a query input. OpenAI also reports
    ``open_page`` and ``find_in_page`` actions; their URL and pattern have no
    measured Anthropic web-search input spelling. They remain readable for a
    text fallback and observable in the loss detail, but do not masquerade as
    a query.
    """
    if not isinstance(action, Mapping):
        return WebSearchActionProjection(
            input={},
            loss_detail="web search action was absent or not an object",
        )

    entry = dict[str, Any](cast(Mapping[str, Any], action))
    action_type = entry.get("type")
    if action_type == "search":
        query = entry.get("query")
        if not (isinstance(query, str) and query.strip()):
            queries = entry.get("queries")
            if isinstance(queries, list):
                joined = ", ".join(
                    candidate.strip()
                    for candidate in cast(list[Any], queries)
                    if isinstance(candidate, str) and candidate.strip()
                )
                query = joined or None
        if isinstance(query, str) and query.strip():
            normalized = query.strip()
            return WebSearchActionProjection(
                input={"query": normalized},
                readable=normalized,
            )
        return WebSearchActionProjection(
            input={},
            readable="search",
            loss_detail="search action carried no non-empty query",
        )

    if action_type == "open_page":
        url = entry.get("url")
        readable = "open_page"
        if isinstance(url, str) and url.strip():
            readable = f"open_page {url.strip()}"
        return WebSearchActionProjection(
            input={},
            readable=readable,
            loss_detail=_unrepresentable_action(entry),
        )

    if action_type == "find_in_page":
        url = entry.get("url")
        pattern = entry.get("pattern")
        parts = ["find_in_page"]
        if isinstance(url, str) and url.strip():
            parts.append(url.strip())
        if isinstance(pattern, str) and pattern.strip():
            parts.append(pattern.strip())
        return WebSearchActionProjection(
            input={},
            readable=" ".join(parts),
            loss_detail=_unrepresentable_action(entry),
        )

    rendered = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    readable = str(action_type).strip() if isinstance(action_type, str) else ""
    return WebSearchActionProjection(
        input={},
        readable=f"{readable} {rendered}".strip(),
        loss_detail=f"unknown web search action has no Anthropic input spelling: {rendered}",
    )


def unavailable_web_search_pair(
    action: object,
    *,
    call_id: str | None = None,
    input_override: Mapping[str, Any] | None = None,
) -> UnavailableWebSearchPair:
    """Build the native pair used when structured search results cannot cross.

    ``input_override`` is for a caller that already owns an Anthropic input —
    the synthetic refusal reads the client's text and must preserve it whole.
    Responses callers omit it and use the action projection instead.
    """
    projection = project_web_search_action(action)
    resolved_call_id = call_id or new_server_tool_call_id()
    call_input = (
        dict[str, Any](input_override)
        if input_override is not None
        else projection.input
    )
    return UnavailableWebSearchPair(
        call={
            "type": "server_tool_use",
            "id": resolved_call_id,
            "name": WEB_SEARCH,
            "input": call_input,
        },
        result={
            "type": WEB_SEARCH_RESULT,
            "tool_use_id": resolved_call_id,
            "content": {
                "type": "web_search_tool_result_error",
                "error_code": UNAVAILABLE,
            },
        },
        action=projection,
    )


def partial_web_search_loss(pair: UnavailableWebSearchPair, status: object) -> str:
    detail = f"web_search_call status={status!r}; structured result unavailable"
    if pair.action.loss_detail:
        detail += f"; {pair.action.loss_detail}"
    return detail


def web_search_call_id_loss(item_id: object) -> str | None:
    if not isinstance(item_id, str) or not item_id:
        return None
    return "web_search_call upstream id not carried"


def unsolicited_web_search_loss(action: object) -> str:
    projected = project_web_search_action(action)
    detail = "unsolicited web_search_call flattened to text; result provenance not carried"
    if projected.loss_detail:
        detail += f"; {projected.loss_detail}"
    return detail


def _unrepresentable_action(action: Mapping[str, Any]) -> str:
    rendered = json.dumps(dict(action), ensure_ascii=False, sort_keys=True)
    return f"{action.get('type')} action has no Anthropic web_search input spelling: {rendered}"


__all__ = [
    "UNAVAILABLE",
    "WEB_SEARCH",
    "WEB_SEARCH_RESULT",
    "UnavailableWebSearchPair",
    "WebSearchActionProjection",
    "new_server_tool_call_id",
    "partial_web_search_loss",
    "project_web_search_action",
    "unavailable_web_search_pair",
    "unsolicited_web_search_loss",
    "web_search_call_id_loss",
]
