"""Shared OpenAI Responses terminal semantics.

The stream adapter and buffered response codec receive different envelopes,
but the meaning of completed, incomplete, tool-use, and usage facts is one
protocol rule. This module owns that rule without depending on delivery.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from app.pipeline.translation_driver.usage import (
    ResponsesUsageError,
    anthropic_usage_from_responses,
)

MAX_TOKENS = "max_tokens"
END_TURN = "end_turn"
TOOL_USE = "tool_use"
CONTENT_FILTER = "content_filter"
FINISHED_STOP_REASONS = frozenset({END_TURN, TOOL_USE, ""})
INCOMPLETE_REASONS = {MAX_TOKENS: "max_output_tokens", CONTENT_FILTER: CONTENT_FILTER}


@dataclass(frozen=True, slots=True)
class ResponsesTerminalFacts:
    event_type: str
    seen: bool
    stop_reason: str
    usage: dict[str, Any]
    upstream_usage: dict[str, Any] | None
    status: str = ""


def stop_reason_from_response(
    payload: Mapping[str, Any],
    *,
    has_tool_call: bool,
) -> tuple[str, str | None]:
    """Map one complete Responses body to Anthropic's terminal vocabulary."""
    status = str(payload.get("status", "completed"))
    if status == "incomplete":
        details = payload.get("incomplete_details")
        reason = ""
        if isinstance(details, Mapping):
            reason = str(cast(Mapping[str, Any], details).get("reason", ""))
        if reason == "max_output_tokens":
            return MAX_TOKENS, None
        return reason or "incomplete", None
    if has_tool_call:
        return TOOL_USE, None
    return END_TURN, None


def terminal_facts_from_event(
    kind: str,
    data: Mapping[str, Any],
    *,
    saw_tool_call: bool,
) -> ResponsesTerminalFacts | None:
    """Normalize a streaming terminal event, or return ``None`` for other events."""
    if kind not in {"response.completed", "response.incomplete"}:
        return None
    raw_response = data.get("response")
    response: Mapping[str, Any] = (
        cast(Mapping[str, Any], raw_response)
        if isinstance(raw_response, Mapping)
        else {}
    )
    terminal_response = dict[str, Any](response)
    if kind == "response.incomplete" and "status" not in terminal_response:
        terminal_response["status"] = "incomplete"
    stop_reason, _ = stop_reason_from_response(
        terminal_response,
        has_tool_call=saw_tool_call,
    )
    raw_usage: object = response.get("usage")
    upstream_usage = (
        dict[str, Any](cast(Mapping[str, Any], raw_usage))
        if isinstance(raw_usage, Mapping)
        else None
    )
    usage: dict[str, Any] = {}
    if upstream_usage is not None:
        try:
            usage = anthropic_usage_from_responses(upstream_usage)
        except ResponsesUsageError:
            usage = {}
    return ResponsesTerminalFacts(
        event_type=kind,
        seen=True,
        stop_reason=stop_reason,
        usage=usage,
        upstream_usage=upstream_usage,
        status=str(terminal_response.get("status", "")),
    )


__all__ = [
    "CONTENT_FILTER",
    "END_TURN",
    "FINISHED_STOP_REASONS",
    "INCOMPLETE_REASONS",
    "MAX_TOKENS",
    "TOOL_USE",
    "ResponsesTerminalFacts",
    "stop_reason_from_response",
    "terminal_facts_from_event",
]
