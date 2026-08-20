from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
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

    http_client = httpx.AsyncClient()
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
    assert captured["client"] is http_client
