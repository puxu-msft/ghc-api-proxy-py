from dataclasses import asdict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.deps import HistoryStoreDependency

router = APIRouter(tags=["history"])


@router.get("/history/api/entries")
async def entries(store: HistoryStoreDependency, limit: int = 100) -> dict[str, object]:
    return {"data": [asdict(entry) for entry in await store.list_entries(limit=limit)]}


@router.get("/history/api/entries/{entry_id}")
async def entry(entry_id: str, store: HistoryStoreDependency) -> dict[str, object]:
    result = await store.get(entry_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return asdict(result)


@router.websocket("/history/ws")
async def history_websocket(websocket: WebSocket, store: HistoryStoreDependency) -> None:
    await store.websockets.connect(websocket)
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "subscribe":
                await websocket.send_json(
                    {"type": "subscribed", "topic": message.get("topic", "history")}
                )
    except WebSocketDisconnect:
        store.websockets.disconnect(websocket)