from typing import Any

from app.pipeline.approval import ApprovalGate, ApprovalRejectedError
from app.pipeline.context import RequestContext


async def apply_approval_guard(
    payload: dict[str, Any],
    *,
    model: str,
    endpoint: str,
    gate: ApprovalGate,
) -> dict[str, Any]:
    if not gate.enabled:
        return payload
    context = RequestContext(
        original_model=model,
        resolved_model=model,
        original_payload=payload,
        endpoint=endpoint,
    )
    result = await gate.wait_for_approval(context)
    if result.status == "rejected":
        raise ApprovalRejectedError(result.reason)
    return result.modified_payload or payload