from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from httpx_ws import WebSocketDisconnect as UpstreamWebSocketDisconnect
from httpx_ws import WebSocketNetworkError, WebSocketUpgradeError
from pydantic import ValidationError

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
    except WebSocketUpgradeError as error:
        await websocket.send_json(
            {
                "type": "error",
                "error": {
                    "message": "Upstream rejected WebSocket upgrade",
                    "status_code": error.response.status_code,
                },
            }
        )
        await websocket.close(code=4000)
    except (WebSocketNetworkError, UpstreamWebSocketDisconnect) as error:
        await websocket.send_json(
            {"type": "error", "error": {"message": str(error)}}
        )
        await websocket.close(code=4000)
    except ValidationError as error:
        await websocket.send_json(
            {
                "type": "error",
                "error": {"message": error.errors()[0]["msg"]},
            }
        )
        await websocket.close(code=4000)