"""Whether a Responses output item leaves work for the client.

The observation and the delivery policy ask related but different questions. The observation says what can be established from the item; the delivery policy also has to choose a safe direction when that answer is unknown. Keeping both answers in one classification lets the direct passthrough preserve its existing release behaviour without letting the console turn a conservative policy fallback into a concrete item type.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast


class ClientActionRequirement(StrEnum):
    REQUIRED = "required"
    NOT_REQUIRED = "not_required"
    UNKNOWN = "unknown"


class ClientActionBasis(StrEnum):
    KNOWN_CLIENT_ACTION = "known_client_action"
    KNOWN_SERVER_ACTION = "known_server_action"
    EXECUTION_CLIENT = "execution_client"
    EXECUTION_SERVER = "execution_server"
    EXECUTION_UNRECOGNIZED = "execution_unrecognized"
    LOCAL_SHELL_DEFAULT = "local_shell_default"
    CONTAINER_EXECUTION = "container_execution"
    LOCAL_SHELL_ENVIRONMENT = "local_shell_environment"
    UNKNOWN_TYPE_FALLBACK = "unknown_type_fallback"


@dataclass(frozen=True, slots=True)
class ClientActionObservation:
    requirement: ClientActionRequirement
    basis: ClientActionBasis
    # The direct leg's existing buffering answer. It is deliberately not derived from `requirement`: two unknown observations have opposite answers under the compatibility policy.
    delivery_required: bool


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


def classify_responses_client_action(item: Mapping[str, Any]) -> ClientActionObservation:
    """Classify one item without imposing a closed item taxonomy.

    Unknown future types stay unknown to observation and retain the direct leg's conservative early-release answer. `tool_search_call` is the counter-example that prevents collapsing those two fields: an absent or unrecognised execution value is also observationally unknown, but the established delivery policy holds it rather than releasing it.
    """
    raw_type = item.get("type")
    item_type = raw_type if isinstance(raw_type, str) else ""
    if item_type in _ALWAYS_CLIENT_ACTION:
        return ClientActionObservation(
            requirement=ClientActionRequirement.REQUIRED,
            basis=ClientActionBasis.KNOWN_CLIENT_ACTION,
            delivery_required=True,
        )
    if item_type in _NEVER_CLIENT_ACTION:
        return ClientActionObservation(
            requirement=ClientActionRequirement.NOT_REQUIRED,
            basis=ClientActionBasis.KNOWN_SERVER_ACTION,
            delivery_required=False,
        )
    if item_type == "tool_search_call":
        execution = item.get("execution")
        if execution == "client":
            return ClientActionObservation(
                requirement=ClientActionRequirement.REQUIRED,
                basis=ClientActionBasis.EXECUTION_CLIENT,
                delivery_required=True,
            )
        if execution == "server":
            return ClientActionObservation(
                requirement=ClientActionRequirement.NOT_REQUIRED,
                basis=ClientActionBasis.EXECUTION_SERVER,
                delivery_required=False,
            )
        return ClientActionObservation(
            requirement=ClientActionRequirement.UNKNOWN,
            basis=ClientActionBasis.EXECUTION_UNRECOGNIZED,
            delivery_required=False,
        )
    if item_type == "shell_call":
        environment = item.get("environment")
        if not isinstance(environment, Mapping):
            return ClientActionObservation(
                requirement=ClientActionRequirement.REQUIRED,
                basis=ClientActionBasis.LOCAL_SHELL_DEFAULT,
                delivery_required=True,
            )
        environment_mapping = cast(Mapping[str, Any], environment)
        if "container" in str(environment_mapping.get("type", "")):
            return ClientActionObservation(
                requirement=ClientActionRequirement.NOT_REQUIRED,
                basis=ClientActionBasis.CONTAINER_EXECUTION,
                delivery_required=False,
            )
        return ClientActionObservation(
            requirement=ClientActionRequirement.REQUIRED,
            basis=ClientActionBasis.LOCAL_SHELL_ENVIRONMENT,
            delivery_required=True,
        )
    return ClientActionObservation(
        requirement=ClientActionRequirement.UNKNOWN,
        basis=ClientActionBasis.UNKNOWN_TYPE_FALLBACK,
        delivery_required=True,
    )


__all__ = [
    "ClientActionBasis",
    "ClientActionObservation",
    "ClientActionRequirement",
    "classify_responses_client_action",
]
