from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx2

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
        http_client: httpx2.AsyncClient,
        url: str,
        *,
        connect: Callable[..., Any] | None = None,
        queue_size: int = 32,
    ) -> None:
        self._http = http_client
        self._url = url
        self._connect = connect if connect is not None else self._open
        self._queue_size = queue_size

    def _open(self, url: str, **kwargs: Any) -> Any:
        """The default `connect`, kept injectable so tests can hand in a session of their own.

        `httpx2.AsyncClient.websocket` rather than `httpx_ws.aconnect_ws`: httpx-ws builds on the pre-fork httpx and normalises only `httpcore.ReadError` / `WriteError`, while an httpx2 client's stream raises the `httpcore2` ones, so its error path would stop recognising a dropped connection. httpx2 vendored httpx-ws 0.9.0 for this and has fixed it since. The client is bound here instead of passed as `client=`, which is the one call-shape difference between the two.
        """
        return self._http.websocket(url, **kwargs)

    async def create_response(
        self,
        frame: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        async with self._connect(
            self._url,
            queue_size=self._queue_size,
        ) as websocket:
            await websocket.send_json(frame)
            while True:
                event: dict[str, Any] = await websocket.receive_json()
                yield event
                if event.get("type") in TERMINAL_EVENTS:
                    return
