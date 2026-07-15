from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.deps import ResponsesWSClientDependency
from app.models.openai import ResponsesRequest

router = APIRouter(tags=["openai-responses"])


@router.websocket("/responses")
async def responses_websocket(
    websocket: WebSocket,
    ws_client: ResponsesWSClientDependency,
) -> None:
    await websocket.accept()
    try:
        frame = await websocket.receive_json()
        if frame.get("type") != "response.create" or not isinstance(
            frame.get("response"), dict
        ):
            await websocket.send_json(
                {"type": "error", "error": {"message": "Expected response.create"}}
            )
            await websocket.close(code=4000)
            return
        payload = dict(frame["response"])
        payload["stream"] = True
        ResponsesRequest.model_validate(payload)
        async for event in ws_client.create_response(
            {"type": "response.create", "response": payload}
        ):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return