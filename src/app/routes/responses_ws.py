from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from httpx_ws import WebSocketDisconnect as UpstreamWebSocketDisconnect
from httpx_ws import WebSocketNetworkError, WebSocketUpgradeError
from pydantic import ValidationError

from app.deps import (
    ApprovalGateDependency,
    ResponsesWSClientDependency,
    RuntimeDependency,
)
from app.models.openai import ResponsesRequest
from app.pipeline.approval import ApprovalRejectedError
from app.pipeline.protocol_guard import apply_approval_guard
from app.routes.protocol_history import (
    finalize_protocol_history,
    start_protocol_history,
)

router = APIRouter(tags=["openai-responses"])


@router.websocket("/responses")
async def responses_websocket(
    websocket: WebSocket,
    ws_client: ResponsesWSClientDependency,
    gate: ApprovalGateDependency,
    runtime: RuntimeDependency,
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
        request = ResponsesRequest.model_validate(payload)
        payload = await apply_approval_guard(
            request.model_dump(mode="json", exclude_unset=True),
            model=request.model,
            endpoint="openai-responses-websocket",
            gate=gate,
        )
        history_entry = start_protocol_history(
            runtime,
            endpoint="openai-responses-websocket",
            model=request.model,
            payload=payload,
        )
        completed = False
        try:
            async for event in ws_client.create_response(
                {"type": "response.create", "response": payload}
            ):
                await websocket.send_json(event)
            completed = True
        finally:
            await finalize_protocol_history(
                runtime,
                history_entry,
                status="completed" if completed else "aborted",
            )
    except WebSocketDisconnect:
        return
    except ApprovalRejectedError as error:
        await websocket.send_json(
            {
                "type": "error",
                "error": {"message": f"Rejected: {error}"},
            }
        )
        await websocket.close(code=4003)
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
