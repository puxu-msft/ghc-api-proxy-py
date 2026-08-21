from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
import pytest

from app.openai.responses_ws import ResponsesWebSocketClient


class FakeSession:
    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.frames = iter(
            [
                {"type": "response.created"},
                {"type": "response.completed"},
            ]
        )

    async def send_json(self, data: Any) -> None:
        self.sent.append(data)

    async def receive_json(self) -> Any:
        return next(self.frames)


@pytest.mark.asyncio
async def test_responses_ws_client_uses_bounded_queue_and_yields_frames() -> None:
    session = FakeSession()
    captured: dict[str, Any] = {}

    @asynccontextmanager
    async def connect(url: str, **kwargs: Any) -> AsyncGenerator[FakeSession]:
        captured["url"] = url
        captured.update(kwargs)
        yield session

    http_client = httpx2.AsyncClient()
    client = ResponsesWebSocketClient(
        http_client,
        "wss://copilot.example/responses",
        connect=connect,
    )
    try:
        frames = [
            frame
            async for frame in client.create_response(
                {"type": "response.create", "response": {"model": "gpt"}}
            )
        ]
    finally:
        await http_client.aclose()

    assert frames == [{"type": "response.created"}, {"type": "response.completed"}]
    assert session.sent == [
        {"type": "response.create", "response": {"model": "gpt"}}
    ]
    assert captured["url"] == "wss://copilot.example/responses"
    assert captured["queue_size"] == 32
    assert "client" not in captured


@pytest.mark.asyncio
async def test_responses_ws_client_opens_the_socket_on_its_own_http_client() -> None:
    """The default `connect` binds the shared client rather than passing it as `client=`.

    That kwarg was httpx-ws's way in; `httpx2.AsyncClient.websocket` is a method on the client, so an injected replacement stops being able to see which client is in use. This pins the one thing the switch could have quietly dropped: the socket is opened on the client this object was given, not on a fresh one.
    """
    opened: dict[str, Any] = {}

    class RecordingClient(httpx2.AsyncClient):
        @asynccontextmanager
        async def websocket(self, url: Any, **kwargs: Any) -> AsyncGenerator[FakeSession]:  # type: ignore[override]
            opened["self"] = self
            opened["url"] = url
            opened.update(kwargs)
            yield FakeSession()

    http_client = RecordingClient()
    client = ResponsesWebSocketClient(
        http_client,
        "wss://copilot.example/responses",
        queue_size=7,
    )
    try:
        frames = [
            frame
            async for frame in client.create_response({"type": "response.create"})
        ]
    finally:
        await http_client.aclose()

    assert frames == [{"type": "response.created"}, {"type": "response.completed"}]
    assert opened["self"] is http_client
    assert opened["url"] == "wss://copilot.example/responses"
    assert opened["queue_size"] == 7
