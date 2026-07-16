import copy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AzureAdaptedRequest:
    original_payload: dict[str, Any]
    wire_payload: dict[str, Any]


def adapt_azure_payload(
    payload: dict[str, Any],
    *,
    deployment: str,
) -> AzureAdaptedRequest:
    original = copy.deepcopy(payload)
    wire = copy.deepcopy(payload)
    wire["model"] = deployment
    return AzureAdaptedRequest(original, wire)