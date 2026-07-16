from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, set[str]] = {}

    async def connect(self, websocket: WebSocket, topic: str = "history") -> None:
        await websocket.accept()
        self._connections[websocket] = {topic}

    def subscribe(self, websocket: WebSocket, topic: str) -> None:
        self._connections.setdefault(websocket, set()).add(topic)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    async def broadcast(self, message: dict[str, Any], topic: str = "history") -> None:
        disconnected: list[WebSocket] = []
        for websocket, topics in self._connections.items():
            if topic not in topics:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)