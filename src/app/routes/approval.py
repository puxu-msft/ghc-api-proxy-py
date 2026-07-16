from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.deps import ApprovalGateDependency, HistoryStoreDependency

router = APIRouter(prefix="/api/approval", tags=["approval"])


@router.get("/pending")
async def pending(gate: ApprovalGateDependency) -> list[dict[str, Any]]:
    return await gate.get_pending()


@router.get("/{approval_id}")
async def detail(approval_id: str, gate: ApprovalGateDependency) -> dict[str, Any]:
    value = await gate.get_detail(approval_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return value


@router.post("/{approval_id}/approve")
async def approve(approval_id: str, gate: ApprovalGateDependency) -> dict[str, bool]:
    return {"resolved": await gate.approve(approval_id)}


@router.post("/{approval_id}/reject")
async def reject(
    approval_id: str,
    gate: ApprovalGateDependency,
    body: dict[str, Any] | None = None,
) -> dict[str, bool]:
    reason = str((body or {}).get("reason", ""))
    return {"resolved": await gate.reject(approval_id, reason)}


@router.post("/{approval_id}/modify")
async def modify(
    approval_id: str,
    body: dict[str, Any],
    gate: ApprovalGateDependency,
) -> dict[str, bool]:
    return {"resolved": await gate.modify_and_approve(approval_id, body)}


@router.websocket("/ws")
async def approval_websocket(
    websocket: WebSocket,
    store: HistoryStoreDependency,
) -> None:
    await store.websockets.connect(websocket, "approval")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        store.websockets.disconnect(websocket)