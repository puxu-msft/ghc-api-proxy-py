from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, set[str]] = {}
        self._closing_topics: set[str] = set()

    async def connect(self, websocket: WebSocket, topic: str = "history") -> bool:
        await websocket.accept()
        if topic in self._closing_topics:
            await websocket.close(code=1012, reason="server_restarting")
            return False
        self._connections[websocket] = {topic}
        return True

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

    async def close_topics(
        self,
        topics: set[str],
        *,
        code: int,
        reason: str,
    ) -> int:
        self._closing_topics.update(topics)
        targets = [
            websocket
            for websocket, subscribed_topics in list(self._connections.items())
            if topics & subscribed_topics
        ]
        failures: list[BaseException] = []
        for websocket in targets:
            try:
                await websocket.close(code=code, reason=reason)
            except BaseException as error:
                failures.append(error)
            finally:
                self.disconnect(websocket)
        if failures:
            raise BaseExceptionGroup("observer close failed", failures)
        return len(targets)

    async def close_topic(
        self,
        topic: str,
        *,
        code: int,
        reason: str,
    ) -> int:
        return await self.close_topics({topic}, code=code, reason=reason)

    def reopen_topics(self, topics: set[str]) -> None:
        self._closing_topics.difference_update(topics)
