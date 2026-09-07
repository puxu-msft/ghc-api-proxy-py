"""Extract the client's logical conversation identity before header shaping."""

from collections.abc import Mapping

INTERACTION_ID_HEADERS: tuple[str, ...] = (
    "x-claude-code-session-id",
    "x-session-id",
    "x-conversation-id",
    "x-chat-session-id",
    "x-thread-id",
    "x-interaction-id",
)

AGENT_ID_HEADERS: tuple[str, ...] = (
    "x-claude-code-agent-id",
    "x-agent-id",
)

_INTERACTION_ID_HEADER_NAMES = frozenset(INTERACTION_ID_HEADERS)


def interaction_id_from_headers(headers: Mapping[str, str]) -> str | None:
    lowered = {
        str(name).lower(): str(value).strip()
        for name, value in headers.items()
    }
    for name in INTERACTION_ID_HEADERS:
        value = lowered.get(name, "")
        if value:
            return value
    return None


def without_interaction_id_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Remove semantic identity headers after extraction, not security headers."""
    return {
        str(name): str(value)
        for name, value in headers.items()
        if str(name).lower() not in _INTERACTION_ID_HEADER_NAMES
    }


def agent_id_from_headers(headers: Mapping[str, str]) -> str | None:
    lowered = {
        str(name).lower(): str(value).strip()
        for name, value in headers.items()
    }
    for name in AGENT_ID_HEADERS:
        value = lowered.get(name, "")
        if value:
            return value
    return None
