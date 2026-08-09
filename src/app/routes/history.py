import json
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Response, WebSocket, WebSocketDisconnect

from app.deps import HistoryStoreDependency

router = APIRouter(tags=["history"])


@router.get("/history/api/entries")
async def entries(
    store: HistoryStoreDependency,
    limit: int = 100,
    model: str | None = None,
    endpoint: str | None = None,
    status: str | None = None,
    session_id: str | None = None,
) -> dict[str, object]:
    values = await store.list_entries(limit=limit)
    values = [
        entry
        for entry in values
        if (model is None or entry.model.resolved == model)
        and (endpoint is None or entry.endpoint == endpoint)
        and (status is None or entry.status == status)
        and (session_id is None or entry.session_id == session_id)
    ]
    return {"data": [asdict(entry) for entry in values]}


@router.get("/history/api/entries/{entry_id}")
async def entry(entry_id: str, store: HistoryStoreDependency) -> dict[str, object]:
    result = await store.get(entry_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return asdict(result)


@router.get("/history/api/entries/{entry_id}/export")
async def export_entry(entry_id: str, store: HistoryStoreDependency) -> Response:
    return Response(
        content=json.dumps(await entry(entry_id, store)),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{entry_id}.json"'},
    )


@router.post("/history/api/entries/{entry_id}/pin")
async def pin(entry_id: str, store: HistoryStoreDependency) -> dict[str, bool]:
    if not await store.set_pinned(entry_id, True):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"pinned": True}


@router.post("/history/api/entries/{entry_id}/unpin")
async def unpin(entry_id: str, store: HistoryStoreDependency) -> dict[str, bool]:
    if not await store.set_pinned(entry_id, False):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"pinned": False}


@router.get("/history/api/sessions")
async def sessions(store: HistoryStoreDependency) -> dict[str, object]:
    entries_value = await store.list_entries(limit=1000)
    grouped: dict[str, int] = {}
    for value in entries_value:
        if value.session_id:
            grouped[value.session_id] = grouped.get(value.session_id, 0) + 1
    return {"data": [{"session_id": key, "request_count": count} for key, count in grouped.items()]}


@router.get("/history/api/stats")
async def stats(store: HistoryStoreDependency) -> dict[str, int]:
    values = await store.list_entries(limit=10000)
    return {
        "total": len(values),
        "completed": sum(value.status == "completed" for value in values),
        "failed": sum(value.status in ("failed", "aborted", "interrupted") for value in values),
    }


@router.get("/history/api/export")
async def export_all(store: HistoryStoreDependency) -> Response:
    values = [asdict(value) for value in await store.list_entries(limit=10000)]
    return Response(content=json.dumps(values), media_type="application/json")


@router.websocket("/history/ws")
async def history_websocket(websocket: WebSocket, store: HistoryStoreDependency) -> None:
    if not await store.websockets.connect(websocket):
        return
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "subscribe":
                topic = str(message.get("topic", "history"))
                store.websockets.subscribe(websocket, topic)
                await websocket.send_json(
                    {"type": "subscribed", "topic": topic}
                )
    except WebSocketDisconnect:
        store.websockets.disconnect(websocket)