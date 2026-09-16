import anyio
import httpx
from fastapi import FastAPI, WebSocket
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

app = FastAPI()


@app.websocket("/responses")
async def responses(websocket: WebSocket) -> None:
    await websocket.accept()
    request = await websocket.receive_json()
    await websocket.send_json({"type": "response.created", "echo": request})
    await anyio.sleep(0.05)
    await websocket.send_json({"type": "response.completed"})
    await websocket.close()


async def main() -> None:
    transport = ASGIWebSocketTransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport) as client,
        aconnect_ws(
            "http://test/responses",
            client=client,
            queue_size=1,
            keepalive_ping_interval_seconds=None,
        ) as websocket,
    ):
        await websocket.send_json({"type": "response.create"})
        first = await websocket.receive_json()
        assert first["type"] == "response.created"
        assert first["echo"] == {"type": "response.create"}
        second = await websocket.receive_json()
        assert second == {"type": "response.completed"}
    print("PASS: httpx-ws ASGI transport delivers messages incrementally with bounded queue")


if __name__ == "__main__":
    anyio.run(main)