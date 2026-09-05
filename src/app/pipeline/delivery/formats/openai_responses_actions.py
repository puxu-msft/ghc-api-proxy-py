"""Classify whether a Responses output item requires the client to act."""

from typing import Any, cast

from app.pipeline.delivery.assembling import ClientAction
from app.pipeline.response_action import (
    ClientActionRequirement,
    classify_responses_client_action,
)


def client_action_requirement(item: dict[str, Any]) -> ClientActionRequirement:
    """Read the observable requirement from the shared Responses classifier."""
    return classify_responses_client_action(item).requirement


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
