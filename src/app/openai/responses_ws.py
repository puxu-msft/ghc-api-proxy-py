from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from httpx_ws import aconnect_ws

TERMINAL_EVENTS = frozenset(
    {
        "response.completed",
        "response.failed",
        "response.incomplete",
        "error",
    }
)


class ResponsesWebSocketClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        url: str,
        *,
        connect: Callable[..., Any] = aconnect_ws,
        queue_size: int = 32,
    ) -> None:
        self._http = http_client
        self._url = url
        self._connect = connect
        self._queue_size = queue_size

    async def create_response(
        self,
        frame: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        async with self._connect(
            self._url,
            client=self._http,
            queue_size=self._queue_size,
        ) as websocket:
            await websocket.send_json(frame)
            while True:
                event: dict[str, Any] = await websocket.receive_json()
                yield event
                if event.get("type") in TERMINAL_EVENTS:
                    return