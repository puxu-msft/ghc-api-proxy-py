"""Classify whether a Responses output item requires the client to act."""

from typing import Any, cast

from app.pipeline.delivery.assembling import ClientAction, ClientActionRequirement

_ALWAYS_CLIENT_ACTION = frozenset(
    {
        "function_call",
        "custom_tool_call",
        "computer_call",
        "local_shell_call",
        "apply_patch_call",
        "mcp_approval_request",
    }
)

_NEVER_CLIENT_ACTION = frozenset(
    {
        "web_search_call",
        "file_search_call",
        "code_interpreter_call",
        "image_generation_call",
        "mcp_call",
        "reasoning",
        "message",
    }
)


def client_action_requirement(item: dict[str, Any]) -> ClientActionRequirement:
    """Classify the item's client-action requirement without making policy decisions.

    The conditional item types carry their execution side on the item itself. A missing or unfamiliar discriminator is unknown rather than either answer: the buffering policy may conservatively release it, while observability still reports that the fact was not established.
    """
    raw_type = item.get("type")
    if not isinstance(raw_type, str) or not raw_type:
        return ClientActionRequirement.UNKNOWN
    if raw_type in _ALWAYS_CLIENT_ACTION:
        return ClientActionRequirement.REQUIRED
    if raw_type in _NEVER_CLIENT_ACTION:
        return ClientActionRequirement.NOT_REQUIRED
    if raw_type == "tool_search_call":
        execution = item.get("execution")
        if execution == "client":
            return ClientActionRequirement.REQUIRED
        if execution == "server":
            return ClientActionRequirement.NOT_REQUIRED
        return ClientActionRequirement.UNKNOWN
    if raw_type == "shell_call":
        environment = item.get("environment")
        if not isinstance(environment, dict):
            return ClientActionRequirement.UNKNOWN
        environment_type = cast(dict[str, Any], environment).get("type")
        if environment_type == "local":
            return ClientActionRequirement.REQUIRED
        if environment_type == "container_reference":
            return ClientActionRequirement.NOT_REQUIRED
        return ClientActionRequirement.UNKNOWN
    return ClientActionRequirement.UNKNOWN


def read_responses_client_actions(response: dict[str, Any]) -> tuple[list[ClientAction], bool]:
    """Read client-action facts from the terminal response's authoritative output snapshot."""
    raw_output = response.get("output")
    if not isinstance(raw_output, list):
        return [], False
    actions: list[ClientAction] = []
    for output_index, raw_item in enumerate(cast(list[object], raw_output)):
        item = cast(dict[str, Any], raw_item) if isinstance(raw_item, dict) else {}
        requirement = client_action_requirement(item)
        if requirement is ClientActionRequirement.NOT_REQUIRED:
            continue
        raw_type = item.get("type")
        raw_name = item.get("name")
        actions.append(
            ClientAction(
                requirement=requirement,
                type=raw_type if isinstance(raw_type, str) and raw_type else "unknown",
                name=raw_name if isinstance(raw_name, str) and raw_name else "",
                output_index=output_index,
            )
        )
    return actions, True
