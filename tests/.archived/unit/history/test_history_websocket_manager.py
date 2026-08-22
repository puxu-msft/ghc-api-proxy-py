from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import WebSocket

from app.history.ws import WebSocketManager


@pytest.mark.asyncio
async def test_close_topic_sends_1012_only_to_matching_observers() -> None:
    manager = WebSocketManager()
    history = Mock()
    history.accept = AsyncMock()
    history.close = AsyncMock()
    approval = Mock()
    approval.accept = AsyncMock()
    approval.close = AsyncMock()
    history_ws = cast(WebSocket, history)
    approval_ws = cast(WebSocket, approval)
    await manager.connect(history_ws, "history")
    await manager.connect(approval_ws, "approval")

    closed = await manager.close_topic(
        "history",
        code=1012,
        reason="server_restarting",
    )

    assert closed == 1
    history.close.assert_awaited_once_with(code=1012, reason="server_restarting")
    approval.close.assert_not_awaited()
    manager.subscribe(approval_ws, "history")
    assert await manager.close_topic("history", code=1012, reason="again") == 1
    approval.close.assert_awaited_once_with(code=1012, reason="again")

    manager.reopen_topics({"history"})
    late = Mock()
    late.accept = AsyncMock()
    late.close = AsyncMock()
    await manager.connect(cast(WebSocket, late), "history")
    late.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_topics_handles_late_connections_and_continues_after_failure() -> None:
    manager = WebSocketManager()
    failing = Mock()
    failing.accept = AsyncMock()
    failing.close = AsyncMock(side_effect=RuntimeError("gone"))
    healthy = Mock()
    healthy.accept = AsyncMock()
    healthy.close = AsyncMock()
    await manager.connect(cast(WebSocket, failing), "history")
    await manager.connect(cast(WebSocket, healthy), "approval")

    with pytest.raises(BaseExceptionGroup, match="observer close failed"):
        await manager.close_topics(
            {"history", "approval"},
            code=1012,
            reason="server_restarting",
        )
    healthy.close.assert_awaited_once_with(code=1012, reason="server_restarting")

    late = Mock()
    late.accept = AsyncMock()
    late.close = AsyncMock()
    await manager.connect(cast(WebSocket, late), "history")
    late.accept.assert_awaited_once()
    late.close.assert_awaited_once_with(code=1012, reason="server_restarting")
