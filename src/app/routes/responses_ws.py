from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.deps import OpenAIClientDependency
from app.models.openai import ResponsesRequest
from app.streaming.openai_sse import parse_sse_json

router = APIRouter(tags=["openai-responses"])


@router.websocket("/responses")
async def responses_websocket(
    websocket: WebSocket,
    client: OpenAIClientDependency,
) -> None:
    await websocket.accept()
    upstream = None
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
        request = ResponsesRequest.model_validate(payload)
        upstream = await client.responses(request)
        async for event in parse_sse_json(upstream.aiter_raw()):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    finally:
        if upstream is not None:
            await upstream.aclose()