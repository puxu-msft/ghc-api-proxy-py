from pathlib import Path

import pytest

from app.context.consumers import ContextEventBus
from app.context.error_persistence import ErrorPersistenceConsumer
from app.pipeline.context import RequestContext
from app.shutdown import ShutdownManager, ShutdownPhase


@pytest.mark.asyncio
async def test_context_bus_dispatches_and_persists_error_off_loop(tmp_path: Path) -> None:
    bus = ContextEventBus()
    consumer = ErrorPersistenceConsumer(tmp_path)
    bus.subscribe(consumer)
    context = RequestContext(original_model="m", original_payload={})

    await bus.publish("failed", context, {"message": "boom"})

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert "boom" in files[0].read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_shutdown_manager_awaits_phase_callbacks() -> None:
    called: list[ShutdownPhase] = []

    async def callback() -> None:
        assert manager.current_phase is not None
        called.append(manager.current_phase)

    manager = ShutdownManager(
        setup=callback,
        graceful_wait=callback,
        abort=callback,
        force_close=callback,
    )
    await manager.run()
    assert called == list(ShutdownPhase)
