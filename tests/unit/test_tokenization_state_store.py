from pathlib import Path
from threading import Event

import anyio
import pytest
from anyio.to_thread import run_sync

from app.tokenization.state_store import TokenizationStateStore


class BlockingStateStore(TokenizationStateStore):
    def __init__(self, path: Path, started: Event, release: Event) -> None:
        super().__init__(path)
        self._started = started
        self._release = release

    def _atomic_write(self, data: bytes) -> None:
        self._started.set()
        if not self._release.wait(timeout=5):
            raise TimeoutError("test did not release atomic write")
        super()._atomic_write(data)


@pytest.mark.asyncio
async def test_state_store_round_trip_and_dirty_lifecycle(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "tokenization.json"
    state = TokenizationStateStore(path)
    state.calibration.learn("anthropic", "model", 10_000, 20_000)
    state.prompt_limits.record(
        "anthropic",
        "model",
        current=20_001,
        limit=20_000,
        source="anthropic_messages_error",
    )

    assert state.dirty is True
    assert await state.flush() is True
    assert state.dirty is False

    restored = TokenizationStateStore(path)
    await restored.load()

    assert restored.calibration.calibrate("anthropic", "model", 10_000) == 20_000
    observation = restored.prompt_limits.get("anthropic", "model")
    assert observation is not None
    assert observation.observed_limit == 20_000
    assert restored.dirty is False


@pytest.mark.asyncio
async def test_corrupted_state_starts_empty(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "tokenization.json"
    path.write_text("{broken", encoding="utf-8")
    state = TokenizationStateStore(path)

    await state.load()

    assert state.snapshot()["calibration"] == {}
    assert "corrupted" in caplog.text


@pytest.mark.asyncio
async def test_learning_during_flush_remains_dirty(tmp_path: Path) -> None:
    started = Event()
    release = Event()
    state = BlockingStateStore(tmp_path / "state.json", started, release)
    state.calibration.learn("anthropic", "model", 10_000, 11_000)
    result: list[bool] = []

    async def flush() -> None:
        result.append(await state.flush())

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(flush)
        assert await run_sync(started.wait, 5)
        state.calibration.learn("anthropic", "model", 20_000, 22_000)
        release.set()

    assert result == [True]
    assert state.dirty is True
    assert await state.flush() is True
    assert state.dirty is False