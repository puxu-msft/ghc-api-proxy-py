from collections.abc import Mapping

SESSION_HEADERS = (
    "x-claude-code-session-id",
    "x-session-id",
    "x-conversation-id",
    "x-chat-session-id",
    "x-thread-id",
    "x-interaction-id",
)


def identify_session(headers: Mapping[str, str]) -> tuple[str | None, str]:
    lowered = {name.lower(): value for name, value in headers.items()}
    session_id = next((lowered[name] for name in SESSION_HEADERS if lowered.get(name)), None)
    return session_id, lowered.get("x-claude-code-agent-id", "main")